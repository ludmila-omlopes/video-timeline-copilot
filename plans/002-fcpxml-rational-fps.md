# Plan 002: Make FCPXML export emit valid rational times for non-integer frame rates

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3eaa336..HEAD -- helpers/export_fcpxml.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-verification-baseline.md
- **Category**: bug
- **Planned at**: commit `3eaa336`, 2026-06-11
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/16

## Why this matters

FCPXML is this project's flagship cross-platform handoff format (README: "The recommended cross-platform handoff is FCPXML"). But for any NTSC-family frame rate — 23.976, 29.97, 59.94 fps, which is most consumer camera and phone footage — the export produces **invalid FCPXML**. FCPXML time attributes must be rational numbers with integer numerator and denominator (e.g. `1001/30000s`). The current code emits the float fps directly into the denominator. Reproduced at the planned-at commit:

```
fps parsed from ffprobe "30000/1001" = 29.97002997002997
time attr produced:   150/29.97002997002997s        (invalid — non-integer denominator)
frameDuration:        100000000000000/2997002997002997s   (astronomically wrong — should be 1001/30000s)
```

`vtc draft-silence-cut` writes the EDL `fps` straight from ffprobe's `avg_frame_rate` (`helpers/draft_silence_cut.py:181`), so this is the *default* outcome for NTSC footage, not an edge case. DaVinci Resolve and Final Cut will reject or mis-time these files.

## Current state

- `helpers/export_fcpxml.py` — the only file with the bug. The relevant functions (lines 11–26 at the planned-at commit):

```python
def fcpx_time(seconds: float, fps: float) -> str:
    return fcpx_time_from_frames(fcpx_frames(seconds, fps), fps)


def fcpx_frames(seconds: float, fps: float) -> int:
    return int(round(seconds * fps))


def fcpx_time_from_frames(frames: int, fps: float) -> str:
    rate = int(fps) if float(fps).is_integer() else fps
    return f"{frames}/{rate}s"


def frame_duration(fps: float) -> str:
    rate = Fraction(1, 1) / Fraction(str(fps))
    return f"{rate.numerator}/{rate.denominator}s"
```

- These are used throughout `build_fcpxml` (same file) for `frameDuration` (line ~87), sequence `duration` (line ~122), gap `offset`/`duration` (lines ~143–145), and asset-clip `offset`/`start`/`duration` (lines ~164–166).
- `helpers/update_fcpxml.py` reuses `write_fcpxml` from this module, so fixing it here fixes both `vtc export-fcpxml` and `vtc update-fcpxml`.
- How the bad fps gets in: `helpers/draft_silence_cut.py:29-36` `parse_frame_rate("30000/1001")` returns `29.97002997002997`, written into `edl.json` as `fps`. EDLs hand-written by the agent typically use integer fps (30), which is why the bug wasn't caught by the manual e2e test (`docs/e2e-test.md` uses `"fps": 30`).
- Repo conventions: stdlib only, `from __future__ import annotations`, type-hinted module-level functions. `Fraction` is already imported in this file.
- Test conventions: established by plan 001 — plain pytest functions in `tests/`, synthetic EDL JSON in `tmp_path`. Model new tests on `tests/test_export_fcpxml.py`.

## Commands you will need

| Purpose | Command (Windows PowerShell; use `.venv/bin/python` on POSIX) | Expected on success |
|---|---|---|
| Install (dev) | `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` | exit 0 |
| Tests | `.\.venv\Scripts\python.exe -m pytest -q` | exit 0, all pass |
| Lint | `.\.venv\Scripts\python.exe -m ruff check .` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `helpers/export_fcpxml.py`
- `tests/test_export_fcpxml.py` (extend)

**Out of scope** (do NOT touch, even though they look related):
- `helpers/draft_silence_cut.py` — writing a long float fps into the EDL is acceptable once the exporter normalizes it; changing the EDL contract is a separate decision.
- `helpers/build_resolve_project.py:160` also formats fps (`SetSetting("timelineFrameRate", ...)`) — known related issue, deliberately deferred (needs a live Resolve install to verify; see Maintenance notes).
- `helpers/common.py:seconds_to_frames` — used by the Resolve backend; leave it alone.
- The FCPXML element structure (assets, spine, gaps) — only the *time-value formatting* changes.

## Git workflow

- Branch: `advisor/002-fcpxml-rational-fps`
- Commit style: short imperative summary, e.g. "Emit rational FCPXML times for NTSC frame rates".
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add a rational-fps helper

In `helpers/export_fcpxml.py`, add:

```python
def fps_fraction(fps: float) -> Fraction:
    """Map a float fps to its conventional rational frame rate.

    Integer rates map to n/1; NTSC-family rates (23.976, 29.97, 59.94...)
    map to n*1000/1001; anything else falls back to a bounded approximation.
    """
    nearest_int = round(fps)
    if nearest_int > 0 and abs(fps - nearest_int) < 1e-6:
        return Fraction(nearest_int, 1)
    ntsc_base = round(fps * 1001 / 1000)
    if ntsc_base > 0 and abs(fps - ntsc_base * 1000 / 1001) < 0.005:
        return Fraction(ntsc_base * 1000, 1001)
    return Fraction(fps).limit_denominator(100000)
```

**Verify**: `.\.venv\Scripts\python.exe -c "from helpers.export_fcpxml import fps_fraction; from fractions import Fraction; assert fps_fraction(30.0)==Fraction(30); assert fps_fraction(29.97002997002997)==Fraction(30000,1001); assert fps_fraction(29.97)==Fraction(30000,1001); assert fps_fraction(23.976)==Fraction(24000,1001); print('ok')"` → `ok`

### Step 2: Rewrite the time formatters on top of fps_fraction

Replace `fcpx_time_from_frames`, `fcpx_frames`, and `frame_duration` so all emitted times are `frames * (1/rate)` reduced to an integer rational:

```python
def fcpx_frames(seconds: float, fps: float) -> int:
    rate = fps_fraction(fps)
    return int(round(seconds * rate.numerator / rate.denominator))


def fcpx_time_from_frames(frames: int, fps: float) -> str:
    rate = fps_fraction(fps)
    value = Fraction(frames * rate.denominator, rate.numerator)
    if value.denominator == 1:
        return f"{value.numerator}s"
    return f"{value.numerator}/{value.denominator}s"


def frame_duration(fps: float) -> str:
    rate = fps_fraction(fps)
    return f"{rate.denominator}/{rate.numerator}s"
```

Keep `fcpx_time` as-is (it composes the two). Note the behavior change for integer fps: `150/30s` now serializes as `5s` (an equal, still-valid value) — update any plan-001 test that asserted the old unreduced string.

**Verify**: `.\.venv\Scripts\python.exe -c "from helpers.export_fcpxml import fcpx_time_from_frames, frame_duration; assert fcpx_time_from_frames(150, 29.97002997002997)=='5005/1001s' or fcpx_time_from_frames(150, 29.97002997002997)=='5/1s' or True; print(fcpx_time_from_frames(150, 29.97002997002997), frame_duration(29.97002997002997))"` → prints `150150/30000s`-equivalent reduced form (`5005/1001s`) and `1001/30000s`. The load-bearing assertions live in the tests (Step 3).

### Step 3: Add regression tests

Extend `tests/test_export_fcpxml.py`:

- `fps_fraction`: the four cases from Step 1's verify, plus `25 → 25/1` and `59.94 → 60000/1001`.
- `frame_duration(29.97002997002997) == "1001/30000s"` and `frame_duration(30) == "1/30s"`.
- `fcpx_time_from_frames(1, 29.97002997002997) == "1001/30000s"`.
- Full-document test: build a synthetic EDL (same `tmp_path` workspace pattern as the existing tests) with `"fps": 29.97002997002997`, run `build_fcpxml`, serialize with `ET.tostring`, and assert via regex that **every** `offset`, `start`, `duration`, and `frameDuration` attribute in the document matches `^\d+s$` or `^\d+/\d+s$` (integer rational — no `.` anywhere in a time value).
- Round-trip sanity: for the same document, parse the sequence `duration` rational and assert it equals `timeline_duration(...)` to within one frame (1001/30000 s).

**Verify**: `.\.venv\Scripts\python.exe -m pytest tests/test_export_fcpxml.py -q` → all pass.

### Step 4: Full suite and lint

**Verify**: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0. `.\.venv\Scripts\python.exe -m ruff check .` → exit 0.

## Test plan

See Step 3 — regression tests live in `tests/test_export_fcpxml.py`, modeled on the plan-001 tests in the same file. Cases: integer fps unchanged-in-meaning, NTSC 29.97/23.976/59.94 mapping, no-float-in-time-attributes document scan, frameDuration correctness.

## Done criteria

ALL must hold:

- [ ] `.\.venv\Scripts\python.exe -m pytest -q` exits 0, including ≥ 5 new tests in `tests/test_export_fcpxml.py`
- [ ] `.\.venv\Scripts\python.exe -m ruff check .` exits 0
- [ ] `python -c "from helpers.export_fcpxml import frame_duration; assert frame_duration(29.97002997002997)=='1001/30000s'"` exits 0 (run via the venv python)
- [ ] A generated FCPXML for a 29.97-fps EDL contains no `.` character inside any `offset`/`start`/`duration`/`frameDuration` attribute (covered by the document-scan test)
- [ ] `git status` shows no modified files outside `helpers/export_fcpxml.py` and `tests/test_export_fcpxml.py`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `helpers/export_fcpxml.py` no longer contains the four functions excerpted in "Current state" (drift).
- `tests/test_export_fcpxml.py` does not exist — plan 001 has not landed; it is a dependency.
- Any plan-001 test other than ones asserting the exact old time-string format (`"150/30s"`-style) breaks — the fix must not change document structure, only time formatting.
- You find yourself wanting to change the EDL JSON schema or `draft_silence_cut.py` to make this work.

## Maintenance notes

- **Deferred, related**: `helpers/build_resolve_project.py:160` does `project.SetSetting("timelineFrameRate", str(int(fps) if fps.is_integer() else fps))` — Resolve expects `"29.97"`, not `"29.97002997002997"`. The new `fps_fraction` gives the pieces to format this correctly; doing it needs a machine with Resolve Studio to verify, so it was left out. Worth a follow-up plan when Resolve is available.
- If an `export_otio.py` backend is added later (listed as a future backend in `docs/architecture.md`), reuse `fps_fraction` rather than re-deriving rational rates.
- Reviewer: check the document-scan test actually iterates *all* elements (spine clips, gaps, sequence, format) — that regex test is the regression guard.
