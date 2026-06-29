#!/usr/bin/env python3
"""oracle — CLI wrapper around the shield.

Pass claims as arguments, or pipe them one-per-line on stdin:

    oracle "Is 91 prime?" "sqrt(9) = 3"
    pbpaste | oracle
    oracle < claims.txt

Each claim is routed to a sound oracle; you get SUPPORTED / REFUTED / DEFERRED
plus the honest coverage report.
"""
import sys

from oracle_shield import shield


def main():
    args = [a for a in sys.argv[1:] if a.strip()]
    claims = args if args else [ln.strip() for ln in sys.stdin if ln.strip()]
    if not claims:
        print('usage: oracle "<claim>" [more...]   |   pbpaste | oracle', file=sys.stderr)
        sys.exit(1)
    shield(claims)


if __name__ == "__main__":
    main()
