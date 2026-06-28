# Publishing this package — your steps (nothing here is pushed)

This directory is **staged locally, not in any git repo and not pushed.** When you're ready, this is the job
(paste one line at a time):

```
cd /Users/melissaellison/Autonomous-Scientist-Core/dist/oracle-shield
git init
git add -A
git commit -m "oracle-shield: a sound-oracle verification layer with an honest coverage report"
```

Then create an empty repo on GitHub and:

```
git remote add origin git@github.com:MonongahelaHellbender/oracle-shield.git
git branch -M main
git push -u origin main
```

## Before you push — checklist

- [ ] **Add a LICENSE** (MIT or Apache-2.0 for the code). None is included so you choose deliberately.
- [ ] Run `python test_oracle_shield.py` once more — it should print **ALL PASS**.
- [ ] Re-read the README; confirm the honest-limits section still matches what the tool does.
- [ ] **Privacy:** this package is self-contained (only `sympy`); it contains no private-project references.
- [ ] (Optional) publish to PyPI later with `python -m build` + `twine upload` once you want `pip install
      oracle-shield` to work for others.

## Scope

This is the **scoped, public-safe, self-contained** oracle-shield (4 oracles, the router, the coverage
report). The fuller engine (more lanes, the Lean/SAT oracles, the dashboards) stays private; lanes plug into
the same `ORACLES` registry when/if you choose to add them.
