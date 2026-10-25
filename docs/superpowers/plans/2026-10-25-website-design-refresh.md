# ChargeForward Website Design Refresh Plan

> Execute as two sequential, one-commit pull requests.

## PR 1 — Current-data landing experience

1. Extend the static verifier with required hero data hooks and the live-explorer primary action.
2. Replace the historical hero instrument with a current Washington charging network signal.
3. Populate the hero from the generated live data bundle and preserve model proof in the analysis section.
4. Refine responsive styling and verify desktop and mobile rendering.

## PR 2 — Live explorer interaction

1. Extend the static verifier with the new county navigation controls.
2. Add an alphabetical county picker and focused ranking expansion control.
3. Strengthen selected-county feedback on the map and in the metric summary.
4. Refine responsive behavior, keyboard access, and visual hierarchy.

## Verification for each PR

- `python3 scripts/verify_site.py`
- `node --check assets/app.js`
- `.venv/bin/python -m pytest -q`
- `git diff --check`
- Browser review at desktop and mobile widths
