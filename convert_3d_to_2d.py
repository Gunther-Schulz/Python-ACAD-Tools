"""
Convert 3D polylines AND 3D solid entities in a DXF to 2D LWPOLYLINEs.

Usage:
  python convert_3d_to_2d.py <input.dxf> [output.dxf]
  (default output: <input>_2D.dxf in same folder)

3DSOLID: extract 8 vertices from ACIS SAB, apply transform, project to XY,
         convex hull → LWPOLYLINE
POLYLINE (3D): drop Z → LWPOLYLINE
"""
import sys
import argparse
import ezdxf
from ezdxf.acis import sab as acis_sab
from pathlib import Path
from scipy.spatial import ConvexHull
import numpy as np

parser = argparse.ArgumentParser(description="Convert 3D DXF entities to 2D LWPOLYLINEs")
parser.add_argument("input", nargs="?", default="/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/22-16 Maxsolar - Friedrichshof/Zeichnung/PVModule.dxf")
parser.add_argument("output", nargs="?", default=None)
parser.add_argument("--bottom-face", action="store_true", help="Use only the 4 bottom-Z vertices instead of full convex hull")
args = parser.parse_args()

SRC = Path(args.input)
DST = Path(args.output) if args.output else SRC.parent / (SRC.stem + "_2D.dxf")
BOTTOM_FACE = args.bottom_face

print(f"Input:  {SRC}")
print(f"Output: {DST}")

src_doc = ezdxf.readfile(str(SRC))
src_msp = src_doc.modelspace()

dst_doc = ezdxf.new(dxfversion=src_doc.dxfversion)
dst_msp = dst_doc.modelspace()

# Copy layers
for layer in src_doc.layers:
    name = layer.dxf.name
    if name == "0":
        continue
    if name not in dst_doc.layers:
        new_layer = dst_doc.layers.new(name)
        new_layer.dxf.color = layer.dxf.color if layer.dxf.hasattr("color") else 7
        if layer.dxf.hasattr("linetype"):
            new_layer.dxf.linetype = layer.dxf.linetype
        if layer.dxf.hasattr("lineweight"):
            new_layer.dxf.lineweight = layer.dxf.lineweight


def get_transform(builder):
    """Extract 4x4 world transform from SAB builder."""
    for ent in builder.entities:
        if ent.name == "transform":
            vecs = [tok.value for tok in ent.data if tok.tag == 20]
            if len(vecs) >= 4:
                rx, ry, rz, t = vecs[0], vecs[1], vecs[2], vecs[3]
                return np.array([
                    [rx[0], ry[0], rz[0], t[0]],
                    [rx[1], ry[1], rz[1], t[1]],
                    [rx[2], ry[2], rz[2], t[2]],
                    [0,     0,     0,     1    ],
                ])
    return np.eye(4)


def get_local_vertices(builder):
    """Extract vertex positions (tag 19 = LOCATION_VEC) from point entities."""
    pts = []
    for ent in builder.entities:
        if ent.name == "point":
            for tok in ent.data:
                if tok.tag == 19:
                    pts.append(tok.value)
    return pts


def solid_to_2d_poly(e):
    """Convert a 3DSOLID to a closed 2D LWPOLYLINE."""
    builder = acis_sab.parse_sab(e.sab)
    M = get_transform(builder)
    local_pts = get_local_vertices(builder)
    if not local_pts:
        return None

    # Transform to world space (keep Z for bottom-face selection)
    world_pts_3d = []
    for p in local_pts:
        h = np.array([p[0], p[1], p[2], 1.0])
        w = M @ h
        world_pts_3d.append((float(w[0]), float(w[1]), float(w[2])))

    if len(world_pts_3d) < 3:
        return None

    if BOTTOM_FACE:
        # Sort by Z, take the 4 lowest vertices
        sorted_pts = sorted(world_pts_3d, key=lambda p: p[2])
        candidates = sorted_pts[:4]
        world_pts = [(p[0], p[1]) for p in candidates]
    else:
        world_pts = [(p[0], p[1]) for p in world_pts_3d]

    pts_arr = np.array(world_pts)
    try:
        hull = ConvexHull(pts_arr)
        ordered = [world_pts[i] for i in hull.vertices]
    except Exception:
        ordered = world_pts

    attribs = {"layer": e.dxf.layer}
    if e.dxf.hasattr("color"):
        attribs["color"] = e.dxf.color
    lw = dst_msp.add_lwpolyline(ordered, dxfattribs=attribs)
    lw.close(True)
    return lw


converted_poly = 0
converted_solid = 0
solid_errors = 0
total = sum(1 for _ in src_msp)

print(f"Processing {total} entities...")

for i, e in enumerate(src_msp):
    if i % 5000 == 0 and i > 0:
        print(f"  {i}/{total}...")

    if e.dxftype() == "POLYLINE":
        pts_2d = [(p[0], p[1]) for p in e.points()]
        flags = e.dxf.flags if e.dxf.hasattr("flags") else 0
        attribs = {"layer": e.dxf.layer}
        if e.dxf.hasattr("color"):
            attribs["color"] = e.dxf.color
        lw = dst_msp.add_lwpolyline(pts_2d, dxfattribs=attribs)
        if flags & 1:
            lw.close(True)
        converted_poly += 1

    elif e.dxftype() == "3DSOLID":
        try:
            result = solid_to_2d_poly(e)
            if result:
                converted_solid += 1
            else:
                solid_errors += 1
        except Exception as ex:
            solid_errors += 1

dst_doc.saveas(str(DST))
print(f"Done.")
print(f"  {converted_poly} 3D polylines → 2D LWPOLYLINEs")
print(f"  {converted_solid} 3D solids → 2D LWPOLYLINEs")
if solid_errors:
    print(f"  {solid_errors} solids skipped (parse errors)")
print(f"Saved: {DST}")
