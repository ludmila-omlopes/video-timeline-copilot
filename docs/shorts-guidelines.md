# Shorts Editing Guidelines

Use these guidelines when the user asks for Shorts, YouTube Shorts, vertical
short-form edits, or social clips intended to stand alone.

## Defaults

- Use a vertical 9:16 timeline by default, usually `resolution: [1080, 1920]`.
- Keep the edit focused on one complete idea, not a collection of weak moments.
- Respect any duration the user provides. If no duration is provided, prefer a
  compact cut that lands the idea cleanly instead of padding the timeline.
- Produce editable artifacts first: EDL, SRT, and FCPXML. Render a preview when
  framing, captions, or pacing need QA.

## Story Shape

- Start on the strongest hook: a clear claim, question, contradiction, visual
  action, or payoff setup.
- Remove preamble unless it is required for the viewer to understand the hook.
- Keep the cut self-contained. A viewer should understand the point without
  seeing the original source.
- Avoid unrelated montage beats unless the user explicitly requests a montage.
- Prefer the cleanest complete delivery when the speaker restarts a thought.

## Pacing And Speech

- Remove dead air, filler, false starts, duplicate retakes, and repeated points.
- Keep complete words and self-contained phrases. Do not trade intelligibility
  for speed.
- Run `vtc refine-audio-cuts --replace` before validation/export on speech
  edits so transcript timing errors do not clip audible word edges.
- Use `vtc evaluate-edl --require-preview --strict-cut-warnings` before final
  handoff when a preview exists.

## Vertical Framing

- Choose an intentional crop per range for horizontal footage; do not rely on
  accidental center crop when the subject is off-center.
- Keep faces, mouths, hands, important UI, and action inside the safe vertical
  frame.
- Avoid cropping subtitles into the subject's face or over critical gameplay UI.

## Gameplay With Facecam

For Shorts cut from gameplay with a facecam overlay, handle the facecam as part
of the vertical edit strategy:

- Use `gameplay-facecam` for reaction, commentary, or personality beats where
  the facecam is the subject.
- Use `gameplay-screen` for gameplay/screen beats. This crops to the largest
  remaining screen region and avoids showing the facecam again.
- Use the same measured facecam rectangle for both presets so the screen crop
  excludes exactly the overlay area.
- Do not use a generic center crop when it leaves the facecam visible in a
  screen-focused scene.
- Add optional `padding` around the facecam rectangle when the overlay has a
  border, shadow, or rounded frame that would otherwise remain visible.

## Captions

- Always export SRT for Shorts workflows.
- Prefer short caption chunks aligned to spoken phrases.
- Avoid long caption blocks that cover the subject or important UI.
- If burned-in captions are requested later, use the SRT as the source of truth
  rather than manually retyping captions.

## B-Roll

- Use B-roll only when it clarifies the point, hides a jump cut, or provides
  necessary visual evidence.
- Avoid generic B-roll that competes with the spoken hook.
- Keep B-roll timing tied to the sentence it supports.

## QA Checklist

- The first seconds contain the hook, not setup fluff.
- The short contains one coherent idea and has a clear ending beat.
- No words, sentence starts, or sentence endings are clipped.
- Vertical framing keeps the subject/action visible throughout.
- Captions are generated and do not create obvious readability problems.
- Preview QA and final evaluation pass before handoff when preview was rendered.
