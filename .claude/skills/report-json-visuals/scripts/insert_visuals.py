#!/usr/bin/env python3
"""
insert_visuals.py — Insert NATIVE Power BI visuals into a legacy single-file report.json.

Why this exists: editing report.json by hand is token-expensive and error-prone (the
`config`/`filters` fields are JSON serialized as escaped strings). This engine lets Claude
Code mutate the report WITHOUT loading the whole blob into its context: it reads a small,
human-approved plan file + the model catalog, builds each visual container as a Python
dict, serializes it correctly, and appends it to the right page.

Approval gate: this script is the EXECUTION step. It must only run AFTER the user has
reviewed and approved the plan (see the report-designer agent). It always writes a .bak
backup first and re-validates the JSON round-trip.

Usage:
    python insert_visuals.py --report <path/to/report.json> \
                             --plan   <path/to/plan.json> \
                             --catalog <path/to/catalog.json> \
                             [--dry-run] [--minify]

Plan file format (JSON): {"visuals": [ <visual-spec>, ... ]}
Each <visual-spec>:
{
  "page": "Confirmaciones de Procesos",      // section displayName (required)
  "id": null,                                  // null => auto-generate 20-hex id
  "visualType": "clusteredBarChart",          // native visual id (required)
  "title": "Adherencia por Subgerencia",      // optional container title
  "position": {"x":24,"y":120,"width":480,"height":300,"z":6000,"tabOrder":0},
  "parentGroupName": null,                     // optional: id of an existing group
  "bindings": {                                // role -> list of field refs
     "Category": [{"table":"DimOrg","field":"Subgerencia","kind":"column","active":true}],
     "Y":        [{"table":"Medidas","field":"adherencia_prom","kind":"measure"}]
  },
  "sort": {"table":"Medidas","field":"adherencia_prom","kind":"measure","direction":"desc"},
  "formatting": {"dataColors":["#1B5E20"],"fontFamily":"Segoe UI","fontSize":10,"dataLabels":true}
}

field "kind": "column" | "measure" | "aggregation" (+ "function" for aggregation).
Prefer "measure" — it avoids the aggregation-function enum and reuses model logic.

Theming (optional): a plan-level "theme" object and/or a per-visual "formatting" object apply
colors/fonts/labels to NATIVE visuals via singleVisual.objects + vcObjects. Supported keys:
  dataColors:[hex...], fontFamily, fontSize, dataLabels:bool, background:hex,
  title:{fontColor:hex, fontSize:n}.
Per-visual "formatting" overrides the plan-level "theme". Formatting is additive and gated by
visual type (axis fonts only on cartesian charts); unsupported combos are skipped, not forced.
For multi-series palettes or properties not covered here, set a PBIP theme file or calque an
existing themed visual (REGLA 3).

Native coloring (defaults if the user doesn't specify; user's theme wins where set):
  - theme.background -> PAGE/canvas background (written to section.config objects.background).
  - theme.slicer {fill,font} -> slicer box fill + item font color.
  - theme.dataColors / formatting.themeColorId -> chart colors.
  DEFAULT_THEME provides a sane palette + white canvas + light slicer when theme is omitted.
  Opt out of page background with plan["page_background"] = false.

Pro building blocks (from a real CdP report):
- HTML Content custom visual: a visual-spec with visualType = the custom GUID (e.g.
  "htmlContent443BE3...") and bindings {"content":[{table:"Medidas",field:"M_HTML_X","kind":"measure"}]}.
  The script auto-registers the GUID in report.publicCustomVisuals.
- Groups: a spec {"group":true,"id":"grp1","displayName":"...","position":{...}}; children set
  "parentGroupName":"grp1" (nesting supported).
- Theme colors (optional): formatting.themeColorId:<int> -> dataPoint.fill ThemeDataColor (instead
  of literal hex via dataColors).
- Dynamic titles: spec "title_measure":"Medidas.<measure>" -> title text is a measure (i18n).
- Slicers: formatting.slicerMode "Dropdown"|"List"|"Between"; spec "syncGroup":"<name>".
"""
import argparse
import json
import os
import re
import secrets
import shutil
import sys

# Verified QueryAggregateFunction enum (matches the published semanticQuery schema).
AGG_FUNC = {
    "sum": 0, "average": 1, "avg": 1, "distinctcount": 2, "dcount": 2,
    "min": 3, "max": 4, "count": 5, "median": 6, "stddev": 7, "variance": 8,
}
AGG_NAME = {0: "Sum", 1: "Avg", 2: "DistinctCount", 3: "Min", 4: "Max",
            5: "Count", 6: "Median", 7: "StdDev", 8: "Variance"}

# Visual families that accept the formatting properties we know are safe.
CARTESIAN = {
    "clusteredColumnChart", "clusteredBarChart", "stackedColumnChart", "stackedBarChart",
    "hundredPercentStackedColumnChart", "hundredPercentStackedBarChart", "barChart",
    "columnChart", "lineChart", "areaChart", "stackedAreaChart",
    "lineClusteredColumnComboChart", "lineStackedColumnComboChart", "scatterChart",
    "waterfallChart", "ribbonChart",
}
PIE_LIKE = {"pieChart", "donutChart", "treemap", "funnel"}

# Defaults de coloreado para tableros NATIVOS. Se aplican si el usuario NO especifica en el tema;
# cualquier clave que el usuario ponga en plan["theme"] gana sobre estos.
DEFAULT_THEME = {
    "fontFamily": "Segoe UI",
    "dataLabels": True,
    "dataColors": ["#2E5AAC", "#27AE60", "#E67E22", "#C0392B", "#7F8C8D", "#8E44AD"],
    "background": "#FFFFFF",                       # fondo del lienzo (página)
    "slicer": {"fill": "#F2F4F7", "font": "#1B2631"},
}


def merge_theme(theme):
    """DEFAULT_THEME <- theme (deep-merge del subdict 'slicer'). theme=None usa solo defaults."""
    theme = theme or {}
    eff = {**DEFAULT_THEME, **theme}
    eff["slicer"] = {**DEFAULT_THEME["slicer"], **(theme.get("slicer") or {})}
    return eff


class PlanError(Exception):
    pass


# --- formatting helpers (build the verified subset of objects/vcObjects) -----------------
def _lit(value):
    return {"expr": {"Literal": {"Value": value}}}


def _str_lit(s):
    return _lit("'" + str(s).replace("'", "''") + "'")


def _bool_lit(b):
    return _lit("true" if b else "false")


def _num_lit(n):  # Power BI font sizes use the D (double) suffix in literals
    return _lit(f"{n}D")


def _color(hexstr):
    return {"solid": {"color": _str_lit(hexstr)}}


def _theme_color(color_id, percent=0):
    return {"solid": {"color": {"expr": {"ThemeDataColor": {"ColorId": color_id, "Percent": percent}}}}}


def _measure_title_expr(table, measure):
    # Dynamic (multilingual) title: the title text is a measure, like the real pro report.
    return {"expr": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": measure}}}


def is_custom_visual(vtype):
    # Custom visuals carry a long hex GUID suffix (e.g. htmlContent443BE3AD55E0...).
    return bool(re.search(r"[A-Fa-f0-9]{20,}", vtype or ""))


def is_pbir_path(p):
    """True if the path points at a PBIR (folder-per-visual) report."""
    if os.path.isdir(p):
        return (os.path.isfile(os.path.join(p, "pages", "pages.json"))
                or os.path.isfile(os.path.join(p, "definition", "pages", "pages.json")))
    return os.path.isfile(os.path.join(os.path.dirname(p), "pages", "pages.json"))


PBIR_MSG = ("El informe del proyecto está en carpeta-por-visual, no como report.json único. "
            "Este toolkit edita el report.json; para analizar el informe en carpeta usa "
            "report_anatomy.py. (Guarda el informe como report.json para insertar aquí.)")


def build_formatting(vtype, fmt):
    """Return (objects, vc_props) for a verified subset of formatting. Gated by visual type.

    objects -> singleVisual.objects (dataPoint, labels, categoryAxis, valueAxis)
    vc_props -> extra vcObjects (background) + a 'title' dict merged into the title properties.
    """
    objects, vc_props = {}, {}
    if not fmt:
        return objects, vc_props

    tcid = fmt.get("themeColorId")   # paleta del tema (opcional) gana sobre hex
    colors = fmt.get("dataColors")
    if tcid is not None and (vtype in CARTESIAN or vtype in PIE_LIKE):
        objects["dataPoint"] = [{"properties": {"fill": _theme_color(tcid)}}]
    elif colors and (vtype in CARTESIAN or vtype in PIE_LIKE):
        objects["dataPoint"] = [{"properties": {"defaultColor": _color(colors[0])}}]

    if "dataLabels" in fmt and (vtype in CARTESIAN or vtype in PIE_LIKE):
        objects.setdefault("labels", [{"properties": {}}])
        objects["labels"][0]["properties"]["show"] = _bool_lit(bool(fmt["dataLabels"]))

    font, size = fmt.get("fontFamily"), fmt.get("fontSize")
    if (font or size) and vtype in CARTESIAN:
        axis = {}
        if font:
            axis["fontFamily"] = _str_lit(font)
        if size:
            axis["fontSize"] = _num_lit(size)
        objects["categoryAxis"] = [{"properties": dict(axis)}]
        objects["valueAxis"] = [{"properties": dict(axis)}]
        lbl = objects.setdefault("labels", [{"properties": {}}])[0]["properties"]
        if font:
            lbl["fontFamily"] = _str_lit(font)
        if size:
            lbl["fontSize"] = _num_lit(size)

    bg = fmt.get("background")
    if bg:
        vc_props["background"] = [{"properties": {"show": _bool_lit(True), "color": _color(bg)}}]

    # Container chrome (profesional, como el tablero real). Aplica a cualquier tipo.
    border = fmt.get("border")
    if border:
        bprops = {"show": _bool_lit(True)}
        if isinstance(border, str):
            bprops["color"] = _color(border)
        vc_props["border"] = [{"properties": bprops}]
    if "visualHeader" in fmt:
        vc_props["visualHeader"] = [{"properties": {"show": _bool_lit(bool(fmt["visualHeader"]))}}]
    if fmt.get("dropShadow"):
        vc_props["dropShadow"] = [{"properties": {"show": _bool_lit(True)}}]

    # Slicer: color de ítems (texto) + fondo del slicer (de theme.slicer o defaults).
    if vtype == "slicer":
        sl = fmt.get("slicer") or {}
        if sl.get("font"):
            objects.setdefault("items", [{"properties": {}}])
            objects["items"][0]["properties"]["fontColor"] = _color(sl["font"])
        if sl.get("fill") and "background" not in vc_props:
            vc_props["background"] = [{"properties": {"show": _bool_lit(True), "color": _color(sl["fill"])}}]

    title = fmt.get("title")
    if isinstance(title, dict):
        tprops = {}
        if title.get("fontColor"):
            tprops["fontColor"] = _color(title["fontColor"])
        if title.get("fontSize"):
            tprops["fontSize"] = _num_lit(title["fontSize"])
        if tprops:
            vc_props["title"] = tprops
    return objects, vc_props


def new_id() -> str:
    return secrets.token_hex(10)  # 20 hex chars, like Power BI's native ids


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_field(ref, catalog, where):
    table = ref.get("table")
    field = ref.get("field")
    kind = ref.get("kind", "column")
    if not table or not field:
        raise PlanError(f"{where}: each binding needs 'table' and 'field'. Got {ref}")
    tables = catalog.get("tables", {})
    if table not in tables:
        raise PlanError(f"{where}: table '{table}' not found in model catalog.")
    if kind == "measure":
        if field not in tables[table].get("measures", []):
            raise PlanError(f"{where}: measure '{table}.{field}' not found in catalog.")
    else:  # column or aggregation (over a column)
        if field not in tables[table].get("columns", []):
            raise PlanError(f"{where}: column '{table}.{field}' not found in catalog.")
    if kind == "aggregation":
        fn = ref.get("function")
        if isinstance(fn, str):
            if fn.lower() not in AGG_FUNC:
                raise PlanError(f"{where}: unknown aggregation function '{fn}'.")
        elif not isinstance(fn, int):
            raise PlanError(f"{where}: aggregation needs 'function' (name or int).")


def query_ref_for(ref):
    table, field, kind = ref["table"], ref["field"], ref.get("kind", "column")
    if kind == "aggregation":
        fn = ref.get("function")
        fn_int = AGG_FUNC[fn.lower()] if isinstance(fn, str) else int(fn)
        return f"{AGG_NAME.get(fn_int, 'Agg')}({table}.{field})", fn_int
    return f"{table}.{field}", None


def select_entry(ref, alias):
    """Build a prototypeQuery.Select entry for one field ref."""
    table, field, kind = ref["table"], ref["field"], ref.get("kind", "column")
    qref, fn_int = query_ref_for(ref)
    native = ref.get("displayName", field)
    src = {"SourceRef": {"Source": alias}}
    if kind == "measure":
        expr = {"Measure": {"Expression": src, "Property": field}}
    elif kind == "aggregation":
        expr = {"Aggregation": {
            "Expression": {"Column": {"Expression": src, "Property": field}},
            "Function": fn_int}}
    else:
        expr = {"Column": {"Expression": src, "Property": field}}
    entry = dict(expr)
    entry["Name"] = qref
    entry["NativeReferenceName"] = native
    return entry, qref


def set_page_background(section, hexcolor):
    """Colorea el fondo del LIENZO (página) escribiendo objects.background en section.config."""
    raw = section.get("config")
    try:
        cfg = json.loads(raw) if isinstance(raw, str) and raw else {}
    except Exception:
        cfg = {}
    objs = cfg.setdefault("objects", {})
    objs["background"] = [{"properties": {
        "color": _color(hexcolor),
        "transparency": _lit("0D"),
        "show": _bool_lit(True),
    }}]
    section["config"] = json.dumps(cfg, ensure_ascii=False)


def build_group_container(spec):
    """Build a visual GROUP container (singleVisualGroup) for nested layouts."""
    page = spec.get("page")
    if not page:
        raise PlanError(f"group spec needs 'page': {spec}")
    pos = spec.get("position", {})
    position = {
        "x": pos.get("x", 0), "y": pos.get("y", 0), "z": pos.get("z", 1000),
        "width": pos.get("width", 400), "height": pos.get("height", 300),
        "tabOrder": pos.get("tabOrder", 0),
    }
    vid = spec.get("id") or new_id()
    config = {"name": vid, "layouts": [{"id": 0, "position": position}],
              "singleVisualGroup": {"displayName": spec.get("displayName", "Grupo"), "groupMode": 0}}
    if spec.get("parentGroupName"):
        config["parentGroupName"] = spec["parentGroupName"]
    container = {  # groups carry no "filters" key
        "config": json.dumps(config, ensure_ascii=False),
        "height": position["height"], "width": position["width"],
        "x": position["x"], "y": position["y"], "z": position["z"],
    }
    return page, vid, container


def build_visual_container(spec, catalog, theme=None):
    page = spec.get("page")
    vtype = spec.get("visualType")
    if not page or not vtype:
        raise PlanError(f"visual spec needs 'page' and 'visualType': {spec}")
    where = f"visual '{vtype}' on page '{page}'"

    bindings = spec.get("bindings", {})
    if not bindings:
        raise PlanError(f"{where}: no 'bindings' provided.")

    # Assign a unique table alias per distinct entity across all roles.
    aliases = {}

    def alias_for(table):
        if table not in aliases:
            base = (table[:1] or "t").lower()
            cand = base
            i = 1
            while cand in aliases.values():
                cand = f"{base}{i}"
                i += 1
            aliases[table] = cand
        return aliases[table]

    select = []
    projections = {}
    seen_qrefs = set()
    for role, refs in bindings.items():
        projections[role] = []
        for i, ref in enumerate(refs):
            validate_field(ref, catalog, f"{where} role '{role}'")
            al = alias_for(ref["table"])
            entry, qref = select_entry(ref, al)
            if qref not in seen_qrefs:
                select.append(entry)
                seen_qrefs.add(qref)
            proj = {"queryRef": qref}
            if ref.get("active"):
                proj["active"] = True
            projections[role].append(proj)

    from_clause = [{"Name": al, "Entity": tbl, "Type": 0} for tbl, al in aliases.items()]

    prototype = {"Version": 2, "From": from_clause, "Select": select}

    sort = spec.get("sort")
    if sort:
        validate_field(sort, catalog, f"{where} sort")
        al = alias_for(sort["table"])
        s_entry, _ = select_entry(sort, al)
        # OrderBy uses the bare expression (strip Name/NativeReferenceName)
        s_expr = {k: v for k, v in s_entry.items()
                  if k not in ("Name", "NativeReferenceName")}
        direction = 2 if str(sort.get("direction", "desc")).lower().startswith("d") else 1
        prototype["OrderBy"] = [{"Direction": direction, "Expression": s_expr}]

    pos = spec.get("position", {})
    position = {
        "x": pos.get("x", 0), "y": pos.get("y", 0), "z": pos.get("z", 1000),
        "width": pos.get("width", 400), "height": pos.get("height", 300),
        "tabOrder": pos.get("tabOrder", 0),
    }

    vid = spec.get("id") or new_id()
    single = {
        "visualType": vtype,
        "projections": projections,
        "prototypeQuery": prototype,
        "drillFilterOtherVisuals": True,
    }

    # Merge plan-level theme with per-visual formatting (formatting wins).
    # 'background' del tema es el fondo del LIENZO (página), no de cada visual → se excluye aquí;
    # un fondo por-visual solo viene de spec.formatting.background.
    theme_for_visual = {k: v for k, v in (theme or {}).items() if k != "background"}
    fmt = {**theme_for_visual, **(spec.get("formatting") or {})}
    objects, vc_props = build_formatting(vtype, fmt)

    title = spec.get("title")
    title_measure = spec.get("title_measure")  # "Table.Measure" -> título dinámico (traducción)
    has_title = bool(title or title_measure)

    # R5: si hay título por propiedad, no dupliques el caption por defecto. En slicer = header off.
    if has_title and vtype == "slicer" and fmt.get("hideDefaultCaption", True):
        objects.setdefault("header", [{"properties": {}}])
        objects["header"][0]["properties"]["show"] = _bool_lit(False)

    # Modo del slicer (Dropdown/List/Between) si se indica.
    slicer_mode = fmt.get("slicerMode")
    if vtype == "slicer" and slicer_mode:
        objects.setdefault("data", [{"properties": {}}])
        objects["data"][0]["properties"]["mode"] = _str_lit(slicer_mode)

    if objects:
        single["objects"] = objects

    # syncGroup: slicers sincronizados entre páginas.
    sync = spec.get("syncGroup")
    if sync:
        single["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}

    vc = {}
    if has_title:
        title_props = {"show": _bool_lit(True)}
        if title_measure:
            t, _, m = title_measure.partition(".")
            title_props["text"] = _measure_title_expr(t, m)
        else:
            title_props["text"] = _str_lit(title)
        title_props.update(vc_props.pop("title", {}))
        vc["title"] = [{"properties": title_props}]
    elif vc_props.get("title"):
        vc["title"] = [{"properties": vc_props.pop("title")}]
    vc.update(vc_props)
    if vc:
        single["vcObjects"] = vc

    config = {"name": vid, "layouts": [{"id": 0, "position": position}],
              "singleVisual": single}
    if spec.get("parentGroupName"):
        config["parentGroupName"] = spec["parentGroupName"]

    container = {
        "config": json.dumps(config, ensure_ascii=False),
        "filters": "[]",
        "height": position["height"], "width": position["width"],
        "x": position["x"], "y": position["y"], "z": position["z"],
    }
    return page, vid, container


def main():
    ap = argparse.ArgumentParser(description="Insert native visuals into a legacy report.json")
    ap.add_argument("--report", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--dry-run", action="store_true", help="Validate + report, do not write")
    ap.add_argument("--minify", action="store_true", help="Write minified (default: indent=2)")
    args = ap.parse_args()

    if is_pbir_path(args.report):
        print(PBIR_MSG, file=sys.stderr)
        sys.exit(2)
    for p in (args.report, args.plan, args.catalog):
        if not os.path.isfile(p):
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            sys.exit(2)

    report = load_json(args.report)
    plan = load_json(args.plan)
    catalog = load_json(args.catalog)

    if "sections" not in report:
        print("Este toolkit edita el report.json único (informe del proyecto PBIP). El archivo dado "
              "no tiene 'sections'. Si el informe está en carpeta-por-visual, analízalo con "
              "report_anatomy.py (no se inserta ahí).", file=sys.stderr)
        sys.exit(2)

    sections_by_name = {s.get("displayName"): s for s in report["sections"]}
    visuals = plan.get("visuals", [])
    if not visuals:
        print("ERROR: plan has no 'visuals'.", file=sys.stderr)
        sys.exit(2)
    # Tema efectivo = defaults internos <- theme del plan (el usuario manda donde especifique).
    theme = merge_theme(plan.get("theme"))

    inserted = []
    custom_used = set()    # custom visual GUIDs to register in publicCustomVisuals
    pages_touched = []     # secciones que recibieron visuales (para colorear su lienzo)
    try:
        for spec in visuals:
            if spec.get("group"):
                page, vid, container = build_group_container(spec)
                vtype = "group"
            else:
                page, vid, container = build_visual_container(spec, catalog, theme)
                vtype = spec.get("visualType")
                if is_custom_visual(vtype):
                    custom_used.add(vtype)
            if page not in sections_by_name:
                avail = ", ".join(repr(k) for k in sections_by_name)
                raise PlanError(f"page '{page}' not found. Available pages: {avail}")
            section = sections_by_name[page]
            section.setdefault("visualContainers", []).append(container)
            if section not in pages_touched:
                pages_touched.append(section)
            inserted.append((page, vid, vtype))
    except PlanError as e:
        print(f"PLAN ERROR (nothing written): {e}", file=sys.stderr)
        sys.exit(1)

    # Fondo del LIENZO: colorear las páginas tocadas con theme.background (default o del usuario),
    # salvo opt-out explícito (plan["page_background"] == false).
    pages_colored = 0
    if plan.get("page_background", True) and theme.get("background"):
        for section in pages_touched:
            set_page_background(section, theme["background"])
            pages_colored += 1

    # Register any custom visual used (e.g. the HTML Content custom visual) so the report loads it.
    registered = []
    if custom_used:
        pcv = report.setdefault("publicCustomVisuals", [])
        for guid in sorted(custom_used):
            if guid not in pcv:
                pcv.append(guid)
                registered.append(guid)

    print("Planned insertions:")
    for page, vid, vtype in inserted:
        print(f"  [{page}] {vtype} -> {vid}")
    if registered:
        print("Registered custom visuals (publicCustomVisuals):")
        for guid in registered:
            print(f"  + {guid}")
    if pages_colored:
        print(f"Page background applied to {pages_colored} page(s): {theme['background']}")

    if args.dry_run:
        print("\nDRY RUN: no file written. Round-trip check on in-memory result...")
        json.dumps(report, ensure_ascii=False)
        print("OK: result serializes cleanly.")
        return

    backup = args.report + ".bak"
    shutil.copy2(args.report, backup)
    dump_kwargs = {"ensure_ascii": False}
    if args.minify:
        dump_kwargs["separators"] = (",", ":")
    else:
        dump_kwargs["indent"] = 2
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, **dump_kwargs)

    # Re-validate the written file round-trips.
    with open(args.report, encoding="utf-8") as f:
        json.load(f)
    print(f"\nWrote {args.report} ({len(inserted)} visuals). Backup: {backup}")
    print("Next: open the project in Power BI Desktop to verify the visuals render.")


if __name__ == "__main__":
    main()
