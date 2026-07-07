# Plan 008: Probe each preview source once, and fix the stale backend list in architecture.md

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3716700..HEAD -- helpers/render_preview.py docs/architecture.md tests/test_preview_qa.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: perf + docs
- **Planned at**: commit `3716700`, 2026-07-01
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/40

## Why this matters

Two small, unrelated-but-tiny fixes bundled to save overhead.

(a) `vtc render-preview` calls `stream_types(source)` once **per range** inside
the render loop. `stream_types` runs a full `ffprobe` subprocess each call
(`helpers/media_tools.py:57-58`, no caching). A timeline with 100 ranges over
2 source files runs ffprobe 100 times instead of 2 — roughly 10s of pure
subprocess overhead wasted. (Honest framing: the per-segment ffmpeg encodes
still dominate total runtime; this is a cheap win, not a dramatic one.)

(b) `docs/architecture.md` lists `export_fcpxml.py` and `update_fcpxml.py`
under "Future backends" although both have existed for months, next to three
modules that don't exist. Anyone (human or agent) reading the doc gets a wrong
picture of what's implemented.

## Current state

- `helpers/render_preview.py` — renders MP4 previews from `edl.json`. The
  per-range loop:

```python
# helpers/render_preview.py:260-290 (abridged)
        for index, item in enumerate(ranges):
            ...
            source = source_paths[item["source"]]
            segment_path = tmp_dir / f"{index:04d}_clip.mp4"
            subprocess.run(
                _segment_args(
                    source,
                    source_start,
                    source_duration,
                    duration,
                    width,
                    height,
                    fps,
                    segment_path,
                    stream_types(source),          # <- line 284: ffprobe per range
                    item.get("transform"),
                ),
                check=True,
            )
```

- `helpers/media_tools.py:57-58`:

```python
def stream_types(path: Path) -> set[str]:
    return {stream.get("codec_type") for stream in ffprobe_json(path).get("streams", [])}
```

- For contrast, `helpers/qa_preview.py:91` already probes once per source by
  building a dict up front.
- `docs/architecture.md:127-133`:

```markdown
Future backends should read the same EDL:

- `export_fcpxml.py`
- `update_fcpxml.py`
- `export_otio.py`
- `export_edl.py`
- `build_premiere_project.py`
```

  Reality: `export_fcpxml.py`, `update_fcpxml.py` (and also
  `import_fcpxml.py`, `build_resolve_project.py`, `update_resolve_timeline.py`)
  exist; `export_otio.py`, `export_edl.py`, `build_premiere_project.py` do not.
- Test conventions: plain pytest + `monkeypatch`, no real ffmpeg. Existing
  render tests (`tests/test_preview_qa.py:75-117`) unit-test `_segment_args`
  only; nothing drives `render_preview()` end to end.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests | `python -m pytest -q` | all pass |
| Focused | `python -m pytest -q tests/test_preview_qa.py` | all pass |
| Lint | `python -m ruff check .` | `All checks passed!` |

On this machine there is a ready venv: use `./.venv/Scripts/python.exe -m ...`
if bare `python -m pytest` reports "No module named pytest".

## Scope

**In scope** (the only files you should modify):
- `helpers/render_preview.py`
- `tests/test_preview_qa.py`
- `docs/architecture.md` (the lines quoted above only)

**Out of scope** (do NOT touch):
- `helpers/media_tools.py` — do NOT add caching (e.g. `lru_cache`) to
  `stream_types`/`ffprobe_json` themselves: files can change on disk between
  CLI invocations within one Python process (tests, future long-lived use),
  and a global cache is a staleness hazard. Cache locally in the render call.
- `helpers/qa_preview.py` — already probes once per source.
- Any other section of `docs/architecture.md`.

## Git workflow

- Branch: `advisor/008-preview-ffprobe-cache`
- Commit style: short imperative subject, e.g. `Probe preview sources once`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Memoize stream_types per source within render_preview

In `helpers/render_preview.py`, inside `render_preview(...)` just before the
`for index, item in enumerate(ranges):` loop, add:

```python
        stream_types_by_source: dict[str, set[str]] = {}
```

In the loop, replace the inline `stream_types(source)` argument with a lookup
that probes each source id at most once:

```python
            source_id = item["source"]
            types = stream_types_by_source.get(source_id)
            if types is None:
                types = stream_types(source)
                stream_types_by_source[source_id] = types
```

and pass `types` to `_segment_args`. Keep everything else in the loop
unchanged. (Lazy per-used-source, not precomputed over all `source_paths` —
an EDL may declare sources no range uses; don't probe those.)

**Verify**: `python -m pytest -q tests/test_preview_qa.py` → all pass.

### Step 2: Add a test that render_preview probes once per source

In `tests/test_preview_qa.py`, add
`test_render_preview_probes_each_source_once(tmp_path, monkeypatch)`:

- Build a minimal EDL JSON in `tmp_path/"edit"/"edl.json"`: one timeline,
  `fps` 30, `resolution` [1920, 1080], one source
  (`{"s1": "raw/clip.mp4"}`), and **three contiguous ranges** all using
  `"source": "s1"` (e.g. record_start 0.0/1.0/2.0, each 1.0s long,
  source_start/source_end pairs 0–1, 1–2, 2–3). Contiguity matters: gaps or
  overlaps raise before rendering.
- Monkeypatch in the `helpers.render_preview` namespace:
  - `find_ffmpeg` → `lambda: "ffmpeg"`
  - `stream_types` → a counting stub appending to a list and returning
    `{"video", "audio"}`
  - `subprocess.run` → a stub recording calls and returning
    `types.SimpleNamespace(returncode=0)` (with `check=True` ffmpeg is never
    actually run; segment files are never created, which is fine because
    `render_preview` does not stat them).
- Call `render_preview(edl_path)` and assert the counting stub was called
  exactly **once** while `subprocess.run` was called 4 times (3 segments + 1
  concat).

Model the monkeypatch style on
`test_qa_preview_writes_report_without_external_probe` in the same file.

**Verify**: `python -m pytest -q tests/test_preview_qa.py` → all pass including the new test. Temporarily reverting Step 1 must make the new test fail (probe count 3) — check this mentally or via `git stash`; do not commit the revert.

### Step 3: Fix the stale backend list in architecture.md

Replace the quoted `docs/architecture.md:127-133` block with:

```markdown
Existing backends that read the same EDL: `export_fcpxml.py`,
`update_fcpxml.py`, `import_fcpxml.py`, `build_resolve_project.py`, and
`update_resolve_timeline.py`.

Future backend candidates should read the same EDL:

- `export_otio.py`
- `export_edl.py`
- `build_premiere_project.py`
```

**Verify**: `python -m ruff check .` → clean; `python -m pytest -q` → all pass.

## Test plan

One new test (Step 2) covering: probe-per-source memoization (the regression
this plan fixes) and, incidentally, the first end-to-end drive of
`render_preview()` with mocked subprocess — happy path with 3 ranges / 1
source. Pattern: `tests/test_preview_qa.py`'s existing monkeypatch tests.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0, including the new probe-count test
- [ ] `python -m ruff check .` exits 0
- [ ] `grep -n "stream_types_by_source" helpers/render_preview.py` → ≥2 matches
- [ ] `grep -n "export_otio" docs/architecture.md` still matches, and the words "Existing backends" appear in `docs/architecture.md`
- [ ] `git status` shows only the three in-scope files changed
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The render loop no longer matches the excerpt (drifted — e.g. someone
  already cached the probe).
- The new test cannot make `render_preview` reach the loop (e.g. validation
  raises on your EDL fixture) after two attempts at fixing the fixture —
  report the exact error instead of loosening validation.
- You are tempted to modify `helpers/media_tools.py` — that is out of scope
  by design (see Scope).

## Maintenance notes

- If `render_preview` ever gains parallel segment rendering, the lazy dict
  memo is not thread-safe; switch to precomputing over used source ids first.
- Reviewer check: the memo keys on the EDL source **id**, not the resolved
  path — two ids pointing at the same file still probe twice. That's
  acceptable (rare, harmless); don't "improve" it to path-keying without
  considering case-insensitive Windows paths.
- Deferred: `docs/architecture.md` may deserve a fuller refresh (module list
  completeness) — out of scope here to keep the diff reviewable.
