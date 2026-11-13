# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
# Pimp My FreeCAD - Body Sweep (work in progress, no toolbar command yet). Copyright (c) 2026 Sedat Kuran - MIT License
"""Body sweep: sweep a convex solid tool along a guide and cut a target, in one go.

The swept envelope is built directly (exact sections perpendicular to the path -> corner tracks -> B-spline
strip faces), not as a boolean of many tool copies. In FreeCAD select, in this order: tool solid, guide
(edges / wire / sketch), target solid, [optional] support face (the tool stays normal to it), then:

    import pda_bodysweep; pda_bodysweep.run_selection()

Needs numpy, scipy and shapely. Every step is logged to <temp>/pda_bodysweep_log.txt (LOG_FILE).
"""
import builtins, time, os, tempfile
import numpy as np
import FreeCAD as App, Part

LOG_FILE = os.path.join(tempfile.gettempdir(), "pda_bodysweep_log.txt")


# ----------------------------------------------------------------- geometry inputs
def guide_points(edges, start_hint, step=0.25):
    """Ordered points of a chain of edges, starting at the end nearest start_hint,
    plus the path lengths where its pieces meet (curvature may jump there)."""
    edges = list(edges)
    V = lambda v: np.array([v.X, v.Y, v.Z])
    ends = [V(e.Vertexes[0]) for e in edges] + [V(e.Vertexes[-1]) for e in edges]
    cur = min(ends, key=lambda p: np.linalg.norm(p - start_hint))
    chain, breaks, acc = [], [], 0.0
    while edges:
        nxt = None
        for e in edges:
            a, b = V(e.Vertexes[0]), V(e.Vertexes[-1])
            if np.linalg.norm(a - cur) < 1e-4:
                nxt = (e, False, b); break
            if np.linalg.norm(b - cur) < 1e-4:
                nxt = (e, True, a); break
        if nxt is None:
            break
        e, rev, cur = nxt; edges.remove(e)
        ps = np.array([[p.x, p.y, p.z] for p in e.discretize(max(4, int(e.Length / step)))])
        chain.append(ps[::-1] if rev else ps)
        acc += e.Length; breaks.append(acc)
    if edges:
        raise ValueError("kilavuz kenarlari tek bir zincir olusturmuyor (%d kenar artti)" % len(edges))
    pts = np.concatenate([chain[0]] + [c[1:] for c in chain[1:]])
    return pts, breaks[:-1]


def surface_ups(face, pts):
    ups = []
    for p in pts:
        u, v = face.Surface.parameter(App.Vector(*p))
        n = face.normalAt(u, v); ups.append((n.x, n.y, n.z))
    return np.array(ups)


def min_turn_radius(pts, ups=None):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    tg = np.gradient(pts, s, axis=0); tg /= np.linalg.norm(tg, axis=1, keepdims=True)
    dt = np.gradient(tg, s, axis=0)
    if ups is not None:                     # bend within the support surface only
        dt = dt - ups * np.sum(dt * ups, axis=1, keepdims=True)
    k = np.linalg.norm(dt, axis=1)[3:-3]
    return 1.0 / max(k.max(), 1e-12)


def mesh_volume(s, tol=0.05):
    v, t = s.tessellate(tol)
    V = np.array([(p.x, p.y, p.z) for p in v]); T = np.array(t)
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    return np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6


def _matrix(A, b):
    return App.Matrix(A[0, 0], A[0, 1], A[0, 2], b[0], A[1, 0], A[1, 1], A[1, 2], b[1],
                      A[2, 0], A[2, 1], A[2, 2], b[2], 0, 0, 0, 1)


def halfspace(P, n, S):
    n = n / np.linalg.norm(n); a = np.cross(n, [0, 0, 1.0])
    if np.linalg.norm(a) < 1e-6:
        a = np.cross(n, [1.0, 0, 0])
    a /= np.linalg.norm(a); b = np.cross(n, a); o = P - a * S / 2 - b * S / 2
    bx = Part.makeBox(S, S, S); bx.transformShape(_matrix(np.c_[n, a, b], o)); return bx


def _shape(x):
    return x.Shape if hasattr(x, "Shape") else x


def _solid(x):
    """A single solid from an object / shape (compounds of one solid are unwrapped)."""
    s = _shape(x)
    if s.ShapeType != "Solid":
        if len(s.Solids) != 1:
            raise ValueError("tek bir kati bekleniyordu, %d kati bulundu" % len(s.Solids))
        s = s.Solids[0]
    return s


# ---------------------------------------------------------------------- main
def run(doc, tool, guide, target=None, support=None, commit=None, fit_tol=0.01, min_strip=1.0,
        min_track_len=10.0, twist_deg=0.0, result_name="BodySweepResult", show=True,
        verify=True, adaptive=True, sec_tol=0.01):
    """tool / target: objects or shapes; guide: object, shape or list of edges;
    support: a face (or object whose first face is used) the tool stays normal to;
    twist_deg: total roll of the tool about the path tangent, spread evenly over the
    path length (a Draft polar array along its own axis is such a screw motion).
    Without a target the result is the swept solid itself."""
    import pda_bodysweep_sections as es
    import pda_bodysweep_brep as bb
    log = []; builtins._bslog = log
    logf = open(LOG_FILE, "w")
    T0 = time.time()
    def L_(s):
        line = "%5.1fs %s" % (time.time() - T0, s); log.append(line); logf.write(line + "\n"); logf.flush()
    out = None
    try:
        tsh = _solid(tool)
        tgt = _shape(target) if target is not None else None
        gsh = guide if isinstance(guide, (list, tuple)) else _shape(guide)
        gedges = list(guide) if isinstance(guide, (list, tuple)) else list(gsh.Edges)
        # convexity: the tool must equal its convex hull
        tess = max(0.005, tsh.BoundBox.DiagonalLength / 5000)     # tool hull resolution
        v, _ = tsh.tessellate(tess)
        Pw = np.array([(q.x, q.y, q.z) for q in v])
        from scipy.spatial import ConvexHull
        hv = ConvexHull(Pw).volume
        if hv > tsh.Volume * 1.01:
            raise ValueError("alet disbukey degil (zarf hacmi %%%.1f fazla); disbukey parcalara bolunmeli"
                             % (100 * (hv / tsh.Volume - 1)))
        c = tsh.CenterOfMass
        pts, breaks = guide_points(gedges, np.array([c.x, c.y, c.z]))
        if not tsh.isInside(App.Vector(*pts[0]), 1e-3, True):
            L_("UYARI: kilavuzun baslangici aletin icinde degil")
        sv = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        tg = np.gradient(pts, sv, axis=0); tg /= np.linalg.norm(tg, axis=1, keepdims=True)
        if support is not None:
            face = support if isinstance(support, Part.Face) else _shape(support).Faces[0]
            ups = surface_ups(face, pts); frame = "destek yuzeyi normali"
        else:
            ups = np.array([0, 0, 1.0]) - tg * tg[:, 2:3]; frame = "dunya Z"
            if np.linalg.norm(ups, axis=1).min() < 1e-3:
                raise ValueError("yol bir yerde dikey: dunya Z yukari yon olamaz, destek yuzeyi verin")
        ups = ups - tg * np.sum(ups * tg, axis=1, keepdims=True)
        ups /= np.linalg.norm(ups, axis=1, keepdims=True)
        if twist_deg:
            th = np.radians(twist_deg) * sv / sv[-1]
            ups = ups * np.cos(th)[:, None] + np.cross(tg, ups) * np.sin(th)[:, None]
            frame += ", burulma %.1f derece" % twist_deg
        path = es.PolyPath(pts, mode="up", ups=ups)
        ups_bend = ups if support is not None else None
        p0, M0 = path.at(0.0)
        tool_c = es.ConvexTool.from_points((Pw - p0) @ M0)
        half_w = np.abs(tool_c.V[:, 1]).max()
        rmin = min_turn_radius(pts, ups_bend)
        L_("yol %.2f mm, %d parca, yukari yon: %s, en dar viraj %.1f mm (alet yari genisligi %.1f)"
           % (path.L, len(breaks) + 1, frame, rmin, half_w))
        if rmin < half_w:
            L_("UYARI: viraj aletten dar, kesit duzlemleri zarfin icinde kesisebilir")
        pose_step = max(0.25, path.L / 2000)
        sw = es.Sweep(tool_c, path, pose_step=pose_step, ends="tube")
        # how far the tube must reach past the path ends: behind the start, back to
        # the rearmost point of the tool's forward-facing faces; past the end, up to the
        # foremost point of its backward-facing faces (0 for a tool centred on the path)
        (pa, Ma), (pb, Mb) = sw.PM[0], sw.PM[-1]
        b0, _ = tool_c.silhouette_extent(Ma, pa, Ma[:, 0])
        _, a1 = tool_c.silhouette_extent(Mb, pb, Mb[:, 0])
        ext = (max(0.0, -b0), max(0.0, a1))
        # a turning tool: later poses swing out behind / ahead of the static end bodies
        # (corner flares); the tube must carry on until they have vanished, otherwise the
        # end body is a step smaller than the envelope next to it
        rch = (sw.protrusion_reach(0), sw.protrusion_reach(1))
        if max(rch) > 0:
            L_("donen aletin tasmasi: basta %.2f mm, sonda %.2f mm" % rch)
        ext = (max(ext[0], rch[0]), max(ext[1], rch[1]))
        L_("tup uzatmasi: basta %.2f mm, sonda %.2f mm" % ext)
        if adaptive:
            # few stations where the envelope is calm, dense where it changes; every
            # interval is checked against a true mid section (sec_tol mm)
            env = es.build_envelope_adaptive(sw, tol=sec_tol, tube_ext=ext, fixed=breaks,
                                             ds_min=max(0.1, min(0.25, path.L / 2000)),
                                             seg_step=1.0, min_strip=min_strip,
                                             min_track_len=min_track_len, log=L_)
        else:
            ds = max(0.25, min(4.0, path.L / 80))     # station spacing scales with the path
            env = es.build_envelope(sw, ds_mid=ds, seg_step=1.0, min_strip=min_strip,
                                    min_track_len=min_track_len, tube_ext=ext)
        env["breaks"] = breaks
        L_("kafes: istasyon %d, kose izi %d, halka noktasi %d" % (len(env["secs"]), env["K"], env["N"]))
        # slot ends: the exact tool at the first / last pose, clipped at the tube end planes;
        # the tube's end rings are snapped onto those exact sections so the seam is shared
        S = 4 * tsh.BoundBox.DiagonalLength
        pieces = []
        for ri, (pm, (Pc, nc)) in ((0, (sw.PM[0], env["clip"][0])), (-1, (sw.PM[-1], env["clip"][1]))):
            A = pm[1] @ M0.T
            b_ = pm[0] - A @ p0
            body = tsh.copy(); body.transformShape(_matrix(A, b_))
            # clip in the tool's own frame, then move the clipped piece: clipping the
            # turned world copy produced invalid pieces (rotation round-off)
            loc = tsh.common(halfspace(A.T @ (Pc - b_), A.T @ nc, S))
            pc = loc.copy(); pc.transformShape(_matrix(A, b_))
            if not pc.isValid():
                pc = body.common(halfspace(Pc, nc, S))
            if pc.Volume < 1e-3 * tsh.Volume:
                # the tube already covers (almost) all of the tool here: a hair-thin
                # leftover would only add sliver faces at the seam - the tube cap closes it
                L_("%s parcasi ihmal edildi (hacim %.3f mm3)" % ("baslangic" if ri == 0 else "bitis", pc.Volume))
                continue
            pieces.append(pc)
            ws = body.slice(App.Vector(*nc), float(nc @ Pc))
            if not ws:
                continue
            comp = Part.Compound(ws)
            ring = env["rings"][ri]
            for j, p in enumerate(ring):
                dd, pr, _ = Part.Vertex(App.Vector(*p)).distToShape(comp)
                if dd < 0.05:
                    q = pr[0][1]; ring[j] = (q.x, q.y, q.z)
        sol = bb.build_solid(env, st_step=1, sew_tol=0.01, fit_tol=fit_tol, log=L_)
        L_("zarf tupu: isValid %s, %d yuz" % (sol.isValid(), len(sol.Faces)))
        if tgt is not None:
            t = time.time(); res = tgt.cut([sol] + pieces, 1e-3)
            L_("KESME %.1fs: isValid %s, %d yuz, en buyuk kenar toleransi %.4f"
               % (time.time() - t, res.isValid(), len(res.Faces), max(e.Tolerance for e in res.Edges)))
            if verify:
                vt = max(0.01, res.BoundBox.DiagonalLength / 5000)
                exp = mesh_volume(tgt, vt) - mesh_volume(tgt.common(sol.fuse(pieces) if pieces else sol), vt)
                L_("hacim: OCC %.1f | ag %.1f | beklenen %.1f" % (res.Volume, mesh_volume(res, vt), exp))
        else:
            t = time.time(); res = sol.fuse(pieces, 1e-3) if pieces else sol.copy()
            try:
                res = res.removeSplitter()
            except Exception:
                pass
            if res.Solids and len(res.Solids) == 1:
                res = res.Solids[0]
            L_("ZARF KATISI %.1fs: isValid %s, %d katı, %d yuz, en buyuk kenar toleransi %.4f"
               % (time.time() - t, res.isValid(), len(res.Solids), len(res.Faces), max(e.Tolerance for e in res.Edges)))
            if verify:
                vt = max(0.01, res.BoundBox.DiagonalLength / 5000)
                L_("hacim: OCC %.1f | ag %.1f" % (res.Volume, mesh_volume(res, vt)))
        out = dict(env=env, sw=sw, path=path, sol=sol, pieces=pieces, res=res)
        builtins._BS = out
        if show and commit is not None:
            def apply():
                o = doc.getObject(result_name) or doc.addObject("Part::Feature", result_name)
                o.Shape = res; o.ViewObject.Visibility = True
                if hasattr(target, "ViewObject"):
                    target.ViewObject.Visibility = False
                doc.recompute()
            commit(apply)
    except Exception:
        import traceback; L_("HATA " + traceback.format_exc()[-1500:])
    L_("bitti"); logf.close()
    return out


def selection():
    """(doc, tool, guide, target, support) from the current GUI selection order."""
    import FreeCADGui as Gui
    sel = Gui.Selection.getSelectionEx()
    if len(sel) < 3:
        raise ValueError("sirayla secin: alet, kilavuz, hedef, [destek yuzeyi]")
    tool, guide, target = sel[0].Object, sel[1], sel[2].Object
    gedges = [s for s in guide.SubObjects if isinstance(s, Part.Edge)] or list(guide.Object.Shape.Edges)
    support = None
    if len(sel) > 3:
        subs = [s for s in sel[3].SubObjects if isinstance(s, Part.Face)]
        support = subs[0] if subs else sel[3].Object.Shape.Faces[0]
    return App.ActiveDocument, tool, gedges, target, support


def run_selection(**kw):
    """Run on the GUI selection (blocks the GUI for a few seconds)."""
    doc, tool, guide, target, support = selection()
    res = run(doc, tool, guide, target, support, commit=lambda f: f(), **kw)
    print("\n".join(builtins._bslog))
    return res
