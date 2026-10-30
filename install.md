# Install

## Recommended install

Choose the coding agents where you want this skill. The skill, the `vtc` CLI,
and the optional Resolve MCP are separate installations. Do not select every
detected agent unless you actually use it.

First check for an existing installation before replacing or consolidating it:

```bash
npx skills list -g
```

Review existing registrations and their locations. If the skill is already
available to a chosen agent, keep it rather than installing another copy. If
there are conflicting or older installations, inspect them before updating or
removing anything; do not automatically delete or overwrite them.

For a fresh installation, run this in an interactive terminal and select the
agents you use when prompted:

```bash
npx skills add ludmila-omlopes/video-timeline-copilot -g
```

The installer may automatically target the current agent when run inside an
agent session. To select exact targets, pass `-a` once per agent instead. For
example, for Codex and Claude Code:

```bash
npx skills add ludmila-omlopes/video-timeline-copilot -g -a codex -a claude-code
```

Choose the recommended shared/symlink installation when offered. Agents using
the shared directory may see the skill even if not explicitly selected; shared
storage avoids duplicate copies but is not an access-control mechanism. Use
the installer's agent-specific options if isolation is required. Do not run
both this method and the bundled installer for the same targets. Check the
result with `npx skills list -g`; report selected targets and actual paths.

Check `vtc --help` in each agent's execution environment. If it already works,
reuse it; otherwise install the CLI once for that environment:

```bash
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
vtc --help
```

Agents on the same machine can share `vtc` when it is on each one's PATH;
remote or isolated environments may need their own installation. Configure the
Resolve MCP separately only if the user wants it: see Optional Resolve MCP
below. Summarize the skill registrations, CLI availability, and MCP connection
status separately. Claude Code and Codex are agent clients; ordinary chat apps
may use different installation methods and may not have local command access.

For local unpublished testing, avoid running `npx skills add .` from a checkout
that contains `.venv`, `.pytest_cache`, or other ignored build/cache folders.
The `skills` CLI copies local directories as they exist on disk. Install from
GitHub after pushing, or use the bundled installer, to avoid copying local
environment files into the installed skill.

`skills.sh` does not run post-install hooks from skills. If the helper CLI is
not installed when the skill is first used, the skill tells the agent to ask
before running the bootstrap commands in the "Agent bootstrap" section below.
The skill also tells the agent to refresh PATH after installing `uv`/`vtc` and
verify `vtc --help` in the current shell before continuing. Manual FFmpeg/Python
fallbacks are reserved for cases where the user refuses to install `vtc` or `uv`
and still asks the agent to continue.

## Agent bootstrap

These are the commands the skill instructs an agent to run (after asking the
user for permission) when `vtc` is missing from `PATH` in a new environment.
They install `uv` if needed, install the helper CLI as an isolated tool, and
make `vtc` available in the current shell.

Windows PowerShell:

```powershell
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  winget install --id astral-sh.uv -e
}

$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = "$machinePath;$userPath"

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
  $uv = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter uv.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty FullName
}
if (-not $uv) {
  throw "uv is installed or requested, but uv.exe was not found. Reopen PowerShell or install uv from https://docs.astral.sh/uv/"
}

& $uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"

$toolDir = "$env:USERPROFILE\.local\bin"
if (Test-Path $toolDir) {
  $env:Path = "$toolDir;$env:Path"
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if ($userPath -notlike "*$toolDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$toolDir", "User")
  }
}

vtc --help
```

macOS/Linux:

```bash
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
export PATH="$HOME/.local/bin:$PATH"
vtc --help
```

If the agent should run helper commands without installing the tool
permanently, `uv tool run` is the approved alternative:

```bash
uv tool run --from "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main" vtc
```

## Bundled installer

This repo also ships a convenience installer:

```bash
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
video-timeline-copilot install --agent codex
```

This installer:

1. Registers the skill for the selected agent (`codex` above; use `claude` for
   Claude Code). Its default is `all`, so specify `--agent` to limit targets.
2. Checks for `ffmpeg` and `ffprobe`. The preceding `uv` command installs `vtc`.

The bundled Codex target registers both shared and legacy locations. Use the
recommended `skills` route when avoiding duplicate discovery is important, and
do not combine both installers for the same targets.

Update later with:

```bash
video-timeline-copilot update --agent codex
```

Run diagnostics with:

```bash
video-timeline-copilot doctor
```

## What gets installed

There are two setup steps:

1. Install the **agent skill** with `npx skills add`, the bundled installer, or
   by placing this repo under an agent skill directory.
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

Do not create a Python virtual environment inside the installed skill folder.
Install the helper CLI separately with `uv tool install`.

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

### Optional Resolve MCP

If the user wants the agent to work in Resolve and no compatible MCP is
connected, offer to set up [samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp).
It is optional and separate from the `vtc` CLI. Do not install it unless the
user wants it. First check the agent's available tools and existing MCP
configuration to avoid a duplicate installation. Identify the user's MCP
client, operating system, and Resolve edition/version from the environment
where possible; ask only for details that cannot be determined.

Follow the server's current [installation guide](https://github.com/samuelgursky/davinci-resolve-mcp/blob/main/docs/install.md)
for prerequisites and client-specific setup. Its documented quick start is:

```bash
npx davinci-resolve-mcp setup
```

Run the installer when the user requests setup and the environment permits it;
otherwise guide the user through running it. Select their actual MCP client,
preserve existing configuration, and follow installer prompts. The installer
may require Node.js, Python, and a local Resolve installation; use its current
documentation for platform-specific requirements. For Studio, open Resolve
and enable **Preferences > General > External scripting using > Local** as
documented upstream. For the free edition, consult the upstream in-app bridge
instructions and version limitations; do not assume every version supports it.

Reload or restart the MCP client if necessary, then check that the Resolve MCP
tools are discoverable and use a read-only connection or project-state check.
A check may launch Resolve. Follow any tool-provided remediation on failure;
report whether the server is installed, connected, and actually tested as
separate facts. If tool discovery requires a new session, explain that and
provide the next step. Do not claim success from installation alone.

If setup is declined, unavailable, or fails, continue with FCPXML delivery:

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
