# Plan 011: Make visual-layer FCPXML geometry actually map source_rect onto dest_rect

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat df3bd56..HEAD -- helpers/export_fcpxml.py helpers/transforms.py tests/test_export_fcpxml.py tests/test_transforms.py`
> NOTE: this plan was written against commit `df3bd56` **plus uncommitted
> working-tree changes**, and it assumes plan 010
> (`plans/010-fcpxml-layer-offset-and-asset-resources.md`) has landed first.
> The authoritative reference is the "Current state" excerpts below — compare
> them against the live files before starting; on a mismatch beyond plan
> 010's changes, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: HIGH (geometry semantics differ between NLE importers; final sign-off needs one manual DaVinci Resolve import — see Step 6)
- **Depends on**: plans/010-fcpxml-layer-offset-and-asset-resources.md
- **Category**: bug
- **Planned at**: commit `df3bd56` + uncommitted working tree, 2026-07-07
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/45

## Why this matters

`visual_layers` is the split-screen feature for vertical Shorts (facecam on
top, gameplay below). The EDL contract says: crop the region `source_rect`
out of the source frame and display it filling `dest_rect` on the timeline
canvas. The MP4 preview renderer implements exactly that. The FCPXML
exporter does **not**: its `adjust-transform` is computed from `dest_rect`
and the timeline size alone — the source rectangle, the source dimensions,
and the conform scaling never enter the math. The emitted XML only looks
right in the degenerate case the unit test uses (source dimensions equal to
timeline dimensions AND a source_rect spanning the full frame axis being
scaled). For the real case — a 1920x1080 gameplay recording placed on a
1080x1920 vertical timeline — the cropped region lands at the wrong
position and wrong size after import. Since FCPXML is this project's primary
output, this makes the flagship Shorts layout feature produce broken
timelines. After this plan, the exported geometry matches the preview
renderer (the ground truth of intent) under an explicit, documented model.

## The geometry model (read carefully — this is the core of the plan)

### What the DTD says

- `adjust-crop` (mode="trim") "modifies the visible image width and height";
  `trim-rect` values are **percentages of the original frame** (the media's
  own pixels). Trim crops; it does not rescale or recenter the image.
- `adjust-conform`: "The absence of 'adjust-conform' implies 'fit'"; types
  are `fit | fill | none`. Conform scales the clip's original frame to the
  project/timeline frame.
- `adjust-transform`: `position` (default "0 0") and `scale` (default
  "1 1") transform the clip's image about the frame center. In this repo's
  Resolve-validated dialect, `position` values are timeline pixels (see
  `test_build_fcpxml_compensates_zoom_for_transform_position` in
  `tests/test_export_fcpxml.py`, which pins pixel values that were verified
  against a real Resolve import) and positive y (`tilt`) follows the code's
  existing convention in `helpers/transforms.py::transform_for_focus_rect`.

### The model to implement

Use `adjust-conform type="none"` on layer clips (image placed at its
original pixel size, centered on the timeline frame — scale factor between
source pixels and timeline pixels is exactly 1). Then, with:

- source frame size `(W_s, H_s)` (real media dimensions),
- timeline frame size `(W_t, H_t)`,
- effective crop rect `r` (in source pixels — see aspect handling below),
- destination rect `D` (in timeline pixels),

the visible image after trim is the region `r`, sitting centered-frame at
its natural position. `adjust-transform` with per-axis scale `(s_x, s_y)`
about the frame center followed by translation `(p_x, p_y)` (x right,
y up) maps the region center `(r.cx, r.cy)` (y-down source coords) to the
dest center. The required values:

```
s = D.width / r.width          # uniform: r is pre-shaped to D's aspect
p_x = (D.cx - W_t/2) - s * (r.cx - W_s/2)
p_y = (H_t/2 - D.cy) - s * (H_s/2 - r.cy)
```

(`D.cx`, `D.cy` in y-down timeline pixels; the two subtractions convert both
centers into y-up offsets from their frame centers.)

### Aspect handling — match the preview exactly

The preview renderer scales the crop with
`force_original_aspect_ratio=increase` then center-crops to the dest size
(`helpers/render_preview.py:325-326`) — i.e., **aspect-fill with center
crop, no distortion**. Reproduce that in the XML by shrinking the trim rect
instead of distorting the scale: compute the largest sub-rectangle of the
authored `source_rect` that has `dest_rect`'s aspect ratio, centered inside
it; use that sub-rectangle as the effective crop rect `r` for BOTH the
`trim-rect` percentages and the transform math above. Then `s` is uniform
(`D.width / r.width == D.height / r.height` up to float error).

Worked example (use as a unit-test oracle): source 1920x1080, timeline
1080x1920, authored `source_rect = {x: 0, y: 270, width: 480, height: 540}`
(facecam, aspect 480/540 ≈ 0.889), `dest_rect = {x: 0, y: 0, width: 1080,
height: 864}` (aspect 1.25). Dest is wider: keep width 480, shrink height to
`480 / 1.25 = 384`, centered → effective `r = {x: 0, y: 348, width: 480,
height: 384}`. Then `s = 1080/480 = 2.25`;
`p_x = (540 - 540) - 2.25 * (240 - 960) = 1620.0`;
`p_y = (960 - 432) - 2.25 * (540 - 540) = 528.0`.
Trim percentages of the 1920x1080 frame: left `0%`, right
`(1920-480)/1920 = 75%`, top `348/1080 = 32.222222%`, bottom
`(1080-732)/1080 = 32.222222%`.

## Current state

Files and roles:

- `helpers/transforms.py` — pure geometry helpers. Contains
  `visual_layer_source_rect`, `visual_layer_dest_rect`,
  `rect_trim_percentages` (all fine, keep), and `layer_position_and_scale`
  (the broken math, lines 171–178):

  ```python
  def layer_position_and_scale(dest: Rect, width: int, height: int) -> tuple[float, float, float, float]:
      if width <= 0 or height <= 0:
          return 0.0, 0.0, 1.0, 1.0
      center_x = dest.center_x - width / 2.0
      center_y = height / 2.0 - dest.center_y
      scale_x = dest.width / width
      scale_y = dest.height / height
      return center_x, center_y, scale_x, scale_y
  ```

  Note it receives only the dest rect and timeline size — the source rect
  and source size are absent, which is why it cannot be correct.

- `helpers/export_fcpxml.py` — `add_visual_adjustments` (lines 106–138)
  emits, per layer clip: `adjust-crop mode="trim"` with `trim-rect` from
  `rect_trim_percentages(source_rect, source_width, source_height)` (correct
  space — keep), then `adjust-conform type="fill"` (replace with `none`),
  then `adjust-transform` from `layer_position_and_scale(dest_rect,
  timeline_width, timeline_height)` (replace with the model above). The
  caller (lines ~309–320) already resolves `source_width`/`source_height`
  from `media_index.json` with fallback to timeline dims.

- `helpers/render_preview.py` — lines 313–332 are the ground-truth
  compositing (crop in source pixels → aspect-fill scale → center-crop →
  overlay at dest x/y). Do not modify; read it to confirm parity.

- `tests/test_export_fcpxml.py` —
  `test_build_fcpxml_exports_visual_layers_as_connected_video_clips`
  (~line 206) pins the current broken transform values
  (`position "0.000 528.000"`, `scale "1.000000 0.450000"`); it must be
  updated to the new model's values.

- `tests/test_transforms.py` — unit tests for `helpers/transforms.py`; the
  pattern for new pure-math tests.

Repo conventions: `from __future__ import annotations` everywhere; pure
helpers in `transforms.py` with frozen dataclasses (`Rect`); tests are plain
pytest functions, no mocking needed for geometry.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Install | `python -m pip install -e ".[dev]"` | exit 0 |
| Tests (fast loop) | `python -m pytest tests/test_transforms.py tests/test_export_fcpxml.py -q` | all pass |
| Full tests | `python -m pytest -q` | all pass |
| Lint | `python -m ruff check .` | exit 0 |

## Scope

**In scope** (the only files you should modify):

- `helpers/transforms.py`
- `helpers/export_fcpxml.py` (only `add_visual_adjustments` and, if needed,
  its call site)
- `tests/test_transforms.py`
- `tests/test_export_fcpxml.py`
- `tests/test_preview_qa.py` (only if a pinned value there breaks — check
  first; it exercises QA over layered EDLs)

**Out of scope** (do NOT touch):

- `helpers/render_preview.py` — it is the ground truth; the XML must match
  it, not vice versa.
- The single-clip (no `visual_layers`) transform path in
  `helpers/export_fcpxml.py` (`resolve_transform` + `adjust-conform fill`,
  lines ~321–332) and `transform_for_focus_rect` — Resolve-validated,
  frozen.
- `helpers/import_fcpxml.py`, `helpers/update_fcpxml.py`,
  `helpers/validate_edl.py`.
- Layer `offset`/asset/lane behavior — plan 010 owns those.

## Git workflow

- Branch: `advisor/011-fcpxml-layer-geometry`, cut after plan 010's changes
  are present.
- Commit style: short imperative summaries (match `git log`).
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add the aspect-fit helper to transforms.py

New pure function in `helpers/transforms.py`:

```python
def aspect_fill_crop_rect(source_rect: Rect, dest_rect: Rect) -> Rect:
    """Largest centered sub-rect of source_rect with dest_rect's aspect ratio.

    Mirrors the preview renderer's scale=force_original_aspect_ratio=increase
    + center-crop so FCPXML and preview show the same pixels.
    """
```

Behavior: if either rect has non-positive area, return `source_rect`
unchanged. Otherwise compare aspects (`width/height`); shrink one axis of
`source_rect`, keep it centered, return the new `Rect`. Guard the equal-
aspect case (return `source_rect` as-is within 1e-9).

**Verify**: add unit tests first (see Test plan, items 1–2), then
`python -m pytest tests/test_transforms.py -q` → all pass.

### Step 2: Replace layer_position_and_scale with the full-model function

In `helpers/transforms.py`, add:

```python
def layer_transform(
    crop_rect: Rect,
    dest_rect: Rect,
    source_width: int,
    source_height: int,
    timeline_width: int,
    timeline_height: int,
) -> tuple[float, float, float]:
    """Return (position_x, position_y, uniform_scale) for adjust-transform
    under conform="none", per the model in docs (see plan 011 / docs/fcpxml.md).
    """
```

Implementing exactly:

```python
scale = dest_rect.width / crop_rect.width
position_x = (dest_rect.center_x - timeline_width / 2.0) - scale * (crop_rect.center_x - source_width / 2.0)
position_y = (timeline_height / 2.0 - dest_rect.center_y) - scale * (source_height / 2.0 - crop_rect.center_y)
```

with degenerate-input guard (any non-positive dimension → `(0.0, 0.0, 1.0)`).
Delete `layer_position_and_scale` and its import in
`helpers/export_fcpxml.py` (grep to confirm no other caller:
`grep -rn "layer_position_and_scale" helpers tests` — expected: only the two
sites you are changing).

**Verify**: `python -m pytest tests/test_transforms.py -q` → all pass
(including the worked-example test from the Test plan).

### Step 3: Rewire add_visual_adjustments

In `helpers/export_fcpxml.py::add_visual_adjustments`:

1. Compute `source_rect` and `dest_rect` as today.
2. `crop_rect = aspect_fill_crop_rect(source_rect, dest_rect)` — use
   `crop_rect` (not `source_rect`) for `rect_trim_percentages`.
3. Change `adjust-conform` to `{"type": "none"}`.
4. Emit `adjust-transform` from `layer_transform(...)`:

   ```python
   ET.SubElement(
       clip,
       "adjust-transform",
       {
           "position": f"{position_x:.3f} {position_y:.3f}",
           "scale": f"{scale:.6f} {scale:.6f}",
       },
   )
   ```

Element order must remain: `adjust-crop`, `adjust-conform`,
`adjust-transform` (matches the DTD's adjustment ordering used elsewhere in
this exporter).

**Verify**: `python -m pytest tests/test_export_fcpxml.py -q` → the old
layers test FAILS on pinned values (expected at this point), everything else
passes.

### Step 4: Update the exporter layers test to the new model

Rewrite the pinned expectations in
`test_build_fcpxml_exports_visual_layers_as_connected_video_clips` by hand-
computing with the model (source dims default to timeline dims in that test
because there is no media_index.json — state the computation in comments).
For the existing fixture (timeline 1080x1920, Facecam
`source_rect {x:0, y:.45, w:.25, h:.35}` → pixels `{0, 864, 270, 672}`,
`dest_rect {x:0, y:0, w:1, h:.45}` → `{0, 0, 1080, 864}`):
dest aspect = 1.25, source_rect aspect = 270/672 ≈ 0.402 → shrink height to
`270/1.25 = 216`, centered → crop `{0, 1092, 270, 216}`; trim: left 0%,
right 75%, top `1092/1920 = 56.875%`, bottom `(1920-1308)/1920 = 31.875%`;
`s = 1080/270 = 4.0`;
`p_x = (540-540) - 4*(135-540) = 1620.0`;
`p_y = (960-432) - 4*(960-1200) = 1488.0`.
Assert `adjust-conform` type is `"none"` on layer clips.

**Verify**: `python -m pytest tests/test_export_fcpxml.py -q` → all pass.

### Step 5: Add the realistic mixed-dimensions test

New test `test_build_fcpxml_layer_geometry_for_horizontal_source_on_vertical_timeline`
in `tests/test_export_fcpxml.py`: 1920x1080 source declared via a
`media_index.json` fixture (see plan 010's Step 4 test for the fixture
shape), timeline `[1080, 1920]`, and the exact worked example from "The
geometry model" section above. Assert trim percentages
(`32.222222%` top/bottom to 6 decimal places), `scale == "2.250000 2.250000"`,
`position == "1620.000 528.000"`.

**Verify**: `python -m pytest -q` → all pass. `python -m ruff check .` →
exit 0.

### Step 6: Empirical Resolve verification (manual gate)

The math above is spec-derived; DaVinci Resolve's FCPXML importer is the
target and must confirm it. This step needs a human (or an agent with
Resolve installed):

1. Build a tiny real workspace (any short mp4 in `raw/`), write an EDL with
   one range + two `visual_layers` (facecam/screen split as in
   `SKILL.md`'s example), run `vtc render-preview` and `vtc export-fcpxml`.
2. Import the `.fcpxml` into DaVinci Resolve (File > Import > Timeline).
3. Compare Resolve's program monitor against the preview MP4 at the same
   timecode: the two layouts must match (same regions, same placement).

If you cannot run Resolve, mark this plan's status in `plans/README.md` as
`DONE (pending manual Resolve verification — step 6)` and list step 6 as
an explicit follow-up in your report. Do not silently skip it.

**Escape hatch — if Resolve renders the layers wrong**: the most likely
cause is Resolve interpreting `adjust-conform type="none"` differently
(e.g., applying fit anyway). In that case switch to conform `fill` and fold
the conform factor `f = max(W_t/W_s, H_t/H_s)` into the model — trim
percentages stay the same, and the transform becomes
`s = D.width / (f * r.width)`,
`p_x = (D.cx - W_t/2) - s * f * (r.cx - W_s/2)`,
`p_y = (H_t/2 - D.cy) - s * f * (H_s/2 - r.cy)` — update
`layer_transform` to take `f` and re-run steps 4–6. If neither model
matches Resolve, STOP and report the observed behavior with a screenshot.

## Test plan

New tests, in order written:

1. `tests/test_transforms.py::test_aspect_fill_crop_rect_shrinks_taller_source` —
   the worked example: source_rect (0, 270, 480, 540), dest (0, 0, 1080, 864)
   → (0, 348, 480, 384).
2. `tests/test_transforms.py::test_aspect_fill_crop_rect_keeps_matching_aspect` —
   equal aspect returns the input rect.
3. `tests/test_transforms.py::test_layer_transform_maps_crop_center_to_dest_center` —
   the worked example asserting (1620.0, 528.0, 2.25); plus an identity case
   (crop == full source == timeline, dest == full frame → (0, 0, 1.0)).
4. Step 4's rewritten exporter test and Step 5's mixed-dimensions test.

Pattern: plain pytest functions as in the existing `tests/test_transforms.py`.
Verification: `python -m pytest -q` → all pass, ≥4 new tests.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0
- [ ] `python -m ruff check .` exits 0
- [ ] `grep -rn "layer_position_and_scale" helpers tests` returns no matches
- [ ] `grep -n "adjust-conform" helpers/export_fcpxml.py` shows `fill` only
      in the no-layers branch and `none` in `add_visual_adjustments`
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated (with the pending-verification
      note if Step 6 could not run)

## STOP conditions

Stop and report back (do not improvise) if:

- Plan 010 has not landed (layer clips still have `offset="0s"`).
- The "Current state" excerpts don't match the live code beyond plan 010's
  documented changes.
- The worked-example numbers don't reproduce from your implementation after
  one debugging pass — the sign conventions are the likely culprit; report
  your computed values vs. the plan's instead of adjusting the test oracle
  to match the code.
- Matching the preview requires changing `helpers/render_preview.py`.
- Step 6's escape hatch also fails (neither conform model matches Resolve).

## Maintenance notes

- Plan 012 documents this geometry model in `docs/fcpxml.md`; if Step 6's
  escape hatch changed the model to conform-fill, plan 012's doc must record
  the *actual* shipped model and the Resolve behavior that forced it.
- Reviewers should scrutinize the y-axis sign handling: source rects are
  y-down, FCPXML transform position is y-up; the double conversion in
  `layer_transform` is where an error would hide.
- The aspect-fill center-crop means an authored `source_rect` whose aspect
  differs wildly from `dest_rect` silently loses pixels (same as the
  preview). A future QA warning in `qa_preview.py`/`validate_edl.py` when
  the aspect mismatch exceeds some threshold was considered and deferred —
  worth doing if users report surprise crops.
- If per-media fps ever lands in `media_index.json`, revisit nothing here —
  this model is fps-independent.
