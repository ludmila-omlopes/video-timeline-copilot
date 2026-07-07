# FCPXML

FCPXML is the primary editable handoff artifact for
`video-timeline-copilot`. `helpers/export_fcpxml.py` generates it from
`edit/edl.json`, `helpers/update_fcpxml.py` updates an existing file in place,
and `helpers/import_fcpxml.py` reads editor changes back into an EDL.

The exporter writes FCPXML version 1.13. DaVinci Resolve is the primary import
target; Final Cut Pro is the format origin and secondary target. Some details
below are defined by the FCPXML DTD. Others are the Resolve dialect this repo
has tested or intentionally pinned.

## Time Model

FCPXML times are rational seconds strings such as `12s` or `1001/30000s`.
Never serialize float seconds directly.

`helpers/export_fcpxml.py` converts all EDL seconds to frame-quantized values:

- `fps_fraction` maps common integer and NTSC rates to rational frame rates.
- `fcpx_frames` rounds seconds to frame counts.
- `fcpx_time_from_frames` serializes the frame count as rational seconds.
- `frame_duration` writes the sequence format's per-frame duration.

For example, at 29.97002997002997 fps, one frame is `1001/30000s`. Keeping
times rational avoids XML that looks precise but lands off-frame after import.

## Timeline Containment Model

The DTD says `offset` defines an object's location in the parent timeline. It
also says `start` defines the local timeline used to schedule contained and
anchored items. That distinction is the main rule for connected clips.

A spine clip's `offset` is its record position. Its `start` is the source
in-point. A connected clip nested inside that spine clip is scheduled in the
parent clip's local timeline, so a layer that starts at the parent's visible
head must use `offset == parent.start`.

```xml
<asset-clip ref="a1" offset="0s" start="12s" duration="2s">
  <asset-clip ref="a2" lane="1" offset="12s" start="30s" duration="2s"/>
</asset-clip>
```

`offset="0s"` on that child would schedule it before the parent's visible
head whenever the parent source in-point is not zero.

Lane values also come from the containment model. The DTD defines lane `0` as
contained in the parent, positive lanes as anchored above, and negative lanes
as anchored below. This exporter uses only positive lanes for connected video
layers. `helpers/validate_edl.py` requires each layer lane to be a positive
integer and unique within the parent range.

## Visual Layers

`visual_layers` keep one primary timing/audio range and add nested video-only
connected clips. The primary clip gets `srcEnable="audio"`; all visible video
comes from the nested layers. If the base source video should be visible, the
EDL must include a layer for it.

Each layer uses:

- an `asset-clip` nested inside the primary clip,
- a positive `lane`,
- `offset` equal to the parent clip's `start`,
- `start` equal to the layer source in-point,
- `srcEnable="video"`,
- `adjust-crop`, `adjust-conform`, and `adjust-transform` to map source pixels
  to the destination rectangle.

The geometry model mirrors `helpers/render_preview.py`: crop the authored
`source_rect`, aspect-fill it into `dest_rect`, then center-crop any excess so
preview MP4s and FCPXML show the same pixels. In FCPXML, the exporter tightens
the trim rectangle to the largest centered sub-rectangle with the destination
aspect ratio, uses `adjust-conform type="none"`, and emits a uniform transform.

With source size `(Ws, Hs)`, timeline size `(Wt, Ht)`, effective crop `r`, and
destination rectangle `D`:

```text
s = D.width / r.width
p_x = (D.cx - Wt / 2) - s * (r.cx - Ws / 2)
p_y = (Ht / 2 - D.cy) - s * (Hs / 2 - r.cy)
```

`D` uses timeline pixels with y down. FCPXML transform position uses the
repo's Resolve-oriented y-up convention.

Worked example: a 1920x1080 source on a 1080x1920 timeline, authored
`source_rect` `{x: 0, y: 270, width: 480, height: 540}`, and `dest_rect`
`{x: 0, y: 0, width: 1080, height: 864}`. The destination is wider, so the
effective crop becomes `{x: 0, y: 348, width: 480, height: 384}`. The
transform is `position="1620.000 528.000"` and
`scale="2.250000 2.250000"`.

This layer model is spec-derived and covered by automated tests. It still
needs the manual Resolve comparison called out in plan 011: import the FCPXML
and compare it to `vtc render-preview` at the same timecode.

## Resources

The exporter writes one `<format>` resource per unique dimension pair. Sequence
clips keep the sequence format. Assets use the media's own format when
`edit/media_index.json` supplies dimensions that differ from the sequence.

Asset duration describes the source media, not a single timeline use. The
exporter prefers the `media_index.json` duration when present and positive.
Without media-index metadata, it declares a duration that covers every
referenced `source_end`, including layer-only sources. An asset shorter than a
referencing clip is a defect importers may reject or mis-conform.

## Resolve Dialect

Some emitted XML is chosen for Resolve behavior, not just DTD validity:

- constant speed changes use `timeMap` with two linear `timept` elements; the
  DTD says a `timeMap` defines an adjusted time range from its first and last
  points,
- transform `position` values are timeline pixels in this repo's pinned tests,
- layer transforms use `adjust-conform type="none"` with explicit trim and
  transform values,
- single-clip transforms without `visual_layers` still use `adjust-conform
  type="fill"` because that path is Resolve-validated.

Resolve treats imported XML as a snapshot. After updating an FCPXML file,
re-import the timeline instead of expecting an existing Resolve timeline to
refresh in place.

## Round Trip Contract

The exporter writes range identity under the metadata key
`com.video-timeline-copilot.range-id`. `helpers/import_fcpxml.py` uses that key
to match imported top-level spine clips back to EDL ranges.

The importer reads only top-level spine `asset-clip` elements. Layer edits made
inside the NLE are not synced back to `visual_layers`; they remain an export
surface, not a round-trip editing contract.

## Checklist: Before You Change `export_fcpxml.py`

- Run `python -m pytest tests/test_fcpxml_invariants.py -q`.
- Never serialize float seconds; use the frame-quantized helpers.
- For anchored connected clips, keep child `offset == parent.start`.
- Keep asset durations long enough to cover every referenced source end.
- Add a pinned-value test for any new geometry behavior.
- Keep spine clip attribute changes compatible with `helpers/import_fcpxml.py`.
- When in doubt, manually compare one Resolve import against
  `vtc render-preview`; the preview is the ground truth of edit intent.

References:

- FCPXML DTD v1.8 mirror in CommandPost:
  https://github.com/CommandPost/CommandPost/blob/develop/src/extensions/cp/apple/fcpxml/dtd/FCPXMLv1_8.dtd
- Apple FCPXML reference:
  https://developer.apple.com/documentation/professional-video-applications/fcpxml-reference
