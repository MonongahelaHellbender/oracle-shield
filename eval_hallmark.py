#!/usr/bin/env python3
"""
eval_hallmark — evaluate the provenance gate against the HALLMARK benchmark.

HALLMARK (github.com/rpatrik96/hallmark) is a citation-hallucination detection benchmark:
labeled bibliography entries (VALID / HALLUCINATED) with fields title/author/year/doi.
This runs `provenance_oracle` on a seeded sample and reports the HONEST numbers:

  * COVERAGE  — the gate only adjudicates DOI-bearing, Crossref-registered citations; DOI-less
                entries and non-Crossref (e.g. arXiv/DataCite) DOIs DEFER. Coverage is the point,
                not a footnote.
  * PRECISION / DETECTION RATE / FPR / F1 — computed ONLY on the covered subset.

Not a leaderboard entry. The provenance gate is a deterministic DOI-existence + retraction +
wrong-referent check, ~1 of HALLMARK's 6 sub-tests; this measures how far that narrow, fail-closed
slice gets on real data. Live Crossref/Handle calls are cached on disk (rerun-free, API-polite).

Usage:
  python3 eval_hallmark.py --data /path/to/hallmark/data/v1.0/dev_public.jsonl --n 160 --seed 20260705
"""
import argparse
import json
import random
import time
from pathlib import Path

import provenance_oracle as pv

# verdict -> prediction. NOT_FOUND / MISMATCH / RETRACTED / FLAGGED are hallucination signals;
# OK = valid; DEFERRED (incl. no-DOI, non-Crossref) = UNCOVERED (no prediction, counted honestly).
_HALLUC = {pv.SOURCE_NOT_FOUND, pv.SOURCE_MISMATCH, pv.SOURCE_RETRACTED, pv.SOURCE_FLAGGED}


def _cache(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def predict(entry, cache):
    f = entry.get("fields", {})
    doi = f.get("doi")
    if not doi:
        return "UNCOVERED", "no DOI in the citation"
    cited = {k: f.get(k) for k in ("title", "year", "author") if f.get(k)}
    # the resolver version is part of the key: a verdict cached under an older resolver must MISS,
    # not silently replay (a 0.6.x DEFER on an arXiv DOI is not a 0.7.0 verdict)
    key = (getattr(pv, "__version__", "0") + "|" + doi + "|" + "|".join(sorted(cited)) + "|"
           + "".join(str(cited.get(k, ""))[:40] for k in sorted(cited)))
    if key in cache:
        verdict, why, net = cache[key][0], cache[key][1], False
    else:
        verdict, why = pv.check_doi(doi, cited=cited)
        cache[key] = [verdict, why]
        net = True
    if verdict == pv.SOURCE_OK:
        return "VALID", why, net
    if verdict in _HALLUC:
        return "HALLUCINATED", why, net
    return "UNCOVERED", why, net


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--n", type=int, default=160)
    ap.add_argument("--seed", type=int, default=20260705)
    ap.add_argument("--cache", default="hallmark_cache.json")
    ap.add_argument("--out", default="hallmark_eval_result.json")
    ap.add_argument("--sleep", type=float, default=0.15, help="polite delay between live lookups")
    args = ap.parse_args()

    entries = [json.loads(l) for l in Path(args.data).read_text().splitlines() if l.strip()]
    rng = random.Random(args.seed)
    rng.shuffle(entries)
    sample = entries[: args.n]

    cache = _cache(args.cache)
    tp = fp = fn = tn = uncovered = 0
    by_tier = {}
    done = 0
    for e in sample:
        label = e.get("label")
        if label not in ("VALID", "HALLUCINATED"):
            continue
        done += 1
        pred, why, *net = predict(e, cache)
        if net and net[0]:
            time.sleep(args.sleep)                       # only sleep on a real network call
            if done % 20 == 0:
                Path(args.cache).write_text(json.dumps(cache))   # checkpoint the cache
        tier = e.get("difficulty_tier", "?")
        by_tier.setdefault(tier, {"cov": 0, "tot": 0, "correct": 0})
        by_tier[tier]["tot"] += 1
        if pred == "UNCOVERED":
            uncovered += 1
            continue
        by_tier[tier]["cov"] += 1
        halluc_pred = pred == "HALLUCINATED"
        halluc_true = label == "HALLUCINATED"
        by_tier[tier]["correct"] += int(halluc_pred == halluc_true)
        if halluc_pred and halluc_true:
            tp += 1
        elif halluc_pred and not halluc_true:
            fp += 1
        elif not halluc_pred and halluc_true:
            fn += 1
        else:
            tn += 1

    Path(args.cache).write_text(json.dumps(cache))
    covered = tp + fp + fn + tn
    dr = tp / (tp + fn) if (tp + fn) else None
    fpr = fp / (fp + tn) if (fp + tn) else None
    prec = tp / (tp + fp) if (tp + fp) else None
    f1 = (2 * prec * dr / (prec + dr)) if (prec and dr) else None
    report = {
        "benchmark": "HALLMARK dev_public", "sample_n": done, "seed": args.seed,
        "covered": covered, "uncovered": uncovered,
        "coverage_fraction": round(covered / done, 3) if done else 0,
        "confusion_on_covered": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": round(prec, 3) if prec is not None else None,
        "detection_rate_recall": round(dr, 3) if dr is not None else None,
        "false_positive_rate": round(fpr, 3) if fpr is not None else None,
        "f1": round(f1, 3) if f1 is not None else None,
        "by_tier": by_tier,
        "note": "Covered = DOI-bearing, Crossref-registered, resolving. The gate is 1 of HALLMARK's "
                "6 sub-tests (DOI existence + retraction + wrong-referent); metrics are on the covered "
                "subset only. Coverage is honest, not hidden.",
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
