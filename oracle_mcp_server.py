#!/usr/bin/env python3
"""oracle-shield MCP server — exposes the sound-oracle verifier as MCP tools.

A Claude client (Claude Code, claude.ai connector, etc.) can call these to get a SOUND verdict on a
checkable claim instead of trusting the model's own reasoning.

Tools:
  verify_claim(claim)   -> route ONE claim: verdict + which oracle + trust basis + reason
  verify_claims(claims) -> batch + an HONEST COVERAGE report (the denominator most evals hide)

Run (stdio):  scientist-env/bin/python oracle_mcp_server.py
"""
import os
import sys

# the self-contained public oracle (sympy-only, 6 lanes) lives next to this file
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle_shield as OS  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("oracle-shield")


@mcp.tool()
def verify_claim(claim: str) -> dict:
    """Verify a SINGLE claim with a sound oracle, instead of trusting model reasoning.

    Returns: verdict (SUPPORTED / REFUTED / DEFERRED), which oracle handled it, its trust basis,
    and the reason. DEFERRED means the claim is not soundly checkable here — that is an honest
    'can't verify', never a wrong verdict.

    Handles: number theory (Is N prime / a perfect square / a perfect cube / divisible? A^B mod M),
    exact arithmetic & algebra, symbolic calculus (derivatives, definite/indefinite integrals,
    limits, finite sums, universal algebraic identities), series convergence, modular congruences,
    and evidence-type / GRADE-style claim wording. Tolerant of common notation (2n, ^, [..], integrate,
    d/dx, lim, sum). Anything else -> DEFERRED.
    """
    r = OS.route(claim)
    return {
        "claim": r["claim"],
        "verdict": r["verdict"],
        "oracle": r["oracle"],
        "trust_basis": r["type"],
        "why": r["why"],
        "soundly_checkable": r["covered"],
    }


@mcp.tool()
def verify_claims(claims: list[str]) -> dict:
    """Verify SEVERAL claims and return per-claim verdicts PLUS an honest coverage report.

    coverage_pct = the fraction that was soundly checkable (the denominator most evaluations hide);
    'uncovered' lists the claims no oracle could touch. Use this to audit a batch of model output.
    """
    rep = OS.report(claims)
    return {
        "records": [
            {"claim": r["claim"], "verdict": r["verdict"], "oracle": r["oracle"], "why": r["why"]}
            for r in rep["records"]
        ],
        "checkable": rep["checkable"],
        "n_claims": rep["n_claims"],
        "coverage_pct": round(100 * rep["checkable_fraction"], 1),
        "adjudicated": rep["adjudicated"],
        "uncovered": rep["uncovered"],
    }


if __name__ == "__main__":
    mcp.run()  # stdio transport
