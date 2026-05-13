# Contributing to ShidaoSlicer (试刀)

Thanks for your interest in ShidaoSlicer. This is a niche belt-printer fork of
OrcaSlicer; the contribution surface is smaller than upstream's but the
constraints are tighter (hardware safety, math invariants). Please read this
before opening a PR.

## License

By contributing, you agree your code is released under **AGPL-3.0-or-later**,
matching the upstream OrcaSlicer license. No CLA is required.

## What this fork is not

- **Not a place to push general OrcaSlicer changes.** Open those upstream at
  https://github.com/SoftFever/OrcaSlicer instead.
- **Not a place to add features unrelated to belt printers** (multi-extruder
  tuning, Bambu cloud integrations, AMS code, etc.). They will be redirected to
  upstream.

What we DO accept:

- Belt-printer specific bug fixes and features.
- New belt printer profiles (CR-30 variants, other 45° machines, …).
- Improvements to the support preprocessor (`validation/support_preprocess.py`).
- Calibration helpers adapted for belt geometry.
- Better gate rules in `validation/belt_gcode_gate.py`.
- Documentation and tutorials for the belt workflow.

## Before you start

1. **Read `docs/architecture/PIPELINE_MODEL.md`** — the 6-stage model and the
   invariants table. Many changes that look local actually break a downstream
   stage (e.g. R11 = `z_mach ≥ -0.05 mm`, the driver-killer check).
2. **Run the validation suite first** so you know the baseline:
   ```bash
   python3 validation/belt_smoke.sh        # 12 PASS / 2 WARN / 0 FAIL expected
   ```
   If smoke fails on `main`, that's a real bug — open an issue, don't paper over.
3. **Look at open Issues / Discussions** before starting big work — someone may
   already be on it, or there may be a known reason it's not been done.

## PR checklist

For a PR to be considered, it must:

- [ ] Pass `belt_smoke.sh` (no new FAIL, no new BLOCKED gate output).
- [ ] **If it touches the C++ belt transform core** (`GCode.cpp`,
      `GCodeWriter.cpp`, `PrintObject*.cpp`, `BeltTransform.*`):
      include a fixture (synthetic STL + expected gcode + expected R-gate
      decision) in `validation/`. PRs to the transform core without a fixture
      will not be merged — every transform change has a way of breaking
      something downstream that only shows up on real hardware.
- [ ] Include a hardware test report, OR clearly state "untested on hardware".
      Untested PRs may still be merged for non-print-path code (UI, build
      system, docs); print-path code requires a HW report.
- [ ] Update `docs/architecture/PIPELINE_MODEL.md` if you change a stage
      invariant.
- [ ] Pass `git push origin <branch>` — the build/install workflow runs on
      GitHub Actions and must complete.

## Build instructions

Linux (Debian/Ubuntu host):

```bash
./build_linux.sh -u     # first time: install system deps
./build_linux.sh -dsi   # build deps + slicer + AppImage
```

Binary lives in `build/src/Release/orca-slicer` (~135 MB) or
`build/src/Debug/orca-slicer` (~2 GB, ImGui asserts + verbose logs).

macOS / Windows: same workflow as upstream OrcaSlicer
(`build_release_macos.sh`, `build_release_vs2022.bat`). Belt-specific changes
are header-compatible — no extra dependencies.

## Issue templates

When reporting bugs, fill in the issue template that matches your case:

- **Bug report** — for unexpected behavior (crash, wrong slice, gate failure).
  Required fields: printer model, OrcaSlicer/ShidaoSlicer commit hash, attached
  gcode (or `belt_gcode_gate.py` output), repro steps, expected vs actual.
- **Feature request** — for new functionality. Required fields: what hardware
  scenario you're targeting, what UX you'd want, what's blocking with current
  code.

Issues without the relevant fields will be closed asking for them.

## Coding style

- Follow upstream OrcaSlicer style (4-space indent, snake_case for functions,
  `m_` prefix for member fields, `_in_progress` / `_done` style for state).
- New belt-specific code blocks: prefix the comment with `// ORCA_BELT:` or
  `// ShidaoSlicer:` so future maintainers can find them.
- Python validation scripts: PEP 8, type-hint new functions (`def
  f(x: int) -> bool:`).

## Communication

- **Issues** — bugs, feature requests.
- **Discussions** — Q&A, "how do I…", design proposals before opening a PR.
- For sensitive matters (security disclosure): email the maintainer (see
  GitHub profile).

Thanks again. Have fun bending Z into Y.
