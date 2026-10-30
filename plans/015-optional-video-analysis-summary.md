# Plan 015: Stop generating the redundant video-analysis Markdown summary by default

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 6779a48..HEAD -- helpers/video_analysis.py tests/test_video_analysis.py SKILL.md docs/architecture.md plans/README.md`
> Plan 013 may have changed `SKILL.md` and `docs/architecture.md`; reconcile
> those additive lifecycle edits. If Python excerpts below changed, stop and
> report rather than guessing.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `plans/013-safe-artifact-cleanup.md`
- **Category**: tech-debt / dx
- **Planned at**: commit `6779a48`, 2026-08-31

## Why this matters

Every `vtc analyze-video` run writes source JSON, sampled JPEGs, and a combined
`video_analysis.md`; `vtc pack-transcripts` then renders the same JSON into the
actual agent reading surface, `takes_packed.md`. Nothing in the workflow reads
the standalone Markdown summary. Making it opt-in removes a redundant file and
prevents a partial analysis run from overwriting that summary with an
incomplete source list, while retaining an escape hatch for humans who want it.

## Current state

- The summary writer is a pure renderer over the same JSON-shaped analyses:

```python
# helpers/video_analysis.py:283-291
def write_analysis_markdown(edit_dir: Path, analyses: list[dict]) -> Path:
    lines = ["# Video analysis", ""]
    for data in analyses:
        lines.append(f"## {data.get('source_name', 'source')}")
        lines.extend(analysis_to_lines(data, max_frames=12, max_events=24))
        lines.append("")
    out = edit_dir / "video_analysis.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
```

- `main()` always writes the summary after writing per-source JSON:

```python
# helpers/video_analysis.py:326-344
analyses = []
for video in videos:
    analysis = build_analysis(...)
    out = edit_dir / "video_analysis" / f"{safe_filename(video.stem)}.json"
    write_json(out, analysis)
    analyses.append(analysis)
    print(f"analyzed {video.name} -> {out}")

markdown = write_analysis_markdown(edit_dir, analyses)
print(f"video analysis summary -> {markdown}")
```

- `helpers/pack_transcripts.py::video_analysis_lines` reads only
  `edit/video_analysis/<stem>.json`; no Python code reads `video_analysis.md`.
- `SKILL.md:211-225` currently advertises all three output forms and then tells
  the agent to read `takes_packed.md`, transcript JSON, and sampled frames—not
  `video_analysis.md`.
- `tests/test_video_analysis.py` covers parsing and `analysis_to_lines`, but
  does not cover output orchestration or summary creation.
- Plan 013 classifies the legacy summary under the `analysis` cleanup profile.
  Keep that compatibility entry even after this plan; old workspaces can still
  contain the file and `--write-summary` can create it.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Focused tests | `python -m pytest -q tests/test_video_analysis.py` | all pass |
| Full tests | `python -m pytest -q` | all pass |
| Lint | `python -m ruff check .` | `All checks passed!` |
| Skill validation | `npx -y skills-ref validate .` | exit 0 |

## Scope

**In scope**:

- `helpers/video_analysis.py`
- `tests/test_video_analysis.py`
- `SKILL.md`
- `docs/architecture.md`
- `plans/README.md` (status only)

**Out of scope**:

- Do not reduce `--max-frames`, alter frame dimensions/sample cadence, combine
  frames into a contact sheet, or change scene/freeze detection.
- Do not remove per-source analysis JSON or sampled frames.
- Do not automatically delete other sources' JSON/frame directories during an
  incremental analysis run; plan 013 is the explicit cleanup boundary.
- Do not change `takes_packed.md` rendering or remove
  `write_analysis_markdown`; it remains the opt-in implementation.

## Git workflow

- Branch: `codex/015-optional-video-analysis-summary`
- Use a short imperative commit subject such as `Make video analysis summary optional`.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Extract testable output orchestration

Add a function near `write_analysis_markdown` with an explicit signature (the
name may vary, but use it from `main()`):

```python
def analyze_videos(
    videos: list[Path],
    edit_dir: Path,
    *,
    write_summary: bool = False,
    sample_interval: float,
    max_frames: int,
    frame_width: int,
    scene_threshold: float,
    freeze_noise_db: float,
    freeze_min_duration: float,
) -> dict:
```

It must call the existing `build_analysis`, write one JSON per source, and
return a report containing string `analysis_files` and nullable `summary`.
When `write_summary` is true, call the existing writer. When false, do not
create the summary; if a legacy `edit/video_analysis.md` exists, unlink that
known generated file so the workspace does not retain a stale/incomplete
summary. Do not touch any other file or source directory.

Keep printing in `main()`, not inside this helper, so tests can inspect return
values without capturing incidental output.

**Verify**: `python -m ruff check helpers/video_analysis.py` -> exit 0.

### Step 2: Add the opt-in CLI flag

Add:

```python
parser.add_argument(
    "--write-summary",
    action="store_true",
    help="Also write the redundant human-readable edit/video_analysis.md summary",
)
```

Call the new orchestration helper with `write_summary=args.write_summary`.
Print per-source JSON outputs as today. Print a summary path only when it was
created. Do not print a deletion message for a missing legacy file; if an
existing summary was removed, a concise message is acceptable.

**Verify**: `python -m helpers.video_analysis --help` -> includes
`--write-summary`; default remains false.

### Step 3: Add orchestration tests without FFmpeg

Extend `tests/test_video_analysis.py`. Monkeypatch
`helpers.video_analysis.build_analysis` to return a minimal analysis payload;
do not call real FFmpeg/FFprobe.

Add at least these tests:

1. Default orchestration writes one JSON per input and no
   `video_analysis.md`.
2. Default orchestration removes a pre-existing legacy summary but preserves
   unrelated files.
3. `write_summary=True` writes the combined Markdown and reports its path.
4. Two input videos produce two JSON paths and one optional combined summary.
5. The resulting JSON remains compatible with `analysis_to_lines` and contains
   sampled-frame references unchanged.

**Verify**: `python -m pytest -q tests/test_video_analysis.py` -> all pass.

### Step 4: Correct the documented default

Update `SKILL.md` and `docs/architecture.md` so the normal output list is:

- `edit/video_analysis/<source>.json`, and
- sampled JPEGs under `edit/video_frames/`.

State that `video_analysis.md` is an optional human-readable projection created
with `--write-summary`; the normal agent reading surface is
`takes_packed.md`. Preserve plan 013's lifecycle guidance and mention that its
analysis profile also handles summaries from older workspaces.

**Verify**: `npx -y skills-ref validate .` -> exit 0.

### Step 5: Run all gates

**Verify**:

- `python -m ruff check .` -> `All checks passed!`
- `python -m pytest -q` -> all pass
- `npx -y skills-ref validate .` -> exit 0
- `npx -y skills add . --list` -> exit 0

## Test plan

The five new tests pin default absence, legacy cleanup, opt-in generation,
multi-source behavior, and unchanged JSON/frame references. They monkeypatch
the expensive `build_analysis` boundary, matching the repository rule that
tests never run FFmpeg.

## Done criteria

- [ ] Default `analyze-video` writes JSON and frames but no standalone Markdown summary.
- [ ] `--write-summary` preserves the old summary capability.
- [ ] A stale legacy summary is removed without touching unrelated artifacts.
- [ ] `takes_packed.md`/JSON behavior is unchanged.
- [ ] Focused/full tests, ruff, and both skill gates pass.
- [ ] No files outside the in-scope list are modified.
- [ ] `plans/README.md` status row is updated.

## STOP conditions

- A live code or agent-flow consumer of `video_analysis.md` is found.
- Removing a legacy summary would also remove manually authored information
  that has no canonical home in per-source JSON observations.
- Testability would require invoking FFmpeg or changing analysis algorithms.
- Plan 013 changed the cleanup profile in a way that conflicts with preserving
  opt-in summaries.

## Maintenance notes

- `video_analysis.md` is a derived view; manual visual observations belong in
  each source JSON's `observations` array so repacking and optional summaries
  preserve them.
- A future single-contact-sheet design could reduce frame count further, but it
  needs a separate quality study because individual frame inspection is part of
  clip selection and vertical-framing review.
