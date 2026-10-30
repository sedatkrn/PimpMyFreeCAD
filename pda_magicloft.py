# -*- coding: utf-8 -*-
# Pimp My PartDesign - Magic Loft / Magic Loft Cut: PartDesign features (Body icinde Pad / Pocket gibi bir adim) ve Part
# katisi. Copyright (c) 2026 Sedat Kuran - MIT License
#
# En az iki kapali kesit (duz yuz, kapali sketch, Binder, kapali kenar halkasi; halka duzlemsel olmak zorunda degil)
# arasinda az kontrol noktali tek yuzey. Rehberler ya secilen sketch / egrilerdir ya da otomatik olusur (ekranda
# duzenlenir): "Hazir rehber ciz" kutusu ikisini ayirir, pasif moddaki veriler saklanir.
# Yuzey Gordon bicimindedir: S(u, v) = S1(u, v) + toplam L_j(u) D_j(v). S1 kesitlerden v yonunde C2 kubik spline,
# L_j rehber konumlarinda 1 / 0 olan periyodik kardinal fonksiyonlar, D_j rehberin S1'den farki. Sonuc numpy ile
# hesaplanir ve tek kubik B-spline'a oturtulur (OCCT supurmesi yok): ~10 ms, Thickness'tan gecer. Koseli profilde
# kose basina ayri yama (koseler keskin kalir). GUI gerektirmez: belge freecadcmd ile de yeniden hesaplanir.
import math

import numpy as np

import FreeCAD as App
import Part

import pda_railpipe as rp
from pda_i18n import T

V = App.Vector
PROPS = "AutoGuideOffsets"  # bu ozellik varsa nesne Magic Loft'tur (onarim)
M = 720                     # kesit basina ornek sayisi
ENDS = ["Free", "Normal", "Tangent"]
TOUCH_TOL = 0.05            # secilen rehber kesite en fazla bu kadar uzak olabilir (mm)
CORNER_DEG = 15.0           # kenar birlesiminde bu acinin ustu kosedir


def _np(v):
    return np.array(tuple(v), float)


# --- baglantilar ---
def links(items):
    """[(nesne, [alt elemanlar])] -> PropertyLinkSubList degeri + her ogenin alt eleman sayisi. Ozellik art arda gelen
    ayni nesneyi birlestirdiginden ogeler boyutlarla ayrilir."""
    val, sizes = [], []
    for o, subs in items:
        subs = list(subs or [])
        val += [(o, s) for s in subs] or [(o, "")]
        sizes.append(max(len(subs), 1))
    return val, sizes


def unlinks(val, sizes):
    flat = []
    for o, subs in val:
        subs = [subs] if isinstance(subs, str) else list(subs or [])
        flat += [(o, s) for s in subs] or [(o, "")]
    out, k = [], 0
    for n in sizes:
        part = flat[k:k + n]
        k += n
        if part:
            out.append((part[0][0], [s for _, s in part if s]))
    return out


def get_items(obj, name):
    return unlinks(getattr(obj, name), list(getattr(obj, name + "Sizes")))


def set_items(obj, name, items):
    val, sizes = links(items)
    setattr(obj, name, val)
    setattr(obj, name + "Sizes", sizes)


# --- profil okuma ---
def _nonplanar(w):
    """Duzlemsel olmayan kapali tel: (tel, agirlik merkezi, en iyi oturan duzlemin normali, False)."""
    P = np.array([tuple(p) for p in w.discretize(Number=193)[:192]])
    c = P.mean(axis=0)
    n = np.linalg.svd(P - c)[2][2]
    return w, V(*c), V(*n), False


def read_profile(o, subs, glob):
    """Kesit: (tel, merkez, normal, katinin yuzu mu) ya da hata metni. Rail Pipe'in profili; ek olarak 3B halka."""
    sh = None
    try:
        sh = rp._shape(o, None, glob)
    except Exception:
        pass
    if subs and subs[0].startswith("Edge"):
        loops = rp.edge_loops([sh.getElement(s) for s in subs])
        if len(loops) != 1:
            return "Rail Pipe: the selected edges must form one closed loop"
        res = rp._edge_profile(sh, subs)
        return _nonplanar(loops[0]) if isinstance(res, str) else res
    res = rp.profile((o, subs), glob)
    if isinstance(res, str) and not subs and sh is not None and not sh.Faces and sh.Edges:   # 3B halkanin Binder'i
        loops = rp.edge_loops(sh.Edges)
        if loops:
            return _nonplanar(max(loops, key=lambda x: x.BoundBox.DiagonalLength))
    return res


def _samples(w):
    """Telin ornekleri (kapali, son = ilk), yay boyu oranlari ve koseler (oran). Koseler tam ornek noktasindadir."""
    E = w.OrderedEdges
    total = sum(e.Length for e in E)
    pts = []
    for i, e in enumerate(E):
        q = [_np(p) for p in e.discretize(Number=max(2, int(round(M * e.Length / total))) + 1)]
        if pts:
            if np.linalg.norm(q[-1] - pts[-1]) < np.linalg.norm(q[0] - pts[-1]):
                q.reverse()
            q = q[1:]
        elif len(E) > 1:                                   # ilk kenarin yonu: sonu ikinci kenara degmeli
            nxt = [_np(v.Point) for v in E[1].Vertexes]
            if min(np.linalg.norm(q[0] - x) for x in nxt) < min(np.linalg.norm(q[-1] - x) for x in nxt):
                q.reverse()
        pts += q
    P = np.array(pts)
    if np.linalg.norm(P[0] - P[-1]) > 1e-9:
        P = np.vstack([P, P[:1]])
    L = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(L)]) / L.sum()
    corners = []
    if len(E) > 1:
        acc, k = 0.0, []
        for e in E:
            k.append(acc)
            acc += e.Length / total
        for f in k:
            i = int(np.argmin(np.abs(s - f)))
            a, b = P[i] - P[i - 1 if i else -2], P[(i + 1) % (len(P) - 1)] - P[i]
            cs = a.dot(b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12)
            if cs < math.cos(math.radians(CORNER_DEG)):
                corners.append(float(s[i]))
    return P, s, corners


class Section(object):
    """Kesit: ornekler + dikis kaydirmasi (shift). at(u): yay boyu orani u'daki nokta."""

    def __init__(self, prof):
        self.wire, c, n, self.solid = prof
        self.P, self.s, self.corners = _samples(self.wire)
        self.c = self.P[:-1].mean(axis=0)
        self.shift = 0.0
        self.tan = None                                    # yuzeye teget: oran basina birim yon
        d = self.P[:-1] - self.c
        self.n = np.cross(d, np.roll(d, -1, axis=0)).sum(axis=0)
        self.n /= max(np.linalg.norm(self.n), 1e-12)

    def flip(self):
        self.P, self.s = self.P[::-1].copy(), 1.0 - self.s[::-1]
        self.corners = [(1.0 - c) % 1.0 for c in self.corners]
        self.n = -self.n

    def at(self, u):
        x = (np.asarray(u, float) + self.shift) % 1.0
        return np.stack([np.interp(x, self.s, self.P[:, k]) for k in range(3)], axis=-1)

    def aligned_corners(self):
        return sorted((c - self.shift) % 1.0 for c in self.corners)

    def nearest(self, p):
        """p'ye en yakin ornegin (kaydirmali) orani ve uzakligi; dogru parcasina izdusumle."""
        a, b = self.P[:-1], self.P[1:]
        d = b - a
        t = np.clip(((p - a) * d).sum(axis=1) / np.maximum((d * d).sum(axis=1), 1e-18), 0, 1)
        q = a + d * t[:, None]
        r = np.linalg.norm(q - p, axis=1)
        i = int(np.argmin(r))
        return (self.s[i] + (self.s[i + 1] - self.s[i]) * t[i] - self.shift) % 1.0, float(r[i])


def _align(secs):
    """Kesitler ayni yonde doner ve dikisler hizalanir (obur kesitin cercevesine tasinip en kucuk kareler)."""
    axis = secs[1].c - secs[0].c
    if secs[0].n.dot(axis) < 0:
        secs[0].flip()
    u = np.arange(90) / 90.0
    ts = np.arange(360) / 360.0
    for a, b in zip(secs, secs[1:]):
        chord = (b.c - a.c) / max(np.linalg.norm(b.c - a.c), 1e-12)
        if b.n.dot(a.n + chord) < 0:                       # 90 derece kesitte a.n yon vermez: yol yonu de sayilir
            b.flip()
        R = App.Rotation(V(*a.n), V(*b.n))
        pa = a.at(u) - a.c
        pa = np.array([tuple(R.multVec(V(*p))) for p in pa]) / max(np.sqrt((pa * pa).sum(axis=1).mean()), 1e-9)
        best = None
        pb = b.at(np.arange(720) / 720.0) - b.c
        pb /= max(np.sqrt((pb * pb).sum(axis=1).mean()), 1e-9)
        idx = (u[None, :] * 720 + ts[:, None] * 720).astype(int) % 720
        cost = ((pb[idx] - pa[None, :, :]) ** 2).sum(axis=(1, 2))
        best = int(np.argmin(cost))
        b.shift = float(ts[best])


# --- taban fonksiyonlari ---
_periodic = {}


def _periodic_inv(N):
    """Periyodik kubik B-spline'in k / N noktalarindaki taban matrisinin tersi ve yarim noktalardaki taban (OCCT'den)."""
    if N not in _periodic:
        c = Part.BSplineCurve()
        c.buildFromPolesMultsKnots([V(1 if k == 0 else 0, 0, 0) for k in range(N)], [1] * (N + 1),
                                   [k / float(N) for k in range(N + 1)], True, 3)
        a = np.array([c.value(k / float(N)).x for k in range(N)])
        h = np.array([c.value((k + 0.5) / N).x for k in range(N)])
        ind = np.arange(N)
        _periodic[N] = (np.linalg.inv(a[(ind[:, None] - ind[None, :]) % N]), h[(ind[:, None] - ind[None, :]) % N])
    return _periodic[N]


def _knots(N):
    return np.concatenate([[0, 0, 0], np.linspace(0, 1, N - 2), [1, 1, 1]])


def _basis(N, q):
    """Kubik, uclari kenetli B-spline tabani (Cox-de Boor): (len(q), N)."""
    t = _knots(N)
    q = np.asarray(q, float)
    B = np.zeros((len(q), N + 3))
    for i in range(N + 3):
        B[:, i] = ((t[i] <= q) & (q < t[i + 1])).astype(float)
    B[q >= 1.0, :] = 0
    B[q >= 1.0, N - 1] = 1
    for d in range(1, 4):
        for i in range(N + 3 - d):
            a = (q - t[i]) / (t[i + d] - t[i]) if t[i + d] > t[i] else 0 * q
            b = (t[i + d + 1] - q) / (t[i + d + 1] - t[i + 1]) if t[i + d + 1] > t[i + 1] else 0 * q
            B[:, i] = a * B[:, i] + b * B[:, i + 1]
    return B[:, :N]


def _greville(N, nodes=()):
    t = _knots(N)
    g = np.array([t[i + 1:i + 4].mean() for i in range(N)])
    for v in nodes:                                        # kesitler izgaranin uzerinde: yuzey onlardan gecer
        g[int(np.argmin(np.abs(g - v)))] = v
    return g


def spline_weights(vn, vq, clamp0, clamp1):
    """vn dugumlerinden gecen C2 kubik: uclar dogal ya da kenetli. Agirliklar (len(vq), len(vn) + 2); son ikisi uc
    tegetleri. Serbest tek parca dogrudur."""
    vn = np.asarray(vn, float)
    vq = np.asarray(vq, float)
    m = len(vn)
    h = np.diff(vn)
    A = np.zeros((m, m))
    Ry = np.zeros((m, m + 2))
    for i in range(1, m - 1):
        A[i, i - 1:i + 2] = h[i - 1], 2 * (h[i - 1] + h[i]), h[i]
        Ry[i, i - 1:i + 2] = 6 / h[i - 1], -6 / h[i - 1] - 6 / h[i], 6 / h[i]
    if clamp0:
        A[0, :2] = 2 * h[0], h[0]
        Ry[0, 0], Ry[0, 1], Ry[0, m] = -6 / h[0], 6 / h[0], -6
    else:
        A[0, 0] = 1
    if clamp1:
        A[-1, -2:] = h[-1], 2 * h[-1]
        Ry[-1, m - 2], Ry[-1, m - 1], Ry[-1, m + 1] = 6 / h[-1], -6 / h[-1], 6
    else:
        A[-1, -1] = 1
    S = np.linalg.solve(A, Ry)                             # (m, m + 2) ikinci turevler
    k = np.clip(np.searchsorted(vn, vq, side="right") - 1, 0, m - 2)
    a = (vn[k + 1] - vq) / h[k]
    c = (vq - vn[k]) / h[k]
    W = (((a ** 3 - a) * h[k] ** 2 / 6)[:, None] * S[k] + ((c ** 3 - c) * h[k] ** 2 / 6)[:, None] * S[k + 1])
    ind = np.arange(len(vq))
    W[ind, k] += a
    W[ind, k + 1] += c
    return W


def _cardinal(us):
    """Periyodik kardinal fonksiyonlar: rehber konumlarinda 1 / 0. fn(u) -> (len(u), n)."""
    w = 0.5 if len(us) < 3 else 1.0 / len(us)
    d = lambda a, b: np.exp(-(np.sin(np.pi * (a[:, None] - b[None, :])) / w) ** 2)
    Ki = np.linalg.inv(d(us, us))
    return lambda u: d(np.asarray(u, float), us).dot(Ki)


class Rail(object):
    """Secilen rehber: tel uzerinde esit aralikli noktalar."""

    def __init__(self, wire):
        self.wire = wire
        self.P = np.array([tuple(p) for p in wire.discretize(Number=801)], float)
        self.frac = np.linspace(0, 1, 801)

    def at(self, a):
        return np.stack([np.interp(a, self.frac, self.P[:, k]) for k in range(3)], axis=-1)


def read_rails(items, glob):
    """Secilen rehberlerden teller: her ayri acik zincir bir rehber. (liste) ya da hata metni."""
    rails = []
    for o, subs in items:
        sh = rp._shape(o, None, glob)
        edges = [sh.getElement(s) for s in subs] if subs else sh.Edges
        for chain in Part.sortEdges(edges):
            w = Part.Wire(chain)
            if w.isClosed():
                return "Magic Loft: a guide must be an open curve (%s)" % o.Label
            rails.append(Rail(w))
    return rails


# --- yuzey ---
class Skin(object):
    """Kesitler + rehberler -> nokta izgarasi, B-spline yuzeyler, kati. Profiller bir kez okunur; sonrasi yalniz numpy."""

    def __init__(self, secs, t0=None, t1=None, tails=(0.0, 0.0), tol=0.02):
        self.secs = secs
        self.tol = tol
        _align(secs)
        c = [s.c for s in secs]
        L = np.concatenate([[0.0], np.cumsum([np.linalg.norm(c[i + 1] - c[i]) for i in range(len(c) - 1)])])
        if L[-1] < 1e-9:
            raise ValueError("Magic Loft: the profiles are on top of each other")
        self.L = float(L[-1])
        self.vn = L / L[-1]
        self.t0, self.t1 = t0, t1                          # None, sabit yon (3) ya da "tan": kesitin tan tablosu
        self.tails = (tails[0] / self.L, tails[1] / self.L)  # uzantilar v biriminde
        self.base_conn = [s.shift for s in secs]
        self.rails = []
        self.auto = None
        self.us = np.zeros(0)
        self.card = None
        self.S = self.A = None
        self._match()

    # kose eslestirme: en cok koseli kesit referans; obur koseler en yakin kirilmaya baglanir
    def _match(self):
        ref = max(self.secs, key=lambda s: len(s.corners))
        br = list(ref.aligned_corners())
        self.ckeys = [[] for _ in self.secs]
        for s in self.secs:
            used = set()
            for c in s.aligned_corners():
                best = None
                for j, b in enumerate(br):
                    d = abs((c - b + 0.5) % 1.0 - 0.5)
                    if j not in used and d < 0.5 / max(len(br), 1) and (best is None or d < best[0]):
                        best = (d, j)
                if best is None:                           # eslesmeyen kose: yeni kirilma
                    br.append(c)
                    used.add(len(br) - 1)
                    self.ckeys[self.secs.index(s)].append((c, c))
                else:
                    used.add(best[1])
                    self.ckeys[self.secs.index(s)].append((br[best[1]], c))
        self.breaks = sorted(br)
        self.corner_mismatch = len(set(len(s.corners) for s in self.secs)) > 1

    def set_connector(self, i, value):
        """Dikis duzeltmesi (yay boyu orani): kesit i, otomatik hizalamaya gore."""
        self.secs[i].shift = (self.base_conn[i] + value) % 1.0
        self._match()

    def set_rails(self, rails):
        """Secilen rehberler. Her biri her kesite degmeli; u konumu kesitlerdeki konumlarin ortalamasi. Hata metni ya
        da None."""
        self.rails, self.auto = [], None
        if not rails:
            self.us, self.card = np.zeros(0), None
            return None
        S = np.zeros((len(self.secs), len(rails)))
        A = np.zeros_like(S)
        for j, r in enumerate(rails):
            for i, sec in enumerate(self.secs):
                d, pts, _ = r.wire.distToShape(sec.wire)
                if d > TOUCH_TOL:
                    return T("Magic Loft: guide %d is %.3f mm away from profile %d") % (j + 1, d, i + 1)
                pr, ps = _np(pts[0][0]), _np(pts[0][1])
                S[i, j] = sec.nearest(ps)[0]
                A[i, j] = r.frac[int(np.argmin(np.linalg.norm(r.P - pr, axis=1)))]
        for i in range(1, S.shape[0]):
            S[i] += np.round(S[0] - S[i])
        us = S.mean(axis=0) % 1.0
        for j in range(len(us)):                           # kosedeki rehber: yama siniri rehberin uzerinde
            for b in self.breaks:
                if abs((us[j] - b + 0.5) % 1.0 - 0.5) < 0.01:
                    us[j] = b
        order = np.argsort(us)
        self.us, self.S, self.A = us[order], S[:, order], A[:, order]
        self.rails = [rails[k] for k in order]
        self.card = _cardinal(self.us)
        # koseli olmayan kesitte eslesme yumusak: parca parca dogrusal esleme yuzeye hiz kirigi birakiyor, kontrol noktasi
        # tavana dayaniyordu (128). Geri donen (katlanan) esleme olursa dogrusala donulur.
        x = np.arange(720) / 720.0
        self.smooth = [not self.ckeys[i] and
                       bool((np.diff(x + self.card(x).dot(self._rail_off(i))) > 0).all()) for i in range(len(self.secs))]
        return None

    def _rail_off(self, i):
        off = self.S[i] - self.us
        return off - np.round(off)

    def auto_us(self, n):
        """n otomatik rehberin konumu: once koseler, yoksa esit aralik."""
        br = list(self.breaks)
        if not br:
            return np.arange(n) / float(n)
        if len(br) >= n:
            out = []
            for k in range(n):
                t = (br[0] + k / float(n)) % 1.0
                c = min((b for b in br if b not in out), key=lambda b: abs((b - t + 0.5) % 1.0 - 0.5))
                out.append(c)
            return np.array(sorted(out))
        while len(br) < n:                                 # kose az: en buyuk bosluklarin ortasi
            br.sort()
            gaps = [((br[(i + 1) % len(br)] - br[i]) % 1.0 or 1.0, i) for i in range(len(br))]
            g, i = max(gaps)
            br.append((br[i] + g / 2) % 1.0)
        return np.array(sorted(br))

    def set_auto(self, n, data):
        """Otomatik rehberler: data[j] = [(v, ofset), ...]; ofset, nokta ile S1 arasindaki fark."""
        self.rails = []
        self.us = self.auto_us(n)
        self.card = _cardinal(self.us)
        self.auto = data

    def _warp(self, i, u):
        """Kesit i uzerindeki oran: rehberlerde kardinal fonksiyonlarla yumusak; koseli kesitte kose ve rehber
        anahtarlarinda parca parca dogrusal."""
        if self.rails and self.smooth[i]:
            u = np.asarray(u, float)
            return u + self.card(u).dot(self._rail_off(i))
        keys = dict(self.ckeys[i])
        if self.rails:
            for j in range(len(self.us)):
                keys[self.us[j]] = self.S[i, j]
        if not keys:
            return np.asarray(u, float)
        ks = sorted(keys)
        xp = np.array(ks)
        off = np.array([keys[k] - k for k in ks])
        off -= np.round(off)
        fp = xp + off
        xp = np.concatenate([xp - 1, xp, xp + 1])
        fp = np.maximum.accumulate(np.concatenate([fp - 1, fp, fp + 1]))
        return np.interp(np.asarray(u, float) % 1.0, xp, fp)

    def _end(self, t, i, u):
        """Uc tegeti: (len(u), 3) ya da sabit yon."""
        if isinstance(t, str):
            x = np.asarray(self._warp(i, u) + self.secs[i].shift, float) % 1.0
            tb = self.secs[i].tan
            K = len(tb)
            xs = np.arange(K + 1) / float(K)
            d = np.stack([np.interp(x, xs, np.append(tb[:, k], tb[0, k])) for k in range(3)], axis=-1)
            return d / np.maximum(np.linalg.norm(d, axis=1), 1e-12)[:, None] * self.strength[0 if i == 0 else 1]
        return t

    def _nodes(self):
        """v dugumleri (uzantilar dahil) ve kesit sirasi (-1 / -2: uzanti)."""
        vn, idx = list(self.vn), list(range(len(self.vn)))
        if self.tails[0] > 0:
            vn, idx = [-self.tails[0]] + vn, [-1] + idx
        if self.tails[1] > 0:
            vn, idx = vn + [1.0 + self.tails[1]], idx + [-2]
        return np.array(vn), idx

    def base(self, u, v):
        """Yalniz kesitlerden: (len(u), len(v), 3)."""
        u = np.asarray(u, float)
        v = np.asarray(v, float)
        vn, idx = self._nodes()
        W = spline_weights(vn, v, self.t0 is not None, self.t1 is not None)
        rows = {}
        for i in range(len(self.secs)):
            rows[i] = self.secs[i].at(self._warp(i, u))
        G = np.zeros((len(u), len(v), 3))
        for k, i in enumerate(idx):
            if i == -1:
                row = rows[0] - self.secs[0].n * self.tails[0] * self.L
            elif i == -2:
                row = rows[len(self.secs) - 1] + self.secs[-1].n * self.tails[1] * self.L
            else:
                row = rows[i]
            G += row[:, None, :] * W[:, k][None, :, None]
        if self.t0 is not None:
            G += np.asarray(self._end(self.t0, 0, u), float).reshape(-1, 1, 3) * W[:, len(vn)][None, :, None] * self.L
        if self.t1 is not None:
            G += np.asarray(self._end(self.t1, len(self.secs) - 1, u), float).reshape(-1, 1, 3) * \
                W[:, len(vn) + 1][None, :, None] * self.L
        return G

    def correction(self, j, v):
        """Rehber j'nin S1'den farki D_j(v): (len(v), 3). Uzantilarda kesitteki deger."""
        vc = np.clip(v, 0.0, 1.0)
        if self.rails:
            WA = spline_weights(self.vn, vc, False, False)[:, :len(self.vn)]
            a = np.clip(WA.dot(self.A[:, j]), 0.0, 1.0)
            return self.rails[j].at(a) - self.base(self.us[j:j + 1], vc)[0]
        pts = sorted(self.auto[j], key=lambda x: x[0]) if j < len(self.auto) else []
        if not pts:
            return np.zeros((len(v), 3))
        nodes = sorted([(float(x), np.zeros(3)) for x in self.vn] + [(float(p[0]), np.asarray(p[1])) for p in pts],
                       key=lambda x: x[0])
        vs = np.array([x[0] for x in nodes])
        W = spline_weights(vs, vc, self.t0 is not None, self.t1 is not None)[:, :len(vs)]
        return W.dot(np.array([x[1] for x in nodes]))

    def grid(self, u, v):
        """Yuzey noktalari: (len(u), len(v), 3)."""
        u = np.asarray(u, float)
        v = np.asarray(v, float)
        R = self.base(u, v)
        if len(self.us) and (self.rails or self.auto):
            C = self.card(u)
            for j in range(len(self.us)):
                R = R + C[:, j][:, None, None] * self.correction(j, v)[None, :, :]
        return R

    def _v_range(self):
        return -self.tails[0], 1.0 + self.tails[1]

    def _nv(self):
        """v yonunde kontrol noktasi: sapma toleransin altina inene dek artar (sabit sayi, rehberli yuzeyi rehberden
        0.5 mm uzakta birakiyordu)."""
        n = 2 * len(self.secs) + 4
        if self.auto:
            n = max(n, 3 * max([len(a) for a in self.auto] + [0]) + 7)
        a, b = self._v_range()
        q = np.linspace(0.0, 1.0, 161)
        u = np.arange(24) / 24.0
        if len(self.us):
            u = np.concatenate([u, self.us])
        G = self.grid(u, a + (b - a) * q)
        while True:
            g = self._gv(n)[0]
            P = np.linalg.solve(_basis(n, g), self.grid(u, a + (b - a) * g).transpose(1, 0, 2).reshape(n, -1))
            if n >= 64 or np.abs(_basis(n, q).dot(P) - G.transpose(1, 0, 2).reshape(len(q), -1)).max() <= self.tol:
                return n
            n = min(n + max(n // 2, 4), 64)

    def _gv(self, Nv):
        a, b = self._v_range()
        nodes = [(x - a) / (b - a) for x in self.vn]
        g = _greville(Nv, nodes)
        return g, a + (b - a) * g

    def _check_v(self):
        return np.unique(np.concatenate([self.vn, (self.vn[1:] + self.vn[:-1]) / 2]))

    def _periodic_poles(self, Nv):
        """Periyodik yuzey: sapma toleransin altina inene dek u yonunde kontrol noktasi artar."""
        for Nu in (24, 32, 48, 64, 96, 128):
            inv, half = _periodic_inv(Nu)
            uk = np.arange(Nu) / float(Nu)
            P = np.einsum("ij,jqa->iqa", inv, self.grid(uk, self._check_v()))
            err = np.linalg.norm(np.einsum("ij,jqa->iqa", half, P) - self.grid((uk + 0.5 / Nu), self._check_v()),
                                 axis=2).max()
            if err <= self.tol:
                break
        gnorm, gv = self._gv(Nv)
        return Nu, np.einsum("ij,jqa->iqa", inv, self.grid(uk, gv)), gnorm

    def surfaces(self, Nv=None):
        """B-spline yuzeyler: koseli kesit varsa kose basina yama, yoksa tek periyodik yuzey."""
        Nv = Nv or self._nv()
        vmult = [4] + [1] * (Nv - 4) + [4]
        vk = list(np.linspace(0, 1, Nv - 2))
        if not self.breaks:
            Nu, Pu, g = self._periodic_poles(Nv)
            P = np.einsum("qj,ija->iqa", np.linalg.inv(_basis(Nv, g)), Pu)
            s = Part.BSplineSurface()
            s.buildFromPolesMultsKnots([[V(*P[i, j]) for j in range(Nv)] for i in range(Nu)], [1] * (Nu + 1), vmult,
                                       [k / float(Nu) for k in range(Nu + 1)], vk, True, False, 3, 3)
            return [s]
        out = []
        br = self.breaks + [self.breaks[0] + 1.0]
        g, gv = self._gv(Nv)
        ginv = np.linalg.inv(_basis(Nv, g))
        for a, b in zip(br, br[1:]):
            for Nu in (6, 8, 12, 16, 24, 32, 48, 64):
                gu = _greville(Nu)
                Bi = np.linalg.inv(_basis(Nu, gu))
                mid = (_knots(Nu)[3:Nu] + _knots(Nu)[4:Nu + 1]) / 2
                vc = self._check_v()
                Pc = Bi.dot(self.grid(a + (b - a) * gu, vc).reshape(Nu, -1))
                err = np.abs(_basis(Nu, mid).dot(Pc) - self.grid(a + (b - a) * mid, vc).reshape(len(mid), -1)).max()
                if err <= self.tol:
                    break
            P = np.einsum("ij,qk,jka->iqa", Bi, ginv, self.grid(a + (b - a) * gu, gv))
            s = Part.BSplineSurface()
            s.buildFromPolesMultsKnots([[V(*P[i, j]) for j in range(Nv)] for i in range(Nu)],
                                       [4] + [1] * (Nu - 4) + [4], vmult, list(np.linspace(0, 1, Nu - 2)), vk,
                                       False, False, 3, 3)
            out.append(s)
        return out

    def solid(self):
        surfs = self.surfaces()
        caps = [_cap([s.vIso(s.bounds()[k]).toShape() for s in surfs]) for k in (2, 3)]
        sh = Part.Shell([s.toShape() for s in surfs] + caps)
        sh.sewShape()
        sol = Part.Solid(sh)
        if sol.Volume < 0:
            sol.reverse()
        return sol


def _cap(edges):
    w = Part.Wire(Part.__sortEdges__(edges)) if len(edges) > 1 else Part.Wire(edges)
    try:
        f = Part.Face(w)
        if f.isValid():
            return f
    except Exception:
        pass
    return Part.makeFilledFace(edges)


def _tangent_table(sec, shape, K=48):
    """Yuzeye teget: kesit boyunca, kesite komsu yuzeyde kesite dik ve yuzden uzaklasan birim yon. Komsu yuz yoksa
    None."""
    wire = sec.wire
    size = max(wire.BoundBox.DiagonalLength, 1.0)
    faces = []
    for f in shape.Faces:
        if f.distToShape(wire)[0] > 1e-4 * size:
            continue
        if f.Surface.TypeId == "Part::GeomPlane":          # kesitin kendi duzlemindeki yuz sayilmaz
            c, n = rp.face_frame(f)
            if abs(n.dot(V(*sec.n))) > 1 - 1e-6 and abs((c - V(*sec.c)).dot(n)) < 1e-4 * size:
                continue
        faces.append(f)
    if not faces:
        return None
    e = 1e-2 * size
    out = np.zeros((K, 3))
    xs = np.arange(K) / float(K)
    for k, x in enumerate(xs):
        p = np.stack([np.interp(x, sec.s, sec.P[:, a]) for a in range(3)])
        q = np.stack([np.interp((x + 1.0 / M) % 1.0, sec.s, sec.P[:, a]) for a in range(3)])
        t = q - np.stack([np.interp((x - 1.0 / M) % 1.0, sec.s, sec.P[:, a]) for a in range(3)])
        v = Part.Vertex(V(*p))
        f = min(faces, key=lambda g: g.distToShape(v)[0])
        n = _np(f.normalAt(*f.Surface.parameter(V(*p))))
        d = np.cross(t, n)
        d /= max(np.linalg.norm(d), 1e-12)
        if f.distToShape(Part.Vertex(V(*(p - d * e))))[0] > 0.2 * e:   # geride yuz yok: ters yon
            d = -d
        out[k] = d
    return out


# --- nesne <-> yuzey ---
def get_auto(obj):
    """Otomatik rehber noktalari: [[(v, ofset numpy), ...], ...] (rehber sayisi kadar)."""
    data = [[] for _ in range(max(obj.GuideCount, 1))]
    for r, v, o in zip(obj.AutoGuideRails, obj.AutoGuideV, obj.AutoGuideOffsets):
        if 0 <= r < len(data):
            data[r].append((float(v), _np(o)))
    return data


def set_auto(obj, data):
    r, vs, o = [], [], []
    for j, pts in enumerate(data):
        for v, d in pts:
            r.append(j)
            vs.append(float(v))
            o.append(V(*d))
    obj.AutoGuideRails, obj.AutoGuideV, obj.AutoGuideOffsets = r, vs, o


def default_auto(vn, n):
    """Her rehberde her kesit araliginin ortasinda bir nokta (az nokta: temiz yuzey), ofset yok."""
    return [[(float((a + b) / 2), np.zeros(3)) for a, b in zip(vn, vn[1:])] for _ in range(n)]


def prepare(obj):
    """Nesneden Skin (profiller okunur) ya da hata metni."""
    g = is_part(obj)
    items = get_items(obj, "Profiles")
    if len(items) < 2:
        return T("Magic Loft: at least two profiles are needed")
    base = _base(obj)
    secs, profs = [], []
    for i, (o, subs) in enumerate(items):
        p = read_profile(o, subs, g)
        if p is None or isinstance(p, str):
            return T("Magic Loft: profile %d: %s") % (i + 1, T(p or "Rail Pipe: the start face is missing"))
        p = _on_body(p, base)
        profs.append(p)
        secs.append(Section(p))
    for a, b in zip(secs, secs[1:]):
        if np.linalg.norm(a.c - b.c) < 1e-6:
            return T("Magic Loft: two profiles are on top of each other")
    # uclar: Dik ve Yuzeye teget; uzanti yalniz Body'ye eklenecek katinin yuzunde (bkz. docs/OCCT_NOTES.md)
    ends = []
    for k, (mode, sec, nxt, sign) in enumerate(((obj.StartConstraint, secs[0], secs[1], 1.0),
                                                (obj.EndConstraint, secs[-1], secs[-2], -1.0))):
        if mode == "Free":
            ends.append(None)
            continue
        if mode == "Normal":
            n = sec.n if sec.n.dot(nxt.c - sec.c) * sign > 0 else -sec.n
            ends.append(n * (obj.StartStrength if k == 0 else obj.EndStrength))   # v yonunde
            continue
        solid = None
        o, subs = items[0 if k == 0 else -1]
        sh = rp._shape(o, None, g)
        solid = sh if sh.Solids else base
        tb = _tangent_table(sec, solid) if solid is not None else None
        if tb is None:
            return T("Magic Loft: Tangent needs a solid face next to profile %d") % (1 if k == 0 else len(secs))
        sec.tan = tb * (-1.0 if k else 1.0)                # tegetler v yonunde
        ends.append("tan")
    tails = [0.0, 0.0]
    if base is not None:
        for k, (p, sec) in enumerate(((profs[0], secs[0]), (profs[-1], secs[-1]))):
            # Yuzeye teget ucta uzanti yok: kesit normali boyunca uzanti, tegeti komsu yuze degil uzantiya uyduruyordu
            # (konide 29 derece sapma); boolean toleransi uzantisiz da temiz sonuc veriyor
            if p[3] and (obj.StartConstraint if k == 0 else obj.EndConstraint) != "Tangent":
                tails[k] = min(0.5, 0.05 * p[0].BoundBox.DiagonalLength)
    sk = Skin(secs, ends[0], ends[1], tails, max(float(obj.FitTolerance), 1e-4))
    sk.strength = (obj.StartStrength, obj.EndStrength)
    sk.base_conn = [s.shift for s in secs]
    conn = list(obj.ConnectorOffsets)
    if not obj.AutoGuides and get_items(obj, "Guides"):    # secilen rehberde eslesmeyi rehber belirler
        conn = []
    for i, c in enumerate(conn[:len(secs)]):
        if c:
            sk.set_connector(i, c)
    # uzanti yonu ilk kesitte geriye: kesit normali v yonunde olmali
    if secs[0].n.dot(secs[1].c - secs[0].c) < 0:
        secs[0].n = -secs[0].n
    if secs[-1].n.dot(secs[-1].c - secs[-2].c) < 0:
        secs[-1].n = -secs[-1].n
    if obj.AutoGuides:
        n = max(int(obj.GuideCount), 1)
        data = get_auto(obj)
        if not any(data):
            data = default_auto(sk.vn, n)
        sk.set_auto(n, data)
    else:
        rails = read_rails(get_items(obj, "Guides"), g)
        if isinstance(rails, str):
            return T(rails) if "%" not in rails else rails
        err = sk.set_rails(rails)
        if err:
            return err
    return sk


def is_part(obj):
    return not obj.TypeId.startswith("PartDesign::")


def _base(obj):
    return rp._base(obj)


def _on_body(p, base):
    """Rail Pipe'in denetimi, ama govdenin icinden gecen kesit (iki yani da dolu) yuzeyinde sayilmaz: ic noktalarin
    govdeye uzakligi da sifirdir."""
    q = rp._on_body(p, base)
    if q is None or not q[3] or p[3] or isinstance(q, str):
        return q
    e = 1e-3 * max(p[0].BoundBox.DiagonalLength, 1.0)
    if base.isInside(p[1] + p[2] * e, 1e-7, False) and base.isInside(p[1] - p[2] * e, 1e-7, False):
        return p
    return q


def classify(selection):
    """Secimden (Gui.Selection.getSelectionEx) profiller ve rehberler: kapali olanlar profil, acik olanlar rehber.
    Ogeler (nesne, [alt elemanlar])."""
    prof, guides = [], []
    for so in selection:
        o = so.Object
        if rp._is_sketch(o):
            target = prof if rp._closed_wire(o.Shape) is not None else guides
            if all(p[0] is not o for p in target):
                target.append((o, []))
            continue
        names = list(so.SubElementNames)
        if names:
            prof += [(o, [s]) for s in names if s.startswith("Face")]
            edges = {s: o.Shape.getElement(s) for s in names if s.startswith("Edge")}
            used = set()
            for w in rp.edge_loops(list(edges.values())) if edges else []:
                sub = [s for s, e in edges.items() if any(e.isSame(x) for x in w.Edges)]
                prof.append((o, sub))
                used.update(sub)
            rest = [s for s in edges if s not in used]
            if rest:
                guides.append((o, rest))
        elif hasattr(o, "Shape"):
            sh = o.Shape
            if len(sh.Faces) == 1 or (not sh.Faces and (rp._closed_wire(sh) or rp.edge_loops(sh.Edges))):
                prof.append((o, []))
            elif not sh.Faces and sh.Edges:
                guides.append((o, []))
    return prof, guides


def sort_chain(items, glob=False):
    """Profilleri uzayda zincir gibi sirala: birbirine en uzak ikilinin birinden baslayip hep en yakin."""
    if len(items) < 3:
        return list(items)
    cs = []
    for o, subs in items:
        p = read_profile(o, subs, glob)
        cs.append(None if p is None or isinstance(p, str) else p[1])
    if any(c is None for c in cs):
        return list(items)
    n = len(items)
    start = max(range(n), key=lambda i: max((cs[i] - c).Length for c in cs))
    left, order = set(range(n)) - {start}, [start]
    while left:
        k = min(left, key=lambda j: (cs[j] - cs[order[-1]]).Length)
        order.append(k)
        left.discard(k)
    return [items[k] for k in order]


# --- nesne ---
class MagicLoft:
    """Magic Loft (FeatureAdditivePython) / Magic Loft Cut (FeatureSubtractivePython) / Part kati nesnesinin Proxy'si."""

    def __init__(self, obj):
        link = "App::PropertyLinkSubListGlobal" if is_part(obj) else "App::PropertyLinkSubList"
        obj.addProperty(link, "Profiles", "Loft", "Closed sections, in loft order")
        obj.addProperty("App::PropertyIntegerList", "ProfilesSizes", "Loft", "Sub-elements per profile")
        obj.setPropertyStatus("ProfilesSizes", "Hidden")
        obj.addProperty(link, "Guides", "Loft", "Selected guide curves (each separate open chain is one guide)")
        obj.addProperty("App::PropertyIntegerList", "GuidesSizes", "Loft", "Sub-elements per guide item")
        obj.setPropertyStatus("GuidesSizes", "Hidden")
        obj.addProperty("App::PropertyBool", "AutoGuides", "Loft",
                        "Draw ready guides: automatic guides edited on screen; the selected guides are kept but unused")
        obj.addProperty("App::PropertyInteger", "GuideCount", "Loft", "Number of automatic guides").GuideCount = 4
        obj.addProperty("App::PropertyIntegerList", "AutoGuideRails", "Loft", "Automatic guide points: guide index")
        obj.addProperty("App::PropertyFloatList", "AutoGuideV", "Loft", "Automatic guide points: position along the loft")
        obj.addProperty("App::PropertyVectorList", PROPS, "Loft", "Automatic guide points: offset from the plain loft")
        for n in ("AutoGuideRails", "AutoGuideV", PROPS):
            obj.setPropertyStatus(n, "Hidden")
        obj.addProperty("App::PropertyFloatList", "ConnectorOffsets", "Loft", "Seam correction per profile")
        obj.setPropertyStatus("ConnectorOffsets", "Hidden")
        for name, tip in (("Start", "first"), ("End", "last")):
            obj.addProperty("App::PropertyEnumeration", name + "Constraint", "Loft", "How the %s profile connects" % tip)
            setattr(obj, name + "Constraint", ENDS)
            obj.addProperty("App::PropertyFloat", name + "Strength", "Loft", "Tangent strength at the %s profile" % tip)
            setattr(obj, name + "Strength", 1.0)
        obj.addProperty("App::PropertyLength", "FitTolerance", "Loft",
                        "Largest deviation of the surface fit: smaller is more exact, larger has fewer control points")
        obj.FitTolerance = 0.02
        if not is_part(obj) and "Refine" not in obj.PropertiesList:
            obj.addProperty("App::PropertyBool", "Refine", "Base", "Merge coplanar faces of the result")
        if not is_part(obj):
            obj.Refine = True
        obj.Proxy = self

    def execute(self, obj):
        sk = prepare(obj)
        if isinstance(sk, str):
            raise RuntimeError(sk)
        try:
            tool = sk.solid()
        except Exception as e:
            raise RuntimeError(T("Magic Loft: the surface failed (%s)") % e)
        if not tool.isValid():
            raise RuntimeError(T("Magic Loft: the surface gave an invalid solid"))
        sub = obj.TypeId == "PartDesign::FeatureSubtractivePython"
        # kesit uyumu ~0.02 mm: uc, katinin kenarina neredeyse degiyor. Toleranssiz boolean gecersiz ya da 20 yuzlu sonuc
        # verip 10 kat yavasliyordu (daire ucu silindir uzerinde: 500 ms, 32 yuz); 1e-3 ile 40 ms, 4 yuz, Thickness gecer.
        res = None
        for fuzzy in (1e-3, 0.01, 0.05, 0.0):
            try:
                res = rp._combine(_base(obj), tool, sub, getattr(obj, "Refine", False), fuzzy)
            except Exception:
                res = None
            if res is not None and res[1]:
                break
        if res is None:
            raise RuntimeError(T("Magic Loft: the boolean with the Body failed"))
        if sk.corner_mismatch and getattr(self, "warned", None) != obj.Name:
            self.warned = obj.Name                         # olculdu: bu geciste Thickness sessizce et vermiyor
            App.Console.PrintWarning(T("Magic Loft: a corner-to-round transition: PartDesign Thickness may give no "
                                       "wall here. Cut the inside with a Magic Loft Cut instead.\n"))
        if hasattr(obj, "AddSubShape"):
            obj.AddSubShape = tool
        obj.Shape = res[0]

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderMagicLoft:
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
        import pda_magicloft_gui
        pda_magicloft_gui.start(vobj.Object)
        return True

    def unsetEdit(self, vobj, mode=0):
        if mode != 0:
            return None
        import pda_magicloft_gui
        pda_magicloft_gui.stop()
        return True

    def getIcon(self):
        import os
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        cut = getattr(self, "Object", None) is not None and self.Object.TypeId == "PartDesign::FeatureSubtractivePython"
        return os.path.join(d, "pda_magicloftcut.svg" if cut else "pda_magicloft.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None


def _setup(obj, profiles, guides):
    MagicLoft(obj)
    set_items(obj, "Profiles", profiles)
    set_items(obj, "Guides", guides or [])
    obj.ConnectorOffsets = [0.0] * len(profiles)
    if App.GuiUp:
        ViewProviderMagicLoft(obj.ViewObject)
        rp._fine_display(obj)


def _default_ends(obj, profiles, glob, base):
    """Katinin yuzunden cikan uc dik, sketch ucu serbest."""
    for name, (o, subs) in (("StartConstraint", profiles[0]), ("EndConstraint", profiles[-1])):
        p = read_profile(o, subs, glob)
        if p is not None and not isinstance(p, str) and _on_body(p, base)[3]:
            setattr(obj, name, "Normal")


def _check(profiles, glob):
    if len(profiles) < 2:
        return "Magic Loft: at least two profiles are needed"
    for i, (o, subs) in enumerate(profiles):
        p = read_profile(o, subs, glob)
        if p is None or isinstance(p, str):
            return T("Magic Loft: profile %d: %s") % (i + 1, T(p or "Rail Pipe: the start face is missing"))
    return None


def make(body, profiles, guides=None, subtractive=False):
    """Body'de yeni Magic Loft / Cut. Nesne ya da hata metni (nesne olusturulmaz)."""
    err = _check(profiles, False)
    if err:
        return err
    base = body.Tip.Shape if getattr(body, "Tip", None) is not None else None
    obj = body.newObject("PartDesign::FeatureSubtractivePython" if subtractive else "PartDesign::FeatureAdditivePython",
                         "MagicLoftCut" if subtractive else "MagicLoft")
    _setup(obj, sort_chain(profiles), guides)
    _default_ends(obj, get_items(obj, "Profiles"), False, base)
    return obj


def make_part(doc, profiles, guides=None):
    """Part workbench: Body disinda bagimsiz kati, boolean yok. Nesne ya da hata metni."""
    err = _check(profiles, True)
    if err:
        return err
    obj = doc.addObject("Part::FeaturePython", "MagicLoft")
    _setup(obj, sort_chain(profiles, True), guides)
    return obj


def make_own_body(doc, profiles, guides=None):
    """Kendi Body'sinde: secimler SubShapeBinder olarak baglanir, loft o Body'nin ilk katisi olur."""
    err = _check(profiles, True)
    if err:
        return err
    body = doc.addObject("PartDesign::Body", "MagicLoftBody")

    def bind(items, name):
        out = []
        for o, subs in items:
            b = body.newObject("PartDesign::SubShapeBinder", name)
            b.Support = [(o, tuple(subs) or ("",))]
            b.recompute()
            if App.GuiUp:
                b.ViewObject.Visibility = False
            out.append((b, []))
        return out
    obj = make(body, bind(sort_chain(profiles, True), "LoftProfile"), bind(guides or [], "LoftGuide"))
    if isinstance(obj, str):
        for o in list(body.Group):
            doc.removeObject(o.Name)
        doc.removeObject(body.Name)
    return obj


def repair_proxies(doc):
    """Proxy'si kopmus Magic Loft nesnelerini onar (FreeCAD bazen eklenti modulunu belge acilirken aktaramiyor)."""
    fixed = []
    for o in (doc.Objects if doc is not None else []):
        if PROPS in getattr(o, "PropertiesList", []) and not isinstance(getattr(o, "Proxy", None), MagicLoft):
            o.Proxy = MagicLoft.__new__(MagicLoft)
            if App.GuiUp and not isinstance(getattr(o.ViewObject, "Proxy", None), ViewProviderMagicLoft):
                o.ViewObject.Proxy = ViewProviderMagicLoft.__new__(ViewProviderMagicLoft)
            o.touch()
            fixed.append(o)
    for o in fixed:
        o.recompute()
    return fixed
