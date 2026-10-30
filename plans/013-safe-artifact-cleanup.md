# Plan 013: Add a dry-run-first cleanup command for regenerable edit artifacts

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 6779a48..HEAD -- helpers/cleanup.py helpers/cli.py tests/test_cleanup.py SKILL.md docs/architecture.md AGENTS.md`
> If any existing in-scope file changed since this plan was written, compare
> the "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: dx / tech-debt
- **Planned at**: commit `6779a48`, 2026-08-31

## Why this matters

One source can produce up to 26 analysis/cache files plus shared files before
the EDL and handoff artifacts are written, but `vtc` has no cleanup command.
Users currently have to delete paths manually, which makes it easy to remove
transcripts or media metadata still needed for re-editing. This plan adds an
explicit, dry-run-first command that deletes only named, regenerable artifact
profiles and never treats the whole `edit/` directory as disposable.

## Current state

- `helpers/cli.py` is the command router. Its complete command table has no
  cleanup entry:

```python
# helpers/cli.py:6-13
COMMANDS = {
    "inventory": ("helpers.inventory", "Index local video media"),
    "analyze-video": ("helpers.video_analysis", "Analyze visual video signals"),
    "transcribe": ("helpers.transcribe", "Transcribe one video with faster-whisper"),
    "pack-transcripts": ("helpers.pack_transcripts", "Pack transcript JSON files"),
    "draft-silence-cut": ("helpers.draft_silence_cut", "Create a draft EDL by removing detected silence"),
    "refine-audio-cuts": ("helpers.audio_refine", "Refine EDL cut boundaries using source audio"),
    "separate-audio": ("helpers.separate_audio", "Separate source audio into Demucs stems"),
```

- `helpers/common.py` provides the repository's path-containment primitive:

```python
# helpers/common.py:28-35
def ensure_within(path: Path, root: Path) -> Path:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path escapes workspace: {resolved_path}") from exc
    return resolved_path
```

- The two cleanup profiles in this plan are intentionally closed lists:
  - `analysis`: `video_analysis/`, `video_analysis.md`, `video_frames/`, and
    `takes_packed.md`.
  - `review`: `previews/`, `qa/preview_report.json`,
    `qa/contact_sheet.jpg`, and `qa/evaluation_report.json`.
- These paths must never be included in either profile: `media_index.json`,
  `transcripts/`, any `edl*.json`, `subtitles/`, `*.fcpxml`, `audio/`,
  `qa/audio_refine_report.json`, `qa/fcpxml_import_report.json`, or
  `resolve/`.
- Renderer clip segments are already correct: `helpers/render_preview.py` and
  `helpers/render_fcpxml_preview.py` create them under
  `tempfile.TemporaryDirectory`, so they are removed automatically.
- Repository conventions: one module per `vtc` subcommand, module-level
  `main()` using argparse, `from __future__ import annotations`, and plain
  pytest functions using `tmp_path`. Follow `helpers/inventory.py` for a
  compact command module and `tests/test_inventory.py` for filesystem tests.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Focused tests | `python -m pytest -q tests/test_cleanup.py` | all pass |
| Full tests | `python -m pytest -q` | all pass (190 before this plan) |
| Lint | `python -m ruff check .` | `All checks passed!` |
| Skill validation | `npx -y skills-ref validate .` | exit 0 |
| Skill listing | `npx -y skills add . --list` | exit 0 and lists the skill |

## Scope

**In scope** (the only files to create or modify):

- `helpers/cleanup.py` (create)
- `helpers/cli.py`
- `tests/test_cleanup.py` (create)
- `SKILL.md`
- `docs/architecture.md`
- `AGENTS.md`
- `plans/README.md` (status only)

**Out of scope**:

- Do not delete anything from a real footage workspace while developing or
  testing; tests use `tmp_path` only.
- Do not add transcript, media-index, EDL, subtitle, FCPXML, audio, Resolve,
  or non-preview QA cleanup.
- Do not add age-based deletion, recursive arbitrary-path arguments, globs
  supplied by the user, a background cleaner, or automatic cleanup after
  every command.
- Do not change renderer temporary-directory behavior.
- Do not implement the Demucs WAV policy from plan 014 or the video-analysis
  summary policy from plan 015 here.

## Git workflow

- Branch: `codex/013-safe-artifact-cleanup`
- Use short imperative commit subjects, for example `Add safe artifact cleanup`.
- Do not push or open a PR unless the operator instructed it.

## Steps

### Step 1: Implement a closed-list cleanup API

Create `helpers/cleanup.py`. Define a constant mapping named
`CLEANUP_PROFILES` with exactly the `analysis` and `review` relative paths
listed in "Current state". Implement:

```python
def cleanup_artifacts(edit_dir: Path, profiles: list[str], *, apply: bool = False) -> dict:
```

Required behavior:

1. Resolve `edit_dir`; fail with `FileNotFoundError` if it does not exist or
   with `NotADirectoryError` if it is not a directory.
2. Reject an empty profile list and unknown profile names with `ValueError`.
3. Build candidates only from `CLEANUP_PROFILES`; never accept a raw path or
   glob from callers.
4. Call `ensure_within(candidate, edit_dir)` for every candidate. Reject a
   candidate root that is a symlink instead of following it. Directory walks
   must not follow nested symlinks; remove a nested symlink itself, not its
   target.
5. Deduplicate candidates when profiles overlap. Count existing regular files
   and their byte sizes. Directories themselves do not increment `file_count`.
6. In dry-run mode (`apply=False`), return the report without changing disk.
7. In apply mode, unlink files/symlinks and recursively remove only the known
   profile directories. Missing candidates are a successful no-op.
8. Return a JSON-serializable dict containing `edit_dir`, sorted `profiles`,
   `apply`, `file_count`, `total_bytes`, and sorted relative `paths`.

Do not reuse the resolved path returned by `ensure_within` as the deletion
target when the original candidate is a symlink. Validate first, reject the
symlink, then delete the original literal child under the resolved edit root.

**Verify**: `python -m ruff check helpers/cleanup.py` -> exit 0.

### Step 2: Add the dry-run-first CLI

Give `helpers/cleanup.py` a module-level `main()` with:

- required `--edit-dir PATH`,
- repeatable required `--profile {analysis,review}`,
- `--apply` to perform deletion; without it the command is a dry run.

Print one summary line including mode, profile names, file count, and bytes.
For a dry run, print an explicit second line telling the operator to rerun with
`--apply`. Do not write a cleanup report file: the cleanup feature must not
create another persistent artifact.

Register it in `helpers/cli.py` as:

```python
"cleanup": ("helpers.cleanup", "Remove regenerable edit artifacts"),
```

Catch `FileNotFoundError`, `NotADirectoryError`, and `ValueError` in `main()`
and convert them to concise `SystemExit` messages, matching other helper CLIs.

**Verify**: `python -m helpers.cleanup --help` -> exit 0 and shows both
profiles plus `--apply`; `python -m helpers.cli --help` -> lists `cleanup`.

### Step 3: Pin deletion boundaries with tests

Create `tests/test_cleanup.py` with plain pytest functions. Build a temporary
`edit/` tree containing every path in both profiles, every explicitly preserved
path from "Current state", and an unrelated `notes.txt`.

Add at least these tests:

1. `test_cleanup_command_is_registered`.
2. `test_cleanup_dry_run_reports_without_deleting`.
3. `test_cleanup_analysis_profile_deletes_only_analysis_artifacts`.
4. `test_cleanup_review_profile_deletes_only_preview_review_artifacts`.
5. `test_cleanup_multiple_profiles_deduplicates_and_counts_bytes`.
6. `test_cleanup_preserves_deliverables_caches_audio_and_unknown_files`.
7. `test_cleanup_rejects_unknown_or_empty_profiles`.
8. `test_cleanup_rejects_missing_or_non_directory_edit_dir`.
9. `test_cleanup_rejects_profile_root_symlink` when symlink creation is
   supported; skip only that test on Windows when the OS denies symlink
   creation.
10. `test_cleanup_apply_is_idempotent` (second run reports zero files).

Avoid testing the CLI through a subprocess; call `cleanup_artifacts` directly
and inspect the filesystem. Monkeypatch only when testing printed CLI behavior.

**Verify**: `python -m pytest -q tests/test_cleanup.py` -> all tests pass.

### Step 4: Document lifecycle and user-consent rules

In `docs/architecture.md`, add an `## Artifact Lifecycle` section with a compact
table covering:

- temporary renderer segments: deleted automatically,
- analysis profile paths: keep through edit selection/revision, then removable,
- review profile paths: keep through final visual review, then removable,
- transcripts/media index/analysis JSON: useful caches, preserved by cleanup,
- EDL/export/audio/Resolve outputs: durable deliverables, preserved.

Document the two exact cleanup commands (dry run, then apply). In `SKILL.md`,
add a short rule near the session-flow handoff: never clean before evaluation
and agent review; only run `vtc cleanup ... --apply` when the user requested a
lean workspace or approved the dry-run result. In `AGENTS.md`, add the new
module to the repo map.

**Verify**: `npx -y skills-ref validate .` -> exit 0.

### Step 5: Run all gates

Run the full repository gates after the focused tests pass.

**Verify**:

- `python -m ruff check .` -> `All checks passed!`
- `python -m pytest -q` -> all pass
- `npx -y skills-ref validate .` -> exit 0
- `npx -y skills add . --list` -> exit 0

## Test plan

The ten tests in Step 3 cover dry-run safety, exact profile boundaries,
preservation of durable/cached files, idempotence, byte counts, invalid input,
and symlink escape behavior. Match the filesystem setup style in
`tests/test_inventory.py`; never operate outside `tmp_path` and never invoke
FFmpeg or other external tools.

## Done criteria

- [ ] `vtc cleanup --help` exposes only named profiles and `--apply`; there is
      no arbitrary path/glob deletion option.
- [ ] A dry run changes no files and reports count/bytes/relative paths.
- [ ] `analysis` and `review` apply runs delete exactly their documented paths.
- [ ] Tests prove media index, transcripts, EDLs, subtitles, FCPXML, audio,
      non-preview QA, Resolve outputs, and unknown files survive.
- [ ] `python -m pytest -q` and `python -m ruff check .` exit 0.
- [ ] Both skill validation commands exit 0.
- [ ] No files outside the in-scope list are modified.
- [ ] `plans/README.md` status row is updated.

## STOP conditions

- The implementation would need to accept user-provided deletion paths or
  delete the `edit/` root itself.
- A profile candidate can resolve outside `edit_dir`, or cross-platform tests
  show directory traversal follows symlink/junction targets.
- Any existing code consumes a profile path after final evaluation in a way
  not recorded in this plan; report the consumer before changing the profile.
- Satisfying a test requires deleting a cache or deliverable listed as
  preserved.
- Any in-scope current-state excerpt has drifted materially.

## Maintenance notes

- Every future generated artifact must be classified as temporary,
  regenerable analysis/review output, cache, or durable deliverable before it
  is added to a cleanup profile.
- Reviewers should treat changes to `CLEANUP_PROFILES` as destructive-behavior
  changes and require preservation tests.
- Transcript/media-index/privacy cleanup is deliberately deferred; it should
  require a separate explicit profile and user-facing warning if ever added.
