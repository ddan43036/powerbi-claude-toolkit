#!/usr/bin/env python3
"""
report_anatomy.py — Reverse-engineer a real PBIP report into a COMPACT anatomy + skeletons.

Handles BOTH report formats (read-only):
  - legacy: a single `*.Report/report.json` with report["sections"][].visualContainers[].config
            (config is JSON serialized as an escaped string).
  - PBIR:   `*.Report/definition/` folder-per-visual: pages/pages.json, pages/<id>/page.json,
            pages/<id>/visuals/<id>/visual.json (real JSON; `visual` or `visualGroup`).

Why this exists: teach the agents/skills how a professional dashboard is actually built (visual
types, positions, groups, theme, measure-bound titles) WITHOUT loading huge files into context.
Python parses; the model only reads compact `anatomy.json` + `skeletons/*.json`.

Usage:
    python report_anatomy.py --report <...\\X.Report\\report.json>   # legacy
    python report_anatomy.py --report "<...\\X.Report>"              # PBIR folder (or its definition)
    [-o anatomy.json] [--skeletons <dir>]
"""
import argparse
import json
import os
import sys

NATIVE = {
    "clusteredColumnChart", "clusteredBarChart", "stackedColumnChart", "stackedBarChart",
    "hundredPercentStackedColumnChart", "hundredPercentStackedBarChart", "barChart", "columnChart",
    "lineChart", "areaChart", "stackedAreaChart", "lineClusteredColumnComboChart",
    "lineStackedColumnComboChart", "scatterChart", "waterfallChart", "ribbonChart",
    "pieChart", "donutChart", "treemap", "funnel", "card", "cardVisual", "multiRowCard", "kpi",
    "gauge", "tableEx", "pivotTable", "map", "filledMap",
}
CHROME_ONLY = {"shape", "image", "textbox", "actionButton"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_str(s):
    try:
        return json.loads(s) if isinstance(s, str) else (s or {})
    except Exception:
        return {}


def title_record(objs):
    """objs = the dict that may hold a 'title' list (vcObjects or visualContainerObjects)."""
    t = (objs or {}).get("title")
    if not t:
        return None
    expr = ((t[0].get("properties", {}) or {}).get("text", {}) or {}).get("expr", {})
    if "Measure" in expr:
        return {"kind": "measure", "value": expr["Measure"].get("Property")}
    if "Literal" in expr:
        return {"kind": "literal", "value": str(expr["Literal"].get("Value", "")).strip("'")}
    return {"kind": "other"} if expr else None


def classify(is_group, vtype, area_ratio):
    if is_group:
        return "group"
    if vtype.startswith("htmlContent"):
        return "html-fullpage" if area_ratio >= 0.5 else "html-card"
    if vtype in CHROME_ONLY or vtype == "slicer":
        return vtype
    if vtype in NATIVE:
        return "native-chart"
    return "native-other"


# ---- legacy adapter -------------------------------------------------------------------------
def record_legacy(vc, pw, ph):
    cfg = parse_str(vc.get("config"))
    name = cfg.get("name")
    pos = ((cfg.get("layouts") or [{}])[0]).get("position", {}) or {}
    x, y = pos.get("x", vc.get("x", 0)), pos.get("y", vc.get("y", 0))
    w, h = pos.get("width", vc.get("width", 0)), pos.get("height", vc.get("height", 0))
    if "singleVisualGroup" in cfg:
        return {"id": name, "class": "group", "name": cfg["singleVisualGroup"].get("displayName"),
                "x": round(x), "y": round(y), "w": round(w), "h": round(h),
                "group": cfg.get("parentGroupName")}, cfg
    sv = cfg.get("singleVisual", {}) or {}
    vtype = sv.get("visualType", "?")
    ratio = (w * h) / (pw * ph) if pw and ph else 0
    rec = {"id": name, "class": classify(False, vtype, ratio), "vtype": vtype,
           "x": round(x), "y": round(y), "w": round(w), "h": round(h), "z": round(pos.get("z", 0)),
           "group": cfg.get("parentGroupName")}
    proj = sv.get("projections") or {}
    b = {r: [p.get("queryRef") for p in lst if isinstance(p, dict)] for r, lst in proj.items()}
    if any(b.values()):
        rec["binding"] = {r: v for r, v in b.items() if v}
    t = title_record(sv.get("vcObjects"))
    if t:
        rec["title"] = t
    if sv.get("syncGroup"):
        rec["syncGroup"] = sv["syncGroup"].get("groupName")
    if "ThemeDataColor" in json.dumps(sv.get("objects", {})):
        rec["themeColor"] = True
    return rec, cfg


# ---- PBIR adapter ---------------------------------------------------------------------------
def record_pbir(vj, pw, ph):
    name = vj.get("name")
    pos = vj.get("position", {}) or {}
    x, y = pos.get("x", 0), pos.get("y", 0)
    w, h = pos.get("width", 0), pos.get("height", 0)
    if "visualGroup" in vj:
        return {"id": name, "class": "group", "name": vj["visualGroup"].get("displayName"),
                "x": round(x), "y": round(y), "w": round(w), "h": round(h),
                "group": vj.get("parentGroupName")}, vj
    vis = vj.get("visual", {}) or {}
    vtype = vis.get("visualType", "?")
    ratio = (w * h) / (pw * ph) if pw and ph else 0
    rec = {"id": name, "class": classify(False, vtype, ratio), "vtype": vtype,
           "x": round(x), "y": round(y), "w": round(w), "h": round(h), "z": round(pos.get("z", 0)),
           "group": vj.get("parentGroupName")}
    b = {}
    for role, st in ((vis.get("query") or {}).get("queryState") or {}).items():
        refs = [p.get("queryRef") for p in (st.get("projections") or []) if isinstance(p, dict)]
        if any(refs):
            b[role] = [r for r in refs if r]
    if b:
        rec["binding"] = b
    t = title_record(vis.get("visualContainerObjects"))
    if t:
        rec["title"] = t
    if "ThemeDataColor" in json.dumps(vis.get("objects", {})):
        rec["themeColor"] = True
    return rec, vj


def page_size(w, h, visuals):
    if not w:
        w = max((v["x"] + v["w"] for v in visuals), default=1280)
    if not h:
        h = max((v["y"] + v["h"] for v in visuals), default=720)
    return round(w), round(h)


def finalize_page(name, w, h, recs_cfgs, skeletons):
    visuals = [r for r, _c in recs_cfgs]
    pw, ph = page_size(w, h, visuals)
    for rec, cfg in recs_cfgs:
        if rec["class"] in ("html-card", "html-fullpage"):
            ratio = (rec["w"] * rec["h"]) / (pw * ph) if pw and ph else 0
            rec["class"] = "html-fullpage" if ratio >= 0.5 else "html-card"
        skeletons.setdefault(rec["class"], cfg)
    counts = {}
    for v in visuals:
        counts[v["class"]] = counts.get(v["class"], 0) + 1
    groups = [{"id": g["id"], "name": g.get("name"), "group": g.get("group")}
              for g in visuals if g["class"] == "group"]
    return {"name": name, "w": pw, "h": ph, "counts": counts,
            "groups": groups, "visuals": [v for v in visuals if v["class"] != "group"]}


def practices(pages):
    total = sum(sum(p["counts"].values()) for p in pages)
    allv = [v for p in pages for v in p["visuals"]]
    groups = sum(p["counts"].get("group", 0) for p in pages)
    tm = sum(1 for v in allv if v.get("title", {}).get("kind") == "measure")
    tc = sum(1 for v in allv if v.get("themeColor"))
    nd = max(1, len(allv))
    types = {}
    for p in pages:
        for k, n in p["counts"].items():
            types[k] = types.get(k, 0) + n
    return {"visuals": total, "groups": groups,
            "pct_title_measure": round(100 * tm / nd), "pct_theme_color": round(100 * tc / nd),
            "types": types}


def anatomy_legacy(report):
    rcfg = parse_str(report.get("config"))
    theme = (((rcfg.get("themeCollection") or {}).get("baseTheme")) or {}).get("name")
    resources = [it.get("path") for rp in report.get("resourcePackages", [])
                 for it in rp.get("resourcePackage", {}).get("items", [])]
    skeletons, pages = {}, []
    for sec in report.get("sections", []):
        rc = [record_legacy(vc, sec.get("width") or 1, sec.get("height") or 1)
              for vc in sec.get("visualContainers", [])]
        pages.append(finalize_page(sec.get("displayName"), sec.get("width"), sec.get("height"),
                                   rc, skeletons))
    rep = {"format": "legacy", "version": rcfg.get("version"), "theme": theme,
           "customVisuals": report.get("publicCustomVisuals", []), "resources": resources}
    return rep, pages, skeletons


def anatomy_pbir(defdir):
    pagesdir = os.path.join(defdir, "pages")
    meta = load(os.path.join(pagesdir, "pages.json"))
    order = meta.get("pageOrder", [])
    skeletons, pages = {}, []
    for pid in order:
        pj = os.path.join(pagesdir, pid, "page.json")
        if not os.path.isfile(pj):
            continue
        pg = load(pj)
        vdir = os.path.join(pagesdir, pid, "visuals")
        rc = []
        if os.path.isdir(vdir):
            for vid in sorted(os.listdir(vdir)):
                vp = os.path.join(vdir, vid, "visual.json")
                if os.path.isfile(vp):
                    rc.append(record_pbir(load(vp), pg.get("width") or 1, pg.get("height") or 1))
        pages.append(finalize_page(pg.get("displayName"), pg.get("width"), pg.get("height"),
                                   rc, skeletons))
    rep = {"format": "pbir", "version": None, "theme": None, "customVisuals": [], "resources": []}
    rjson = os.path.join(defdir, "report.json")
    if os.path.isfile(rjson):
        rc = load(rjson)
        if isinstance(rc, dict):
            rep["theme"] = (((rc.get("themeCollection") or {}).get("baseTheme")) or {}).get("name")
            rep["customVisuals"] = rc.get("publicCustomVisuals", []) or []
    return rep, pages, skeletons


def resolve_input(path):
    if os.path.isfile(path):
        try:
            j = load(path)
        except Exception:
            j = None
        if isinstance(j, dict) and "sections" in j:
            return "legacy", j, None
        d = os.path.dirname(path)
        if os.path.isfile(os.path.join(d, "pages", "pages.json")):
            return "pbir", None, d
        return "legacy", (j or {}), None
    for cand in (os.path.join(path, "definition"), path):
        if os.path.isfile(os.path.join(cand, "pages", "pages.json")):
            return "pbir", None, cand
    if os.path.isfile(os.path.join(path, "report.json")):
        return "legacy", load(os.path.join(path, "report.json")), None
    return None, None, None


def main():
    ap = argparse.ArgumentParser(description="Anatomy + skeletons from a PBIP report (legacy or PBIR).")
    ap.add_argument("--report", required=True, help="report.json (legacy) or *.Report/definition (PBIR)")
    ap.add_argument("-o", "--out")
    ap.add_argument("--skeletons", help="Directory to write one representative config per class.")
    ap.add_argument("--find", help="LOCALIZAR: imprime solo los visuales cuyo id/título/tipo coincida.")
    args = ap.parse_args()

    fmt, report, defdir = resolve_input(args.report)
    if fmt is None:
        print(f"ERROR: no encuentro un report (legacy o PBIR) en: {args.report}", file=sys.stderr)
        sys.exit(2)
    rep, pages, skeletons = anatomy_legacy(report) if fmt == "legacy" else anatomy_pbir(defdir)
    rep["practices"] = practices(pages)
    anatomy = {"report": rep, "pages": pages}

    # --find: localizar visual(es) sin volcar toda la anatomía (token-light para MODIFICAR).
    if args.find:
        q = args.find.lower()
        hits = []
        for p in pages:
            for v in p["visuals"]:
                title = (v.get("title", {}) or {}).get("value") or ""
                if (q in (v.get("id") or "").lower() or q in (v.get("vtype") or "").lower()
                        or q in str(title).lower() or q in (v.get("class") or "").lower()):
                    hits.append({"page": p["name"], **v})
        print(json.dumps(hits, indent=2, ensure_ascii=False))
        print(f"(--find '{args.find}': {len(hits)} coincidencia(s))", file=sys.stderr)
        return

    text = json.dumps(anatomy, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        pr = rep["practices"]
        names = ", ".join(f"{p['name'].strip() if p['name'] else '?'}({sum(p['counts'].values())}v)"
                          for p in pages)
        print(f"Wrote {args.out}: format={rep['format']}; {len(pages)} pages [{names}]; "
              f"{pr['visuals']} visuals, {pr['groups']} groups; "
              f"title-measure {pr['pct_title_measure']}%, themeColor {pr['pct_theme_color']}%",
              file=sys.stderr)
    else:
        print(text)

    if args.skeletons:
        os.makedirs(args.skeletons, exist_ok=True)
        for klass, cfg in skeletons.items():
            c = dict(cfg)
            c["name"] = ""
            with open(os.path.join(args.skeletons, f"{klass}.json"), "w", encoding="utf-8") as f:
                json.dump(c, f, indent=2, ensure_ascii=False)
        print(f"Wrote {len(skeletons)} skeletons to {args.skeletons}", file=sys.stderr)


if __name__ == "__main__":
    main()
