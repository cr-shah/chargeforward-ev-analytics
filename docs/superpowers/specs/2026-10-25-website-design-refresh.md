# ChargeForward Website Design Refresh

**Date:** 2026-10-25

## Goal

Make the published case study communicate its decision value within the first screen and make the live county explorer faster to navigate, while preserving the black, warm white, and acid green ChargeForward identity.

## Design direction

The landing view will lead with the current public data bundle. A Washington network visualization, source freshness, statewide EV stock, public port count, and highest opportunity county will replace the historical model chart in the hero. Model quality remains prominent in the analysis section and the hero proof strip.

The live explorer will gain a direct county picker, a compact county summary, and a focused top ranking view. Existing map, score modes, methodology, sources, and model evidence remain available.

## Accuracy and accessibility

- Describe data as current public data, based on each source's update cadence; avoid claiming streaming or real time data.
- Keep a visible methodology trail and caveats for siting decisions.
- Use native controls, keyboard reachable interactions, visible focus states, descriptive SVG labels, and reduced motion behavior.
- Preserve responsive layouts from mobile through wide desktop.

## Delivery

1. PR 1: current-data landing experience.
2. PR 2: live explorer interaction and responsive hierarchy.

Each PR contains one reviewable commit and must pass the static site verifier, JavaScript syntax check, and project test suite.
