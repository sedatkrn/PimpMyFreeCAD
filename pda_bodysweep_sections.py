# -*- coding: utf-8 -*-
"""Exact-section body-sweep envelope for convex polyhedral tools (box first).

No raster: every pose of the tool is cut by the section plane analytically
(convex polyhedron -> convex polygon), all poses are united exactly with
shapely, and corners are true polygon vertices.  Corner tracks give the
lattice one fixed topology for the whole sweep; the static start / end bodies
add stations at their own vertex positions, so the end caps are made of the
bodies' own planar faces and close on the body's extreme vertex/edge/face.
"""
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from scipy.optimize import linear_sum_assignment


# ------------------------------------------------------------------ tool
class ConvexTool:
    def __init__(self, V, E):
        self.V = np.asarray(V, float)
        self.E = np.asarray(E, int)

    def silhouette_extent(self, M, p, t):
        """(behind, ahead) for this convex tool placed with rotation M at p, motion t:
        behind = min of t.(X - p) over faces facing forward (n.t > 0); behind that
        plane a forward-moving copy stays inside the tool. ahead = max over faces
        facing backward, the mirror condition at the end of the sweep."""
        from scipy.spatial import ConvexHull
        X = p + self.V @ M.T
        H = ConvexHull(X)
        nt = H.equations[:, :3] @ t
        d = (X - p) @ t
        fv = np.unique(H.simplices[nt > 1e-9]); bv = np.unique(H.simplices[nt < -1e-9])
        return (d[fv].min() if len(fv) else 0.0), (d[bv].max() if len(bv) else 0.0)

    @staticmethod
    def from_points(P):
        """Convex hull of a point cloud (e.g. a fine tessellation of a convex solid)."""
        from scipy.spatial import ConvexHull
        P = np.asarray(P, float)
        H = ConvexHull(P)
        used = np.unique(H.simplices)
        remap = -np.ones(len(P), int); remap[used] = np.arange(len(used))
        E = set()
        for a, b, c in remap[H.simplices]:
            E.update({(min(a, b), max(a, b)), (min(b, c), max(b, c)), (min(a, c), max(a, c))})
        return ConvexTool(P[used], sorted(E))

    @staticmethod
    def box(L, W, H, M=np.eye(3), o=np.zeros(3)):
        c = np.array([[x, y, z] for x in (0, L) for y in (0, W) for z in (0, H)], float)
        E = [(i, j) for i in range(8) for j in range(i + 1, 8)
             if np.sum(np.abs(c[i] - c[j]) > 1e-9) == 1]
        return ConvexTool(c @ M.T + o, E)


def slice_convex(Vw, d, E, P, y, a):
    """Plane cut of one convex pose. d = signed distances of Vw to the plane."""
    i, j = E[:, 0], E[:, 1]
    di, dj = d[i], d[j]
    m = (di * dj <= 0) & (np.abs(di - dj) > 1e-12)
    if m.sum() < 3:
        return None
    s = di[m] / (di[m] - dj[m])
    X = Vw[i[m]] + s[:, None] * (Vw[j[m]] - Vw[i[m]])
    uv = np.c_[(X - P) @ y, (X - P) @ a]
    pg = Polygon(uv).convex_hull
    return pg if pg.geom_type == "Polygon" and pg.area > 1e-9 else None


# ------------------------------------------------------------------ path
class PolyPath:
    """Densely sampled smooth path, Z-up frames, linear extrapolation past the ends."""

    def __init__(self, pts, mode="zup", ups=None):
        """mode 'zup': third axis = world Z made perpendicular to t (box file);
        mode 'tz': third axis = t x Z (PathArray rule of sweep-test-spline2);
        mode 'up': third axis = given up vector per sample (e.g. the normal of the
        surface the path lies on), made perpendicular to t."""
        pts = np.asarray(pts, float)
        self.pts = pts
        self.mode = mode
        self.ups = None if ups is None else np.asarray(ups, float)
        self.s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        self.L = self.s[-1]
        tg = np.gradient(pts, self.s, axis=0)
        self.tg = tg / np.linalg.norm(tg, axis=1, keepdims=True)

    def at(self, s):
        sc = min(max(s, 0.0), self.L)
        p = np.array([np.interp(sc, self.s, self.pts[:, k]) for k in range(3)])
        t = np.array([np.interp(sc, self.s, self.tg[:, k]) for k in range(3)])
        t /= np.linalg.norm(t)
        if self.mode == "tz":
            z = np.cross(t, [0, 0, 1.0]); z /= np.linalg.norm(z)
        elif self.mode == "up":
            up = np.array([np.interp(sc, self.s, self.ups[:, k]) for k in range(3)])
            z = up - t * (t @ up); z /= np.linalg.norm(z)
        else:
            z = np.array([0, 0, 1.0]) - t * t[2]; z /= np.linalg.norm(z)
        y = np.cross(z, t)
        return p + (s - sc) * t, np.c_[t, y, z]


# ------------------------------------------------------------ the sweep
def _smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def _unit(v):
    return v / np.linalg.norm(v)


class Sweep:
    """Section planes are perpendicular to the path in the middle; towards both ends
    they turn smoothly until they are parallel to the static body's own end face, so
    the last section *is* that face and the cap closes on the body's real geometry."""

    def __init__(self, tool, path, pose_step=0.5, blend=None, ends="blend"):
        """tool: one ConvexTool or a list of them (convex decomposition of any tool).
        ends='blend': planes turn onto the static bodies' end faces (convex tools);
        ends='tube' : planes stay perpendicular, the tube is closed by flat caps at
                      s=0 and s=L and the static bodies are kept as exact solids."""
        from scipy.spatial import ConvexHull
        self.parts = list(tool) if isinstance(tool, (list, tuple)) else [tool]
        self.tool, self.path, self.ends = self.parts[0], path, ends
        if ends == "blend" and len(self.parts) > 1:
            raise ValueError("ends='blend' needs a convex tool; use ends='tube'")
        n = max(2, int(np.ceil(path.L / pose_step)))
        self.ps = np.linspace(0, path.L, n + 1)
        self.PM = [path.at(s) for s in self.ps]
        self.Vp = [np.array([p + T.V @ M.T for p, M in self.PM]) for T in self.parts]
        self.Vw = np.concatenate(self.Vp, axis=1)                        # (n,nv,3)
        Vall = np.concatenate([T.V for T in self.parts])
        diam = 2 * np.max(np.linalg.norm(Vall - Vall.mean(0), axis=1))
        self.blend = blend if blend is not None else 1.5 * diam
        if ends != "blend":
            self.cap = None
            return
        # dominant end faces of the static start / end bodies
        self.cap = []
        for k, sgn in ((0, -1.0), (-1, +1.0)):
            p, M = self.PM[k]; t = M[:, 0]
            H = ConvexHull(self.Vw[k])
            nrm = H.equations[:, :3]
            j = int(np.argmax(sgn * nrm @ t))
            f = nrm[j]                                   # outward face normal
            n_pl = -f if sgn < 0 else f                  # plane normal, oriented like t
            on = np.abs((self.Vw[k] - self.Vw[k][H.simplices[j][0]]) @ f) < 1e-6
            self.cap.append(dict(n=n_pl, face=self.Vw[k][on], p=p, t=t))

    def frame(self, s):
        """Section plane at station s: point P and columns (normal, u-axis, v-axis)."""
        P, M = self.path.at(s)
        t, z = M[:, 0], M[:, 2]
        L, B = self.path.L, self.blend
        n = t
        if self.ends != "blend":
            pass
        elif s < B:
            w = _smooth(s / B); n = _unit((1 - w) * self.cap[0]["n"] + w * t)
        elif s > L - B:
            w = _smooth((L - s) / B); n = _unit((1 - w) * self.cap[1]["n"] + w * t)
        a = _unit(z - n * (n @ z)); y = np.cross(a, n)
        return P, np.c_[n, y, a]

    def cap_station(self, X, side):
        """Station s whose plane passes through world point X (start/end region)."""
        c = self.cap[side]
        base = 0.0 if side == 0 else self.path.L
        return base + c["n"] @ (X - c["p"]) / (c["n"] @ c["t"])

    def section(self, s):
        P, M = self.frame(s)
        t, y, a = M[:, 0], M[:, 1], M[:, 2]
        polys = []
        for T, Vp in zip(self.parts, self.Vp):
            polys += self._part_polys(T, Vp, P, t, y, a)
        U = unary_union(polys) if polys else None
        if U is None or U.is_empty:
            return P, M, None
        self.last_pieces = 1
        if isinstance(U, MultiPolygon):
            big = max(g.area for g in U.geoms)
            self.last_pieces = sum(1 for g in U.geoms if g.area > 1e-3 * big)
            U = max(U.geoms, key=lambda g: g.area)
        return P, M, (U if not U.is_empty else None)

    def _part_polys(self, T, Vw, P, t, y, a):
        D = (Vw - P) @ t                                                 # (n,nv)
        E = T.E; ei, ej = E[:, 0], E[:, 1]
        lo = np.minimum(D[:-1].min(1), D[1:].min(1)); hi = np.maximum(D[:-1].max(1), D[1:].max(1))
        sel = np.where((lo <= 0) & (hi >= 0))[0]
        if len(sel) == 0:
            return []
        # continuous motion between pose k and k+1: hull of both cuts and the points
        # where vertex trajectories pierce the plane (exact for translation).  All
        # pairs at once: points are labelled with their pair and hulled in bulk.
        import shapely
        slot = np.full(len(D), -1); slot[sel] = np.arange(len(sel))
        Q = np.unique(np.r_[sel, sel + 1])
        di, dj = D[Q][:, ei], D[Q][:, ej]
        m = (di * dj <= 0) & (np.abs(di - dj) > 1e-12)
        qi, ek = np.nonzero(m)
        f = di[qi, ek] / (di[qi, ek] - dj[qi, ek])
        A_ = Vw[Q[qi], ei[ek]]; B_ = Vw[Q[qi], ej[ek]]
        Xc = A_ + f[:, None] * (B_ - A_)
        q = Q[qi]
        X_l, L_l = [], []
        for lab in (slot[q], slot[np.maximum(q - 1, 0)] * (q > 0) - (q == 0)):   # as k, as k+1
            ok = lab >= 0
            X_l.append(Xc[ok]); L_l.append(lab[ok])
        d0, d1 = D[sel], D[sel + 1]
        mv = (d0 * d1 <= 0) & (np.abs(d0 - d1) > 1e-12)
        pk, vk = np.nonzero(mv)
        fv = d0[pk, vk] / (d0[pk, vk] - d1[pk, vk])
        X_l.append(Vw[sel[pk], vk] + fv[:, None] * (Vw[sel[pk] + 1, vk] - Vw[sel[pk], vk]))
        L_l.append(pk)
        X = np.concatenate(X_l); lab = np.concatenate(L_l)
        if len(X) < 3:
            return []
        o = np.argsort(lab, kind="stable"); X, lab = X[o], lab[o]
        uv = np.c_[(X - P) @ y, (X - P) @ a]
        hulls = shapely.convex_hull(shapely.multipoints(uv, indices=lab))
        hulls = hulls[(shapely.get_type_id(hulls) == 3) & (shapely.area(hulls) > 1e-9)]
        return list(hulls)

    def static_slice(self, k, s):
        """Exact cut of the tool at pose k with the section plane at station s."""
        P, M = self.frame(s)
        polys = []
        for T, Vp in zip(self.parts, self.Vp):
            g = slice_convex(Vp[k], (Vp[k] - P) @ M[:, 0], T.E, P, M[:, 1], M[:, 2])
            if g is not None:
                polys.append(g)
        return unary_union(polys) if polys else None

    def protrusion_reach(self, side, rel_tol=2e-4, iters=9):
        """How far past the path end (side 0: before the start, 1: after the end) the
        envelope still sticks out of the static end body's own cut.  With a pure
        translation that is nothing; when the tool turns, later poses swing out behind
        the first one (corner flares), and the tube has to follow them until they
        have vanished.  Bisection on the excess area; 0 when there is none."""
        L = self.path.L; k = 0 if side == 0 else -1
        base = 0.0 if side == 0 else L; sgn = -1.0 if side == 0 else 1.0
        P, M = self.PM[k]; d = (self.Vw[k] - P) @ M[:, 0]
        cap = max(0.0, -d.min()) if side == 0 else max(0.0, d.max())
        if cap <= 0:
            return 0.0
        _, _, U0 = self.section(base)
        if U0 is None:
            return 0.0
        thr = rel_tol * U0.area

        def excess(dd):
            s_ = base + sgn * dd
            _, _, U = self.section(s_)
            if U is None:
                return 0.0
            S0 = self.static_slice(k, s_)
            return U.area if S0 is None else U.difference(S0.buffer(0.02)).area
        if excess(0.0) <= thr:
            return 0.0
        lo, hi = 0.0, cap
        if excess(hi) > thr:
            return cap
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            if excess(mid) > thr:
                lo = mid
            else:
                hi = mid
        return hi

    def body_stations(self):
        """Stations through every vertex of the static start / end body."""
        return (np.array([self.cap_station(X, 0) for X in self.Vw[0]]),
                np.array([self.cap_station(X, 1) for X in self.Vw[-1]]))


# ------------------------------------------------------------- helpers
def ccw_ring(U, tol=0.01):
    c = np.array(U.simplify(tol, preserve_topology=True).exterior.coords)[:-1]
    ar = 0.5 * np.sum(c[:, 0] * np.roll(c[:, 1], -1) - np.roll(c[:, 0], -1) * c[:, 1])
    return c if ar > 0 else c[::-1]


def turning_deg(c):
    a = c - np.roll(c, 1, axis=0); b = np.roll(c, -1, axis=0) - c
    return np.degrees(np.arctan2(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0], (a * b).sum(1)))


def cum_len(c):
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.r_[c, c[:1]], axis=0), axis=1))]


def point_at(c, cl, s):
    """Point on closed polyline c at arclength s (mod perimeter)."""
    Lp = cl[-1]; s = s % Lp
    i = int(np.clip(np.searchsorted(cl, s, side="right") - 1, 0, len(c) - 1))
    f = (s - cl[i]) / max(cl[i + 1] - cl[i], 1e-15)
    return c[i] + f * (c[(i + 1) % len(c)] - c[i])


def project_arclen(c, cl, q):
    """Arclength of the closest point of closed polyline c to 2D point q."""
    A = c; B = np.roll(c, -1, axis=0); AB = B - A
    f = np.clip(((q - A) * AB).sum(1) / np.maximum((AB * AB).sum(1), 1e-15), 0, 1)
    X = A + f[:, None] * AB
    k = int(np.argmin(np.linalg.norm(X - q, axis=1)))
    return cl[k] + f[k] * (cl[k + 1] - cl[k])


# ------------------------------------------------------------- pipeline
def _mid_stations(L, ds):
    """0, ds, 2ds, ... , L without a near-duplicate station just before L (two
    stations a few microns apart make a jump no smooth column curve can follow)."""
    st = np.arange(0.0, L, ds)
    if len(st) > 1 and L - st[-1] < 0.5 * ds:
        st = st[:-1]
    return np.r_[st, L]


def build_envelope(sw, ds_mid=5.0, n_end=8, corner_deg=12.0, corner_lo=4.0, match_mm=12.0, seg_step=2.0,
                   tip_eps=1e-3, tube_ext=None, ds_ext=2.0, min_strip=1.0,
                   min_track_len=10.0, keep_deg=45.0, stations=None, cache=None, coarse_gap=np.inf, min_gap=0.5):
    """stations: explicit station list (adaptive refinement); cache: dict s -> section."""
    L = sw.path.L
    if stations is not None:
        st = np.unique(np.asarray(stations, float))
        if sw.ends == "tube":
            sw.tube_ends = (st[0], st[-1])
        else:
            b0, b1 = sw.body_stations()
    elif sw.ends == "blend":
        b0, b1 = sw.body_stations()
        s_lo, s_hi = b0.min(), b1.max()
        # stations: uniform in the middle, plus every static-body vertex, plus a few in between
        st = list(_mid_stations(L, ds_mid))
        st += [float(x) for x in b0 if x < 0] + [float(x) for x in b1 if x > L]
        for a_, b_ in ((s_lo, 0.0), (L, s_hi)):
            st += list(np.linspace(a_, b_, n_end + 2)[1:-1])
        st = np.unique(np.round(st, 6))
        st = st[(st > s_lo + tip_eps) & (st < s_hi - tip_eps)]
        st = np.r_[s_lo + tip_eps, st, s_hi - tip_eps]
    else:
        # tube: past both path ends for as long as the section stays ONE piece
        # (a non-convex body splits further out); the static bodies are clipped at
        # the tube's end planes, so tube and bodies only meet on a plane - never
        # tangentially, which is what made the boolean draw saw-tooth edges
        ext_max = sw.blend / 1.5 / 2 if tube_ext is None or isinstance(tube_ext, (tuple, list)) else tube_ext
        def reach(sign):
            last, d = 0.0, ds_ext
            while d <= ext_max + 1e-9:
                s = -d if sign < 0 else L + d
                _, _, U = sw.section(s)
                if U is None or sw.last_pieces > 1:
                    break
                last = d; d += ds_ext
            return last
        if isinstance(tube_ext, (tuple, list)):
            e0, e1 = float(tube_ext[0]), float(tube_ext[1])      # given (convex tools)
        else:
            e0, e1 = reach(-1), reach(+1)
        st = np.unique(np.r_[np.linspace(-e0, 0, int(np.ceil(e0 / ds_ext)) + 1)[:-1] if e0 > 0 else [],
                             _mid_stations(L, ds_mid),
                             np.linspace(L, L + e1, int(np.ceil(e1 / ds_ext)) + 1)[1:] if e1 > 0 else []])
        sw.tube_ends = (-e0, L + e1)

    # ---- 1. exact sections
    secs = []
    for s in st:
        if cache is not None and s in cache:
            P, M, U = cache[s]
        else:
            P, M, U = sw.section(s)
            if cache is not None:
                cache[s] = (P, M, U)
        if U is None or U.area < 1e-6:
            continue
        c = ccw_ring(U)
        secs.append(dict(s=s, P=P, M=M, c=c, cl=cum_len(c)))
    W3 = lambda S, uv: S["P"] + uv[..., 0:1] * S["M"][:, 1] + uv[..., 1:2] * S["M"][:, 2]

    # ---- 2. corners per section (true vertices with real turning)
    # hysteresis: a track is born only on a strong corner (> corner_deg) but is
    # followed down to corner_lo, so a corner near the threshold cannot flicker
    for S in secs:
        tr = turning_deg(S["c"])
        idx = np.where(np.abs(tr) > corner_lo)[0]
        S["ci"] = idx
        S["strong"] = np.abs(tr[idx]) > corner_deg
        S["ang"] = np.abs(tr[idx])
        S["cs"] = S["cl"][idx]
        S["cw"] = W3(S, S["c"][idx])

    # ---- 3. corner tracks across stations (Hungarian on 3D distance)
    tracks = []                       # list of dict: {station_index: corner_index}
    prev = {}                         # corner index in previous station -> track id
    for i, S in enumerate(secs):
        cur = {}
        if i > 0 and len(S["cw"]) and len(secs[i - 1]["cw"]):
            # compare in each section's own (u, v) frame: the frame follows the path's
            # bends and the tool's twist, so a tool corner stays nearly in place there
            Sp = secs[i - 1]
            A = Sp["c"][Sp["ci"]]; B = S["c"][S["ci"]]
            C = np.linalg.norm(A[:, None] - B[None], axis=2)
            r, k = linear_sum_assignment(C)
            for a_, b_ in zip(r, k):
                # corners travel with the tool: allow for the path advance between stations
                if C[a_, b_] < match_mm and a_ in prev:
                    cur[b_] = prev[a_]
        for b_ in range(len(S["cw"])):
            if b_ not in cur:
                if not S["strong"][b_]:
                    continue                      # weak corners only continue tracks
                cur[b_] = len(tracks); tracks.append({})
            tracks[cur[b_]][i] = b_
        prev = cur
    # drop short-lived tracks (noise)
    # (a track seen on only 2 stations of a coarse interval is kept: refinement decides)
    sv = np.array([S["s"] for S in secs])
    tracks = [T for T in tracks if len(T) >= 3 or sv[max(T)] - sv[min(T)] > coarse_gap
              or (min(T) > 0 and sv[min(T)] - sv[min(T) - 1] > coarse_gap)
              or (max(T) < len(sv) - 1 and sv[max(T) + 1] - sv[max(T)] > coarse_gap)]
    if not tracks:
        # no corner anywhere (round section): three virtual tracks, evenly spaced
        im = len(secs) // 2; S = secs[im]; Lp = S["cl"][-1]
        S["cs"] = np.r_[S["cs"], Lp * np.arange(3) / 3]
        S["cw"] = np.r_[S["cw"].reshape(-1, 3), W3(S, np.array([point_at(S["c"], S["cl"], a) for a in Lp * np.arange(3) / 3]))]
        S["ang"] = np.r_[S["ang"], [0.0] * 3]
        n0 = len(S["cs"]) - 3
        tracks = [{im: n0 + j} for j in range(3)]
    # lifetime filter: a corner that lives for less than min_track_len of path
    # (typical in bends) is folded into its neighbours instead of getting a strip
    if min_track_len > 0:
        sv = np.array([S["s"] for S in secs])
        whole = sv[-1] - sv[0]
        # ...but a sharp corner (a real edge of the tool, e.g. 90 deg) is kept however
        # briefly it lives: only shallow, flickering corners are folded away
        keep = [T for T in tracks
                if sv[max(T)] - sv[min(T)] >= min(min_track_len, 0.5 * whole)
                or max(secs[i]["ang"][T[i]] for i in T) >= keep_deg]
        tracks = keep if len(keep) >= 3 else tracks

    # ---- 4. place every track on every station (fixed topology)
    nS = len(secs); K = len(tracks)
    pos = np.zeros((nS, K))           # arclength on each ring
    def proj(S, Xw):
        q = np.array([(Xw - S["P"]) @ S["M"][:, 1], (Xw - S["P"]) @ S["M"][:, 2]])
        a = project_arclen(S["c"], S["cl"], q)
        return a, W3(S, point_at(S["c"], S["cl"], a))
    for k, T in enumerate(tracks):
        act = sorted(T)
        X = {}
        for i in act:
            pos[i, k] = secs[i]["cs"][T[i]]; X[i] = secs[i]["cw"][T[i]]
        # inactive stations: carry the track station by station, so it stays a
        # continuous line on the surface (a virtual feature line)
        for i in range(act[-1] + 1, len(secs)):
            pos[i, k], X[i] = proj(secs[i], X[i - 1])
        for i in range(act[0] - 1, -1, -1):
            pos[i, k], X[i] = proj(secs[i], X[i + 1])
        for i0, i1 in zip(act[:-1], act[1:]):          # gaps inside the active range
            for i in range(i0 + 1, i1):
                pos[i, k], X[i] = proj(secs[i], X[i - 1])
    # global cyclic order of the tracks, read at the middle station, starting at the
    # longest-lived track (the reference every station is unwrapped against)
    im = nS // 2
    ref = int(np.argmax([len(T) for T in tracks]))
    order = list(np.argsort((pos[im] - pos[im, ref]) % secs[im]["cl"][-1]))
    pos = pos[:, order]; tracks = [tracks[k] for k in order]
    # unwrap every station by continuity from the middle one outwards, then forbid
    # crossings (a track that would overtake its neighbour stops on it)
    rel = np.zeros_like(pos)
    def unwrap(i, prev):
        Lp = secs[i]["cl"][-1]
        r = (pos[i] - pos[i, 0]) % Lp
        if prev is not None:
            # keep each track on the side it was on at the neighbouring station
            pf = prev / prev_L[0] * Lp
            r = np.where(r - pf > Lp / 2, r - Lp, np.where(pf - r > Lp / 2, r + Lp, r))
        r = np.clip(r, 0, Lp)
        r[0] = 0.0
        return np.maximum.accumulate(r)
    prev_L = [secs[im]["cl"][-1]]
    rel[im] = unwrap(im, None)
    for rng in (range(im + 1, nS), range(im - 1, -1, -1)):
        prev = rel[im]; prev_L[0] = secs[im]["cl"][-1]
        for i in rng:
            rel[i] = unwrap(i, prev)
            prev = rel[i]; prev_L[0] = secs[i]["cl"][-1]
    for i in range(nS):
        pos[i] = pos[i, 0] + rel[i]

    # ---- 4a. virtual tracks keep their distance: where a corner does not exist its
    # track is only a parameter line, and clamping it onto a neighbour (no crossing)
    # made strips of zero width over long stretches - degenerate faces that fold
    # between rows.  Real corners stay put; runs of virtual tracks between two real
    # ones are pushed apart to at least min_gap (or an even share of the space).
    if min_gap > 0 and K > 1:
        Lps_ = np.array([S["cl"][-1] for S in secs])
        for i in range(nS):
            act = np.array([i in T for T in tracks])
            if act.all():
                continue
            Lp = Lps_[i]
            # rotate so that the run structure starts at a real corner (or track 0)
            r0 = int(np.argmax(act)) if act.any() else 0
            idx = [(r0 + j) % K for j in range(K)]
            p = np.array([pos[i, k] + (Lp if k < r0 else 0.0) for k in idx])   # monotone
            fixed_ = np.array([act[k] for k in idx]); fixed_[0] = True
            bounds = np.r_[np.where(fixed_)[0], K]
            for a_, b_ in zip(bounds[:-1], bounds[1:]):
                n_ = b_ - a_ - 1
                if n_ <= 0:
                    continue
                A_ = p[a_]; B_ = p[b_] if b_ < K else p[0] + Lp
                g = min(min_gap, (B_ - A_) / (n_ + 1))
                q = p[a_ + 1:b_].copy()
                for j in range(n_):                                   # forward
                    q[j] = max(q[j], (A_ if j == 0 else q[j - 1]) + g)
                for j in range(n_ - 1, -1, -1):                       # backward
                    q[j] = min(q[j], (B_ if j == n_ - 1 else q[j + 1]) - g)
                p[a_ + 1:b_] = q
            for j, k in enumerate(idx):
                pos[i, k] = p[j] - (Lp if k < r0 else 0.0)
            # keep the common form: pos[i,0] first, the rest increasing within one turn
            base0 = pos[i, 0]
            pos[i] = base0 + (pos[i] - base0) % Lp
            pos[i, 0] = base0

    # ---- 4b. merge hair-thin strips: two tracks that never get further apart than
    # min_strip are the same corner for any practical purpose, and a sliver strip
    # makes degenerate faces in the boolean.  Keep the longer-lived track.
    Lps = np.array([S["cl"][-1] for S in secs])
    while K > 3:
        wmax = (np.c_[pos[:, 1:], pos[:, 0] + Lps] - pos).max(0)
        k = int(np.argmin(wmax))
        if wmax[k] >= min_strip:
            break
        k2 = (k + 1) % K
        cand = [j for j in (k, k2) if j != 0]            # track 0 is the unwrap reference
        drop = min(cand, key=lambda j: len(tracks[j]))
        pos = np.delete(pos, drop, axis=1); tracks.pop(drop); K -= 1

    # ---- 5. samples per segment: fixed for the whole sweep
    segL = np.zeros((nS, K))
    for i, S in enumerate(secs):
        nxt = np.r_[pos[i, 1:], pos[i, 0] + S["cl"][-1]]
        segL[i] = nxt - pos[i]
    m = np.maximum(1, np.ceil(segL.max(0) / seg_step).astype(int))
    N = int(m.sum())

    rings = np.zeros((nS, N, 3))
    for i, S in enumerate(secs):
        pts = []
        for k in range(K):
            for q in range(m[k]):
                pts.append(point_at(S["c"], S["cl"], pos[i, k] + segL[i, k] * q / m[k]))
        rings[i] = W3(S, np.array(pts))

    # first / last ring sit 'tip_eps' inside the static bodies' extreme vertex, edge or
    # face; snap them onto that exact tip (vertex -> point, edge -> segment, face -> kept)
    for ri, side, bs in (((0, 0, b0), (-1, 1, b1)) if sw.ends == "blend" else ()):
        Vb = sw.Vw[0 if side == 0 else -1]
        ext = bs.min() if side == 0 else bs.max()
        tip = Vb[np.abs(bs - ext) < 1e-6]
        if len(tip) == 1:
            rings[ri][:] = tip[0]
        elif len(tip) == 2:
            A_, B_ = tip; AB = B_ - A_
            f = np.clip(((rings[ri] - A_) @ AB) / (AB @ AB), 0, 1)
            rings[ri] = A_ + f[:, None] * AB
        else:                                    # a face: flatten onto its plane
            n = sw.cap[side]["n"]
            rings[ri] = rings[ri] - np.outer((rings[ri] - tip[0]) @ n, n)
    out = dict(secs=secs, tracks=tracks, pos=pos, m=m, N=N, rings=rings, K=K, ends=sw.ends)
    if sw.ends == "tube":
        # clip planes for the static bodies: (point, outward normal)
        out["clip"] = [(secs[0]["P"], -secs[0]["M"][:, 0]), (secs[-1]["P"], secs[-1]["M"][:, 0])]
    return out


def _cap_tris(ring, S, flip):
    """Constrained Delaunay triangulation of a planar ring (indices into ring)."""
    import shapely
    uv = np.c_[(ring - S["P"]) @ S["M"][:, 1], (ring - S["P"]) @ S["M"][:, 2]]
    keep = [0]
    for j in range(1, len(uv)):
        if np.linalg.norm(uv[j] - uv[keep[-1]]) > 1e-7:
            keep.append(j)
    if np.linalg.norm(uv[keep[-1]] - uv[keep[0]]) < 1e-7:
        keep.pop()
    pg = Polygon(uv[keep])
    if not pg.is_valid:
        pg = pg.buffer(0)
    lut = {tuple(np.round(uv[j], 9)): j for j in keep}
    out = []
    for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(pg)):
        c = np.array(tri.exterior.coords)[:3]
        ids = [lut.get(tuple(np.round(p, 9))) for p in c]
        if None in ids:
            continue
        ar = (c[1, 0] - c[0, 0]) * (c[2, 1] - c[0, 1]) - (c[2, 0] - c[0, 0]) * (c[1, 1] - c[0, 1])
        if (ar > 0) == flip:
            ids = [ids[0], ids[2], ids[1]]
        out.append(ids)
    return out


def envelope_mesh(env):
    """Quads between rings (triangulated), cones/planes to the static bodies' tips."""
    R = env["rings"]; nS, N, _ = R.shape
    V = [R.reshape(-1, 3)]; F = []
    for i in range(nS - 1):
        a = i * N; b = (i + 1) * N
        for j in range(N):
            j2 = (j + 1) % N
            F += [(a + j, a + j2, b + j), (a + j2, b + j2, b + j)]
    base = nS * N
    if env.get("ends") == "tube":
        for side in (0, 1):
            r0 = 0 if side == 0 else (nS - 1) * N
            S = env["secs"][0 if side == 0 else -1]
            for t in _cap_tris(R[0 if side == 0 else -1], S, flip=(side == 0)):
                F.append(tuple(r0 + k for k in t))
    for side in ((0, 1) if env.get("ends") != "tube" else ()):
        r0 = 0 if side == 0 else (nS - 1) * N
        V.append(R[0 if side == 0 else -1].mean(0)[None]); t0 = base; base += 1
        for j in range(N):
            j2 = (j + 1) % N
            F.append((r0 + j2, r0 + j, t0) if side == 0 else (r0 + j, r0 + j2, t0))
    V = np.concatenate(V); F = np.array(F)
    # weld + drop degenerate triangles
    key = np.round(V / 1e-6).astype(np.int64)
    uk, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.ravel()
    Vu = np.zeros((len(uk), 3)); Vu[inv] = V
    F = inv[F]
    ok = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    return Vu, F[ok]


def mesh_stats(V, F):
    E = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1)
    _, cnt = np.unique(E, axis=0, return_counts=True)
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    vol = np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6
    return dict(V=len(V), F=len(F), boundary=int((cnt == 1).sum()), nonmanifold=int((cnt > 2).sum()), volume=vol)


def frustum(r0, r1, z0, z1, n=192, outside=True):
    """Convex polygonal frustum around local Z (r0 at z0, r1 at z1).
    outside=True: circumscribed polygon, so it contains the true cone (max error
    r*(1/cos(pi/n)-1), 0.015 mm for r=110, n=192)."""
    if outside:
        k = 1.0 / np.cos(np.pi / n); r0, r1 = r0 * k, r1 * k
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    V = np.r_[np.c_[r0 * np.cos(a), r0 * np.sin(a), np.full(n, z0)],
              np.c_[r1 * np.cos(a), r1 * np.sin(a), np.full(n, z1)]]
    E = [(i, (i + 1) % n) for i in range(n)] + [(n + i, n + (i + 1) % n) for i in range(n)] \
        + [(i, n + i) for i in range(n)]
    return ConvexTool(V, E)


# ------------------------------------------------------------- adaptive stations
def _ring_gap(true_c, q):
    """Max distance of the true section's vertices (2D) to the closed polyline q."""
    import shapely
    lr = shapely.LinearRing(q)
    return float(shapely.distance(shapely.points(true_c), lr).max())


def check_intervals(env, sw, cache):
    """For every pair of neighbouring stations: compute the TRUE section half way and
    compare it with what the column curves (interpolated along the path) give there.
      fwd : how far the curves' points leave the true section          (mm)
      rev : how far the true section's vertices lie from the curves' ring,
            minus the same gap at the two real stations (that part comes from the
            sampling across the strip, which no extra station can change)   (mm)"""
    import shapely
    from scipy.interpolate import make_interp_spline
    secs = env["secs"]; R = env["rings"]; nS, N = R.shape[:2]
    seg = np.linalg.norm(np.diff(R, axis=0), axis=2).mean(1)
    u = np.r_[0.0, np.cumsum(np.maximum(seg, 1e-9))]; u /= u[-1]
    spl = make_interp_spline(u, R.reshape(nS, -1), k=min(3, nS - 1))
    dspl = spl.derivative()
    base = np.array([_ring_gap(S["c"], (R[i] - S["P"]) @ S["M"][:, 1:3]) for i, S in enumerate(secs)])
    # the stations' own rings are simplified (ccw_ring tol): that offset is not an
    # interpolation error, so it is subtracted like the across-strip sampling gap
    basef = np.zeros(nS)
    for i, S in enumerate(secs):
        U0 = cache.get(S["s"], (None, None, None))[2]
        if U0 is not None:
            basef[i] = float(shapely.distance(shapely.points((R[i] - S["P"]) @ S["M"][:, 1:3]), U0.exterior).max())
    fwd = np.zeros(nS - 1); rev = np.zeros(nS - 1); mids = np.zeros(nS - 1)
    J = np.arange(N)
    for i in range(nS - 1):
        sm = 0.5 * (secs[i]["s"] + secs[i + 1]["s"]); mids[i] = sm
        if sm not in cache:
            cache[sm] = sw.section(sm)
        P, M, U = cache[sm]
        if U is None:
            fwd[i] = rev[i] = np.inf; continue
        n = M[:, 0]
        uu = np.linspace(u[i], u[i + 1], 17)
        d = (spl(uu).reshape(17, N, 3) - P) @ n                     # (17, N)
        ch = d[:-1] * d[1:] <= 0
        k = np.where(ch.any(0), ch.argmax(0), np.abs(d).argmin(0).clip(0, 15))
        d0, d1 = d[k, J], d[k + 1, J]
        f = np.where(np.abs(d0 - d1) > 1e-15, d0 / np.where(np.abs(d0 - d1) > 1e-15, d0 - d1, 1), 0).clip(0, 1)
        ug = uu[k] + f * (uu[1] - uu[0])
        for _ in range(2):                                           # Newton on (C(u)-P).n = 0
            X = spl(ug).reshape(N, N, 3)[J, J]
            g = (X - P) @ n; gd = dspl(ug).reshape(N, N, 3)[J, J] @ n
            ug = np.clip(ug - g / np.where(np.abs(gd) > 1e-12, gd, 1e-12), u[i], u[i + 1])
        X = spl(ug).reshape(N, N, 3)[J, J]
        q = (X - P) @ M[:, 1:3]
        fwd[i] = float(shapely.distance(shapely.points(q), U.exterior).max()) - max(basef[i], basef[i + 1])
        rev[i] = _ring_gap(ccw_ring(U), q) - max(base[i], base[i + 1])
    return fwd, rev, mids


def build_envelope_adaptive(sw, tol=0.01, rev_tol=None, ds0=None, ds_min=0.25, ds_birth=1.0,
                            tube_ext=(0.0, 0.0), fixed=(), max_iter=16, max_st=1500, log=None, **kw):
    """Few stations where the envelope is calm, many where it changes: start sparse
    (path ends, tube ends and guide breaks always included), check every interval
    against a true mid section, split the ones that miss the tolerance, repeat.
    Interval ends where a corner track is born or dies are also split down to
    ds_birth, so new corners are located precisely."""
    import time
    rev_tol = tol if rev_tol is None else rev_tol
    L = sw.path.L
    e0, e1 = float(tube_ext[0]), float(tube_ext[1])
    # a hair-short extension only puts two stations microns apart (a jump no smooth
    # column can follow); the exact end piece covers that bit instead
    e0 = e0 if e0 >= 4 * ds_min else 0.0
    e1 = e1 if e1 >= 4 * ds_min else 0.0
    cache = {}
    def area(s):
        if s not in cache:
            cache[s] = sw.section(s)
        U = cache[s][2]
        return 0.0 if U is None else U.area
    # where the tool's end face is almost square to the path, the outermost tube
    # section is a sliver and the next one, a fraction of a mm on, is the full face:
    # no smooth column can make that jump (it bulges past the cap).  End the tube
    # where the section has really arrived; what lies behind is the exact end piece.
    step = max(ds_min, 0.25)
    for side in (0, 1):
        e = (e0, e1)[side]
        if e <= 0:
            continue
        base = 0.0 if side == 0 else L
        sgn = -1.0 if side == 0 else 1.0
        A_ref = area(base)
        d_ = e
        while d_ > 0 and area(base + sgn * d_) < 0.25 * A_ref:
            d_ -= step
        d_ = max(d_, 0.0)
        if d_ < 4 * ds_min:
            d_ = 0.0
        if d_ != e and log:
            log("tup %s ucu %.2f mm -> %.2f mm (kesit orada daha oturmamis)" % ("bas" if side == 0 else "son", e, d_))
        if side == 0:
            e0 = d_
        else:
            e1 = d_
    ds0 = ds0 or max(8 * ds_min, L / 16)
    st = [np.linspace(0, L, int(np.ceil(L / ds0)) + 1)]
    if e0 > 0:
        st.append(np.linspace(-e0, 0, max(2, int(np.ceil(e0 / ds0))) + 1))
    if e1 > 0:
        st.append(np.linspace(L, L + e1, max(2, int(np.ceil(e1 / ds0))) + 1))
    st = np.unique(np.r_[np.concatenate(st), [float(x) for x in fixed if 0 < x < L]])
    t0 = time.time()
    for it in range(max_iter):
        env = build_envelope(sw, stations=st, cache=cache, tube_ext=(e0, e1), coarse_gap=2 * ds_birth, **kw)
        fwd, rev, mids = check_intervals(env, sw, cache)
        sv = np.array([S["s"] for S in env["secs"]]); gap = np.diff(sv)
        bad = ((fwd > tol) | (rev > rev_tol)) & (gap > 2 * ds_min)
        nS = len(sv)
        birth = np.zeros(nS - 1, bool)
        for T in env["tracks"]:
            lo, hi = min(T), max(T)
            if lo > 0:
                birth[lo - 1] = True
            if hi < nS - 1:
                birth[hi] = True
        bad |= birth & (gap > ds_birth)
        if log:
            log("uyarlamali tur %d: %d istasyon, %d iz, en buyuk sapma ileri %.4f geri %.4f mm, bolunecek %d aralik (%.1fs, %d kesit hesaplandi)"
                % (it, nS, env["K"], fwd.max(), rev.max(), int(bad.sum()), time.time() - t0, len(cache)))
        if not bad.any() or nS + bad.sum() > max_st:
            break
        st = np.unique(np.r_[st, mids[bad]])
    env["adapt"] = dict(fwd=fwd, rev=rev, iters=it + 1, computed=len(cache))
    return env
