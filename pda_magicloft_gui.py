# -*- coding: utf-8 -*-
# Pimp My PartDesign - Magic Loft: ekranda duzenleme ve gorev paneli. Copyright (c) 2026 Sedat Kuran - MIT License
#
# Magic Loft'a cift tiklayinca (setEdit): profil ve rehber listeleri, uc kisitlari, "Hazir rehber ciz". Otomatik
# rehberler sari cizgi, noktalari tutamak (kesit noktalari sabit, beyaz; Ctrl+tik ile coklu secim); secili noktada Tasi
# gizmosu. Yesil connector noktalari kesitlerin dikisini duzeltir, kenar uclarini ve ortalarini yakalar (secilen rehber
# varken eslesmeyi rehber belirler, gizlenir). Surukerken yalniz
# numpy ile hafif ag; fare birakilinca gercek B-spline yuzey (boolean yok), Zebra aciksa yansima cizgileriyle.
# Kati OK'e basinca hesaplanir; OK degisiklikleri tek geri alma adimi olarak birakir, Cancel geri alir.
import numpy as np

import FreeCAD as App
import FreeCADGui as Gui
from pivy import coin
from PySide import QtCore, QtWidgets

import pda_common as sm
import pda_magicloft as ml
from pda_i18n import T

V = App.Vector
_editor = None
fresh = None                                               # komutun yeni olusturdugu nesne: Cancel onu da geri alir
STRIPES = 32                                              # zebra dokusu: 16 acik, 16 koyu serit
PREVIEW_ALPHA = 0.3                                        # gercek yuzey onizlemesinin saydamligi (zebra opak kalir)
SNAP_PX = 12.0                                             # connector kenar ucu / ortasini bu kadar pikselden yakalar


def start(obj):
    global _editor
    stop()
    _editor = Editor(obj)


def stop():
    global _editor
    if _editor is not None:
        e, _editor = _editor, None
        e.close()


def _style(color, size, *nodes):
    lm = coin.SoLightModel()
    lm.model = coin.SoLightModel.BASE_COLOR
    bc = coin.SoBaseColor()
    bc.rgb = color
    ds = coin.SoDrawStyle()
    ds.pointSize = size
    ds.lineWidth = size
    sep = coin.SoSeparator()
    for n in (lm, bc, ds) + nodes:
        sep.addChild(n)
    return sep


def _set_points(coord, node, P):
    P = [tuple(p) for p in P]
    coord.point.setValues(0, len(P) or 1, P or [(0.0, 0.0, 0.0)])
    coord.point.setNum(len(P) or 1)
    node.numPoints = len(P)


def _set_lines(coord, node, lines):
    P = [tuple(p) for ln in lines for p in ln]
    coord.point.setValues(0, len(P) or 1, P or [(0.0, 0.0, 0.0)])
    coord.point.setNum(len(P) or 1)
    n = [len(ln) for ln in lines]
    node.numVertices.setValues(0, len(n), n)
    node.numVertices.setNum(len(n))


def _zebra_texture():
    tex = coin.SoTexture2()
    data = bytes(bytearray(255 if (x * STRIPES // 256) % 2 == 0 else 25 for y in range(4) for x in range(256)))
    img = coin.SoSFImage()
    img.setValue(coin.SbVec2s(256, 4), 1, data)
    tex.image = img
    return tex


class Editor(object):
    def __init__(self, obj):
        self.obj, self.doc = obj, obj.Document
        self.view = Gui.ActiveDocument.ActiveView
        self.gp = obj.getGlobalPlacement() if hasattr(obj, "getGlobalPlacement") else App.Placement()
        self.inv = self.gp.inverse()
        self.picked = []                                   # secili noktalar: (rehber, nokta sirasi); sonuncu asil nokta
        self.span = None                                   # secili rehber yeri: (rehber, v)
        self.drag = None
        self.cable, self.elastic = False, 0.1
        self.show_preview = sm._param().GetBool("MagicLoftPreview", True)
        self.zebra = sm._param().GetBool("MagicLoftZebra", False)
        self.error = None
        self.fresh = obj.Name if fresh is obj else None
        ml.spread_prop(obj)
        self.doc.openTransaction(T("Edit Magic Loft"))
        self.r_coord, self.r_line = coin.SoCoordinate3(), coin.SoLineSet()
        self.f_coord, self.f_pts = coin.SoCoordinate3(), coin.SoPointSet()
        self.m_coord, self.m_pts = coin.SoCoordinate3(), coin.SoPointSet()
        self.s_coord, self.s_pts = coin.SoCoordinate3(), coin.SoPointSet()
        self.c_coord, self.c_pts = coin.SoCoordinate3(), coin.SoPointSet()
        self.l_coord, self.l_line = coin.SoCoordinate3(), coin.SoLineSet()
        self.p_coord, self.p_line = coin.SoCoordinate3(), coin.SoLineSet()     # profiller (ara profiller de gorunsun)
        self.i_coord, self.i_pts = coin.SoCoordinate3(), coin.SoPointSet()     # ara profildeki sabit rehber noktalari
        self.x_coord, self.x_pts = coin.SoCoordinate3(), coin.SoPointSet()     # connector surukleme: yakalama yerleri
        self.root = coin.SoAnnotation()
        for n in (_style((0.2, 0.75, 0.95), 2.0, self.p_coord, self.p_line),
                  _style((0.98, 0.80, 0.15), 2.5, self.r_coord, self.r_line),
                  _style((0.1, 0.8, 0.25), 1.5, self.l_coord, self.l_line),
                  _style((0.95, 0.95, 0.95), 10, self.f_coord, self.f_pts),
                  _style((0.2, 0.75, 0.95), 10, self.i_coord, self.i_pts),
                  _style((0.98, 0.80, 0.15), 10, self.m_coord, self.m_pts),
                  _style((0.6, 1.0, 0.65), 8, self.x_coord, self.x_pts),
                  _style((0.1, 0.9, 0.25), 13, self.c_coord, self.c_pts),
                  _style((1.0, 0.30, 0.0), 14, self.s_coord, self.s_pts)):
            self.root.addChild(n)
        self.parent = sm._scene_parent(self.view)
        self.real = coin.SoSeparator()                     # gercek yuzey: yama basina ag
        for f in ("renderCaching", "boundingBoxCaching", "renderCulling", "pickCulling"):
            setattr(self.real, f, coin.SoSeparator.OFF)
        self.parent.addChild(self.real)
        self._mesh_nodes()
        self.parent.addChild(self.root)
        self.gizmo = sm.MoveGizmo(self.view)
        self.parent.addChild(self.gizmo.root)
        self.zoom = QtCore.QTimer()
        self.zoom.timeout.connect(self.gizmo.update_scale)
        self.zoom.start(50)
        self._preview_on()
        self.cb_btn = self.view.addEventCallbackPivy(coin.SoMouseButtonEvent.getClassTypeId(), self.on_btn)
        self.cb_mov = self.view.addEventCallbackPivy(coin.SoLocation2Event.getClassTypeId(), self.on_move)
        self.panel = Panel(self)
        self.reload()
        Gui.Control.closeDialog()
        Gui.Control.showDialog(self.panel)

    @property
    def sel(self):
        """Asil secili nokta: gizmo ve koordinatlar onda."""
        return self.picked[-1] if self.picked else None

    @sel.setter
    def sel(self, key):
        self.picked = [] if key is None else [key]

    # --- koordinatlar ---
    def world(self, p):
        return self.gp.multVec(V(*tuple(p)))

    def local_dir(self, d):
        return self.inv.Rotation.multVec(V(d))

    # --- model ---
    def reload(self):
        """Profil / rehber / uc degisti: profiller yeniden okunur."""
        self.sel, self.span = None, None
        sk = ml.prepare(self.obj)
        self.error = sk if isinstance(sk, str) else None
        self.skin = None if self.error else sk
        if self.skin is not None and self.obj.AutoGuides and not any(ml.get_auto(self.obj)):
            ml.set_auto(self.obj, sk.auto)
        self.panel.sync()
        self.redraw()
        self.show_real()

    def auto_mode(self):
        return self.skin is not None and bool(self.obj.AutoGuides)

    def connector_on(self):
        return self.skin is not None and not self.skin.rails

    def nodes(self):
        """Otomatik rehber noktalari: [(rehber, nokta sirasi ya da None (kesit), v, nokta)]."""
        if not self.auto_mode():
            return []
        sk, out = self.skin, []
        for j in range(len(sk.us)):
            vs = np.array([x for x in sk.vn] + [p[0] for p in sk.auto[j]])
            ks = [None] * len(sk.vn) + list(range(len(sk.auto[j])))
            G = sk.base(sk.us[j:j + 1], vs)[0]
            for q, (k, v) in enumerate(zip(ks, vs)):
                off = np.zeros(3) if k is None else sk.auto[j][k][1]
                out.append((j, k, float(v), G[q] + off))
        return out

    def connectors(self):
        sk = self.skin
        return [sec.at(sk._warp(i, np.zeros(1)))[0] for i, sec in enumerate(sk.secs)]

    # --- cizim ---
    def redraw(self):
        sk = self.skin
        if sk is None:
            for c, n in ((self.f_coord, self.f_pts), (self.m_coord, self.m_pts), (self.s_coord, self.s_pts),
                         (self.c_coord, self.c_pts), (self.i_coord, self.i_pts), (self.x_coord, self.x_pts)):
                _set_points(c, n, [])
            _set_lines(self.p_coord, self.p_line, [])
            _set_lines(self.r_coord, self.r_line, [])
            _set_lines(self.l_coord, self.l_line, [])
            self._clear_mesh()
            self._clear_real()
            self.gizmo.place(None)
            return
        lines = []
        vs = np.linspace(0.0, 1.0, 101)
        if len(sk.us):
            C = sk.grid(sk.us, vs)
            lines = [[self.world(p) for p in C[j]] for j in range(len(sk.us))]
        _set_lines(self.r_coord, self.r_line, lines)
        _set_lines(self.p_coord, self.p_line, [[self.world(p) for p in sec.P[::4]] + [self.world(sec.P[0])]
                                               for sec in sk.secs])
        N = self.nodes()
        self.N = N
        fixed = [n for n in N if n[1] is None]             # kesit noktalari sabit: secilmez; ara profildekiler ayri renk
        _set_points(self.f_coord, self.f_pts, [self.world(n[3]) for n in fixed if n[2] in (0.0, 1.0)])
        _set_points(self.i_coord, self.i_pts, [self.world(n[3]) for n in fixed if n[2] not in (0.0, 1.0)])
        _set_points(self.m_coord, self.m_pts, [self.world(n[3]) for n in N if n[1] is not None])
        cur = [n for n in N if n[1] is not None and (n[0], n[1]) in self.picked]
        _set_points(self.s_coord, self.s_pts, [self.world(n[3]) for n in cur])
        if self.connector_on():
            con = [self.world(p) for p in self.connectors()]
            _set_points(self.c_coord, self.c_pts, con)
            _set_lines(self.l_coord, self.l_line, [con])
        else:
            _set_points(self.c_coord, self.c_pts, [])
            _set_lines(self.l_coord, self.l_line, [])
        snaps = []
        if self.drag is not None and self.drag["key"][0] == "connector":
            snaps = [self.world(p) for p in self.snap_points(self.drag["i"])]
        _set_points(self.x_coord, self.x_pts, snaps)
        if self.drag is None or self.drag["key"][0] == "point":
            main = [n for n in cur if (n[0], n[1]) == self.sel]
            self.gizmo.place(self.world(main[0][3]) if main else None)
        self._mesh()

    # hafif ag: yalniz numpy, surukleme adiminda
    def _mesh_nodes(self):
        sub = self.obj.TypeId == "PartDesign::FeatureSubtractivePython"
        mat = coin.SoMaterial()
        mat.diffuseColor = (0.9, 0.15, 0.15) if sub else (0.15, 0.85, 0.5)
        mat.transparency = 0.45
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
        self.t_coord, self.t_mesh = coin.SoCoordinate3(), coin.SoQuadMesh()
        lm = coin.SoLightModel()
        lm.model = coin.SoLightModel.BASE_COLOR
        col = coin.SoBaseColor()
        col.rgb = (0.1, 0.45, 0.25) if not sub else (0.5, 0.1, 0.1)
        self.t_lines = coin.SoIndexedLineSet()
        self.t_caps = coin.SoIndexedFaceSet()              # uclar: merkezden yelpaze (girintili kesitte yaklasik)
        self.tube = coin.SoSeparator()
        for f in ("renderCaching", "boundingBoxCaching", "renderCulling", "pickCulling"):
            setattr(self.tube, f, coin.SoSeparator.OFF)
        nodes = [hints, mat]
        if hasattr(coin, "SoDepthBuffer"):
            db = coin.SoDepthBuffer()
            db.write = False
            nodes.append(db)
        nodes += [self.t_coord, self.t_mesh, self.t_caps, lm, col, self.t_lines]
        for n in nodes:
            self.tube.addChild(n)
        self.parent.addChild(self.tube)

    def _clear_mesh(self):
        self.t_mesh.verticesPerRow = 0
        self.t_mesh.verticesPerColumn = 0
        self.t_lines.coordIndex.setNum(0)
        self.t_caps.coordIndex.setNum(0)

    def _mesh(self):
        if not self.show_preview or self.drag is None:     # birakinca gercek yuzey cizilir
            self._clear_mesh()
            return
        Nu, Nv = 48, 32
        G = self.skin.grid(np.arange(Nu + 1) / float(Nu), np.linspace(0.0, 1.0, Nv))
        W = self.world_array(G.reshape(-1, 3))
        P = [tuple(p) for p in W]
        n = len(P)
        caps = []
        for q, k in enumerate((0, Nv - 1)):                # alt ve ust kapak: merkez noktalari sona eklenir
            P.append(tuple(W[k::Nv][:Nu].mean(axis=0)))
            for i in range(Nu):
                caps += [n + q, i * Nv + k, (i + 1) * Nv + k, -1]
        self.t_caps.coordIndex.setValues(0, len(caps), caps)
        self.t_caps.coordIndex.setNum(len(caps))
        self.t_coord.point.setValues(0, len(P), P)
        self.t_coord.point.setNum(len(P))
        self.t_mesh.verticesPerRow = Nv
        self.t_mesh.verticesPerColumn = Nu + 1
        idx = []
        for i in range(0, Nu + 1, 4):
            idx += [i * Nv + k for k in range(Nv)] + [-1]
        self.t_lines.coordIndex.setValues(0, len(idx), idx)
        self.t_lines.coordIndex.setNum(len(idx))

    def world_array(self, P):
        m = self.gp.toMatrix()
        A = np.array([[m.A11, m.A12, m.A13], [m.A21, m.A22, m.A23], [m.A31, m.A32, m.A33]])
        return P.dot(A.T) + np.array([m.A14, m.A24, m.A34])

    # gercek yuzey: B-spline'in kendisi (kati ve boolean yok)
    def _clear_real(self):
        self.real.removeAllChildren()

    def show_real(self):
        self._clear_real()
        if self.skin is None or not self.show_preview or self.drag is not None:
            return
        try:
            surfs = self.skin.surfaces()
        except Exception as e:
            App.Console.PrintWarning(T("Magic Loft: the surface failed (%s)") % e + "\n")
            return
        sub = self.obj.TypeId == "PartDesign::FeatureSubtractivePython"
        for s in surfs:
            self.real.addChild(self._surface_node(s, sub))
        for k in (2, 3):                                   # kapaklar: katidaki yuzlerin aynisi
            try:
                self.real.addChild(self._cap_node(ml._cap([s.vIso(s.bounds()[k]).toShape() for s in surfs]), sub))
            except Exception as e:
                App.Console.PrintWarning(T("Magic Loft: the surface failed (%s)") % e + "\n")

    def _cap_node(self, face, sub):
        pts, tris = face.tessellate(0.05)
        sep = coin.SoSeparator()
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
        mat = coin.SoMaterial()
        mat.diffuseColor = (0.9, 0.3, 0.3) if sub else (0.55, 0.78, 0.68)
        mat.transparency = PREVIEW_ALPHA
        coord, fs = coin.SoCoordinate3(), coin.SoIndexedFaceSet()
        P = [tuple(self.world(p)) for p in pts]
        coord.point.setValues(0, len(P), P)
        idx = [i for t in tris for i in (t[0], t[1], t[2], -1)]
        fs.coordIndex.setValues(0, len(idx), idx)
        for n in (hints, mat, coord, fs):
            sep.addChild(n)
        return sep

    def _surface_node(self, s, sub):
        u0, u1, v0, v1 = s.bounds()
        Nu, Nv = max(2 * s.NbUPoles, 48), max(2 * s.NbVPoles, 40)
        ng = self.gp.Rotation
        P, Q = [], []
        for u in np.linspace(u0, u1, Nu + 1):
            for v in np.linspace(v0, v1, Nv):
                P.append(tuple(self.world(s.value(u, v))))
                try:
                    Q.append(tuple(ng.multVec(s.normal(u, v))))
                except Exception:
                    Q.append((0.0, 0.0, 1.0))
        sep = coin.SoSeparator()
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
        sep.addChild(hints)
        mat = coin.SoMaterial()
        if self.zebra:
            mat.diffuseColor = (1.0, 1.0, 1.0)
            mat.emissiveColor = (0.25, 0.25, 0.25)
            sep.addChild(mat)
            sep.addChild(_zebra_texture())
            sep.addChild(coin.SoTextureCoordinateEnvironment())
        else:
            mat.diffuseColor = (0.9, 0.3, 0.3) if sub else (0.55, 0.78, 0.68)
            mat.specularColor = (0.5, 0.5, 0.5)
            mat.shininess = 0.5
            mat.transparency = PREVIEW_ALPHA
            sep.addChild(mat)
        coord, norm, bind, mesh = coin.SoCoordinate3(), coin.SoNormal(), coin.SoNormalBinding(), coin.SoQuadMesh()
        coord.point.setValues(0, len(P), P)
        norm.vector.setValues(0, len(Q), Q)
        bind.value = coin.SoNormalBinding.PER_VERTEX
        mesh.verticesPerRow = Nv
        mesh.verticesPerColumn = Nu + 1
        for n in (coord, norm, bind, mesh):
            sep.addChild(n)
        return sep

    def _preview_on(self):
        vo = self.obj.ViewObject
        self.saved = dict(vis=vo.Visibility)
        base = getattr(self.obj, "BaseFeature", None)
        self.saved["base"] = base.ViewObject.Visibility if base is not None else None
        if base is not None:
            base.ViewObject.Visibility = True
        vo.Visibility = False

    def _preview_off(self):
        sv = getattr(self, "saved", None)
        if sv is None:
            return
        base = getattr(self.obj, "BaseFeature", None)
        if base is not None and sv["base"] is not None:
            base.ViewObject.Visibility = sv["base"]
        self.obj.ViewObject.Visibility = sv["vis"]

    # --- fare ---
    def _screen(self, p):
        return self.view.getPointOnViewport(self.world(p))

    @staticmethod
    def _dist(s, pos):
        return ((s[0] - pos[0]) ** 2 + (s[1] - pos[1]) ** 2) ** 0.5

    def pick_node(self, pos, radius=12.0):
        best = None
        for n in getattr(self, "N", []):
            if n[1] is None:                               # kesit noktasi: profile ait, secilmez
                continue
            s = self._screen(n[3])
            d = ((s[0] - pos[0]) ** 2 + (s[1] - pos[1]) ** 2) ** 0.5
            if d < radius and (best is None or d < best[0]):
                best = (d, n)
        return None if best is None else best[1]

    def pick_connector(self, pos, radius=12.0):
        if not self.connector_on():
            return None
        best = None
        for i, p in enumerate(self.connectors()):
            s = self._screen(p)
            d = ((s[0] - pos[0]) ** 2 + (s[1] - pos[1]) ** 2) ** 0.5
            if d < radius and (best is None or d < best[0]):
                best = (d, i)
        return None if best is None else best[1]

    def pick_rail(self, pos, radius=8.0):
        """Imlecin altindaki rehber yeri: (rehber, v) ya da None."""
        sk = self.skin
        if not self.auto_mode() or not len(sk.us):
            return None
        vs = np.linspace(0.0, 1.0, 61)
        C = sk.grid(sk.us, vs)
        best = None
        for j in range(len(sk.us)):
            for k, p in enumerate(C[j]):
                s = self._screen(p)
                d = ((s[0] - pos[0]) ** 2 + (s[1] - pos[1]) ** 2) ** 0.5
                if d < radius and (best is None or d < best[0]):
                    best = (d, j, float(vs[k]))
        return None if best is None else (best[1], best[2])

    def on_btn(self, cb):
        ev = cb.getEvent()
        if ev.getButton() != coin.SoMouseButtonEvent.BUTTON1 or self.skin is None:
            return
        pos = ev.getPosition().getValue()
        if ev.getState() != coin.SoButtonEvent.DOWN:
            if self.drag is not None:
                cb.setHandled()
                self.end_drag()
            return
        if self.drag is not None:
            self.end_drag()
        n = self.pick_node(pos)
        key = None
        if n is not None and ev.wasCtrlDown():             # Ctrl+tik: secime ekle / cikar
            cb.setHandled()
            k = (n[0], n[1])
            if k in self.picked:
                self.picked.remove(k)
            else:
                self.picked.append(k)
            self.span = None
            self.redraw()
            self.panel.sync()
            return
        if n is None or (n[0], n[1]) == self.sel:
            key = self.gizmo.pick(pos)
            if key is not None:
                n = next((x for x in self.N if (x[0], x[1]) == self.sel), None)
        if n is None:
            i = self.pick_connector(pos)
            if i is not None:
                cb.setHandled()
                self.sel = None
                self.drag = dict(key=("connector", i), i=i)
                self.redraw()
                return
            sp = self.pick_rail(pos)
            if sp is None:
                if self.picked:                            # bos yere tik: secim kalkar
                    self.sel = None
                    self.redraw()
                    self.panel.sync()
                return
            cb.setHandled()
            self.sel, self.span = None, sp
            self.redraw()
            self.panel.sync()
            return
        cb.setHandled()
        k = (n[0], n[1])
        self.span = None
        if k in self.picked:                               # secimdeki nokta: hepsi birlikte tasinir, bu asil olur
            self.picked.remove(k)
            self.picked.append(k)
        else:
            self.sel = k
        if n[1] is not None:
            self.drag = dict(key=key or ("point", 0), w0=self.world(n[3]), j=n[0], k=n[1], auto0=self._copy_auto())
            self.drag["ref"] = self.measure(pos)
            self._clear_real()
        self.redraw()
        self.panel.sync()

    def _copy_auto(self):
        return [[(v, np.array(o)) for v, o in pts] for pts in self.skin.auto]

    def measure(self, pos):
        g = self.drag
        kind, i = g["key"]
        o, d = sm._ray(self.view, pos)
        if kind == "move":
            return sm._line_param(o, d, g["w0"], sm.AXES[i])
        if kind == "plane":
            return sm._plane_hit(o, d, g["w0"], sm.AXES[i])
        den = d.dot(self.view_dir())
        return o + d * ((g["w0"] - o).dot(self.view_dir()) / den) if abs(den) > 1e-12 else g["w0"]

    def view_dir(self):
        return V(self.view.getViewDirection())

    def end_drag(self):
        g, self.drag = self.drag, None
        if g is None:
            return
        if self.auto_mode():
            ml.set_auto(self.obj, self.skin.auto)
        self.redraw()
        self.show_real()
        self.panel.sync()

    def on_move(self, cb):
        g = self.drag
        pos = cb.getEvent().getPosition().getValue()
        if g is None:
            self.gizmo.set_hover(self.gizmo.pick(pos))
            return
        if not sm._left_held():
            self.end_drag()
            return
        cb.setHandled()
        if g["key"][0] == "connector":
            self.drag_connector(g["i"], pos)
            return
        cur = self.measure(pos)
        if cur is None or g["ref"] is None:
            return
        kind, i = g["key"]
        dw = sm.AXES[i] * (cur - g["ref"]) if kind == "move" else cur - g["ref"]
        self.gizmo.place(g["w0"] + dw)
        self.move_to(g, np.array(tuple(self.local_dir(dw))))

    def snap_points(self, i):
        """Kesit i'nin yakalama yerleri: kenar uclari ve ortalari."""
        sec = self.skin.secs[i]
        return sec.at(np.array(sec.snaps) - sec.shift)

    def drag_connector(self, i, pos):
        sk = self.skin
        sec = sk.secs[i]
        dist = lambda p: self._dist(self._screen(p), pos)
        d = [dist(p) for p in self.snap_points(i)]
        q = int(np.argmin(d))
        if d[q] < SNAP_PX:
            x = sec.snaps[q]
        else:
            x = sec.s[::4][min(range(len(sec.P[::4])), key=lambda k: dist(sec.P[::4][k]))]
        value = (x - sk.base_conn[i]) % 1.0
        conn = list(self.obj.ConnectorOffsets) + [0.0] * len(sk.secs)
        conn[i] = float(value)
        self.obj.ConnectorOffsets = conn[:len(sk.secs)]
        sk.set_connector(i, value)
        self.redraw()

    def move_to(self, g, d):
        """Surukleme baslangicina gore d (yerel): secili noktalar birlikte ya da tek noktada Move neighbors ile kablo gibi."""
        sk = self.skin
        data = [[(v, np.array(o)) for v, o in pts] for pts in g["auto0"]]
        if self.cable and len(self.picked) < 2:
            self._cable(data, g["j"], g["k"], d)
        else:
            for j, k in self.picked:
                data[j][k] = (data[j][k][0], data[j][k][1] + d)
        sk.auto = data
        self.redraw()
        self.panel.sync()

    def _cable(self, data, j, k, d):
        """Kablo: noktanin kesit araligindaki dugumler pda_common.rail_cable ile; kesitler sabit."""
        sk = self.skin
        v = data[j][k][0]
        a = max(x for x in sk.vn if x <= v)
        b = min(x for x in sk.vn if x >= v)
        idx = sorted([q for q, p in enumerate(data[j]) if a < p[0] < b], key=lambda q: data[j][q][0])
        vs = np.array([a] + [data[j][q][0] for q in idx] + [b])
        G = sk.base(sk.us[j:j + 1], vs)[0]
        N = G.copy()
        for n, q in enumerate(idx):
            N[n + 1] = G[n + 1] + data[j][q][1]
        ta = (N[1] - N[0]) / max(np.linalg.norm(N[1] - N[0]), 1e-9)
        tb = (N[-1] - N[-2]) / max(np.linalg.norm(N[-1] - N[-2]), 1e-9)
        h = idx.index(k) + 1
        X = sm.rail_cable(N, h, d, True, self.elastic, ta, tb)
        for n, q in enumerate(idx):
            data[j][q] = (data[j][q][0], X[n + 1] - G[n + 1])

    # --- panel islemleri ---
    def set_coord(self, axis, val):
        cur = [n for n in getattr(self, "N", []) if self.sel == (n[0], n[1]) and n[1] is not None]
        if not cur:
            return
        w = self.world(cur[0][3])
        t = V(w)
        setattr(t, "xyz"[axis], val)
        if (t - w).Length < 1e-9:
            return
        g = dict(j=cur[0][0], k=cur[0][1], auto0=self._copy_auto())
        self.move_to(g, np.array(tuple(self.local_dir(t - w))))
        ml.set_auto(self.obj, self.skin.auto)
        self.show_real()

    def add_point(self):
        """Secili rehber yerine; yoksa secili noktanin rehberinde en buyuk boslugun ortasina yeni nokta."""
        sk = self.skin
        if not self.auto_mode():
            return
        if self.span is not None:
            j, v = self.span
        elif self.sel is not None:
            j = self.sel[0]
            vs = sorted(list(sk.vn) + [p[0] for p in sk.auto[j]])
            v = max(zip(vs, vs[1:]), key=lambda x: x[1] - x[0])
            v = (v[0] + v[1]) / 2
        else:
            return
        if min(abs(v - x) for x in list(sk.vn) + [p[0] for p in sk.auto[j]]) < 1e-3:
            return
        cur = sk.correction(j, np.array([v]))[0]           # yeni nokta egrinin uzerinde: sekil degismez
        sk.auto[j].append((float(v), cur))
        sk.auto[j].sort(key=lambda x: x[0])
        ml.set_auto(self.obj, sk.auto)
        self.sel = (j, [p[0] for p in sk.auto[j]].index(float(v)))
        self.span = None
        self.redraw()
        self.show_real()
        self.panel.sync()

    def delete_point(self):
        if not self.auto_mode() or not self.picked:
            return
        for j, k in sorted(self.picked, reverse=True):     # sondan: kalanlarin sirasi kaymaz
            del self.skin.auto[j][k]
        ml.set_auto(self.obj, self.skin.auto)
        self.sel = None
        self.redraw()
        self.show_real()
        self.panel.sync()

    def set_guide_count(self, n):
        if int(self.obj.GuideCount) == int(n):
            return
        self.obj.GuideCount = int(n)
        self.obj.AutoGuideRails, self.obj.AutoGuideV, self.obj.AutoGuideOffsets = [], [], []   # yeniden kurulur
        self.reload()

    def set_prop(self, name, val):
        if getattr(self.obj, name) != val:
            setattr(self.obj, name, val)
            self.reload()

    def set_view(self, name, val):
        setattr(self, {"MagicLoftPreview": "show_preview", "MagicLoftZebra": "zebra"}[name], bool(val))
        sm._param().SetBool(name, bool(val))
        self.redraw()
        self.show_real()

    # --- bitis ---
    def finish(self, ok):
        self.finished = True
        self.close()
        global _editor
        _editor = None
        if ok:
            self.doc.commitTransaction()
            self.obj.touch()
        else:
            self.doc.abortTransaction()                    # resetEdit acik islemi kapatir: once geri alinir
        Gui.ActiveDocument.resetEdit()
        while not ok and self.fresh and self.doc.getObject(self.fresh) is not None and self.doc.UndoCount:
            self.doc.undo()                                # yeni nesne: olusturma adimi da gider
        self.doc.recompute()

    def close(self):
        if getattr(self, "closed", False):
            return
        self.closed = True
        if not getattr(self, "finished", False):
            self.doc.commitTransaction()
            self.obj.touch()
            self.doc.recompute()
        try:
            self.view.removeEventCallbackPivy(coin.SoMouseButtonEvent.getClassTypeId(), self.cb_btn)
            self.view.removeEventCallbackPivy(coin.SoLocation2Event.getClassTypeId(), self.cb_mov)
        except Exception:
            pass
        self.zoom.stop()
        for n in (self.tube, self.real, self.gizmo.root, self.root):
            try:
                self.parent.removeChild(n)
            except Exception:
                pass
        self._preview_off()
        Gui.Control.closeDialog()


class Panel(object):
    def __init__(self, ed):
        self.ed = ed
        self.form = w = QtWidgets.QWidget()
        w.setWindowTitle(T("Magic Loft"))
        lay = QtWidgets.QVBoxLayout(w)
        self.err = QtWidgets.QLabel()
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: #d9534f;")
        lay.addWidget(self.err)
        # profiller
        g = QtWidgets.QGroupBox(T("Profiles"))
        grid = QtWidgets.QGridLayout(g)
        self.profiles = QtWidgets.QListWidget()
        self.profiles.setMaximumHeight(90)
        grid.addWidget(self.profiles, 0, 0, 1, 4)
        for c, (text, fn) in enumerate(((T("Up"), lambda: self.move_profile(-1)), (T("Down"), lambda: self.move_profile(1)),
                                        (T("Add selection"), self.add_profiles), (T("Remove"), self.remove_profile))):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda checked=False, fn=fn: fn())
            grid.addWidget(b, 1, c)
        lay.addWidget(g)
        # uclar
        g = QtWidgets.QGroupBox(T("Start / end constraints"))
        grid = QtWidgets.QGridLayout(g)
        self.ends = {}
        for r, (name, label) in enumerate((("Start", T("Start")), ("End", T("End")))):
            grid.addWidget(QtWidgets.QLabel(label), r, 0)
            c = QtWidgets.QComboBox()
            for e, text in zip(ml.ENDS, (T("Free"), T("Normal to profile"), T("Tangent to face"))):
                c.addItem(text, e)
            c.setCurrentIndex(ml.ENDS.index(getattr(ed.obj, name + "Constraint")))
            c.currentIndexChanged.connect(lambda i, name=name: self.ed.set_prop(name + "Constraint", ml.ENDS[i]))
            grid.addWidget(c, r, 1)
            s = self._spin(0.05, 10.0, 2, " x", 0.1)
            s.setValue(getattr(ed.obj, name + "Strength"))
            s.setToolTip(T("Tangent strength"))
            s.valueChanged.connect(lambda v, name=name: self.ed.set_prop(name + "Strength", float(v)))
            grid.addWidget(s, r, 2)
            self.ends[name] = (c, s)
        lay.addWidget(g)
        # rehberler
        g = QtWidgets.QGroupBox(T("Guides"))
        grid = QtWidgets.QGridLayout(g)
        self.auto = QtWidgets.QCheckBox(T("Draw ready guides"))
        self.auto.setToolTip(T("Automatic guides you edit on screen. The selected guides are kept but not used while "
                               "this is on"))
        self.auto.setChecked(bool(ed.obj.AutoGuides))
        self.auto.toggled.connect(lambda on: self.ed.set_prop("AutoGuides", bool(on)))
        grid.addWidget(self.auto, 0, 0, 1, 2)
        grid.addWidget(QtWidgets.QLabel(T("Number of guides")), 0, 2)
        self.count = QtWidgets.QSpinBox()
        self.count.setRange(1, 32)
        self.count.setKeyboardTracking(False)
        self.count.setValue(int(ed.obj.GuideCount))
        self.count.setToolTip(T("Changing the number rebuilds the automatic guides; edits on them are lost"))
        self.count.valueChanged.connect(lambda v: self.ed.set_guide_count(v))
        grid.addWidget(self.count, 0, 3)
        grid.addWidget(QtWidgets.QLabel(T("Guide influence")), 1, 0, 1, 2)
        self.spread = self._spin(0.5, 4.0, 2, " x", 0.25)
        self.spread.setToolTip(T("How far a guide acts sideways: larger gives a broader, smoother surface between "
                                 "guides, smaller a narrower ridge"))
        self.spread.setValue(float(ed.obj.GuideSpread))
        self.spread.valueChanged.connect(lambda v: self.ed.set_prop("GuideSpread", float(v)))
        grid.addWidget(self.spread, 1, 2, 1, 2)
        self.guides = QtWidgets.QListWidget()
        self.guides.setMaximumHeight(70)
        grid.addWidget(self.guides, 2, 0, 1, 4)
        self.g_add = QtWidgets.QPushButton(T("Add selection"))
        self.g_add.clicked.connect(lambda checked=False: self.add_guides())
        grid.addWidget(self.g_add, 3, 0, 1, 2)
        self.g_del = QtWidgets.QPushButton(T("Remove"))
        self.g_del.clicked.connect(lambda checked=False: self.remove_guide())
        grid.addWidget(self.g_del, 3, 2, 1, 2)
        lay.addWidget(g)
        # secili nokta
        g = QtWidgets.QGroupBox(T("Selected point"))
        g.setToolTip(T("Ctrl+click guide points to select several: they move and delete together"))
        self.point_box = g
        grid = QtWidgets.QGridLayout(g)
        self.xyz = []
        for k, a in enumerate("XYZ"):
            grid.addWidget(QtWidgets.QLabel(a), k, 0)
            b = self._spin(-1e7, 1e7, 3, " mm")
            b.editingFinished.connect(lambda k=k, b=b: self.ed.set_coord(k, b.value()))
            grid.addWidget(b, k, 1)
            self.xyz.append(b)
        row = QtWidgets.QHBoxLayout()
        for text, fn in ((T("Add point"), ed.add_point), (T("Delete point"), ed.delete_point)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda checked=False, fn=fn: fn())
            row.addWidget(b)
        grid.addLayout(row, 3, 0, 1, 2)
        self.cable = QtWidgets.QCheckBox(T("Move neighbors"))
        self.cable.setToolTip(T("The guide follows the dragged point like a cable"))
        self.cable.toggled.connect(lambda on: setattr(self.ed, "cable", bool(on)))
        grid.addWidget(self.cable, 4, 0, 1, 2)
        grid.addWidget(QtWidgets.QLabel(T("Elasticity")), 5, 0)
        self.elastic = self._spin(0.0, 1.0, 2, "", 0.05)
        self.elastic.setValue(ed.elastic)
        self.elastic.valueChanged.connect(lambda v: setattr(self.ed, "elastic", float(v)))
        grid.addWidget(self.elastic, 5, 1)
        lay.addWidget(g)
        # secenekler
        import pda_commands
        g = QtWidgets.QGroupBox(T("Options"))
        grid = QtWidgets.QGridLayout(g)
        prev = QtWidgets.QCheckBox(T("Show preview"))
        prev.setChecked(ed.show_preview)
        prev.toggled.connect(lambda on: self.ed.set_view("MagicLoftPreview", on))
        grid.addWidget(prev, 0, 0)
        zeb = QtWidgets.QCheckBox(T("Zebra"))
        zeb.setToolTip(T("Reflection stripes on the surface, to judge its quality. Shown when you release the mouse"))
        zeb.setChecked(ed.zebra)
        zeb.toggled.connect(lambda on: self.ed.set_view("MagicLoftZebra", on))
        grid.addWidget(zeb, 0, 1)
        grid.addWidget(QtWidgets.QLabel(T("Fit tolerance")), 1, 0)
        tol = self._spin(0.001, 1.0, 3, " mm", 0.005)
        tol.setToolTip(T("Largest deviation of the surface fit: smaller is more exact, larger has fewer control points"))
        tol.setValue(float(ed.obj.FitTolerance))
        tol.valueChanged.connect(lambda v: self.ed.set_prop("FitTolerance", float(v)))
        grid.addWidget(tol, 1, 1)
        own = QtWidgets.QCheckBox(T("New Magic Lofts in their own Body"))
        own.setChecked(pda_commands.own_body("MagicLoftOwnBody"))
        own.toggled.connect(lambda on: pda_commands.set_own_body(on, "MagicLoftOwnBody"))
        grid.addWidget(own, 2, 0, 1, 2)
        lay.addWidget(g)
        lay.addStretch()
        self.fill_lists()

    @staticmethod
    def _spin(lo, hi, dec, suffix, step=1.0):
        b = QtWidgets.QDoubleSpinBox()
        b.setRange(lo, hi)
        b.setDecimals(dec)
        b.setSuffix(suffix)
        b.setSingleStep(step)
        b.setKeyboardTracking(False)
        return b

    @staticmethod
    def _label(item):
        o, subs = item
        return o.Label + (" : " + ", ".join(subs) if subs else "")

    def fill_lists(self):
        for box, name in ((self.profiles, "Profiles"), (self.guides, "Guides")):
            row = box.currentRow()
            box.clear()
            for it in ml.get_items(self.ed.obj, name):
                box.addItem(self._label(it))
            box.setCurrentRow(min(row, box.count() - 1))

    def _set(self, name, items, row=None):
        try:
            ml.set_items(self.ed.obj, name, items)
        except Exception as e:                             # or. baska Body'den baglanti
            App.Console.PrintWarning(T("Magic Loft: can't use that selection (%s)") % e + "\n")
            return
        self.fill_lists()
        if row is not None:
            (self.profiles if name == "Profiles" else self.guides).setCurrentRow(row)
        self.ed.reload()

    def move_profile(self, d):
        items = ml.get_items(self.ed.obj, "Profiles")
        i = self.profiles.currentRow()
        if i < 0 or not 0 <= i + d < len(items):
            return
        items[i], items[i + d] = items[i + d], items[i]
        conn = (list(self.ed.obj.ConnectorOffsets) + [0.0] * len(items))[:len(items)]
        conn[i], conn[i + d] = conn[i + d], conn[i]
        self.ed.obj.ConnectorOffsets = conn
        self._set("Profiles", items, i + d)

    def add_profiles(self):
        prof = ml.classify(Gui.Selection.getSelectionEx())[0]
        if prof:
            self.ed.obj.ConnectorOffsets = list(self.ed.obj.ConnectorOffsets) + [0.0] * len(prof)
            self._set("Profiles", ml.get_items(self.ed.obj, "Profiles") + prof)

    def remove_profile(self):
        items = ml.get_items(self.ed.obj, "Profiles")
        i = self.profiles.currentRow()
        if 0 <= i < len(items) and len(items) > 2:
            del items[i]
            conn = (list(self.ed.obj.ConnectorOffsets) + [0.0] * (len(items) + 1))[:len(items) + 1]
            del conn[i]
            self.ed.obj.ConnectorOffsets = conn
            self._set("Profiles", items)

    def add_guides(self):
        guides = ml.classify(Gui.Selection.getSelectionEx())[1]
        if guides:
            self._set("Guides", ml.get_items(self.ed.obj, "Guides") + guides)

    def remove_guide(self):
        items = ml.get_items(self.ed.obj, "Guides")
        i = self.guides.currentRow()
        if 0 <= i < len(items):
            del items[i]
            self._set("Guides", items)

    def sync(self):
        ed = self.ed
        self.err.setText(ed.error or "")
        self.err.setVisible(bool(ed.error))
        auto = bool(ed.obj.AutoGuides)
        self.count.setEnabled(auto)
        for x in (self.guides, self.g_add, self.g_del):    # pasif mod: secimler saklanir, soluk gorunur
            x.setEnabled(not auto)
        self.point_box.setEnabled(auto)
        self.cable.setEnabled(len(ed.picked) < 2)          # kablo tek noktada; birden coksu birlikte tasinir
        cur =[n for n in getattr(ed, "N", []) if ed.sel == (n[0], n[1]) and n[1] is not None]
        for k, b in enumerate(self.xyz):
            b.setEnabled(bool(cur))
            if cur and not b.hasFocus():
                b.blockSignals(True)
                b.setValue(getattr(ed.world(cur[0][3]), "xyz"[k]))
                b.blockSignals(False)

    def getStandardButtons(self):
        return int(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)

    def accept(self):
        self.ed.finish(True)
        return True

    def reject(self):
        self.ed.finish(False)
        return True
