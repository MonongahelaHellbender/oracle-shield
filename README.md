# oracle-shield

*Route a claim to a sound oracle, get a verdict plus the trust basis — and an honest coverage report.*

A small verification layer for AI-produced claims. An untrusted router dispatches each claim to a
deterministic / sound oracle (number theory, closed-form algebra, modular arithmetic, evidence-type
licensing). Covered claims get **SUPPORTED / REFUTED** with the oracle's trust basis; everything else is
**DEFERRED** — and the tool reports the **coverage denominator** most evaluations hide.

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

## Design

- **Trust lives in the oracles, never the router.** A misroute, an unknown claim, or a *crashing* oracle all
  yield a missed check (DEFERRED) — never a wrong verdict. The router is safe to be dumb (or, later, learned).
- **Coverage is the open problem, reported honestly.** The shield only covers the verifiable slice of what a
  model emits; the report lists the uncovered fraction by name. Adding a lane = adding one `ORACLES` entry.

## Honest limits

- The four oracles are a starting set, not the world. The evidence-type lane is a **minimal illustrative
  GRADE-style ladder**, not an epidemiology engine.
- On real open-ended text the checkable fraction is **small** — that's the point of the coverage report, not
  a bug. This is verification *infrastructure*, not a claim that most model output can be checked.

*Author: Melissa D. Ellison.*
