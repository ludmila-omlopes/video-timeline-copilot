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

## Remove The Muted Camera-Audio Track

Run this only after the inspect recipe confirms which track holds the camera
audio (the clip names are the video files). The example uses track 1:

```lua
D={}; for _,a in pairs(tl:GetItemListInTrack('audio',1)) do if type(a)~='number' then D[#D+1]=a end end; print('delete', #D, tl:DeleteClips(D, false)); print('track', tl:DeleteTrack('audio',1)); print('audio tracks', tl:GetTrackCount('audio'))
```

Links between the video and the remaining audio survive the deletion.
