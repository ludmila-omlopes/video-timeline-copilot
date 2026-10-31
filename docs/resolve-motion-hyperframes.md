# Explainer Motion Overlays With HyperFrames

How to add motion graphics that explain what the speaker says (a list from a
study, a diagram of the eye, a scale of values) on top of an edited Resolve
timeline. Verified with HyperFrames 0.8.223 and DaVinci Resolve 21 Free
(Windows) in October 2026: 12 overlays on a 17-minute talking-head edit.

## 1. Find The Moments

Read the transcript of the delivered edit and mark passages where a picture
explains better than the face:

- lists and classifications (results of a study, rarity tiers, categories);
- a mechanism (how the eye focuses light, how a meter reacts);
- comparisons and numbers ("1 in 12 men", "red means up in China");
- recaps that tie back to a framework introduced earlier.

Skip opinions, jokes and asides, and don't overlay a passage that already has
B-roll unless the overlay adds the missing information (a rarity list over
gameplay of an inventory works; a title over a film scene does not).

Check every claim before animating it. Put the source on screen in small type
when the speaker cites a study, and mark values that only illustrate a trend as
"ilustrativo"/"illustrative" instead of inventing numbers.

## 2. Get Word-Level Timing On The Edited Timeline

Animate each element when its word is spoken. Map the source transcript words
onto record time through the exported FCPXML of the current timeline: for every
spine clip, a word at source time `s` inside the clip's audio range
`[start, start + duration)` lands at `offset + (s - start)`. Use that mapped
list, not a transcript of an earlier cut: a few seconds of drift accumulate
after each round of trims.

## 3. Build One HyperFrames Project Per Overlay

- `npx hyperframes init <dir> --non-interactive --skip-skills --example blank`,
  then load the `/hyperframes` skill (`npx hyperframes skills update hyperframes`)
  and read its `overlays.md` and `motion.md`.
- 1920x1080, root `data-fps="60000/1001"` (match the timeline), transparent
  `html`/`body`, one `.clip` wrapper that spans the whole duration, children
  animated with one paused GSAP timeline registered on `window.__timelines`.
- Write times as absolute timeline seconds and convert with
  `at = t => t - T0`, where `T0` is the overlay's record start. Elements enter
  about 0.1-0.2 s before their word.
- Side panels over a talking head: dark glass (`rgba(15,16,22,.88)`), left
  edge at about 72 px and no wider than about 540 px so the speaker stays clear
  at every punch-in level. Grow the panel with `clip-path: inset()` as rows
  appear, instead of showing an empty box.
- Full-screen diagrams (an opaque background that fades in and out) suit
  mechanisms that need the whole frame; keep them under about 20 s.
- Type at least 28 px for anything the viewer must read.
- `npx hyperframes check --json` for errors; ignore `film_silent` and
  `first_frame_empty` for overlays. Then `npx hyperframes snapshot --at ...`
  and composite the PNGs over a real frame of the speaker before rendering.

## 4. Render With Alpha

```bash
npx hyperframes render --format webm --quality delivery --fps 60000/1001 --output overlay.webm
```

VP9 WebM with alpha is small (a 10 s panel is about 0.3 MB) and Resolve 21 Free
reads its transparency. Also verified in Resolve 21: QuickTime Animation
(`qtrle`, `argb`) and PNG-in-MOV keep alpha. ProRes 4444 (`--format mov`) keeps
alpha too but is far larger, which matters when files must be copied to
another machine.

## 5. Place On V3

Duplicate the timeline, import the overlays into their own bin and place them
on a new track above the B-roll, with the same `AppendToTimeline` call as
`docs/resolve-broll.md` (`trackIndex=3`, `startFrame=0`,
`endFrame=frames`, `recordFrame=round(T0 * fps)`). Overlays sit above V2, so a
list can run over B-roll. Check one frame per overlay in the viewer.
