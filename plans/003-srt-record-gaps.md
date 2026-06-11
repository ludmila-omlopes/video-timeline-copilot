# Plan 003: Fix SRT export — honor record gaps, repair the transcript cache, sanitize default filenames

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3eaa336..HEAD -- helpers/export_srt.py tests/`
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
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/17

## Why this matters

`vtc export-srt` computes subtitle times by accumulating source durations — it completely ignores `record_start`. Every other consumer of the EDL (FCPXML export, the MP4 preview renderer, the Resolve builder) places clips at their `record_start` and renders black/silence for record gaps. So for any timeline with an intentional gap, the SRT drifts ahead of the actual timeline by the total gap duration — subtitles fire during the wrong clips. The EDL contract (`SKILL.md`, "EDL Contract" section) explicitly supports `record_start`, and the skill instructs the agent to always export SRT, so wrong output ships by default.

Two more defects live in the same function and are fixed together because they share tests:

1. **Broken cache**: the transcript cache is keyed by `str(path)` but membership-checked with a `Path` object, so the check never hits and the transcript JSON is re-read from disk for every range.
2. **Unsanitized default filename**: when a timeline has no explicit `subtitles.path`, the output filename is built from the raw timeline name with only spaces replaced. A timeline name containing `/`, `\`, or `..` writes outside `edit/subtitles/` — bypassing the workspace-containment guarantee that the validator enforces for explicit paths (README: "The EDL validator rejects source and subtitle paths that escape the footage workspace").

## Current state

- `helpers/export_srt.py` — the only implementation file in scope (82 lines). The offset bug (lines 20–53, abbreviated):

```python
def build_srt_for_timeline(edl: dict, timeline: dict, edit_dir: Path, out_path: Path) -> None:
    entries = []
    transcript_cache: dict[str, dict] = {}
    offset = 0.0

    for item in sorted(timeline["ranges"], key=lambda r: float(r.get("record_start", 0))):
        ...
        duration = source_end - source_start
        transcript_path = edit_dir / "transcripts" / f"{Path(timeline['sources'][source_id]).stem}.json"

        if transcript_path not in transcript_cache:          # BUG: keys are str, this is a Path — never True
            if not transcript_path.exists():
                offset += duration
                continue
            transcript_cache[str(transcript_path)] = read_json(transcript_path)

        words = words_in_range(transcript_cache[str(transcript_path)].get("words", []), source_start, source_end)
        chunk = []
        for word in words:
            ...
                local_start = max(source_start, chunk[0]["start"]) - source_start + offset   # BUG: offset ignores record gaps
                local_end = min(source_end, chunk[-1]["end"]) - source_start + offset
        ...
        offset += duration
```

- The default-filename bug (lines 70–77):

```python
    for timeline in edl["timelines"]:
        subtitle_spec = timeline.get("subtitles") or {}
        out_path = subtitle_spec.get("path")
        if out_path:
            target = ensure_within(edit_dir.parent / out_path, edit_dir.parent)
        else:
            target = edit_dir / "subtitles" / f"{timeline['name'].replace(' ', '_')}.srt"   # BUG: unsanitized
```

- Reference semantics to mirror — `helpers/export_fcpxml.py:132-148` and `helpers/render_preview.py:239-260` both do: sort ranges by `record_start`, default a missing `record_start` to the running cursor (back-to-back), insert a gap when `record_start > cursor`, then `cursor = max(cursor, record_start + duration)`. The SRT export must use the same placement rule so all three outputs agree.
- Sanitization convention: `helpers/common.py:38` `safe_filename(value, fallback)` — already used for the same purpose by `export_fcpxml.default_fcpxml_path` (line 217–219) and `render_preview.preview_path`. Containment convention: `helpers/common.py:28` `ensure_within(path, root)`.
- Test conventions: plan 001 created `tests/test_export_srt.py` with synthetic transcript JSON + EDL in `tmp_path`. Extend that file.

## Commands you will need

| Purpose | Command (Windows PowerShell; use `.venv/bin/python` on POSIX) | Expected on success |
|---|---|---|
| Install (dev) | `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` | exit 0 |
| Tests | `.\.venv\Scripts\python.exe -m pytest -q` | exit 0, all pass |
| Lint | `.\.venv\Scripts\python.exe -m ruff check .` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `helpers/export_srt.py`
- `tests/test_export_srt.py` (extend)

**Out of scope** (do NOT touch, even though they look related):
- `helpers/validate_edl.py` — adding a timeline-name validation rule is a separate decision; the fix here is sanitize-at-write.
- `helpers/export_fcpxml.py`, `helpers/render_preview.py` — they are the *reference* for gap semantics, not targets.
- The SRT chunking heuristics (5-word/punctuation grouping, 0.3 s minimum display) — behavior to preserve, not redesign.
- The explicit-`subtitles.path` branch — it is already `ensure_within`-guarded; leave it.

## Git workflow

- Branch: `advisor/003-srt-record-gaps`
- Commit style: short imperative summary, e.g. "Fix SRT timing for record gaps".
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Write failing regression tests first

In `tests/test_export_srt.py`, using the same `tmp_path` workspace pattern as the existing tests (transcript at `edit/transcripts/clip.json`, source key `"A001"` → `"raw/clip.mp4"`):

1. **Gap shifts subtitles**: timeline with two ranges over the same source — range A: `source_start=0, source_end=2, record_start=0`; range B: `source_start=10, source_end=12, record_start=5` (a 3-second record gap after A). Transcript has words at 0.5–1.0 s and 10.5–11.0 s. Assert the second SRT entry's start timestamp is `00:00:05,500` (record-based), not `00:00:02,500` (the current concatenated-offset behavior).
2. **Missing record_start defaults to back-to-back**: range B without a `record_start` key lands at the running cursor (entry at `00:00:02,500`).
3. **Missing transcript still advances the cursor**: range A over a source with no transcript JSON, range B (with transcript) at `record_start=4` → B's entries start at 4 s + word offset.
4. **Default filename is sanitized and contained**: EDL timeline named `"..\\..\\evil"` with no `subtitles` spec → calling `main()`-level export (or the extracted target-resolution logic, see Step 3) writes the file inside `edit/subtitles/` with a sanitized name, and nothing is created outside `tmp_path/edit/`.
5. **Cache hit**: monkeypatch `helpers.export_srt.read_json` with a counting wrapper; a timeline with 3 ranges over the same source triggers exactly 1 read.

Run them; tests 1, 4, 5 must FAIL against current code (2 and 3 may pass incidentally — keep them as guards).

**Verify**: `.\.venv\Scripts\python.exe -m pytest tests/test_export_srt.py -q` → new tests 1/4/5 fail, pre-existing tests pass.

### Step 2: Fix timing and cache in build_srt_for_timeline

Rework the loop to record-based placement, mirroring `export_fcpxml.build_fcpxml`'s cursor rule:

```python
cursor = 0.0
for item in sorted(timeline["ranges"], key=lambda r: float(r.get("record_start", 0))):
    source_id = item["source"]
    source_start = float(item["source_start"])
    source_end = float(item["source_end"])
    duration = source_end - source_start
    record_start = float(item.get("record_start", cursor))

    transcript_path = edit_dir / "transcripts" / f"{Path(timeline['sources'][source_id]).stem}.json"
    cache_key = str(transcript_path)
    if cache_key not in transcript_cache:
        transcript_cache[cache_key] = read_json(transcript_path) if transcript_path.exists() else None
    payload = transcript_cache[cache_key]
    if payload is None:
        cursor = max(cursor, record_start + duration)
        continue

    words = words_in_range(payload.get("words", []), source_start, source_end)
    # ... existing chunking unchanged, but entry times become:
    #   local_start = max(source_start, chunk[0]["start"]) - source_start + record_start
    #   local_end   = min(source_end, chunk[-1]["end"]) - source_start + record_start
    cursor = max(cursor, record_start + duration)
```

Keep the chunking block byte-for-byte except the two time expressions (`+ offset` → `+ record_start`); delete the `offset` variable entirely.

**Verify**: `.\.venv\Scripts\python.exe -m pytest tests/test_export_srt.py -q` → tests 1, 2, 3, 5 pass.

### Step 3: Sanitize the default output filename

In `main()` (line ~76), change the default branch to:

```python
from helpers.common import safe_filename   # add to the existing common import line
...
target = ensure_within(
    edit_dir / "subtitles" / f"{safe_filename(str(timeline['name']), 'timeline')}.srt",
    edit_dir.parent,
)
```

Note `safe_filename` replaces spaces with `_` too, so `"Main Timeline"` still becomes `Main_Timeline.srt` — the e2e doc's expected output (`docs/e2e-test.md`, `test_video/edit/subtitles/Main_Timeline.srt`) is unchanged.

**Verify**: `.\.venv\Scripts\python.exe -m pytest tests/test_export_srt.py -q` → all pass, including test 4.

### Step 4: Full suite and lint

**Verify**: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0. `.\.venv\Scripts\python.exe -m ruff check .` → exit 0.

## Test plan

See Step 1 — five regression tests in `tests/test_export_srt.py`, modeled on the plan-001 tests in the same file. The gap test (case 1) is the headline regression; the timestamp assertion must check the rendered `HH:MM:SS,mmm` string, not internal floats.

## Done criteria

ALL must hold:

- [ ] `.\.venv\Scripts\python.exe -m pytest -q` exits 0, including ≥ 5 new tests in `tests/test_export_srt.py`
- [ ] The gap regression test asserts a record-based timestamp (`00:00:05,500`) and passes
- [ ] `grep -n "offset" helpers/export_srt.py` returns no matches (PowerShell: `Select-String -Path helpers/export_srt.py -Pattern "offset"`)
- [ ] `grep -n "replace(' ', '_')" helpers/export_srt.py` returns no matches
- [ ] `git status` shows no modified files outside `helpers/export_srt.py` and `tests/test_export_srt.py`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `helpers/export_srt.py` no longer matches the "Current state" excerpts (drift).
- `tests/test_export_srt.py` does not exist — plan 001 has not landed; it is a dependency.
- A plan-001 test fails in a way that suggests it encoded the *old* gap-ignoring behavior as correct for a timeline WITH gaps — plan 001 was instructed not to do that; report instead of silently rewriting it.
- Matching the FCPXML cursor semantics appears to require touching `export_fcpxml.py` or `render_preview.py`.

## Maintenance notes

- All three timeline consumers (FCPXML, preview renderer, SRT) now share the same informal placement rule (sort by `record_start`, default to cursor, cursor = max). If a fourth backend is added (e.g. the `export_otio.py` mentioned in `docs/architecture.md`), consider extracting this iteration into a shared helper in `helpers/common.py` — deliberately not done here to keep the diff reviewable.
- Reviewer: scrutinize the chunking block diff — it must be unchanged except the two `+ record_start` expressions.
- Deferred: overlapping record ranges (two ranges covering the same record time) produce overlapping subtitles in all backends; the validator doesn't flag overlaps. Recorded in `plans/README.md` as an unplanned finding.
