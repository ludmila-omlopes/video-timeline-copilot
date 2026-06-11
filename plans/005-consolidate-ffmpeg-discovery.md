# Plan 005: Consolidate ffmpeg/ffprobe discovery into one cached module

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3eaa336..HEAD -- helpers/ tests/`
> Note: `helpers/render_preview.py` and `helpers/qa_preview.py` were UNTRACKED
> at the planned-at commit (see STOP conditions). If other in-scope files
> changed, compare the "Current state" excerpts against the live code before
> proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (touches subprocess plumbing used by four commands)
- **Depends on**: plans/001-verification-baseline.md
- **Category**: tech-debt
- **Planned at**: commit `3eaa336`, 2026-06-11
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/19

## Why this matters

FFmpeg tool discovery is implemented four different ways across the helpers, with three user-visible consequences:

1. **Inconsistent behavior**: `vtc render-preview` finds ffmpeg via WinGet/Program Files fallback paths when it's not on `PATH`, but `vtc draft-silence-cut` gives up immediately (`shutil.which` only). Same machine, same install — one command works, the other errors. The git history shows the fallback was added precisely because a real user hit this ("Resolve ffprobe from common install paths", commit `3b5c8d5`).
2. **Repeated filesystem scans**: `render_preview` calls its `find_ffmpeg()` inside the argument-builder for *every segment* of the preview. When ffmpeg is not on `PATH`, each call recursively globs all of `Program Files` — for an EDL with dozens of kept ranges (typical for silence cuts) that is dozens of full recursive directory scans per render.
3. **Duplicated probing**: `stream_types()` exists twice with different implementations (`render_preview.py`, `qa_preview.py`), and `qa_preview` probes the same file twice (once for streams, once for duration) because the two wrappers each call `ffprobe_json`.

One small module with cached lookups fixes the inconsistency, the rescans, and the duplication at once.

## Current state

Four discovery/probing implementations:

- `helpers/inventory.py:13-37` — `find_ffprobe()`: `shutil.which` + WinGet + Program Files recursive glob fallback. Imported by `render_preview.py` and `qa_preview.py`.
- `helpers/draft_silence_cut.py:22-26` — `find_ffmpeg()`: `shutil.which` only, no fallback:

```python
def find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise FileNotFoundError("ffmpeg was not found on PATH. Install FFmpeg or add its bin directory to PATH.")
```

- `helpers/render_preview.py:16-36` — `find_ffmpeg()`: `shutil.which` + WinGet + Program Files glob fallback (same shape as `inventory.find_ffprobe`). Called, uncached, inside `_segment_args` (line ~121), `_gap_args` (line ~154), and `_concat_args` (line ~193) — i.e., once per rendered segment.
- `helpers/render_preview.py:39-55` — `stream_types(path)`: inline ffprobe subprocess.
- `helpers/qa_preview.py:14-41` — `ffprobe_json(path)`, `stream_types(path)`, `media_duration(path)`: a second, separate ffprobe-JSON wrapper stack. `qa_preview` imports `find_ffmpeg` and `preview_path` from `render_preview`.
- `helpers/inventory.py:40-66` — `ffprobe(path)`: builds its own ffprobe JSON call and flattens it into the media-index dict shape; used by `draft_silence_cut` too.

Repo conventions: stdlib only, `from __future__ import annotations`, type hints, `pathlib`. Shared pure helpers live in `helpers/common.py`, which deliberately has no `subprocess` import — so the new shared module is a NEW file, not an addition to `common.py`.

Test conventions: plan 001 — plain pytest functions, `tmp_path`, `monkeypatch`; no test may require ffmpeg/ffprobe to actually be installed.

## Commands you will need

| Purpose | Command (Windows PowerShell; use `.venv/bin/python` on POSIX) | Expected on success |
|---|---|---|
| Install (dev) | `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` | exit 0 |
| Tests | `.\.venv\Scripts\python.exe -m pytest -q` | exit 0, all pass |
| Lint | `.\.venv\Scripts\python.exe -m ruff check .` | exit 0 |

## Scope

**In scope** (the only files you should create or modify):
- `helpers/media_tools.py` (create)
- `helpers/inventory.py`, `helpers/draft_silence_cut.py`, `helpers/render_preview.py`, `helpers/qa_preview.py` (switch to the new module)
- `tests/test_media_tools.py` (create)

**Out of scope** (do NOT touch, even though they look related):
- `helpers/inventory.py:ffprobe()`'s *return shape* — `media_index.json` consumers depend on it; only its tool-discovery call changes.
- The ffmpeg argument lists in `render_preview.py` (`-ss`/`-t`/filters/codecs) — rendering behavior must not change.
- `helpers/transcribe.py` — faster-whisper finds its own ffmpeg; not part of this.
- `helpers/common.py` — keep it subprocess-free.

## Git workflow

- Branch: `advisor/005-consolidate-ffmpeg-discovery`
- Commit style: short imperative summary, e.g. "Consolidate cached ffmpeg/ffprobe discovery".
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Create helpers/media_tools.py

New module containing, moved/merged from the implementations above:

```python
from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
from pathlib import Path


def _find_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found

    exe = f"{name}.exe"
    candidates: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if packages.exists():
            candidates.extend(packages.glob(f"**/{exe}"))
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root:
            candidates.extend(Path(root).glob(f"**/{exe}"))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        f"{name} was not found on PATH or in common FFmpeg install locations. "
        "Install FFmpeg or add its bin directory to PATH."
    )


@functools.lru_cache(maxsize=None)
def find_ffmpeg() -> str:
    return _find_tool("ffmpeg")


@functools.lru_cache(maxsize=None)
def find_ffprobe() -> str:
    return _find_tool("ffprobe")


def ffprobe_json(path: Path) -> dict:
    proc = subprocess.run(
        [find_ffprobe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def stream_types(path: Path) -> set[str]:
    return {stream.get("codec_type") for stream in ffprobe_json(path).get("streams", [])}


def media_duration(path: Path) -> float | None:
    value = ffprobe_json(path).get("format", {}).get("duration")
    return float(value) if value is not None else None
```

Note the cached discovery (`lru_cache`) — the Program Files scan now happens at most once per process per tool.

**Verify**: `.\.venv\Scripts\python.exe -c "from helpers.media_tools import find_ffmpeg, find_ffprobe, ffprobe_json, stream_types, media_duration; print('ok')"` → `ok`

### Step 2: Switch the four call sites

1. `helpers/inventory.py` — delete its `find_ffprobe` definition; add `from helpers.media_tools import find_ffprobe`. Keep `ffprobe()` (the media-index flattener) but you may simplify its body to build on `ffprobe_json` as long as the returned dict is byte-identical in shape. Re-export for compatibility is NOT needed if you also update the importers in the same commit (next items).
2. `helpers/draft_silence_cut.py` — delete its `find_ffmpeg` definition; `from helpers.media_tools import find_ffmpeg`. This is the behavior upgrade: draft-silence-cut now gets the fallback discovery.
3. `helpers/render_preview.py` — delete its `find_ffmpeg` and `stream_types` definitions; import both from `helpers.media_tools`. Replace `from helpers.inventory import find_ffprobe` accordingly (it only needed it for `stream_types`).
4. `helpers/qa_preview.py` — delete its `ffprobe_json`, `stream_types`, `media_duration`; import from `helpers.media_tools`. It currently imports `find_ffmpeg, preview_path` from `render_preview` — keep importing `preview_path` from there, take `find_ffmpeg` from `media_tools`.

Search the whole repo for leftover references: `Select-String -Path helpers\*.py -Pattern "def find_ffmpeg|def find_ffprobe|def stream_types|def ffprobe_json|def media_duration"` must show only `helpers/media_tools.py` (and `inventory.py`'s `def ffprobe(` is fine).

**Verify**: `.\.venv\Scripts\python.exe -c "import helpers.inventory, helpers.draft_silence_cut, helpers.render_preview, helpers.qa_preview; from helpers.draft_silence_cut import find_ffmpeg as a; from helpers.render_preview import find_ffmpeg as b; assert a is b; print('ok')"` → `ok` (same function object — the inconsistency is gone).

### Step 3: Add tests

Create `tests/test_media_tools.py` (no real ffmpeg needed):

1. **PATH hit, no scan**: `monkeypatch.setattr(shutil, "which", lambda name: f"/fake/{name}")` → wait, patch the module's reference: `monkeypatch.setattr("helpers.media_tools.shutil.which", ...)`. Clear caches first (`find_ffmpeg.cache_clear()`); assert `find_ffmpeg() == "/fake/ffmpeg"`.
2. **Caching**: patch `which` with a counting wrapper; call `find_ffmpeg()` three times after `cache_clear()`; the counter is 1.
3. **Not found raises**: patch `which` to return `None` and patch `os.environ` lookups via `monkeypatch.delenv`/`setenv` so the candidate dirs don't exist; after `cache_clear()`, `find_ffmpeg()` raises `FileNotFoundError` mentioning "PATH".
4. **stream_types / media_duration parse**: monkeypatch `helpers.media_tools.ffprobe_json` to return a canned payload (`{"streams": [{"codec_type": "video"}, {"codec_type": "audio"}], "format": {"duration": "12.5"}}`) and assert `{"video","audio"}` / `12.5`. (Patch `ffprobe_json`, not `subprocess`, to keep the test trivial.)

Important: every test that touches the cached functions must call `cache_clear()` in setup AND teardown (use a fixture) so test order can't leak a cached fake path into other tests.

**Verify**: `.\.venv\Scripts\python.exe -m pytest tests/test_media_tools.py -q` → all pass.

### Step 4: Full suite and lint

**Verify**: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0. `.\.venv\Scripts\python.exe -m ruff check .` → exit 0 (the deleted duplicates must not leave unused imports behind).

## Test plan

See Step 3 — `tests/test_media_tools.py`, 4+ cases. Model structure on plan-001 test files. The cache-hygiene fixture (cache_clear before/after) is mandatory.

## Done criteria

ALL must hold:

- [ ] `.\.venv\Scripts\python.exe -m pytest -q` exits 0, including the new `tests/test_media_tools.py`
- [ ] `.\.venv\Scripts\python.exe -m ruff check .` exits 0
- [ ] `helpers.draft_silence_cut.find_ffmpeg is helpers.render_preview.find_ffmpeg` (Step 2 verify command passes)
- [ ] Exactly one definition each of `find_ffmpeg`, `find_ffprobe`, `stream_types`, `ffprobe_json`, `media_duration` exists under `helpers/`, all in `media_tools.py`
- [ ] `vtc --help` still lists all 13 commands (`.\.venv\Scripts\vtc.exe --help`)
- [ ] `git status` shows no modified files outside the in-scope list
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `helpers/render_preview.py` or `helpers/qa_preview.py` does NOT exist in your checkout. They were untracked (uncommitted) when this plan was written — if they're missing, the preview feature was never committed; report instead of recreating them.
- The "Current state" excerpts don't match the live code (drift — particularly likely for these two recently-added files).
- Changing `inventory.ffprobe()` to reuse `ffprobe_json` would alter the `media_index.json` dict shape in any way — keep the old body instead and report the constraint.
- Any rendering-behavior test or manual check suggests ffmpeg argument lists changed.

## Maintenance notes

- New ffmpeg-touching commands should import from `helpers.media_tools` — reviewers should reject new inline `shutil.which("ffmpeg")` calls.
- The `lru_cache` means a process won't notice ffmpeg being installed *mid-run*; that's fine for a CLI but would matter if the helpers ever become a long-lived server.
- Deferred: `qa_preview` still probes the preview file twice (`media_duration` in two places); a per-path memo on `ffprobe_json` was considered and skipped — file probing is cheap relative to discovery scans, and caching probe results by path risks staleness across renders in one process.
