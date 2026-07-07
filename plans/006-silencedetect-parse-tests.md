# Plan 006: Make ffmpeg silencedetect output parsing directly testable and test it

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3716700..HEAD -- helpers/draft_silence_cut.py tests/test_draft_silence_cut.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `3716700`, 2026-07-01
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/38

## Why this matters

`vtc draft-silence-cut` is the entry point of the whole silence-removal
feature. It works by running ffmpeg's `silencedetect` filter and regex-parsing
ffmpeg's **stderr** text output. Every existing test monkeypatches
`detect_silences` away, so the parsing code has zero coverage. If a future
ffmpeg version changes its stderr wording even slightly, parsing silently
returns an empty list, the tool cuts nothing, and the user gets an uncut
timeline with no error. This plan extracts the parsing into a pure function and
pins its behavior with fixture-based tests using realistic ffmpeg stderr text.

## Current state

- `helpers/draft_silence_cut.py` — contains `detect_silences(video, noise, duration)`
  (starts at line 40). It builds the ffmpeg command, runs it with
  `subprocess.run(..., capture_output=True, text=True)`, raises `RuntimeError`
  on non-zero exit, then parses `proc.stderr` inline:

```python
# helpers/draft_silence_cut.py:53-72 (inside detect_silences)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"ffmpeg silencedetect failed with exit code {proc.returncode}")

    silences: list[dict] = []
    current_start: float | None = None
    for line in proc.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            current_start = float(start_match.group(1))
            continue

        end_match = re.search(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", line)
        if end_match:
            end = float(end_match.group(1))
            detected_duration = float(end_match.group(2))
            start = current_start if current_start is not None else max(0.0, end - detected_duration)
            silences.append({"start": start, "end": end, "duration": detected_duration})
            current_start = None
    return silences
```

- `tests/test_draft_silence_cut.py` — existing tests are small pure-function
  tests plus `monkeypatch`-based tests. Every test that reaches
  `detect_silences` replaces it entirely, e.g.:

```python
# tests/test_draft_silence_cut.py:178
    monkeypatch.setattr("helpers.draft_silence_cut.detect_silences", lambda video, noise, duration: [])
```

- Real ffmpeg `silencedetect` stderr looks like this (interleaved with other
  ffmpeg output such as progress lines):

```text
[silencedetect @ 0000021c4f4a1b40] silence_start: 1.30245
frame=  120 fps= 60 q=-0.0 size=N/A time=00:00:04.00 bitrate=N/A speed=  30x
[silencedetect @ 0000021c4f4a1b40] silence_end: 3.5045 | silence_duration: 2.20205
```

- Repo conventions: plain pytest functions named `test_<behavior>`, no
  classes, no fixtures beyond `tmp_path`/`monkeypatch`. Tests never invoke
  real ffmpeg/ffprobe. Match the style of the existing tests in
  `tests/test_draft_silence_cut.py`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Install (fresh env only) | `python -m pip install -e ".[dev]"` | exit 0 |
| Tests | `python -m pytest -q` | all pass (136 pass at planning time) |
| Focused tests | `python -m pytest -q tests/test_draft_silence_cut.py` | all pass |
| Lint | `python -m ruff check .` | `All checks passed!` |

On this machine there is a ready venv: prefix commands with
`./.venv/Scripts/python.exe -m` instead of `python -m` if `python -m pytest`
reports "No module named pytest".

## Scope

**In scope** (the only files you should modify):
- `helpers/draft_silence_cut.py` — extract the parse loop into a new pure function.
- `tests/test_draft_silence_cut.py` — add tests.

**Out of scope** (do NOT touch, even though they look related):
- `helpers/audio_refine.py` — different audio analysis path, unrelated regexes.
- The ffmpeg command construction in `detect_silences` (the `cmd` list) — do
  not change flags or filter syntax.
- Any behavior change to parsing. This plan is behavior-preserving refactor +
  tests. The "dangling silence_start" behavior (see Test plan) must be kept
  as-is and only documented.

## Git workflow

- Branch: `advisor/006-silencedetect-parse-tests` (repo convention: `advisor/NNN-<slug>` for plan work, see merged PRs #24–#26).
- Commit style: single short imperative subject line, e.g. `Add silencedetect parse tests` (matches `git log --oneline` style like "Fix SRT timing for record gaps").
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Extract a pure parse function

In `helpers/draft_silence_cut.py`, add a module-level function directly above
`detect_silences`:

```python
def parse_silencedetect_output(stderr: str) -> list[dict]:
```

Move the parse loop (the code from `silences: list[dict] = []` through
`return silences` shown in "Current state") into it verbatim, iterating over
`stderr.splitlines()`. Then make `detect_silences` end with
`return parse_silencedetect_output(proc.stderr)`. No logic changes.

**Verify**: `python -m pytest -q tests/test_draft_silence_cut.py` → all existing tests pass.

### Step 2: Add fixture-based parse tests

In `tests/test_draft_silence_cut.py`, import `parse_silencedetect_output` in
the existing `from helpers.draft_silence_cut import (...)` block and add tests
using realistic stderr strings (use the sample format from "Current state",
including the `[silencedetect @ ...]` prefix and an interleaved `frame=...`
progress line):

1. `test_parse_silencedetect_extracts_paired_silences` — two start/end pairs
   → two dicts with correct `start`, `end`, `duration` floats.
2. `test_parse_silencedetect_ignores_unrelated_lines` — parsing is unaffected
   by interleaved progress/`Stream mapping:` lines.
3. `test_parse_silencedetect_derives_start_from_duration_when_missing` —
   a `silence_end: 5.0 | silence_duration: 2.0` line with no preceding
   `silence_start` → one dict with `start == 3.0`.
4. `test_parse_silencedetect_drops_trailing_unclosed_silence` — input ending
   with a `silence_start` and no matching `silence_end` → that silence is NOT
   reported (this pins the current behavior; see Maintenance notes).
5. `test_parse_silencedetect_returns_empty_for_empty_stderr` — `""` → `[]`.

**Verify**: `python -m pytest -q tests/test_draft_silence_cut.py` → all pass, including 5 new tests.

### Step 3: Add one wiring test for detect_silences error path

Add `test_detect_silences_raises_on_ffmpeg_failure`: monkeypatch
`helpers.draft_silence_cut.find_ffmpeg` to `lambda: "ffmpeg"` and
`helpers.draft_silence_cut.subprocess.run` to return an object with
`returncode=1` and `stderr="boom"` (a `types.SimpleNamespace` is fine), then
assert `detect_silences(Path("x.mp4"), "-35dB", 0.7)` raises `RuntimeError`
with `"boom"` in the message.

**Verify**: `python -m pytest -q` → all pass. `python -m ruff check .` → clean.

## Test plan

Covered by Steps 2–3: happy path, noise-line tolerance, derived start, the
trailing-unclosed-silence edge case, empty input, and the subprocess failure
path. Model the structure after the existing
`test_draft_ranges_uses_transcript_gaps_even_when_audio_is_not_silent`
(monkeypatch style) and the pure-function tests at the top of the same file.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0; ≥6 new tests in `tests/test_draft_silence_cut.py`
- [ ] `python -m ruff check .` exits 0
- [ ] `grep -n "def parse_silencedetect_output" helpers/draft_silence_cut.py` returns one match
- [ ] `detect_silences` still exists and calls the new function (`grep -n "parse_silencedetect_output(proc.stderr)" helpers/draft_silence_cut.py`)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The parse loop in `detect_silences` no longer matches the excerpt above
  (drifted).
- Any pre-existing test in `tests/test_draft_silence_cut.py` fails after the
  extraction — the refactor must be behavior-preserving; do not "fix" existing
  tests to make them pass.
- You find yourself wanting to change the regexes or handle the trailing
  unclosed silence differently — that is a behavior change, out of scope.

## Maintenance notes

- Deliberately pinned quirk: a silence still open at end-of-stream (ffmpeg
  emits `silence_start` with no `silence_end`) is dropped, so trailing silence
  at the very end of a video is never cut. If that is ever deemed a bug, fix
  it in `parse_silencedetect_output` (close the range at total duration) and
  flip test 4 — the test exists to force that conversation.
- If ffmpeg output format changes in a future version, these tests will NOT
  catch it (they use fixture text). The e2e check in `docs/e2e-test.md` is the
  layer that exercises real ffmpeg.
