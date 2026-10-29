# -*- coding: utf-8 -*-
# Pimp My PartDesign - shared GUI helpers: Move gizmo (arrows / planes / free cube), screen rays, scene access and
# the cable solver for guide points. Taken from FcSubDModelerWB (subd_modeler.py) so the add-ins do not depend on the
# SubD Modeler workbench. Copyright (c) 2026 Sedat Kuran - MIT License
import math

import numpy as np

import FreeCAD as App
from pivy import coin
from PySide import QtCore, QtWidgets

PARAM = "User parameter:BaseApp/Preferences/Mod/PimpMyPartDesign"


def _param():
    """Eklenti ayarlari (FreeCAD parametreleri)."""
    return App.ParamGet(PARAM)


def _sep(*nodes):
    s = coin.SoSeparator()
    for n in nodes:
        s.addChild(n)
    return s

def _scene_parent(view):
    # Bu FreeCAD surumunde yalnizca SoFCUnifiedSelection > ObjectGroup altindaki
    # dugumler ciziliyor; sahne kokune eklenenler gorunmuyor.
    sg = view.getSceneGraph()
    for i in range(sg.getNumChildren()):
        sel = sg.getChild(i)
        if sel.getTypeId().getName().getString() == "SoFCUnifiedSelection":
            for j in range(sel.getNumChildren()):
                if sel.getChild(j).getName().getString() == "ObjectGroup":
                    return sel.getChild(j)
    return sg

GIZMO_PX = 90.0          # varsayilan ok boyu, ekranda piksel (yakinlasip uzaklasinca sabit kalir); Options'ta ayarlanir
PICK_PX = 8.0            # tutamagi yakalama uzakligi (px)
GZ_RGB = ((0.94, 0.27, 0.27), (0.13, 0.77, 0.37), (0.23, 0.51, 0.96))
HOT = (1.0, 1.0, 0.6)
AXES = (App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1))
PLANE_A, PLANE_B = 0.22, 0.42          # duzlem karesinin iki eksendeki baslangic / bitisi (ok boyunun orani)
FREE_R = 0.07                          # merkez kupun yari boyu
PLANE_EDGE = 0.2        # duzlem normali ile bakis arasindaki |cos| bundan kucukse kare yandan gorunuyor sayilir

def _left_held():
    return bool(QtWidgets.QApplication.mouseButtons() & QtCore.Qt.LeftButton)

def _vv(v):
    W, H = v.getSize()
    return v.getCameraNode().getViewVolume(float(W) / H), W, H

class _Handle(object):
    """Tek bir tutamak: renk/kalinlik dugumleri (vurgu icin) + cizim."""

    def __init__(self, rgb, width):
        self.rgb = rgb
        self.width = width
        self.sep = coin.SoSeparator()
        self.col = coin.SoBaseColor()
        self.col.rgb = rgb
        self.style = coin.SoDrawStyle()
        self.style.lineWidth = width
        self.sep.addChild(self.col)
        self.sep.addChild(self.style)

    def hot(self, on):
        self.col.rgb = HOT if on else self.rgb
        self.style.lineWidth = self.width + (1.5 if on else 0.0)

    def lines(self, pts, idx):
        co = coin.SoCoordinate3()
        co.point.setValues(0, len(pts), pts)
        ls = coin.SoIndexedLineSet()
        ls.coordIndex.setValues(0, len(idx), idx)
        self.sep.addChild(co)
        self.sep.addChild(ls)
        return co


class _FillHandle(_Handle):
    """Dolgulu tutamak (duzlem karesi, merkez kup): cizgi + yari saydam dolgu; soluk = tutulamaz."""

    def __init__(self, rgb, width, alpha):
        _Handle.__init__(self, rgb, width)
        self.alpha = alpha
        self.mat = coin.SoMaterial()
        self.mat.diffuseColor = rgb
        self.mat.emissiveColor = rgb
        self.mat.transparency = alpha
        self.fill = coin.SoSeparator()
        self.fill.addChild(self.mat)
        self.sep.addChild(self.fill)
        self._dim = False

    def hot(self, on):
        _Handle.hot(self, on and not self._dim)
        c = HOT if (on and not self._dim) else self.rgb
        self.mat.diffuseColor = c
        self.mat.emissiveColor = c

    def dim(self, off):
        if off == self._dim:
            return
        self._dim = off
        self.mat.transparency = 0.93 if off else self.alpha
        self.col.rgb = tuple(0.35 + 0.3 * c for c in self.rgb) if off else self.rgb


def _plane_corners(i):
    a, b = AXES[(i + 1) % 3], AXES[(i + 2) % 3]
    return [a * u + b * w for u, w in ((PLANE_A, PLANE_A), (PLANE_B, PLANE_A), (PLANE_B, PLANE_B), (PLANE_A, PLANE_B))]


def _plane_square(i):
    h = _FillHandle(GZ_RGB[i], 1.5, 0.6)
    pts = [(p.x, p.y, p.z) for p in _plane_corners(i)]
    h.lines(pts, [0, 1, 2, 3, 0, -1])
    co = coin.SoCoordinate3()
    co.point.setValues(0, 4, pts)
    fs = coin.SoFaceSet()
    fs.numVertices.setValue(4)
    sh = coin.SoShapeHints()
    sh.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
    for n in (sh, co, fs):
        h.fill.addChild(n)
    return h.sep, h


def _free_cube():
    h = _FillHandle((0.92, 0.92, 0.95), 1.5, 0.15)
    r = FREE_R
    c = [(x, y, z) for x in (-r, r) for y in (-r, r) for z in (-r, r)]
    h.lines(c, [0, 1, 3, 2, 0, -1, 4, 5, 7, 6, 4, -1, 0, 4, -1, 1, 5, -1, 2, 6, -1, 3, 7, -1])
    cu = coin.SoCube()
    cu.width = cu.height = cu.depth = 2 * r
    h.fill.addChild(cu)
    return h.sep, h


def _arrow(i):
    h = _Handle(GZ_RGB[i], 3.0)
    s = coin.SoSeparator()
    r = coin.SoRotation()
    r.rotation.setValue(coin.SbRotation(coin.SbVec3f(1, 0, 0), coin.SbVec3f(*AXES[i])))
    s.addChild(r)
    s.addChild(h.sep)
    h.lines([(0, 0, 0), (1, 0, 0)], [0, 1, -1])
    t = coin.SoTransform()
    t.translation = (1.05, 0, 0)
    t.rotation.setValue(coin.SbVec3f(0, 0, 1), -math.pi / 2)
    cn = coin.SoCone()
    cn.bottomRadius = 0.06
    cn.height = 0.18
    h.sep.addChild(t)
    h.sep.addChild(cn)
    return s, h


def _stretch_handle(i):
    """Stretch tutamagi: eksen cizgisi + ucunda kucuk kup (LightWave Stretch)."""
    h = _Handle(GZ_RGB[i], 3.0)
    s = coin.SoSeparator()
    r = coin.SoRotation()
    r.rotation.setValue(coin.SbRotation(coin.SbVec3f(1, 0, 0), coin.SbVec3f(*AXES[i])))
    s.addChild(r)
    s.addChild(h.sep)
    h.lines([(0, 0, 0), (1, 0, 0)], [0, 1, -1])
    t = coin.SoTranslation()
    t.translation = (1.04, 0, 0)
    cu = coin.SoCube()
    cu.width = cu.height = cu.depth = 0.12
    h.sep.addChild(t)
    h.sep.addChild(cu)
    return s, h


def _size_cube():
    """Size tutamagi: merkezde orantili olcekleme kupu."""
    h = _FillHandle((0.95, 0.80, 0.25), 1.5, 0.35)
    r = 0.11
    c = [(x, y, z) for x in (-r, r) for y in (-r, r) for z in (-r, r)]
    h.lines(c, [0, 1, 3, 2, 0, -1, 4, 5, 7, 6, 4, -1, 0, 4, -1, 1, 5, -1, 2, 6, -1, 3, 7, -1])
    cu = coin.SoCube()
    cu.width = cu.height = cu.depth = 2 * r
    h.fill.addChild(cu)
    return h.sep, h


RING_N = 64


def _ring_pts(i):
    """i ekseni etrafindaki birim cemberin noktalari (eksene dik duzlemde)."""
    a = AXES[(i + 1) % 3]
    b = AXES[(i + 2) % 3]
    return [a * math.cos(2 * math.pi * k / RING_N) + b * math.sin(2 * math.pi * k / RING_N) for k in range(RING_N)]


def _ring(i):
    h = _Handle(GZ_RGB[i], 3.5)
    h.lines([(p.x, p.y, p.z) for p in _ring_pts(i)], list(range(RING_N)) + [0, -1])
    return h.sep, h


def _rotation_matrix(axis, ang):
    """Birim eksen etrafinda ang radyanlik donus matrisi (Rodrigues)."""
    x, y, z = axis
    c, s, t = math.cos(ang), math.sin(ang), 1 - math.cos(ang)
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                     [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                     [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def _ray(v, pos):
    """Imlec pikselinden (sol alt kokenli) dunya isini: (baslangic, birim yon)."""
    p = v.getPoint((pos[0], pos[1]))
    cn = v.getCameraNode()
    if cn.isOfType(coin.SoPerspectiveCamera.getClassTypeId()):
        o = App.Vector(*cn.position.getValue().getValue())
        d = p - o
    else:
        d = App.Vector(*v.getViewDirection())
        o = p - d * 1e7
    d.normalize()
    return o, d


def _to_screen(vv, W, H, p):
    sx, sy, _ = vv.projectToScreen(coin.SbVec3f(p.x, p.y, p.z)).getValue()
    return sx * W, sy * H


def _seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _view_dir(v, p):
    cn = v.getCameraNode()
    if cn.isOfType(coin.SoPerspectiveCamera.getClassTypeId()):
        d = p - App.Vector(*cn.position.getValue().getValue())
    else:
        d = App.Vector(*v.getViewDirection())
    if d.Length > 1e-12:
        d.normalize()
    return d


def _in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for k in range(n):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _line_param(o, d, p0, a):
    w = o - p0
    b = d.dot(a)
    den = 1.0 - b * b
    if abs(den) < 1e-6:
        return None
    return (w.dot(a) - b * w.dot(d)) / den


def _plane_hit(o, d, c, n):
    den = d.dot(n)
    if abs(den) < 1e-6:
        return None
    t = (c - o).dot(n) / den
    return o + d * t


class MoveGizmo(object):
    """Secimin merkezinde gizmo. Tasi: X/Y/Z oklari, XY/YZ/XZ duzlem kareleri, merkezde serbest tasima kupu.
    Dondur: X/Y/Z eksenleri etrafinda halkalar. Yalnizca cizimdir; fare olaylarini oturum yakalar ve
    pick() ile tutamagi sorar."""

    def __init__(self, view):
        self.view = view
        self.mode = "move"   # "move" | "rotate"
        self.center = None
        self.size = 1.0
        self.px = min(max(_param().GetFloat("GizmoSize", GIZMO_PX), 30.0), 400.0)   # ok boyu (px)
        self.hover = None
        self.handles = {}
        self.root = coin.SoSwitch()
        ann = coin.SoAnnotation()          # derinlik testi olmadan: nesnenin icinde kalsa da gorunur
        self.pos = coin.SoTranslation()
        self.scale = coin.SoScale()
        ann.addChild(self.pos)
        ann.addChild(self.scale)
        self.modes = coin.SoSwitch()
        ann.addChild(self.modes)
        g = coin.SoSeparator()
        for i in range(3):
            s, h = _arrow(i)
            g.addChild(s)
            self.handles[("move", i)] = h
        for i in range(3):
            s, h = _plane_square(i)
            g.addChild(s)
            self.handles[("plane", i)] = h
        s, h = _free_cube()
        g.addChild(s)
        self.handles[("free", 0)] = h
        self.modes.addChild(g)
        g = coin.SoSeparator()
        for i in range(3):
            s, h = _ring(i)
            g.addChild(s)
            self.handles[("rotate", i)] = h
        self.modes.addChild(g)
        g = coin.SoSeparator()                         # Stretch: uclari kuplu eksenler; Size: merkez kup
        for i in range(3):
            s, h = _stretch_handle(i)
            g.addChild(s)
            self.handles[("stretch", i)] = h
        s, h = _size_cube()
        g.addChild(s)
        self.handles[("size", 0)] = h
        self.modes.addChild(g)
        self.root.addChild(ann)
        self.root.whichChild = -1
        self.set_mode("move")

    def set_mode(self, mode):
        self.mode = mode
        self.modes.whichChild = {"move": 0, "rotate": 1, "scale": 2}[mode]

    def place(self, center):
        self.center = center
        if center is None:
            self.root.whichChild = -1
            return
        self.root.whichChild = 0
        self.pos.translation = (center.x, center.y, center.z)
        self.update_scale()

    def update_scale(self):
        if self.center is None:
            return
        vv, W, H = _vv(self.view)
        p = self.center
        size = vv.getWorldToScreenScale(coin.SbVec3f(p.x, p.y, p.z), self.px / float(H))
        if abs(size - self.size) > 1e-9 * max(size, 1.0):
            self.size = size
            self.scale.scaleFactor.setValue(size, size, size)
        vd = _view_dir(self.view, p)
        for i in range(3):
            self.handles[("plane", i)].dim(abs(vd.dot(AXES[i])) < PLANE_EDGE)

    def pick(self, pos):
        """Imlecin PICK_PX yakinindaki tutamak: (tur, eksen) ya da None."""
        if self.center is None:
            return None
        vv, W, H = _vv(self.view)
        x, y = pos
        if self.mode == "rotate":
            best, bd = None, PICK_PX
            for i in range(3):
                pts = [_to_screen(vv, W, H, self.center + q * self.size) for q in _ring_pts(i)[::2]]
                for k in range(len(pts)):
                    dd = _seg_dist(x, y, pts[k], pts[(k + 1) % len(pts)])
                    if dd < bd:
                        best, bd = ("rotate", i), dd
            return best
        c = _to_screen(vv, W, H, self.center)
        k = max(self.px / GIZMO_PX, 0.6)                   # merkez kupun yakalama yaricapi gizmoyla buyur
        if self.mode == "scale":
            if math.hypot(x - c[0], y - c[1]) < 12.0 * k:
                return ("size", 0)
            best, bd = None, PICK_PX
            for i in range(3):
                e = _to_screen(vv, W, H, self.center + AXES[i] * (self.size * 1.1))
                dd = _seg_dist(x, y, c, e)
                if dd < bd:
                    best, bd = ("stretch", i), dd
            return best
        if math.hypot(x - c[0], y - c[1]) < 10.0 * k:  # oncelik: merkez kup, sonra kareler, sonra oklar
            return ("free", 0)
        for i in range(3):
            if self.handles[("plane", i)]._dim:
                continue
            poly = [_to_screen(vv, W, H, self.center + q * self.size) for q in _plane_corners(i)]
            if _in_poly(x, y, poly):
                return ("plane", i)
        best, bd = None, PICK_PX
        for i in range(3):
            e = _to_screen(vv, W, H, self.center + AXES[i] * (self.size * 1.2))
            dd = _seg_dist(x, y, c, e)
            if dd < bd:
                best, bd = ("move", i), dd
        return best

    def set_hover(self, key):
        if key == self.hover:
            return
        if self.hover in self.handles:
            self.handles[self.hover].hot(False)
        if key in self.handles:
            self.handles[key].hot(True)
        self.hover = key


# ---------- Kablo cozucu (kilavuz noktalari kablo gibi cekmek) ----------

def rail_cable(N, h, d, fixed_b, elastic, ta, tb=None, iters=30, friction=12.0, bend=6.0):
    """Kilavuzu kablo gibi cek: N dugumler (0: A, hep sabit; son: B, fixed_b ise sabit), h cekilen dugum, d
    tasima; ta / tb: A'dan cikis, B'ye giris yonu (uclarda hayali dugum: kablo dik cikar). Serbest dugumler
    bukulme enerjisi + boy degisimi cezasiyla en aza indirilir (Levenberg-Marquardt): aradaki kivrimlar acilir /
    gevser, gerilince dumduz olup esit uzar. friction: tek uclu rail'de cekilen noktanin ardindaki serbest kuyruk
    masadaki kablo gibi eski yerinde kalmaya direnir: ortadan cekilince orada bombe olur, serbest uc az oynar, hat
    gerilince surukleyerek gelir (ucu itip cekerken ve iki uclu rail'de kuyruk yok). elastic: boy sertligi, 0 zincir (boylar korunur) .. 1 lastik (kolay uzar / kisalir). Yeni dugumler."""
    N = np.asarray(N, float)
    n = len(N)
    L = np.linalg.norm(np.diff(N, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(L)])
    ta = np.asarray(ta, float)
    t = N[h] + d
    # baslangic: tasima yay uzunluguna gore sabit uca dogru azalarak; boyundan kisa kalan bolum yana bombe
    # yapar (dumduz sikisan kablo dengede kalir, bukulmezdi): yon surukleme ya da egrinin eski seklinden
    w = np.clip(s / max(s[h], 1e-12), 0.0, 1.0)
    w[h:] = (s[-1] - s[h:]) / max(s[-1] - s[h], 1e-12)    # tek uclu kuyruk da serbest uca dogru azalir
    w[h] = 1.0
    X = N + np.outer(w, d)
    for a, b in ((0, h), (h, n - 1)) if fixed_b else ((0, h),):
        c = X[b] - X[a]
        D, Ls = np.linalg.norm(c), s[b] - s[a]
        if b - a < 2 or D >= Ls or D < 1e-12:
            continue
        k = c / D
        for v in [d] + list(N[a:b + 1] - N[a]) + list(np.eye(3)):
            v = v - v.dot(k) * k
            if np.linalg.norm(v) > 1e-6 * max(Ls, 1.0):
                X[a:b + 1] += np.outer(np.sin(np.pi * (s[a:b + 1] - s[a]) / Ls),
                                       v / np.linalg.norm(v) * 0.5 * math.sqrt(Ls * Ls - D * D))
                break
    X[0], X[h] = N[0], t
    if fixed_b:
        X[-1] = N[-1]
    Y = np.vstack([[N[0] - ta * L[0]], X] + ([[N[-1] + np.asarray(tb, float) * L[-1]]] if fixed_b else []))
    m = len(Y)
    free = np.ones(m, bool)
    free[[0, 1, h + 1]] = False
    if fixed_b:
        free[[m - 2, m - 1]] = False
    cols = np.repeat(free, 3)
    Y0 = Y.copy()
    Y0[1:n + 1] = N                                        # surtunme: kuyruk dugumlerinin eski yeri
    fw = np.zeros(m)
    if not fixed_b:
        fw[h + 2:n + 1] = friction
    fw = np.repeat(fw, 3)[cols]
    Jf = np.diag(fw)
    sk = 10.0 ** (1.5 - 3.0 * min(max(float(elastic), 0.0), 1.0))   # boy cezasi: 30 (zincir) .. 0.03 (lastik)
    nl = len(L)
    Jb = np.zeros((3 * (m - 2), 3 * m))                    # bukulme satirlari sabit (dogrusal)
    for j in range(1, m - 1):
        for q, c in ((j - 1, 1.0), (j, -2.0), (j + 1, 1.0)):
            Jb[3 * (j - 1):3 * j, 3 * q:3 * q + 3] += bend * c * np.eye(3)
    Jb = Jb[:, cols]
    ri = np.repeat(np.arange(nl), 3)
    ca = 3 * (np.arange(nl) + 1)[:, None] + np.arange(3)   # parca i: Y[i + 1] -> Y[i + 2]

    def resid(Y):
        v = Y[2:] - Y[1:-1] if not fixed_b else Y[2:-1] - Y[1:-2]   # gercek parcalar (hayali uclar haric)
        l = np.linalg.norm(v, axis=1)
        return np.concatenate([sk * (l - L), bend * (Y[:-2] - 2 * Y[1:-1] + Y[2:]).ravel(),
                               fw * (Y[free] - Y0[free]).ravel()]), v, l

    def jac(v, l):
        Jl = np.zeros((nl, 3 * m))
        u = (sk * v / np.maximum(l, 1e-12)[:, None]).ravel()
        Jl[ri, ca.ravel()] = -u
        Jl[ri, (ca + 3).ravel()] = u
        return np.vstack([Jl[:, cols], Jb, Jf])
    lam = 1e-2
    r, v, l = resid(Y)
    cost = r.dot(r)
    for _ in range(iters):
        J = jac(v, l)
        A = J.T @ J
        g = J.T @ r
        while True:
            step = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-9), -g)
            Y2 = Y.copy()
            Y2[free] += step.reshape(-1, 3)
            r2, v2, l2 = resid(Y2)
            c2 = r2.dot(r2)
            if c2 < cost or lam > 1e8:
                break
            lam *= 4
        if c2 >= cost:
            break
        Y, r, v, l, cost, lam = Y2, r2, v2, l2, c2, max(lam / 3, 1e-6)
        if np.abs(step).max() < 1e-6:
            break
    return Y[1:n + 1]
