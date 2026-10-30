# -*- coding: utf-8 -*-
# Pimp My PartDesign - FreeCAD commands (toolbar / menu). Copyright (c) 2026 Sedat Kuran - MIT License
import os

import FreeCAD as App
import FreeCADGui as Gui

from pda_i18n import T

ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
ICON = os.path.join(ICONS, "pda_addins.svg")


class _RailPipe:
    """PartDesign Body'de Rail Pipe (ekler) / Rail Groove (oyar): secili bir ya da iki profil (duz yuz ya da kapali
    sketch) arasinda kilavuz egri boyunca supurme (pda_railpipe)."""

    def __init__(self, subtractive):
        self.sub = subtractive

    def GetResources(self):
        if self.sub:
            return {"Pixmap": os.path.join(ICONS, "pda_railgroove.svg"), "MenuText": T("Rail Groove"),
                    "ToolTip": T("PartDesign: cut a groove along a guide curve from a flat face or closed sketch (and "
                                 "to a second one). Edit GuidePoints, Tension and EndScale in the property view")}
        return {"Pixmap": os.path.join(ICONS, "pda_railpipe.svg"), "MenuText": T("Rail Pipe"),
                "ToolTip": T("PartDesign: add a pipe along a guide curve from a flat face or closed sketch to a "
                             "second one or a free end. Edit GuidePoints, Tension and EndScale in the property "
                             "view")}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        import pda_railpipe
        prof = []               # (nesne, "FaceN"), kapali kenarlar icin (nesne, ["EdgeN", ...]), sketch icin (sketch, None)
        for so in Gui.Selection.getSelectionEx():
            if pda_railpipe._is_sketch(so.Object):        # sketch: kenarina tiklanmis ya da agacta secili
                if all(p[0] is not so.Object for p in prof):
                    prof.append((so.Object, None))
            elif so.SubElementNames:
                prof += [(so.Object, sub) for sub in so.SubElementNames if sub.startswith("Face")]
                prof += _edge_profiles(so)
            elif hasattr(so.Object, "Shape") and len(so.Object.Shape.Faces) == 1:
                prof.append((so.Object, "Face1"))           # agacta secilen tek yuzlu nesne (or. Binder)
        if not 1 <= len(prof) <= 2:
            App.Console.PrintWarning(T("Rail Pipe: select one or two flat faces, closed edges or closed "
                                       "sketches of a PartDesign Body.\n"))
            return
        obj = prof[0][0]
        doc = obj.Document
        end = prof[1] if len(prof) > 1 else None
        # Part workbench'te: Body disinda kendi basina kati. PartDesign'da "own Body" secenegi acikken: yeni Body.
        part = not self.sub and _workbench() == "PartWorkbench"
        own = not self.sub and not part and own_body()
        if not (part or own):
            bodies = [p[0].getParentGeoFeatureGroup() if hasattr(p[0], "getParentGeoFeatureGroup") else None
                      for p in prof]
            body = bodies[0]
            if any(b is None or b.TypeId != "PartDesign::Body" or b is not body for b in bodies):
                if self.sub:
                    App.Console.PrintWarning(T("Rail Pipe: the faces must belong to a PartDesign Body.\n"))
                    return
                own = True                                 # profiller ayri nesnelerde: boru kendi Body'sinde
        doc.openTransaction(T("Rail Groove") if self.sub else T("Rail Pipe"))
        if part:
            new = pda_railpipe.make_part(doc, prof[0], end)
        elif own:
            new = pda_railpipe.make_own_body(doc, prof[0], end)
        else:
            new = pda_railpipe.make(body, prof[0], end, self.sub)
        if isinstance(new, str):
            doc.abortTransaction()
            App.Console.PrintWarning(T(new) + "\n")
            return
        doc.recompute()
        doc.commitTransaction()
        for p in prof:                                     # PartDesign gibi: kullanilan sketch'ler gizlenir
            if p[1] is None:
                p[0].ViewObject.Visibility = False
        if "Invalid" in new.State:
            App.Console.PrintWarning(T("Rail Pipe: the first sweep failed; adjust GuidePoints in the property "
                                       "view.\n"))
        elif getattr(new, "BaseFeature", None) is not None:
            new.BaseFeature.ViewObject.Visibility = False
            new.ViewObject.Visibility = True
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(new)


class _MagicLoft:
    """Magic Loft (ekler) / Magic Loft Cut (oyar): secili kapali kesitler arasinda temiz yuzey; acik sketch / egriler
    rehber olur (pda_magicloft). Gorev paneli hemen acilir: sira, uc kisitlari, rehberler."""

    def __init__(self, subtractive):
        self.sub = subtractive

    def GetResources(self):
        if self.sub:
            return {"Pixmap": os.path.join(ICONS, "pda_magicloftcut.svg"), "MenuText": T("Magic Loft Cut"),
                    "ToolTip": T("PartDesign: cut a loft through two or more closed profiles, with selected or "
                                 "automatic guides")}
        return {"Pixmap": os.path.join(ICONS, "pda_magicloft.svg"), "MenuText": T("Magic Loft"),
                "ToolTip": T("PartDesign: add a clean loft through two or more closed profiles (also 3D edge loops), "
                             "with selected or automatic guides. Open curves in the selection become guides")}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        import pda_magicloft
        prof, guides = pda_magicloft.classify(Gui.Selection.getSelectionEx())
        if len(prof) < 2:
            App.Console.PrintWarning(T("Magic Loft: select at least two closed profiles (flat faces, closed edge "
                                       "loops or closed sketches); open curves become guides.\n"))
            return
        doc = prof[0][0].Document
        part = not self.sub and _workbench() == "PartWorkbench"
        own = not self.sub and not part and own_body()
        body = None
        if not (part or own):
            items = prof + guides
            bodies = [p[0].getParentGeoFeatureGroup() for p in items]
            body = bodies[0]
            if any(b is None or b.TypeId != "PartDesign::Body" or b is not body for b in bodies):
                if self.sub:
                    App.Console.PrintWarning(T("Magic Loft: the profiles must belong to a PartDesign Body.\n"))
                    return
                own = True
        doc.openTransaction(T("Magic Loft Cut") if self.sub else T("Magic Loft"))
        if part:
            new = pda_magicloft.make_part(doc, prof, guides)
        elif own:
            new = pda_magicloft.make_own_body(doc, prof, guides)
        else:
            new = pda_magicloft.make(body, prof, guides, self.sub)
        if isinstance(new, str):
            doc.abortTransaction()
            App.Console.PrintWarning(T(new) + "\n")
            return
        doc.recompute()
        doc.commitTransaction()
        for p in prof + guides:                            # PartDesign gibi: kullanilan sketch'ler gizlenir
            if not p[1] and hasattr(p[0], "ViewObject") and p[0].ViewObject is not None:
                p[0].ViewObject.Visibility = False
        if getattr(new, "BaseFeature", None) is not None and "Invalid" not in new.State:
            new.BaseFeature.ViewObject.Visibility = False
            new.ViewObject.Visibility = True
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(new)
        Gui.ActiveDocument.setEdit(new, 0)


def _edge_profiles(so):
    """Secili kenarlardan profiller: her kapali halka bir profil, (nesne, ["EdgeN", ...]). Kapanmayan kenarlar
    (kare halkanin tek bir kenari gibi) profil olmaz."""
    import pda_railpipe
    names = [s for s in so.SubElementNames if s.startswith("Edge")]
    if not names:
        return []
    edges = {n: so.Object.Shape.getElement(n) for n in names}
    return [(so.Object, [n for n, e in edges.items() if any(e.isSame(x) for x in w.Edges)])
            for w in pda_railpipe.edge_loops(list(edges.values()))]


def _workbench():
    try:
        return Gui.activeWorkbench().name()
    except Exception:
        return ""


def own_body():
    """Secenek: PartDesign'da her yeni Rail Pipe kendi Body'sinde (Preferences/Mod/PimpMyPartDesign/RailPipeOwnBody)."""
    import pda_common
    return pda_common._param().GetBool("RailPipeOwnBody", False)


def set_own_body(on):
    import pda_common
    pda_common._param().SetBool("RailPipeOwnBody", bool(on))


class _OwnBody:
    """Secenek dugmesi (isaretlenebilir): yeni Rail Pipe'lar PartDesign'da kendi Body'lerinde olussun. Ayni Body'deki
    borular her degisiklikte birlikte yeniden hesaplanmaz, boolean'a girmez (hizli)."""

    def GetResources(self):
        return {"Pixmap": os.path.join(ICONS, "pda_railpipe.svg"), "MenuText": T("Rail Pipe in its own Body"),
                "ToolTip": T("PartDesign: each new Rail Pipe gets its own Body (its profiles are bound with "
                             "SubShapeBinders), so pipes don't recompute and fuse together. Fuse the Bodies later "
                             "if you need one solid"),
                "Checkable": own_body()}

    def IsActive(self):
        return True

    def Activated(self, checked=None):
        set_own_body(bool(checked) if checked is not None else not own_body())


COMMANDS = ["PDA_RailPipe", "PDA_RailGroove", "PDA_MagicLoft", "PDA_MagicLoftCut"]
OPTIONS = ["PDA_RailPipeOwnBody"]

Gui.addCommand("PDA_RailPipe", _RailPipe(False))
Gui.addCommand("PDA_RailGroove", _RailPipe(True))
Gui.addCommand("PDA_MagicLoft", _MagicLoft(False))
Gui.addCommand("PDA_MagicLoftCut", _MagicLoft(True))
Gui.addCommand("PDA_RailPipeOwnBody", _OwnBody())
