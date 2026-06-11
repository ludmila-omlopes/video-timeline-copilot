# Plan 004: Stop `vtc inventory` from indexing generated files in the edit directory

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3eaa336..HEAD -- helpers/inventory.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-verification-baseline.md
- **Category**: bug
- **Planned at**: commit `3eaa336`, 2026-06-11
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/18

## Why this matters

`vtc inventory` recursively scans the whole footage folder for video files. The generated outputs also live inside that folder, under `edit/` — including MP4 previews from `vtc render-preview` (`edit/previews/<project>_preview.mp4`). So the second time inventory runs in a workspace (a normal occurrence: the skill flow re-inventories when footage is added, and agents re-run steps freely), the media index lists the project's *own rendered previews as source footage*. The agent reading `media_index.json` can then transcribe or cut from a preview render — garbage in the edit, wasted transcription time, and a confusing index. The fix is to exclude the edit directory (and dot-directories) from the scan.

## Current state

- `helpers/inventory.py` — the scan is in `main()` (lines 69–88 at the planned-at commit):

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Index local video media into edit/media_index.json")
    parser.add_argument("folder", type=Path, help="Folder containing source media")
    parser.add_argument("--edit-dir", type=Path, default=None, help="Output edit directory")
    args = parser.parse_args()

    root = args.folder.resolve()
    edit_dir = (args.edit_dir or root / "edit").resolve()
    videos = sorted(p for p in root.rglob("*") if p.suffix.lower() in VIDEO_EXTENSIONS)   # BUG: includes edit_dir outputs
    items = []

    for video in videos:
        try:
            items.append(ffprobe(video))
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            items.append({"path": str(video), "error": str(exc)})

    out = edit_dir / "media_index.json"
    write_json(out, {"root": str(root), "media": items})
    print(f"indexed {len(items)} media file(s) -> {out}")
```

- `VIDEO_EXTENSIONS` comes from `helpers/common.py:9`: `{".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}`.
- Files that end up under `edit/` and match those extensions: `edit/previews/*_preview.mp4` (written by `helpers/render_preview.py`). Future outputs may add more.
- Repo conventions: stdlib only, `from __future__ import annotations`, `pathlib` everywhere, small pure helpers that `main()` orchestrates (see `helpers/draft_silence_cut.py` for the pattern of extracted testable functions).
- Test conventions: plan 001 — plain pytest functions, `tmp_path` workspaces, `monkeypatch` where subprocess calls must be avoided. There is no existing `tests/test_inventory.py`; this plan creates it. Tests must NOT require `ffprobe` to be installed.

## Commands you will need

| Purpose | Command (Windows PowerShell; use `.venv/bin/python` on POSIX) | Expected on success |
|---|---|---|
| Install (dev) | `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` | exit 0 |
| Tests | `.\.venv\Scripts\python.exe -m pytest -q` | exit 0, all pass |
| Lint | `.\.venv\Scripts\python.exe -m ruff check .` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `helpers/inventory.py`
- `tests/test_inventory.py` (create)

**Out of scope** (do NOT touch, even though they look related):
- `helpers/common.py` — `VIDEO_EXTENSIONS` stays where it is.
- `helpers/transcribe.py` transcript-name collisions and stale-cache behavior — separate known finding, recorded in `plans/README.md`.
- Any change to the `media_index.json` schema — downstream consumers (`helpers/export_fcpxml.py:load_media_index`) read it.

## Git workflow

- Branch: `advisor/004-inventory-exclude-edit-outputs`
- Commit style: short imperative summary, e.g. "Exclude edit outputs from media inventory".
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Extract a testable scan function with the exclusion

In `helpers/inventory.py`, add above `main()`:

```python
def iter_source_videos(root: Path, edit_dir: Path) -> list[Path]:
    """List source video files under root, excluding generated edit outputs
    and hidden directories."""
    videos = []
    edit_dir = edit_dir.resolve()
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        resolved = path.resolve()
        if edit_dir == resolved or edit_dir in resolved.parents:
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        videos.append(path)
    return videos
```

Then in `main()`, replace the `videos = sorted(...)` line with:

```python
    videos = iter_source_videos(root, edit_dir)
```

**Verify**: `.\.venv\Scripts\python.exe -c "import helpers.inventory as m; assert callable(m.iter_source_videos); print('ok')"` → `ok`

### Step 2: Add tests

Create `tests/test_inventory.py` (no ffprobe needed — only `iter_source_videos` is tested):

1. **Excludes edit outputs**: build `tmp_path/raw/clip.mp4`, `tmp_path/edit/previews/proj_preview.mp4`, `tmp_path/edit/clip2.mp4` (all `write_bytes(b"")`). `iter_source_videos(tmp_path, tmp_path / "edit")` returns exactly `[raw/clip.mp4]`.
2. **Custom edit dir**: outputs under `tmp_path/custom_edit/` are excluded when `edit_dir=tmp_path/"custom_edit"`, while `tmp_path/edit/x.mp4` (now just a regular folder) IS included.
3. **Extension filter**: `raw/notes.txt` and `raw/clip.MOV` (uppercase) → only the `.MOV` is returned (case-insensitive match).
4. **Hidden directories skipped**: `tmp_path/.cache/clip.mp4` is not returned.
5. **Edit dir outside root**: `edit_dir` pointing outside `tmp_path` (e.g. a sibling temp dir) does not raise and returns the normal source list.

**Verify**: `.\.venv\Scripts\python.exe -m pytest tests/test_inventory.py -q` → 5 tests pass.

### Step 3: Full suite and lint

**Verify**: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0. `.\.venv\Scripts\python.exe -m ruff check .` → exit 0.

## Test plan

See Step 2 — `tests/test_inventory.py`, 5 cases, modeled structurally on the plan-001 test files (plain functions + `tmp_path`). No subprocess, no ffprobe.

## Done criteria

ALL must hold:

- [ ] `.\.venv\Scripts\python.exe -m pytest -q` exits 0, including 5 new tests in `tests/test_inventory.py`
- [ ] `helpers/inventory.py` `main()` calls `iter_source_videos(root, edit_dir)`; the inline `rglob` filter line is gone
- [ ] A workspace containing `edit/previews/x_preview.mp4` yields a `media_index.json` without that file (covered by test 1 at the function level)
- [ ] `git status` shows no modified files outside `helpers/inventory.py` and `tests/test_inventory.py`
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `helpers/inventory.py` `main()` no longer matches the "Current state" excerpt (drift).
- `tests/` does not exist or `python -m pytest` is not runnable — plan 001 has not landed; it is a dependency.
- You are tempted to also dedupe/restructure `media_index.json` — schema is out of scope.

## Maintenance notes

- If a future command writes video files anywhere other than under `edit/` (e.g. a proxy folder), `iter_source_videos` needs to learn about it — keep all generated video outputs under `edit/` to avoid that.
- Reviewer: check the `edit_dir in resolved.parents` containment logic against a nested custom `--edit-dir` (test 2 covers it).
- Related unplanned finding (recorded in the index): `vtc transcribe` caches by source *stem* only, so two sources with the same filename in different subfolders collide in `edit/transcripts/`, and a changed source with an existing transcript is silently served stale.
