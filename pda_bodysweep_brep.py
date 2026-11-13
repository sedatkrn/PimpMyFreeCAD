# -*- coding: utf-8 -*-
"""Lattice (from exact_sections.build_envelope) -> FreeCAD BRep solid.

Tensor-product construction with shared edges:
  1. every lattice column (one point per station) is interpolated along the path
     with ONE common parameterisation -> all column curves share knots;
  2. each strip between two neighbouring corner tracks becomes one face over the
     whole path: its v-poles are the column curves' poles, interpolated across
     the strip (degree <= 3, no corner inside a strip);
  3. a strip's side boundary is exactly its corner column's curve, so the
     neighbouring face has the very same edge -> sewing is exact;
  4. the tube ends (ends='tube') are planar faces built from the strips' end edges.
"""
import numpy as np


def _V(p):
    import FreeCAD as App
    return App.Vector(float(p[0]), float(p[1]), float(p[2]))


def _ring_dev(Q, Rr):
    """Surface error of fitted rows: distance of every fitted point to its own
    station's ring (closed polyline). Points may slide ALONG the ring (that is only
    a different sampling of the same surface); only leaving the ring is an error.
    Row by row, so memory stays at (points x segments) per row."""
    out = np.empty(len(Q))
    for i in range(len(Q)):
        A = Rr[i]; AB = np.roll(A, -1, axis=0) - A                     # (N, 3)
        L2 = np.maximum((AB * AB).sum(-1), 1e-18)
        D = Q[i][:, None, :] - A[None]                                   # (Nq, N, 3)
        f = np.clip((D * AB[None]).sum(-1) / L2[None], 0, 1)
        X = A[None] + f[..., None] * AB[None]
        out[i] = np.sqrt(((Q[i][:, None, :] - X) ** 2).sum(-1).min(1)).max()
    return out


def column_curves(env, st_step=1, tol=0.005, deg=3, max_spans=400, log=None):
    """All lattice columns as cubic B-splines on ONE common knot vector, fitted by
    least squares with as few knots as the tolerance allows (few knots = smooth
    surfaces that OCC intersects cleanly; one knot vector = shared edges)."""
    import Part
    from scipy.interpolate import BSpline
    R = env["rings"]; nS = len(R)
    rows = list(range(0, nS, st_step))
    if rows[-1] != nS - 1:
        rows.append(nS - 1)
    s = np.array([env["secs"][i]["s"] for i in rows], float)
    # common parameter = mean chord length of all columns (not path length): near
    # a tip the section collapses like sqrt(distance), which is singular in s but a
    # smooth parabola in the columns' own arc length
    seg = np.linalg.norm(np.diff(R[rows], axis=0), axis=2).mean(1)
    cl = np.r_[0.0, np.cumsum(np.maximum(seg, 1e-9))]
    u = cl / cl[-1]
    Y = R[rows].reshape(len(rows), -1)                       # (rows, ncols*3)
    # adaptive knots: start coarse, split only the spans whose rows miss the
    # tolerance (dense near the tips where the section collapses, sparse elsewhere).
    # Knots sit only between data parameters and every span keeps >= min_pts data
    # rows, so every pole is pinned by data (an empty span lets least squares throw
    # a pole anywhere - that made a 2e11 mm3 'solid' and hung OCC)
    n = len(u)
    cand = 0.5 * (u[:-1] + u[1:])                  # knot i sits between rows i and i+1
    min_pts = 1
    sel = sorted(set(np.linspace(0, n - 2, 9).round().astype(int)[1:-1].tolist()))
    # path breaks (where the guide's pieces meet, curvature jumps): a triple knot
    # there lets every column kink in parameter speed without dragging the fit
    brk_u = np.interp(np.asarray(env.get("breaks", []), float), s, u) if env.get("breaks") else np.array([])
    brk_u = brk_u[(brk_u > u[1]) & (brk_u < u[-2])]

    def fit(sel):
        inner = cand[sel] if sel else np.array([])
        if len(brk_u):
            inner = inner[np.min(np.abs(inner[:, None] - brk_u[None]), axis=1) > 1.5 / n] if len(inner) else inner
            inner = np.sort(np.r_[inner, np.repeat(brk_u, deg)])
        t = np.r_[[0.0] * (deg + 1), inner, [1.0] * (deg + 1)]
        B = BSpline.design_matrix(u, t, deg).toarray()
        # end poles pinned to the end rows (clamped curve passes through them), so
        # rings that collapse onto a tip stay exactly collapsed; interior poles by LSQ
        P = np.empty((B.shape[1], Y.shape[1]))
        P[0], P[-1] = Y[0], Y[-1]
        rhs = Y - np.outer(B[:, 0], P[0]) - np.outer(B[:, -1], P[-1])
        if B.shape[1] > 2:
            P[1:-1], *_ = np.linalg.lstsq(B[:, 1:-1], rhs, rcond=None)
        Q = (B @ P).reshape(n, -1, 3)
        return inner, P, _ring_dev(Q, R[rows])

    for _ in range(60):
        inner, P, e_row = fit(sel)
        err = e_row.max()
        if err <= tol:
            break
        bounds = [-1] + sel + [n - 1]              # span j holds rows bounds[j]+1 .. bounds[j+1]
        new = []
        for j in range(len(bounds) - 1):
            a, b = bounds[j], bounds[j + 1]
            if e_row[a + 1:b + 1].max() > tol and (b - a) >= 2 * min_pts:
                new.append((a + b) // 2)
        if not new or len(sel) + len(new) > max_spans:
            break
        sel = sorted(set(sel + new))
    if err > tol:
        # the sparse fit cannot follow a sharp change: interpolate every row instead
        # (one common knot vector for all columns, exact through the data)
        from scipy.interpolate import make_interp_spline
        spl = make_interp_spline(u, Y, k=deg)
        t = spl.t; P = spl.c
        inner = t[deg + 1:-(deg + 1)]
        err = 0.0
        if log:
            log("seyrek uydurma tolerans disi, tam interpolasyona gecildi")
    # last guard: poles must stay near the data
    span_box = np.ptp(Y.reshape(n, -1, 3).reshape(-1, 3), axis=0).max()
    lo = Y.reshape(-1, 3).min(0) - span_box; hi = Y.reshape(-1, 3).max(0) + span_box
    Pc = P.reshape(-1, 3)
    if np.any(Pc < lo) or np.any(Pc > hi):
        raise RuntimeError("sutun uydurmasi kontrolden cikti (kutup veriden cok uzak)")
    spans = len(inner) + 1
    if log:
        log("sutun egrileri: %d aralik, en buyuk sapma %.4f mm" % (spans, err))
    kv, km = np.unique(np.round(inner, 12), return_counts=True)
    knots = np.r_[0.0, kv, 1.0]
    mults = [deg + 1] + km.tolist() + [deg + 1]
    P = P.reshape(P.shape[0], -1, 3)
    cols = []
    for j in range(R.shape[1]):
        c = Part.BSplineCurve()
        c.buildFromPolesMultsKnots([_V(p) for p in P[:, j]], mults, list(knots), False, deg)
        cols.append(c)
    return cols


def strip_face(env, cols, k):
    import Part
    m = env["m"]; N = env["N"]
    c0 = int(np.sum(m[:k]))
    idx = [(c0 + q) % N for q in range(m[k] + 1)]
    Pv = np.array([[[p.x, p.y, p.z] for p in cols[j].getPoles()] for j in idx])   # (nu, nv, 3)
    nu = Pv.shape[0]
    # across the strip the column-curve poles are used directly as the control net
    # of a clamped uniform B-spline: the two side boundaries are then exactly the
    # corner columns' curves (shared with the neighbours) and pinched rows, where
    # columns coincide, are harmless
    du = min(3, nu - 1)
    nk = nu - du + 1
    uk = list(np.linspace(0, 1, nk))
    um = [du + 1] + [1] * (nk - 2) + [du + 1]
    poles = [[_V(p) for p in Pv[ju]] for ju in range(nu)]
    cv = cols[idx[0]]
    s = Part.BSplineSurface()
    s.buildFromPolesMultsKnots(poles, um, cv.getMultiplicities(), uk, cv.getKnots(),
                               False, False, du, cv.Degree)
    return s.toShape()


def build_solid(env, st_step=1, sew_tol=0.01, fit_tol=0.005, log=print):
    import Part
    cols = column_curves(env, st_step, tol=fit_tol, log=log)
    faces = []
    for k in range(env["K"]):
        try:
            faces.append(strip_face(env, cols, k))
        except Exception as ex:
            log("serit %d hatasi: %s" % (k, ex))
    log("serit yuzleri: %d" % len(faces))
    s1 = Part.Compound(faces).copy(); s1.sewShape(sew_tol)
    sh = s1.Shells
    log("ilk dikis: shell %s" % [len(x.Faces) for x in sh])
    base = sh[0] if len(sh) == 1 else Part.Shell(s1.Faces)
    cnt = {}
    for f in base.Faces:
        for e in f.Edges:
            if e.Degenerated:
                continue
            h = e.hashCode(); cnt.setdefault(h, [e, 0]); cnt[h][1] += 1
    free = [v[0] for v in cnt.values() if v[1] == 1]
    groups = Part.sortEdges(free)
    log("serbest kenar: %d, tel: %d, kapali: %s" % (len(free), len(groups),
                                                   [Part.Wire(g).isClosed() for g in groups]))
    caps = []
    for g in groups:
        wire = Part.Wire(g)
        if wire.Length < 1e-3:
            log("kapak teli cok kucuk (%.2e mm), atlandi" % wire.Length)
            continue
        try:
            caps.append(Part.Face(wire))
        except Exception as ex:
            # never makeFilledFace here: it can hang OCC; fit a plane instead
            pts = np.array([[v.X, v.Y, v.Z] for v in wire.Vertexes] +
                           [[p.x, p.y, p.z] for e in wire.Edges for p in e.discretize(8)])
            c = pts.mean(0); n = np.linalg.svd(pts - c)[2][2]
            sag = np.abs((pts - c) @ n).max()
            log("duz kapak olmadi (%s); duzlem sapmasi %.4f mm" % (ex, sag))
            pl = Part.Plane(_V(c), _V(n))
            caps.append(Part.Face(pl, wire))
    s2 = Part.Compound(base.Faces + caps).copy(); s2.sewShape(sew_tol)
    log("son dikis: shell %s kapali %s" % ([len(x.Faces) for x in s2.Shells],
                                          [x.isClosed() for x in s2.Shells]))
    sol = Part.Solid(s2.Shells[0])
    log("kati olusturuldu, yon kontrolu")
    if sol.Volume < 0:
        sol.reverse()
    log("yon tamam")
    return sol
