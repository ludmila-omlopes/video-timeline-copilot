# video-timeline-copilot

Create editable video timelines with Codex.

<img width="843" height="516" alt="image" src="https://github.com/user-attachments/assets/e7ab61ca-5c17-4325-b861-59f152a4e9a0" />

Drop footage in a folder, ask Codex for an edit, and get structured handoff
files back: `edl.json`, `.srt`, and `.fcpxml`. If DaVinci Resolve Studio
external scripting is available, it can also build a native Resolve project.

The primary output is an editable timeline, not a flattened MP4.

## What It Does

- Inventories local video files into `edit/media_index.json`.
- Transcribes footage with `faster-whisper` and word timestamps.
- Packs transcripts into `edit/takes_packed.md`, the main reading surface for
  the agent.
- Flags likely repeated takes in the packed transcript so Codex can keep the
  cleanest delivery instead of cutting in multiple versions of the same line.
- Creates deterministic draft silence-cut timelines with configurable thresholds
  and transcript-aware word-boundary snapping.
- Lets Codex reason about the edit and write `edit/edl.json`.
- Validates the EDL before any editor-specific export and warns about obvious
  cut-craft problems when transcript timings are available.
- Exports `.srt` subtitles.
- Exports `.fcpxml` for manual import into Resolve Free, Final Cut Pro, or
  other tools that support FCPXML.
- Renders optional MP4 previews directly from `edl.json` and writes automated
  QA reports with contact sheets before handoff.
- Evaluates validation, cut quality, preview QA, and agent-review criteria so
  weak outputs can be revised before final handoff.
- Optionally builds `.drp` / `.dra` projects through the DaVinci Resolve
  scripting API when external scripting is available.

## Setup

Install the agent skill with `skills.sh`:

```bash
npx skills add ludmila-omlopes/video-timeline-copilot -g -a codex
```

Then install the Python helper CLI with `uv`:

```bash
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
vtc --help
```

The `npx skills add` command installs the `SKILL.md` instructions. The `uv`
command installs the `vtc` helper CLI used for media inventory, transcription,
EDL validation, subtitles, FCPXML, previews, and Resolve handoff.

When testing from a local checkout, prefer installing from GitHub after pushing
or use the bundled installer. `npx skills add .` copies the local directory as
it exists on disk, including ignored folders such as `.venv` if they are present.

`skills.sh` does not run post-install hooks from skills. If the helper CLI is
not installed when the skill is first used, the skill tells the agent to ask
before running the install commands already documented in `SKILL.md`. The skill
also tells the agent to refresh PATH after installing `uv`/`vtc` and verify
`vtc --help` in the current shell before continuing. The agent should only use a
manual FFmpeg/Python fallback if the user refuses to install `vtc` or `uv` and
still asks it to continue.

If you prefer one command that installs the helper CLI and registers the skill
for Claude and Codex, use the bundled installer:

```bash
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
video-timeline-copilot install
```

Update later with:

```bash
npx skills update video-timeline-copilot
video-timeline-copilot update
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

Most users should use the `skills.sh` and `uv` setup above. Manual setup has two
parts:

1. The **agent skill** is installed by placing this repo under a Claude or
   Codex skills folder.
2. The **Python helper CLI** is installed into a Python environment so commands
   like `vtc transcribe` are available.

The recommended manual CLI install uses `uv` instead of a hand-managed virtual
environment:

```bash
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
vtc --help
```

Then either run `video-timeline-copilot install` or place/symlink this
repository into your agent skill folder.

```powershell
# 1. Clone the repo directly into the Codex skills folder
mkdir $env:USERPROFILE\.codex\skills -ErrorAction SilentlyContinue
git clone https://github.com/ludmila-omlopes/video-timeline-copilot.git `
  $env:USERPROFILE\.codex\skills\video-timeline-copilot
cd $env:USERPROFILE\.codex\skills\video-timeline-copilot

# 2. Verify the CLI installed by uv
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
  previews/
  qa/
  resolve/
```

## Examples

See [examples/](examples/) for small, media-free example workspaces that show
the expected `media_index.json`, transcript JSON, `takes_packed.md`, and
`edl.json` files for silence-removal and highlight-edit workflows.

## CLI Quickstart

```powershell
vtc inventory .\my-video --edit-dir .\my-video\edit
vtc transcribe .\my-video\raw\interview.mp4 --edit-dir .\my-video\edit
vtc pack-transcripts --edit-dir .\my-video\edit
vtc draft-silence-cut .\my-video\raw\interview.mp4 --edit-dir .\my-video\edit
vtc validate-edl .\my-video\edit\edl.json
vtc export-srt .\my-video\edit\edl.json
vtc export-fcpxml .\my-video\edit\edl.json
vtc render-preview .\my-video\edit\edl.json
vtc qa-preview .\my-video\edit\edl.json
vtc evaluate-edl .\my-video\edit\edl.json --require-preview
```

`vtc pack-transcripts` annotates nearby repeated deliveries as
`possible repeated take`. Those notes are meant for the editing pass: keep only
the cleanest complete version of a restarted sentence or repeated point unless
the repetition is intentionally part of the video.

`vtc draft-silence-cut` creates an editable rough cut by detecting silence with
FFmpeg, then using transcript word timestamps to split long no-speech gaps when
transcripts are available. It writes kept ranges into `edit/edl.json`. Defaults
are conservative:

```powershell
vtc draft-silence-cut .\my-video\raw\interview.mp4 --edit-dir .\my-video\edit --style documentary
```

Useful controls:

- `--noise -35dB`: silence threshold passed to FFmpeg `silencedetect`.
- `--min-silence 0.7`: minimum sustained silence before a gap is removed.
- `--padding 0.25`: pre/post-roll kept around detected activity.
- `--min-segment 0.8`: discard tiny kept fragments; the CLI enforces at least
  0.8 seconds.
- `--merge-gap 0.35`: merge nearby kept ranges.
- `--max-word-gap 0.8`: split transcript word gaps longer than this many seconds.
- `--style social|highlight|documentary|longform`: pacing preset.
- `--no-word-snap`: skip transcript word-boundary adjustment.

When `edit/transcripts/<source>.json` exists, the helper adjusts cut points to
word timings so draft silence cuts do not trim through spoken words, and it
removes long pauses even when the audio is not technically silent. See
[docs/audio-analysis.md](docs/audio-analysis.md) for detector tradeoffs.
EDL validation reports kept transcript gaps longer than the configured
`max_word_gap`; self-evaluation treats those long gaps as blockers.

If the FCPXML has already been created and you want to keep updating that same
file instead of choosing new output names, run:

```powershell
vtc update-fcpxml .\my-video\edit\edl.json
```

For a custom XML path:

```powershell
vtc update-fcpxml .\my-video\edit\edl.json --xml .\my-video\edit\current.fcpxml
```

For Resolve Free, import the generated `.fcpxml` manually:

```text
File > Import > Timeline > Import AAF, EDL, XML...
```

## Preview and QA

`vtc render-preview` creates an MP4 proxy from the EDL without requiring
Resolve:

```powershell
vtc render-preview .\my-video\edit\edl.json
```

Default output:

```text
my-video/edit/previews/<project>_preview.mp4
```

The renderer cuts linked audio and video together from each EDL range. If the
timeline has record gaps, overlaps, or clips shorter than the minimum clip
duration, validation fails before preview rendering instead of creating
black/silent filler.

Run QA after rendering:

```powershell
vtc qa-preview .\my-video\edit\edl.json
```

Default outputs:

```text
my-video/edit/qa/preview_report.json
my-video/edit/qa/contact_sheet.jpg
```

The report includes expected versus actual duration, cut/source counts, record
gaps, record overlaps, short clips, transform zoom/position coverage, and
audio-only or video-only regions when a range or source stream appears to lack
linked audio/video. Use `--preview`, `--report`, `--contact-sheet`, or
`--timeline` to override the defaults.

## Self-Evaluation

Run `vtc evaluate-edl` after validation, export, preview rendering, and QA:

```powershell
vtc evaluate-edl .\my-video\edit\edl.json --require-preview --attempt 1 --max-attempts 3
```

Default output:

```text
my-video/edit/qa/evaluation_report.json
```

The evaluation report combines EDL validation, cut-quality warnings, preview QA,
and agent-review criteria for prompt alignment, pacing, and visual coherence. It
returns one of three statuses:

- `pass`: machine checks passed; finish the listed agent review before handoff.
- `needs_revision`: revise `edit/edl.json`, rerun exports/preview/QA, and call
  `evaluate-edl` again with the next `--attempt` value.
- `blocked`: the edit still fails after `--max-attempts`; stop and report the
  blockers instead of continuing to iterate.

Record gaps, overlaps, and clips shorter than the minimum duration are always
blockers. Use `--strict-cut-warnings` when softer cut-quality warnings, such as
cuts inside words, should also block delivery.

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

To keep working inside an existing Resolve project that is already open, update
that project instead of creating a new one:

```powershell
vtc update-resolve-timeline .\my-video\edit\edl.json --project "Existing Project"
```

By default this creates uniquely named timelines when a timeline with the same
name already exists. To intentionally replace matching timelines:

```powershell
vtc update-resolve-timeline .\my-video\edit\edl.json --project "Existing Project" --replace-existing
```

This rebuilds timelines from the EDL; it does not live-patch individual clips
inside the selected timeline. If the existing Resolve project frame rate differs
from the EDL fps, the command stops unless `--allow-fps-mismatch` is provided.

Updating an FCPXML file on disk does not make Resolve refresh a timeline that
was already imported from that XML. Resolve treats XML import as a timeline
snapshot, so reimport the updated XML or use `vtc update-resolve-timeline` when
Resolve scripting is available.

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
  -> SRT / FCPXML / preview QA
  -> self-evaluation loop
  -> optional Resolve project
```

The EDL is the durable edit contract. It contains timeline names, source media,
source in/out times, record positions, resolution, subtitles, markers, and
optional transform metadata.

## Design Principles

1. Editable timelines are the primary output.
2. Transcript-first editing keeps the agent focused on meaningful cut points.
3. The LLM writes structured edit intent; helper scripts perform deterministic
   file generation.
4. Silence removal is a draft timeline generator, not the final creative edit.
5. Validate before exporting.
6. Evaluate before handoff and revise weak outputs within a bounded loop.
7. Keep all per-session outputs in the footage folder's `edit/` directory.
8. When Resolve scripting is unavailable, produce SRT and FCPXML instead of
   blocking the workflow.

See [SKILL.md](SKILL.md) for Codex usage rules, [install.md](install.md) for
setup details, [docs/architecture.md](docs/architecture.md) for internals,
[docs/audio-analysis.md](docs/audio-analysis.md) for silence-cut behavior, and
[docs/e2e-test.md](docs/e2e-test.md) for release validation.

## Contact

Questions, feedback, or ideas for the project? Reach me on X/Twitter:
[@ludylops](https://x.com/ludylops)
