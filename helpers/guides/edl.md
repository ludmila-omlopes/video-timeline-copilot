# EDL Contract

The JSON the agent writes as edit intent: timelines, sources, ranges, transforms, layers, stills, mute, and retimes.

The EDL is JSON. It may contain one or more timelines. Each timeline contains
source media, cut ranges, optional transforms, optional subtitles, and optional
markers.

```json
{
  "version": 1,
  "project_name": "Generated_Edit",
  "fps": 30,
  "timelines": [
    {
      "name": "Short 01 - 9x16",
      "resolution": [1080, 1920],
      "sources": {
        "A001": "raw/interview.mp4"
      },
      "ranges": [
        {
          "source": "A001",
          "source_start": 12.42,
          "source_end": 18.9,
          "record_start": 0,
          "track": 1,
          "speed": 2.0,
          "beat": "HOOK",
          "quote": "This is the hook.",
          "reason": "Cleanest opening.",
          "transform": {
            "zoom": 1.35,
            "pan": 0,
            "tilt": -120
          }
        }
      ],
      "subtitles": {
        "mode": "srt",
        "path": "edit/subtitles/Short_01_9x16.srt"
      },
      "markers": true
    }
  ]
}
```

For a horizontal title card or text-heavy frame that would be clipped by the
default vertical fill, give that interval its own range and reduce `zoom` until
the complete text-bearing region fits with safe side margins. With the current
post-fill transform semantics, a 16:9 source placed in a 9:16 canvas usually
needs a starting `zoom` near `0.316` for a full-frame contain layout. Derive the
general starting value as `(output_width / output_height) / (source_width /
source_height)`, then verify it in the rendered preview and exported FCPXML.
Black bars are preferable to cropped words. Resume the normal face/gameplay
crop in a new range as soon as the text is gone.

`allow_repeat: true` marks a range whose opening intentionally repeats a recent
phrase (anaphora, parallel questions) so `vtc qa-transcript` does not flag it.

`speed` is an optional playback multiplier. Use `2.0` for 200% speed,
`0.5` for 50% speed, and omit it for normal speed. A retimed range keeps the
same `source_start`/`source_end` source span, but its timeline duration becomes
`(source_end - source_start) / speed`. `export-fcpxml` writes constant-speed
retimes as Resolve-compatible `timeMap` entries so the speed change remains
editable after import. FCPXML imports from Resolve may also include
`record_duration` to preserve Resolve's frame-rounded clip duration.

For gameplay recordings with a facecam overlay, transform presets can derive
safe zoom/pan/tilt values from a facecam rectangle:

```json
{
  "transform": {
    "preset": "gameplay-facecam",
    "facecam": {"x": 1600, "y": 720, "width": 320, "height": 360}
  }
}
```

Use `gameplay-facecam` when the scene should crop into the camera. Use
`gameplay-screen` with the same `facecam` rectangle when the scene should show
the gameplay/screen area while excluding the facecam. Rectangles can be pixel
coordinates or normalized values from `0.0` to `1.0`. Optional `padding`
expands the excluded/focused facecam rectangle before calculating the transform.

For Shorts that need the facecam and screen visible at the same time, keep a
single timing/audio range and add `visual_layers`. Each layer crops a source
region into a destination region on the vertical canvas. The preview renderer
composites the layered layout. FCPXML export promotes a same-source gameplay or
screen layer to the primary visible clip when possible, then writes the
remaining layers as connected video clips above it; this matches Resolve's own
export style for vertical gameplay/facecam timelines. When a layer's
`source_rect` and `dest_rect` aspect ratios differ, the crop is tightened
around its center to match the destination aspect in both preview and FCPXML
output:

```json
{
  "source": "A001",
  "source_start": 325.333,
  "source_end": 338.866,
  "record_start": 0,
  "visual_layers": [
    {
      "name": "Facecam",
      "source_rect": {"x": 0.0, "y": 0.43, "width": 0.24, "height": 0.36},
      "dest_rect": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.45}
    },
    {
      "name": "Screen",
      "source_rect": {"x": 0.13, "y": 0.12, "width": 0.67, "height": 0.67},
      "dest_rect": {"x": 0.0, "y": 0.50, "width": 1.0, "height": 0.45}
    }
  ]
}
```

## Describing The Cut

Optional top-level `description` (one line saying what the cut is, or the
selection criteria for selects) and `plan` (path of the approved plan under
`edit/plans/`) keep a cut recognizable later. Per range, `beat`, `quote`, and
`reason` label the clip in the editor; `visual` is a free-text note of what is
on screen. None of these affect timing.

## Still Images

A still (a title card, photo, or screenshot: `.png`, `.jpg`, `.jpeg`) is a
source like any other. It is held, not played, so `source_start` is `0` and
`source_end` is the hold length in seconds:

```json
{
  "sources": {"A001": "raw/gameplay.mp4", "T001": "raw/title-card.png"},
  "ranges": [
    {"source": "T001", "source_start": 0, "source_end": 3.0, "record_start": 0, "beat": "TITLE"},
    {"source": "A001", "source_start": 12.4, "source_end": 18.9, "record_start": 3.0}
  ]
}
```

A still has no sound: the timeline is silent while it holds, and the timeline
is single-track for audio, so a still cannot sit over continuing dialogue. Pick
a hold that suits the pacing (two to three seconds for a title card). `speed` and
`visual_layers` do not apply to stills; `transform` does. Stills are fitted inside the frame, not cropped to fill it.

## Muting A Clip

`"mute": true` on a range keeps the picture and drops that clip's own sound,
for B-roll with unusable audio or a stretch that will be scored. The timeline
is silent there until the next clip. Muted ranges get no captions, are skipped
by audio boundary refinement and transcript QA, and are reported by preview QA
as silent by design, not as a fault.
