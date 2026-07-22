#!/usr/bin/env python3
"""
layout_map.py — Print an ASCII map of a report page layout (token-light).

Why this exists: the designer needs to "see" where visuals sit on a page to place new ones on
the grid without collisions, but report.json is huge and must never be loaded into the model's
context. This script does the reading in Python and emits only a compact ASCII map + a legend.

It can map the EXISTING layout (--report), a PROPOSED layout (--plan), or BOTH overlaid so the
designer can spot overlaps between what's there and what's being added.

Markers: existing visuals = lowercase letters (a, b, c...); proposed (plan) visuals = digits/
uppercase (1..9, A..Z). A cell shared by two visuals shows '#' (collision).

Usage:
    python layout_map.py --report <report.json> [--plan plan.json] [--page "Name"]
    python layout_map.py --plan plan.json --width 1280 --height 720
    python layout_map.py --areas intent.yaml      # resolve layout.areas (grid-template-areas)
    [--cols 12] [--cw 72] [--ch 24] [--intent intent.yaml]

--areas resolves the CSS-grid-like `layout.areas` in intent.yaml into pixel rects (area -> x/y/w/h)
on the 12-col grid and draws them, so anyone can arrange the layout in intent.yaml and see it.

Exit code 0 always (informational); collisions/out-of-bounds are reported, not fatal.
"""
import argparse
import json
import os
import re
import sys

EXIST_MARKERS = "abcdefghijklmnopqrstuvwxyz"
PLAN_MARKERS = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def literal_text(prop):
    try:
        v = prop["expr"]["Literal"]["Value"]
        if isinstance(v, str) and v.startswith("'") and v.endswith("'"):
            return v[1:-1].replace("''", "'")
        return v
    except Exception:
        return None


def parse_intent_defaults(path):
    """Best-effort, dependency-free extraction of canvas size + grid columns from intent.yaml."""
    out = {}
    try:
        text = open(path, encoding="utf-8").read()
    except Exception:
        return out
    mw = re.search(r"width:\s*(\d+)", text)
    mh = re.search(r"height:\s*(\d+)", text)
    mc = re.search(r"columns:\s*(\d+)", text)
    if mw:
        out["width"] = int(mw.group(1))
    if mh:
        out["height"] = int(mh.group(1))
    if mc:
        out["cols"] = int(mc.group(1))
    return out


def parse_layout(path):
    """Best-effort parse of intent.yaml `layout` (grid + areas) without PyYAML.
    Returns (grid dict, areas: list[list[token]], canvas_w, canvas_h)."""
    text = open(path, encoding="utf-8").read()
    lines = text.split("\n")
    grid = {"columns": 12, "margin": 24, "gutter": 12}
    mg = re.search(r"grid:\s*\{([^}]*)\}", text)
    if mg:
        for k in ("columns", "rows", "margin", "gutter"):
            m = re.search(rf"{k}\s*:\s*(\d+)", mg.group(1))
            if m:
                grid[k] = int(m.group(1))
    # areas: collect the list items under an `areas:` key
    areas = []
    in_areas = False
    areas_indent = None
    for ln in lines:
        if re.match(r"^\s*areas:\s*$", ln):
            in_areas = True
            areas_indent = len(ln) - len(ln.lstrip())
            continue
        if in_areas:
            m = re.match(r"^(\s*)-\s*(.+?)\s*$", ln)
            if m and (areas_indent is None or len(m.group(1)) > areas_indent):
                row = m.group(2).strip().strip('"').strip("'")
                areas.append(row.split())
            elif ln.strip() == "" or ln.lstrip().startswith("#"):
                continue
            else:
                break
    cw = int(re.search(r"width:\s*(\d+)", text).group(1)) if re.search(r"width:\s*(\d+)", text) else 1280
    ch = int(re.search(r"height:\s*(\d+)", text).group(1)) if re.search(r"height:\s*(\d+)", text) else 720
    return grid, areas, cw, ch


def areas_to_visuals(grid, areas, cw, ch):
    """Resolve grid-template-areas to pixel rects. Returns (visuals, warnings)."""
    warnings = []
    cols = grid.get("columns", 12)
    rows = len(areas)
    margin = grid.get("margin", 24)
    gutter = grid.get("gutter", 12)
    if rows == 0:
        return [], ["layout.areas vacío o no encontrado."]
    for i, r in enumerate(areas):
        if len(r) != cols:
            warnings.append(f"fila {i+1} tiene {len(r)} tokens (se esperaban {cols} columnas).")
    col_w = (cw - 2 * margin - (cols - 1) * gutter) / cols
    row_h = (ch - 2 * margin - (rows - 1) * gutter) / rows
    spans = {}  # token -> [minc, minr, maxc, maxr]
    for r, rowtokens in enumerate(areas):
        for c, tok in enumerate(rowtokens):
            if tok == ".":
                continue
            s = spans.setdefault(tok, [c, r, c, r])
            s[0], s[1] = min(s[0], c), min(s[1], r)
            s[2], s[3] = max(s[2], c), max(s[3], r)
    visuals = []
    for tok, (minc, minr, maxc, maxr) in spans.items():
        x = round(margin + minc * (col_w + gutter))
        y = round(margin + minr * (row_h + gutter))
        w = round((maxc - minc + 1) * col_w + (maxc - minc) * gutter)
        h = round((maxr - minr + 1) * row_h + (maxr - minr) * gutter)
        visuals.append({"source": "area", "vtype": tok, "title": "", "x": x, "y": y, "w": w, "h": h})
    visuals.sort(key=lambda v: (v["y"], v["x"]))
    return visuals, warnings


def visuals_from_report(report):
    """page -> {w, h, visuals:[{source,vtype,title,x,y,w,h}]}."""
    pages = {}
    for sec in report.get("sections", []):
        page = sec.get("displayName", "?")
        entry = pages.setdefault(page, {"w": sec.get("width"), "h": sec.get("height"),
                                        "visuals": []})
        for vc in sec.get("visualContainers", []):
            raw = vc.get("config")
            if not isinstance(raw, str):
                continue
            try:
                cfg = json.loads(raw)
            except Exception:
                continue
            sv = cfg.get("singleVisual") or {}
            vtype = sv.get("visualType") or ("group" if "singleVisualGroup" in cfg else "?")
            title = None
            tobj = (sv.get("vcObjects") or {}).get("title")
            if tobj:
                title = literal_text(tobj[0].get("properties", {}).get("text", {}))
            pos = (cfg.get("layouts") or [{}])[0].get("position", {})
            entry["visuals"].append({
                "source": "exist", "vtype": vtype, "title": title,
                "x": vc.get("x", pos.get("x", 0)), "y": vc.get("y", pos.get("y", 0)),
                "w": vc.get("width", pos.get("width", 0)),
                "h": vc.get("height", pos.get("height", 0)),
            })
    return pages


def merge_plan(pages, plan, default_w, default_h):
    for spec in plan.get("visuals", []):
        page = spec.get("page", "?")
        entry = pages.setdefault(page, {"w": default_w, "h": default_h, "visuals": []})
        pos = spec.get("position", {})
        entry["visuals"].append({
            "source": "plan", "vtype": spec.get("visualType", "?"), "title": spec.get("title"),
            "x": pos.get("x", 0), "y": pos.get("y", 0),
            "w": pos.get("width", 0), "h": pos.get("height", 0),
        })
    return pages


def to_cells(v, pw, ph, cw, ch):
    cx0 = max(0, min(cw - 1, int(round(v["x"] / pw * cw))))
    cy0 = max(0, min(ch - 1, int(round(v["y"] / ph * ch))))
    cx1 = max(cx0 + 1, min(cw, int(round((v["x"] + v["w"]) / pw * cw))))
    cy1 = max(cy0 + 1, min(ch, int(round((v["y"] + v["h"]) / ph * ch))))
    return cx0, cy0, cx1, cy1


def render_page(page, info, cols, cw, ch, default_w, default_h):
    pw = info.get("w") or default_w
    ph = info.get("h") or default_h
    grid = [[" "] * cw for _ in range(ch)]
    legend, collisions = [], False
    ei = pi = 0
    for v in info["visuals"]:
        if v["source"] == "plan":
            marker = PLAN_MARKERS[pi % len(PLAN_MARKERS)]
            pi += 1
        else:  # exist / area -> letters
            marker = EXIST_MARKERS[ei % len(EXIST_MARKERS)]
            ei += 1
        cx0, cy0, cx1, cy1 = to_cells(v, pw, ph, cw, ch)
        for yy in range(cy0, cy1):
            for xx in range(cx0, cx1):
                cur = grid[yy][xx]
                if cur == " ":
                    grid[yy][xx] = marker
                elif cur != marker:
                    grid[yy][xx] = "#"
                    collisions = True
        oob = (v["x"] + v["w"] > pw + 1) or (v["y"] + v["h"] > ph + 1)
        warn = " [OUT OF BOUNDS]" if oob else ""
        title = (v["title"] or "")[:28]
        legend.append(
            f"  [{marker}] {v['source']:5} {v['vtype']:<26} "
            f"x{v['x']} y{v['y']} {v['w']}x{v['h']}  \"{title}\"{warn}")

    # Column ruler (bootstrap-like): tick every column boundary.
    ruler = [" "] * cw
    for c in range(cols + 1):
        pos = min(cw - 1, int(round(c / cols * cw)))
        ruler[pos] = "|"
    out = []
    out.append(f"\nPágina: \"{page}\"  ({pw}x{ph}px, grid {cols} col, mapa {cw}x{ch})")
    out.append("   " + "".join(ruler))
    out.append("  +" + "-" * cw + "+")
    for row in grid:
        out.append("  |" + "".join(row) + "|")
    out.append("  +" + "-" * cw + "+")
    out.extend(legend)
    if collisions:
        out.append("  (!) '#' = celdas compartidas por 2+ visuales (colisión a revisar)")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="ASCII map of a report page layout.")
    ap.add_argument("--report")
    ap.add_argument("--plan")
    ap.add_argument("--page", help="Only this page (displayName).")
    ap.add_argument("--intent", help="intent.yaml to read canvas size / grid columns.")
    ap.add_argument("--areas", help="intent.yaml: resolve layout.areas to rects + map (no report).")
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    ap.add_argument("--cols", type=int)
    ap.add_argument("--cw", type=int, default=72, help="Map width in chars.")
    ap.add_argument("--ch", type=int, default=24, help="Map height in chars.")
    args = ap.parse_args()

    # --areas mode: resolve grid-template-areas from intent.yaml into pixel rects.
    if args.areas:
        grid, areas, cw_px, ch_px = parse_layout(args.areas)
        visuals, warns = areas_to_visuals(grid, areas, args.width or cw_px, args.height or ch_px)
        info = {"w": args.width or cw_px, "h": args.height or ch_px, "visuals": visuals}
        cols = args.cols or grid.get("columns", 12)
        print(render_page("layout.areas", info, cols, args.cw, args.ch,
                          info["w"], info["h"]))
        for w in warns:
            print(f"  (!) {w}")
        return

    if not args.report and not args.plan:
        print("ERROR: pass --report, --plan or --areas.", file=sys.stderr)
        sys.exit(2)

    if args.report and (os.path.isdir(args.report) or os.path.isfile(
            os.path.join(os.path.dirname(args.report), "pages", "pages.json"))):
        print("El informe está en carpeta-por-visual, no como report.json único. El mapa de layout "
              "trabaja sobre report.json; para analizar el informe en carpeta usa report_anatomy.py.",
              file=sys.stderr)
        sys.exit(2)

    defaults = parse_intent_defaults(args.intent) if args.intent else {}
    default_w = args.width or defaults.get("width", 1280)
    default_h = args.height or defaults.get("height", 720)
    cols = args.cols or defaults.get("cols", 12)

    pages = {}
    if args.report:
        pages = visuals_from_report(load(args.report))
    if args.plan:
        pages = merge_plan(pages, load(args.plan), default_w, default_h)

    names = [args.page] if args.page else list(pages.keys())
    for name in names:
        if name not in pages:
            print(f"(página no encontrada: {name})", file=sys.stderr)
            continue
        print(render_page(name, pages[name], cols, args.cw, args.ch, default_w, default_h))


if __name__ == "__main__":
    main()
