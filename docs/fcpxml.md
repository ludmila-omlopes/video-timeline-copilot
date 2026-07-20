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

### Embedded Media Timecode

EDL `source_start` and `source_end` values are always relative to the first
frame in the media file. Source files may instead expose a nonzero timecode
origin, commonly `01:00:00:00` in MOV files. `vtc inventory` reads this value
from the primary video stream, a QuickTime `tmcd` data stream, or format tags
and stores it as `start_timecode` plus `timecode_rate` in
`edit/media_index.json`.

The exporter converts that origin to rational seconds and uses it as the
FCPXML asset `start`. Every source-facing time is then written in the asset's
local timeline:

- a range at EDL source time `12s` starts at `3612s` when its asset starts at
  `3600s`,
- connected layers use their own asset origins for `start` while keeping
  `offset` equal to the parent clip's absolute `start`,
- `timeMap` values include the same origin so retimes remain within the asset's
  declared time range.

The importer and FCPXML preview renderer subtract the asset origin again before
writing EDL times or seeking into the physical file. Media indexes created by
older versions do not contain these fields; rerun `vtc inventory` before
re-exporting an affected project.

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

`visual_layers` keep one primary timing/audio range and add one or more visual
regions. For Resolve import compatibility, the exporter promotes one eligible
same-source layer to the primary visible `asset-clip` when possible. It prefers
layers named like `gameplay`, `screen`, `main`, or `base`, then the largest
destination rectangle. Other layers become nested connected video clips above
the primary clip.

If no layer can safely carry the range's primary audio timing, the exporter
falls back to an audio-only primary clip with every visual layer nested as a
connected video clip.

Connected layers use:

- an `asset-clip` nested inside the primary clip,
- a positive `lane`,
- `offset` equal to the parent clip's `start`,
- `start` equal to the layer source in-point,
- `srcEnable="video"`,
- `adjust-crop` and `adjust-transform` to map source pixels to the destination
  rectangle.

The geometry model mirrors `helpers/render_preview.py`: crop the authored
`source_rect`, aspect-fill it into `dest_rect`, then center-crop any excess so
preview MP4s and FCPXML show the same pixels. In FCPXML, the exporter tightens
the trim rectangle to the largest centered sub-rectangle with the destination
aspect ratio and emits Resolve-style `adjust-transform` values.

With source size `(Ws, Hs)`, timeline size `(Wt, Ht)`, effective crop `r`, and
destination rectangle `D`:

```text
pixel_scale = D.width / r.width
fit_scale = min(Wt / Ws, Ht / Hs)
xml_scale = pixel_scale / fit_scale
crop_top_xml = 100 * r.y / Hs
crop_bottom_xml = 100 * (Hs - r.bottom) / Hs
p_x_pixels = (D.cx - Wt / 2) - pixel_scale * (r.cx - Ws / 2)
p_y_pixels = Ht / 2 - D.cy
p_x_xml = p_x_pixels / (Ht / 100)
p_y_xml = p_y_pixels / (Ht / 100)
```

`D` uses timeline pixels with y down. `trim-rect` selects the source region;
`adjust-transform position` then places the layer with Resolve's imported trim
semantics. Horizontal position keeps source-center compensation so asymmetric
left/right trim lands on the authored destination. Vertical position is based
on the destination center only, using the repo's Resolve-oriented y-up
convention.
`xml_scale` compensates for Resolve's default fit conform on horizontal assets
inside vertical timelines. Resolve imports FCPXML `position` values in a
100-units-per-sequence-height coordinate space, so pixel positions are divided
by `Ht / 100` before serialization.
Resolve exports `trim-rect` margins as percentage-like numeric values without
the `%` suffix, so visual-layer crop serialization follows that dialect.
Resolve imports horizontal `left`/`right` trim through a side-specific crop
mapping. The exporter compensates with `--resolve-crop-x-factor` and writes
horizontal visual-layer trim as `source_trim_percent / factor`; the matching
`render-fcpxml-preview` command interprets XML trim with the inverse formula:
`ui_crop = xml_trim / 100 * source_width * fit_scale * factor`.

Worked example: a 1920x1080 source on a 1080x1920 timeline, authored
`source_rect` `{x: 0, y: 270, width: 480, height: 540}`, and `dest_rect`
`{x: 0, y: 0, width: 1080, height: 864}`. The destination is wider, so the
effective crop becomes `{x: 0, y: 348, width: 480, height: 384}`. The pixel
scale is `2.25`; after compensating for Resolve's default `0.5625` fit scale,
the FCPXML transform is `position="84.375 27.500"` and
`scale="4.000000 4.000000"`.

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
- plain range transform `position` values are timeline pixels in this repo's
  pinned tests, while visual-layer transforms use Resolve's imported
  100-units-per-sequence-height coordinate space,
- visual layer transforms avoid `adjust-conform type="none"` because Resolve
  imports that path differently from its own exported Shorts layouts,
- single-clip transforms without `visual_layers` still use `adjust-conform
  type="fill"` because that path is Resolve-validated.

Use `vtc render-fcpxml-preview exported.fcpxml --resolve-crop-x-factor 2` to
inspect the exported XML geometry directly. This preview is intentionally
separate from `vtc render-preview`, which renders the EDL intent before XML
translation.

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
- Preserve embedded asset timecode across plain clips, connected layers,
  retimes, FCPXML import, and FCPXML preview seeking.
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
