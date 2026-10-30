# -*- coding: utf-8 -*-
# Pimp My PartDesign - application (non-GUI) start-up. Saved objects refer to the modules "pda_railpipe" and
# "pda_magicloft", so documents must open (and recompute) without the GUI too.
import FreeCAD

# FreeCAD 26.3+ belge acilirken yalniz Mod altindan bulunan modulleri aktarir. Klasor Mod'a baglanti (junction / symlink)
# ile kuruluysa FreeCAD gercek yolu (or. Documents\...) sys.path'in basina ekler, aktarma engellenir ve nesneler
# Proxy'siz acilir (parametrik zincir kopar). Sira FreeCAD'in elinde: zaten yuklu modul ise engellenmiyor (olculdu).
try:
    import pda_railpipe
    import pda_magicloft
except Exception as e:
    FreeCAD.Console.PrintWarning("Pimp My PartDesign: %s\n" % e)
