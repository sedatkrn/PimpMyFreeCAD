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
