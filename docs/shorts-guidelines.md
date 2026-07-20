# Shorts Editing Guidelines

Use these guidelines when the user asks for Shorts, YouTube Shorts, vertical
short-form edits, or social clips intended to stand alone.

The goal is a complete, stand-alone piece: one idea, a strong opening hook, a
useful payoff, and an intentional ending. Optimize for clarity and retention;
do not confuse fast pacing with cutting every pause or changing shots without a
reason.

## Decision Procedure

Before writing the EDL:

1. Identify the requested format and duration. Default to 9:16 and
   `resolution: [1080, 1920]`, but preserve an explicitly requested format or
   duration.
2. Read the packed transcript and visual context. When the crop, gameplay UI,
   facecam, action, or visual payoff matters, analyze the video and inspect the
   relevant sampled frames before choosing the moment.
3. Shortlist complete candidate ideas. Rank them by hook strength, standalone
   clarity, payoff or emotional change, visual support, and clean audio
   boundaries.
4. Select one coherent idea unless the user explicitly asks for a montage. A
   shorter complete idea is better than a longer edit padded with weak material.
5. Build the EDL around hook -> minimal context -> payoff -> ending, then
   validate the speech boundaries and the vertical framing in a rendered
   preview.

## Defaults

- Use a vertical 9:16 timeline by default, usually `resolution: [1080, 1920]`.
- Treat the resolution as a delivery default, not a replacement for inspecting
  the source crop.
- Respect any duration the user provides. If no duration is provided, choose the
  shortest cut that communicates the idea cleanly. Do not pad or remove the
  payoff to hit an arbitrary length.
- Produce editable artifacts first: EDL, SRT, and FCPXML. For an actual Shorts
  edit, always render a preview and run `vtc qa-preview` before handoff.

## Story Shape

- Start on the strongest hook: a clear claim, question, contradiction, reveal,
  reaction, visual action, or payoff setup.
- Keep only the context needed to understand the hook. Remove greetings, channel
  intros, repeated setup, and outro material unless they are necessary or
  explicitly requested.
- Keep the cut self-contained. A viewer should understand the point without
  seeing the original source.
- End after the idea lands: on a reaction, result, or concise closing line. Do
  not end on a clipped word, unresolved setup, empty tail, or accidental source
  transition.
- Avoid unrelated montage beats unless the user explicitly requests a montage.
- Prefer the cleanest complete delivery when the speaker restarts a thought.

## Pacing And Speech

- Remove dead air, filler, false starts, duplicate retakes, and repeated points,
  but preserve complete words, emotional breaths, and the pause before a
  punchline or reveal.
- Keep complete, self-contained phrases. Do not trade intelligibility for speed.
- Change shot, crop, or B-roll only when it adds information, emphasis, or a
  motivated cover for a jump cut. Fast pacing is not arbitrary cutting.
- Run `vtc refine-audio-cuts --replace` before validation/export on speech
  edits so transcript timing errors do not clip audible word edges.
- Use `vtc evaluate-edl --require-preview --strict-cut-warnings` before final
  handoff. If evaluation requests revision, update the EDL and rerun exports,
  preview, QA, and evaluation.

## Vertical Framing

- Choose an intentional crop per range for horizontal footage; do not rely on
  accidental center crop when the subject is off-center.
- Keep faces, mouths, hands, important UI, action, and captions inside the safe
  vertical frame.
- If a subject moves out of frame, split the range and apply a new transform or
  use `visual_layers`; do not assume a static crop tracks the subject.
- Avoid putting captions over the face, hands, critical gameplay UI, or the lower
  interface area where publishing controls may appear.

## Gameplay With Facecam

For Shorts cut from gameplay with a facecam overlay, handle the facecam as part
of the vertical edit strategy:

- Use `gameplay-facecam` for reaction, commentary, or personality beats where
  the facecam is the subject.
- Use `gameplay-screen` for gameplay/screen beats. This crops to the largest
  remaining screen region and avoids showing the facecam again.
- Use `visual_layers` when the facecam and screen should be visible at the same
  time in a split vertical layout. Keep one timing/audio range and define a
  facecam layer plus a screen layer with `source_rect` and `dest_rect`.
- Use the same measured facecam rectangle for both presets so the screen crop
  excludes exactly the overlay area.
- Do not use a generic center crop when it leaves the facecam visible in a
  screen-focused scene.
- Add optional `padding` around the facecam rectangle when the overlay has a
  border, shadow, or rounded frame that would otherwise remain visible.

## Captions

- Always export SRT for Shorts workflows.
- Prefer short caption chunks aligned to spoken phrases, usually no more than
  two readable lines at a time.
- Avoid long caption blocks that cover the subject or important UI.
- If burned-in captions are requested later, use the SRT as the source of truth
  rather than manually retyping captions.

## Audio And B-Roll

- Make the voice intelligible before adding music or effects. If voice and music
  are baked together and the balance is poor, use `vtc separate-audio` as an
  optional handoff step.
- Use B-roll only when it clarifies the point, provides evidence, adds meaningful
  visual rhythm, or hides a motivated jump cut.
- Keep B-roll tied to the sentence or action it supports. Do not cover the
  strongest line with generic filler.

## QA Checklist

- The opening contains the hook, not setup fluff.
- The short contains one coherent idea and has a clear ending beat.
- No words, sentence starts, or sentence endings are clipped.
- Vertical framing keeps the subject, action, and critical UI visible throughout.
- Captions are generated, readable, and do not cover important content.
- Voice remains intelligible and B-roll supports rather than distracts from the
  point.
- `preview_report.json` has no duration, gap, overlap, transform, audio-only,
  video-only, or short-clip failures.
- Preview inspection and strict final evaluation pass before handoff.
