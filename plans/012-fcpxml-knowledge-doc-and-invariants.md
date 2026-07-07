# Plan 012: Write the FCPXML knowledge base (docs/fcpxml.md) and encode its rules as invariant tests

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat df3bd56..HEAD -- helpers/export_fcpxml.py docs/ AGENTS.md SKILL.md tests/`
> This plan was written against commit `df3bd56` + uncommitted working-tree
> changes and assumes plans 010 and 011 have landed. Before starting, read
> the CURRENT `helpers/export_fcpxml.py` and `helpers/transforms.py` — the
> document you write must describe the code as it exists after 010/011, and
> plan 011's Step 6 may have switched the geometry model to its conform-fill
> escape hatch. Describe what shipped, not what this plan predicts.

## Status

- **Priority**: P1
- **Effort**: S-M
- **Risk**: LOW (docs + additive tests only)
- **Depends on**: plans/010-fcpxml-layer-offset-and-asset-resources.md, plans/011-fcpxml-layer-geometry.md
- **Category**: docs / tests
- **Planned at**: commit `df3bd56` + uncommitted working tree, 2026-07-07
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/46

## Why this matters

The multi-layer FCPXML bugs fixed by plans 010/011 all came from the same
root cause: FCPXML's timing and spatial semantics are subtle
(parent-relative anchoring, local timelines, trim-vs-conform-vs-transform
interaction, a Resolve-specific dialect), and none of that knowledge was
written down in this repo — so each contributor or agent editing
`export_fcpxml.py` re-derives it and gets parts wrong. The maintainer
explicitly asked for this knowledge to be documented "so it makes no more
mistakes." The durable home is (a) a contributor-facing reference,
`docs/fcpxml.md`, linked from `AGENTS.md` so every agent working on this
repo is routed to it before touching the exporter, and (b) a set of
invariant tests that mechanically enforce the documented rules on every
generated document — knowledge that enforces itself survives contributor
turnover; a personal skill outside the repo would not.

## Current state

- `docs/` contains `architecture.md`, `audio-analysis.md`,
  `shorts-guidelines.md`, `e2e-test.md` — plain Markdown, sentence-style
  prose, no front matter. `docs/fcpxml.md` does not exist.
- `AGENTS.md` "Repo map" section lists one line per helper module
  (e.g. `- helpers/export_fcpxml.py - exports FCPXML from a
  video-timeline-copilot EDL.`) and its "Conventions" section is a bulleted
  list; `docs/architecture.md` is referenced right below the repo map.
- `SKILL.md` (end-user product spec) documents `visual_layers` with a JSON
  example (~line 500) and states layers export "as one primary audio clip
  with connected video-only layers in FCPXML."
- `helpers/export_fcpxml.py` — the exporter. Key facts to document (verify
  each against the post-010/011 code before writing):
  - Times are rational seconds: `fcpx_time`/`fps_fraction`/
    `fcpx_time_from_frames` quantize to frames and emit `N/Ds` strings;
    NTSC rates map to 1001-denominator fractions.
  - `FCPXML_VERSION = "1.13"`; range-id round-trip metadata key
    `com.video-timeline-copilot.range-id` (consumed by
    `helpers/import_fcpxml.py`).
  - Spine clips: `offset` = record position, `start` = source in-point,
    `duration` = frame-quantized timeline duration; gaps/overlaps raise.
  - Layers: primary clip becomes `srcEnable="audio"`; each layer is a
    nested `asset-clip` with `lane >= 1`, `offset` equal to the parent's
    `start` (plan 010), trim/conform/transform per plan 011's model.
  - Speed: Resolve-style `timeMap` with two linear `timept`s
    (`add_time_map`).
- Tests: `tests/test_export_fcpxml.py` holds all exporter tests;
  `write_fcpx_edl` is the workspace fixture helper;
  `test_build_fcpxml_uses_integer_rational_time_attributes_for_ntsc_fps`
  (~line 298) is the exemplar of an invariant-style test that sweeps the
  whole generated tree.

Authoritative external references to cite in the doc (verified during
planning):

- FCPXML DTD comments (v1.8, identical wording through 1.13), from
  `https://github.com/CommandPost/CommandPost/blob/develop/src/extensions/cp/apple/fcpxml/dtd/FCPXMLv1_8.dtd`:
  - `offset`: "defines the location of the object in the parent timeline
    (default is '0s')."
  - `start`: "defines a local timeline to schedule contained and anchored
    items. The default start value is '0s'."
  - `lane`: "0 = contained inside its parent (default), >0 = anchored above
    its parent, <0 = anchored below its parent."
  - `adjust-conform`: "The absence of 'adjust-conform' implies 'fit'."
  - `timeMap`: "defines a new adjusted time range for the clip using the
    first and last 'timept' elements."
- Apple's FCPXML reference: `https://developer.apple.com/documentation/professional-video-applications/fcpxml-reference`

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Install | `python -m pip install -e ".[dev]"` | exit 0 |
| Tests | `python -m pytest -q` | all pass |
| Lint | `python -m ruff check .` | exit 0 |
| Skill validation (CI gate) | `npx -y skills-ref validate .` | exit 0 |

## Scope

**In scope**:

- `docs/fcpxml.md` (create)
- `tests/test_fcpxml_invariants.py` (create)
- `AGENTS.md` (add one repo-map/conventions pointer line)
- `SKILL.md` (one short paragraph, only if plan 011 shipped the aspect-fill
  center-crop behavior — see Step 3)

**Out of scope** (do NOT touch):

- Any `helpers/*.py` — this plan changes zero behavior. If writing an
  invariant test reveals a behavior bug, STOP and report it; do not fix it
  here.
- `docs/architecture.md`, `README.md`.
- Existing tests.

## Git workflow

- Branch: `advisor/012-fcpxml-knowledge-doc`.
- Commit style: short imperative summaries (match `git log`).
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Write docs/fcpxml.md

Match the tone/format of `docs/architecture.md` (plain Markdown, `##`
sections, prose + fenced examples). Required sections and content — every
code claim verified against the live post-010/011 code, every spec claim
carrying its DTD quote:

1. **Purpose** — FCPXML is the primary handoff artifact; generated by
   `helpers/export_fcpxml.py`, updated by `helpers/update_fcpxml.py`,
   re-imported by `helpers/import_fcpxml.py`; version 1.13; target
   importers are DaVinci Resolve (primary, empirically validated) and
   Final Cut Pro.
2. **Time model** — rational-seconds strings (`3003/30000s`); all times
   frame-quantized via `fps_fraction`/`fcpx_frames`; NTSC handling; why
   float seconds must never be serialized directly.
3. **The timeline containment model** (the section that would have
   prevented the layer bugs — make it prominent):
   - `offset` = position in the **parent's** timeline (DTD quote).
   - `start` = origin of the element's **local** timeline for contained and
     anchored children (DTD quote).
   - Therefore: an anchored (connected) clip that must begin at its
     parent's visible head needs `offset == parent.start`, and `"0s"` is
     wrong whenever the parent's in-point is not 0. State this as a rule
     with a two-clip XML example.
   - `lane` semantics (DTD quote); this exporter uses lanes ≥ 1, unique per
     parent, validated in `helpers/validate_edl.py`.
4. **How visual_layers are serialized** — primary clip `srcEnable="audio"`
   (audio + timing come from the primary; ALL video comes from layers — an
   EDL wanting base video visible must include a layer for it), nested
   video-only `asset-clip` per layer, and the geometry model exactly as
   shipped by plan 011 (trim percentages are of the **source** frame;
   conform mode; the transform formulas with the worked example; the
   aspect-fill center-crop parity rule with `render_preview.py`). If plan
   011 used its conform-fill escape hatch, document that model and the
   observed Resolve behavior that forced it.
5. **Resources** — one `<format>` per unique dimensions; assets carry the
   media's own format and real duration (media-index duration preferred);
   asset `duration` must cover every referenced `source_end` — an asset
   shorter than its clips is a defect importers may reject.
6. **The Resolve dialect** — parts validated empirically against Resolve
   rather than the DTD: `timeMap`/`timept` retimes, transform `position`
   in timeline pixels, `adjust-transform` scale conventions; note FCP
   proper may interpret transform units differently and that Resolve is the
   validation target. Also: Resolve treats XML import as a snapshot
   (re-import after updating the file; see README's note).
7. **Round-trip contract** — the `com.video-timeline-copilot.range-id`
   metadata key; importer reads only top-level spine `asset-clip`s; layer
   edits made inside the NLE are not synced back to the EDL.
8. **Checklist: before you change export_fcpxml.py** — a short list:
   run `tests/test_fcpxml_invariants.py`; never serialize float seconds;
   anchored offset rule; asset-duration rule; add a pinned-value test for
   any new geometry; changes to spine-clip attributes must keep
   `import_fcpxml` matching; when in doubt, verify one manual Resolve
   import against `vtc render-preview` output (the preview is the ground
   truth of intent).

**Verify**: `npx -y skills-ref validate .` → exit 0 (doc files are part of
the packaged skill tree; this is the CI gate that would catch a packaging
problem).

### Step 2: Encode the rules as tests/test_fcpxml_invariants.py

New test module, modeled structurally on `tests/test_export_fcpxml.py`
(reuse its `write_fcpx_edl`-style fixture — copy the helper or import
nothing and build the workspace inline; do NOT import private helpers from
the other test module). Build one representative EDL exercising the full
surface: two sources (one layer-only) with a `media_index.json`, a vertical
timeline, ranges with nonzero `source_start`, one retimed range
(`speed: 2.0`), one range with two `visual_layers`. Then assert tree-wide
invariants (each its own test function so failures name the violated rule):

1. `test_all_time_attributes_are_rational_seconds` — every
   `offset`/`start`/`duration`/`frameDuration` in the tree matches
   `^\d+(?:/\d+)?s$` (pattern from the existing NTSC test).
2. `test_anchored_clips_offset_equals_parent_start` — for every nested
   `asset-clip` with a `lane` attribute, `offset == parent.start`.
3. `test_lanes_are_positive_and_unique_per_parent`.
4. `test_every_ref_resolves` — every `ref`/`format` attribute value exists
   as a resource `id` in `<resources>`.
5. `test_asset_durations_cover_all_referenced_source_ends` — for each
   asset, parse its `duration` and assert it is ≥ every referencing clip's
   `start + duration` mapped through any `timeMap` (simplification allowed:
   assert ≥ every clip's source_end taken from the EDL fixture — document
   the shortcut in a comment).
6. `test_primary_clips_with_layers_are_audio_only` — `srcEnable="audio"`
   on any spine clip containing nested clips, `srcEnable="video"` on every
   nested layer clip.

**Verify**: `python -m pytest tests/test_fcpxml_invariants.py -q` → all
pass. If any invariant FAILS against current code, that is a STOP condition
(you found a live bug or plans 010/011 landed incompletely) — report it.

### Step 3: Add the pointers

- `AGENTS.md` — in the Repo map, extend the `export_fcpxml.py` line (or add
  a sentence after the repo map next to the existing `docs/architecture.md`
  pointer): "See `docs/fcpxml.md` before changing FCPXML
  generation/import — it documents the timing/anchoring/geometry rules the
  exporters must uphold."
- `SKILL.md` — only if the shipped geometry does aspect-fill center-crop:
  add one sentence to the `visual_layers` paragraph (~line 501) telling the
  EDL author that when `source_rect` and `dest_rect` aspect ratios differ,
  the crop is tightened (centered) to the destination aspect, in both
  preview and FCPXML. This is end-user product behavior, which is why it
  belongs in `SKILL.md`; everything else in this plan is contributor
  knowledge and stays in `docs/`.

**Verify**: `python -m pytest -q` → all pass; `python -m ruff check .` →
exit 0; `npx -y skills-ref validate .` → exit 0.

## Test plan

Step 2 IS the test plan (6 new invariant tests). No other tests change.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `docs/fcpxml.md` exists and contains the strings "local timeline",
      "anchored", `com.video-timeline-copilot.range-id`, and a
      "before you change" checklist section
- [ ] `python -m pytest tests/test_fcpxml_invariants.py -q` exits 0 with
      ≥6 tests collected
- [ ] `python -m pytest -q` and `python -m ruff check .` exit 0
- [ ] `grep -n "fcpxml.md" AGENTS.md` returns ≥1 match
- [ ] `npx -y skills-ref validate .` exits 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Plans 010/011 are not both DONE in `plans/README.md`.
- Any Step 2 invariant fails against the current exporter — that is a live
  bug report, not something to patch around in the test.
- The current geometry code contradicts plan 011's primary model AND its
  escape-hatch model — you cannot document what you cannot identify; report
  what the code actually does.
- Writing the doc would require asserting a Resolve behavior that was never
  verified (plan 011 Step 6 skipped) — write the section anyway but mark it
  explicitly "spec-derived, not yet Resolve-verified" and say so in your
  report.

## Maintenance notes

- `docs/fcpxml.md` must be updated in the same PR as any future
  `export_fcpxml.py`/`import_fcpxml.py` semantic change — reviewers should
  reject exporter changes that don't touch the doc or the invariants.
- The invariant tests intentionally overlap some per-feature tests in
  `tests/test_export_fcpxml.py`; that redundancy is the point (per-feature
  tests pin values, invariants pin rules). Do not "deduplicate" them.
- Deferred: validating generated XML against the actual Apple DTD (e.g.
  vendored `FCPXMLv1_13.dtd` + `xmlschema`/`lxml` in CI). Rejected for now:
  adds a native/lxml dependency and Apple DTD redistribution questions;
  the invariant tests cover the classes of mistake this repo has actually
  made.
