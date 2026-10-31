# Pimp My PartDesign

Extra features for FreeCAD's **PartDesign** workbench. They are real PartDesign steps in a Body (like Pad or
Pocket): they recompute with the Body, later steps (fillets, pockets) build on them and the result exports to
STEP. The tools show up in PartDesign's own *Part Design Modeling Features* toolbar (next to Additive /
Subtractive Pipe) and in a small *Pimp My PartDesign* workbench.

Requires **FreeCAD 1.0 or newer** (developed on 26.3). No extra Python packages.

## Rail Pipe / Rail Groove

Sweeps a profile along a guide curve and adds it to the Body (**Rail Pipe**) or cuts it out (**Rail Groove**).

- **Profiles:** select one or two **flat faces**, **closed edges** (a circular edge or a closed flat loop) or
  **closed sketches** (click a sketch edge or pick the
  sketch in the tree). Two profiles: the start profile blends into the end profile. One profile: the pipe ends
  free; *EndScale* sizes the free end. An empty Body works too (the pipe becomes its first solid).
- **Guide curve:** leaves the start profile perpendicular and (with two profiles) enters the end profile
  perpendicular, passing through *GuidePoints*. *Tension* (0 smooth .. 1 straight between points) tightens it;
  uneven point spacing does not make it bulge. *Reversed* flips the start direction.
- **Edit on screen:** double-click the feature. The previous solid stays visible and the pipe is drawn as a light
  green (pipe) or red (groove) translucent mesh around the yellow guide curve. No solid is computed while you
  edit, so dragging stays fluid (~20 ms per step); the real, smooth pipe is computed once when you press **OK**.
  - Click a yellow point and move it with the **Move gizmo** (arrows: along X / Y / Z, squares: in a plane, cube:
    in the screen plane) or drag the point itself. The white end points belong to the profiles and stay put.
  - Click the curve to pick a span: *Add point* puts a point exactly where you clicked. *Delete point* removes the
    selected one.
  - *Move neighbors*: the guide follows the dragged point like a cable; *Elasticity* 0 = chain (lengths kept) ..
    1 = rubber band.
  - The task panel also has the selected point's X / Y / Z, *Tension*, *End scale* and *Reversed*.
  - **OK** computes the pipe and keeps the changes as one undo step, **Cancel** reverts them.
  - *Shell* (under *Options*) makes the pipe hollow with open ends and the given *Wall thickness*. Use this
    instead of PartDesign Thickness, which is unreliable on swept surfaces.
- **Several pipes, faster:** with *Rail Pipe in its own Body* switched on (checkable button next to Rail Groove,
  also under *Options* in the task panel) each new pipe gets its own Body; its profiles are bound with
  SubShapeBinders, so the pipes don't recompute and fuse together on every change. Fuse the Bodies later if you
  need one solid.
- **Part workbench:** the Rail Pipe button is at the end of the Part Tools toolbar. There the pipe is a standalone solid
  outside any Body (profiles can be faces or sketches of any object, read in global coordinates); add it to or
  cut it from a shape with Part Fuse / Cut. Editing on screen works the same way.

Limits of this first version: the profile is the start face's / sketch's outer outline (holes are ignored), no
scale per guide point yet.

## Magic Loft / Magic Loft Cut

A clean loft through two or more closed profiles, added to the Body (**Magic Loft**) or cut out (**Magic Loft Cut**).
It builds one low-pole surface instead of a dense sweep: fast, and made to take PartDesign Thickness and export to STEP.

- **Profiles:** select flat faces, closed sketches, Binders or closed edge loops; a loop may be **non-planar** (a parting
  line, for example). They are ordered automatically; *Up* / *Down* change the order. Seams and corners are matched
  automatically. For a section in the middle, select one more profile.
- **Guides:** open sketches or curves in the selection become guides, and each separate open chain in a sketch is one
  guide. A guide must touch every profile, otherwise the feature reports which one is how far away. With
  **Draw ready guides** on, automatic guides appear instead (4 by default, *Number of guides* changes it and rebuilds
  them); the selected guides stay in the list, unused, until you switch it off.
- **Start / end constraints:** *Free*, *Normal to profile* or *Tangent to face* per end, with a strength. An end on a
  solid's face starts as Normal, a sketch end as Free.
- **Edit on screen:** double-click the feature (the panel also opens right after creating one). Move the yellow points
  of the automatic guides with the Move gizmo, add and delete points, use *Move neighbors* (one point at a time).
  Ctrl+click selects several points, which move and delete together. Drag the green **connector** dots to fix a twist;
  they snap to edge ends and midpoints (hidden with selected guides, which set the matching themselves). While dragging you see a
  light mesh; on release the real surface; *Zebra* shows reflection stripes on it. The solid is computed on **OK**.
- **Guide influence:** how far a guide acts sideways. A larger value lifts a broader area instead of a narrow ridge
  (new features start at 2 x; features saved earlier keep 1 x, so their shape doesn't change until you raise it).
- **Part workbench:** a standalone solid outside any Body. *New Magic Lofts in their own Body* in the panel works like Rail Pipe's own
  option, but is set separately.

Limits: a **corner-to-round** transition (hexagon to circle) gets no wall from PartDesign Thickness and no error from it;
the feature warns about it. Cut the inside with a Magic Loft Cut from inset profiles instead. Close loft, a centerline,
curvature (G2) ends and open profiles are not available.

## Dome

Raises a flat face into a cap that runs tangent into the faces around it, like the Dome command in other CAD systems.
Select one flat face of a Body and press **Dome**. The panel has *Height*, *Reversed* (cut into the solid) and *Tangent to
steep walls*, and the real solid updates as you change them. **OK** keeps it as one undo step; **Cancel** reverts it and
removes a new feature. The panel shows the measured tangent error.

- **Vertical walls all around** (a plain Pad top, a cylinder end): the dome starts tangent to the walls and rises along a
  quarter ellipse, like a bullet. The surface is exact (0 degrees, exact height). Sharp corners run up to the top as ridges.
  It needs an outline fully visible from its centre and no holes. With *Tangent to steep walls* off you get a smooth bump
  instead, with a free slope at the walls.
- **Filleted top edges:** the neighbour is horizontal, so the surface starts flat and rises in a gentle S (under 0.01
  degrees). Curved, concave and sharp-cornered outlines and faces with holes work; the dome returns to the face level at
  every hole.

Limits:
- **Mixed edges and holes next to steep walls:** when only some neighbours are steep, or the face has a hole, those edges
  are not tangent. The edge stays sharp and the panel counts it.
- **Drafted walls:** the bullet shape starts straight up, so it is off by the draft angle (5.7 degrees on a 5.7 degree wall).
- **Slanted neighbours and low domes:** a chamfer needs enough height. A 45 degree chamfer on an 80 x 50 top is 29 degrees
  off at 4 mm and 3 degrees off at 15 mm.
- **Filleted curved edges:** the edge between the dome and its neighbour can fail OCCT's strict BOP check, although the solid
  is valid and exports to STEP. Booleans away from the rim worked in every test.
- **Thickness:** PartDesign Thickness works on smooth outlines. It failed or left the part unchanged on outlines with sharp
  corners.
- **Collisions:** a smooth bump that runs into another part of the solid falls back to a real boolean, which takes seconds.
- **Not available:** a peak moved off-centre with a point, and domes on curved faces.

## Installation

**Addon Manager (custom repository)**
1. *Tools → Addon manager → ⚙ (settings) → Custom repositories*, add
   `https://github.com/sedatkrn/partdesign_addins` with branch `main`.
2. Find **Pimp My PartDesign**, install, restart FreeCAD.

**Manual:** clone or unzip this repository into FreeCAD's user `Mod` folder and restart FreeCAD:
- Windows: `%APPDATA%\FreeCAD\<version>\Mod\PimpMyPartDesign`
- Linux: `~/.local/share/FreeCAD/<version>/Mod/PimpMyPartDesign`
- macOS: `~/Library/Application Support/FreeCAD/<version>/Mod/PimpMyPartDesign`

## Language

English by default, **Turkish** built in. `auto` (the default) follows FreeCAD's language; set
`Preferences/Mod/PimpMyPartDesign/Language` to `en` or `tr` to force one.

## For developers

[docs/OCCT_NOTES.md](docs/OCCT_NOTES.md) collects the OCCT / FreeCAD lessons behind Rail Pipe (sweep frames,
continuity, booleans, fast on-screen previews). Rail Pipe started in
[FcSubDModelerWB](https://github.com/sedatkrn/FcSubDModelerWB), where its guide curve mirrors the SubD modeler's
Rail bridge.

## License

MIT — see [LICENSE](LICENSE). Code comments are mostly in Turkish (the author's language); the user interface and
documentation are in English.

---

### Türkçe

FreeCAD **PartDesign** için ek özellikler. Body içinde Pad / Pocket gibi gerçek bir adım olarak çalışırlar;
araçlar PartDesign'ın *Part Design Modeling Features* araç çubuğunda ve küçük bir *Pimp My PartDesign*
workbench'inde görünür.

**Rail Pipe / Rail Groove:** bir ya da iki profil (Body'nin düz yüzü ya da kapalı sketch) seçip düğmeye basın.
Profil, yüzlerden dik çıkan bir kılavuz eğri boyunca süpürülür ve Body'ye eklenir (Pipe) ya da oyulur (Groove).
Özelliğe çift tıklayınca kılavuz ekranda düzenlenir: sarı noktayı gizmo ile ya da doğrudan sürükleyin, eğriye
tıklayıp *Nokta ekle* ile tam tıkladığınız yere nokta koyun, *Komşular da gelsin* ile kılavuz kablo gibi gelir.
Önizleme PartDesign'daki gibi yeşil / kırmızı yarı saydamdır. **Tamam** tek geri alma adımıdır, **İptal** geri alır.

**Sihirli Loft (Magic Loft) / Sihirli Loft Oyma:** iki ya da daha fazla kapalı profil seçin (düz yüz, kapalı sketch,
Binder, düzlemsel olmayabilen kapalı kenar halkası); seçimdeki açık eğriler rehber olur. *Hazır rehber çiz* açıkken
otomatik rehberler oluşur ve ekranda düzenlenir, seçili rehberler saklanır ama kullanılmaz. Uçlar *Serbest*, *Profile
dik* ya da *Yüzeye teğet* olabilir. Yeşil connector noktaları burulmayı düzeltir, *Zebra* yüzey kalitesini gösterir.
Köşeliden yuvarlağa geçişte PartDesign Thickness et vermez; içini Sihirli Loft Oyma ile boşaltın.

**Kubbe (Dome):** bir Body'nin düz yüzünü seçip düğmeye basın, *Yükseklik* verin; yüz, kenarlarda komşu yüzlere teğet bir
kubbeye dönüşür, *Ters* katının içine oyar. Dört yanı dik duvarsa kubbe duvarlara teğet başlar (mermi biçimi), keskin
köşeler tepeye sırt olarak gider. Fillet'li kenarda düz başlar; iç bükey çizgi ve delikli yüz de çalışır.
