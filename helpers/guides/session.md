# Session Flow

The command-by-command path from a footage folder to a checked, editable timeline, plus the self-evaluation gate.

Other guides hold the detail this one points to: `footage` (learning what is in
the material), `cuts` (choosing and planning the cut), `edl`, `cut-craft`,
`handoff`, and `shorts`. Print any of them with `vtc guide <name>`.

1. Inventory media, then check what is already analyzed:

   ```bash
   vtc inventory /path/to/footage --edit-dir /path/to/footage/edit
   vtc status --edit-dir /path/to/footage/edit
   ```

   Read saved answers before asking anything: `vtc preferences` and
   `vtc context --edit-dir /path/to/footage/edit`.

2. Transcribe sources with faster-whisper. Save the project's names and terms
   first (`vtc context --add-term`), because the glossary primes recognition:

   ```bash
   vtc transcribe --all --edit-dir /path/to/footage/edit
   ```

   Pass video paths instead of `--all` to transcribe specific sources. The
   model is loaded once for the whole run. After transcription, correct
   misheard names with `vtc fix-transcript` (the `footage` guide has the rules
   of evidence).

3. Analyze visual context when the edit depends on visible events, scene
   changes, action, on-screen text, objects, people, or framing. For Shorts,
   also do this before selecting clips whenever the crop, gameplay UI, facecam,
   or visual payoff affects which take is strongest:

   ```bash
   vtc analyze-video /path/to/footage/raw/interview.mp4 --edit-dir /path/to/footage/edit
   ```

   This creates `edit/video_analysis/<source>.json`, `edit/video_analysis.md`,
   and sampled frames under `edit/video_frames/`. The default helper uses local
   FFmpeg scene/freeze detection and sampled frames only. It does not run OCR,
   object detection, face recognition, or a hosted vision model, so there is no
   extra model cost.

   Signals are not understanding. Whenever clips are chosen by what is on
   screen, or the folder holds more than three sources, also build contact
   sheets and write a summary per source, following the `footage` guide:

   ```bash
   vtc contact-sheet --edit-dir /path/to/footage/edit
   ```

   Then look at each `edit/contact_sheets/<source>_full.jpg`, read
   `vtc dialogue <source>`, and write `edit/summaries/<source>.md`. Confirm
   with `vtc status --ready --edit-dir /path/to/footage/edit`. Summaries and
   contact-sheet paths are included in `takes_packed.md` and indexed in
   `edit/library.md`.

4. Pack transcripts and cached visual context:

   ```bash
   vtc pack-transcripts --edit-dir /path/to/footage/edit
   ```

5. Read `edit/library.md` first, then `edit/takes_packed.md`, any needed
   transcript JSON files, and the contact sheets or sampled frames referenced
   by the visual context. With many sources, follow the reading order in the
   `footage` guide instead of reading everything. Settle the kind of cut and,
   for a story-shaped cut, the plan (the `cuts` guide) before selecting clips.
   For a Short, shortlist candidate
   ideas and check each for a hook, enough context to stand alone, a payoff, a
   clean ending, and a usable vertical crop. Inspect title cards and every
   interval containing meaningful source-baked text; a crop is not usable if it
   removes any required word or character. If `takes_packed.md` says no cached
   video analysis exists, treat visual matching as limited and say so when
   framing or visual selection materially affects the result.

6. Write `edit/edl.json` from the user's requested outcome. Combine transcript
   timing with visual-analysis signals when selecting clips. For draft silence
   removal, use the deterministic helper:

   ```bash
   vtc draft-silence-cut /path/to/footage/raw/interview.mp4 --edit-dir /path/to/footage/edit
   ```

   Without `--style`, the helper uses the saved `cut_style` preference (and any
   saved `padding`/`min_silence`). Pass `--style` only to override it for this
   edit. Apply the same air and pause values when cuts are written by hand.

   Then inspect/refine the generated EDL when the request requires more than
   mechanical silence removal. For a Shorts edit, prefer a deliberate manual
   selection of one idea over using a silence-cut draft as the final story.
   Before continuing, verify that every source entry resolves to an original
   user-provided media file unless the user explicitly authorized a derived
   source.

7. Refine speech cut boundaries from the source audio:

   ```bash
   vtc refine-audio-cuts /path/to/footage/edit/edl.json --replace
   ```

   This expands cut starts/ends outward only when RMS activity is found close
   to the boundary. It is meant to catch transcript timestamps that end a word
   slightly before the audible phoneme finishes.

   For talking-head edits with jump cuts, add punch-ins after the cuts are
   final:

   ```bash
   vtc punch-ins /path/to/footage/edit/edl.json --focus 0.55,0.33
   ```

   `--focus` is the speaker's eye position, normalized from the top-left of
   the frame. Read it from a sampled frame (`edit/video_frames/`) instead of
   guessing; the zoom keeps that point in place. The helper cycles framing at
   every cut (wide 1.0 and medium 1.12 by default). Short questions and
   exclamations, or ranges marked `"emphasis": true`, get a closer 1.25. A
   range that continues the previous one without a cut keeps its zoom. Ranges
   with an existing transform or `visual_layers` are left alone unless
   `--overwrite` is passed, and vertical timelines are skipped (Shorts use
   their own framing). Keep punch-ins subtle: about 1.1-1.3, never so tight
   that the head or hands touch the frame edge. Check headroom on the close
   level in the preview or in Resolve.

   To apply the same plan to a timeline already open in Resolve (for example
   after the user adjusted cuts there), pass `--lua edit/punch_ins.lua` and run
   that line in the Resolve Console. It refuses to run when the clip count
   differs. Work on a duplicate of the user's timeline
   (`Timeline:DuplicateTimeline`), never on the original.

   If the user needs to rebalance baked-in voice and background music, split the
   source audio into Demucs stems:

   ```bash
   vtc separate-audio /path/to/footage/raw/interview.mp4 --edit-dir /path/to/footage/edit
   ```

   The default output is a two-stem vocal split under
   `edit/audio/demucs/htdemucs/<source>/` with `vocals.wav`, `no_vocals.wav`,
   and `vtc_stems.json`. Use `--mode 4-stem` for vocals, drums, bass, and
   other.

8. Validate:

   ```bash
   vtc validate-edl /path/to/footage/edit/edl.json
   ```

9. Generate subtitles:

   ```bash
   vtc export-srt /path/to/footage/edit/edl.json
   ```

10. Confirm the sources are present and unchanged, then export FCPXML:

   ```bash
   vtc verify-media --edit-dir /path/to/footage/edit --edl /path/to/footage/edit/edl.json
   vtc export-fcpxml /path/to/footage/edit/edl.json
   ```

   If `verify-media` reports a missing or changed source, stop and follow
   "Keeping The Work Safe" in the `footage` guide before exporting.

   When the destination is Premiere Pro, or `export-fcpxml` warns about mixed
   frame rates and the clips arrive offline in Resolve, export the cuts-only
   FCP7 XML instead (see the `handoff` guide for what it does not carry):

   ```bash
   vtc export-xml /path/to/footage/edit/edl.json
   ```

   If an FCPXML already exists and the user wants to keep updating the same XML
   file path, use:

   ```bash
   vtc update-fcpxml /path/to/footage/edit/edl.json
   ```

   Use `--xml /path/to/file.fcpxml` when the existing XML is not the default
   project-name path. This rewrites the XML file on disk; it does not live-sync
   an already-imported Resolve timeline.

   If the user manually edited a timeline in an FCPXML-compatible NLE and
   exported a fresh XML, sync those cuts back to a new EDL before continuing
   agent-led editing:

   ```bash
   vtc import-fcpxml /path/to/footage/edit/Adjusted.fcpxml --base-edl /path/to/footage/edit/edl.json
   ```

   The default output is `edit/edl.imported.json` with a reconciliation report
   at `edit/qa/fcpxml_import_report.json`. Use `--replace` only when the user
   explicitly wants to replace the base EDL; the helper validates a temporary
   import and writes an `edl.bak.json` backup before replacing.

   Before handoff, inspect the exported FCPXML asset resources. Confirm that
   every video and audio asset points to an original user-provided file and that
   separately recorded original audio remains a distinct editable source. Fail
   the handoff check if a helper-created proxy, synchronized clip, transcode,
   stem, preview, render, or flattened file appears as a source without the
   user's explicit authorization.

   For a Resolve handoff, do not treat original-media URLs alone as sufficient
   proof. Keep timeline component names tied to the original filenames and
   avoid per-range browser or source-clip names such as `P1_001`. When the
   original master clips already exist in the Media Pool, tell the user to
   disable **Automatically import source clips into media pool** in the XML
   import dialog and select the bin containing those masters. Also disable
   **Automatically set project settings** unless the user wants the project
   settings changed. After import,
   verify that Resolve conformed the timeline to the existing original clips
   and did not create one Media Pool item per edit. If it did, revise the XML
   component structure or use the Resolve scripting backend before handoff.

11. Render a preview and QA report for Shorts, and do so for any other edit when
    framing, captions, or technical timeline integrity is important:

   ```bash
   vtc render-preview /path/to/footage/edit/edl.json
   vtc qa-preview /path/to/footage/edit/edl.json
   ```

   Default outputs are:

   ```text
   edit/previews/<project>_preview.mp4
   edit/qa/preview_report.json
   edit/qa/contact_sheet.jpg
   ```

   Read `preview_report.json` before handoff. For Shorts, inspect the first
   seconds, every crop change, caption placement, every source-baked text card,
   the payoff, and the final frame, not only the automated checks. Check the
   beginning, middle, and end of each text-bearing range and fail visual QA if
   any meaningful word or character is clipped or unreadable. Intentional black
   bars are acceptable when they preserve the full composition and text. Treat
   duration mismatches, transform coverage failures, audio-only/video-only
   regions, record gaps, record overlaps, and short clips as issues to correct.
   When FCPXML geometry itself is under inspection, render the exported XML
   separately instead of relying only on the EDL preview:

   ```bash
   vtc render-fcpxml-preview /path/to/footage/edit/timeline.fcpxml --resolve-crop-x-factor 2
   ```

   Use this to compare the actual exported XML layout against the EDL preview
   when debugging Resolve crop/transform import behavior.

   For speech edits, check what the timeline actually says:

   ```bash
   vtc qa-transcript /path/to/footage/edit/edl.json
   ```

   It transcribes each range on its own and flags phrases that restart a
   recent phrase, which is how retakes left in the edit look. Read
   `edit/qa/transcript_readout.md` (one line per range, with record timecodes)
   end to end, not only the flagged lines: it also shows clipped words and
   fragments. Parallel rhetorical phrases can be flagged too; keep them by
   setting `"allow_repeat": true` on the later range.

12. Run self-evaluation before final handoff. For Shorts, require the preview
    and strict cut warnings. For speech edits, also require transcript QA:

   ```bash
   vtc evaluate-edl /path/to/footage/edit/edl.json --require-preview --strict-cut-warnings --require-transcript-qa --attempt 1 --max-attempts 3
   ```

   Default output:

   ```text
   edit/qa/evaluation_report.json
   ```

   If the report status is `needs_revision`, revise `edit/edl.json`, rerun
   validation, SRT/FCPXML export, preview rendering, QA, and evaluation with the
   next `--attempt` value. Stop after `--max-attempts`; if the status is still
   `blocked`, tell the user what failed instead of continuing to iterate.

13. For a user who wants to continue in Resolve, use the available integration.
    If a Resolve MCP is already connected, inspect its tool descriptions and
    connection/capabilities first. Confirm the intended project and timeline
    from the request and readback before changing anything. A connection check
    may launch Resolve; follow the MCP's own setup and error guidance. Do not
    require or silently install an MCP: if none is connected, offer it as an
    optional way to work in the open project, without blocking delivery. If the
    user wants it installed, follow the optional MCP setup in `install.md`;
    their request authorizes setup, subject to the environment's permissions.

    When the MCP supports checked FCPXML import, use it for the generated XML
    if importing into Resolve is requested. Prefer checked/dry-run operations,
    use original media, and avoid sanitization or relinking that silently
    removes or substitutes clips. When existing masters should be reused, select
    the appropriate Media Pool bin and disable automatic source import if the
    integration supports it; otherwise explain the manual import option. Read
    back the imported timeline, its tracks and media links, and report offline
    or mismatched items. Structural readback does not prove visual correctness:
    inspect actual Resolve output when possible, especially framing and layers,
    or state that visual verification is pending. If import or inspection is
    unsupported or fails, report the limitation and use the scripting backend
    where appropriate or provide manual import steps.

    When external scripting is available, the CLI can also build a Resolve
    project directly from the EDL:

   ```bash
   vtc resolve-env-check
   vtc build-resolve-project /path/to/footage/edit/edl.json
   ```

   If the user already has the Resolve project open and wants to keep working
   in that project, update the existing project instead:

   ```bash
   vtc update-resolve-timeline /path/to/footage/edit/edl.json --project "Existing Project"
   ```

   By default, this creates uniquely named replacement timelines and leaves old
   timelines intact. Use `--replace-existing` only when the user explicitly
   wants matching timeline names deleted and recreated. Do not also build or
   import a second timeline unless requested or needed to resolve a failure.

   After importing a timeline whose speech comes from separately recorded
   audio, link each video item to its audio before handoff. Without links,
   trimming the video does not trim the audio. When the external recording
   replaces the camera audio, also offer to remove the muted camera-audio
   track. Use the MCP, the scripting backend, or the in-app Console recipes in
   the `resolve-console` guide, then save the project.

## Self-Evaluation Loop

Use `vtc evaluate-edl` as the final gate before handoff. It checks:

- export validity through `vtc validate-edl` rules
- cut-craft warnings such as cuts inside spoken words or partial
  transcript-backed sentences/segments
- preview QA when `edit/qa/preview_report.json` exists
- duration, audio-only, and video-only preview failures
- transcript QA when `edit/qa/transcript_report.json` exists: repeats across
  cuts block, repeats inside one range warn, and a report older than the EDL
  is stale
- agent-review criteria for prompt alignment, pacing, and visual coherence

The helper writes a JSON report with `status`, `blockers`, `warnings`,
`revision_guidance`, and remaining attempts. Treat `status: pass` as permission
to proceed only after doing the listed agent review. Treat
`status: needs_revision` as instructions to revise the EDL and rerun the
workflow. Treat `status: blocked` as a hard stop: report the blockers and the
attempt count to the user.

Guardrails:

- Default maximum: 3 evaluation attempts.
- Do not render more than once per attempt unless a render command fails or the
  EDL changed.
- Do not use external paid or network video-analysis services unless the user
  explicitly asks for that path.
- Keep every report under `edit/qa/` so the user can inspect what was checked.

## After Delivery

- Hand over with the editorial notes described in the `cuts` guide and the
  import step for the user's editor from the `handoff` guide.
- Save anything durable the session taught about the user or the footage
  (`vtc preferences --add-note`, `vtc context --add-note`, `--add-term`).
- Back up the edit folder: `vtc backup --edit-dir /path/to/footage/edit --label <cut name>`.
