# Plan 007: Add AGENTS.md contributor docs so coding agents stop re-deriving the repo

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3716700..HEAD -- AGENTS.md CLAUDE.md README.md`
> If `AGENTS.md` or `CLAUDE.md` already exists, treat it as a STOP condition
> (someone did this work already).

## Status

- **Priority**: P1
- **Effort**: S-M
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `3716700`, 2026-07-01
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/39

## Why this matters

This repository is developed almost entirely by coding agents (branch history:
`codex/*` and `advisor/*` branches, PRs #23–#36). There is no AGENTS.md or
CLAUDE.md, and README has no "develop from source" section — every agent
session re-derives the module layout, conventions, and test commands from
scratch, and sometimes gets them wrong (e.g. missing that tests must never
invoke real ffmpeg). A concise AGENTS.md is the highest-leverage DX fix for
this repo's actual workflow.

**Important distinction the file must preserve**: `SKILL.md` is the *product*
— instructions for agents *using* the tool to edit videos. AGENTS.md is for
agents *developing this repo*. Do not mix the two or edit SKILL.md.

## Current state

- No `AGENTS.md`, `CLAUDE.md`, or CONTRIBUTING file exists at the repo root.
- `README.md` covers end-user install only (uv tool install, skills.sh); the
  dev loop (editable install + pytest) appears only implicitly in
  `.github/workflows/ci.yml`.
- CI (`.github/workflows/ci.yml`): matrix of ubuntu/windows/macos ×
  Python 3.10/3.12, steps: `python -m pip install -e ".[dev]"`,
  `python -m ruff check .`, `python -m pytest -q`,
  `npx -y skills-ref validate .`, `npx -y skills add . --list`.
- Test suite: 136 tests, ~0.7s, pure pytest functions with
  `tmp_path`/`monkeypatch`; **no test invokes real ffmpeg/ffprobe/whisper** —
  subprocess boundaries are always monkeypatched.
- Packaging: `pyproject.toml`, setuptools, `packages = ["helpers"]`, console
  scripts `vtc = helpers.cli:main` and
  `video-timeline-copilot = helpers.installer:main`. Optional extras:
  `transcribe` (faster-whisper), `demucs`, `dev` (pytest, ruff).
- Module convention: each `vtc` subcommand is one module in `helpers/` with a
  module-level `main()` using argparse; `helpers/cli.py` is a thin dispatch
  table (`COMMANDS` dict mapping command name → (module, description)).
- Session outputs always go to the footage folder's `edit/` directory; the
  repo/skill directory stays clean, and generated media/transcripts must
  never be committed.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests | `python -m pytest -q` | all pass |
| Lint | `python -m ruff check .` | `All checks passed!` |
| Skill validation | `npx -y skills-ref validate .` | exit 0 |

On this machine there is a ready venv: use `./.venv/Scripts/python.exe -m ...`
if bare `python -m pytest` reports "No module named pytest".

## Scope

**In scope** (the only files you should create/modify):
- `AGENTS.md` (create, repo root)
- `CLAUDE.md` (create, repo root — 2-line pointer to AGENTS.md)
- `README.md` — add one short "Development" section linking to AGENTS.md

**Out of scope** (do NOT touch):
- `SKILL.md` — the product spec for agents using the tool; changing it can
  alter end-user behavior of the skill.
- `docs/architecture.md` — plan 008 touches it; avoid merge conflicts.
- Any Python file.

## Git workflow

- Branch: `advisor/007-agents-md`
- Commit style: short imperative subject, e.g. `Add AGENTS.md contributor docs`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Write AGENTS.md

Create `AGENTS.md` at the repo root with exactly these sections (keep the
whole file under ~120 lines; terse and factual, no marketing):

1. **What this repo is** — 3 sentences: agent skill (SKILL.md) + Python helper
   CLI (`vtc`) that turns footage into editable timelines (EDL → SRT/FCPXML/
   Resolve). State the SKILL.md-vs-AGENTS.md distinction from "Why this
   matters" above.
2. **Dev setup** — fenced commands:
   `python -m venv .venv`, activate (both PowerShell and bash lines),
   `python -m pip install -e ".[dev]"`, `python -m pytest -q`,
   `python -m ruff check .`. Note: full suite runs in under a second, ffmpeg
   is NOT required to run tests.
3. **Repo map** — one line per `helpers/` module (all 24: audio_refine,
   build_resolve_project, cli, common, draft_silence_cut, evaluate_edl,
   export_fcpxml, export_srt, import_fcpxml, installer, inventory,
   media_tools, pack_transcripts, qa_preview, render_preview,
   resolve_env_check, separate_audio, timing, transcribe, transforms,
   update_fcpxml, update_resolve_timeline, validate_edl, video_analysis).
   Derive each line from the module's argparse description or docstring — do
   not guess. Point to `docs/architecture.md` for data flow.
4. **Conventions** — bullet list:
   - one module per `vtc` subcommand, module-level `main()` + argparse;
     register new commands in the `COMMANDS` dict in `helpers/cli.py`.
   - `from __future__ import annotations` at top of every module.
   - tests: plain pytest functions, `tmp_path`/`monkeypatch` only; NEVER
     invoke real ffmpeg/ffprobe/whisper/Demucs in tests — monkeypatch the
     subprocess or helper boundary (point at
     `tests/test_draft_silence_cut.py` as the exemplar).
   - all per-session outputs under the footage folder's `edit/` dir; never
     commit generated media, transcripts, or `edit/` outputs.
   - path safety: resolve EDL paths with `resolve_relative` +
     `ensure_within` from `helpers/common.py` (see
     `helpers/validate_edl.py:286-297` for the pattern).
5. **CI** — the exact five CI steps and the OS/Python matrix, so agents run
   the same gates locally before pushing.
6. **Plans workflow** — one paragraph: `plans/` holds advisor-written
   implementation plans; executors follow a plan's own instructions and
   update `plans/README.md`.

**Verify**: `python -m pytest -q` → still all pass (docs change; sanity gate). File exists and each helpers module name appears in it: `grep -c "^" AGENTS.md` → >0, and spot-check `grep -n "validate_edl" AGENTS.md` → ≥1 match.

### Step 2: Add CLAUDE.md pointer

Create `CLAUDE.md` containing only:

```markdown
# CLAUDE.md

Read [AGENTS.md](AGENTS.md) — it is the contributor guide for this repo. `SKILL.md` is the end-user product spec, not contributor docs.
```

**Verify**: `type CLAUDE.md` (or `cat CLAUDE.md`) shows the pointer.

### Step 3: Link from README

In `README.md`, after the "Manual Install" section, add a short section:

```markdown
## Development

Contributor and agent guidelines (dev setup, repo map, conventions, CI gates)
live in [AGENTS.md](AGENTS.md).
```

**Verify**: `npx -y skills-ref validate .` → exit 0 (the skill package still validates with the new root files). `python -m ruff check .` → clean.

## Test plan

No code changes; the gates are the existing suite plus skill validation:
`python -m pytest -q` all pass, `npx -y skills-ref validate .` exit 0.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `AGENTS.md` exists with the 6 sections above; all 24 helpers module names appear in it
- [ ] `CLAUDE.md` exists and references AGENTS.md
- [ ] `README.md` contains a "## Development" section linking AGENTS.md
- [ ] `python -m pytest -q` exits 0; `python -m ruff check .` exits 0; `npx -y skills-ref validate .` exits 0
- [ ] `git status` shows only AGENTS.md, CLAUDE.md, README.md changed
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `AGENTS.md` or `CLAUDE.md` already exists.
- `npx -y skills-ref validate .` fails after adding the files — the skill
  packaging may be sensitive to root-level files; report the error instead of
  reshuffling files.
- A module's purpose cannot be determined from its argparse description or
  code — write "(purpose unclear — verify)" rather than inventing one.

## Maintenance notes

- When a new `vtc` subcommand module is added, its one-line entry in the
  AGENTS.md repo map must be added too — reviewers should check this on any
  PR that touches `helpers/cli.py`'s `COMMANDS` dict.
- If SKILL.md and AGENTS.md ever start overlapping (agent-usage rules leaking
  into contributor docs or vice versa), split along the rule: "uses the tool"
  → SKILL.md, "changes this repo" → AGENTS.md.
