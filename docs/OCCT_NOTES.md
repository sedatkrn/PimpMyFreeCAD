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
    **But** in bends the sections are no longer perpendicular to the spine (the aux curve's arc length differs
    from the spine's): measured on the motor-test pipes an r = 20 mm pipe varied 16.8 .. 20.4 mm and looked faceted,
    while CorrectedFrenet without C1 approximation was exactly 20.000 mm. Rail Pipe now tries CorrectedFrenet first.
  - **Seams of round profiles.** A circle is one closed edge: its seam (vertex) cannot be moved by reordering
    edges. If the start and end circles' seams are turned against each other, a two-section sweep twists between
    them and narrows in the middle (hyperboloid waist, 19.3 mm on r = 20). Rebuild the end circle as
    `Part.Edge(curve, u, u + period)` with `u = curve.parameter(target)` (keep the edge orientation).
  - Measure sweeps by the distance of surface samples to the spine edge (`edge.distToShape(Part.Vertex(p))`): a
    round pipe must give its radius everywhere.
  - `setBiNormalMode(plane normal)` works for planar and straight guides, but is sometimes invalid with two
    profiles in a bend. Use it as a fallback.
- **Offsets need C1.** CorrectedFrenet without C1 approximation is exactly round but leaves parametric C0 joints at
  the guide's knots (the frame depends on curvature, which jumps at the C1 knots of the guide); `makeThickness` /
  PartDesign Thickness then fail with "BRep_API: command not done". Splitting the face at those knots does not
  help, neither does knot removal. Use `setForceApproxC1(True)` **with** `setMaxDegree(3)`,
  `setMaxSegments(1000)`, `setTolerance(1e-4, 1e-4, 1e-2)`: C1, r = 20 +- 0.07 mm (defaults: off by up to 4 mm),
  ~0.1 s. Interpolating a C2 guide through samples wiggled and was worse.
- **Round pipes: loft instead of sweep.** Place circle sections along the guide with an own rotation-minimizing
  frame (product of minimal rotations between tangents, ~12 sub-steps per station, at least 48 stations, seam
  carried along) and `Part.makeLoft(sections, True, False, False, 5)`: r = 20 +- 0.025 mm, normals within 0.4
  degrees, C2, 15 x 51 poles, offsets work. The C1 sweep (15 x 210 poles) was right in position but rendered
  blotchy. A loft between ellipses of different size failed in `makeThickness`, so only circles use it.
- **Judge quality by normals and on screen**, not only by distance to the spine: compare `normalAt` with the
  direction from the nearest spine point. Also lower the display tessellation (AngularDeflection 28.5 deg default
  draws streaks on curved pipes; 5 deg and Deviation 0.05 look smooth).
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
- **Several features in one Body.** Boolean only with the Body's solids the tool really touches (bounding box
  overlap, then `distToShape` = 0, ~0.3 s per solid) and keep the rest as they are. A tool that touches nothing
  becomes one more solid: count that as a clean result, not as a split. Fusing every new pipe with the whole
  growing Body (plus refine and the volume check) took 8.6 / 10.6 / 20.5 s for pipes 2-4; now about 1-2 s.

- **Fuzzy booleans for near-coincident ends.** A fitted loft end on a body edge is off by ~0.01 mm. `fuse(tool)` then took
  500 ms and gave 20-32 faces, sometimes invalid; `fuse(tool, 1e-3)` took 40 ms, 4 faces after refine, valid, Thickness
  OK, volume right. Pass the same tolerance to `common` in the volume check, which was as slow otherwise.

## Thickness

- **It can do nothing silently.** On a corner-to-round loft (hexagon to circle) `makeThickness` returns the input
  unchanged at 1.5 mm and raises at 0.5 mm; PartDesign Thickness shows Up-to-date with no wall. Same with `makeLoft`
  surfaces. Hexagon to hexagon works; an inner loft from inset profiles + cut works.
- **`Shape.Volume` is unreliable on its result** (`GeomOffsetSurface`): 10925..13098 for one geometry, while the volume of
  `tessellate()` gave 12913..12920. Compare tessellated volumes.

## Direct lofts (Magic Loft)

- A surface computed with numpy and fitted to one cubic B-spline (`buildFromPolesMultsKnots`) beat `makeLoft` where it
  matters here: valid on a non-planar section where `makeLoft` was invalid, 24-48 x 8-13 poles whatever the profile's
  own pole count (`makeLoft` gave 867 x 2 for a 72-point spline, but 15 x 2 for a true ellipse), about 10 ms.
- Check the fit in **both** directions. A fixed 12 rows along the loft left the surface 0.50 mm off a guide with a 0.02 mm
  tolerance (user test file, guides with a tight end). Growing the rows until the error is under the tolerance gave 27
  rows and 0.004 mm, still about 40 ms.
- A piecewise-linear parameter map leaves a speed kink the fit can never absorb: the pole count hit its cap (128) at
  every tolerance. A smooth map through the same keys needed 96 at 0.02 mm and 48 at 0.1 mm.
- A periodic surface's basis is easiest to get right by probing: build a curve with one unit pole and read its values.
- An end tangent must be applied at the real end. An overlap span along the section normal bent the surface away from
  the adjacent face (29 degrees on a cone); without the span the normals matched to 0.00.
- `Part.Solid` from `Part.Shell([surfaces, caps])` after `sewShape()` works when the caps are built from the surface's
  own `vIso` edges.

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
