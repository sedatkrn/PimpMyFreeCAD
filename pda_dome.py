# -*- coding: utf-8 -*-
# Pimp My PartDesign - Dome: duz yuzun uzerinde, kenarlarda komsu yuzlere teget kubbe. Copyright (c) 2026 Sedat Kuran - MIT License
#
# Yuzey OCCT dolgusu (GeomPlate) degil: yuzun duzleminde yukseklik alani h(x, y), kubik B-spline uzayinda ince plaka
# enerjisini en aza indirir (Ritz): kenarda h = 0 ve dh/dn = komsu yuzun egimi, yuk Height'i verecek kadar. Sonuc
# dogrudan B-spline, ayrica oturtma yok. Olculdu (yuvarlak dikdortgen, 80 x 50, 4 mm): teget hatasi 0.0005 derece, kenar
# boslugu 3e-6 mm, 0.3 s; GeomPlate 0.04 derece ama delikte ve ic bukeyde gecersiz kati ya da 0.03..0.6 mm bosluk verdi.
# Teget kubbe kenarda sifira inen ince bir dilimdir, boolean bozuluyordu (0 kati, gecersiz sonuc): yuz katinin icinde
# dogrudan degistirilir. Boolean yalniz kubbe katinin baska bir yerine degiyorsa denenir.
# Butun komsular dikse (Elliptical) yukseklik alani yetmez, egim sonsuza gider: kenar merkeze dogru kuculurken ceyrek elips
# boyunca yukselir (ellipse_patches). Tam NURBS, duvara teget hatasi 0; burada boolean sorunsuz.
import numpy as np

import FreeCAD as App
import Part

import pda_railpipe as rp
from pda_i18n import T

V = App.Vector
FREE_DEG = 60.0             # komsu bu acidan dik: teget olunamaz (egim sonsuza gider), kenar egimi serbest birakilir
CORNER_DEG = 10.0           # kenar birlesiminde bu acinin ustu kosedir: egim koseye dogru sifira iner
CELLS = (40, 56)            # kenar boslugu buyukse ikinci, ince izgara
GAP_OK = 1e-3               # mm
GAP_MAX = 0.02              # mm: izgara yuz icin kaba (cok dar bolge)
LAMBDA = 1e6
GHOST = 1e-5
MARGIN = 3                  # izgara yuzun disina tasan hucre: yuz duzgun dugum bolgesinde kalir
SUB = 5                     # hucre basina alt nokta (kesik hucrelerin integrali)


def cubic(s):
    """Duzgun kubik B-spline: hucre icinde s (0..1) icin N, N', N'' (birim hucre)."""
    s = np.asarray(s, float)
    r = 1 - s
    N = np.stack([r**3, 3*s**3 - 6*s**2 + 4, -3*s**3 + 3*s**2 + 3*s + 1, s**3], -1) / 6.0
    D = np.stack([-3*r**2, 9*s**2 - 12*s, -9*s**2 + 6*s + 3, 3*s**2], -1) / 6.0
    S = np.stack([6*r, 18*s - 12, -18*s + 6, 6*s], -1) / 6.0
    return N, D, S


def _segments(loops):
    return np.vstack([p[:-1] for p in loops]), np.vstack([p[1:] for p in loops])


def _inside_rows(X, Y, loops):
    """Cift-tek kurali, ayni y'li noktalar birlikte (izgara icin hizli)."""
    A, B = _segments(loops)
    out = np.zeros(len(X), bool)
    for y in np.unique(Y):
        k = np.nonzero(Y == y)[0]
        c = (A[:, 1] > y) != (B[:, 1] > y)
        if c.any():
            xs = np.sort(A[c, 0] + (y - A[c, 1]) * (B[c, 0] - A[c, 0]) / (B[c, 1] - A[c, 1]))
            out[k] = np.searchsorted(xs, X[k]) % 2 == 1
    return out


def _inside(P, loops):
    A, B = _segments(loops)
    res = np.zeros(len(P), bool)
    for i, (x, y) in enumerate(P):
        c = (A[:, 1] > y) != (B[:, 1] > y)
        res[i] = (A[c, 0] + (y - A[c, 1]) * (B[c, 0] - A[c, 0]) / (B[c, 1] - A[c, 1]) > x).sum() % 2 == 1
    return res


def neighbour(shape, edge, face):
    for f in shape.ancestorsOfType(edge, Part.Face):
        if not f.isSame(face):
            return f
    return None


def frame(face):
    """Duzlem cercevesi: x en uzun duz kenar boyunca (izgara kenarlarla hizali), n yuzun disa bakan normali."""
    u0, u1, v0, v1 = face.ParameterRange
    n = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
    n.normalize()
    lines = [e for e in face.Edges if e.Curve.TypeId == "Part::GeomLine"]
    if lines:
        e = max(lines, key=lambda x: x.Length)
        x = e.tangentAt(e.FirstParameter)
    else:
        P = np.array([tuple(p) for p in face.OuterWire.discretize(Number=200)])
        x = V(*(float(c) for c in np.linalg.svd(P - P.mean(axis=0))[2][0]))
    x = x - n * x.dot(n)
    x.normalize()
    return face.CenterOfGravity, x, n.cross(x), n


class Field(object):
    """Bir yuzun yukseklik alani: h = a * h1 (yuk) + b * hg (kenar egimi). Height degisince yalniz a, b degisir."""

    def __init__(self, face, shape, cells=40, tangent=True):
        self.face, self.shape, self.tangent = face, shape, tangent
        self.o, self.x, self.y, self.n = frame(face)
        self.loops = [np.array([self.to2(p) for p in w.discretize(Number=max(400, int(w.Length / 0.2)))])
                      for w in face.Wires]
        pts = np.vstack(self.loops)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        self.dx, self.dy = (hi - lo) / cells
        self.org = lo - MARGIN * np.array([self.dx, self.dy])
        self.nc = cells + 2 * MARGIN
        self.np = self.nc + 3
        self._samples()
        self._solve()

    def to2(self, p):
        d = V(p) - self.o
        return d.dot(self.x), d.dot(self.y)

    def _samples(self):
        step = min(self.dx, self.dy) / 3.0
        eps = 0.05 * min(self.dx, self.dy)
        pts, nrm, g, free = [], [], [], []
        for e in self.face.Edges:
            f = neighbour(self.shape, e, self.face)
            ts = np.linspace(e.FirstParameter, e.LastParameter, max(8, int(e.Length / step)) + 1)
            ep, ed, en2 = [], [], []
            for t in ts:
                p, d = e.valueAt(t), e.tangentAt(t)
                ep.append(self.to2(p))
                ed.append((d.dot(self.x), d.dot(self.y)))
                if f is None:
                    en2.append((0.0, 0.0, 1.0))
                else:
                    m = f.normalAt(*f.Surface.parameter(p))
                    m.normalize()
                    en2.append((m.dot(self.x), m.dot(self.y), m.dot(self.n)))
            ep, ed, en2 = np.array(ep), np.array(ed), np.array(en2)
            ed /= np.linalg.norm(ed, axis=1)[:, None]
            en = np.stack([-ed[:, 1], ed[:, 0]], 1)
            mid = np.arange(1, len(ep) - 1)
            if _inside(ep[mid] + eps * en[mid], self.loops).mean() < 0.5:   # n: yuzun icine
                en = -en
            ang = np.degrees(np.arctan2(-(en2[:, 0] * en[:, 0] + en2[:, 1] * en[:, 1]), en2[:, 2]))  # +: komsu disa dusuyor
            fr = np.abs(ang) > FREE_DEG
            gg = np.where(fr, 0.0, np.tan(np.radians(np.clip(ang, 0.0, FREE_DEG))))
            pts.append(ep), nrm.append(en), g.append(gg), free.append(fr)
        # keskin kosede iki kenarin h = 0'i egimi sifira zorlar: egim koseye dogru iner, yoksa sonuc kirisir
        cell = max(self.dx, self.dy)
        ends = [(p[k], n[k]) for p, n in zip(pts, nrm) for k in (0, -1)]
        corners = [a[0] for i, a in enumerate(ends) for b in ends[i + 1:]
                   if np.linalg.norm(a[0] - b[0]) < 1e-6 and a[1].dot(b[1]) < np.cos(np.radians(CORNER_DEG))]
        self.bp, self.bn = np.vstack(pts), np.vstack(nrm)
        self.bg, self.bfree = np.concatenate(g), np.concatenate(free)
        for c in corners:
            s = np.clip(np.linalg.norm(self.bp - c, axis=1) / (3 * cell), 0.0, 1.0)
            self.bg = self.bg * s * s * (3 - 2 * s)
        if not self.tangent:                               # oyma: komsu yukari gelmez, duz baslar
            self.bg = np.zeros_like(self.bg)

    def rows(self, P):
        """2B noktalar: kontrol noktasi indeksleri (m x 16) ve deger, d/dx, d/dy satirlari."""
        tu = (P[:, 0] - self.org[0]) / self.dx
        tv = (P[:, 1] - self.org[1]) / self.dy
        iu = np.clip(np.floor(tu).astype(int), 0, self.nc - 1)
        iv = np.clip(np.floor(tv).astype(int), 0, self.nc - 1)
        Nu, Du, _ = cubic(tu - iu)
        Nv, Dv, _ = cubic(tv - iv)
        ids = np.stack([(iu + a) * self.np + iv + b for a in range(4) for b in range(4)], 1)
        val = (Nu[:, :, None] * Nv[:, None, :]).reshape(len(P), 16)
        rx = (Du[:, :, None] * Nv[:, None, :]).reshape(len(P), 16) / self.dx
        ry = (Nu[:, :, None] * Dv[:, None, :]).reshape(len(P), 16) / self.dy
        return ids, val, rx, ry

    def _cell_ids(self, i, j):
        return np.array([(i + a) * self.np + j + b for a in range(4) for b in range(4)])

    def _solve(self):
        s = (np.arange(SUB) + 0.5) / SUB
        Ns, Ds, Ss = cubic(s)
        dx, dy = self.dx, self.dy
        area = dx * dy / SUB**2
        tab = np.zeros((SUB, SUB, 16, 16))                 # hucre ici alt noktalarin enerji tablolari: butun hucrelerde ayni
        load = np.zeros((SUB, SUB, 16))
        for a in range(SUB):
            for b in range(SUB):
                bxx = np.outer(Ss[a], Ns[b]).ravel() / dx**2
                byy = np.outer(Ns[a], Ss[b]).ravel() / dy**2
                bxy = np.outer(Ds[a], Ds[b]).ravel() / (dx * dy)
                tab[a, b] = (np.outer(bxx, bxx) + np.outer(byy, byy) + 2 * np.outer(bxy, bxy)) * area
                load[a, b] = np.outer(Ns[a], Ns[b]).ravel() * area
        cu = (np.arange(self.nc)[:, None] + s[None, :]).ravel() * dx + self.org[0]
        cv = (np.arange(self.nc)[:, None] + s[None, :]).ravel() * dy + self.org[1]
        X, Y = np.meshgrid(cu, cv, indexing="ij")
        mask = _inside_rows(X.ravel(), Y.ravel(), self.loops).reshape(X.shape)
        N = self.np**2
        A = np.zeros((N, N))
        f = np.zeros(N)
        full = tab.sum(axis=(0, 1))
        scale = dx * dy
        for i in range(self.nc):
            for j in range(self.nc):
                m = mask[i * SUB:(i + 1) * SUB, j * SUB:(j + 1) * SUB]
                if m.any():
                    ids = self._cell_ids(i, j)
                    A[np.ix_(ids, ids)] += scale * (full if m.all() else (tab * m[:, :, None, None]).sum(axis=(0, 1)))
                    f[ids] += (load * m[:, :, None]).sum(axis=(0, 1)) / scale
        ids, val, rx, ry = self.rows(self.bp)
        active = A.diagonal() > 0
        active[ids.ravel()] = True
        for i in range(self.nc):                           # hayalet ceza: kesik hucrelerde kontrol noktalari sallanmasin
            for j in range(self.nc):
                c = self._cell_ids(i, j)
                if active[c].any():
                    A[np.ix_(c, c)] += GHOST * scale * full
        np.add.at(A, (ids[:, :, None].repeat(16, 2), ids[:, None, :].repeat(16, 1)),
                  LAMBDA * val[:, :, None] * val[:, None, :])
        rn = rx * self.bn[:, 0:1] + ry * self.bn[:, 1:2]
        c = ~self.bfree
        w = LAMBDA * min(dx, dy)**2
        g = np.zeros(N)
        np.add.at(A, (ids[c][:, :, None].repeat(16, 2), ids[c][:, None, :].repeat(16, 1)),
                  w * rn[c][:, :, None] * rn[c][:, None, :])
        np.add.at(g, ids[c], w * rn[c] * self.bg[c][:, None])
        act = np.nonzero(active)[0]
        M = A[np.ix_(act, act)]
        M += 1e-12 * np.trace(M) / len(act) * np.eye(len(act))
        sol = np.linalg.solve(M, np.stack([f[act], g[act]], 1))
        h1, hg = np.zeros(N), np.zeros(N)
        h1[act], hg[act] = sol[:, 0], sol[:, 1]
        gi, gv, _, _ = self.rows(np.stack([X[mask], Y[mask]], 1))
        z1 = (h1[gi] * gv).sum(axis=1)
        h1 /= np.abs(z1).max()
        self.h1, self.hg = h1, hg
        self.z1, self.zg = z1 / np.abs(z1).max(), (hg[gi] * gv).sum(axis=1)

    def coefficients(self, height):
        """Tepe Height olacak sekilde (a, b). Komsu egimi bu yukseklige gore fazla dikse b < 1: egim tutmaz, yuzey kenarda
        sirt yapip ortada cukurlasmak yerine duz kalir."""
        top = self.zg.max() if self.zg.size else 0.0
        b = min(1.0, 0.9 * height / top) if top > 0 else 1.0
        lo, hi = 0.0, 4.0 * height + 1.0
        for _ in range(50):
            a = (lo + hi) / 2
            if (a * self.z1 + b * self.zg).max() > height:
                hi = a
            else:
                lo = a
        return (lo + hi) / 2, b

    def surface(self, height, sign=1.0):
        a, b = self.coefficients(height)
        c = (sign * (a * self.h1 + b * self.hg)).reshape(self.np, self.np)
        gx = self.org[0] + self.dx * (np.arange(self.np) - 1.0)
        gy = self.org[1] + self.dy * (np.arange(self.np) - 1.0)
        poles = [[self.o + self.x * float(gx[i]) + self.y * float(gy[j]) + self.n * float(c[i, j])
                  for j in range(self.np)] for i in range(self.np)]
        ku = [float(self.org[0] + self.dx * (k - 3)) for k in range(self.np + 4)]
        kv = [float(self.org[1] + self.dy * (k - 3)) for k in range(self.np + 4)]
        s = Part.BSplineSurface()
        s.buildFromPolesMultsKnots(poles, [1] * len(ku), [1] * len(kv), ku, kv, False, False, 3, 3)
        s.segment(ku[3], ku[self.nc + 3], kv[3], kv[self.nc + 3])    # uclari kenetli: STEP okuyuculari icin
        return s


def trim(surf, face):
    """Yuzeyi yuzun kendi kenarlarina oturt: kenarlar ayni kalir, komsu yuzlerle ortak olur."""
    d = Part.Face(surf, face.OuterWire)
    inner = [w for w in face.Wires if not w.isSame(face.OuterWire)]
    if inner:
        d.fix(1e-3, 1e-5, 1e-2)                            # pcurve'ler olmadan delik acilmiyor
        d.cutHoles(inner)
    d.fix(1e-3, 1e-5, 1e-2)
    return d


def gap_of(surf, face, fld):
    out = 0.0
    for e in face.Edges:
        for t in np.linspace(e.FirstParameter, e.LastParameter, 25):
            p = e.valueAt(float(t))
            out = max(out, (surf.value(*fld.to2(p)) - p).Length)
    return out


def tangent_error(dome, face, shape, fld):
    """Kenarlarda komsu yuze gore en buyuk aci (derece), teget olunabilen kenarlar uzerinde; dik duvar sayisi."""
    S = dome.Surface
    worst, steep = 0.0, 0
    for e in face.Edges:
        f = neighbour(shape, e, face)
        if f is None:
            continue
        err = []
        for t in np.linspace(e.FirstParameter, e.LastParameter, 11)[1:-1]:
            p = e.valueAt(float(t))
            m, m2 = S.normal(*fld.to2(p)), f.normalAt(*f.Surface.parameter(p))
            err.append((np.degrees(np.arccos(min(1.0, abs(m.dot(m2) / (m.Length * m2.Length))))),
                        abs(m2.dot(frame_normal(face))) / m2.Length))
        if min(c for _, c in err) < np.cos(np.radians(FREE_DEG)):
            steep += 1
        else:
            worst = max(worst, max(a for a, _ in err))
    return worst, steep


def frame_normal(face):
    u0, u1, v0, v1 = face.ParameterRange
    return face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)


def can_ellipse(face, shape):
    """Dik duvarli kubbe olur mu: tek dis cizgi, merkezden her kenar noktasi gorunur, butun komsular dik. Merkez (yuzun
    agirlik merkezi) ya da hata degil None."""
    if len(face.Wires) != 1:
        return None
    n = frame_normal(face)
    n.normalize()
    c = face.CenterOfGravity
    turn = []
    for e in face.Edges:
        f = neighbour(shape, e, face)
        if f is None:
            return None
        for t in np.linspace(e.FirstParameter, e.LastParameter, 21):
            p = e.valueAt(float(t))
            m = f.normalAt(*f.Surface.parameter(p))
            if abs(m.dot(n)) / m.Length > np.cos(np.radians(FREE_DEG)):
                return None
            turn.append(((p - c).cross(e.tangentAt(float(t))).dot(n)) * (-1.0 if e.Orientation == "Reversed" else 1.0))
    turn = np.array(turn)
    # merkezden bakinca kenar hep ayni yone donmeli; duz kenar merkezden geciyorsa 0 olur, o da olmaz
    size = face.BoundBox.DiagonalLength
    return c if (turn > 1e-6 * size).all() or (turn < -1e-6 * size).all() else None


def ellipse_patches(face, center, height, sign):
    """Her kenar icin bir yama: kenar egrisi merkeze dogru kuculurken ceyrek elips boyunca yukselir. Yay ve egri carpimi
    tam NURBS: sinir kenarin kendisi, duvardaki teget tam yuzey normali yonunde. Yamalar tepede tek noktada bulusur;
    keskin kose tepeye kadar sirt olarak gider."""
    n = frame_normal(face)
    n.normalize()
    arc = ((1.0, 0.0, 1.0), (1.0, 1.0, np.sqrt(0.5)), (0.0, 1.0, 1.0))  # (olcek, yukseklik, agirlik)
    out = []
    for e in face.Edges:
        for cv in _smooth_spans(e):
            P, W = cv.getPoles(), cv.getWeights()
            poles = [[center + (p - center) * s + n * (sign * height * z) for p in P] for s, z, _ in arc]
            weights = [[w * float(a) for w in W] for _, _, a in arc]
            s = Part.BSplineSurface()
            s.buildFromPolesMultsKnots(poles, [3, 3], cv.getMultiplicities(), [0.0, 1.0], cv.getKnots(), False, False,
                                       2, cv.Degree, weights)
            out.append((e, s))
    return out


def _smooth_spans(edge):
    """Kenarin NURBS'u, parametrik C0 dugumlerinde bolunmus. Daire / elips bu dugumlerle gelir: tek yamada BOP C0 hatasi
    verdi ve STEP'ten donen hacim 46..120 mm3 saptı."""
    a, b, cv = edge.FirstParameter, edge.LastParameter, edge.Curve
    if cv.TypeId in ("Part::GeomCircle", "Part::GeomEllipse"):
        cuts = list(np.linspace(a, b, int(np.ceil((b - a) / (np.pi / 2) - 1e-9)) + 1))   # parametre radyan: ceyrek basina tek aralik
    elif cv.TypeId == "Part::GeomBSplineCurve":
        inner = [k for k, m in zip(cv.getKnots(), cv.getMultiplicities()) if m >= cv.Degree and a + 1e-9 < k < b - 1e-9]
        cuts = [a] + inner + [b]
        if len(cuts) == 2 and edge.isClosed():             # kapali ama duzgun: dikis tek yamada kalmasin
            cuts.insert(1, (a + b) / 2.0)
    else:
        cuts = [a, b]
    out = []
    for p, q in zip(cuts[:-1], cuts[1:]):
        c = cv.toBSpline(float(p), float(q))
        if c.isPeriodic():
            c.setNotPeriodic()
        out.append(c)
    return out


def ellipse_tool(face, patches):
    shapes = [s.toShape() for _, s in patches]
    rims = [Part.Edge(s.uIso(0.0)) for _, s in patches]
    cap = Part.Face(Part.Wire(Part.__sortEdges__(rims)))   # kenarlar yamalarla ayni bolunmede
    sh = Part.Shell(shapes + [cap])
    sh.sewShape()
    sol = Part.Solid(sh)
    if sol.Volume < 0:
        sol.reverse()
    return sol


def ellipse_error(face, shape, patches):
    """Duvardaki en buyuk aci (derece): yama normali ile komsu yuz normali."""
    worst = 0.0
    for e, s in patches:
        f = neighbour(shape, e, face)
        v0, v1 = s.bounds()[2:]
        for t in np.linspace(0.02, 0.98, 25):
            q = s.value(0.0, v0 + (v1 - v0) * float(t))
            a, b = s.normal(0.0, v0 + (v1 - v0) * float(t)), f.normalAt(*f.Surface.parameter(q))
            worst = max(worst, np.degrees(np.arccos(min(1.0, abs(a.dot(b)) / (a.Length * b.Length)))))
    return worst


def read_face(link):
    """(nesne, yuz) ya da hata metni."""
    if not link or link[0] is None or not link[1]:
        return "Dome: the face is missing"
    try:
        f = link[0].Shape.getElement(link[1][0])
    except Exception:
        return "Dome: the face is missing"
    if f.ShapeType != "Face" or f.Surface.TypeId != "Part::GeomPlane":
        return "Dome: the face must be flat"
    return link[0], f


def same_face(shape, face):
    """Bir sekilde ayni geometrideki yuz: secim eski bir adimin yuzu olabilir, degistirilecek yuz son govdede."""
    c, a = face.CenterOfGravity, face.Area
    for f in shape.Faces:
        if f.isSame(face):
            return f
    for f in shape.Faces:
        if f.Surface.TypeId == "Part::GeomPlane" and abs(f.Area - a) < 1e-6 * max(a, 1.0) \
                and (f.CenterOfGravity - c).Length < 1e-5 and len(f.Edges) == len(face.Edges):
            return f
    return None


def lens(dome, face):
    """AddSubShape ve hacim denetimi icin: kubbe + duz yuz."""
    sh = Part.Shell([dome, face.copy()])
    sh.sewShape()
    sol = Part.Solid(sh)
    if sol.Volume < 0:
        sol.reverse()
    return sol


def replace_face(base, face, dome):
    """Katida yuzu kubbeyle degistir. Diger katilar oldugu gibi kalir. Gecersizse None."""
    target = next((s for s in base.Solids if any(f.isSame(face) for f in s.Faces)), None)
    if target is None:
        return None
    sh = Part.Shell([dome if f.isSame(face) else f for f in target.Faces])
    sh.sewShape()
    sol = Part.Solid(sh)
    if sol.Volume < 0:
        sol.reverse()
    if not sol.isValid():
        return None
    rest = [s for s in base.Solids if not s.isSame(target)]
    return sol if not rest else Part.makeCompound(rest + [sol])


def collides(base, dome, face, sign, fld):
    """Kubbe katinin baska bir yerine degiyor mu: eklerken yuzey katinin disinda, oyarken icinde kalmali."""
    u0, u1, v0, v1 = face.ParameterRange
    S = dome.Surface
    n = frame_normal(face)
    n.normalize()
    for i in range(1, 8):                                  # isInside kavisli govdede pahali: az nokta yeter
        for j in range(1, 8):
            q = face.Surface.value(u0 + (u1 - u0) * i / 8.0, v0 + (v1 - v0) * j / 8.0)
            if not face.isInside(q, 1e-6, False):
                continue
            p = S.value(*fld.to2(q))
            if abs((p - q).dot(n)) < 1e-2:
                continue
            if base.isInside(p, 1e-6, False) != (sign < 0):
                return True
    return False


def elliptical_prop(obj):
    if "Elliptical" not in obj.PropertiesList:
        obj.addProperty("App::PropertyBool", "Elliptical", "Dome",
                        "Next to steep walls: start tangent to the walls (bullet shape). Off: a smooth bump with a free "
                        "slope at the edges")


class Dome:
    """Dome (FeatureAdditivePython). Reversed: kubbe yuzun altina, oyma."""

    def __init__(self, obj):
        obj.addProperty("App::PropertyLinkSub", "Face", "Dome", "Flat face to raise")
        obj.addProperty("App::PropertyLength", "Height", "Dome", "Height of the dome above the face").Height = 4.0
        obj.addProperty("App::PropertyBool", "Reversed", "Dome", "Dome into the solid (a cut) instead of out of it")
        elliptical_prop(obj)
        obj.Elliptical = True
        obj.addProperty("App::PropertyAngle", "TangentError", "Dome",
                        "Largest angle to the neighbouring faces along the edges it can be tangent to")
        obj.addProperty("App::PropertyInteger", "SteepEdges", "Dome",
                        "Edges next to a wall too steep to be tangent to (the slope there is free)")
        for n in ("TangentError", "SteepEdges"):
            obj.setPropertyStatus(n, ["ReadOnly", "Output"])
        if "Refine" not in obj.PropertiesList:
            obj.addProperty("App::PropertyBool", "Refine", "Base", "Merge coplanar faces of the result")
        obj.Proxy = self

    def ellipse(self, obj, base, face, center, height, sign):
        """Dik duvara teget kubbe. Boolean olmaz, duz plaka yuzeyine donulur: False."""
        try:
            patches = ellipse_patches(face, center, height, sign)
            tool = ellipse_tool(face, patches)
            if not tool.isValid():
                return False
            res = None
            for fuzzy in (1e-5, 1e-3):
                r = rp._combine(base, tool, obj.Reversed, getattr(obj, "Refine", False), fuzzy)
                if r is not None and r[1]:
                    res = r[0]
                    break
        except Exception:
            return False
        if res is None:
            return False
        obj.TangentError = ellipse_error(face, base, patches)
        obj.SteepEdges = 0
        obj.AddSubShape = tool
        obj.Shape = res
        return True

    def field(self, obj, face, shape):
        """Ayni yuz icin cozum saklanir: Height ve surukleme 0.3 s yerine ~30 ms."""
        tangent = not obj.Reversed
        key = (shape.hashCode(), face.hashCode(), tangent)
        c = getattr(self, "_cache", None)
        if c is not None and c[0] == key:
            return c[1]
        fld = Field(face, shape, CELLS[0], tangent)
        if gap_of(fld.surface(1.0), face, fld) > GAP_OK:        # olcek 1 mm: bosluk h ile orantili
            fld = Field(face, shape, CELLS[1], tangent)
        self._cache = (key, fld)
        return fld

    def execute(self, obj):
        got = read_face(obj.Face)
        if isinstance(got, str):
            raise RuntimeError(T(got))
        base = rp._base(obj)
        if base is None or not base.Solids:
            raise RuntimeError(T("Dome: the Body has no solid yet"))
        face = same_face(base, got[1])
        if face is None:
            raise RuntimeError(T("Dome: the face is not on the previous solid; select it again on the last feature"))
        height = float(obj.Height)
        if height <= 0:
            raise RuntimeError(T("Dome: the height must be above zero"))
        sign = -1.0 if obj.Reversed else 1.0
        center = can_ellipse(face, base) if obj.Elliptical else None
        if center is not None and self.ellipse(obj, base, face, center, height, sign):
            return
        # kopya: pcurve ve tolerans kenarlara yerinde yazilir, onceki adimin sekli bozulmasin (Rail Pipe'taki gibi)
        work = base.copy()
        wface = work.Faces[next(i for i, f in enumerate(base.Faces) if f.isSame(face))]
        try:
            fld = self.field(obj, face, base)
            surf = fld.surface(height, sign)
            dome = trim(surf, wface)
            gap = gap_of(surf, face, fld)
            # kenarlar yuzeyden bu kadar uzak: duz kenarlarda BOP denetimi temiz gecer. fixTolerance degil: toleransi fix'in
            # buldugunun altina indirince delikli yuzde kati gecersiz oluyordu
            dome.limitTolerance(max(4.0 * gap, 1e-5), 1.0, Part.Edge)
        except Exception as e:
            raise RuntimeError(T("Dome: the surface failed (%s)") % e)
        if not dome.isValid():
            raise RuntimeError(T("Dome: the surface failed (%s)") % "invalid face")
        if gap > GAP_MAX * max(height, 1.0):
            raise RuntimeError(T("Dome: the outline has parts too narrow for the surface"))
        tool = lens(dome, wface)
        res = None
        if not collides(base, dome, face, sign, fld):
            res = replace_face(work, wface, dome)
        if res is None:                                    # baska bir yere degiyor: gercek boolean
            for fuzzy in (1e-3, 0.01):
                try:
                    r = rp._combine(base, tool, obj.Reversed, getattr(obj, "Refine", False), fuzzy)
                except Exception:
                    r = None
                if r is not None and r[1]:
                    res = r[0]
                    break
        if res is None:
            raise RuntimeError(T("Dome: the dome runs into another part of the solid; lower the height"))
        err, steep = tangent_error(dome, face, base, fld)
        obj.TangentError = err
        obj.SteepEdges = steep
        obj.AddSubShape = tool
        obj.Shape = res

    def onDocumentRestored(self, obj):
        elliptical_prop(obj)

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderDome:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def doubleClicked(self, vobj):
        import FreeCADGui as Gui
        Gui.ActiveDocument.setEdit(vobj.Object, 0)
        return True

    def setEdit(self, vobj, mode=0):
        if mode != 0:
            return None
        import pda_dome_gui
        pda_dome_gui.start(vobj.Object)
        return True

    def unsetEdit(self, vobj, mode=0):
        if mode != 0:
            return None
        import pda_dome_gui
        pda_dome_gui.stop()
        return True

    def getIcon(self):
        import os
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "pda_dome.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None


def make(body, target, sub):
    """Body'de yeni Dome. Yuz son govdede varsa ona baglanir. Nesne ya da hata metni (nesne olusturulmaz)."""
    got = read_face((target, [sub]))
    if isinstance(got, str):
        return got
    tip = body.Tip
    if tip is None or tip.Shape.isNull() or not tip.Shape.Solids:
        return "Dome: the Body has no solid yet"
    face = same_face(tip.Shape, got[1])
    if face is None:
        return "Dome: the face is not on the previous solid; select it again on the last feature"
    idx = next(i for i, f in enumerate(tip.Shape.Faces) if f.isSame(face))
    obj = body.newObject("PartDesign::FeatureAdditivePython", "Dome")
    Dome(obj)
    obj.Face = (tip, ["Face%d" % (idx + 1)])
    if App.GuiUp:
        ViewProviderDome(obj.ViewObject)
        rp._fine_display(obj)
    return obj


def is_dome(o):
    props = getattr(o, "PropertiesList", [])
    return "SteepEdges" in props and "TangentError" in props


def repair_proxies(doc):
    """Proxy'si kopmus Dome nesnelerini onar (FreeCAD bazen eklenti modulunu belge acilirken aktaramiyor)."""
    fixed = []
    for o in (doc.Objects if doc is not None else []):
        if is_dome(o) and not isinstance(getattr(o, "Proxy", None), Dome):
            o.Proxy = Dome.__new__(Dome)
            if App.GuiUp and not isinstance(getattr(o.ViewObject, "Proxy", None), ViewProviderDome):
                o.ViewObject.Proxy = ViewProviderDome.__new__(ViewProviderDome)
            o.touch()
            fixed.append(o)
    for o in fixed:
        o.recompute()
    return fixed
