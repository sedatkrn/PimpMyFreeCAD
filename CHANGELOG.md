# Changelog

## Unreleased

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
