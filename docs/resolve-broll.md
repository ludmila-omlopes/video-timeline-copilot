# B-Roll Over A Talking Head In Resolve

How to cover an edited talking-head timeline with B-roll on V2. Verified on
DaVinci Resolve 21 Free (Windows) in October 2026 on a 17-minute, 3840x2160,
59.94 fps edit with 52 B-roll shots.

## 1. Pick Where B-Roll Goes

Work from the transcript of the delivered edit (`vtc qa-transcript` writes
`edit/qa/transcript_readout.md` with record times per range).

- Cover a sentence when it names something the viewer can see: a game, a film
  scene, an artwork, a place, an object, a menu, a statistic shown on screen.
- Keep the speaker on screen for personal opinions, asides, jokes, calls to
  action and the first line of a new section. Cutting back to the face gives
  the B-roll rhythm.
- Start and end each shot on a range boundary (a sentence start or a cut), so
  B-roll changes never land mid-word.
- 3-8 s per shot. Split longer passages into two or three shots that follow
  the narration (for example "green area / dark area / green / dark" while the
  speaker contrasts two places).
- Avoid text in the B-roll (review scores, logos, captions, end cards) unless
  the text is the point.

## 2. Gather Sources

1. Ask whether the user has a B-roll folder and look there first.
2. Put anything downloaded in a dedicated folder inside the project (for
   example `<project>/brolls/`), never mixed with the raw footage.
3. Useful sources for game videos: the Steam store API
   (`store.steampowered.com/api/appdetails?appids=<id>` lists trailer HLS
   URLs; `ffmpeg -i <m3u8> -c copy -bsf:a aac_adtstoasc out.mp4`), and
   `yt-dlp` with `--download-sections "*mm:ss-mm:ss"` and an H.264 format
   (`bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]`) so Resolve Free decodes it.
   Use what the user is allowed to use; ask when unsure.
4. Make a contact sheet per source before choosing in/out points:
   `ffmpeg -i src.mp4 -vf "fps=1/3,scale=320:-1,tile=6x8" -frames:v 1 sheet.jpg`.

## 3. Pre-Render Each Shot

Render every planned shot as its own clip instead of cutting the original
sources inside Resolve:

- same frame rate as the timeline, 1920x1080 or the timeline size, scaled to
  cover (`scale=W:H:force_original_aspect_ratio=increase,crop=W:H`), no audio;
- 1 s handles before and after the used range, so the user can still trim;
- stills become motion: a slow push-in (`zoompan` on a 2x upscale to avoid
  jitter) or, for a portrait image in a landscape frame, a slow tilt with a
  moving `crop`.

This avoids source-frame-rate arithmetic in the API, fixes odd aspect ratios
and low-resolution sources once, and turns stills into video. Then render one
check sheet with the first, middle and last used frame of every shot and fix
black frames, fades, title cards and text overlays before touching Resolve.

## 4. Place On V2 From The Console

Duplicate the user's timeline first (`tl:DuplicateTimeline(name)`, then
`project:SetCurrentTimeline`). The timeline switch takes keyboard focus away
from the Console: click the Console input again before typing the next line.

```lua
mp=pr:GetMediaPool(); fo=mp:AddSubFolder(mp:GetRootFolder(),'B-roll'); mp:SetCurrentFolder(fo)
its=mp:ImportMedia(paths); M={}; for _,it in ipairs(its) do M[it:GetName()]=it end
if tl:GetTrackCount('video')<2 then tl:AddTrack('video') end
-- P = {{file, head_frames, record_start_frame, record_end_frame}, ...}
CI={}; for _,p in ipairs(P) do CI[#CI+1]={mediaPoolItem=M[p[1]], startFrame=p[2],
  endFrame=p[2]+(p[4]-p[3]), trackIndex=2, recordFrame=p[3], mediaType=1} end
print(#mp:AppendToTimeline(CI))
```

- `endFrame` is exclusive: `startFrame + duration`, not `- 1`.
- `recordFrame` is absolute timeline frames (`tl:GetStartFrame()` is usually
  0 for an imported FCPXML timeline, 86400 or 108000 for others).
- `mediaType=1` places video only.
- Snap record frames to the nearest V1 clip boundary (within 3-4 frames) so
  rounded transcript times do not leave one-frame slivers.
- Verify after placing: compare every V2 item's `GetStart()`/`GetEnd()`/
  `GetName()` with the plan and print mismatches.

## 5. Move A Timeline-Level Blur To The Clips

A timeline node (for example the light background blur from
`docs/resolve-talking-head.md`) also processes V2, so the B-roll gets the
inverted-window blur. Move it to clip level on V1:

1. **Color** page, playhead on a talking-head clip with no B-roll above it.
2. Node editor in **Timeline** mode: select the node, **Ctrl+C**.
3. Switch to **Clip** mode, select node 01, **Ctrl+V**.
4. Back to **Timeline** mode, select the node, **Delete**.
5. Console: copy that clip's grade to every other V1 clip:

```lua
-- src = the V1 clip that now holds the grade
V={}; for _,v in pairs(tl:GetItemListInTrack('video',1)) do if type(v)~='number' and v~=src then V[#V+1]=v end end
print(src:CopyGrades(V))
```

At clip level the window follows each clip's punch-in zoom, so it stays on the
speaker at every framing. Check one wide, one close and one B-roll frame.

## 6. Hand Off

Save (`pm:SaveProject()`), export an FCPXML backup of the new timeline, and
tell the user which passages got B-roll, which stayed on the speaker, where
the shot files and the plan live, and which sources were downloaded.
