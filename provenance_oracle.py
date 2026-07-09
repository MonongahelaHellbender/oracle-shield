#!/usr/bin/env python3
"""
provenance-oracle — deterministic source-provenance gate for cited DOIs.

Checks the PROVENANCE of a citation, never the truth of the claim it supports:
  1. EXISTENCE  — does the DOI resolve in the Handle System (doi.org)? Catches fabricated /
                  LLM-hallucinated citations. (Handle API, not publisher pages, so no bot-blocking.)
                  This leg is registration-agency-agnostic: it resolves Crossref AND DataCite
                  (arXiv) DOIs alike.
  2. METADATA   — read the DOI's actual record and cross-check the cited title/year/author.
                  Crossref DOIs use the Crossref works API; arXiv / DataCite DOIs use the
                  DataCite REST API (api.datacite.org). Catches the wrong-referent citation.
  3. RETRACTION — does Crossref list a retraction/withdrawal notice targeting this DOI?
                  (The Retraction Watch database is folded into Crossref metadata.) DataCite
                  carries no equivalent retraction feed, so this leg is Crossref-only.

Verdicts (fail-closed):
  SOURCE_OK          DOI resolves and its metadata is confirmable — for Crossref DOIs, also
                     "no retraction/withdrawal notice found"; for DataCite/arXiv DOIs, existence
                     + metadata only (retraction status is not tracked in DataCite — see `why`)
  SOURCE_RETRACTED   a retraction / withdrawal / removal notice targets this DOI (Crossref only)
  SOURCE_FLAGGED     a correction / erratum / expression-of-concern targets it (read it before citing)
  SOURCE_NOT_FOUND   the Handle System does not resolve it — fabricated or mistyped
  DEFERRED           network failure, rate limit, or a DOI that resolves but is registered with
                     neither Crossref nor DataCite (some other agency we cannot read here) —
                     an honest hole, never a guess

Honest scope:
  * SOURCE_OK means "exists and carries no retraction notice" — it does NOT mean good science.
  * This is a PRE-GATE, deliberately NOT registered as an oracle-shield claim lane: passing
    provenance never SUPPORTS a claim; only failing it disqualifies the citation as evidence.
  * Prior art: Zotero ships Retraction Watch alerts; scite grades citations. The job here is the
    fail-closed verdict spine for AI-EMITTED citations, with a selftest that must pass first.

Pure standard library. Run:
  python3 provenance_oracle.py --selftest              # planted cases (injected transport); must pass first
  python3 provenance_oracle.py --check "10.1016/S0140-6736(97)11096-0"
  python3 provenance_oracle.py --check "The result (doi:10.1038/nature14539) shows..."
  python3 provenance_oracle.py --check "arXiv:2606.16541"   # bare arXiv id -> 10.48550/arXiv.2606.16541
  python3 provenance_oracle.py --live-test             # known-answer network probes
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# Bumped whenever verdict logic changes (resolvers, checks, thresholds). Downstream verdict caches
# (e.g. eval_hallmark) key on this so a resolver upgrade invalidates stale verdicts instead of
# silently replaying them.
__version__ = "0.7.0"

SOURCE_OK = "SOURCE_OK"
SOURCE_RETRACTED = "SOURCE_RETRACTED"
SOURCE_FLAGGED = "SOURCE_FLAGGED"
SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
SOURCE_MISMATCH = "SOURCE_MISMATCH"          # DOI is real but belongs to a DIFFERENT work than cited
DEFERRED = "DEFERRED"

MAILTO = "mellison.docs@gmail.com"          # polite-pool identification for Crossref
TIMEOUT = 15

_FATAL_TYPES = {"retraction", "withdrawal", "removal", "retracted"}
_FLAG_TYPES = {"correction", "erratum", "expression_of_concern", "concern", "partial_retraction", "addendum"}

# DOI syntax per Crossref guidance; trailing sentence punctuation stripped after match.
_DOI_RX = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>]+)", re.I)

# arXiv identifiers. arXiv registers a DataCite DOI 10.48550/arXiv.<id> for every paper, so a bare
# id (or an "arXiv:"-prefixed one) is normalized to that canonical DOI and checked via DataCite.
# New-style id shape only: YYMM.NNNNN (+ optional version). The month is validated (01-12) so a
# stray decimal in prose does not masquerade as an id.
_ARXIV_PREFIX_RX = re.compile(r"arxiv:\s*(\d{4}\.\d{4,5}(?:v\d+)?)", re.I)
_ARXIV_ID_RX = re.compile(r"^(\d{2})(\d{2})\.(\d{4,5})(?:v\d+)?$")


def normalize_arxiv_id(s):
    """Bare arXiv id (new-style YYMM.NNNNN, optional vN) -> canonical DataCite DOI, else None.
    The version suffix is dropped: the base DOI is the one arXiv registers and always resolves."""
    if not isinstance(s, str):
        return None
    m = _ARXIV_ID_RX.match(s.strip())
    if not m:
        return None
    yy, mm, num = m.groups()
    if not 1 <= int(mm) <= 12:                           # month gate: rejects e.g. 1334.5678
        return None
    return f"10.48550/arXiv.{yy}{mm}.{num}"


def extract_doi(text):
    """First DOI in free text, or a normalized arXiv id, or None.
    Precedence: a full DOI (handles doi: prefixes and https://doi.org/ URLs) wins; then an
    "arXiv:"-prefixed id anywhere in the text; then a bare arXiv id standing as the whole input
    (bare ids are NOT scanned out of arbitrary prose, to avoid matching stray decimals)."""
    if not isinstance(text, str):
        return None
    m = _DOI_RX.search(text)
    if m:
        return m.group(1).rstrip(".,;:)]}\"'") or None
    m = _ARXIV_PREFIX_RX.search(text)
    if m:
        return normalize_arxiv_id(m.group(1))
    return normalize_arxiv_id(text.strip())


# ── transport (injectable for the selftest; real network only at the edges) ──────────

def _http_json(url):
    """GET url -> (status_code, parsed_json_or_None). Raises on transport-level failure."""
    req = urllib.request.Request(url, headers={"User-Agent": f"provenance-oracle (mailto:{MAILTO})"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:                # 4xx/5xx: a real answer, not a failure
        return exc.code, None


def real_handle_lookup(doi):
    """Handle System API: (status, json). 200/responseCode 1 = the DOI exists."""
    return _http_json("https://doi.org/api/handles/" + urllib.parse.quote(doi, safe=""))


def real_crossref_work(doi):
    """Crossref works record: 200 = Crossref-registered, 404 = not Crossref's DOI."""
    return _http_json("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
                      + f"?mailto={MAILTO}")


def real_crossref_updates(doi):
    """Notices (retractions/corrections/...) that declare they update this DOI."""
    return _http_json("https://api.crossref.org/works?filter=updates:"
                      + urllib.parse.quote(doi, safe="") + f"&rows=20&mailto={MAILTO}")


def real_datacite_work(doi):
    """DataCite REST record: 200 = DataCite-registered (arXiv, preprints, datasets), 404 = not theirs."""
    return _http_json("https://api.datacite.org/dois/" + urllib.parse.quote(doi, safe=""))


REAL_TRANSPORT = {"handle": real_handle_lookup, "work": real_crossref_work,
                  "updates": real_crossref_updates, "datacite": real_datacite_work}


# ── metadata match: the wrong-referent check ─────────────────────────────────────────
# The 2026 hallucination literature's frontier case: a REAL DOI paired with a DIFFERENT paper's
# title/authors sails through existence+retraction checks (cf. CiteCheck arXiv:2605.27700, the
# HALLMARK benchmark). Deterministic, fail-closed comparison: the TITLE dominates — clear
# disjunction refutes the pairing, the ambiguous middle DEFERS, never a guess.

_NONWORD = re.compile(r"[^a-z0-9 ]+")


def _norm(s):
    return re.sub(r"\s+", " ", _NONWORD.sub(" ", str(s).lower())).strip()


def _title_verdict(cited_title, record_title):
    """True match / False mismatch / None ambiguous — normalized containment then token overlap."""
    a, b = _norm(cited_title), _norm(record_title)
    if not a or not b:
        return None
    if a == b or a in b or b in a:
        return True
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    if jac >= 0.7:
        return True
    if jac <= 0.35:
        return False
    return None                                          # gray band -> defer


def _metadata_verdict(cited, message):
    """None = metadata consistent enough to proceed; else a (verdict, why) tuple."""
    rec_titles = message.get("title") or []
    if cited.get("title"):
        if not rec_titles:
            return DEFERRED, "the DOI's record carries no title — cannot confirm the referent"
        tv = _title_verdict(cited["title"], rec_titles[0])
        if tv is False:
            return SOURCE_MISMATCH, (f"the DOI resolves to a DIFFERENT work: record title "
                                     f"{rec_titles[0]!r} does not match the cited title")
        if tv is None:
            return DEFERRED, f"title similarity is ambiguous vs record title {rec_titles[0]!r} — check by hand"
    corroborator_misses = []
    year = None
    for key in ("issued", "published-print", "published-online"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            year = parts[0][0]
            break
    if cited.get("year") and year:
        try:
            if abs(int(cited["year"]) - int(year)) > 1:  # ±1 tolerates online-first vs print
                corroborator_misses.append(f"year (cited {cited['year']}, record {year})")
        except (TypeError, ValueError):
            pass
    if cited.get("author"):
        families = [_norm(a.get("family", "")) for a in message.get("author") or []]
        want = _norm(cited["author"])
        if families and want and not any(want in f or f in want for f in families if f):
            corroborator_misses.append(f"first author (cited {cited['author']!r})")
    if len(corroborator_misses) >= 2 or (corroborator_misses and not cited.get("title")):
        return SOURCE_FLAGGED, "metadata partially disagrees: " + "; ".join(corroborator_misses)
    return None


def _datacite_to_message(attrs):
    """Adapt a DataCite `attributes` record into the Crossref `message` shape _metadata_verdict reads,
    so the same title-dominant, fail-closed wrong-referent logic serves both registration agencies."""
    titles = [t.get("title") for t in (attrs.get("titles") or []) if t.get("title")]
    authors = []
    for c in attrs.get("creators") or []:
        family = c.get("familyName")
        if not family:                                   # DataCite may only give "Family, Given" in `name`
            name = str(c.get("name") or "")
            family = name.split(",")[0].strip() if "," in name else name.strip()
        authors.append({"family": family})
    message = {"title": titles, "author": authors}
    year = attrs.get("publicationYear")
    if year:
        message["issued"] = {"date-parts": [[year]]}
    return message


# ── the gate ──────────────────────────────────────────────────────────────────────────


def _check_datacite(doi, transport, cited=None):
    """DataCite arm — reached only after the Handle System confirmed the DOI resolves but Crossref
    disowns it (HTTP 404). DataCite owns arXiv (10.48550/arXiv.*) and most preprint/dataset DOIs.
    Fail-closed: a DOI resolvable in the Handle System yet registered with NEITHER Crossref nor
    DataCite (some other agency) still DEFERS — its metadata and notices are unreadable here.
    SOURCE_OK here means existence + confirmable metadata; DataCite carries no retraction feed, so
    that guarantee is narrower than the Crossref path and the `why` string says so."""
    try:
        d_status, d_payload = transport["datacite"](doi)
    except Exception as exc:  # noqa: BLE001 — unreachable is NOT nonexistent
        return DEFERRED, f"DataCite lookup failed ({exc}) — cannot confirm the record here"
    if d_status == 404:
        return DEFERRED, ("DOI resolves in the Handle System but is registered with neither "
                          "Crossref nor DataCite — metadata unreadable here, so no verdict")
    if d_status != 200 or not isinstance(d_payload, dict):
        return DEFERRED, f"DataCite lookup inconclusive (HTTP {d_status})"
    attrs = (d_payload.get("data") or {}).get("attributes") or {}
    state = attrs.get("state")
    if state and state not in ("findable", "registered"):  # e.g. 'draft' — not a public, citable DOI
        return DEFERRED, f"DataCite record state is {state!r}, not public — no verdict"
    if cited:                                            # wrong-referent check against DataCite metadata
        mv = _metadata_verdict({k: v for k, v in cited.items() if v}, _datacite_to_message(attrs))
        if mv is not None:                               # MISMATCH / DEFERRED / FLAGGED returned as-is —
            return mv                                    # no Crossref retraction feed to check first
    why = ("resolves; DataCite-registered (e.g. arXiv) — existence confirmed; retraction/withdrawal "
           "status is not tracked in DataCite, so this verdict is existence + metadata only")
    if cited and cited.get("title"):
        why += "; cited title matches the DataCite record"
    return SOURCE_OK, why

def check_doi(doi, transport=None, cited=None):
    """Fail-closed provenance verdict for one DOI. Network trouble -> DEFERRED, never a guess.
    `cited` (optional): {"title": ..., "year": ..., "author": ...} as they appear IN the citation —
    enables the wrong-referent check against the DOI's actual Crossref record."""
    t = transport or REAL_TRANSPORT
    flagged_meta = None
    try:
        status, payload = t["handle"](doi)
    except Exception as exc:  # noqa: BLE001 — unreachable is NOT nonexistent
        return DEFERRED, f"handle lookup failed ({exc}) — cannot distinguish missing from unreachable"
    if status == 200 and isinstance(payload, dict) and payload.get("responseCode") == 1:
        pass                                             # exists — continue to retraction check
    elif status == 404 or (isinstance(payload, dict) and payload.get("responseCode") == 100):
        return SOURCE_NOT_FOUND, "the Handle System does not resolve this DOI — fabricated or mistyped"
    else:
        return DEFERRED, f"handle lookup inconclusive (HTTP {status})"

    try:
        w_status, w_payload = t["work"](doi)
    except Exception as exc:  # noqa: BLE001
        return DEFERRED, f"Crossref lookup failed ({exc})"
    if w_status == 404:                                  # not Crossref's DOI — try DataCite (arXiv, preprints)
        return _check_datacite(doi, t, cited)
    if w_status != 200:
        return DEFERRED, f"Crossref works lookup inconclusive (HTTP {w_status})"

    if cited:                                            # wrong-referent check, title-dominant
        message = (w_payload or {}).get("message", {}) if isinstance(w_payload, dict) else {}
        mv = _metadata_verdict({k: v for k, v in cited.items() if v}, message)
        if mv is not None and mv[0] in (SOURCE_MISMATCH, DEFERRED):
            return mv                                    # a mismatched referent never reaches OK
        flagged_meta = mv                                 # (SOURCE_FLAGGED, why) or None — retraction still checked first

    try:
        u_status, u = t["updates"](doi)
    except Exception as exc:  # noqa: BLE001
        return DEFERRED, f"Crossref updates lookup failed ({exc})"
    if u_status != 200 or not isinstance(u, dict):
        return DEFERRED, f"updates lookup inconclusive (HTTP {u_status})"

    kinds = []
    for item in u.get("message", {}).get("items", []):
        for upd in item.get("update-to", []):
            if str(upd.get("DOI", "")).lower() == doi.lower():
                kinds.append(str(upd.get("type", "")).lower().replace(" ", "_"))
    fatal = sorted({k for k in kinds if k in _FATAL_TYPES})
    flags = sorted({k for k in kinds if k in _FLAG_TYPES})
    unknown = sorted({k for k in kinds if k and k not in _FATAL_TYPES and k not in _FLAG_TYPES})
    if fatal:
        return SOURCE_RETRACTED, f"notice(s) targeting this DOI: {', '.join(fatal)}"
    if unknown:
        # an update type we don't recognize is treated as a flag, not silently ignored
        return SOURCE_FLAGGED, f"unrecognized update notice type(s): {', '.join(unknown)} — read before citing"
    if flags:
        return SOURCE_FLAGGED, f"non-retraction notice(s): {', '.join(flags)} — read before citing"
    if flagged_meta is not None:
        return flagged_meta                              # corroborator (year/author) disagreements
    ok_why = "resolves; Crossref-registered; no retraction/withdrawal notice found"
    if cited and cited.get("title"):
        ok_why += "; cited title matches the DOI's record"
    return SOURCE_OK, ok_why


def check_text(text, transport=None):
    """Extract the first DOI from free text and gate it. No DOI -> DEFERRED (nothing checkable)."""
    doi = extract_doi(text)
    if not doi:
        return {"doi": None, "verdict": DEFERRED, "why": "no DOI found in the text"}
    verdict, why = check_doi(doi, transport)
    return {"doi": doi, "verdict": verdict, "why": why}


# ── selftest: planted cases with an injected transport — no network, must pass first ──

def _fake(handle=(200, {"responseCode": 1}), work=(200, {}), datacite=(404, None),
          updates_items=None, raise_on=None):
    def h(doi):
        if raise_on == "handle":
            raise OSError("network down")
        return handle
    def w(doi):
        if raise_on == "work":
            raise OSError("network down")
        return work
    def d(doi):
        if raise_on == "datacite":
            raise OSError("network down")
        return datacite
    def u(doi):
        if raise_on == "updates":
            raise OSError("network down")
        return 200, {"message": {"items": updates_items or []}}
    return {"handle": h, "work": w, "datacite": d, "updates": u}


def _items(doi, *types):
    return [{"update-to": [{"DOI": doi, "type": t}]} for t in types]


D = "10.1000/example.1"
_REC = {"message": {"title": ["Deep learning for verification of medical claims"],
                    "issued": {"date-parts": [[2015]]},
                    "author": [{"family": "Ellison", "given": "M."}]}}
# arXiv/DataCite fixtures: ARXIV is a real DataCite DOI; _DC_REC mirrors api.datacite.org's shape
# (data.attributes.{titles,publicationYear,creators,state}) — the EviBound paper (verified 2026-07-07).
ARXIV = "10.48550/arXiv.2511.05524"
_DC_TITLE = "Evidence-Bound Autonomous Research (EviBound): A Governance Framework for Eliminating False Claims"
_DC_REC = {"data": {"attributes": {
    "titles": [{"title": _DC_TITLE}],
    "publicationYear": 2025,
    "creators": [{"familyName": "Chen", "name": "Chen, Ruiying"}],
    "state": "findable"}}}
METADATA_SELFTEST = [
    # (name, cited dict, expected) — all against the _REC record above
    ("exact title match", {"title": "Deep learning for verification of medical claims"}, SOURCE_OK),
    ("subtitle containment matches", {"title": "Deep learning for verification"}, SOURCE_OK),
    ("wrong referent title", {"title": "Attention is all you need"}, SOURCE_MISMATCH),
    ("ambiguous title overlap defers", {"title": "Verification of deep claims in learning networks and medical robots"}, DEFERRED),
    ("year off by one tolerated", {"title": "Deep learning for verification of medical claims", "year": "2016"}, SOURCE_OK),
    ("year+author both off -> flagged", {"title": "Deep learning for verification of medical claims",
                                          "year": "2011", "author": "Smith"}, SOURCE_FLAGGED),
]
# wrong-referent logic reused verbatim on the DataCite arm, run against _DC_REC via _datacite_to_message
DATACITE_METADATA_SELFTEST = [
    ("arXiv exact title -> OK", {"title": _DC_TITLE}, SOURCE_OK),
    ("arXiv containment title -> OK", {"title": "Evidence-Bound Autonomous Research"}, SOURCE_OK),
    ("arXiv wrong referent -> MISMATCH", {"title": "Attention is all you need"}, SOURCE_MISMATCH),
    ("arXiv year+author both off -> FLAGGED", {"title": _DC_TITLE, "year": "2019", "author": "Smith"}, SOURCE_FLAGGED),
]
SELFTEST = [
    ("clean source", D, _fake(), SOURCE_OK),
    ("retraction notice", D, _fake(updates_items=_items(D, "retraction")), SOURCE_RETRACTED),
    ("withdrawal notice", D, _fake(updates_items=_items(D, "withdrawal")), SOURCE_RETRACTED),
    ("correction only", D, _fake(updates_items=_items(D, "correction")), SOURCE_FLAGGED),
    ("expression of concern", D, _fake(updates_items=_items(D, "expression_of_concern")), SOURCE_FLAGGED),
    ("unknown notice type fails closed to FLAGGED", D, _fake(updates_items=_items(D, "new_weird_type")), SOURCE_FLAGGED),
    ("retraction beats correction", D, _fake(updates_items=_items(D, "correction", "retraction")), SOURCE_RETRACTED),
    ("notice for a DIFFERENT doi is ignored", D, _fake(updates_items=_items("10.1000/other", "retraction")), SOURCE_OK),
    ("nonexistent DOI", D, _fake(handle=(404, {"responseCode": 100})), SOURCE_NOT_FOUND),
    ("network down -> DEFER, never NOT_FOUND", D, _fake(raise_on="handle"), DEFERRED),
    ("crossref outage -> DEFER", D, _fake(raise_on="updates"), DEFERRED),
    # DataCite arm: Crossref 404 hands off to DataCite (default _fake datacite=(404,None) = not theirs)
    ("resolves but neither Crossref nor DataCite -> DEFER", D, _fake(work=(404, None)), DEFERRED),
    ("arXiv/DataCite DOI resolves -> SOURCE_OK", ARXIV, _fake(work=(404, None), datacite=(200, _DC_REC)), SOURCE_OK),
    ("fabricated arXiv DOI -> SOURCE_NOT_FOUND (Handle 404)", ARXIV, _fake(handle=(404, {"responseCode": 100})), SOURCE_NOT_FOUND),
    ("arXiv DOI, DataCite unreachable -> DEFER (unreachable != missing)", ARXIV, _fake(work=(404, None), raise_on="datacite"), DEFERRED),
]
EXTRACT_CASES = [
    ("as shown (doi:10.1038/nature14539).", "10.1038/nature14539"),
    ("see https://doi.org/10.1016/S0140-6736(97)11096-0 for details", "10.1016/S0140-6736(97)11096-0"),
    ("no citation here at all", None),
    # arXiv normalization: full DOI wins, then arXiv: prefix, then a bare id standing alone
    ("full form 10.48550/arXiv.2606.16541 here", "10.48550/arXiv.2606.16541"),
    ("see arXiv:2606.16541 for the method", "10.48550/arXiv.2606.16541"),
    ("2511.05524", "10.48550/arXiv.2511.05524"),          # bare id as the whole input
    ("2606.16541v2", "10.48550/arXiv.2606.16541"),        # version suffix dropped to the base DOI
    ("1334.5678", None),                                   # month 34 invalid -> not an arXiv id
]


def selftest(verbose=True):
    fails = 0
    for name, doi, transport, expected in SELFTEST:
        got, _ = check_doi(doi, transport)
        ok = got == expected
        fails += (not ok)
        if verbose:
            print(f"  [{'ok ' if ok else 'FAIL'}] expect {expected:17} got {got:17} {name}")
    for name, cited, expected in METADATA_SELFTEST:
        got, _ = check_doi(D, _fake(work=(200, _REC)), cited=cited)
        ok = got == expected
        fails += (not ok)
        if verbose:
            print(f"  [{'ok ' if ok else 'FAIL'}] expect {expected:17} got {got:17} metadata: {name}")
    for name, cited, expected in DATACITE_METADATA_SELFTEST:
        got, _ = check_doi(ARXIV, _fake(work=(404, None), datacite=(200, _DC_REC)), cited=cited)
        ok = got == expected
        fails += (not ok)
        if verbose:
            print(f"  [{'ok ' if ok else 'FAIL'}] expect {expected:17} got {got:17} datacite: {name}")
    # retraction must dominate a matching title
    got, _ = check_doi(D, _fake(work=(200, _REC), updates_items=_items(D, "retraction")),
                       cited={"title": "Deep learning for verification of medical claims"})
    ok = got == SOURCE_RETRACTED
    fails += (not ok)
    if verbose:
        print(f"  [{'ok ' if ok else 'FAIL'}] expect {SOURCE_RETRACTED:17} got {got:17} metadata: retraction dominates a matching title")
    for text, expected in EXTRACT_CASES:
        got = extract_doi(text)
        ok = got == expected
        fails += (not ok)
        if verbose:
            print(f"  [{'ok ' if ok else 'FAIL'}] extract -> {str(got):42} {text[:44]!r}")
    if verbose:
        total = (len(SELFTEST) + len(METADATA_SELFTEST) + len(DATACITE_METADATA_SELFTEST)
                 + 1 + len(EXTRACT_CASES))
        print(f"\n  {'ALL PASS' if fails == 0 else str(fails) + ' FAILURE(S)'} ({total} planted cases)")
    return fails


LIVE_CASES = [
    ("10.1016/S0140-6736(97)11096-0", None, SOURCE_RETRACTED),   # Wakefield 1998, retracted 2010
    ("10.1038/nature14539", None, SOURCE_OK),                    # LeCun/Bengio/Hinton 2015, standing
    ("10.99999/definitely-not-a-real-doi-2026", None, SOURCE_NOT_FOUND),
    ("10.1038/nature14539", {"title": "Deep learning"}, SOURCE_OK),               # right referent
    ("10.1038/nature14539", {"title": "Attention is all you need"}, SOURCE_MISMATCH),  # wrong referent
    ("10.48550/arXiv.2511.05524", None, SOURCE_OK),              # real arXiv paper via DataCite (EviBound)
    ("10.48550/arXiv.2699.99999", None, SOURCE_NOT_FOUND),       # fabricated arXiv DOI (Handle 404)
    ("10.48550/arXiv.2511.05524", {"title": "Evidence-Bound Autonomous Research"}, SOURCE_OK),  # right referent
]


def live_test():
    fails = 0
    for doi, cited, expected in LIVE_CASES:
        got, why = check_doi(doi, cited=cited)
        ok = got == expected
        fails += (not ok)
        tag = f" cited={cited['title']!r}" if cited else ""
        print(f"  [{'ok ' if ok else 'FAIL'}] expect {expected:17} got {got:17} {doi}{tag}")
        print(f"        {why}")
    print(f"\n  {'LIVE: ALL PASS' if fails == 0 else str(fails) + ' LIVE FAILURE(S)'}")
    return fails


def main():
    ap = argparse.ArgumentParser(description="Fail-closed provenance gate for cited DOIs.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--live-test", action="store_true", help="known-answer network probes")
    ap.add_argument("--check", metavar="DOI_OR_TEXT")
    ap.add_argument("--cited-title", help="title as it appears in the citation (wrong-referent check)")
    ap.add_argument("--cited-year", help="year as cited")
    ap.add_argument("--cited-author", help="first-author family name as cited")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(1 if selftest() else 0)
    if selftest(verbose=False):                          # fail-closed: never run on a broken gate
        print("SELFTEST FAILING — refusing to run.", file=sys.stderr)
        sys.exit(2)
    if args.live_test:
        sys.exit(1 if live_test() else 0)
    if args.check:
        cited = {"title": args.cited_title, "year": args.cited_year, "author": args.cited_author}
        cited = {k: v for k, v in cited.items() if v} or None
        doi = extract_doi(args.check)
        if not doi:
            print(json.dumps({"doi": None, "verdict": DEFERRED, "why": "no DOI found in the text"}, indent=2))
            return
        verdict, why = check_doi(doi, cited=cited)
        print(json.dumps({"doi": doi, "verdict": verdict, "why": why}, indent=2))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
