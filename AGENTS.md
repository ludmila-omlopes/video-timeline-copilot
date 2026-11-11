# What this repo is

`video-timeline-copilot` is an agent skill plus a Python helper CLI for turning local footage into editable timelines. `SKILL.md` is the product: instructions for agents using the tool to edit videos. `AGENTS.md` is for agents developing this repo, so keep contributor workflow here and end-user behavior in `SKILL.md`.

# Dev setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
```

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
```

The full test suite runs in under a second on a warm local checkout. FFmpeg, FFprobe, Whisper, and Demucs are not required for tests; subprocess and helper boundaries are monkeypatched.

# Repo map

- `helpers/audio_refine.py` - refines EDL cut boundaries using source audio activity.
- `helpers/backup.py` - backs up, lists, and restores the edit folder.
- `helpers/build_resolve_project.py` - builds a DaVinci Resolve project from a video-timeline-copilot EDL.
- `helpers/cli.py` - dispatches `vtc <command>` through the `COMMANDS` table.
- `helpers/common.py` - shared JSON, path-safety, safe filename, text folding, clock, frame, and SRT timestamp helpers.
- `helpers/contact_sheet.py` - builds time-stamped contact sheets of whole sources or ranges.
- `helpers/dialogue.py` - prints a source's dialogue as clean text or writes the full transcript.
- `helpers/draft_silence_cut.py` - creates deterministic draft EDLs by removing detected silence.
- `helpers/evaluate_edl.py` - evaluates an EDL before final handoff.
- `helpers/export_fcpxml.py` - exports FCPXML from a video-timeline-copilot EDL; see `docs/fcpxml.md` before changing generation/import semantics.
- `helpers/export_xml.py` - exports cuts-only FCP7 XML (xmeml) for Premiere and as a mixed-frame-rate fallback.
- `helpers/export_srt.py` - generates SRT subtitle files from an EDL and transcript cache.
- `helpers/find_phrase.py` - finds where a phrase is spoken across transcripts, with word-level times.
- `helpers/fix_transcript.py` - corrects misheard names in transcripts without moving word timing.
- `helpers/guide.py` - prints the agent guides bundled under `helpers/guides/`.
- `helpers/import_fcpxml.py` - imports an edited FCPXML back into a video-timeline-copilot EDL.
- `helpers/installer.py` - installs video-timeline-copilot for Claude and Codex.
- `helpers/inventory.py` - indexes local video and still-image media into `edit/media_index.json`.
- `helpers/media_tools.py` - locates FFmpeg/FFprobe and reads stream, duration, and dimension metadata.
- `helpers/pack_transcripts.py` - packs transcript JSON files into `takes_packed.md`.
- `helpers/preferences.py` - stores user editing preferences such as `cut_style`, `editor`, and notes in the tool home.
- `helpers/project_context.py` - stores per-project context, glossary, and notes in `edit/project.json`.
- `helpers/punch_ins.py` - adds alternating punch-in zoom transforms to talking-head ranges.
- `helpers/qa_preview.py` - runs automated QA checks for an EDL preview render.
- `helpers/qa_transcript.py` - re-transcribes the edited timeline per range and flags repeated takes left in the edit.
- `helpers/render_preview.py` - renders an MP4 preview from a video-timeline-copilot EDL.
- `helpers/resolve_env_check.py` - checks DaVinci Resolve scripting access.
- `helpers/status.py` - reports which sources are analyzed and writes `edit/library.md`.
- `helpers/separate_audio.py` - separates source audio into Demucs stems.
- `helpers/timing.py` - converts EDL source durations, timeline durations, speeds, and record times.
- `helpers/transcribe.py` - transcribes one or all indexed videos with faster-whisper, primed by the project glossary.
- `helpers/transforms.py` - resolves transform, focus rectangle, gameplay crop, and visual layer geometry.
- `helpers/update_fcpxml.py` - updates an existing FCPXML file in place from an EDL.
- `helpers/update_resolve_timeline.py` - creates or replaces timelines in an existing DaVinci Resolve project.
- `helpers/validate_edl.py` - validates video-timeline-copilot EDL JSON.
- `helpers/verify_media.py` - checks that indexed sources exist and are unchanged, and relinks moved files on request.
- `helpers/video_analysis.py` - analyzes source video context into `edit/video_analysis/*.json`.

`SKILL.md` is a short map. The agent-facing detail lives in `helpers/guides/*.md`, which are packaged with the CLI and printed by `vtc guide <name>`; edit behavior there, keep `SKILL.md` to principles and routing, and keep contributor knowledge in `docs/`. `tests/test_stills_mute_xml.py` fails if `SKILL.md` or a guide names a guide or `vtc` command that does not exist.

See `docs/architecture.md` for the data flow between inventory, transcript packing, EDL intent, validation, preview, QA, and editor backends. See `docs/fcpxml.md` before changing FCPXML generation/import; it documents the timing, anchoring, geometry, and resource rules the exporters must uphold.

# Conventions

- Use one module per `vtc` subcommand, with a module-level `main()` using argparse. Register new commands in the `COMMANDS` dict in `helpers/cli.py`.
- Put `from __future__ import annotations` at the top of every module.
- Tests are plain pytest functions using `tmp_path` and `monkeypatch`. Never invoke real FFmpeg, FFprobe, Whisper, or Demucs in tests; monkeypatch the subprocess or helper boundary. `tests/test_draft_silence_cut.py` is the exemplar.
- Put all per-session outputs under the footage folder's `edit/` directory. Never commit generated media, transcripts, or `edit/` outputs.
- Resolve EDL paths with `resolve_relative` plus `ensure_within` from `helpers/common.py`; follow the source validation pattern in `helpers/validate_edl.py`.

# CI

CI runs on `ubuntu-latest`, `windows-latest`, and `macos-latest` with Python `3.10` and `3.12`. Local changes should pass the same five command gates before pushing:

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -q
npx -y skills-ref validate .
npx -y skills add . --list
```

# Plans workflow

`plans/` holds advisor-written implementation plans. Executors should follow a plan's own instructions, honor its STOP conditions, run its verification commands, and update the corresponding status row in `plans/README.md`.
