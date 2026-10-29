# OCCT / FreeCAD notes

Lessons measured while building Rail Pipe on FreeCAD 26.3 (OCCT via the Python `Part` module). They apply to
any sweep, boolean or interactive PartDesign tool in this repository.

## Sweeps (`Part.BRepOffsetAPI.MakePipeShell`)

- **Guide spline continuity.** Build the guide from Hermite spans as one cubic B-spline (Bezier poles per span),
  with knot spacing equal to each span's chord length, then `removeKnot(i, 2, tol)` on the inner knots. With
  multiplicity 3 the curve is only parametrically C0: the BOP check reports `GeomAbs_C0` edges / faces and later
  booleans can break. Scaling inner tangents by the span length (`2 l_i / (l_{i-1} + l_i)`) both removes the
  bulge after a long span followed by a short one and makes the joints C1 with chord-length knots.
- **Frame mode.**
  - `setFrenetMode(False)` (CorrectedFrenet) lets the cross-section wobble a few degrees around the tube: the seam
    and edge lines look kinked (~2 mm on r = 40 mm). On a straight line it is undefined
    (`BRepAdaptor_Curve::No geometry`).
  - `setAuxiliarySpine(aux, True, 0)` with `aux` = a curve through *spine + side vector of our own
    rotation-minimizing frame* fixes the wobble (~0.1 deg). Use **CurvilinearEquivalence = True** only: `False`
    sometimes hangs for more than a minute. Try the side vector at 1x and 2x the profile size.
  - `setBiNormalMode(plane normal)` works for planar and straight guides, but is sometimes invalid with two
    profiles in a bend. Use it as a fallback.
- **`setForceApproxC1(True)`** avoids C0 faces, but together with two profiles it can fling the control poles.
  `Shape.BoundBox` is computed from the poles, so check sanity with `Shape.optimalBoundingBox()` instead.
- A swept solid can come out **inside-out**: test `isInside(spine midpoint)` and `reverse()` it.
- **Ends on body faces.** A sweep that ends exactly on a body face leaves tiny edges and self-intersecting
  vertices after the fuse. Extend the spine ~0.5 mm past the face with a straight span (C1 with chord-length
  knots) and move the profile there.

## Booleans

- Validate the result **by volume**: fuse = body + tool − common, cut = body − common. A sweep that passes
  `isValid()` can still lose the tool in the boolean.
- `Shape.check(True)` (BOP check) can take **25 s** on a sharp bend; don't call it inside a recompute.

## PartDesign Python features

- `PartDesign::FeatureAdditivePython` / `FeatureSubtractivePython`: read `BaseFeature.Shape`, set `AddSubShape`
  and `Shape`. The `Refine` property already exists (adding it again raises).
- The view provider (`PartDesignGui::ViewProviderPython`) has the native Pad / Pocket preview:
  `showPreview(True)`, `updatePreview()`, `PreviewColor` (add (0, 1, 0.6), cut red). While editing: object
  `Transparency` 100 and `DisplayMode` "Shaded" (its own edges z-fight with the preview's), base feature visible.
- Put commands into another workbench's toolbar with `Gui.addWorkbenchManipulator` and
  `modifyToolBars()` returning `[{"append": cmd, "toolBar": "Part Design Modeling Features"}]`.
- Default `Deviation` 0.5 makes curved sweeps look lumpy; 0.1 is a better default.

## Fast on-screen editing

- While dragging, sweep only the tool in the fast mode, set `AddSubShape` and call `updatePreview()`. Skip the
  boolean, refine, the inside-out test and the tight bounding box. Use a coarse `Deviation` (0.5) and don't call
  `Gui.updateGui()` in the timer. This took a drag step from 0.26 s to 0.05 s. Do the full recompute on release
  (`obj.touch()` first).
- Coin can lose the button-release event: in the motion callback check `QApplication.mouseButtons()` and end the
  drag there.
- When gizmo handles overlap other points, pick points first and the gizmo second.

## Testing

Run heavy or experimental OCCT loops in a **separate `freecadcmd` process**
(`freecadcmd script.py --pass args`), never in a live FreeCAD session: a slow sweep there freezes the GUI and
unsaved work can be lost. `doc.saveCopy(path)` gets a user's geometry out without touching their document.
