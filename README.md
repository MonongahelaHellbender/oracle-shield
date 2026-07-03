# oracle-shield

*Route a claim to a sound oracle, get a verdict plus the trust basis — and an honest coverage report.*

A small verification layer for AI-produced claims. An untrusted router dispatches each claim to a
deterministic / sound oracle (number theory, closed-form algebra, symbolic calculus/algebra, series
convergence, modular arithmetic, evidence-type licensing). Covered claims get **SUPPORTED / REFUTED** with the oracle's trust
basis; everything else is **DEFERRED** — and the tool reports the **coverage denominator** most evaluations
hide.

## Why

Language models are *confidently wrong* on checkable claims — e.g. they call `2147483647` (a prime) composite,
and `9999800001` (= 99999²) not a square. The fix isn't a smarter model; it's an **external sound oracle**.
This is that layer: small, sound, and honest about the (large) fraction it can't cover.

## Install & run

```
pip install sympy            # the only dependency
python oracle_shield.py      # runs the demo + the coverage report
python test_oracle_shield.py # 15 regression + robustness tests
```

## Use it programmatically

```python
from oracle_shield import route, report

route("Is 2147483647 prime?")
# -> {'verdict': 'SUPPORTED', 'oracle': 'number-theory', 'type': 'Python (deterministic)', ...}

report(["Is 1000003 a perfect square?", "This claim is not checkable."])
# -> {'checkable': 1, 'n_claims': 2, 'checkable_fraction': 0.5, 'adjudicated': 1, 'uncovered': [...], ...}
```

## What the symbolic lane understands

Phrase one claim per line; coverage depends on the wording:

```
d/dx sin(x) = cos(x)                 derivatives
integral_0^1 x^2 dx = 1/3            definite integrals
integral cos(x) dx = sin(x)          indefinite integrals (checked by differentiating)
lim_{x->0} sin(x)/x = 1              limits
sum_{k=1}^n k = n*(n+1)/2            finite summations (closed form)
(a+b)^2 = a^2 + 2*a*b + b^2          universal algebraic identities
sum_{k=1}^infinity 1/k^2 converges   series convergence / divergence (separate lane)
```

## Design

- **Trust lives in the oracles, never the router.** A misroute, an unknown claim, or a *crashing* oracle all
  yield a missed check (DEFERRED) — never a wrong verdict. The router is safe to be dumb (or, later, learned).
- **Coverage is the open problem, reported honestly.** The shield only covers the verifiable slice of what a
  model emits; the report lists the uncovered fraction by name. Adding a lane = adding one `ORACLES` entry.

## Honest limits

- The six oracles are a starting set, not the world. The evidence-type lane is a **minimal illustrative
  GRADE-style ladder**, not an epidemiology engine.
- The symbolic lane is **sound but incomplete**: it computes the answer with a CAS and checks it against the
  claim by symbolic simplification; equality it cannot settle returns DEFERRED rather than a guess.
- On real open-ended text the checkable fraction is **small** — that's the point of the coverage report, not
  a bug. This is verification *infrastructure*, not a claim that most model output can be checked.

## Changelog

**0.2.0** — added a **symbolic calculus/algebra lane** (derivatives, definite/indefinite integrals, limits,
finite summations, universal algebraic identities) and a **series-convergence lane** (sympy convergence
tests). Tolerant parsing for the notation models actually emit — implicit multiplication (`2n`), `[..]`
grouping, LaTeX `^{...}`, `int`/`\int`/`integrate` and prose integral phrasings, the word "derivative",
broadened prime/divisibility wording. Soundness preserved throughout: ambiguous tokens (e.g. lowercase
`e`/`i`, "second derivative") **DEFER** rather than risk a wrong verdict. Six oracles; 41 tests.

**0.1.0** — initial release: number-theory, closed-form, modular, and evidence-type oracles + the coverage
report.

*Author: Melissa D. Ellison.*

---

*Part of a portfolio of refusal-first AI-assurance & verification tools — [github.com/MonongahelaHellbender](https://github.com/MonongahelaHellbender). Related: [rag-triad](https://github.com/MonongahelaHellbender/rag-triad) · [honesty-atlas](https://github.com/MonongahelaHellbender/honesty-atlas) · [assurance-compiler](https://github.com/MonongahelaHellbender/assurance-compiler) · [gradeability-audit](https://github.com/MonongahelaHellbender/gradeability-audit) · [oracle-shield](https://github.com/MonongahelaHellbender/oracle-shield) · [rag-assurance](https://github.com/MonongahelaHellbender/rag-assurance).*
