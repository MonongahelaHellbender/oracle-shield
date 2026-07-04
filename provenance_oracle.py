#!/usr/bin/env python3
"""
provenance-oracle — deterministic source-provenance gate for cited DOIs.

Checks the PROVENANCE of a citation, never the truth of the claim it supports:
  1. EXISTENCE  — does the DOI resolve in the Handle System (doi.org)? Catches fabricated /
                  LLM-hallucinated citations. (Handle API, not publisher pages, so no bot-blocking.)
  2. RETRACTION — does Crossref list a retraction/withdrawal notice targeting this DOI?
                  (The Retraction Watch database is folded into Crossref metadata.)

Verdicts (fail-closed):
  SOURCE_OK          DOI resolves; Crossref-registered; no retraction/withdrawal notice found
  SOURCE_RETRACTED   a retraction / withdrawal / removal notice targets this DOI
  SOURCE_FLAGGED     a correction / erratum / expression-of-concern targets it (read it before citing)
  SOURCE_NOT_FOUND   the Handle System does not resolve it — fabricated or mistyped
  DEFERRED           network failure, rate limit, or a non-Crossref DOI (e.g. DataCite) whose
                     retraction status is unknowable here — an honest hole, never a guess

Honest scope:
  * SOURCE_OK means "exists and carries no retraction notice" — it does NOT mean good science.
  * This is a PRE-GATE, deliberately NOT registered as an oracle-shield claim lane: passing
    provenance never SUPPORTS a claim; only failing it disqualifies the citation as evidence.
  * Prior art: Zotero ships Retraction Watch alerts; scite grades citations. The job here is the
    fail-closed verdict spine for AI-EMITTED citations, with a selftest that must pass first.

Pure standard library. Run:
  python3 provenance_oracle.py --selftest              # 13 planted cases; must pass first
  python3 provenance_oracle.py --check "10.1016/S0140-6736(97)11096-0"
  python3 provenance_oracle.py --check "The result (doi:10.1038/nature14539) shows..."
  python3 provenance_oracle.py --live-test             # 3 known-answer network probes
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SOURCE_OK = "SOURCE_OK"
SOURCE_RETRACTED = "SOURCE_RETRACTED"
SOURCE_FLAGGED = "SOURCE_FLAGGED"
SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
DEFERRED = "DEFERRED"

MAILTO = "mellison.docs@gmail.com"          # polite-pool identification for Crossref
TIMEOUT = 15

_FATAL_TYPES = {"retraction", "withdrawal", "removal", "retracted"}
_FLAG_TYPES = {"correction", "erratum", "expression_of_concern", "concern", "partial_retraction", "addendum"}

# DOI syntax per Crossref guidance; trailing sentence punctuation stripped after match.
_DOI_RX = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>]+)", re.I)


def extract_doi(text):
    """First DOI in free text (handles doi: prefixes and https://doi.org/ URLs), or None."""
    if not isinstance(text, str):
        return None
    m = _DOI_RX.search(text)
    if not m:
        return None
    doi = m.group(1).rstrip(".,;:)]}\"'")
    return doi or None


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


REAL_TRANSPORT = {"handle": real_handle_lookup, "work": real_crossref_work, "updates": real_crossref_updates}


# ── the gate ──────────────────────────────────────────────────────────────────────────

def check_doi(doi, transport=None):
    """Fail-closed provenance verdict for one DOI. Network trouble -> DEFERRED, never a guess."""
    t = transport or REAL_TRANSPORT
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
        w_status, _ = t["work"](doi)
    except Exception as exc:  # noqa: BLE001
        return DEFERRED, f"Crossref lookup failed ({exc})"
    if w_status == 404:
        return DEFERRED, ("DOI exists but is not Crossref-registered (e.g. DataCite) — "
                          "retraction status is unknowable here")
    if w_status != 200:
        return DEFERRED, f"Crossref works lookup inconclusive (HTTP {w_status})"

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
    return SOURCE_OK, "resolves; Crossref-registered; no retraction/withdrawal notice found"


def check_text(text, transport=None):
    """Extract the first DOI from free text and gate it. No DOI -> DEFERRED (nothing checkable)."""
    doi = extract_doi(text)
    if not doi:
        return {"doi": None, "verdict": DEFERRED, "why": "no DOI found in the text"}
    verdict, why = check_doi(doi, transport)
    return {"doi": doi, "verdict": verdict, "why": why}


# ── selftest: planted cases with an injected transport — no network, must pass first ──

def _fake(handle=(200, {"responseCode": 1}), work=(200, {}), updates_items=None, raise_on=None):
    def h(doi):
        if raise_on == "handle":
            raise OSError("network down")
        return handle
    def w(doi):
        if raise_on == "work":
            raise OSError("network down")
        return work
    def u(doi):
        if raise_on == "updates":
            raise OSError("network down")
        return 200, {"message": {"items": updates_items or []}}
    return {"handle": h, "work": w, "updates": u}


def _items(doi, *types):
    return [{"update-to": [{"DOI": doi, "type": t}]} for t in types]


D = "10.1000/example.1"
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
    ("non-Crossref (DataCite) DOI -> DEFER on retraction status", D, _fake(work=(404, None)), DEFERRED),
]
EXTRACT_CASES = [
    ("as shown (doi:10.1038/nature14539).", "10.1038/nature14539"),
    ("see https://doi.org/10.1016/S0140-6736(97)11096-0 for details", "10.1016/S0140-6736(97)11096-0"),
    ("no citation here at all", None),
]


def selftest(verbose=True):
    fails = 0
    for name, doi, transport, expected in SELFTEST:
        got, _ = check_doi(doi, transport)
        ok = got == expected
        fails += (not ok)
        if verbose:
            print(f"  [{'ok ' if ok else 'FAIL'}] expect {expected:17} got {got:17} {name}")
    for text, expected in EXTRACT_CASES:
        got = extract_doi(text)
        ok = got == expected
        fails += (not ok)
        if verbose:
            print(f"  [{'ok ' if ok else 'FAIL'}] extract -> {str(got):42} {text[:44]!r}")
    if verbose:
        print(f"\n  {'ALL PASS' if fails == 0 else str(fails) + ' FAILURE(S)'} "
              f"({len(SELFTEST) + len(EXTRACT_CASES)} planted cases)")
    return fails


LIVE_CASES = [
    ("10.1016/S0140-6736(97)11096-0", SOURCE_RETRACTED),   # Wakefield 1998, retracted 2010
    ("10.1038/nature14539", SOURCE_OK),                    # LeCun/Bengio/Hinton 2015, standing
    ("10.99999/definitely-not-a-real-doi-2026", SOURCE_NOT_FOUND),
]


def live_test():
    fails = 0
    for doi, expected in LIVE_CASES:
        got, why = check_doi(doi)
        ok = got == expected
        fails += (not ok)
        print(f"  [{'ok ' if ok else 'FAIL'}] expect {expected:17} got {got:17} {doi}")
        print(f"        {why}")
    print(f"\n  {'LIVE: ALL PASS' if fails == 0 else str(fails) + ' LIVE FAILURE(S)'}")
    return fails


def main():
    ap = argparse.ArgumentParser(description="Fail-closed provenance gate for cited DOIs.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--live-test", action="store_true", help="3 known-answer network probes")
    ap.add_argument("--check", metavar="DOI_OR_TEXT")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(1 if selftest() else 0)
    if selftest(verbose=False):                          # fail-closed: never run on a broken gate
        print("SELFTEST FAILING — refusing to run.", file=sys.stderr)
        sys.exit(2)
    if args.live_test:
        sys.exit(1 if live_test() else 0)
    if args.check:
        r = check_text(args.check)
        print(json.dumps(r, indent=2))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
