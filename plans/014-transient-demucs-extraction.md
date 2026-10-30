# Plan 014: Delete the extracted PCM file after successful Demucs separation

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 6779a48..HEAD -- helpers/separate_audio.py tests/test_separate_audio.py SKILL.md plans/README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: perf / dx
- **Planned at**: commit `6779a48`, 2026-08-31

## Why this matters

`vtc separate-audio` decodes every source to 44.1 kHz, stereo, 16-bit PCM and
keeps that WAV after Demucs succeeds. That costs about 10 MiB per source minute
in addition to the retained stems, although no downstream helper consumes the
extracted WAV. The command should remove its private intermediate by default,
while preserving it on failures and offering an explicit debugging/reuse flag.

## Current state

- `helpers/separate_audio.py` creates or reuses the intermediate here:

```python
# helpers/separate_audio.py:44-70
def extracted_audio_path(source: Path, edit_dir: Path) -> Path:
    return edit_dir / "audio" / "extracted" / f"{safe_filename(source.stem, 'source')}.wav"


def extract_source_audio(source: Path, destination: Path, *, overwrite: bool = False) -> Path:
    if destination.exists() and not overwrite:
        return destination
    # ... ffmpeg writes pcm_s16le, stereo, 44100 Hz to destination ...
```

- After Demucs and stem validation, the file is only recorded in the manifest
  and return payload; it is not removed:

```python
# helpers/separate_audio.py:183-206
run_demucs(command, runner=runner)

track_dir = demucs_track_dir(resolved_out_root, model, audio)
stems = expected_stems(track_dir, mode, output_format)
missing = [path for path in stems.values() if not Path(path).exists()]
if missing:
    raise FileNotFoundError("Demucs did not create expected stem file(s): " + ", ".join(missing))

manifest_path = write_manifest(
    track_dir,
    source=source,
    extracted_audio=audio,
    # ...
)
return {
    "source": str(source),
    "extracted_audio": str(audio),
    "output_dir": str(track_dir),
    "manifest": str(manifest_path),
    "stems": stems,
}
```

- `tests/test_separate_audio.py::test_separate_audio_writes_manifest_with_stems`
  already fakes both extraction and Demucs using `tmp_path`; extend that style.
- No helper reads `vtc_stems.json` or its `extracted_audio` field. Documentation
  is the only other reference.
- Preserve the existing public keys, but use `null`/`None` when the intermediate
  was deleted and add an explicit retention boolean so manifests never point at
  a file that no longer exists.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Focused tests | `python -m pytest -q tests/test_separate_audio.py` | all pass |
| Full tests | `python -m pytest -q` | all pass |
| Lint | `python -m ruff check .` | `All checks passed!` |
| Skill validation | `npx -y skills-ref validate .` | exit 0 |

## Scope

**In scope**:

- `helpers/separate_audio.py`
- `tests/test_separate_audio.py`
- `SKILL.md`
- `plans/README.md` (status only)

**Out of scope**:

- Do not delete stems or `vtc_stems.json`.
- Do not change Demucs model/mode/format defaults or FFmpeg encoding settings.
- Do not add the extracted WAV to plan 013's cleanup profiles.
- Do not delete the extracted WAV when Demucs raises, expected stems are
  missing, or validation has not completed.
- Do not change arbitrary `--out-root` behavior or clean Demucs model caches.

## Git workflow

- Branch: `codex/014-transient-demucs-extraction`
- Use a short imperative commit subject such as `Remove completed Demucs extraction`.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add an explicit retention option to the Python API

Add `keep_extracted_audio: bool = False` to `separate_audio`. Keep extraction,
Demucs execution, and missing-stem validation in their current order. Only
after every expected stem exists:

1. If `keep_extracted_audio` is false, unlink the generated/cached `audio`
   path. If the now-empty `audio/extracted/` directory can be removed with
   `rmdir()`, remove it; ignore only the expected non-empty-directory error.
2. If unlinking fails, raise `RuntimeError` with the path and original error.
   Do not report the command as successful with an unexpectedly retained file.
3. If retention is true, leave the file untouched.

Change `write_manifest` to accept `extracted_audio: Path | None` and
`extracted_audio_retained: bool`. Its stable output shape must be:

```json
{
  "source": "...",
  "extracted_audio": null,
  "extracted_audio_retained": false,
  "model": "htdemucs",
  "mode": "vocals",
  "format": "wav",
  "stems": {},
  "command": []
}
```

When retention is requested, `extracted_audio` is the string path and the
boolean is true. Return the same two fields from `separate_audio` with identical
semantics. Keeping the existing key with `null` is preferred over removing it,
because callers parsing a stable manifest shape should not need a presence
check.

**Verify**: `python -m ruff check helpers/separate_audio.py` -> exit 0.

### Step 2: Expose `--keep-extracted-audio`

Add an argparse flag:

```python
parser.add_argument(
    "--keep-extracted-audio",
    action="store_true",
    help="Keep the intermediate PCM WAV after successful stem separation",
)
```

Pass it to `separate_audio`. After success, print whether the extracted WAV was
removed or retained, using the return payload rather than re-deriving the path.
Do not alter the existing `--overwrite` meaning: it still controls whether an
existing intermediate is re-extracted before Demucs.

**Verify**: `python -m helpers.separate_audio --help` -> includes
`--keep-extracted-audio` and the existing options.

### Step 3: Add lifecycle regression tests

Extend `tests/test_separate_audio.py` with at least these cases:

1. The existing successful default test now asserts the extracted WAV and its
   empty parent directory are gone, the stems/manifest remain, and both result
   and manifest contain `extracted_audio is None` plus
   `extracted_audio_retained is False`.
2. `keep_extracted_audio=True` retains the WAV and reports its path/true in both
   result and manifest.
3. A Demucs exception leaves the extracted WAV for retry/debugging and writes
   no success manifest.
4. Missing expected stems leave the extracted WAV and raise the existing
   `FileNotFoundError`.
5. A non-empty `audio/extracted/` directory keeps its other files while only
   the current source WAV is removed.
6. An `unlink()` failure is surfaced as `RuntimeError`; monkeypatch the Path
   boundary or a small extraction-cleanup helper instead of relying on file
   permissions.

Tests must not invoke real FFmpeg or Demucs.

**Verify**: `python -m pytest -q tests/test_separate_audio.py` -> all pass.

### Step 4: Update the agent-facing contract

In the `SKILL.md` audio-separation step, state that successful separation keeps
the stems and manifest but deletes the extracted PCM WAV by default. Document
`--keep-extracted-audio` for debugging or repeated Demucs runs. Make clear that
failures retain the intermediate for diagnosis.

Do not duplicate the full CLI reference here; plan 017 will consolidate the
human-facing README after this behavior lands.

**Verify**: `npx -y skills-ref validate .` -> exit 0.

### Step 5: Run all gates

**Verify**:

- `python -m ruff check .` -> `All checks passed!`
- `python -m pytest -q` -> all pass
- `npx -y skills-ref validate .` -> exit 0
- `npx -y skills add . --list` -> exit 0

## Test plan

Step 3 covers successful default cleanup, explicit retention, both pre-cleanup
failure paths, coexistence with other extracted sources, and filesystem cleanup
failure. Use the existing fake extraction/fake Demucs functions as the
structural pattern; all files stay under `tmp_path`.

## Done criteria

- [ ] A successful default separation leaves stems and manifest but no extracted WAV.
- [ ] `--keep-extracted-audio` preserves the WAV.
- [ ] Demucs or missing-stem failures preserve the WAV.
- [ ] Manifest and return payload never contain a stale extracted-audio path.
- [ ] Focused and full tests pass; ruff passes.
- [ ] Both skill validation commands pass.
- [ ] No files outside the in-scope list are modified.
- [ ] `plans/README.md` status row is updated.

## STOP conditions

- A live consumer of `vtc_stems.json` requires `extracted_audio` to remain a
  non-null path.
- Demucs still holds the WAV open after the subprocess returns on any supported
  platform, causing repeatable cleanup failures.
- Correct behavior would require deleting the intermediate before stem
  existence validation.
- Tests would need real FFmpeg/Demucs or changes outside scope.

## Maintenance notes

- The extracted WAV is an implementation detail, not a deliverable. Future
  separation backends should follow the same delete-on-success,
  preserve-on-failure rule.
- Reviewers should verify that every error path before successful stem
  validation retains the intermediate and that manifests never lie about file
  retention.
