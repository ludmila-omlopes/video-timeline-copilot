# Plan 010: Fix connected-clip offsets, asset resources, and lane validation in FCPXML export

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat df3bd56..HEAD -- helpers/export_fcpxml.py helpers/validate_edl.py tests/test_export_fcpxml.py tests/test_validate_edl.py`
> NOTE: this plan was written against commit `df3bd56` **plus uncommitted
> working-tree changes** (the `visual_layers` export feature lives in the
> working tree, not in `df3bd56`). The authoritative reference is the
> "Current state" excerpts below — compare them against the live files before
> starting; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (changes serialized XML that DaVinci Resolve consumes; guarded by round-trip tests)
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `df3bd56` + uncommitted working tree, 2026-07-07
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/44

## Why this matters

FCPXML is this project's most important output: it is the recommended
cross-platform handoff into DaVinci Resolve and Final Cut Pro. The
multi-layer path (`visual_layers` → connected clips) currently emits XML that
is wrong per the FCPXML specification in three independent ways, and the
mistakes stack: (1) every connected layer clip is placed at `offset="0s"` in
its parent's **local** timeline, so any range whose `source_start` is not 0 —
which is essentially every real cut — gets its overlay video shifted
`source_start` seconds before the audio; (2) media used **only** as a visual
layer gets an `<asset>` with `duration="0s"`, and every asset is declared
with the *timeline's* format (e.g., a horizontal 1920x1080 gameplay file is
declared vertical 1080x1920), which misleads importers; (3) lane numbers are
not validated, so duplicate or zero lanes silently produce invalid stacking.
This plan fixes all three mechanically-verifiable defects. (The layer
position/scale geometry has its own deeper problem — that is plan 011, which
depends on this one.)

## FCPXML background you need (do not skip)

Authoritative semantics, quoted from the FCPXML DTD comments (v1.8+, same in
1.13):

- `offset`: "defines the location of the object in the parent timeline
  (default is '0s')."
- `start`: "defines a local timeline to schedule contained and anchored
  items. The default start value is '0s'."
- `lane`: "specifies where the object is contained/anchored relative to its
  parent: 0 = contained inside its parent (default), >0 = anchored above its
  parent, <0 = anchored below its parent."

Consequence: an anchored (connected) clip nested inside a parent `asset-clip`
is scheduled on the parent's **local timeline**, whose origin is defined by
the parent's `start` attribute. The parent asset-clips here set
`start = fcpx_time(source_start, fps)`. Therefore a connected layer that must
begin exactly when the parent becomes visible needs
`offset == parent's start value` — NOT `"0s"`. `"0s"` places it
`source_start` seconds *before* the parent's visible head. The current unit
test only passes because it uses `source_start: 0.0`.

Also: an `<asset>`'s `duration` describes the media file. Declaring `0s` for
a real file, or pointing the asset's `format` at the sequence's format when
the media has different dimensions, is wrong metadata that importers
(Resolve offline relink, conform decisions) can act on.

## Current state

Files and roles:

- `helpers/export_fcpxml.py` — builds the FCPXML tree from a validated EDL.
  All three defects live here.
- `helpers/validate_edl.py` — EDL validator; has a `visual_layers` block
  (lines ~350–370) that validates rects but not lanes.
- `tests/test_export_fcpxml.py` — exporter tests; `write_fcpx_edl` helper at
  the top builds a temp workspace. The layers test
  (`test_build_fcpxml_exports_visual_layers_as_connected_video_clips`,
  line ~206) uses `source_start: 0.0` and no `media_index.json`, so it never
  catches these bugs.
- `tests/test_validate_edl.py` — validator tests;
  `test_validate_accepts_visual_layers_on_a_single_timing_range` (line ~130)
  is the pattern for new lane-validation tests.
- `tests/test_import_fcpxml.py` — round-trip guard; must stay green.

Defect 1 — connected clip offset (`helpers/export_fcpxml.py:294-308`):

```python
layer_clip = ET.SubElement(
    clip,
    "asset-clip",
    {
        "name": str(layer.get("name") or layer.get("label") or f"Layer {layer_index + 1}"),
        "ref": layer_asset_id,
        "lane": str(int(layer.get("lane", layer.get("track", layer_index + 1)))),
        "offset": "0s",
        "start": fcpx_time(layer_source_start, fps),
        ...
```

The parent clip is created a few lines above with
`"start": fcpx_time(source_start, fps)` (`helpers/export_fcpxml.py:267`).

Defect 2 — asset duration and format (`helpers/export_fcpxml.py:204-221`):

```python
for source_id, source_path in timeline["sources"].items():
    if source_id in assets:
        continue
    resolved = ensure_within(resolve_relative(source_path, footage_root), footage_root)
    asset_id = f"a{len(assets) + 1}"
    assets[source_id] = (asset_id, resolved)
    longest_duration = max(
        (float(item["source_end"]) for item in timeline["ranges"] if item["source"] == source_id),
        default=0.0,
    )
    add_asset(
        resources,
        asset_id,
        resolved,
        fcpx_time(longest_duration, fps),
        formats[format_key],          # <-- timeline format, not media format
        media_by_path.get(resolved),
    )
```

`longest_duration` only scans **primary** ranges (`item["source"]`), never
`visual_layers[*].source` / layer `source_end`, so a facecam file used only
as a layer gets `duration="0s"`. `formats[format_key]` is the sequence
format of whichever timeline declared the source first.

`media_index.json` entries (built by `helpers/inventory.py:19-25`) provide
per-media `duration` (float seconds), `width`, `height`, `audio_channels`,
`audio_rate` — no fps. `load_media_index` (`helpers/export_fcpxml.py:339-350`)
already maps resolved paths to these dicts, and `add_asset` already consumes
`audio_channels`/`audio_rate`.

Defect 3 — lanes unvalidated (`helpers/export_fcpxml.py:300`): the effective
lane is `layer.get("lane", layer.get("track", layer_index + 1))`. Nothing
rejects `lane: 0` (meaning "inside parent", not anchored — invalid for a
connected clip per the DTD) or two layers resolving to the same lane
(overlapping same-lane siblings are invalid stacking).

Repo conventions that apply:

- `from __future__ import annotations` at the top of every module (already
  present in all touched files).
- Tests are plain pytest functions with `tmp_path`; never invoke real
  FFmpeg/FFprobe — the exporter tests only touch JSON/XML, no mocking needed.
- Error style in the exporter: `raise ValueError(f"range {index + 1} ...")`;
  error style in the validator: append strings like
  `f"{layer_prefix}.lane must be a positive integer"`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Install | `python -m pip install -e ".[dev]"` | exit 0 |
| Tests (fast loop) | `python -m pytest tests/test_export_fcpxml.py tests/test_validate_edl.py tests/test_import_fcpxml.py -q` | all pass |
| Full tests | `python -m pytest -q` | all pass |
| Lint | `python -m ruff check .` | exit 0, no findings |

## Scope

**In scope** (the only files you should modify):

- `helpers/export_fcpxml.py`
- `helpers/validate_edl.py`
- `tests/test_export_fcpxml.py`
- `tests/test_validate_edl.py`

**Out of scope** (do NOT touch, even though they look related):

- The layer `position`/`scale`/`adjust-conform` geometry in
  `add_visual_adjustments` and `helpers/transforms.py` — that is plan 011.
- `helpers/import_fcpxml.py` — it reads only top-level spine clips and the
  sequence format; nothing here changes what it parses. If a change seems
  required there, STOP.
- `helpers/update_fcpxml.py`, `helpers/render_preview.py`,
  `helpers/build_resolve_project.py`.
- The single-clip (no `visual_layers`) transform path
  (`helpers/export_fcpxml.py:321-332`) — its output was validated against a
  real Resolve import; do not alter its attributes.
- `hasVideo`/`hasAudio` hardcoded to "1" in `add_asset` — known imprecision,
  deliberately deferred (needs per-media stream info the exporter can get
  from `media_index`, but changing it risks Resolve relink behavior; not
  part of this fix).

## Git workflow

- Branch: `advisor/010-fcpxml-layer-offset-and-asset-resources` off the
  current branch (`codex/issues-38-41-plans`). NOTE: the in-scope files have
  uncommitted changes that ARE the feature being fixed; do not stash or
  revert them.
- Commit style (from `git log`): short imperative summaries, e.g.
  "Fix connected-clip offsets in FCPXML export".
- Do NOT push or open a PR unless the operator instructed it.

### Step 1: Anchor layer clips at the parent's start

In `helpers/export_fcpxml.py`, in the `visual_layers` loop, change the layer
clip's `"offset"` from `"0s"` to the same value as the parent clip's `start`
attribute — the parent's frame-quantized source start:

```python
"offset": fcpx_time(source_start, fps),
```

`source_start` here must be the **parent range's** `source_start` (the local
variable already defined at `helpers/export_fcpxml.py:253`), not the layer's
`layer_source_start`. The layer's own in-point stays in its `start`
attribute, which is already `fcpx_time(layer_source_start, fps)`.

**Verify**: `python -m pytest tests/test_export_fcpxml.py -q` → all pass
(the existing layers test uses `source_start 0.0`, where both values
coincide; new coverage comes in Step 4).

### Step 2: Give each asset its media format and a real duration

Still in `build_fcpxml`:

1. Extend the asset loop so the declared duration covers **all** uses of the
   source: primary ranges (`item["source_end"]` where
   `item["source"] == source_id`) AND visual layers (for each range item,
   each `layer` in `item.get("visual_layers") or []` where
   `layer.get("source", item["source"]) == source_id`, use
   `float(layer.get("source_end", item["source_end"]))`). Then, if the media
   index entry for this file has a positive `duration`, prefer that (it is
   the true file duration from ffprobe): 
   `declared = media_duration if media_duration > 0 else computed_max`.
2. Give assets whose media dimensions differ from the timeline resolution
   their own `<format>` resource instead of the sequence format. Concretely:
   look up `media_by_path.get(resolved)`; if it has positive `width` and
   `height` and `(width, height)` differs from the timeline's
   `(int(width), int(height))`, create (or reuse — keep a dict keyed by
   `(w, h)`, shared with the sequence formats dict since the shape is
   identical) a format element:

   ```python
   {
       "id": format_id,
       "name": f"FFVideoFormat{w}x{h}",
       "frameDuration": frame_duration(fps),
       "width": str(w),
       "height": str(h),
   }
   ```

   and pass that format id to `add_asset`. The media index has no per-file
   fps, so reusing the timeline `frameDuration` is the documented, accepted
   approximation. If no media-index entry exists (tests without
   `media_index.json`), keep today's behavior (sequence format).
   The existing `formats` dict keyed by `(int(width), int(height))` already
   deduplicates — reuse it rather than adding a parallel dict.

Do NOT change the `format` attribute on `asset-clip` elements (both primary
and layer clips keep the sequence format id) — that attribute's current value
is part of the Resolve-validated dialect; only the `<asset>`'s own `format`
ref changes.

**Verify**: `python -m pytest tests/test_export_fcpxml.py tests/test_import_fcpxml.py -q`
→ all pass.

### Step 3: Validate lanes in the EDL validator

In `helpers/validate_edl.py`, inside the existing `visual_layers` loop
(after the `dest_rect` checks, ~line 370), compute the effective lane exactly
as the exporter does — `layer.get("lane", layer.get("track", layer_index + 1))` —
and append errors when:

- the value is not an integer (or integer-valued number) ≥ 1:
  `f"{layer_prefix}.lane must be a positive integer"`
- the effective lane duplicates another layer's effective lane in the same
  range: `f"{layer_prefix}.lane duplicates lane <n> in the same range"`

Track seen lanes in a set per range. Coerce with the same
`int(...)`-after-float-check pattern used elsewhere in the validator (wrap
in `try/except (TypeError, ValueError)` → the "must be a positive integer"
error).

**Verify**: `python -m pytest tests/test_validate_edl.py -q` → all pass.

### Step 4: Add regression tests

In `tests/test_export_fcpxml.py` (model on the existing
`test_build_fcpxml_exports_visual_layers_as_connected_video_clips`):

1. `test_build_fcpxml_anchors_layers_at_parent_start` — a range with
   `source_start: 12.0`, `source_end: 14.0`, one visual layer. Assert every
   nested `asset-clip`'s `offset` equals the parent `asset-clip`'s `start`
   attribute (compare strings; both are `fcpx_time(12.0, fps)` = `"12s"` at
   fps 30).
2. `test_build_fcpxml_layer_only_source_gets_media_duration_and_format` —
   two source files (`raw/clip.mp4`, `raw/facecam.mp4`), a
   `edit/media_index.json` written by the test containing entries for both
   (facecam: `{"path": "raw/facecam.mp4", "duration": 90.0, "width": 1920,
   "height": 1080, "audio_channels": 2, "audio_rate": 48000}`), a vertical
   `[1080, 1920]` timeline whose only range uses `clip.mp4` as primary and
   `facecam.mp4` only inside `visual_layers` (with `source_start`/`source_end`
   on the layer). Assert: the facecam `<asset>` `duration` parses (use the
   local `parse_fcpx_time` helper) to 90.0, not 0; and its `format` attribute
   points to a `<format>` element with `width="1920" height="1080"`.
3. Extend the existing layers test (or add a sibling) to assert
   `offset` of layer clips is present and equals parent `start` even in the
   `source_start 0.0` case (`"0s"` == `"0s"`), so the attribute is pinned.

In `tests/test_validate_edl.py` (model on
`test_validate_rejects_visual_layer_with_unknown_source` at ~line 150):

4. `test_validate_rejects_duplicate_visual_layer_lanes` — two layers with
   explicit `"lane": 1` each → expect an error containing
   `visual_layers[1].lane`.
5. `test_validate_rejects_non_positive_visual_layer_lane` — one layer with
   `"lane": 0` → expect `lane must be a positive integer`.

**Verify**: `python -m pytest -q` → all pass, including 4–5 new tests.
`python -m ruff check .` → exit 0.

## Test plan

Covered by Step 4. Structural pattern: `write_fcpx_edl` helper +
element-tree assertions, as in `tests/test_export_fcpxml.py`. The media-index
fixture is new — write the JSON with `json.dumps` into
`tmp_path / "edit" / "media_index.json"`; paths in it are relative to the
footage root (see `load_media_index` resolving with `resolve_relative`).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0; new tests from Step 4 exist and pass
- [ ] `python -m ruff check .` exits 0
- [ ] `grep -n "\"offset\": \"0s\"" helpers/export_fcpxml.py` returns no matches
- [ ] `python -m pytest tests/test_import_fcpxml.py -q` exits 0 (round-trip unaffected)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The "Current state" excerpts don't match the live code (the working tree
  this plan was written against has drifted or been committed differently).
- `tests/test_import_fcpxml.py` fails after Step 2 — the importer resolving
  assets by `media-rep` src should be format-agnostic; a failure means an
  assumption about the importer is wrong.
- You find yourself needing to change `helpers/transforms.py` or the
  `add_visual_adjustments` function — that's plan 011's territory.
- The lane validation breaks any existing example workspace under
  `examples/` (run `python -m pytest -q`; the examples are exercised by
  tests) — report which EDL uses duplicate/zero lanes instead of relaxing
  the rule.

## Maintenance notes

- Plan 011 (layer geometry) builds directly on this: it rewrites
  `add_visual_adjustments` and assumes offsets/assets are already correct.
- Reviewers should scrutinize: the layer `offset` must be the **parent's**
  frame-quantized `source_start`, not the layer's; these differ whenever a
  layer overrides `source_start`.
- Deferred: per-media fps in `media_index.json` (would let asset formats
  carry true `frameDuration`); `hasVideo`/`hasAudio` accuracy on `<asset>`.
- Anything that changes how `range_id` metadata or top-level spine clips are
  written must keep `vtc import-fcpxml` matching (see
  `tests/test_import_fcpxml.py`).
