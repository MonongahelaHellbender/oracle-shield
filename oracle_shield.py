#!/usr/bin/env python3
"""
oracle-shield — route a claim to a SOUND oracle, adjudicate, and report COVERAGE.

A small verification layer. An untrusted RULE-BASED router dispatches each claim to a deterministic/sound
oracle (number theory, closed-form algebra, modular arithmetic, evidence-type licensing). Covered claims get
SUPPORTED / REFUTED with the oracle's trust basis; everything else is DEFERRED — and the tool reports the
COVERAGE denominator most evaluations hide.

Design principles:
  * Trust lives in the oracles, never in the router. A matcher or adjudicator that crashes — or a claim no
    oracle handles — yields a MISSED check (DEFERRED), never a wrong verdict. So the router can be dumb (or,
    later, a learned net) without endangering soundness.
  * The registry is the extension point: add a lane = add one ORACLES entry.

Self-contained; needs only `sympy`.  Run:  python oracle_shield.py
"""
import itertools
import math
import re

import sympy
from sympy.parsing.sympy_parser import (parse_expr, standard_transformations,
                                        implicit_multiplication_application)

_TX = standard_transformations + (implicit_multiplication_application,)

SUPPORTED, REFUTED, DEFERRED = "SUPPORTED", "REFUTED", "DEFERRED"


# ── oracle 1: number theory (deterministic Python) ───────────────────────────

def _is_prime(n):
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


def _is_square(n):
    r = math.isqrt(n)
    return r * r == n


def _is_cube(n):
    r = round(n ** (1.0 / 3.0))
    return any(c >= 0 and c ** 3 == n for c in (r - 1, r, r + 1))


_NT_PATTERNS = [
    (re.compile(r"is\s+(\d+)\s+(?:an?\s+)?prime", re.I),
     lambda m: (_is_prime(int(m[1])), f"primality of {m[1]}")),
    (re.compile(r"is\s+(\d+)\s+a perfect square", re.I),
     lambda m: (_is_square(int(m[1])), f"perfect-square test of {m[1]}")),
    (re.compile(r"is\s+(\d+)\s+a perfect cube", re.I),
     lambda m: (_is_cube(int(m[1])), f"perfect-cube test of {m[1]}")),
    (re.compile(r"is\s+(\d+)\s+(?:an?\s+)?divisible by\s+(\d+)", re.I),
     lambda m: (int(m[1]) % int(m[2]) == 0, f"divisibility {m[1]}/{m[2]}")),
    (re.compile(r"(\d+)\s*\^\s*(\d+)\s*mod\s*(\d+)\s*=\s*(\d+)", re.I),
     lambda m: (pow(int(m[1]), int(m[2]), int(m[3])) == int(m[4]),
                f"modular exp {m[1]}^{m[2]} mod {m[3]} = {pow(int(m[1]), int(m[2]), int(m[3]))}")),
]


def nt_match(text):
    t = text.replace(",", "")
    return any(p.search(t) for p, _ in _NT_PATTERNS)


def nt_adjudicate(text):
    t = text.replace(",", "")
    for pat, fn in _NT_PATTERNS:
        m = pat.search(t)
        if m:
            holds, why = fn(m)
            return (SUPPORTED if holds else REFUTED, why)
    return None


# ── oracle 2: closed-form algebra (sympy CAS, exact) ─────────────────────────

def cf_match(text):
    if nt_match(text):
        return False
    return bool(re.search(r"[=<>≤≥]", text)) and bool(re.search(r"sqrt|\^|\*|/|\d", text))


def cf_adjudicate(text):
    t = text.replace("^", "**").replace("≤", "<=").replace("≥", ">=")
    op = next((o for o in ["<=", ">=", "=", "<", ">"] if o in t), None)
    if not op:
        return None
    lhs, rhs = t.split(op, 1)
    A, B = sympy.sympify(lhs), sympy.sympify(rhs)   # may raise -> route() defers
    if A.free_symbols or B.free_symbols:
        return None                                  # free vars => a forall-claim, not ground; defer
    if op == "=":
        eq = (A - B).equals(0)
        return None if eq is None else (SUPPORTED if eq else REFUTED, "sympy exact equality")
    rel = {"<=": A <= B, ">=": A >= B, "<": A < B, ">": A > B}[op]
    if rel in (sympy.true, sympy.false):
        return (SUPPORTED if bool(rel) else REFUTED, "sympy exact inequality")
    return None


# ── oracle: symbolic calculus & algebra (sympy CAS, exact) ───────────────────
# Verifies derivatives, definite/indefinite integrals, limits, finite summations, and universal
# algebraic identities. Soundness: an answer is computed by the CAS, then checked equal to the claim via
# symbolic simplification; equality it cannot settle returns None -> DEFERRED (never a guess). An
# indefinite integral is checked the only sound way — by differentiating the claimed antiderivative.

def _S(s):
    # tolerant math parsing: ^ -> **, [..] -> (..), 'infinity' -> oo, and implicit multiplication
    # ("2n", ")(", "2(x+1)") — the conventions models and humans actually write.
    s = s.replace("^", "**").replace("[", "(").replace("]", ")")
    s = re.sub(r"\*\*\{([^}]*)\}", r"**(\1)", s)         # LaTeX exponent x^{...} -> x**(...)
    s = re.sub(r"\binfinity\b|\binf\b", "oo", s, flags=re.I)
    return parse_expr(s, transformations=_TX)


_AMBIG = {"e", "i"}  # lowercase e/i: could be Euler's number / the imaginary unit, NOT a free variable


def _zero(expr):
    """True = provably 0, False = provably nonzero, None = undecided (-> DEFER)."""
    try:
        expr = sympy.sympify(expr)
        if sympy.expand(expr) == 0:
            return True
        s = sympy.simplify(expr)
        if s == 0:
            return True
        fs = s.free_symbols
        if any(str(x) in _AMBIG for x in fs):
            return None     # 'e'/'i' might be a constant we mis-parsed as a variable -> never REFUTE, defer
        if not fs:
            r = s.equals(0)
            return r if r in (True, False) else None
        if s.is_polynomial(*sorted(fs, key=str)):
            return False                                  # a nonzero polynomial is not an identity
        return None                                      # transcendental & unresolved -> defer
    except Exception:  # noqa: BLE001
        return None


def _verdict(z, basis):
    if z is True:
        return (SUPPORTED, basis)
    if z is False:
        return (REFUTED, basis + " — the two sides are not equal")
    return None


_DERIV = re.compile(r"d\s*/\s*d\s*([a-zA-Z])\s+(.+?)\s*=\s*(.+)$")
# natural-language first derivative: anchored + only 'the/first' prefix so 'second/partial derivative'
# do NOT match (they would be silently mis-computed as first-order -> a wrong verdict).
_DERIV2 = re.compile(r"^\s*(?:the\s+)?(?:first\s+)?derivative\s+(?:of\s+)?(.+?)\s*=\s*(.+)$", re.I)
# integral keyword: ∫ / int / \int / integral / integrate  (the forms models actually emit)
_INTKW = r"(?:∫|\\?int(?:egral|egrate)?)"
_DEFINT = re.compile(rf"{_INTKW}\s*_\s*\{{?(.+?)\}}?\s*\^\s*\{{?(.+?)\}}?\s+(.+?)\s*d([a-zA-Z])\s*=\s*(.+)$", re.I)
_DEFINT2 = re.compile(rf"{_INTKW}\s+(.+?)\s*d([a-zA-Z])\s+from\s+(.+?)\s+to\s+(.+?)\s*=\s*(.+)$", re.I)
_DEFINT3 = re.compile(rf"{_INTKW}\s+from\s+(.+?)\s+to\s+(.+?)\s+(.+?)\s*d([a-zA-Z])\s*=\s*(.+)$", re.I)
_INDEFINT = re.compile(rf"{_INTKW}\s+(.+?)\s*d([a-zA-Z])\s*=\s*(.+)$", re.I)
_LIM = re.compile(r"lim\s*_?\s*\{?\s*([a-zA-Z])\s*(?:->|→|to)\s*([^}\s]+)\s*\}?\s+(.+?)\s*=\s*(.+)$", re.I)
_SUM = re.compile(r"(?:∑|sum)\s*_\s*\{?\s*([a-zA-Z])\s*=\s*(.+?)\s*\}?\s*\^\s*\{?(.+?)\}?\s+(.+?)\s*=\s*(.+)$", re.I)
_SYM_SIG = re.compile(r"d\s*/\s*d[a-zA-Z]|\bderivative|∫|\bintegr|\blim|∑|\bsum", re.I)


def sym_match(text):
    if nt_match(text):
        return False
    if _SYM_SIG.search(text):
        return True
    if "=" in text and not re.search(r"[<>≤≥]", text) and "≡" not in text:
        core = re.sub(r"sqrt|sin|cos|tan|exp|log|pi|integral|lim|sum", "", text, flags=re.I)
        return bool(re.search(r"[a-zA-Z]", core))        # a plain equation carrying free symbols
    return False


def sym_adjudicate(text):
    m = _DERIV.search(text)
    if m:
        v = sympy.Symbol(m.group(1))
        return _verdict(_zero(sympy.diff(_S(m.group(2)), v) - _S(m.group(3))), f"symbolic derivative d/d{v}")
    m = _DERIV2.search(text)
    if m:
        f = _S(m.group(1))
        vs = sorted(f.free_symbols, key=str)
        if len(vs) != 1:
            return None                                  # ambiguous differentiation variable -> defer
        return _verdict(_zero(sympy.diff(f, vs[0]) - _S(m.group(2))), f"symbolic derivative d/d{vs[0]}")
    m = _DEFINT.search(text)
    if m:
        v = sympy.Symbol(m.group(4))
        val = sympy.integrate(_S(m.group(3)), (v, _S(m.group(1)), _S(m.group(2))))
        return _verdict(_zero(val - _S(m.group(5))), "definite integral (exact)")
    m = _DEFINT2.search(text)
    if m:
        v = sympy.Symbol(m.group(2))
        val = sympy.integrate(_S(m.group(1)), (v, _S(m.group(3)), _S(m.group(4))))
        return _verdict(_zero(val - _S(m.group(5))), "definite integral (exact)")
    m = _DEFINT3.search(text)
    if m:
        v = sympy.Symbol(m.group(4))
        val = sympy.integrate(_S(m.group(3)), (v, _S(m.group(1)), _S(m.group(2))))
        return _verdict(_zero(val - _S(m.group(5))), "definite integral (exact)")
    m = _INDEFINT.search(text)
    if m:
        v = sympy.Symbol(m.group(2))
        return _verdict(_zero(sympy.diff(_S(m.group(3)), v) - _S(m.group(1))),
                        "indefinite integral (checked by differentiating the claimed antiderivative)")
    m = _LIM.search(text)
    if m:
        v = sympy.Symbol(m.group(1))
        val = sympy.limit(_S(m.group(3)), v, _S(m.group(2)))
        return _verdict(_zero(val - _S(m.group(4))), f"limit as {v}->{m.group(2)}")
    m = _SUM.search(text)
    if m:
        v = sympy.Symbol(m.group(1))
        val = sympy.summation(_S(m.group(4)), (v, _S(m.group(2)), _S(m.group(3))))
        return _verdict(_zero(sympy.simplify(val - _S(m.group(5)))), "summation closed form")
    if "=" in text and not re.search(r"[<>≤≥]", text) and "≡" not in text:
        parts = text.split("=")
        if len(parts) == 2:
            try:
                A, B = _S(parts[0]), _S(parts[1])
            except Exception:  # noqa: BLE001
                return None
            if A.free_symbols or B.free_symbols:
                return _verdict(_zero(A - B), "algebraic identity (sympy, ∀ over the symbols)")
    return None


# ── oracle: series convergence (sympy convergence tests — sound) ─────────────
# "sum_{k=1}^infinity 1/k^2 converges / diverges" -> Sum(...).is_convergent() (ratio/root/p-series/
# integral/alternating tests). An undecidable case raises -> DEFER; a finite upper bound -> DEFER.

_CONV = re.compile(r"(?:∑|sum)\s*_\s*\{?\s*([a-zA-Z])\s*=\s*(.+?)\s*\}?\s*\^\s*\{?(.+?)\}?\s+(.+?)\s+(?:is\s+)?(converges?|convergent|diverges?|divergent)\b", re.I)


def conv_match(text):
    return bool(_CONV.search(text))


def conv_adjudicate(text):
    m = _CONV.search(text)
    if not m:
        return None
    var = sympy.Symbol(m.group(1))
    if _S(m.group(3)) != sympy.oo:
        return None                                      # convergence is a property of an INFINITE series
    claims_conv = "conver" in m.group(5).lower()
    try:
        c = sympy.Sum(_S(m.group(4)), (var, _S(m.group(2)), sympy.oo)).is_convergent()
    except Exception:  # noqa: BLE001
        return None                                      # no conclusive test -> defer, never guess
    if c not in (True, False):
        return None
    return (SUPPORTED if (bool(c) == claims_conv) else REFUTED,
            f"series {'converges' if c else 'diverges'} (sympy convergence tests)")


# ── oracle 3: modular congruences over ℤ/mℤ (finite exhaustion = complete) ────

_MOD = re.compile(r"(.+?)≡(.+?)\(?\s*mod\s*(\d+)\s*\)?", re.I)


def mod_match(text):
    return "≡" in text and re.search(r"mod\s*\d+", text, re.I) is not None


def mod_adjudicate(text):
    m = _MOD.search(text)
    if not m:
        return None
    lhs = m.group(1).strip().replace("^", "**")
    rhs = m.group(2).strip().replace("^", "**")
    mod = int(m.group(3))
    L, R = sympy.sympify(lhs), sympy.sympify(rhs)    # may raise -> route() defers
    vs = sorted(L.free_symbols | R.free_symbols, key=str)
    if not vs:
        return (SUPPORTED if (int(L) - int(R)) % mod == 0 else REFUTED, f"residue check mod {mod}")
    if mod ** len(vs) > 20000:
        return None
    diff = L - R
    for combo in itertools.product(range(mod), repeat=len(vs)):
        if int(diff.subs(dict(zip(vs, combo)))) % mod != 0:
            cx = ", ".join(f"{v}={c}" for v, c in zip(vs, combo))
            return (REFUTED, f"counterexample mod {mod}: {cx}")
    return (SUPPORTED, f"all {mod}^{len(vs)} residues exhausted mod {mod} — complete")


# ── oracle 4: evidence-type ⊢ claim-wording (illustrative GRADE-style ladder) ─
# Minimal, standalone: enforces that weaker evidence cannot license a stronger claim
# (e.g. observational evidence cannot license a causal claim). Not a full epidemiology engine.

_EV_STRENGTH = {"anecdote": 0, "case_report": 0, "observational_study": 1, "cohort": 1, "case_control": 1,
                "rct": 3, "randomized_trial": 3, "meta_analysis": 4, "systematic_review": 4}
_CLAIM_DEMAND = {"association": 1, "correlation": 1, "causes": 3, "causal": 3, "efficacy": 3}


def ev_match(text):
    return re.search(r"evidence\s*[:=]\s*\w+.*claim\s*[:=]\s*\w+", text, re.I) is not None


def ev_adjudicate(text):
    m = re.search(r"evidence\s*[:=]\s*(\w+).*claim\s*[:=]\s*(\w+)", text, re.I)
    if not m:
        return None
    ev, cl = m.group(1).lower(), m.group(2).lower()
    if ev not in _EV_STRENGTH or cl not in _CLAIM_DEMAND:
        return None                                  # unknown type -> defer, don't guess
    if _EV_STRENGTH[ev] >= _CLAIM_DEMAND[cl]:
        return (SUPPORTED, f"GRADE-style: '{ev}' licenses '{cl}'")
    return (REFUTED, f"GRADE-style: '{ev}' too weak to license '{cl}'")


ORACLES = [
    {"name": "number-theory", "type": "Python (deterministic)",     "match": nt_match, "adjudicate": nt_adjudicate},
    {"name": "closed-form",    "type": "sympy CAS (exact)",          "match": cf_match, "adjudicate": cf_adjudicate},
    {"name": "symbolic",       "type": "sympy calculus/algebra (exact)", "match": sym_match, "adjudicate": sym_adjudicate},
    {"name": "convergence",    "type": "sympy convergence tests (sound)", "match": conv_match, "adjudicate": conv_adjudicate},
    {"name": "modular",        "type": "ℤ/mℤ exhaustion (complete)",  "match": mod_match, "adjudicate": mod_adjudicate},
    {"name": "evidence-type",  "type": "GRADE-style ladder (illustrative)", "match": ev_match, "adjudicate": ev_adjudicate},
]


def _uncovered(text, why="no oracle covers this (uncovered surface)"):
    return {"claim": text, "covered": False, "oracle": "—", "type": "—", "verdict": DEFERRED, "why": why}


def route(text):
    """Dispatch one claim to the first sound oracle that can adjudicate it. Never raises; a crashing oracle
    or an unhandled claim falls through to DEFERRED (a missed check, never a wrong verdict)."""
    if not isinstance(text, str) or not text.strip():
        return _uncovered(text, "empty or non-text input")
    for o in ORACLES:
        try:
            if not o["match"](text):
                continue
            res = o["adjudicate"](text)
        except Exception:  # noqa: BLE001 — a crashing oracle must never decide
            continue
        if res is not None:
            v, why = res
            return {"claim": text, "covered": True, "oracle": o["name"],
                    "type": o["type"], "verdict": v, "why": why}
    return _uncovered(text)


def report(claims):
    """Structured result, no printing — the programmatic API."""
    recs = [route(c) for c in claims]
    covered = [r for r in recs if r["covered"]]
    n, c = len(recs), len(covered)
    return {"records": recs, "n_claims": n, "checkable": c,
            "checkable_fraction": (c / n) if n else 0.0,
            "adjudicated": sum(1 for r in covered if r["verdict"] in (SUPPORTED, REFUTED)),
            "uncovered": [r["claim"] for r in recs if not r["covered"]]}


def shield(claims):
    """Run the shield and print the routing + the coverage report. Returns the records."""
    rep = report(claims)
    recs = rep["records"]
    print("=== oracle shield — route · adjudicate · cover ===\n")
    for r in recs:
        tag = {SUPPORTED: "✓ SUPPORTED", REFUTED: "✗ REFUTED", DEFERRED: "· DEFERRED"}[r["verdict"]]
        lane = f"[{r['oracle']}]" if r["covered"] else "[uncovered]"
        print(f"  {tag:13} {lane:<16} {r['claim']}")
        if r["covered"]:
            print(f"                 trust: {r['type']} — {r['why']}")
    n, c = rep["n_claims"], rep["checkable"]
    print("\n  --- COVERAGE (the denominator most evals hide) ---")
    print(f"  checkable fraction : {c}/{n} = {rep['checkable_fraction'] * 100:.0f}%   (an oracle could take it)")
    print(f"  adjudication rate  : {rep['adjudicated']}/{c} of the checkable got a definite verdict"
          if c else "  adjudication rate  : n/a")
    print(f"  UNCOVERED          : {n - c}/{n} — open-ended claims no oracle touches (the shield's holes)")
    for claim in rep["uncovered"]:
        print(f"      · {claim}")
    print("\n  Trust lives in the oracles; the router is untrusted (a misroute → DEFERRED, never a wrong"
          "\n  verdict). Coverage measured on the input as-given. Add a lane = add an ORACLES entry.")
    return recs


DEMO = [
    "Is 2147483647 prime?",                              # true (2^31-1)
    "Is 152399025 a perfect square?",                    # true (12345^2)
    "Is 1000000007 divisible by 3?",                     # false
    "sqrt(2)+sqrt(3) = sqrt(5+2*sqrt(6))",               # true
    "sqrt(4) = 3",                                       # false
    "d/dx sin(x) = cos(x)",                              # symbolic — true
    "integral_0^1 x^2 dx = 1/3",                         # symbolic — true
    "lim_{x->0} sin(x)/x = 1",                           # symbolic — true
    "sum_{k=1}^n k = n*(n+1)/2",                         # symbolic — true
    "(a+b)^2 = a^2 + 2*a*b + b^2",                       # symbolic identity — true
    "n^5 ≡ n (mod 5)",                                   # true (Fermat)
    "(a+b)^3 ≡ a^3+b^3 (mod 3)",                         # true (freshman's dream mod 3)
    "evidence: observational_study claim: causes",       # refuted (spin)
    "evidence: observational_study claim: association",  # supported
    "This model is safe to deploy.",                     # uncovered
    "Scaling will solve reasoning.",                     # uncovered
]


if __name__ == "__main__":
    shield(DEMO)
