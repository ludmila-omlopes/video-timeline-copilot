# Editor Handoff

Delivering to DaVinci Resolve, Premiere Pro, Final Cut Pro, or an unknown editor, and what each path can and cannot carry.

## Choosing The Path

- For DaVinci Resolve, offer optional integration to import and inspect the
  timeline when the user wants to work in Resolve. Use an available compatible
  MCP; if none is connected and the user wants one, follow the optional setup
  in `install.md` (beside `SKILL.md`, and in the repository). Do not make setup a
  condition of delivery.
- For Adobe Premiere Pro, deliver the cuts-only FCP7 XML from `vtc export-xml`
  (Premiere does not read FCPXML). It carries cuts, order, stills, muted clips,
  linked audio, and markers. It does not carry zoom/pan/tilt, `visual_layers`,
  or speed changes; the command lists every range whose framing was left
  behind, and refuses retimed ranges. Tell the user what to reapply.
- For Final Cut Pro or another editor, deliver FCPXML and relevant import
  guidance. Check that the specific editor and requested features support it;
  do not promise compatibility or a native project without evidence. Do not
  offer Resolve MCP setup for another editor unless the user requests it.
- For an unknown or unsupported editor, explain the compatibility uncertainty
  and offer the EDL, SRT, and FCPXML as available artifacts; do not claim a
  successful import.

At handoff, distinguish what was generated, imported, checked for media links,
and visually inspected. Report any unverified or failed steps explicitly.

Early in each session, check whether DaVinci Resolve is running on the computer
that holds the working media, using a read-only process or app inventory when
available. Do this even if another editor is selected, but do not launch
Resolve or offer its integration solely because it is running. A running process
does not prove that scripting, MCP, or a project is connected; check those
separately when needed. Do not use an MCP call that automatically launches
Resolve as a running-state check. If the process state cannot be observed, say
it is unknown rather than assuming it is open or closed. If Resolve is the
destination and is not running, tell the user and, if they want live handoff,
help them open it; continue independent preparation or manual FCPXML delivery
as appropriate.

When the user asks to edit a timeline that is already open in Resolve, export
it first (**File > Export > Timeline**, FCPXML 1.8 `.fcpxml`, not the
`.fcpxmld` bundle) and read its structure before planning: compound clips, the
offsets and `timeMap` sync of separately recorded audio, muted camera audio,
and cuts the user already made. Treat earlier manual cuts as editorial intent
(they show which takes the user prefers), express new ranges against the
original media, and deliver a new timeline. Never modify the user's timeline.
See the `fcpxml-audio` guide for flattening compound clips.

## Resolve Caveats

DaVinci Resolve's scripting API is strongest at project creation, media import,
timeline creation, timeline item property changes, markers, project export, and
project archive. Subtitle automation varies by Resolve version. Always generate
SRT as a stable handoff artifact even when trying to import subtitle tracks.

Retimed ranges are supported by the FCPXML exporter/importer, not by the Resolve
scripting backend. If the EDL contains `speed` or `record_duration`, export
FCPXML and import it into Resolve instead of using `build-resolve-project` or
`update-resolve-timeline`.

`vtc update-resolve-timeline` works against an existing Resolve project. It
rebuilds EDL timelines in that project; it does not live-edit individual clips
inside the currently selected timeline. If `--replace-existing` is used and
Resolve refuses to delete an active timeline, create a uniquely named timeline
first or switch to another timeline before retrying.

DaVinci Resolve Free may not expose external scripting. Its in-app Console
(**Workspace > Console**, Lua) does run the scripting API against the open
project; use it for small post-import fixes such as linking clips or removing a
track (the `resolve-console` guide). Some MCP servers offer
an in-app bridge depending on the Resolve version and setup; consult the
available server's instructions rather than assuming it works. If no suitable
integration is available, deliver validated EDL, SRT, and FCPXML and tell the
user how to import the FCPXML manually.

## What Each Path Carries

| EDL feature | FCPXML (`export-fcpxml`) | FCP7 XML (`export-xml`) | Resolve scripting (`build-resolve-project`) |
|---|---|---|---|
| Cuts and order | yes | yes | yes |
| Zoom / pan / tilt | yes | no, listed as a warning | yes |
| `visual_layers` | yes | no, listed as a warning | no, refuses |
| `speed` | yes, editable | no, refuses | no, refuses |
| Still images | yes | yes | no, refuses |
| `mute` | yes | yes | no, refuses |
| Markers | no | yes | yes |

FCPXML is the default for Resolve and Final Cut. Stills and muted clips in
FCPXML are covered by automated structure tests but have not been confirmed in
every editor version: after the first import of a cut that uses them, check that
the still appears for its full hold and that the muted clip is silent, and say
so at handoff.

## Mixed Frame Rates

`vtc export-fcpxml` warns when a source's native frame rate differs from the
timeline's. That is legal, and usually imports fine. If Resolve brings such
clips in offline or out of sync, re-export with `vtc export-xml`, which states
each file's own rate, and import that `.xml` instead. Tell the user why the
file type changed. Do not switch to the fallback when no warning or import
problem occurred.

## Import Step To Give The User

- DaVinci Resolve: **File > Import > Timeline**, then choose the `.fcpxml`
  (or the `.xml` when the fallback was used). Follow the Media Pool import
  options in the `session` guide, step 10.
- Adobe Premiere Pro: **File > Import**, then choose the `.xml`.
- Final Cut Pro: **File > Import > XML**, then choose the `.fcpxml`.

Offer to open the timeline file for them. On macOS, `open -a "DaVinci Resolve"
<file>` (or `"Final Cut Pro"`, `"Adobe Premiere Pro"`) hands it to the right
application. On Windows, editors import these files rather than open them, so
reveal the file in Explorer instead (`explorer /select,"<file>"`) and repeat
the import step. Do either only when the user wants it, and remember the answer
with `vtc preferences --add-note`.
