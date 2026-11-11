# Knowing The Footage

How to learn what is in the footage before choosing clips: transcripts, contact sheets, written summaries, the project glossary, and the saved context that carries across sessions.

A cut is only as good as the agent's picture of the material. Transcripts say
what was said. They do not say what happened on screen, and for gameplay,
vlogs, B-roll, and reactions the picture is half the story. This guide builds
that picture once, caches it under `edit/`, and makes it cheap to reread.

## How Deep To Go

Scale the pass to the request.

- One or two talking-head files and a mechanical request (remove silence,
  captions, a re-export): inventory and transcripts are enough.
- Anything where clips are chosen (highlight, Short, scene, selects, rough cut,
  script edit), anything where the picture carries meaning (gameplay, screen
  recordings, B-roll, events), or more than three sources: do the full pass
  below before proposing a cut.

Do not offer a creative cut from a folder that `vtc status --ready` reports as
not ready. Finish the analysis first, or tell the user which sources are
missing and what that limits.

## The Full Pass

Every step is idempotent: it skips sources that already have the artifact, so
adding footage later and rerunning only processes what is new.

1. Index the folder and see where things stand.

   ```bash
   vtc inventory /path/to/footage --edit-dir /path/to/footage/edit
   vtc status --edit-dir /path/to/footage/edit
   ```

   Videos and still images (`.png`, `.jpg`, `.jpeg`) are both indexed. Read the
   warnings: two videos with the same file name would overwrite each other's
   transcript, so ask the user to rename one before going on.

2. Read what is already known, then fill the gaps before transcribing.

   ```bash
   vtc preferences
   vtc context --edit-dir /path/to/footage/edit
   ```

   Names are what speech recognition gets wrong: the game, characters, people,
   the channel, brands, places. Collect them from the request, the folder and
   file names, and any script the user supplied. If none are evident, ask one
   short question ("Any names I should spell right: the game, characters,
   people?"). Save them before transcription, because the glossary primes
   recognition:

   ```bash
   vtc context --edit-dir <edit> --set language=pt --add-term "Hollow Knight" --add-term "Hornet"
   ```

   `language` is a short code such as `pt` or `en`.

3. Transcribe everything in one run. The model loads once.

   ```bash
   vtc transcribe --all --edit-dir /path/to/footage/edit
   ```

   This is the slow step. For a large folder, offer to keep the computer awake
   (`caffeinate -i` on macOS; a keep-awake PowerShell loop on Windows), run it
   in the background when the environment allows, and report progress from the
   `transcript: N/M` lines. Do not start a second heavy job (another
   transcription, stem separation) alongside it.

4. Build contact sheets.

   ```bash
   vtc contact-sheet --edit-dir /path/to/footage/edit
   ```

   Each source gets `edit/contact_sheets/<name>_full.jpg`: one image with 16
   evenly spaced frames, each stamped with its source time. Sources longer than
   ten minutes also get one closer sheet per ten-minute window. A `.json` beside
   each sheet lists the exact time of every tile.

5. Optionally add motion signals when pacing depends on action:

   ```bash
   vtc analyze-video --edit-dir /path/to/footage/edit
   ```

   Scene changes and static ranges are useful for finding where gameplay
   happens and where nothing moves. They are signals, not understanding.

6. Write a summary for every source. This is the step that makes the footage
   legible, and it is the agent's job, not a helper's.

   For each video, look at its contact sheet image (and the per-window sheets
   for long sources) and read its dialogue:

   ```bash
   vtc dialogue <source> --edit-dir /path/to/footage/edit
   ```

   Then write `edit/summaries/<source name>.md` in exactly this shape:

   ```markdown
   # <file name>
   Duration: HH:MM:SS

   ## Overview
   Two or three specific sentences: what happens, in what order, and how it ends.

   ## Key Moments
   - [HH:MM:SS] What happens, in a few words. Use the times on the contact sheet.

   ## Visuals
   - Three to six bullets: location or game area, framing, facecam position,
     on-screen text or UI, anything that changes.

   ## Notable Lines
   > "Up to three quotes worth building around." Write `None` if nothing stands out.

   ## Cutaways
   Shots that could cover another clip's audio, or `None`.
   ```

   The `## Overview` and `## Visuals` headings are required; `vtc status` uses
   them to tell a finished summary from a stub.

   For a still image, open the image itself and write three or four sentences
   (subject, composition, any text on it) to
   `edit/summaries/<file name with extension>.md` using the same headings.

   Rules for summaries:

   - Describe only what the sheet shows and the dialogue says. Do not infer
     content from a file name, a camera brand, or what such videos usually
     contain.
   - Record where the facecam sits and what on-screen text appears. Shorts
     framing depends on both.
   - Never open the video file itself to "watch" it. Zoom with a contact sheet.

   With many sources, split the work when the environment has sub-agents: give
   each one a batch of about ten sources with, per source, the contact sheet
   path, the dialogue command, and the output path, and have it reply with one
   line per source. Sub-agents write summary files only. The main thread tracks
   progress with `vtc status --pending summary`. Without sub-agents, write the
   summaries in sequence.

7. Proofread the transcripts now that the footage is understood.

   ```bash
   vtc fix-transcript --edit-dir <edit> --glossary --dry-run
   vtc fix-transcript --edit-dir <edit> --replace "Holo Night => Hollow Knight"
   ```

   The helper matches whole spoken words, ignores case and accents, and never
   moves a timestamp: a correction with the same number of words keeps every
   word slot, and any other correction collapses the run into one word that
   spans the same start and end. The untouched transcript is kept once under
   `edit/transcripts/originals/`.

   Correct a word only with evidence:

   - the intended term is in the glossary, the project context, or the user's
     script, and the transcript has a close mishearing of it; or
   - the token is not a real word and only one real reading is phonetically
     close; or
   - the correct form appears elsewhere in the same transcript and the suspect
     token sounds like it.

   Never correct from general knowledge alone, never hand-edit transcript JSON,
   and leave a doubtful word as it is. Record each confirmed mishearing so the
   next transcription and the next fix both benefit:

   ```bash
   vtc context --edit-dir <edit> --add-term "Hollow Knight=Holo Night|Hollow Night"
   ```

8. Write down the big picture and what was learned about the user.

   ```bash
   vtc context --edit-dir <edit> --set footage_summary="Two sessions of ... recorded with facecam bottom-left; tone is ..."
   vtc context --edit-dir <edit> --add-note "Wants boss fights kept whole, not trimmed for pace"
   vtc preferences --add-note "Never open on a greeting; start on the first strong line"
   ```

   Project notes describe this footage. Preference notes describe the person and
   apply to every project. Save a note when the user states a standing rule or
   corrects the same thing twice. Do not save one-off instructions.

9. Confirm readiness, refresh the reading surfaces, and back up.

   ```bash
   vtc status --ready --edit-dir <edit>
   vtc pack-transcripts --edit-dir <edit>
   vtc backup --edit-dir <edit> --label analysis
   ```

   `vtc status` rewrites `edit/library.md` on every run.

## Reading Order While Cutting

Go from cheap to expensive, and stop as soon as the question is answered.

1. `edit/library.md`: every source with its overview, plus the project context,
   glossary, and notes. Read it whole.
2. `edit/summaries/<source>.md` for the sources that look relevant.
3. The contact sheet of a shortlisted source, to see it.
4. `vtc dialogue <source> --timestamps` to read what is said and roughly when.
5. `vtc find-phrase "words" --edit-dir <edit>` for exact word-level in and out
   times across every transcript. It tolerates mishearings; pass
   `--min-ratio 1` for exact wording only.
6. A zoomed contact sheet when a cut point depends on the picture.
7. The transcript JSON only for word timings that `find-phrase` did not give.

`edit/takes_packed.md` holds every phrase of every source with repeated-take
notes. With a handful of sources, read it whole. With many, pack only the
sources in play:

```bash
vtc pack-transcripts --edit-dir <edit> --sources clip_a.mp4 clip_b.mp4 --out <edit>/takes_scene1.md
```

## Zooming In

```bash
vtc contact-sheet /path/to/clip.mp4 --edit-dir <edit> --start 02:00 --end 02:30
```

Speech cuts do not need frame hunting: transcript word times place them and
`vtc refine-audio-cuts` protects the word edges. A cut that depends on the
picture alone (a hit landing, a reveal, a reaction with no words) has no such
safety net, so zoom until the tiles are under a second apart and cut on the
tile that shows the moment.

## Keeping The Work Safe

- Before any export, confirm the sources are where the index says and have not
  changed since they were analyzed:

  ```bash
  vtc verify-media --edit-dir <edit> --edl <edit>/edl.json
  ```

  `missing` means the file is gone or moved. If the report found the same file
  elsewhere, show the user the old and new locations and rerun with `--relink`
  only after they confirm. Never relink on your own. `changed` means the file
  was replaced or re-exported after analysis, so its transcript, sheets, and
  summary are stale: redo them with `--force` on the affected source.
- Back up after analysis and after each delivered cut with `vtc backup`. Backups
  go to the tool home, outside the footage folder, and skip files that can be
  rebuilt. `vtc backup --list` shows them; `vtc backup --restore <file>`
  extracts one into a new folder beside `edit/` and never overwrites the
  current work.

## Context That Carries Over

At the start of every session, read `vtc preferences` and, once the folder is
known, `vtc context`. Apply what they say without asking again: the saved
editor, language, cut rhythm, glossary, and notes are answers the user already
gave.
