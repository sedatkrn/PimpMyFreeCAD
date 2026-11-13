"""FreeCAD-free smoke test of the Body Sweep core: box tool along an arc -> closed manifold mesh.
Run from the repo root:  python3 tests/smoke_bodysweep_core.py   (needs numpy, scipy, shapely)"""
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pda_bodysweep_sections as es
# arc path in XY, box tool 10x6x4 centred on path start
th = np.linspace(0, np.pi/2, 400); R = 60.0
pts = np.c_[R*np.sin(th), R*(1-np.cos(th)), np.zeros_like(th)]
path = es.PolyPath(pts, mode="up", ups=np.tile([0,0,1.0], (len(pts),1)))
p0, M0 = path.at(0.0)
tool = es.ConvexTool.box(10, 6, 4, o=np.array([-5, -3, -2.0]))
sw = es.Sweep(tool, path, pose_step=max(0.25, path.L/2000), ends="tube")
t=time.time()
env = es.build_envelope_adaptive(sw, tol=0.01, tube_ext=(0.0, 0.0), fixed=[], ds_min=0.25, log=print)
print("stations", len(env["secs"]), "tracks", env["K"], "N", env["N"], "%.1fs" % (time.time()-t))
V, F = es.envelope_mesh(env); print(es.mesh_stats(V, F))
# expected: swept volume of box along arc ~ area(6x4)*L plus end effects
print("path L", path.L, "approx prism", 6*4*path.L)
st = es.mesh_stats(V, F)
assert st["boundary"] == 0 and st["nonmanifold"] == 0, st
assert 0.95 < st["volume"] / (6*4*path.L) < 1.10, st
print("OK")
