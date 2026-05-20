# End-to-End First-User Test

Use this checklist to test the project as if you are installing it for the first
time on a clean machine.

This checklist is currently written for Windows PowerShell. The CLI/FCPXML
workflow is expected to work on Linux/macOS too, but those platforms still need
their own validated setup checklist.

## 1. Create a Fresh Skill Install

From outside this repo:

```powershell
mkdir $env:USERPROFILE\.codex\skills -ErrorAction SilentlyContinue
```

Copy or clone the project into the Codex skills folder:

```powershell
git clone https://github.com/ludmila-omlopes/video-timeline-copilot.git $env:USERPROFILE\.codex\skills\video-timeline-copilot
cd $env:USERPROFILE\.codex\skills\video-timeline-copilot
```

For a local unpublished test, copy this repo folder into that destination
instead of cloning it.

## 2. Register Skill and Install CLI in a Clean Virtual Environment

For a true Codex skill simulation, the repo should be present under:

```text
~/.codex/skills/video-timeline-copilot
```

The virtual environment is only for the Python helper CLI and dependencies.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[transcribe]"
vtc --help
```

Expected: `vtc --help` lists commands including `transcribe`,
`pack-transcripts`, `export-srt`, and `export-fcpxml`.

## 3. Prepare Test Footage

Create this folder structure:

```text
test_video/
  raw/
    teste.mp4
```

Use a short real MP4 for `teste.mp4`. A 10-60 second talking-head clip is enough.

## 4. Run the CLI Workflow

```powershell
vtc inventory .\test_video --edit-dir .\test_video\edit
vtc transcribe .\test_video\raw\teste.mp4 --edit-dir .\test_video\edit
vtc pack-transcripts --edit-dir .\test_video\edit
```

Expected outputs:

```text
test_video/edit/media_index.json
test_video/edit/transcripts/teste.json
test_video/edit/takes_packed.md
```

## 5. Create a Minimal EDL

Create `test_video/edit/edl.json`:

```json
{
  "version": 1,
  "project_name": "Teste_Edit",
  "fps": 30,
  "archive_project": true,
  "timelines": [
    {
      "name": "Main Timeline",
      "resolution": [1920, 1080],
      "sources": {
        "A001": "raw/teste.mp4"
      },
      "ranges": [
        {
          "source": "A001",
          "source_start": 0,
          "source_end": 10,
          "record_start": 0,
          "track": 1,
          "beat": "INTRO",
          "quote": "",
          "reason": "First test cut"
        }
      ],
      "subtitles": {
        "mode": "srt",
        "path": "edit/subtitles/Main_Timeline.srt"
      },
      "markers": true
    }
  ]
}
```

Adjust `source_end` if the source video is shorter than 10 seconds.

## 6. Validate and Export Fallback Artifacts

```powershell
vtc validate-edl .\test_video\edit\edl.json
vtc export-srt .\test_video\edit\edl.json
vtc export-fcpxml .\test_video\edit\edl.json
```

Expected outputs:

```text
test_video/edit/subtitles/Main_Timeline.srt
test_video/edit/Teste_Edit.fcpxml
```

For DaVinci Resolve Free, import the FCPXML manually:

```text
File > Import > Timeline > Import AAF, EDL, XML...
```

## 7. Optional Resolve Studio Test

Only run this if DaVinci Resolve external scripting is available:

```powershell
vtc resolve-env-check
vtc build-resolve-project .\test_video\edit\edl.json
```

Expected outputs:

```text
test_video/edit/resolve/build_log.json
test_video/edit/resolve/Teste_Edit.drp
test_video/edit/resolve/Teste_Edit.dra
```

## 8. Codex Skill Usage Test

Start a new Codex session from a separate footage workspace, then ask:

```text
Use video-timeline-copilot on this folder and remove the silent parts from the
video.
```

Expected behavior:

- Codex reads `SKILL.md`.
- Codex infers the footage root and source video.
- Codex creates/uses `edit/`.
- Codex uses `vtc inventory`, `vtc transcribe`, and `vtc pack-transcripts`.
- Codex writes the internal `edit/edl.json` without requiring the user to know
  that file name.
- Codex validates the EDL and exports SRT and FCPXML.
- If Resolve scripting is unavailable, Codex stops before native project build
  and tells the user to import the FCPXML manually.

## Pass Criteria

The first-user test passes when:

- The repo is present under `~/.codex/skills/video-timeline-copilot`.
- Helper CLI installation succeeds in a fresh virtual environment.
- `vtc --help` works.
- Transcription produces a cached transcript.
- `takes_packed.md` is generated.
- EDL validation passes.
- SRT and FCPXML are generated.
- The FCPXML can be selected in Resolve's timeline import dialog.
