# FCPXML Audio Notes

The fallback exporter should describe each EDL range as one `asset-clip`, not as
separate `video` and `audio` story elements. Apple documents `asset-clip` as the
shorthand for using the full set of media components from a single asset, and
its `start` and `duration` apply to every media component in that asset.

DaVinci Resolve still displays embedded audio on audio tracks after import. That
is normal for linked A/V media. The XML should not create audio-only edits unless
it emits standalone `audio` elements or `asset-clip` elements with
`srcEnable="audio"`.

To reduce importer inference, generated assets include explicit component
metadata:

- `hasVideo="1"` and `videoSources="1"`
- `hasAudio="1"`, `audioSources="1"`, `audioChannels`, and `audioRate`
- sequence `audioLayout` and `audioRate`
- clip `srcEnable="all"`, `audioRole`, and `videoRole`

If Resolve imports audio without matching video, inspect the generated FCPXML for
standalone `<audio>` elements, `srcEnable="audio"`, or mismatched clip timing.
The current exporter is expected to create only primary-spine `asset-clip`
entries for EDL ranges.

Timeline gaps are unsafe because Resolve imports them as visible black/silent
space. The exporter validates record timing before writing XML and refuses EDLs
with frame-real gaps, overlaps, or clips shorter than the minimum duration.
