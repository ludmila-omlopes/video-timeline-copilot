# Plan 016: Remove temporary replacement EDLs after failed FCPXML imports

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 6779a48..HEAD -- helpers/import_fcpxml.py tests/test_import_fcpxml.py SKILL.md plans/README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug / dx
- **Planned at**: commit `6779a48`, 2026-08-31

## Why this matters

`import-fcpxml --replace` correctly validates a temporary EDL before replacing
the base, but a validation/import failure leaves `edl.imported.tmp.json` in the
workspace. That file is not a deliverable and may be invalid, yet its name looks
like a candidate the user should inspect or keep. The replacement path should
clean its private temporary file on every success, failure, and exception while
preserving the base EDL and existing backup semantics.

## Current state

```python
# helpers/import_fcpxml.py:375-383
base_edl_path = base_edl_path.resolve()
fcpxml_path = fcpxml_path.resolve()
destination = base_edl_path if replace else (out_path or default_out_path(base_edl_path)).resolve()
candidate_path = (
    base_edl_path.with_name(f"{base_edl_path.stem}.imported.tmp{base_edl_path.suffix}")
    if replace
    else destination
)
report_file = (report_path or default_report_path(base_edl_path)).resolve()
```

```python
# helpers/import_fcpxml.py:429-460
write_json(candidate_path, imported_edl)
validation_errors = validate(candidate_path)

status = "pass"
if validation_errors or errors:
    status = "failed"
elif warnings:
    status = "needs_attention"

backup_path = None
final_out = candidate_path
if replace and status != "failed":
    backup_path = base_edl_path.with_name(f"{base_edl_path.stem}.bak{base_edl_path.suffix}")
    shutil.copy2(base_edl_path, backup_path)
    shutil.move(str(candidate_path), str(base_edl_path))
    final_out = base_edl_path
# ... report uses "out": str(final_out) and is written afterward ...
```

- On failed replacement, `final_out` remains the temp path and the file is not
  removed. Non-replace imports intentionally write `edl.imported.json`; those
  outputs must remain even when the report status is failed.
- `tests/test_import_fcpxml.py` covers normal import, trims, retimes, reordering,
  and strict unknown-source failure, but it has no `replace=True` tests.
- Existing single-backup behavior (`edl.bak.json` overwritten by later
  successful replacements) is documented and explicitly out of scope.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Focused tests | `python -m pytest -q tests/test_import_fcpxml.py` | all pass |
| Full tests | `python -m pytest -q` | all pass |
| Lint | `python -m ruff check .` | `All checks passed!` |
| Skill validation | `npx -y skills-ref validate .` | exit 0 |

## Scope

**In scope**:

- `helpers/import_fcpxml.py`
- `tests/test_import_fcpxml.py`
- `SKILL.md`
- `plans/README.md` (status only)

**Out of scope**:

- Do not change FCPXML matching, trimming, retime, source-map, or warning rules.
- Do not change non-replace failed-import retention.
- Do not redesign or version backups.
- Do not suppress exceptions or delete the base EDL/report.
- Do not add temp candidates to the general cleanup command; the producing
  operation owns immediate cleanup.

## Git workflow

- Branch: `codex/016-clean-failed-import-candidate`
- Use a short imperative commit subject such as `Clean failed import candidates`.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Give replacement candidates exception-safe ownership

Refactor only the candidate write/validate/move portion of `import_fcpxml` so a
replacement candidate is removed in a `finally` block whenever it still
exists. Requirements:

1. The cleanup applies only when `replace=True`.
2. On successful replacement, `shutil.move` consumes the candidate, so the
   finally block is a no-op.
3. On a normal failed status, remove the candidate before returning the report.
4. If `validate`, backup copy, move, or report preparation raises, remove the
   candidate and re-raise the original exception.
5. If cleanup itself fails while another exception is active, preserve useful
   context using exception chaining; do not silently hide either failure.
6. Never unlink `base_edl_path`, `destination` for non-replace mode, or the
   backup.

For a failed replacement report, set `out` to `None` rather than a string path
that no longer exists. Add `temporary_candidate_removed: true` for failed
replacement reports and false otherwise. Preserve the existing report keys.
The CLI already prints `report['out']`; change that success line to print only
when `out` is non-null so failure output does not say `-> None`.

**Verify**: `python -m ruff check helpers/import_fcpxml.py` -> exit 0.

### Step 2: Add replace-mode regression tests

Extend `tests/test_import_fcpxml.py` using its `write_base_edl` and
`exported_xml` helpers. Add at least:

1. `test_import_fcpxml_replace_success_creates_backup_and_removes_candidate`:
   report passes, base contains imported data, `.bak.json` contains the original,
   and `.imported.tmp.json` does not exist.
2. `test_import_fcpxml_replace_failure_preserves_base_without_candidate`:
   make the XML contain an unknown source and call strict replacement; assert
   failed status, unchanged base bytes, no backup, no candidate, `out is None`,
   and `temporary_candidate_removed is True`.
3. `test_import_fcpxml_replace_cleans_candidate_when_validation_raises`:
   monkeypatch `helpers.import_fcpxml.validate` to raise; assert the exception is
   propagated, base is unchanged, and no candidate/backup remains.
4. `test_import_fcpxml_non_replace_failure_keeps_requested_output`: pin current
   behavior so the cleanup refactor cannot erase a user-requested diagnostic
   output.

**Verify**: `python -m pytest -q tests/test_import_fcpxml.py` -> all pass.

### Step 3: Clarify the agent-facing behavior

Update the short `SKILL.md` import paragraph: replacement mode validates a
private temporary candidate, discards it on failure, writes a backup and swaps
it into place on success. Do not add internal implementation detail beyond
those observable guarantees.

**Verify**: `npx -y skills-ref validate .` -> exit 0.

### Step 4: Run all gates

**Verify**:

- `python -m ruff check .` -> `All checks passed!`
- `python -m pytest -q` -> all pass
- `npx -y skills-ref validate .` -> exit 0
- `npx -y skills add . --list` -> exit 0

## Test plan

The four tests cover successful replacement, reported failure, unexpected
validation exception, and the deliberately different non-replace behavior.
All fixtures stay under `tmp_path`; no external editor or media tool runs.

## Done criteria

- [ ] No `.imported.tmp.json` remains after replace success, normal failure, or exception.
- [ ] Failed replacement leaves base bytes unchanged and creates no backup.
- [ ] Successful replacement still creates the documented backup and updates the base.
- [ ] Non-replace failed imports keep their requested output.
- [ ] Failed replacement reports do not claim a nonexistent `out` path.
- [ ] Focused/full tests, ruff, and both skill gates pass.
- [ ] No files outside the in-scope list are modified.
- [ ] `plans/README.md` status row is updated.

## STOP conditions

- A caller requires failed replacement reports to expose the temporary file as
  a durable diagnostic artifact.
- Safe cleanup would require deleting or renaming the base EDL before validation.
- The refactor changes matching/import semantics or non-replace behavior.
- Cleanup failures cannot be tested without platform-specific destructive setup.

## Maintenance notes

- Private temporary files should be owned and cleaned by the operation that
  creates them, not by a later workspace cleanup pass.
- Reviewers should scrutinize `finally` scope: it must cover every point after
  candidate creation and must be gated by `replace`.
