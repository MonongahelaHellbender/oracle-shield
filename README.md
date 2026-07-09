# oracle-shield

*Route a claim to a sound oracle, get a verdict plus the trust basis — and an honest coverage report.*

A small verification layer for AI-produced claims. An untrusted router dispatches each claim to a
deterministic / sound oracle (number theory, closed-form algebra, symbolic calculus/algebra, series
convergence, modular arithmetic, evidence-type licensing, and clinical-statistics consistency). Covered claims get **SUPPORTED / REFUTED** with the oracle's trust
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
python test_oracle_shield.py # 61 regression + robustness tests
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

## Clinical / statistical claims

Three deterministic lanes check whether a reported statistic is *internally consistent* — not whether
the estimate is correct, only whether the claim's own numbers agree. Each defers on anything it can't
settle by arithmetic.

```
RR 1.30 (95% CI 0.95-1.78), significant                      CI vs significance — REFUTED (straddles 1)
sensitivity 99%, specificity 99%, prevalence 0.1%, PPV 99%   Bayes base rate  — REFUTED (true PPV ~9%)
control 2%, treatment 1%, NNT 100                            ARR/RRR/NNT      — SUPPORTED (surfaces ARR 1pp)
```

The middle line is the classic **base-rate-neglect** error — a 99%/99% test at 0.1% prevalence has a
positive predictive value near **9%**, not 99%. Sound basis: the 95% CI ⟷ 0.05 duality (interval
containment of the null — 1 for a ratio, 0 for a difference), Bayes' theorem, and ARR = CER−EER. A claim
is SUPPORTED only when it rounds to the truth, REFUTED only when it is a full unit or more off, and
DEFERRED in between — or when the estimate type, CI level, a one-sided test, or a missing field leaves
the answer undetermined.

## Citation provenance (separate pre-gate — `provenance_oracle.py`)

Junk can also enter as a **fabricated or retracted citation**. The provenance gate checks a cited
DOI's existence (Handle System — catches LLM-hallucinated DOIs, and resolves Crossref **and**
DataCite/arXiv DOIs alike), its metadata (Crossref works API for Crossref DOIs, the DataCite REST
API for arXiv/DataCite DOIs), and retraction status (Crossref, which now carries the Retraction
Watch database):

```
python3 provenance_oracle.py --selftest    # 34 planted cases; refuses to run otherwise
python3 provenance_oracle.py --check "10.1016/S0140-6736(97)11096-0"   # -> SOURCE_RETRACTED
python3 provenance_oracle.py --check "arXiv:2606.16541"                # bare arXiv id -> 10.48550/arXiv.2606.16541
python3 provenance_oracle.py --live-test   # known-answer network probes (Wakefield 1998, a real arXiv paper, etc.)
```

**arXiv / DataCite coverage.** arXiv IDs are the dominant citation form in AI/ML, and arXiv registers
a DataCite DOI (`10.48550/arXiv.<id>`) for every paper. The gate resolves these: existence via the
Handle System, and title/year/author cross-check via the DataCite REST API — so a real arXiv paper
gets `SOURCE_OK` and a fabricated `10.48550/arXiv.2699.99999` gets `SOURCE_NOT_FOUND`, instead of both
`DEFERRED`. A bare id (`2606.16541` or `arXiv:2606.16541`) is normalized to the canonical DOI first.
The one honest narrowing: DataCite carries no retraction feed, so a DataCite `SOURCE_OK` means
"exists + metadata confirmed," and its `why` string says the retraction/withdrawal status was not
checkable — a strictly weaker guarantee than a Crossref `SOURCE_OK`, never silently equated.

Verdicts: `SOURCE_OK / SOURCE_RETRACTED / SOURCE_FLAGGED / SOURCE_NOT_FOUND / SOURCE_MISMATCH /
DEFERRED` — network failure DEFERS (unreachable ≠ nonexistent), and a DOI that resolves but is
registered with neither Crossref nor DataCite (some other agency) DEFERS rather than guessing. Pass
`--cited-title` (optionally `--cited-year`,
`--cited-author`) to also catch the **wrong-referent citation** — a real DOI paired with a
different paper's title, the hallucination class that sails through existence checks; title
comparison is fail-closed (clear disjunction → `SOURCE_MISMATCH`, ambiguous overlap → DEFER). It is deliberately **not** registered as a claim lane: passing provenance
never *supports* a claim — only failing it disqualifies the citation as evidence. `SOURCE_OK`
means "exists, no retraction notice," not "good science." (Prior art: Zotero's Retraction Watch
alerts, scite — this gate's job is the fail-closed verdict spine for AI-emitted citations.)

**Benchmarked on HALLMARK** (github.com/rpatrik96/hallmark, the citation-hallucination benchmark).
On a seeded 160-entry sample of `dev_public` (`eval_hallmark.py`, same sample and seed across
versions), the gate — one of HALLMARK's six sub-tests — measured at v0.7.1: **covered 49.4%** of
entries and on that covered slice scored **precision 0.90 · detection-rate 0.60 · FPR 0.09 ·
F1 0.72**. Version history on the identical sample, so the frontier is visible: v0.6
(Crossref-only) covered 42.5% at F1 0.68; v0.7.0 (DataCite/arXiv arm) bought ~7 points of coverage
at F1 0.65 because the marginal arXiv entries are harder (no retraction feed — existence + metadata
only, as their `why` states); v0.7.1 (author-set disjointness: cited authors sharing zero surnames
with the DOI record flags on its own — the swapped/placeholder-author signature) recovered the
quality at full coverage with **zero new false positives**. Declared boundaries that remain
UNCAUGHT by design: wrong-venue (venue strings too noisy to match deterministically), near-miss
titles inside the fuzzy tolerance, preprint-vs-published and arXiv-version semantics — a citation
whose DOI, title, and authors all check out but whose venue or version is misstated passes this
gate. (The 3 false positives are title-match over-fires — a tolerance-tuning item, not a
soundness break.)

## Design

- **Trust lives in the oracles, never the router.** A misroute, an unknown claim, or a *crashing* oracle all
  yield a missed check (DEFERRED) — never a wrong verdict. The router is safe to be dumb (or, later, learned).
- **Coverage is the open problem, reported honestly.** The shield only covers the verifiable slice of what a
  model emits; the report lists the uncovered fraction by name. Adding a lane = adding one `ORACLES` entry.

## Honest limits

- The eleven oracles are a starting set, not the world. The evidence-type / causal-licensing /
  universal-safety lanes are **minimal illustrative wording-licensing rules**, not an epidemiology
  engine; the clinical-statistics lanes check a claim's internal arithmetic consistency, not whether
  the underlying estimate is correct.
- The symbolic lane is **sound but incomplete**: it computes the answer with a CAS and checks it against the
  claim by symbolic simplification; equality it cannot settle returns DEFERRED rather than a guess.
- On real open-ended text the checkable fraction is **small** — that's the point of the coverage report, not
  a bug. This is verification *infrastructure*, not a claim that most model output can be checked.

## Changelog

**0.7.0** — provenance gate gains a **DataCite / arXiv arm**. arXiv IDs are the dominant citation
form in AI/ML and were the largest coverage hole: they resolve in the Handle System but not in
Crossref, so every one landed on `DEFERRED`. Now, when Crossref disowns a DOI (HTTP 404), the gate
falls through to the DataCite REST API — a real arXiv paper gets `SOURCE_OK`, a fabricated
`10.48550/arXiv.2699.99999` gets `SOURCE_NOT_FOUND`, and the wrong-referent title/year/author
cross-check runs against the DataCite record (the Crossref logic is reused verbatim via a
shape-adapter). Bare arXiv ids (`2606.16541`, `arXiv:2606.16541`) normalize to the canonical
`10.48550/arXiv.<id>`. Fail-closed throughout: DataCite has no retraction feed, so a DataCite
`SOURCE_OK` is existence + metadata only (its `why` says so), and a DOI registered with neither
Crossref nor DataCite still DEFERS. 34 planted selftest cases + 8 known-answer live probes.

**0.6.0** — two **prose wording-licensing lanes** (fail-closed siblings of the GRADE lane):
`causal-licensing` (observational evidence + an *unhedged* causal claim → REFUTED; hedged → SUPPORTED;
an experimental/RCT cue or an idiom → DEFER) and `universal-safety` ("no side effects", "100% safe" →
REFUTED, since no finite study licenses a universal negative; a finite-scope report or a hedge →
DEFER). Eleven oracles; 69 tests. Also: `eval_hallmark.py` benchmarks the provenance gate against
HALLMARK (see above).

**0.5.0** — provenance gate learns the **wrong-referent check**: cited title/year/author are
compared against the DOI's actual Crossref record (title-dominant, fail-closed: clear disjunction
→ `SOURCE_MISMATCH`, gray band → DEFER, year ±1 tolerated, retraction still trumps a matching
title). Closes the hallucination class where a real DOI is paired with a different paper —
cf. CiteCheck (arXiv:2605.27700) and the HALLMARK benchmark, against which a systematic
evaluation is the declared next step. 22 planted cases + 5 live known-answer probes.

**0.4.0** — added the **citation-provenance pre-gate** (`provenance_oracle.py`): DOI existence via
the Handle System (catches fabricated/LLM-hallucinated citations) + retraction/correction notices
via Crossref (Retraction Watch data). Fail-closed: network trouble and non-Crossref DOIs DEFER;
unknown notice types flag rather than pass. 15 planted selftest cases (injected transport, no
network) + 3 known-answer live probes; not a claim lane by design — provenance failure
disqualifies a citation, provenance success supports nothing.

**0.3.0** — added three deterministic **clinical / statistical** lanes: confidence-interval-vs-significance
(the 95% CI ⟷ 0.05 duality), Bayes **PPV/NPV** (the base-rate-neglect catch), and **ARR/RRR/NNT** risk
arithmetic (surfaces absolute risk next to any relative claim). A shared precision-aware tolerance SUPPORTS
only when a claim rounds to the truth and REFUTES only when it is a full unit or more off, else DEFERS.
Every underdetermined input (unknown estimate type, non-95% CI level, one-sided test, ARR≤0 for NNT,
ambiguous rate) defers. Nine oracles; 61 tests.

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
