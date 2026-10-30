# Plan 017: Make README concise and give each Markdown file one canonical purpose

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 6779a48..HEAD -- README.md install.md docs/cli.md docs/fcpxml.md docs/fcpxml-audio.md AGENTS.md SKILL.md docs/architecture.md plans/README.md`
> This plan deliberately runs after plans 013-016, which will change several
> documentation files. Read their landed behavior first and preserve it. Stop
> if any prerequisite is not DONE or its observable behavior differs from its
> plan.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: `plans/013-safe-artifact-cleanup.md`, `plans/014-transient-demucs-extraction.md`, `plans/015-optional-video-analysis-summary.md`, `plans/016-clean-failed-import-candidate.md`
- **Category**: docs / dx
- **Planned at**: commit `6779a48`, 2026-08-31

## Why this matters

The 604-line README currently acts as landing page, installer guide, CLI
reference, architecture overview, and Resolve troubleshooting guide. This has
already produced a direct contradiction: README tells macOS/Linux users to
create `.venv` inside the installed skill while `install.md` explicitly says
not to do that. This plan makes `install.md` canonical for setup, creates one
scoped CLI reference, keeps README as a concise product/quickstart page, and
removes small contributor-doc drift without deleting load-bearing guidance.

## Current state

- `README.md` is 604 lines / about 2,971 words. It duplicates installation at
  lines 42-162, CLI detail at 224-464, and Resolve setup at 465-519.
- The concrete contradiction is:

```markdown
<!-- README.md:150-161 -->
On macOS/Linux, the skill registration step is usually:
...
cd ~/.codex/skills/video-timeline-copilot
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[transcribe]"
```

```markdown
<!-- install.md:137-149 -->
## Manual skill install
...
Do not create a Python virtual environment inside the installed skill folder.
Install the helper CLI separately with `uv tool install`.
```

- `install.md` already contains recommended install, agent bootstrap, bundled
  installer, locations, manual registration, dependency/platform notes, and
  Resolve setup. It is the canonical installation document; do not create a
  second install document.
- `SKILL.md` is the product behavior contract for agents and is intentionally
  detailed. Do not move user-facing agent rules out merely to reduce its line
  count. Plans 013-016 add cleanup/output behavior that the CLI reference must
  reflect.
- `docs/fcpxml-audio.md` has no inbound links. Its 28 lines describe linked A/V
  `asset-clip` behavior, explicit component metadata, and gap safety; these are
  relevant to `docs/fcpxml.md` and should be merged there before deletion.
- `docs/fcpxml.md:149-151` references historical plan 011 instead of stating a
  standalone maintenance requirement.
- `AGENTS.md` manually lists helper modules but currently omits
  `render_fcpxml_preview.py` and `timecode.py`; after plan 013 it must also list
  `cleanup.py`.
- Historical plan files 006-016 are intentionally self-contained executor
  artifacts. Do not shorten or delete them as part of product-doc cleanup.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Docs references | `rg -n "docs/cli.md|install.md" README.md SKILL.md docs AGENTS.md` | canonical links are present |
| Full tests | `python -m pytest -q` | all pass |
| Lint | `python -m ruff check .` | `All checks passed!` |
| Skill validation | `npx -y skills-ref validate .` | exit 0 |
| Skill listing | `npx -y skills add . --list` | exit 0 |

## Scope

**In scope**:

- `README.md`
- `install.md` (only small link/wording corrections if needed; keep canonical content)
- `docs/cli.md` (create)
- `docs/fcpxml.md`
- `docs/fcpxml-audio.md` (delete after merging unique content)
- `AGENTS.md`
- `SKILL.md` and `docs/architecture.md` (link corrections only; preserve behavior)
- `plans/README.md` (status and dependency wording only)

**Out of scope**:

- No Python, test, packaging, workflow, or runtime behavior changes.
- Do not rewrite `docs/shorts-guidelines.md`, `docs/audio-analysis.md`, or
  `docs/e2e-test.md`; they are objective and scoped to their jobs.
- Do not remove warnings, security/privacy notes, behavioral caveats, or
  required verification steps—move them to the canonical reference if they are
  too detailed for README.
- Do not shorten individual plan files or `SKILL.md` for an arbitrary line target.

## Git workflow

- Branch: `codex/017-canonicalize-markdown`
- Use a short imperative commit subject such as `Consolidate project documentation`.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Create the canonical CLI reference

Create `docs/cli.md` in the same factual, plain-Markdown style as
`docs/architecture.md`. Move—not copy—the detailed operational material from
README into these sections:

1. `# CLI Reference` with a one-paragraph scope.
2. `## Standard Workflow` with the ordered inventory, transcription, optional
   video analysis, packing, EDL, validation, export, preview/QA, and evaluation
   commands.
3. `## Analysis and Drafting`: transcript device fallback, repeated-take
   annotations, `analyze-video --write-summary`, silence-cut controls, and
   audio refinement.
4. `## Audio Separation`: stem modes, default deletion of extracted PCM,
   `--keep-extracted-audio`, manifest/stem paths, and failure retention.
5. `## FCPXML Update and Import`: update/import behavior, replacement backup,
   and failed-candidate cleanup.
6. `## Preview, QA, and Evaluation`: outputs, revision loop, and bounded attempts.
7. `## Cleanup`: plan 013's exact dry-run/apply commands, profile contents,
   and preserved caches/deliverables.
8. `## Resolve`: environment check, project creation/update commands, and link
   to `install.md#davinci-resolve-setup` for setup.

Keep each fact in one section. Link to specialized docs instead of repeating
their explanations (`audio-analysis.md`, `shorts-guidelines.md`, `fcpxml.md`).

**Verify**: `rg -n '^## ' docs/cli.md` -> all eight sections appear;
`rg -n 'vtc (cleanup|separate-audio|analyze-video|import-fcpxml|evaluate-edl)' docs/cli.md`
-> each command appears.

### Step 2: Reduce README to landing page and quickstart

Refactor README to retain:

- product name, image, one-paragraph outcome, and editable-timeline principle,
- a concise capability list,
- the two recommended install commands exactly once, followed by links to
  `install.md` for all alternatives/troubleshooting,
- three user prompt examples,
- a short footage/output layout that distinguishes caches/intermediates from
  durable deliverables,
- one compact standard CLI sequence plus a link to `docs/cli.md`,
- security/privacy notes,
- a short architecture flow and design principles,
- links to specialized docs, development guide, and contact.

Remove the `## Manual Install` section, duplicated platform compatibility,
Windows Resolve environment variables, command-by-command tutorials, and deep
EDL/transform explanation from README after confirming each retained fact has a
canonical destination. `README.md` must not contain instructions to create a
virtual environment inside a skill folder.

Target no more than 450 lines and 2,200 words. This is a guardrail against
recreating the current multi-reference README, not permission to remove
load-bearing warnings.

**Verify**:

```powershell
@'
from pathlib import Path
p = Path("README.md")
text = p.read_text(encoding="utf-8")
assert len(text.splitlines()) <= 450
assert len(text.split()) <= 2200
assert "## Manual Install" not in text
assert "RESOLVE_SCRIPT_API" not in text
assert "python -m venv .venv" not in text
assert "docs/cli.md" in text and "install.md" in text
'@ | python -
```

Expected: exit 0 with no output.

### Step 3: Merge the orphaned FCPXML audio note

Add a concise `### Linked Audio and Video` subsection to `docs/fcpxml.md` near
the containment/resources discussion. Preserve the unique facts from
`docs/fcpxml-audio.md`:

- ordinary EDL A/V ranges use one `asset-clip`, not separate story elements,
- Resolve displays embedded audio on audio tracks normally,
- explicit asset/sequence/clip component metadata reduces importer inference,
- unexpected audio-only imports should be diagnosed through standalone audio,
  `srcEnable`, and timing,
- record gaps/overlaps/short clips are rejected before export.

Then delete `docs/fcpxml-audio.md`. Replace the plan-011 sentence at
`docs/fcpxml.md:149-151` with a standalone maintenance statement: automated
tests cover the model, but release validation should compare a real Resolve
import against `vtc render-preview` at the same timecode until the pending
manual verification is recorded as complete. Do not claim it has happened.

**Verify**: `Test-Path docs/fcpxml-audio.md` -> `False`;
`rg -n 'Linked Audio and Video|srcEnable|audioChannels' docs/fcpxml.md` -> matches;
`rg -n 'plan 011' docs/fcpxml.md` -> no matches.

### Step 4: Refresh contributor routing and cross-links

In `AGENTS.md`, make the repo map complete for every `helpers/*.py` except
`__init__.py`, including `cleanup.py`, `render_fcpxml_preview.py`, and
`timecode.py`. Keep one factual line per module; do not turn it into a second
architecture document. Add `docs/cli.md` to the sentence that routes readers to
canonical references.

In `SKILL.md` and `docs/architecture.md`, replace any README deep-reference
links with `docs/cli.md` where appropriate, without changing plan 013-016
behavior. In `install.md`, change only links or a sentence needed to route CLI
usage to `docs/cli.md`; preserve its installation commands and bootstrap detail.

Use this machine check for the repo map:

```powershell
@'
from pathlib import Path
text = Path("AGENTS.md").read_text(encoding="utf-8")
missing = [p.name for p in Path("helpers").glob("*.py") if p.name != "__init__.py" and p.name not in text]
assert not missing, missing
'@ | python -
```

Expected: exit 0 with no output.

### Step 5: Run link/text and repository gates

Check for the known stale/duplicate patterns, then run all CI gates.

**Verify**:

- `rg -n 'python -m venv .venv|RESOLVE_SCRIPT_API' README.md` -> no matches
- `rg -n 'fcpxml-audio.md|plan 011' README.md SKILL.md install.md docs AGENTS.md` -> no matches
- `python -m ruff check .` -> `All checks passed!`
- `python -m pytest -q` -> all pass
- `npx -y skills-ref validate .` -> exit 0
- `npx -y skills add . --list` -> exit 0

## Test plan

This is a documentation-only plan. Verification is structural rather than
unit-test-based: word/line bounds, absence of the contradictory install path,
complete helper-module routing, presence of every new CLI behavior, no links to
the deleted note, and both skill package gates. The unchanged Python suite must
also pass.

## Done criteria

- [ ] README is at most 450 lines/2,200 words and acts as landing page/quickstart.
- [ ] `install.md` is the sole detailed installation source and README contains no contradictory venv path.
- [ ] `docs/cli.md` is the sole detailed CLI reference and includes plans 013-016 behavior.
- [ ] Unique FCPXML audio guidance is in `docs/fcpxml.md`; the orphan file is deleted.
- [ ] `AGENTS.md` names every helper module except `__init__.py`.
- [ ] No document refers to historical plan 011 as current technical guidance.
- [ ] Full tests, ruff, and both skill gates pass.
- [ ] No files outside the in-scope list are modified.
- [ ] `plans/README.md` status row is updated.

## STOP conditions

- Any prerequisite plan is not DONE or its CLI/output behavior differs from
  what this plan says to document.
- Moving README content would leave a warning or supported command with no
  canonical home.
- `docs/fcpxml-audio.md` contains behavior contradicted by the live exporter;
  report the contradiction instead of copying stale claims.
- Skill validation requires restoring duplicated content rather than linking a
  packaged relative document.
- The line/word target can be met only by removing security, destructive-action,
  or workflow-gating guidance.

## Maintenance notes

- New installation detail belongs in `install.md`; new CLI syntax/output belongs
  in `docs/cli.md`; agent decision rules belong in `SKILL.md`; contributor
  architecture/invariants belong in `docs/`/`AGENTS.md`.
- README should link to those sources and explain outcomes, not mirror them.
- Reviewers should reject documentation PRs that update one duplicate while
  leaving a conflicting copy elsewhere.
