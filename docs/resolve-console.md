# Resolve Console Recipes

Use these recipes for small fixes after importing a timeline into DaVinci Resolve
when no Resolve MCP or external scripting is available. Verified on DaVinci
Resolve 21 Free (Windows) in October 2026.

## Opening The Console

- **Workspace > Console**. Lua is the default language.
- The input field takes one line, so write each command as a single line.
- Use the `resolve` global (the app object). In one session the chain starting
  with `Resolve()` failed with "attempt to index a nil value".
- Output can take a few seconds to appear.
- Read the timeline name and track contents first. Change only the timeline the
  user named, then save with **Ctrl+S**.

## Gotcha

`GetItemListInTrack()` returns a table that also contains a numeric entry, so
calling a method on every value fails with "attempt to index local (a number
value)". Skip it with `type(x) ~= 'number'`.

## Inspect Tracks

```lua
tl=resolve:GetProjectManager():GetCurrentProject():GetCurrentTimeline(); print(tl:GetName(), tl:GetTrackCount('audio')); for t=1,tl:GetTrackCount('audio') do local c=0; local nm={}; for _,a in pairs(tl:GetItemListInTrack('audio',t)) do if type(a)~='number' then c=c+1; nm[a:GetName()]=true end end; local s=''; for k in pairs(nm) do s=s..k..'; ' end; print(t, tl:GetTrackName('audio',t), c, s) end
```

## Link Each Video Clip To Its Audio

Resolve imports separately recorded audio, exported as connected `lane="-1"`
clips, without a link to the video. Trimming the video then leaves the audio
untouched. This recipe links every V1 item to each audio item that overlaps it
by more than half of the shorter clip:

```lua
A={}; for t=1,tl:GetTrackCount('audio') do for _,a in pairs(tl:GetItemListInTrack('audio',t)) do if type(a)~='number' then A[#A+1]={a,a:GetStart(),a:GetEnd()} end end end; n=0; nv=0; for _,v in pairs(tl:GetItemListInTrack('video',1)) do if type(v)~='number' then nv=nv+1; local vs,ve=v:GetStart(),v:GetEnd(); for _,x in ipairs(A) do local ov=math.min(ve,x[3])-math.max(vs,x[2]); if ov>0.5*math.min(ve-vs,x[3]-x[2]) then if tl:SetClipsLinked({v,x[1]},true) then n=n+1 end end end end end; print('audios',#A,'videos',nv,'links',n)
```

Expect `links` to equal the number of video items times the number of audio
tracks that carry a matching clip.

## Export The Open Timeline

Use this to read the user's manual adjustments (trims, deleted clips) before
continuing an edit. No file dialog is needed:

```lua
tl=resolve:GetProjectManager():GetCurrentProject():GetCurrentTimeline(); print(tl:GetName(), #tl:GetItemListInTrack('video',1)); print(tl:Export('D:\\path\\to\\edit\\current.fcpxml', resolve.EXPORT_FCPXML_1_8, resolve.EXPORT_NONE))
```

Resolve writes linked video and separately recorded audio as a `<clip>` that
holds a `<video>` element plus a nested `<clip lane="1">` with an `<audio>`
element. Read the clip `start` (source time) and `duration` from the outer
`<clip>`.

## Import A Timeline

Import generated FCPXML through **File > Import > Timeline…** with
**Automatically import source clips into media pool** and **Automatically set
project settings** unchecked. That links the timeline to the masters already in
the Media Pool.

Do not use `MediaPool:ImportTimelineFromFile(path, {importSourceClips=false})`
for this. In Resolve 21 Free it imported every clip as **Media Offline**
instead of linking to the existing masters.

Links between video and separately recorded audio do not survive a round trip.
Re-importing Resolve's own exported `<clip>` + nested audio structure still
gave unlinked clips. Run the link recipe after every import.

## Punch-Ins On An Open Timeline

`vtc punch-ins edl.json --lua punch_ins.lua` writes one console line that sets
`ZoomX`, `ZoomY`, `Pan` and `Tilt` on each V1 clip, in timeline order. Duplicate
the user's timeline first, make the duplicate current, then run the line:

```lua
p=resolve:GetProjectManager():GetCurrentProject(); z=p:GetCurrentTimeline():DuplicateTimeline('My timeline (zoom)'); p:SetCurrentTimeline(z)
```

Units seen in Resolve 21: `Pan`/`Tilt` are timeline pixels and negative `Tilt`
moves the image down (verified). `Pan` is assumed to follow the same convention
(negative moves left); check one clip before trusting it. Variables declared
with `local` vanish after each console line, so use globals for objects that
you reuse across lines. The scripting API has no keyframe calls, so animated
(slow) zooms need the Inspector or Dynamic Zoom by hand.

## Remove The Muted Camera-Audio Track

Run this only after the inspect recipe confirms which track holds the camera
audio (the clip names are the video files). The example uses track 1:

```lua
D={}; for _,a in pairs(tl:GetItemListInTrack('audio',1)) do if type(a)~='number' then D[#D+1]=a end end; print('delete', #D, tl:DeleteClips(D, false)); print('track', tl:DeleteTrack('audio',1)); print('audio tracks', tl:GetTrackCount('audio'))
```

Links between the video and the remaining audio survive the deletion.

## Fusion Titles (Call-Outs, Lower Thirds)

Do not use `Timeline:InsertFusionTitleIntoTimeline(name)` on an edited
timeline. In Resolve 21 it does a ripple insert on V1 near the playhead, so
every clip after it moves by the title's length (5 s). Undo with **Ctrl+Z** in
the main window, then export the timeline and compare it with an export from
before.

To place a title template (for example the user's own call-outs under
**Titles** in the Effects library):

1. Console: `tl:SetCurrentTimecode(tc)` to put the playhead on the word. The
   timecode base is 60 for a 59.94 NDF timeline: frame `n` is
   `string.format('%02d:%02d:%02d:%02d', h, m, s, n % 60)`.
2. Drag the title from the Effects library onto an empty upper track and
   drop it right at the playhead. Snapping puts the start on the playhead.
3. Console: list the track's items and check `GetStart()`.

Before typing in the Console, check that its input line is focused. If the
Console window is hidden, keystrokes go to the main window, where letters are
editing shortcuts (one stray key placed a media pool clip on V2).

A reusable component saved as a `.drt` (for example a members list) imports
with `mp:ImportTimelineFromFile(path, {importSourceClips=false})`. That makes
the imported timeline current, so switch back with `pr:SetCurrentTimeline(tl)`.
Then place its compound clip from the bin with `AppendToTimeline` on an upper
track.

### Resizing Or Moving A Title That Slides Off Screen

A Transform added after the last node of a title (to make it smaller or move
it) also moves the off-screen positions its elements slide to. An element that
left the 1.0 frame edge before now stops inside the frame and stays visible
after the animation ends. With pivot 0.5, `Size` S and `Center` (Cx, Cy), the
visible frame edges in the title's own coordinates are
`right = 0.5 + (1 - Cx) / S`, `top = 0.5 + (1 - Cy) / S` and
`bottom = 0.5 - Cy / S`. Push every off-screen keyframe out by the same amount
(for example `1.099 + (right - 1)` plus a small margin) and scale its Bezier
handles about the rest value, so the ease keeps its shape. A crop to the frame
before the Transform is no fix: the elements then vanish at a hard vertical
line in the middle of the picture.

On titles already on the timeline, change the splines through the Fusion API:
`xf.Center:GetConnectedOutput():GetTool()` is the XYPath and its
`X:GetConnectedOutput():GetTool()` the BezierSpline, then
`spline:SetKeyFrames(table, true)`. In that table the `LH`/`RH` handles are
offsets from their keyframe, not the absolute values that the `.setting` file
stores; passing absolute values bends the curves (the element drifts while it
should rest). Read back `tool.Center[frame]` at several frames and compare
with the curve evaluated from the file before checking pictures. The Console
has no `dofile` or `io`, so paste longer scripts as one line.

The viewer and `GrabStill` can lag a seek by one frame when a Fusion title is
slow to render. Wait about 6 s after each seek before grabbing.
