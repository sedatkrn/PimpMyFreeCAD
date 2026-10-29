# Changelog

## Unreleased

- Round Rail Pipes (circle at both ends) are now built as a loft through circle sections placed along the guide
  with our own twist-free frame: r = 20 +- 0.025 mm, surface normals within 0.4 degrees, C2, about 50 control
  rows along the pipe instead of 210. The C1 sweep was accurate in position but its many small patches looked
  blotchy on screen. Thickness works; other profiles keep the C1 sweep.
- New pipes get a finer display tessellation (Deviation 0.05, AngularDeflection 5 degrees); FreeCAD's 28.5 degree
  default drew streaks on curved pipes. For older pipes set these two in the View properties.
- Rail Pipe works with **Thickness** (and other offsets) again: the pipe surface is built C1 (CorrectedFrenet with
  C1 approximation, max degree 3, 1000 segments, 1e-4 tolerance). The exact sweep without C1 left parametric C0
  joints at the guide points and OCCT refused to offset it ("BRep_API: command not done"); the default C1
  approximation was off by up to 4 mm. motor-test pipes: r = 20 +- 0.07 mm, 2 mm Thickness OK on all four.
- Rail Pipe in its own Body (option: checkable button in PartDesign's toolbar and the add-in's menu, also under
  *Options* in the task panel): each new pipe gets a new Body with its profiles bound by SubShapeBinders, so
  pipes no longer recompute and fuse together (motor-test pipe 1: 0.15 s).
- Rail Pipe in the Part workbench (button at the end of the Part Tools toolbar): a standalone Part solid outside any Body, profiles
  from any object read in global coordinates, no boolean (use Part Fuse / Cut). Same on-screen editing.
- A closed wire without a face (e.g. a SubShapeBinder of a sketch) works as a profile.
- Rail Pipe surface: the pipe is now exactly round along its whole length. The sweep first tries CorrectedFrenet
  without C1 approximation (the auxiliary-spine mode tilted the sections in bends: an r=20 pipe varied between
  16.8 and 20.4 mm and looked faceted); a circle end profile gets its seam aligned with the start profile (the
  two circles' seams were turned against each other and the pipe narrowed in the middle, 19.3 mm).
- Rail Pipe speed with several pipes in one Body: the boolean only involves the solids the new pipe really
  touches, and a new pipe that touches nothing no longer counts as a split result (that made every later pipe
  try all sweep modes with full booleans: motor-test pipes 2-4 took 8.6 / 10.6 / 20.5 s, now about 1-2 s).
- Documents made with FcSubDModelerWB's Rail Pipe copy (subd_railpipe) open with this add-in: their Rail Pipe /
  Groove objects are linked to it automatically (same properties); save the document to keep it.
- Renamed to **Pimp My PartDesign** (workbench, toolbar, menu, Addon Manager name). Command names, the `pda_`
  modules and documents made with 0.1.0 are unchanged; the language setting moved to
  `Preferences/Mod/PimpMyPartDesign`.
- Rail Pipe: a profile face that belongs to no solid (SubShapeBinder of a face, a lone face) no longer sends
  the pipe out of its back side: like a sketch, it leaves towards the other profile. A binder or sketch that
  lies on the Body's surface is treated like the Body's own face (outward, end carried into the body, so the
  fuse no longer splits or comes out empty). A single-face object picked in the tree is accepted.

## 0.1.0 (2026-10-29)

First release. Rail Pipe / Rail Groove moved here from FcSubDModelerWB.

- **Rail Pipe / Rail Groove**: PartDesign features (FeatureAdditivePython / FeatureSubtractivePython) that sweep a
  flat face or closed sketch along a guide curve to a second profile or a free end and fuse it into / cut it out
  of the Body. Properties: *GuidePoints*, *Tension*, *EndScale*, *Reversed*.
- On-screen guide editing (double-click): Move gizmo or direct drag, span selection with *Add point* at the
  clicked spot, *Delete point*, *Move neighbors* (cable) with *Elasticity*, X / Y / Z of the selected point,
  native PartDesign preview (green / red, translucent), fast preview while dragging, smooth sweep on release.
- Robust sweep: C1 guide spline, ends carried slightly past body faces, auxiliary spine for a wobble-free seam,
  fallbacks through several frame modes, boolean result checked by volume.
- Buttons in PartDesign's *Part Design Modeling Features* toolbar and a *PartDesign Add-ins* workbench.
  English / Turkish interface.
