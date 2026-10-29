# -*- coding: utf-8 -*-
# Pimp My PartDesign - FreeCAD GUI start-up. Copyright (c) 2026 Sedat Kuran - MIT License
#
# Araclar PartDesign'in kendi arac cubugunda ("Part Design Modeling Features", Additive / Subtractive Pipe'in
# yaninda) gorunur; ayrica kucuk bir "Pimp My PartDesign" workbench'i de ayni araclari toplar.
import FreeCADGui as Gui


class PimpMyPartDesignWorkbench(Gui.Workbench):
    MenuText = "Pimp My PartDesign"
    ToolTip = "Extra PartDesign features: Rail Pipe / Rail Groove along an editable guide curve"

    def __init__(self):
        import pda_commands
        self.__class__.Icon = pda_commands.ICON

    def Initialize(self):
        import pda_commands
        self.appendToolbar("Pimp My PartDesign", pda_commands.COMMANDS)
        self.appendMenu("Pimp My PartDesign", pda_commands.COMMANDS)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


class _PartDesignTools:
    """Araclar PartDesign'in "Part Design Modeling Features" arac cubugunda da olsun (FreeCAD 1.0+ workbench
    manipulator)."""

    def modifyToolBars(self):
        try:
            if Gui.activeWorkbench().name() != "PartDesignWorkbench":
                return []
        except Exception:
            return []
        import pda_commands
        return [{"append": c, "toolBar": "Part Design Modeling Features"} for c in pda_commands.COMMANDS]


class _RestoreObserver:
    """Belge acilinca: Proxy'si kopmus Rail Pipe / Groove nesnelerini onar (FreeCAD eklenti modulunu belge acilirken
    ice aktaramadiysa sekil guncellenmez) ve FcSubDModelerWB'nin eski subd_railpipe nesnelerini bu eklentiye tasi."""

    def slotFinishRestoreDocument(self, doc):
        if any("GuidePoints" in o.PropertiesList and type(getattr(o, "Proxy", None)).__module__ != "pda_railpipe"
               for o in doc.Objects):
            import pda_railpipe
            n = len(pda_railpipe.repair_proxies(doc))
            if n:
                App.Console.PrintMessage("Pimp My PartDesign: %d Rail Pipe / Groove object(s) linked to this add-in "
                                         "in %s (save the document to keep it)\n" % (n, doc.Name))


import FreeCAD as App
App.addDocumentObserver(_RestoreObserver())
Gui.addWorkbench(PimpMyPartDesignWorkbench())
if hasattr(Gui, "addWorkbenchManipulator"):
    Gui.addWorkbenchManipulator(_PartDesignTools())
