# Plan 001: Establish a verification baseline — pytest suite, ruff, and CI

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3eaa336..HEAD -- pyproject.toml helpers/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `3eaa336`, 2026-06-11
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/15

## Why this matters

This repo has **zero automated tests, no linter, and no CI**. The only verification today is a manual end-to-end checklist (`docs/e2e-test.md`) that requires real footage, FFmpeg, and a human. Yet most of the codebase is pure-function logic (range math, time formatting, EDL validation, XML assembly) that is trivially unit-testable without any media files. Several confirmed bugs (invalid FCPXML for NTSC frame rates, SRT subtitle drift across record gaps) are queued in plans 002–005, and none of those fixes can be landed safely or proven correct without a test harness. This plan is the prerequisite for every other plan in `plans/`. A CI matrix across Windows/Linux/macOS also directly serves the README's stated goal: "Broader Linux/macOS testing ... planned for a later compatibility pass."

## Current state

- `pyproject.toml` — setuptools project, no dev dependencies, no test/lint config. Full current content:

```toml
[project]
name = "video-timeline-copilot"
version = "0.1.0"
description = "Transcript-first AI timeline generation with DaVinci Resolve project output"
readme = "README.md"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
transcribe = ["faster-whisper>=1.1.0"]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["helpers"]

[project.scripts]
vtc = "helpers.cli:main"
```

- `helpers/` — 16 small stdlib-only modules (~2,100 lines total). Each command module has a `main()` using `argparse`. All use `from __future__ import annotations`, type hints, and `pathlib`. The only third-party dependency is the optional `faster-whisper` (imported lazily inside `helpers/transcribe.py:main`).
- There is no `tests/` directory, no `.github/` directory, and no lint configuration anywhere in the repo.
- Pure functions worth testing (verified to exist at these locations as of the planned-at commit):
  - `helpers/common.py` — `safe_filename` (line 38), `srt_timestamp` (line 47), `ensure_within` (line 28), `seconds_to_frames` (line 43), `resolve_relative` (line 21).
  - `helpers/draft_silence_cut.py` — `parse_frame_rate` (line 29), `complement_silences` (line 81), `snap_to_words` (line 110), `pad_ranges` (line 127), `merge_ranges` (line 135), `normalize_negative_noise_arg` (line 229).
  - `helpers/pack_transcripts.py` — `group_words` (line 15), `normalize_text` (line 41), `repeated_delivery_note` (line 47).
  - `helpers/validate_edl.py` — `validate` (line 35), `cut_inside_word` (line 28), `cut_quality_warnings` (line 100). `validate()` reads an EDL JSON from disk and checks that source files exist, so tests create a temp workspace (`tmp_path/edit/edl.json` + empty `tmp_path/raw/clip.mp4` placeholder files).
  - `helpers/export_fcpxml.py` — `timeline_duration` (line 208), `fcpx_time_from_frames` (line 19), `frame_duration` (line 24), `default_fcpxml_path` (line 217), `build_fcpxml` (line 62). `build_fcpxml` does NOT require source files to exist (it only resolves paths and checks workspace containment), so a synthetic EDL in `tmp_path` is enough to test the generated XML structure.
  - `helpers/export_srt.py` — `words_in_range` (line 9), `build_srt_for_timeline` (line 20). Needs a synthetic transcript JSON at `tmp_path/edit/transcripts/<stem>.json`.

No tests should invoke `ffmpeg`/`ffprobe` or `faster-whisper` — anything that would need them is out of scope for this plan.

## Commands you will need

| Purpose | Command (Windows PowerShell) | Expected on success |
|---|---|---|
| Create venv | `python -m venv .venv` | exit 0 |
| Install (dev) | `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` | exit 0 |
| Tests | `.\.venv\Scripts\python.exe -m pytest` | exit 0, all pass |
| Lint | `.\.venv\Scripts\python.exe -m ruff check .` | exit 0 |

On macOS/Linux substitute `.venv/bin/python`. The `dev` extra does not exist yet — Step 1 creates it. If a `.venv` already exists in your working copy, reuse it instead of recreating it.

## Scope

**In scope** (the only files you should create or modify):
- `pyproject.toml` (add `dev` extra and ruff config)
- `tests/` (create; all new test files)
- `.github/workflows/ci.yml` (create)
- `helpers/*.py` — ONLY to fix trivial ruff findings (unused imports, unused variables). No behavioral changes.

**Out of scope** (do NOT touch):
- Any behavioral change to `helpers/` — bugs you notice are covered by plans 002–005; do not fix them here. In particular do NOT "fix" the SRT gap handling or FCPXML time format even if a test reveals they look wrong.
- `helpers/transcribe.py`, `helpers/build_resolve_project.py`, `helpers/update_resolve_timeline.py`, `helpers/resolve_env_check.py` internals — they need external runtimes (faster-whisper, DaVinci Resolve); no tests for them in this plan.
- `docs/`, `README.md`, `SKILL.md`, `examples/`.

## Git workflow

- Branch: `advisor/001-verification-baseline`
- Commit style: short imperative summary line, matching repo history (e.g. "Add deterministic draft silence cuts"). Suggested: "Add pytest suite, ruff config, and CI workflow".
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add the dev extra and ruff config to pyproject.toml

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
transcribe = ["faster-whisper>=1.1.0"]
dev = ["pytest>=8.0", "ruff>=0.4"]
```

(keep the existing `transcribe` line; add `dev` next to it), and at the end of the file:

```toml
[tool.ruff]
target-version = "py310"
```

Do not configure extra ruff rule sets — the default rule set (E4/E7/E9/F) is the baseline.

**Verify**: `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` → exit 0; `.\.venv\Scripts\python.exe -m ruff --version` → prints a version.

### Step 2: Run ruff and fix only trivial findings

Run `.\.venv\Scripts\python.exe -m ruff check .`. Expected: zero or a small number of findings (unused imports/variables). Fix only mechanical findings (delete unused import, rename unused loop variable to `_`). 

**Verify**: `.\.venv\Scripts\python.exe -m ruff check .` → exit 0, "All checks passed".

### Step 3: Write the unit test suite

Create `tests/` with an empty `tests/__init__.py` NOT required (pytest rootdir discovery works without it; do not add one). Write these files. Use plain `pytest` style: module-level test functions, `tmp_path` fixture for filesystem work, no classes, no mocks except `monkeypatch` where stated.

1. `tests/test_common.py` — for `helpers.common`:
   - `safe_filename`: replaces illegal characters (`"a/b:c" → "a_b_c"`), strips leading/trailing `._-`, returns fallback for empty/garbage-only input.
   - `srt_timestamp`: `0.0 → "00:00:00,000"`, `3661.5 → "01:01:01,500"`, negative input clamps to `"00:00:00,000"`, millisecond rounding (`1.9995 → "00:00:02,000"`).
   - `ensure_within`: path inside root returns resolved path; `root/../escape` raises `ValueError`.
   - `seconds_to_frames`: `(1.0, 30) → 30`, rounding behavior `(0.49/30 ...)` — assert `seconds_to_frames(0.5, 30) == 15` and `seconds_to_frames(0.016, 30) == 0`.
2. `tests/test_draft_silence_cut.py` — for `helpers.draft_silence_cut`:
   - `parse_frame_rate`: `"30000/1001"` → `pytest.approx(29.97002997)`, `"25"` → 25.0, `None` → 30.0, `"0/0"` → 30.0.
   - `complement_silences`: no silences → one full range; silences at start/middle/end produce correct complements; silence extending past `total_duration` is clamped.
   - `pad_ranges`: padding clamps at 0 and `total_duration`; zero-length ranges dropped.
   - `merge_ranges`: ranges closer than `merge_gap` merge; segments shorter than `min_segment` are dropped; result sorted.
   - `snap_to_words`: empty word list returns input unchanged; a range overlapping words expands/contracts to word boundaries ± padding; a range overlapping no words is kept as-is.
   - `normalize_negative_noise_arg`: `["--noise", "-35dB"]` becomes `["--noise=-35dB"]`; other args pass through.
3. `tests/test_pack_transcripts.py` — for `helpers.pack_transcripts`:
   - `group_words`: words with a gap ≥ threshold split into two phrases; words missing start/end are skipped.
   - `normalize_text`: lowercases, strips punctuation, collapses whitespace.
   - `repeated_delivery_note`: near-identical phrase within window returns a note; phrase below `min_words` returns `None`; previous phrase outside `repeat_window` returns `None`.
4. `tests/test_validate_edl.py` — build a temp workspace per test: `tmp_path/raw/clip.mp4` (write `b""`), `tmp_path/edit/edl.json` (write a minimal valid EDL modeled on the one in `docs/e2e-test.md` section 5, with `sources: {"A001": "raw/clip.mp4"}`). Cases:
   - valid EDL → `validate()` returns `[]`.
   - missing source file → error mentioning "does not exist".
   - source path `"../outside.mp4"` → error mentioning "escapes workspace".
   - `fps: 0` → error; `source_end <= source_start` → error; `media_type: "audio"` → error.
   - `cut_inside_word`: cut strictly inside a word returns the word; cut within tolerance of a boundary returns `None`.
5. `tests/test_export_fcpxml.py` — synthetic EDL at `tmp_path/edit/edl.json` with **integer fps 30** (do NOT add fractional-fps tests here — plan 002 owns those):
   - `timeline_duration`: max of `record_start + (source_end - source_start)` over ranges.
   - `build_fcpxml`: returns a tree whose root tag is `fcpxml`; one `asset` per source; an EDL with two ranges where the second `record_start` leaves a gap produces a `gap` element in the `spine`; a range whose duration rounds to zero frames raises `ValueError`.
   - `default_fcpxml_path`: project name with spaces/illegal chars is sanitized into the filename.
6. `tests/test_export_srt.py` — synthetic transcript at `tmp_path/edit/transcripts/clip.json` containing `{"words": [...]}` with a handful of timed words; EDL timeline with one range and `record_start: 0` (do NOT test timelines with record gaps here — plan 003 owns gap behavior and will change it):
   - `build_srt_for_timeline` writes an `.srt` whose first entry starts at `00:00:00` and contains the expected words.
   - a range over a source with no transcript file produces an empty SRT (no entries).
   - `words_in_range` includes words overlapping the range boundary and excludes words fully outside.

**Verify**: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0; at least 30 tests collected and passing.

### Step 4: Add the CI workflow

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.10", "3.12"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install -e ".[dev]"
      - run: python -m ruff check .
      - run: python -m pytest -q
```

**Verify**: `python -c "import pathlib; t=pathlib.Path('.github/workflows/ci.yml').read_text(); assert 'matrix' in t and 'pytest' in t; print('ok')"` → prints `ok`. (Full YAML validation happens when CI first runs; tests must not require ffmpeg, which is why the workflow installs none.)

## Test plan

The test suite IS the deliverable — see Step 3. Structural pattern: there is no existing test to model after; use plain pytest functions with `tmp_path`, one assertion theme per test, named `test_<function>_<case>`.

## Done criteria

ALL must hold:

- [ ] `.\.venv\Scripts\python.exe -m pytest -q` exits 0 with ≥ 30 tests passing
- [ ] `.\.venv\Scripts\python.exe -m ruff check .` exits 0
- [ ] `pyproject.toml` contains a `dev` optional-dependency group with pytest and ruff
- [ ] `.github/workflows/ci.yml` exists and references both `ruff check` and `pytest`
- [ ] `git status` shows no modified files outside the in-scope list
- [ ] No test imports `faster_whisper` or shells out to `ffmpeg`/`ffprobe`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- A function named in "Current state" does not exist at (approximately) the cited location — the codebase has drifted.
- Making a test pass appears to require changing behavior in `helpers/` (beyond deleting unused imports). That means you found a real bug — record which test and which module, mark the test `xfail` with a reason referencing the plan number if one of plans 002–005 covers it, and report.
- `pip install -e ".[dev]"` fails for reasons other than a typo you introduced.
- Ruff reports findings that cannot be fixed mechanically (i.e., anything beyond unused imports/variables).

## Maintenance notes

- Plans 002–005 each add regression tests to this suite; their "Done criteria" assume `python -m pytest` works as established here.
- The CI matrix doubles as the README's promised Linux/macOS compatibility signal for the pure-Python layer. Real media-path validation (ffmpeg-dependent) is intentionally deferred — a future plan could add an optional CI job that installs ffmpeg and runs `draft-silence-cut` against a generated test tone.
- Reviewers should scrutinize that tests assert real values (timestamps, XML structure), not just "no exception raised".
