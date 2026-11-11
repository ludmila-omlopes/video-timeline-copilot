# Cut Craft

Defaults for common requests, the user's cut rhythm, repeated takes, and where cuts may land.

## Defaults For Simple Requests

For simple requests, choose conservative defaults:

- "remove silence" / "remove silent parts": keep speech ranges based on word
  timestamp gaps, using the user's cut rhythm (see below) for how much air
  stays around speech. Prefer
  `vtc draft-silence-cut` for the first deterministic pass when the user wants
  mechanical silence removal; it removes transcript word gaps even when the
  audio is not technically silent. Then run `vtc refine-audio-cuts --replace`
  so cut boundaries are expanded by source audio activity, not only transcript
  word timestamps.
  Also collapse repeated takes: if the speaker restarts the same sentence or
  repeats the same point nearby, include only one version. Do not leave record
  gaps or half-second fragments; keep clips at least 0.8 seconds unless a
  longer configured minimum applies.
- "short edit" without a duration: create a 10-30 second rough cut depending on
  source length.

Cut rhythm: before drafting any edit that removes pauses from speech, know how
tight the user wants the cuts. Run `vtc preferences` first. If a `cut_style` is
saved, or the request already says how tight to cut, use it without asking.
Otherwise ask one short question in plain language, with an example:

| Option to offer | `cut_style` | Air kept around speech | Pauses removed from |
|---|---|---|---|
| Very tight, YouTube jump cuts | `tight` | ~0.05 s | 0.25 s |
| Tight with a short breath | `social` | ~0.12 s | 0.35 s |
| Natural | `documentary` | ~0.25 s | 0.7 s |
| Relaxed, long-form | `longform` | ~0.35 s | 0.9 s |

Save the answer with `vtc preferences --set cut_style=<style>` and tell the
user it will be the default next time and can be changed. Fine-tune with
`--set padding=<seconds>` or `--set min_silence=<seconds>` when the user wants
something between presets. If nobody answers, use `documentary` and say so.
When the user tightens or loosens many cuts by hand after delivery, offer to
switch the saved style (or padding) to match, so the next draft starts closer.
- "Shorts", "YouTube Short", or vertical short-form edit: default to a 9:16
  timeline, usually `resolution: [1080, 1920]`, unless the user explicitly asks
  for another format. Select one self-contained idea and shape it as hook,
  minimal context, payoff, and a deliberate ending. Treat roughly 60-90 seconds
  as an editorial sweet spot, not a hard limit. A YouTube Short may run up to
  180 seconds; do not shorten strong material artificially, and allow a cut to
  exceed 120 seconds when the complete idea remains engaging. Do not pad to a
  target duration or combine unrelated highlights just to fill the timeline.
- "highlight" / "best moments": prioritize clear, self-contained transcript
  phrases and avoid isolated filler words, false starts, and duplicate
  deliveries.
- "Shorts" from gameplay with a facecam overlay: treat facecam handling as
  part of the vertical Shorts framing. Use `preset: gameplay-facecam` for
  reaction/commentary beats and `preset: gameplay-screen` for gameplay beats,
  with the same known facecam rectangle, so the screen-focused scene excludes
  the facecam instead of showing it again.
- Talking head (one person speaking to a fixed camera) edited with jump cuts:
  add small punch-ins so consecutive clips never share the same framing. Do it
  by default unless the saved preference `punch_ins` is `false` or the user
  declines, and mention it at handoff (see step 7). When the destination is
  Resolve, also offer a light background blur (saved preference
  `background_blur`). It is a Resolve grade, not EDL data: apply it after
  import, following the `resolve-talking-head` guide.

Treat `takes_packed.md` notes such as `possible repeated take` and
`possible self-correction/restart` as warnings that the marked phrase probably
duplicates or corrects an earlier attempt. Do not place both versions on the
timeline unless the user's request explicitly asks to show the repetition.
Prefer the more complete, fluent, and contextually useful delivery; often that
is the later take after the speaker restarted. If the restart detector is too
strict or too loose for a transcript, rerun `vtc pack-transcripts` with
`--restart-overlap-words` or `--restart-max-gap`.

If an edit strategy could materially change the user's intended story, briefly
state the strategy before writing the EDL. For straightforward mechanical
requests like removing silence, proceed without asking for confirmation unless
there is ambiguity.

## Cut Craft Rules

By default, place cuts on complete word, phrase, sentence, beat, pause, or clear
visual transition boundaries. Avoid cutting through words, syllables, breaths,
and incomplete phrases unless the user explicitly asks for a deliberately
aggressive or stylized edit. Prefer the cleanest complete delivery when nearby
phrases repeat the same idea.

For tight social edits, remove more dead air but preserve audible word
starts/ends, keep record_start values contiguous, and avoid sub-minimum clips.
For documentary and long-form edits, preserve more natural pauses and avoid
rapid jump cuts unless the visual continuity is acceptable. For highlights,
favor self-contained phrases and avoid isolated filler words.

Always run `vtc validate-edl` before export. When transcript timings exist, the
validator warns if a source cut appears to land inside a spoken word or if the
timeline keeps only part of a transcript-backed sentence/segment. Validation
fails when a timeline has record gaps, record overlaps, or clips shorter than
the minimum duration. Final `vtc evaluate-edl` treats speech-boundary warnings
as blockers for handoff.

Before validation/export on speech edits, run `vtc refine-audio-cuts --replace`
on the EDL. The helper does not choose new dialogue content; it only expands
existing source_start/source_end boundaries outward when nearby source audio
indicates that the transcript timestamp would clip the audible word edge.

When transcript timestamps and source audio activity disagree, trust the audio.
A larger Whisper model is not automatically better for timing: on one
45-minute Portuguese recording, `medium` dropped words and stretched one word
over 5 seconds where `small` stayed aligned with the audio.

For speech edits, verify the content, not only the boundaries: run
`vtc qa-transcript` after every EDL change and read its readout. Whisper often
writes a phrase once when it hears it twice in a row, so retakes can be missing
from the source transcript and only show up when each range is transcribed on
its own. List ambiguous editorial removals for the user with approximate
timecodes.
