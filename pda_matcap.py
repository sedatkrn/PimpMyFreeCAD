# -*- coding: utf-8 -*-
# Pimp My FreeCAD - matcap view of Part / PartDesign shapes. Copyright (c) 2026 Sedat Kuran - MIT License
#
# Matcap: yuzey normaline gore boyanmis "isikli kure" dokusu. Isik, parlama ve kenar kararmasi dokunun icinde: sahne
# isiklarindan bagimsiz ve cok hizli. Yalniz gorunum: nesneye ve belgeye hicbir sey yazilmaz, secim Preferences'ta.
# Her yuz dugumu ortak doku + shader ile bir ayiriciya sarilir; kenar ve noktalar etkilenmez. Kapatinca sahne eski haline doner.
import FreeCAD as App
import FreeCADGui as Gui
import numpy as np
from pivy import coin

import pda_common

PARAM = "Matcap"

# Ayar: taban rengi, ortam, ana / dolgu isigi, parlama (guc, siddet), kenar kararmasi, kenar parlamasi; "env": taban
# yerine studyo yansimasi (metal).
MATCAPS = {
    "Clay": dict(base=(0.80, 0.74, 0.68), amb=0.30, key=0.72, fill=0.16, spec=(14.0, 0.06), ao=0.55, rim=0.04),
    "Plastic": dict(base=(0.62, 0.66, 0.72), amb=0.24, key=0.74, fill=0.18, spec=(70.0, 0.55), ao=0.45, rim=0.22),
    "Black plastic": dict(base=(0.14, 0.14, 0.15), amb=0.40, key=1.10, fill=0.50, spec=(40.0, 0.60), ao=0.40, rim=0.45),
    "Ceramic": dict(base=(0.93, 0.92, 0.89), amb=0.34, key=0.60, fill=0.14, spec=(180.0, 0.90), ao=0.35, rim=0.30),
    "Metal": dict(base=(0.80, 0.81, 0.84), amb=0.0, key=0.0, fill=0.0, spec=(120.0, 0.50), ao=0.30, rim=0.0, env=True),
}
FACE_NODES = ("SoBrepFaceSet",)

_group = None           # ortak doku + shader (tum ayiricilarda ayni dugum)
_tex = None
_sel = None             # secim / on secim rengi (shader parametresi)
_pre = None
_observer = None


def _matcap_image(name, size=256):
    """MATCAPS ayarindan size x size RGB doku (bytes; ilk satir kurenin alti, Coin dokusu gibi)."""
    c = MATCAPS[name]
    y, x = np.mgrid[0:size, 0:size]
    x, y = (x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1
    r = np.maximum(np.hypot(x, y), 1.0)                    # daire disi kenar rengini alir (doku suzmesinde dikis yok)
    x, y = x / r, y / r
    n = np.dstack((x, y, np.sqrt(np.maximum(1 - x * x - y * y, 0.0))))
    light = lambda *v: np.array(v) / np.linalg.norm(v)
    key, fill = light(-0.45, 0.65, 0.65), light(0.75, 0.05, 0.45)
    half = (key + (0, 0, 1)) / np.linalg.norm(key + (0, 0, 1))
    base = np.array(c["base"])
    if c.get("env"):                                       # yansima yonune gore studyo: tavan, ufuk bandi, koyu zemin
        ry = 2 * n[..., 2] * n[..., 1]
        sky = 0.45 + 0.50 * np.clip(ry, 0, 1) ** 0.7
        ground = 0.10 + 0.25 * np.clip(-ry - 0.15, 0, 1)
        t = np.clip((ry + 0.04) / 0.08, 0, 1)
        env = ground + t * t * (3 - 2 * t) * (sky - ground) + 0.30 * np.exp(-(ry / 0.05) ** 2)
        rgb = env[..., None] * base
    else:
        dif = c["amb"] + c["key"] * np.maximum(n @ key, 0) + c["fill"] * np.maximum(n @ fill, 0)
        rgb = dif[..., None] * base
    p, k = c["spec"]
    rgb = rgb + (k * np.maximum(n @ half, 0) ** p)[..., None]
    rgb = rgb + (c["rim"] * (1 - n[..., 2]) ** 4 * np.clip(y * 0.5 + 0.5, 0, 1))[..., None]
    t = np.clip(n[..., 2] / 0.55, 0, 1)                    # kenara dogru karar: sahte AO
    rgb = rgb * (1 - c["ao"] * (1 - t * t * (3 - 2 * t)))[..., None]
    return (np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes()


def _matcap_shader():
    """Dokuyu piksel basina okur. FreeCAD secim / on secim rengini gl_Color'da verir (olculdu): renk tercihlerdeki
    vurgu rengine esitse yuz o renkle boyanir, doku parlakligi sekli gostermeye devam eder; yoksa secim gorunmezdi."""
    vs = coin.SoVertexShader()
    vs.sourceType = coin.SoShaderObject.GLSL_PROGRAM
    vs.sourceProgram = ("varying vec3 vN; varying vec3 vC; void main(){ vC = gl_Color.rgb; "
                        "vN = gl_NormalMatrix * gl_Normal; gl_Position = ftransform(); }")
    fs = coin.SoFragmentShader()
    fs.sourceType = coin.SoShaderObject.GLSL_PROGRAM
    fs.sourceProgram = ("uniform sampler2D tex; uniform vec3 sel; uniform vec3 pre; varying vec3 vN; varying vec3 vC; "
                        "void main(){ vec3 n = normalize(vN); if (!gl_FrontFacing) n = -n; "
                        "vec3 t = texture2D(tex, n.xy * 0.5 + 0.5).rgb; "
                        "if (distance(vC, sel) < 0.02 || distance(vC, pre) < 0.02) "
                        "t = vC * (0.45 + 0.75 * dot(t, vec3(0.2126, 0.7152, 0.0722))); "
                        "gl_FragColor = vec4(t, gl_FrontMaterial.diffuse.a); }")
    prog = coin.SoShaderProgram()
    prog.shaderObject.set1Value(0, vs)
    prog.shaderObject.set1Value(1, fs)
    fs.parameter.set1Value(0, _sel)
    fs.parameter.set1Value(1, _pre)
    return prog


def _highlight_colors():
    """Tercihlerdeki secim / on secim rengi shader'a: matcap her secildiginde yeniden okunur."""
    p = App.ParamGet("User parameter:BaseApp/Preferences/View")
    for node, key, default in ((_sel, "SelectionColor", 0x00abffff), (_pre, "HighlightColor", 0x0ac8ffff)):
        c = p.GetUnsigned(key, default)
        node.value = ((c >> 24 & 255) / 255.0, (c >> 16 & 255) / 255.0, (c >> 8 & 255) / 255.0)


def _nodes():
    global _group, _tex, _sel, _pre
    if _group is None:
        _sel, _pre = coin.SoShaderParameter3f(), coin.SoShaderParameter3f()
        _sel.name = "sel"
        _pre.name = "pre"
        _group = coin.SoGroup()
        _group.ref()
        _tex = coin.SoTexture2()
        _tex.model = coin.SoTexture2.REPLACE
        _group.addChild(_tex)
        _group.addChild(_matcap_shader())
    return _group


def _paths(root, node=None, type_name=None):
    sa = coin.SoSearchAction()
    sa.setSearchingAll(True)
    sa.setInterest(coin.SoSearchAction.ALL)
    if node is not None:
        sa.setNode(node)
    else:
        sa.setType(coin.SoType.fromName(type_name))
    sa.apply(root)
    pl = sa.getPaths()                                     # listeyi sa tutar: yollar kopyalanir
    return [pl[i].copy() for i in range(pl.getLength())]


def _pairs(root, **kw):
    """(ust grup, alt dugum) ciftleri. FlatRoot iki moddan da gorunur: ayni cift iki kez gelir; yollar degisiklikle
    guncellendiginden degistirmeden once toplanir, ikinciyi findChild < 0 eler."""
    return [(coin.cast(p.getNodeFromTail(1), "SoGroup"), p.getTail()) for p in _paths(root, **kw)]


def _view_roots(doc):
    for o in doc.Objects:
        vo = getattr(o, "ViewObject", None)
        root = getattr(vo, "RootNode", None) if vo is not None else None
        if root is not None:
            yield root


def _install(root):
    group = _nodes()
    for name in FACE_NODES:
        for parent, face in _pairs(root, type_name=name):
            i = parent.findChild(face)
            if i < 0 or parent.findChild(group) >= 0:
                continue
            sep = coin.SoSeparator()
            sep.renderCaching = coin.SoSeparator.OFF       # secim rengi degisince eski goruntu kalmasin
            sep.addChild(group)
            sep.addChild(face)
            parent.replaceChild(i, sep)


def _uninstall(root):
    pairs = [(coin.cast(p.getNodeFromTail(2), "SoGroup"), coin.cast(p.getNodeFromTail(1), "SoGroup"))
             for p in _paths(root, node=_group)]
    for parent, sep in pairs:
        i = parent.findChild(sep)
        if i >= 0:
            parent.replaceChild(i, sep.getChild(1))


def apply_document(doc):
    if current():
        for root in _view_roots(doc):
            _install(root)


class _Observer:
    """Yeni ya da geri alinan nesneler ve acilan belgeler de matcap'le gorunsun: olay basina bir kez, yukleme bitince."""

    def __init__(self):
        self.pending = set()

    def _later(self, doc):
        from PySide import QtCore
        if not self.pending:
            QtCore.QTimer.singleShot(0, self._run)
        self.pending.add(doc.Name)

    def _run(self):
        from PySide import QtCore
        names, self.pending = self.pending, set()
        for name in names:
            doc = App.listDocuments().get(name)
            if doc is None:
                continue
            if doc.Restoring:
                self.pending.add(name)
            else:
                apply_document(doc)
        if self.pending:
            QtCore.QTimer.singleShot(200, self._run)

    def slotCreatedObject(self, obj):
        self._later(obj.Document)

    def slotActivateDocument(self, doc):
        self._later(doc)

    def slotUndoDocument(self, doc):
        self._later(doc)

    def slotRedoDocument(self, doc):
        self._later(doc)


def current():
    name = pda_common._param().GetString(PARAM, "")
    return name if name in MATCAPS else ""


def set_matcap(name):
    """Matcap'i tum belgelerde degistirir; "" kapatir, sahne eski haline doner."""
    global _observer
    name = name if name in MATCAPS else ""
    pda_common._param().SetString(PARAM, name)
    docs = App.listDocuments().values()
    if name:
        _nodes()
        _highlight_colors()
        _tex.image.setValue(coin.SbVec2s(256, 256), 3, _matcap_image(name))
        if _observer is None:
            _observer = _Observer()
            App.addDocumentObserver(_observer)
        for doc in docs:
            apply_document(doc)
    elif _group is not None:
        if _observer is not None:
            App.removeDocumentObserver(_observer)
            _observer = None
        for doc in docs:
            for root in _view_roots(doc):
                _uninstall(root)
    for gd in (Gui.getDocument(d.Name) for d in docs):
        if gd is not None and hasattr(gd.ActiveView, "redraw"):
            gd.ActiveView.redraw()


def restore():
    """Kayitli secim: FreeCAD acilisinda bir kez."""
    if current() and _group is None:
        set_matcap(current())
