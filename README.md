# video-timeline-copilot

Create editable video timelines with Codex.

Drop footage in a folder, ask Codex for an edit, and get structured handoff
files back: `edl.json`, `.srt`, and `.fcpxml`. If DaVinci Resolve Studio
external scripting is available, it can also build a native Resolve project.

The primary output is an editable timeline, not a flattened MP4.

## What It Does

- Inventories local video files into `edit/media_index.json`.
- Transcribes footage with `faster-whisper` and word timestamps.
- Packs transcripts into `edit/takes_packed.md`, the main reading surface for
  the agent.
- Lets Codex reason about the edit and write `edit/edl.json`.
- Validates the EDL before any editor-specific export.
- Exports `.srt` subtitles.
- Exports `.fcpxml` for manual import into Resolve Free, Final Cut Pro, or
  other tools that support FCPXML.
- Optionally builds `.drp` / `.dra` projects through the DaVinci Resolve
  scripting API when external scripting is available.

## Setup Prompt

Paste this into Codex:

```text
Set up https://github.com/ludmila-omlopes/video-timeline-copilot.git for me.
Read install.md first. Register the repo as a Codex skill under
~/.codex/skills/video-timeline-copilot, then set up the Python helper CLI in an
isolated virtual environment. Make sure ffmpeg/ffprobe are available. Then read
SKILL.md for daily usage. Do not transcribe anything yet; just tell me when the
skill is ready and what folder structure I should use for footage.
```

After setup, point Codex at a footage folder:

```text
Use video-timeline-copilot on this folder and remove the silent parts from the
video.
```

Other examples:

```text
Use video-timeline-copilot on this folder and create a 30 second highlight edit.
```

```text
Use video-timeline-copilot on this folder and make a rough cut from the best
spoken moments.
```

Codex should infer the source video, create/use `edit/`, inventory sources,
transcribe, pack the transcript, create the internal EDL, validate it, and export
the handoff files. All session outputs live in the footage folder's `edit/`
directory; the skill directory stays clean.

## Manual Install

There are two parts:

1. The **Codex skill** is installed by placing this repo under
   `~/.codex/skills/video-timeline-copilot`.
2. The **Python helper CLI** is installed into a Python environment so commands
   like `vtc transcribe` are available.

The virtual environment is for the helper CLI and dependencies, not for Codex
skill discovery.

```powershell
# 1. Clone the repo directly into the Codex skills folder
mkdir $env:USERPROFILE\.codex\skills -ErrorAction SilentlyContinue
git clone https://github.com/ludmila-omlopes/video-timeline-copilot.git `
  $env:USERPROFILE\.codex\skills\video-timeline-copilot
cd $env:USERPROFILE\.codex\skills\video-timeline-copilot

# 2. Create a virtual environment for the helper CLI
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[transcribe]"

# 3. Verify the CLI
vtc --help
```

Install FFmpeg separately and make sure `ffmpeg` and `ffprobe` are on `PATH`.

On macOS/Linux, the skill registration step is usually:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/ludmila-omlopes/video-timeline-copilot.git \
  ~/.codex/skills/video-timeline-copilot
cd ~/.codex/skills/video-timeline-copilot
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[transcribe]"
vtc --help
```

## Platform Compatibility

Current status:

- Windows: primary tested platform for the CLI workflow.
- Linux: expected to work for inventory, transcription, EDL validation, SRT, and
  FCPXML export, but not yet fully validated end to end.
- macOS: expected to work for the same CLI/FCPXML path, but not yet validated.
- DaVinci Resolve scripting: platform-specific and currently documented with
  Windows paths only.

The recommended cross-platform handoff is FCPXML:

```bash
vtc export-fcpxml /path/to/footage/edit/edl.json
```

Broader Linux/macOS testing and platform-specific Resolve setup docs are planned
for a later compatibility pass.

## Footage Folder

Use a separate workspace for each edit:

```text
my-video/
  raw/
    interview.mp4
  edit/
```

Generated files go under `edit/`:

```text
my-video/edit/
  media_index.json
  transcripts/
  takes_packed.md
  edl.json
  subtitles/
  My_Edit.fcpxml
  resolve/
```

## CLI Quickstart

```powershell
vtc inventory .\my-video --edit-dir .\my-video\edit
vtc transcribe .\my-video\raw\interview.mp4 --edit-dir .\my-video\edit
vtc pack-transcripts --edit-dir .\my-video\edit
vtc validate-edl .\my-video\edit\edl.json
vtc export-srt .\my-video\edit\edl.json
vtc export-fcpxml .\my-video\edit\edl.json
```

For Resolve Free, import the generated `.fcpxml` manually:

```text
File > Import > Timeline > Import AAF, EDL, XML...
```

## DaVinci Resolve

`vtc export-fcpxml` is the default fallback for users who cannot use Resolve
external scripting.

`vtc build-resolve-project` requires:

- DaVinci Resolve installed on the same machine.
- DaVinci Resolve Studio, or another edition/version that exposes external
  scripting.
- External scripting enabled in Resolve preferences.
- Resolve open when the command runs.
- Python able to import `DaVinciResolveScript`.

On Windows, typical environment variables look like:

```powershell
$env:RESOLVE_SCRIPT_API="C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
$env:RESOLVE_SCRIPT_LIB="C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
$env:PYTHONPATH="$env:PYTHONPATH;$env:RESOLVE_SCRIPT_API\Modules"
```

Then:

```powershell
vtc resolve-env-check
vtc build-resolve-project .\my-video\edit\edl.json
```

If `vtc resolve-env-check` reports `api_import_ok_resolve_not_connected` and
your Resolve preferences do not show external scripting options, use FCPXML
instead.

## Security and Privacy Notes

- Transcription runs locally with `faster-whisper`, but the model may be
  downloaded from Hugging Face the first time it is used.
- Source media, transcripts, EDLs, subtitles, and FCPXML files can contain
  private content. They are written under the footage folder's `edit/`
  directory.
- Only run the workflow on media files you trust. `vtc inventory` calls
  `ffprobe`, so keeping FFmpeg updated matters.
- Do not commit generated footage, transcripts, subtitles, or `edit/` outputs to
  a public repository.
- The EDL validator rejects source and subtitle paths that escape the footage
  workspace.

## How It Works

The model reasons about the edit. Deterministic helpers execute the workflow.

```text
local media
  -> media inventory
  -> faster-whisper transcript cache
  -> packed transcript for Codex
  -> agent-authored edl.json
  -> validation
  -> SRT / FCPXML / optional Resolve project
```

The EDL is the durable edit contract. It contains timeline names, source media,
source in/out times, record positions, resolution, subtitles, markers, and
optional transform metadata.

## Design Principles

1. Editable timelines are the primary output.
2. Transcript-first editing keeps the agent focused on meaningful cut points.
3. The LLM writes structured edit intent; helper scripts perform deterministic
   file generation.
4. Validate before exporting.
5. Keep all per-session outputs in the footage folder's `edit/` directory.
6. When Resolve scripting is unavailable, produce SRT and FCPXML instead of
   blocking the workflow.

See [SKILL.md](SKILL.md) for Codex usage rules, [install.md](install.md) for
setup details, [docs/architecture.md](docs/architecture.md) for internals, and
[docs/e2e-test.md](docs/e2e-test.md) for release validation.
