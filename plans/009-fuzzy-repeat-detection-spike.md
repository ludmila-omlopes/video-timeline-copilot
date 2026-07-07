# Plan 009: Spike — detect partial restarts and self-corrections as repeated takes (issue #32)

> **Executor instructions**: This is a design/spike plan, not a build-everything
> plan. Follow it step by step; run every verification command. If anything in
> "STOP conditions" occurs, stop and report — do not improvise. When done,
> update the status row for this plan in `plans/README.md` — unless a reviewer
> dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3716700..HEAD -- helpers/pack_transcripts.py tests/test_pack_transcripts.py`
> If either file changed since this plan was written, compare the "Current
> state" excerpts against the live code before proceeding; on a mismatch,
> treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M (coarse — spike)
- **Risk**: MED (false positives degrade the packed transcript for every edit)
- **Depends on**: none
- **Category**: direction
- **Issue**: https://github.com/ludmila-omlopes/video-timeline-copilot/issues/41 (plan); addresses finding from issue #32

## Why this matters

Issue #32 (direct user report, in Portuguese): when a narrator slightly
flubs a line and immediately corrects it — "A gente vai publicar na terça...
na quinta-feira", "esse arquivo fica em docs... em helpers/docs" — the packed
transcript does not flag it, so the agent keeps both the flub and the
correction in the rough cut. The current detector compares **whole phrases**
against earlier whole phrases; a correction that restarts only the tail of a
sentence is structurally invisible to it. The goal of this spike is a
detection that flags these partial restarts with a low false-positive rate,
or a written conclusion that it can't be done reliably at the text level.

## Current state

- `helpers/pack_transcripts.py` — builds `edit/takes_packed.md` from
  transcript JSON. Words are grouped into phrases by silence gaps
  (`group_words`, line 16: a new phrase starts when the inter-word gap ≥
  `silence_threshold`, default 0.5s). Each phrase is then compared to
  previous phrases within a 45s window:

```python
# helpers/pack_transcripts.py:48-81 (abridged)
def repeated_delivery_note(phrase, previous_phrases, *, repeat_window, similarity_threshold, min_words):
    text = normalize_text(phrase.get("text") or "")
    words = text.split()
    if len(words) < min_words:          # default min_words = 3
        return None
    for previous in reversed(previous_phrases):
        if phrase["start"] - previous["end"] > repeat_window:   # default 45.0s
            break
        ...
        shorter, longer = sorted((text, previous_text), key=len)
        contains_retake = len(shorter.split()) >= min_words and shorter in longer
        starts_same = words[:min_words] == previous_words[:min_words]
        similar = SequenceMatcher(None, text, previous_text).ratio() >= similarity_threshold  # default 0.82
        if contains_retake or starts_same or similar:
            return f"possible repeated take of {fmt(previous['start'])}-{fmt(previous['end'])}; use only the cleanest complete delivery"
    return None
```

- Why issue #32's cases slip through, concretely. Take
  "A gente vai publicar na terça" → (pause) → "na quinta-feira":
  - `contains_retake`: "na quinta-feira" is not a substring of the first phrase — fails.
  - `starts_same`: first 3 words differ — fails.
  - `similar`: whole-string ratio is far below 0.82 — fails.
  And when the pause is shorter than `silence_threshold` (0.5s), both
  fragments land in ONE phrase, where no comparison happens at all.
- CLI knobs (in `main()`, lines ~163-165): `--repeat-window` 45.0,
  `--repeat-similarity` 0.82, `--repeat-min-words` 3. Notes are emitted as
  `[NOTE: ...]` suffixes on phrase lines in `build_packed_lines` (line ~122).
- Tests: `tests/test_pack_transcripts.py` — plain pytest functions building
  word lists and asserting on `build_packed_lines` / `repeated_delivery_note`
  output. Follow this structure.
- Transcript JSON provides word-level `start`/`end` (faster-whisper word
  timestamps), so word timing is available inside phrases.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests | `python -m pytest -q` | all pass |
| Focused | `python -m pytest -q tests/test_pack_transcripts.py` | all pass |
| Lint | `python -m ruff check .` | `All checks passed!` |

On this machine there is a ready venv: use `./.venv/Scripts/python.exe -m ...`
if bare `python -m pytest` reports "No module named pytest".

## Scope

**In scope**:
- `helpers/pack_transcripts.py` — new detection logic + note text.
- `tests/test_pack_transcripts.py` — new tests.
- `README.md` / `SKILL.md` — only if the spike ships (Step 4), one short
  paragraph each describing the new note type; no other edits.

**Out of scope** (do NOT touch):
- `helpers/draft_silence_cut.py` — cutting decisions stay with the agent;
  this feature only annotates the packed transcript.
- Semantic/embedding similarity, external NLP dependencies, or any new
  runtime dependency — the package deliberately has zero runtime deps.
- Changing the existing whole-phrase detection or its defaults — additive only.

## Git workflow

- Branch: `advisor/009-fuzzy-repeat-detection`
- Commit style: short imperative subject, e.g. `Flag partial restarts as repeat candidates`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Build the evaluation harness first (tests as spec)

In `tests/test_pack_transcripts.py`, add (initially failing) tests encoding
issue #32's acceptance criteria. Build word lists with realistic timings
(words ~0.3s long, correction pause ~0.3-0.6s). Positive cases:

1. Tail correction, same phrase (pause < 0.5s so no phrase split):
   words for "a gente vai publicar na terça na quinta-feira" → expect a note.
2. Tail correction across a phrase split (pause ≥ 0.5s):
   phrase A "esse arquivo fica em docs", phrase B "em helpers docs" → expect a note on B.
3. Restart after interruption: phrase A "eu acho que esse trecho",
   phrase B "esse trecho precisa sair" → expect a note on B.

Negative cases (must NOT be flagged):

4. Enumeration: "primeiro a gente grava, depois a gente corta, depois a gente publica".
5. Intentional emphasis of ≤2 words: "muito, muito bom".
6. Ordinary distinct consecutive phrases sharing a topic word.

**Verify**: `python -m pytest -q tests/test_pack_transcripts.py` → new tests FAIL (red), pre-existing tests still pass.

### Step 2: Implement restart detection at the word level

Add a new pure function in `helpers/pack_transcripts.py`:

```python
def restart_correction_note(phrase, previous_phrases, *, min_overlap_words: int = 2, max_restart_gap: float = 1.5) -> str | None:
```

Recommended algorithm (adjust freely if the tests say otherwise — the tests
are the contract, this sketch is not):

- **Cross-phrase restart**: let B = current phrase, A = the immediately
  previous phrase with `B.start - A.end <= max_restart_gap`. Tokenize both
  with the existing `normalize_text`. If B's first `min_overlap_words` tokens
  match any contiguous token window in the last ~6 tokens of A with
  SequenceMatcher token-ratio ≥ 0.8 (compare token lists, not raw strings),
  and B is not simply a continuation (i.e. the matched window is NOT A's
  final tokens followed by entirely new material — require that B replaces
  A's tail rather than extends it: the token immediately after the match in B
  differs from the token after the matched window in A, or A's match window
  reaches A's end), flag B.
- **Intra-phrase restart**: scan the phrase's own word list for a token
  window of length ≥ `min_overlap_words` that repeats within the next ~8
  tokens with a word-timing gap ≥ 0.15s between the two occurrences
  (hesitation signal), e.g. "esse trecho ... esse trecho". Flag the phrase.
- **False-positive guards** (these make tests 4-6 pass): never flag on a
  single repeated token; skip windows made only of stopword-length tokens
  (≤2 chars); for enumerations, require the repeated window to be ≥
  `min_overlap_words` AND the surrounding words to differ (in an enumeration
  like "depois a gente X, depois a gente Y" the window recurs with *parallel*
  structure — exempt matches where the token before each occurrence is
  identical).

Note text, matching the existing style:
`"possible self-correction/restart of <t0>-<t1>; keep only the corrected delivery"`
(for intra-phrase, use the phrase's own start/end).

Wire it into `build_packed_lines` alongside `repeated_delivery_note`: compute
both; if both fire, prefer the existing repeated-take note. Expose knobs as
CLI args following the existing pattern (`--restart-overlap-words`,
`--restart-max-gap`) with the defaults above.

**Verify**: `python -m pytest -q tests/test_pack_transcripts.py` → ALL pass (new and pre-existing). `python -m ruff check .` → clean.

### Step 3: Evaluate false positives against the bundled examples

Run the packer against the repo's media-free example workspace(s) under
`examples/` (they contain transcript JSON): for each example,
run `python -m helpers.pack_transcripts --edit-dir <example>/edit` on a COPY
of the example under a temp directory (never modify `examples/` in place —
`takes_packed.md` is a committed artifact there). Diff the produced
`takes_packed.md` against the committed one: the only acceptable new
differences are `self-correction/restart` notes that are genuinely plausible
when you read the surrounding text. Record the count of new notes and your
judgment for each in the spike report (Step 4).

**Verify**: `git status` → `examples/` unmodified.

### Step 4: Ship or write down why not

- If tests pass and Step 3 shows no implausible flags: keep the
  implementation, add one short paragraph to `README.md` (near the existing
  `possible repeated take` explanation, around line 238) and to `SKILL.md`'s
  equivalent section describing the new note and its knobs. Comment on issue
  #32 is NOT in scope (no gh writes).
- If Step 3 shows implausible flags you cannot eliminate with the guards
  within a reasonable effort: revert the wiring (keep the pure function and
  tests marked `xfail` with a reason), and write `plans/009-spike-report.md`
  summarizing: what was tried, observed false-positive examples, and what
  signal is missing (this is a legitimate spike outcome).

**Verify**: `python -m pytest -q` → all pass; `python -m ruff check .` → clean.

## Test plan

Steps 1-2 above are the test plan: 3 positive cases from issue #32's own
examples, 3 negative guards. Model after existing tests in
`tests/test_pack_transcripts.py` (word-list construction style).

## Done criteria

Machine-checkable. ALL must hold (shipping outcome):

- [ ] `python -m pytest -q` exits 0; ≥6 new tests in `tests/test_pack_transcripts.py`
- [ ] `python -m ruff check .` exits 0
- [ ] `grep -n "restart_correction_note" helpers/pack_transcripts.py` → ≥2 matches (def + call site)
- [ ] `git status` shows only in-scope files changed; `examples/` untouched
- [ ] `plans/README.md` status row updated

OR (no-ship outcome): `plans/009-spike-report.md` exists with findings, tests
are `xfail` with reasons, suite green, index row set to BLOCKED with a
one-line reason.

## STOP conditions

Stop and report back (do not improvise) if:

- `repeated_delivery_note` or `group_words` no longer match the excerpts
  (drifted).
- Making the negative tests pass requires weakening a positive test — that's
  the false-positive wall; switch to the no-ship outcome instead of shipping
  a detector that over-flags.
- You need a new runtime dependency or semantic similarity model — out of
  scope by design; take the no-ship outcome and record it.

## Maintenance notes

- The thresholds (`min_overlap_words=2`, `max_restart_gap=1.5`, token ratio
  0.8) are guesses pinned by tests, not truths — tune via the tests, and note
  final values in the shipped docs.
- Portuguese is the primary user language here; `normalize_text` lowercases
  and strips punctuation but does not strip accents. Do not add accent
  folding without a test showing it's needed (Whisper output is generally
  accent-consistent within one recording).
- Future interaction: if `group_words`' `silence_threshold` default changes,
  the intra- vs cross-phrase split shifts; both detection branches must stay.
