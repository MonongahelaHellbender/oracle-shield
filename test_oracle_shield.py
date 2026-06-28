#!/usr/bin/env python3
"""Regression + robustness tests for the oracle shield. Run: python test_oracle_shield.py"""
from oracle_shield import route, report, SUPPORTED, REFUTED, DEFERRED

CASES = [
    ("Is 2147483647 prime?", SUPPORTED),                    # true (Mersenne 2^31-1)
    ("Is 1000000007 divisible by 3?", REFUTED),
    ("Is 1000003 a perfect square?", REFUTED),
    ("Is 2^10 mod 1000 = 24?", SUPPORTED),
    ("sqrt(2)*sqrt(8) = 4", SUPPORTED),                     # = sqrt(16) = 4
    ("sqrt(4) = 3", REFUTED),
    ("n^5 ≡ n (mod 5)", SUPPORTED),                         # Fermat
    ("n^2 ≡ 1 (mod 4)", REFUTED),                           # n=0 counterexample
    ("evidence: observational_study claim: causes", REFUTED),
    ("evidence: observational_study claim: association", SUPPORTED),
    ("This sentence is not checkable.", DEFERRED),
    ("(a+b)^2 = a^2 + 2*a*b + b^2", DEFERRED),              # free vars -> defer
    ("", DEFERRED),                                         # empty input
    (12345, DEFERRED),                                      # non-string input
    ("sqrt(2 = 4", DEFERRED),                               # malformed: matches closed-form, crashes parse -> MUST defer
]


def main():
    fails = 0
    for claim, expected in CASES:
        got = route(claim)["verdict"]                       # must never raise
        ok = got == expected
        fails += (not ok)
        print(f"  [{'ok ' if ok else 'FAIL'}] expect {expected:9} got {got:9}  {claim!r}")
    rep = report([c for c, _ in CASES])
    print(f"\n  coverage on the test set: {rep['checkable']}/{rep['n_claims']} checkable, "
          f"{rep['adjudicated']} adjudicated, {len(rep['uncovered'])} uncovered")
    print("  " + ("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)"))
    return fails


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
