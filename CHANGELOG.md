# Changelog

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
