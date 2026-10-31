# Talking-Head Finishing In Resolve

Steps that live in DaVinci Resolve itself rather than in the EDL or FCPXML.
Verified on DaVinci Resolve 21 Free (Windows) in October 2026 on a fixed-camera
3840x2160 talking head.

## Light Background Blur

Goal: keep the speaker sharp and soften the room slightly. Applying it once to
the whole timeline covers every clip, including later edits.

Resolve Free has no person segmentation (Magic Mask and Depth Map are Studio
features), so use a soft inverted window:

1. Work on a duplicate of the user's timeline, never on the original.
2. **Color** page. In the node editor, switch the dropdown from **Clip** to
   **Timeline**. The node graph is empty.
3. Click the node editor and press **Alt+S** to add a corrector node.
4. **Window** palette: enable the **Circle** window and type the values:
   - `Pan`/`Tilt` place the center. 50/50 is the frame center; a higher `Pan`
     moves it right and a lower `Tilt` moves it down. Center it on the
     speaker's face and upper torso, slightly below the eyes.
   - `Size` and `Aspect`: a tall ellipse (`Aspect` below 50) that covers the
     head with some headroom and runs past the bottom of the frame. The window
     scale is not linear: on the reference shot, `Size` 50 was about a third of
     the frame width and `Size` 75 already overflowed the frame.
   - `Soft 1` around 12 so the transition is invisible.
   - Reference values from the "Cores" shot (face at x 0.55, eyes at y 0.33):
     `Size` 56, `Aspect` 38, `Pan` 52.4, `Tilt` 48.6, `Soft 1` 12.
5. Click the window's **Invert** toggle (the first icon at the right of the
   window row) so the correction affects the outside.
6. **Blur** palette: `Radius` 0.62 with the channels linked (0.50 means no blur).
   Stay between 0.58 and 0.70 for a "light" blur.
7. Turn the viewer overlay off (bottom-left of the viewer, **Off**) to judge
   the result. Check a wide, a medium and a close punch-in clip, then set the
   overlay back to **Power Window**.
8. Save the project (**Ctrl+S**).

Why a timeline node works with punch-ins: `vtc punch-ins` keeps the speaker's
eyes at the same screen position at every zoom level, so one window stays
aligned. At the closest level, the edges of hair and shoulders can touch the
soft edge; widen `Size` slightly if they look soft.

Limits to tell the user: the window does not follow movement. If the speaker
leans far out of it, that part softens too. With Resolve Studio, prefer a
**Magic Mask** (Person) on a clip node with the blur outside the mask, or the
**Depth Map** effect.

To remove the effect, disable or delete the timeline node.

Before adding B-roll on V2, move this node to the V1 clips: a timeline node
also blurs the B-roll. See `docs/resolve-broll.md`, step 5.
