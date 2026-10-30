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

## Separately Recorded Audio In Resolve

Observed with DaVinci Resolve 21 Free:

- Connected `lane="-1"` audio `asset-clip` children import onto their own audio
  track, **unlinked** from the video. Trimming the video in the Cut or Edit page
  does not trim the audio. Link the pairs after import with
  `docs/resolve-console.md` (or an MCP or the scripting backend) and say so at
  handoff.
- The camera's embedded audio still imports as a linked track, even at
  `adjust-volume amount="-100"`. When the external recording replaces it, offer
  to remove that track after import.
- Do not rebuild an edit as per-range `ref-clip` elements that point at a
  Resolve compound clip. Resolve created one compound Media Pool item per range
  (192 items for 192 cuts). Flatten to the original assets instead: choose the
  visible video for each range (a higher `lane` wins where clips overlap) and
  compute the external audio `start` from the compound's audio offset and its
  `timeMap` ratio.
- Recomputing the audio `start` for every range keeps sync without a `timeMap`
  when drift inside one range is negligible. For example, at 0.99991 speed a
  range of a few seconds drifts less than 1 ms.
