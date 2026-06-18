# End-to-End First-User Test

Use this checklist to test the project as if you are installing it for the first
time on a clean machine.

This checklist is currently written for Windows PowerShell. The CLI/FCPXML
workflow is expected to work on Linux/macOS too, but those platforms still need
their own validated setup checklist.

## 1. Create a Fresh Skill Install

Install the skill through the same path a user would normally use:

```powershell
npx skills add ludmila-omlopes/video-timeline-copilot -g -a codex
```

For local unpublished testing, push the branch first and install from that
GitHub source when practical. If you use `npx skills add .`, first remove local
ignored folders such as `.venv`, because the `skills` CLI copies the local
directory exactly as it exists on disk.

Verify that only one copy is installed and that it does not contain `.venv`:

```powershell
Get-ChildItem -Recurse -Filter SKILL.md $env:USERPROFILE\.agents\skills\video-timeline-copilot
Test-Path $env:USERPROFILE\.agents\skills\video-timeline-copilot\.venv
```

Expected: exactly one `SKILL.md`, and `.venv` returns `False`.

## 2. Install the Helper CLI

Install the Python helper CLI separately from the skill:

```powershell
uv tool install --force "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
vtc --help
```

For testing an unpublished local checkout, use the local package path:

```powershell
uv tool install --force "D:\Codigos_Diversos\video-timeline-copilot[transcribe]"
vtc --help
```

Expected: `vtc --help` lists commands including `transcribe`,
`pack-transcripts`, `export-srt`, `export-fcpxml`, `render-preview`, and
`qa-preview`, and `evaluate-edl`.

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
vtc render-preview .\test_video\edit\edl.json
vtc qa-preview .\test_video\edit\edl.json
vtc evaluate-edl .\test_video\edit\edl.json --require-preview --attempt 1 --max-attempts 3
```

Expected outputs:

```text
test_video/edit/subtitles/Main_Timeline.srt
test_video/edit/Teste_Edit.fcpxml
test_video/edit/previews/Teste_Edit_preview.mp4
test_video/edit/qa/preview_report.json
test_video/edit/qa/contact_sheet.jpg
test_video/edit/qa/evaluation_report.json
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
- Codex evaluates the final EDL/preview output and revises failed outputs within
  the configured attempt limit.
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
- Preview QA and evaluation reports are generated.
- The FCPXML can be selected in Resolve's timeline import dialog.
