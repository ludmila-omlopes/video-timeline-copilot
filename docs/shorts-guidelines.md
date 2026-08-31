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
   facecam, action, source-baked text, or visual payoff matters, analyze the
   video and inspect the relevant sampled frames before choosing the moment.
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
  duration that communicates the idea cleanly. Use roughly 60-90 seconds as the
  preferred range when it fits naturally, not as a compulsory target. Do not
  pad or remove context, development, or payoff to hit an arbitrary length.
- Produce editable artifacts first: EDL, SRT, and FCPXML. For an actual Shorts
  edit, always render a preview and run `vtc qa-preview` before handoff.

## Duration

- Treat 180 seconds as the maximum duration for a YouTube Short, unless the
  user names a different platform or delivery specification.
- Prefer approximately 60-90 seconds when the complete idea works at that
  length. This is an editorial sweet spot, not a technical limit or quota.
- Keep a 90-120 second cut when it needs that time. Allow it to exceed 120
  seconds, up to 180 seconds, when the hook, progression, and payoff remain
  strong and every retained beat contributes.
- Never accelerate speech excessively, remove necessary reasoning, cut the
  payoff, or fragment one coherent idea merely to force the edit below 60 or
  90 seconds. Likewise, never pad weak material to reach those durations.
- When reporting or recommending duration, make clear that Shorts can be up to
  three minutes and explain longer choices editorially rather than treating
  anything over one minute as invalid.

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

### Source-Baked Text And Title Cards

- Treat titles, lists, quotations, charts, labels, diagrams, subtitles, and any
  other meaningful text already visible in the source as critical content.
- Split the timeline range when the text appears and again when it disappears,
  so its framing does not force the entire Short into a distant crop.
- Prefer a tight crop around the complete text-bearing region when every word
  remains readable. Otherwise fit the full horizontal composition inside the
  vertical canvas and accept intentional black bars above and below it.
- Never crop through a word, remove a list item, hide a diagram label, or leave
  only part of a title visible. Keep visible side margins around the text.
- With post-fill transforms, use a starting `zoom` near `0.316` to contain a
  16:9 source in a 9:16 canvas. For other aspect ratios, start with
  `(output_width / output_height) / (source_width / source_height)`, then adjust
  from the rendered preview rather than trusting the calculation alone.
- Keep generated captions outside the source text region. Resume the normal
  face, gameplay, or action crop in a new range after the source text leaves.
- Preserve the original source as the timeline asset; do not create a flattened
  text-card clip merely to solve the framing unless the user explicitly asks.

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
- Every meaningful source-baked title, word, list item, and label is fully
  visible and readable. Inspect the beginning, middle, and end of each
  text-bearing range; intentional letterboxing is acceptable.
- Captions are generated, readable, and do not cover important content.
- Voice remains intelligible and B-roll supports rather than distracts from the
  point.
- `preview_report.json` has no duration, gap, overlap, transform, audio-only,
  video-only, or short-clip failures.
- Preview inspection and strict final evaluation pass before handoff.
