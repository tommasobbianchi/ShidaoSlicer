#!/usr/bin/env python3
"""Render a belt-printer G-code as a 3D toolpath preview PNG.

Usage:
    gcode_preview.py <file.gcode> --up-to-layer N [--out file.png] \
                     [--elev 28 --azim -55 --width 1200 --height 900]

Shows all travels and extrusions from layer 1 to N inclusive.
Extrusion lines colored by layer progression (viridis). Travels faded gray.

For belt printers: coords are machine-space (Y = along belt, Z = height vs belt).
The 45° inclined slicing shows up as the characteristic tapered "wedge" shape.
"""

import argparse
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from matplotlib import cm


RE_G1 = re.compile(r"^G[01]\s")
RE_X = re.compile(r"X(-?[0-9.]+)")
RE_Y = re.compile(r"Y(-?[0-9.]+)")
RE_Z = re.compile(r"Z(-?[0-9.]+)")
RE_E = re.compile(r"E(-?[0-9.]+)")


def parse(gcode_path: Path, max_layer: int):
    """Parse G1 moves up to and including `max_layer`.

    Returns (ext_segments, travel_segments) where each segment is
    ((x0,y0,z0), (x1,y1,z1), layer_index).
    """
    x = y = z = 0.0
    prev_e = None
    layer = 0
    ext = []
    travel = []
    for line in gcode_path.read_text().splitlines():
        if ";LAYER_CHANGE" in line:
            layer += 1
            if layer > max_layer:
                break
            continue
        if not RE_G1.match(line):
            continue
        # strip comments
        cmd = line.split(";", 1)[0]
        nx = ny = nz = None
        mx = RE_X.search(cmd); my = RE_Y.search(cmd); mz = RE_Z.search(cmd); me = RE_E.search(cmd)
        if mx: nx = float(mx.group(1))
        if my: ny = float(my.group(1))
        if mz: nz = float(mz.group(1))
        new_x = nx if nx is not None else x
        new_y = ny if ny is not None else y
        new_z = nz if nz is not None else z
        is_ext = False
        if me:
            e_val = float(me.group(1))
            if prev_e is not None and e_val > prev_e + 1e-4:
                is_ext = True
            prev_e = e_val
        seg = ((x, y, z), (new_x, new_y, new_z), layer)
        if is_ext:
            ext.append(seg)
        else:
            travel.append(seg)
        x, y, z = new_x, new_y, new_z
    return ext, travel, layer


def plot(ext, travel, up_to_layer, out_path: Path, total_layers: int,
         width=1200, height=900, elev=28, azim=-55):
    fig = plt.figure(figsize=(width / 100, height / 100), dpi=100, facecolor="#0d1117")
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("#0d1117")

    # Extrusions colored by layer index (viridis)
    cmap = cm.get_cmap("viridis")
    for (p0, p1, layer) in ext:
        t = layer / max(total_layers, 1)
        ax.plot(
            [p0[0], p1[0]], [p0[1], p1[1]], [p0[2], p1[2]],
            color=cmap(t), linewidth=0.55, alpha=0.85,
        )
    # Travels as faint gray
    for (p0, p1, _) in travel:
        ax.plot(
            [p0[0], p1[0]], [p0[1], p1[1]], [p0[2], p1[2]],
            color="#404654", linewidth=0.3, alpha=0.35,
        )

    # Belt bed reference: triangle in X-Y at Z=0
    all_x = [p[0] for seg in ext for p in seg[:2]]
    all_y = [p[1] for seg in ext for p in seg[:2]]
    if all_x and all_y:
        xmin, xmax = min(all_x) - 10, max(all_x) + 10
        ymax = max(all_y) + 10
        # draw a simple rectangle outline on the belt plane Z=0
        bx = [xmin, xmax, xmax, xmin, xmin]
        by = [0, 0, ymax, ymax, 0]
        bz = [0, 0, 0, 0, 0]
        ax.plot(bx, by, bz, color="#7d8590", linewidth=0.8, alpha=0.6)

    ax.set_xlabel("X (mm)", color="#c9d1d9")
    ax.set_ylabel("Y (mm, belt)", color="#c9d1d9")
    ax.set_zlabel("Z (mm, height)", color="#c9d1d9")
    pct = int(round(100 * up_to_layer / max(total_layers, 1)))
    ax.set_title(
        f"Belt slice preview — layers 1–{up_to_layer} / {total_layers} "
        f"({pct}%, {len(ext)} extrusions)",
        color="#c9d1d9", pad=12, fontsize=12,
    )
    ax.view_init(elev=elev, azim=azim)
    # Aspect
    try:
        ax.set_box_aspect((1, 1.2, 0.8))
    except Exception:
        pass
    # Dark tick labels
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor("#161b22")
        axis.pane.set_edgecolor("#30363d")
        for t in axis.get_ticklabels():
            t.set_color("#c9d1d9")
    plt.tight_layout()
    plt.savefig(out_path, dpi=100, facecolor="#0d1117", bbox_inches="tight")
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gcode", type=Path)
    ap.add_argument("--up-to-layer", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--elev", type=float, default=28)
    ap.add_argument("--azim", type=float, default=-55)
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()

    # Count total layers for progress title
    total = 0
    for line in args.gcode.read_text().splitlines():
        if ";LAYER_CHANGE" in line:
            total += 1

    ext, travel, reached = parse(args.gcode, args.up_to_layer)
    plot(ext, travel, reached, args.out, total,
         width=args.width, height=args.height, elev=args.elev, azim=args.azim)
    print(f"rendered: up to layer {reached}/{total}, {len(ext)} extrusions, {len(travel)} travels → {args.out}")


if __name__ == "__main__":
    main()
