# Install

## Recommended install

Recommended:

```bash
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
video-timeline-copilot install
```

This installer:

1. Installs the `vtc` Python CLI directly from GitHub with `uv tool install`.
2. Registers the skill for Claude and Codex.
3. Checks for `ffmpeg` and `ffprobe`.

Update later with:

```bash
video-timeline-copilot update
```

Run diagnostics with:

```bash
video-timeline-copilot doctor
```

## What gets installed

There are two setup steps:

1. Install the **Codex skill** by placing this repo under
   an agent skill directory.
2. Install the **Python helper CLI** into a Python environment so commands like
   `vtc inventory` and `vtc transcribe` are available.

The installer handles skill registration. `uv tool install` handles the Python
CLI so users do not have to manage a virtual environment manually.

## Skill locations

The installer registers the same `SKILL.md` in the common personal skill
locations:

- Claude: `~/.claude/skills/video-timeline-copilot`
- Codex / Open Agent Skills: `~/.agents/skills/video-timeline-copilot`
- Codex legacy compatibility: `~/.codex/skills/video-timeline-copilot`

## Manual skill install

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

## Manual Python helper CLI

Recommended isolated install with uv:

```bash
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
```

After installation, the `vtc` command is available on `PATH`:

```bash
vtc --help
```

To reinstall from the latest GitHub `main`:

```bash
uv tool install --force "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
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
