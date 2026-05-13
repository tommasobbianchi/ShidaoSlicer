# Description

<!--
What does this PR change and why? Link the issue it addresses, if any.
-->

## Belt impact

<!-- Check ALL that apply: -->

- [ ] **Touches the C++ belt transform core** (`GCode.cpp`, `GCodeWriter.cpp`,
      `PrintObject*.cpp`, `BeltTransform.*`) — requires a validation fixture
      (synthetic STL + expected gcode + expected R-gate decision) under
      `validation/`. PRs to the transform core without a fixture WILL NOT be
      merged. See `docs/architecture/PIPELINE_MODEL.md`.
- [ ] Touches `validation/support_preprocess.py` (support generation).
- [ ] Touches `validation/belt_gcode_gate.py` (safety gate).
- [ ] Touches the belt-aware GUI (Plater, GCodeViewer, Preview/Device tabs).
- [ ] Documentation / build / CI only — no print-path impact.

## Testing

- [ ] `python3 validation/belt_smoke.sh` reports the same PASS/WARN/FAIL counts
      as `main` (no new failures).
- [ ] If the PR changes gcode output: attached gate report for a representative
      slice (`python3 validation/belt_gcode_gate.py out.gcode`). R7 and R11
      must PASS.
- [ ] Hardware test: printed on a real belt printer and reported result, OR
      explicitly flagged "untested on HW" (acceptable only for non-print-path
      changes).

## Screenshots / video

<!--
Useful for GUI changes, preview rendering bugs, slicer geometry changes.
For HW tests, attach a photo of the print and (if relevant) the printer
console / Klipper log.
-->

## Notes for the reviewer

<!-- Anything weird, anything you tried and reverted, edge cases discovered. -->
