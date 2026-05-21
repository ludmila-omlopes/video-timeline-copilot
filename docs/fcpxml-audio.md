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

Zero-duration gaps are also unsafe. The exporter compares gap boundaries in
rounded frame units before writing XML, so sub-frame spacing between adjacent
cuts does not become a `gap` whose serialized duration is `0/...s`.
