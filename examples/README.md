# Examples

These example workspaces show the files that `video-timeline-copilot` creates
and consumes during an edit. They intentionally do not include source media.

- `simple-cut/` shows a short silence-removal edit from one talking-head clip.
- `highlight-edit/` shows a compact highlight edit assembled from one longer
  interview clip.

Each example mirrors the normal footage-folder layout:

```text
example-name/
  raw/
  edit/
    media_index.json
    transcripts/
    takes_packed.md
    edl.json
```

To run one locally, add your own media file at the path referenced by
`edit/edl.json`, or update the EDL `sources` entry to point at a real file in
the workspace.
