# Simple Cut Example

This example removes a pause and repeated phrase from a short talking-head
recording. The source media is intentionally omitted; `raw/interview.mp4` is the
expected local path if you want to validate or export the sample EDL.

Useful files:

- `edit/media_index.json`: example output from `vtc inventory`.
- `edit/transcripts/interview.json`: compact transcript with word timestamps.
- `edit/takes_packed.md`: reading surface for the agent.
- `edit/edl.json`: final structured edit decision list.

Expected result: a 13.5 second timeline made from two spoken ranges, with the
silent gap removed.
