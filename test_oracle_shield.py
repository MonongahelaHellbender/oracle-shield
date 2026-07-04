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
    ("d/dx sin(x) = cos(x)", SUPPORTED),                    # symbolic — derivative
    ("d/dx x^3 = 2*x^2", REFUTED),                          # symbolic — wrong derivative
    ("integral_0^1 x^2 dx = 1/3", SUPPORTED),              # symbolic — definite integral
    ("integral cos(x) dx = sin(x)", SUPPORTED),            # symbolic — indefinite (checked via diff)
    ("lim_{x->0} sin(x)/x = 1", SUPPORTED),                # symbolic — limit
    ("sum_{k=1}^n k^2 = n*(n+1)*(2*n+1)/6", SUPPORTED),    # symbolic — summation
    ("(a+b)^2 = a^2 + 2*a*b + b^2", SUPPORTED),            # symbolic — universal identity (now provable)
    ("(a+b)^2 = a^2 + b^2", REFUTED),                       # symbolic — false identity
    ("Is 2 a prime number?", SUPPORTED),                   # robustness — 'a prime' phrasing
    ("sum_{k=1}^n k^2 = n*(n+1)*(2n+1)/6", SUPPORTED),     # robustness — implicit multiplication (2n)
    ("sum_{k=1}^n k^3 = [n*(n+1)/2]^2", SUPPORTED),        # robustness — [..] grouping + implicit mult
    ("(2+3i)(2-3i) = 13", DEFERRED),                       # SOUNDNESS — true via i=√-1; must DEFER, never REFUTE
    ("lim_{n->infinity} (1 + 1/n)^n = e", DEFERRED),       # SOUNDNESS — true via e=Euler; must DEFER, never REFUTE
    ("integrate x dx from 0 to n = n^2/2", SUPPORTED),     # robustness — prose "integrate ... from ... to ..."
    ("integrate cos(x) dx = sin(x)", SUPPORTED),           # robustness — prose indefinite "integrate"
    ("Is 24 a divisible by 6?", SUPPORTED),                # robustness — broadened divisibility phrasing
    ("int sin(x) dx = -cos(x) + C", SUPPORTED),            # robustness — 'int' keyword + '+ C' (C diffs to 0)
    ("int cos(x) dx = sin(x) + C", SUPPORTED),             # robustness — 'int' keyword
    ("d/dx e^{x} = e^{x}", DEFERRED),                      # SOUNDNESS — LaTeX braces ok but 'e' ambiguous -> DEFER
    ("derivative sin(x) = cos(x)", SUPPORTED),             # robustness — NL 'derivative' phrasing
    ("derivative of x^3 = 3*x^2", SUPPORTED),              # robustness — NL 'derivative of'
    ("second derivative of x^2 = 2", DEFERRED),            # SOUNDNESS — must NOT mis-compute as first-order
    ("integral from 0 to 1 x^2 dx = 1/3", SUPPORTED),      # robustness — bounds-first prose integral
    ("sum_{k=1}^infinity 1/k^2 converges", SUPPORTED),     # convergence lane — p-series p=2
    ("sum_{k=1}^infinity 1/k converges", REFUTED),         # convergence lane — harmonic diverges
    ("sum_{k=1}^oo 1/k diverges", SUPPORTED),              # convergence lane — diverges claim
    ("sum_{k=1}^5 1/k converges", DEFERRED),               # convergence lane — finite bound -> defer
    ("", DEFERRED),                                         # empty input
    (12345, DEFERRED),                                      # non-string input
    ("sqrt(2 = 4", DEFERRED),                               # malformed: matches closed-form, crashes parse -> MUST defer
    ("d/dx (1/0) = 0", DEFERRED),                           # SOUNDNESS — 1/0 parses to zoo (singular); ill-posed input must DEFER, not SUPPORT
    ("2147483647 is prime", SUPPORTED),                     # coverage — declarative primality (README marquee, previously DEFERRED)
    ("9999800001 is a perfect square", SUPPORTED),          # coverage — declarative perfect-square, 99999^2 (previously DEFERRED)
    ("2147483646 is prime", REFUTED),                       # coverage — declarative, both-direction gold (even => not prime)
    ("RR 0.70 (95% CI 0.55-0.89), significant", SUPPORTED), # stats-CI — ratio, CI excludes 1 => significant, claim matches
    ("RR 1.30 (95% CI 0.95-1.78), significant", REFUTED),   # stats-CI — ratio, CI contains 1 => not significant; claim wrong
    ("mean difference 2.3 (95% CI 0.5 to 4.1), significant", SUPPORTED),   # stats-CI — diff, CI excludes 0 => significant
    ("mean difference 2.3 (95% CI -0.5 to 5.1) is not significant", SUPPORTED),  # stats-CI — diff, CI contains 0 => not sig, matches
    ("HR 0.80 (95% CI 0.65-0.98), not significant", REFUTED),  # stats-CI — ratio, CI excludes 1 => significant; "not significant" wrong
    ("1.30 (95% CI 0.95-1.78), significant", DEFERRED),     # SOUNDNESS — no estimate type => null unknown => DEFER
    ("OR 1.30 (90% CI 1.05-1.61), significant", DEFERRED),  # SOUNDNESS — 90% CI not dual to 0.05 => DEFER
    ("sensitivity 99%, specificity 99%, prevalence 0.1%, PPV 99%", REFUTED),   # Bayes — base-rate neglect: true PPV ~9%
    ("sensitivity 99%, specificity 99%, prevalence 0.1%, PPV 9%", SUPPORTED),  # Bayes — correct PPV
    ("sensitivity 90%, specificity 90%, prevalence 50%, PPV 90%", SUPPORTED),  # Bayes — balanced base rate, PPV 90%
    ("sensitivity 99%, specificity 99%, PPV 9%", DEFERRED),                    # SOUNDNESS — no prevalence => DEFER
    ("control 2%, treatment 1%, NNT 100", SUPPORTED),      # risk — ARR 1pp => NNT 100
    ("control 2%, treatment 1%, NNT 50", REFUTED),         # risk — true NNT is 100, not 50
    ("control 2%, treatment 1%, RRR 50%", SUPPORTED),      # risk — relative reduction correct (basis surfaces ARR 1pp)
    ("control 2%, treatment 1%, ARR 5%", REFUTED),         # risk — true ARR is 1pp, not 5%
    ("control 2%, treatment 1%", DEFERRED),                # SOUNDNESS — no claimed statistic => DEFER
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
