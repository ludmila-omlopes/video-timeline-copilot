# Install

There are two separate setup steps:

1. Install the **Codex skill** by placing this repo under
   `~/.codex/skills/video-timeline-copilot`.
2. Install the **Python helper CLI** into a Python environment so commands like
   `vtc inventory` and `vtc transcribe` are available.

The virtual environment is only for the helper CLI and dependencies. Codex skill
discovery comes from the `SKILL.md` file in the skills folder.

## Codex Skill Install

Windows PowerShell:

```powershell
mkdir $env:USERPROFILE\.codex\skills -ErrorAction SilentlyContinue
git clone https://github.com/ludmila-omlopes/video-timeline-copilot.git `
  $env:USERPROFILE\.codex\skills\video-timeline-copilot
cd $env:USERPROFILE\.codex\skills\video-timeline-copilot
```

macOS/Linux:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/ludmila-omlopes/video-timeline-copilot.git \
  ~/.codex/skills/video-timeline-copilot
cd ~/.codex/skills/video-timeline-copilot
```

## Python Helper CLI

Recommended isolated install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

On Windows PowerShell, activate with:

```powershell
.\.venv\Scripts\Activate.ps1
```

After installation, the `vtc` command is available on `PATH`:

```bash
vtc --help
vtc inventory --help
vtc transcribe --help
vtc pack-transcripts --help
vtc validate-edl --help
vtc export-srt --help
vtc export-fcpxml --help
vtc resolve-env-check --help
vtc build-resolve-project --help
```

## Dependencies

Python 3.10+ is required.

For transcription:

```bash
pip install -e ".[transcribe]"
```

For media inventory and audio extraction, install `ffmpeg` and ensure both
`ffmpeg` and `ffprobe` are on `PATH`.

Keep FFmpeg updated and run the workflow on media files you trust.

## Platform Compatibility

Windows is the primary tested platform today. Linux and macOS are expected to
work for the CLI/FCPXML workflow, but they have not yet been fully validated end
to end in this repo.

DaVinci Resolve scripting setup is platform-specific. The current Resolve
examples use Windows paths. Use `vtc export-fcpxml` as the portable fallback.

## DaVinci Resolve Setup

Free Resolve users should use the FCPXML fallback:

```bash
vtc export-fcpxml /path/to/footage/edit/edl.json
```

Then import the generated `.fcpxml` manually in Resolve.

The native Resolve builder requires a local Resolve install and external
scripting access. In current Resolve releases, that generally means DaVinci
Resolve Studio. On Windows, these environment variables are typically needed:

```powershell
$env:RESOLVE_SCRIPT_API="C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
$env:RESOLVE_SCRIPT_LIB="C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
$env:PYTHONPATH="$env:PYTHONPATH;$env:RESOLVE_SCRIPT_API\Modules"
```

Start Resolve before running:

```bash
vtc build-resolve-project /path/to/footage/edit/edl.json
```
