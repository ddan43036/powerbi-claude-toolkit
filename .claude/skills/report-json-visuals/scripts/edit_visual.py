#!/usr/bin/env python3
"""
edit_visual.py — Token-light targeted edits to NATIVE visuals in a legacy report.json.

For MODIFY-by-prompt: instead of loading the huge report.json into the model's context, this
script locates ONE visual by a selector and patches just the requested properties (title, colors,
position, page background, slicer colors, or a generic objects/vcObjects property). Python does the
read/parse/serialize; the model only sees a short summary. Always writes a .bak and re-validates
the JSON round-trip.

Find the target first with:  report_anatomy.py --find "<text|id|type>"

Usage:
    python edit_visual.py --report <report.json> (--id HEX | --title "text" | --type VT [--page "Name"])
        [--title "new"] [--title-measure "Tabla.Medida"]
        [--theme-color N] [--data-color "#RRGGBB"]
        [--slicer-fill "#RRGGBB"] [--slicer-font "#RRGGBB"]
        [--page-background "#RRGGBB"]
        [--x N --y N --width N --height N]
        [--set "objects.labels.show=true"] [--dry-run]

HTML panels are edited as measures (apply_measures.py), not here.
"""
import argparse
import json
import os
import re
import shutil
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def _bool(b):
    return _lit("true" if b else "false")


def _num(n):
    return _lit(f"{n}D")


def _str(s):
    return _lit("'" + str(s).replace("'", "''") + "'")


def _color(hexstr):
    return {"solid": {"color": _str(hexstr)}}


def _theme_color(cid):
    return {"solid": {"color": {"expr": {"ThemeDataColor": {"ColorId": int(cid), "Percent": 0}}}}}


def _measure_title(table, measure):
    return {"expr": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": measure}}}


def is_pbir_path(p):
    if os.path.isdir(p):
        return (os.path.isfile(os.path.join(p, "pages", "pages.json"))
                or os.path.isfile(os.path.join(p, "definition", "pages", "pages.json")))
    return os.path.isfile(os.path.join(os.path.dirname(p), "pages", "pages.json"))


def title_text(sv):
    t = (sv.get("vcObjects") or {}).get("title")
    if not t:
        return None
    v = ((t[0].get("properties", {}) or {}).get("text", {}) or {}).get("expr", {}).get("Literal", {}).get("Value")
    return v[1:-1].replace("''", "'") if isinstance(v, str) and v.startswith("'") else None


def find_visual(report, args):
    """Return (section, container, cfg, singleVisual) for the first match, or None."""
    for sec in report.get("sections", []):
        for vc in sec.get("visualContainers", []):
            raw = vc.get("config")
            if not isinstance(raw, str):
                continue
            try:
                cfg = json.loads(raw)
            except Exception:
                continue
            sv = cfg.get("singleVisual")
            if not sv:
                continue
            if args.id and cfg.get("name") == args.id:
                return sec, vc, cfg, sv
            if args.title:
                tt = title_text(sv)
                if tt and args.title.lower() in tt.lower():
                    return sec, vc, cfg, sv
            if args.type and sv.get("visualType") == args.type:
                if not args.page or sec.get("displayName") == args.page:
                    return sec, vc, cfg, sv
    return None


def set_objects_prop(sv, group, prop, expr_value, container="objects"):
    objs = sv.setdefault(container, {})
    lst = objs.setdefault(group, [{"properties": {}}])
    lst[0].setdefault("properties", {})[prop] = expr_value


def parse_set_value(val):
    if re.match(r"^#[0-9A-Fa-f]{6}$", val):
        return _color(val)
    if val.lower() in ("true", "false"):
        return _bool(val.lower() == "true")
    if re.match(r"^-?\d+(\.\d+)?$", val):
        return _num(val)
    return _str(val)


def main():
    ap = argparse.ArgumentParser(description="Targeted edits to a native visual in report.json")
    ap.add_argument("--report", required=True)
    ap.add_argument("--id"); ap.add_argument("--title-find", dest="title")
    ap.add_argument("--type"); ap.add_argument("--page")
    ap.add_argument("--set-title", dest="new_title")
    ap.add_argument("--title-measure")
    ap.add_argument("--theme-color", type=int)
    ap.add_argument("--data-color")
    ap.add_argument("--slicer-fill"); ap.add_argument("--slicer-font")
    ap.add_argument("--page-background")
    ap.add_argument("--x", type=float); ap.add_argument("--y", type=float)
    ap.add_argument("--width", type=float); ap.add_argument("--height", type=float)
    ap.add_argument("--set", action="append", default=[], help="objects.<group>.<prop>=<value>")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if is_pbir_path(args.report):
        print("El informe está en carpeta-por-visual; este editor trabaja sobre el report.json único.",
              file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(args.report):
        print(f"ERROR: no existe {args.report}", file=sys.stderr); sys.exit(2)
    if not (args.id or args.title or args.type):
        print("ERROR: da un selector: --id, --title-find o --type [--page]", file=sys.stderr); sys.exit(2)

    report = load(args.report)
    found = find_visual(report, args)
    if not found:
        print("ERROR: no se encontró el visual con ese selector.", file=sys.stderr); sys.exit(1)
    sec, vc, cfg, sv = found
    vid = cfg.get("name"); page = sec.get("displayName")
    vtype = sv.get("visualType")
    changes = []

    if args.new_title is not None or args.title_measure:
        vco = sv.setdefault("vcObjects", {})
        tprops = (vco.get("title") or [{"properties": {}}])[0].setdefault("properties", {})
        tprops["show"] = _bool(True)
        if args.title_measure:
            t, _, m = args.title_measure.partition(".")
            tprops["text"] = _measure_title(t, m); changes.append(f"title=medida {args.title_measure}")
        else:
            tprops["text"] = _str(args.new_title); changes.append(f"title='{args.new_title}'")
        vco["title"] = [{"properties": tprops}]

    if args.theme_color is not None:
        set_objects_prop(sv, "dataPoint", "fill", _theme_color(args.theme_color))
        changes.append(f"themeColor={args.theme_color}")
    if args.data_color:
        set_objects_prop(sv, "dataPoint", "defaultColor", _color(args.data_color))
        changes.append(f"dataColor={args.data_color}")
    if args.slicer_font:
        set_objects_prop(sv, "items", "fontColor", _color(args.slicer_font))
        changes.append(f"slicerFont={args.slicer_font}")
    if args.slicer_fill:
        set_objects_prop(sv, "background", "color", _color(args.slicer_fill), container="vcObjects")
        set_objects_prop(sv, "background", "show", _bool(True), container="vcObjects")
        changes.append(f"slicerFill={args.slicer_fill}")

    for s in args.set:
        if "=" not in s:
            continue
        path, _, val = s.partition("=")
        parts = path.split(".")
        if len(parts) == 3 and parts[0] in ("objects", "vcObjects"):
            set_objects_prop(sv, parts[1], parts[2], parse_set_value(val), container=parts[0])
            changes.append(f"{path}={val}")

    # Position (updates both config.layouts and the container's duplicated x/y/w/h)
    pos = (cfg.get("layouts") or [{}])[0].setdefault("position", {})
    for k, v in (("x", args.x), ("y", args.y), ("width", args.width), ("height", args.height)):
        if v is not None:
            pos[k] = v; vc[k] = v; changes.append(f"{k}={v}")

    # Page (canvas) background of the visual's section
    if args.page_background:
        raw = sec.get("config")
        try:
            scfg = json.loads(raw) if isinstance(raw, str) and raw else {}
        except Exception:
            scfg = {}
        scfg.setdefault("objects", {})["background"] = [{"properties": {
            "color": _color(args.page_background), "transparency": _lit("0D"), "show": _bool(True)}}]
        sec["config"] = json.dumps(scfg, ensure_ascii=False)
        changes.append(f"pageBackground={args.page_background}")

    if not changes:
        print("Nada que cambiar (no se pasaron operaciones).", file=sys.stderr); sys.exit(1)

    vc["config"] = json.dumps(cfg, ensure_ascii=False)
    print(f"Editado [{page}] {vtype} {vid}: " + ", ".join(changes))
    if args.dry_run:
        json.dumps(report, ensure_ascii=False)
        print("DRY RUN: no se escribió. Round-trip OK."); return
    backup = args.report + ".bak"
    shutil.copy2(args.report, backup)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(args.report, encoding="utf-8") as f:
        json.load(f)
    print(f"OK. Backup: {backup}. Valida con validate_report.py.")


if __name__ == "__main__":
    main()
