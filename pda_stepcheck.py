# -*- coding: utf-8 -*-
# Pimp My FreeCAD - STEP check: is a shape fit for export? Copyright (c) 2026 Sedat Kuran - MIT License
#
# Sekle dokunmaz: kopya gecici STEP dosyasina yazilip geri okunur, dosya silinir. Sinirlar mm.
import os
import tempfile

import Part

from pda_i18n import T

OK, INFO, WARNING, ERROR = "ok", "info", "warning", "error"
TOL_WARN, TOL_ERROR = 0.01, 0.1
SHORT_EDGE = 0.01
VOLUME_WARN, VOLUME_ERROR = 1e-4, 0.01      # oran
BOX_WARN = 0.01


def _closed(sh):
    return all(s.isClosed() for s in sh.Solids for s in s.Shells)


def _strict(sh):
    """OCCT'nin siki BOP denetimi; hata metni ya da None. Gecerli katida da takilabilir: uyari."""
    try:
        sh.copy().check(True)
    except Exception as e:
        # ilk satir yalniz baslik ("BOP check found the following errors:"): asil bilgi sonraki satirlarda
        lines = [x.strip() for x in str(e).splitlines() if x.strip() and x.strip() != "No error"]
        lines = [x.replace("Error in ", "") for x in lines if not x.startswith("BOP check found")]
        return "; ".join("%d x %s" % (lines.count(x), x) for x in dict.fromkeys(lines)) if lines else T("the check failed")
    return None


def _roundtrip(sh):
    """Kopyayi STEP'e yazip geri okur: (sekil, dosya boyutu)."""
    fd, path = tempfile.mkstemp(suffix=".step", prefix="pda_stepcheck_")
    os.close(fd)
    try:
        sh.copy().exportStep(path)
        back = Part.Shape()
        back.read(path)
        return back, os.path.getsize(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def compare(sh, back):
    """Geri okunan sekli karsilastirir: (durum, baslik, ayrinti) listesi."""
    out = []
    if not back.isValid():
        out.append((ERROR, T("Read back"), T("the shape read from STEP is not valid")))
    else:
        out.append((OK, T("Read back"), T("the shape read from STEP is valid")))
    a, b = len(sh.Solids), len(back.Solids)
    out.append((OK if a == b else ERROR, T("Solids after STEP"), "%d -> %d" % (a, b)))
    a, b = len(sh.Faces), len(back.Faces)
    out.append((OK if a == b else WARNING, T("Faces after STEP"), "%d -> %d" % (a, b)))
    a, b = len(sh.Edges), len(back.Edges)
    out.append((OK if a == b else INFO, T("Edges after STEP"), "%d -> %d" % (a, b)))
    if sh.Solids and back.Solids:
        v = abs(back.Volume - sh.Volume) / max(abs(sh.Volume), 1e-9)
        st = ERROR if v > VOLUME_ERROR else (WARNING if v > VOLUME_WARN else OK)
        out.append((st, T("Volume after STEP"), "%.2f -> %.2f mm3 (%.4f %%)" % (sh.Volume, back.Volume, 100 * v)))
    if back.Faces:
        # BoundBox kontrol noktalarina, varsayilan optimalBoundingBox gorunum mesh'ine bakar: hacim ayniyken B-spline yuzeyde
        # 2.3 ve 0.17 mm fark gosterdiler (olculdu). Mesh'siz: iki sekil ayni yoldan olculur.
        a, b = sh.optimalBoundingBox(False, False), back.optimalBoundingBox(False, False)
        d = max(abs(getattr(a, n) - getattr(b, n)) for n in ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"))
        out.append((WARNING if d > BOX_WARN else OK, T("Bounding box after STEP"), "%.4f mm" % d))
    return out


def check(sh):
    """Rapor: (durum, baslik, ayrinti) listesi."""
    if sh is None or sh.isNull() or not sh.Faces:
        return [(ERROR, T("Shape"), T("no faces to export"))]
    out = []
    if sh.isValid():
        out.append((OK, T("Valid shape"), T("yes")))
    else:
        out.append((ERROR, T("Valid shape"), T("no")))
    msg = _strict(sh)
    out.append((WARNING, T("Strict check"), msg[:200]) if msg else (OK, T("Strict check"), T("no problems")))
    if not sh.Solids:
        out.append((WARNING, T("Solids"), T("none: this is a surface, not a solid")))
    else:
        out.append((OK if len(sh.Solids) == 1 else INFO, T("Solids"), str(len(sh.Solids))))
        out.append((OK, T("Closed"), T("yes")) if _closed(sh) else (ERROR, T("Closed"), T("an open shell")))
    tol = max(sh.getTolerance(1, t) for t in (Part.Vertex, Part.Edge, Part.Face))
    st = ERROR if tol > TOL_ERROR else (WARNING if tol > TOL_WARN else OK)
    out.append((st, T("Largest tolerance"), "%.6f mm" % tol))
    short = sum(1 for e in sh.Edges if e.Length < SHORT_EDGE)
    out.append((WARNING if short else OK, T("Very short edges"), "%d (< %g mm)" % (short, SHORT_EDGE)))
    kinds = {}
    for f in sh.Faces:
        n = f.Surface.TypeId.split("::")[-1].replace("Geom", "")
        kinds[n] = kinds.get(n, 0) + 1
    out.append((INFO, T("Faces"), "%d: " % len(sh.Faces) + ", ".join("%d %s" % (c, n) for n, c in sorted(kinds.items()))))
    try:
        back, size = _roundtrip(sh)
    except Exception as e:
        out.append((ERROR, T("Export to STEP"), str(e)[:200]))
        return out
    out.append((OK, T("Export to STEP"), "%.1f kB" % (size / 1024.0)))
    return out + compare(sh, back)


def worst(rows):
    for st in (ERROR, WARNING):
        if any(r[0] == st for r in rows):
            return st
    return OK


def show(objs):
    """Secili nesnelerin raporu: modal olmayan pencere, sekle dokunmaz."""
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets
    QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
    try:
        reports = [(o, check(o.Shape)) for o in objs]
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()
    dlg = QtWidgets.QDialog(Gui.getMainWindow(), QtCore.Qt.Tool)
    dlg.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    dlg.setWindowTitle(T("STEP check"))
    dlg.resize(620, 420)
    lay = QtWidgets.QVBoxLayout(dlg)
    tree = QtWidgets.QTreeWidget()
    tree.setColumnCount(3)
    tree.setHeaderLabels([T("Check"), T("Result"), T("Details")])
    names = {OK: T("OK"), INFO: T("Info"), WARNING: T("Warning"), ERROR: T("Error")}
    colors = {OK: "#3aa655", INFO: "#7f8c9b", WARNING: "#d9a400", ERROR: "#d9403a"}
    for o, rows in reports:
        st = worst(rows)
        top = QtWidgets.QTreeWidgetItem([o.Label, names[st], ""])
        top.setForeground(1, QtGui.QBrush(QtGui.QColor(colors[st])))
        for r in rows:
            it = QtWidgets.QTreeWidgetItem([r[1], names[r[0]], r[2]])
            it.setForeground(1, QtGui.QBrush(QtGui.QColor(colors[r[0]])))
            it.setToolTip(2, r[2])
            top.addChild(it)
        tree.addTopLevelItem(top)
        top.setExpanded(True)
    for c in range(2):
        tree.resizeColumnToContents(c)
    lay.addWidget(tree)
    dlg.show()
    return dlg
