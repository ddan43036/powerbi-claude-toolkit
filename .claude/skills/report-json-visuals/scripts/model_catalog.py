#!/usr/bin/env python3
"""
model_catalog.py — Build a compact JSON catalog of a Power BI semantic model from TMDL.

The catalog is the single source of truth for "what fields exist" so the report side never
invents table/column/measure names, and so agents reason over a small JSON instead of
re-reading every .tmdl (token saving). Pragmatic extractor, not a full TMDL parser.

Usage:
    python model_catalog.py <path-to-*.SemanticModel/definition> [-o catalog.json]
"""
import argparse
import json
import os
import re
import sys

RE_TABLE = re.compile(r"^\s*table\s+(?P<name>'[^']+'|[^\s]+)\s*$")
RE_COLUMN = re.compile(r"^\s*column\s+(?P<name>'[^']+'|[^\s=]+)")
RE_MEASURE = re.compile(r"^\s*measure\s+(?P<name>'[^']+'|[^\s=]+)\s*=")
RE_DISPLAYFOLDER = re.compile(r"^\s*displayFolder:\s*(?P<v>.+?)\s*$")
RE_FORMATSTRING = re.compile(r"^\s*formatString:\s*(?P<v>.+?)\s*$")
RE_REL = re.compile(r"^\s*relationship\s+(?P<name>\S+)")
RE_FROMCOL = re.compile(r"^\s*fromColumn:\s*(?P<ref>.+?)\s*$")
RE_TOCOL = re.compile(r"^\s*toColumn:\s*(?P<ref>.+?)\s*$")
RE_ISACTIVE = re.compile(r"^\s*isActive:\s*(?P<v>\w+)")
RE_XFILTER = re.compile(r"^\s*crossFilteringBehavior:\s*(?P<v>\w+)")

# Column names that hint a calendar / date table (used to tag role "time").
RE_TIMECOL = re.compile(
    r"(fecha|date|a[nñ]o|year|mes|month|semana|week|trimestre|quarter|periodo|d[ií]a\b|day)",
    re.IGNORECASE,
)


def unquote(name):
    name = name.strip()
    if name.startswith("'") and name.endswith("'"):
        return name[1:-1]
    return name


def split_ref(ref):
    ref = ref.strip()
    m = re.match(r"^'([^']+)'\.(.+)$", ref)
    if m:
        return unquote(m.group(1)), unquote(m.group(2))
    if "." in ref:
        table, _, col = ref.partition(".")
        return unquote(table), unquote(col)
    return None, unquote(ref)


def indent_of(line):
    n = 0
    for ch in line:
        if ch in ("\t", " "):
            n += 1
        else:
            break
    return n


def parse_tmdl_file(path, tables, folders=None, formats=None, bodies=None, param_tables=None):
    current = None
    tindent = None
    last_measure = None  # (table, measure) to attach the next displayFolder line to
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("/"):
                continue
            ind = indent_of(line)
            mt = RE_TABLE.match(line)
            if mt:
                current = unquote(mt.group("name"))
                tindent = ind
                last_measure = None
                tables.setdefault(current, {"columns": [], "measures": []})
                continue
            if current is not None and tindent is not None and ind <= tindent:
                s = line.lstrip()
                if not (s.startswith(("column", "measure", "hierarchy", "partition", "'"))
                        or ":" in s):
                    if not s.startswith("table"):
                        current = None
            if current is not None:
                # Field Parameter marker (used for language switchers like TL_*).
                if param_tables is not None and "ParameterMetadata" in line:
                    param_tables.add(current)
                mc = RE_COLUMN.match(line)
                if mc:
                    col = unquote(mc.group("name"))
                    if col not in tables[current]["columns"]:
                        tables[current]["columns"].append(col)
                    last_measure = None
                    continue
                mm = RE_MEASURE.match(line)
                if mm:
                    meas = unquote(mm.group("name"))
                    if meas not in tables[current]["measures"]:
                        tables[current]["measures"].append(meas)
                    last_measure = (current, meas)
                    if bodies is not None:
                        bodies[last_measure] = [line]   # measure decl (may hold inline expr)
                    continue
                if last_measure is not None:
                    if bodies is not None:
                        bodies[last_measure].append(line)  # accumulate the measure body
                    if folders is not None:
                        md = RE_DISPLAYFOLDER.match(line)
                        if md:
                            folders[last_measure] = md.group("v")
                            continue
                    if formats is not None:
                        mfs = RE_FORMATSTRING.match(line)
                        if mfs:
                            formats[last_measure] = mfs.group("v")


def parse_relationships(path, rels):
    cur = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            mr = RE_REL.match(line)
            if mr:
                if cur:
                    rels.append(cur)
                cur = {"name": mr.group("name"), "fromTable": None, "fromColumn": None,
                       "toTable": None, "toColumn": None, "isActive": True,
                       "crossFilteringBehavior": None}
                continue
            if cur is None:
                continue
            mf = RE_FROMCOL.match(line)
            if mf:
                cur["fromTable"], cur["fromColumn"] = split_ref(mf.group("ref"))
                continue
            mtc = RE_TOCOL.match(line)
            if mtc:
                cur["toTable"], cur["toColumn"] = split_ref(mtc.group("ref"))
                continue
            ma = RE_ISACTIVE.match(line)
            if ma:
                cur["isActive"] = ma.group("v").lower() == "true"
                continue
            mx = RE_XFILTER.match(line)
            if mx:
                cur["crossFilteringBehavior"] = mx.group("v")
    if cur:
        rels.append(cur)


def classify_tables(tables, relationships, auto):
    """Tag each table with a coarse role so the analyst/designer can tell dimensions from facts
    without re-reading the TMDL. Heuristic (relationships drive the cardinality call):
      - "measures"  : holds measures and (almost) no columns (e.g. the `Medidas` table).
      - "time"      : has calendar/date-like columns (lookup side of date relationships).
      - "fact"      : sits on the MANY side of a relationship (fromTable) -> transactions.
      - "dimension" : sits ONLY on the ONE side (toTable) -> lookup/categorical.
      - "unknown"   : no relationships and no measures -> the agent decides.
      - "auto"      : auto-generated date tables (ignore).
    """
    auto_set = set(auto)
    one_side, many_side = set(), set()
    for r in relationships:
        if r.get("toTable"):
            one_side.add(r["toTable"])
        if r.get("fromTable"):
            many_side.add(r["fromTable"])
    roles = {}
    for t, info in tables.items():
        if t in auto_set:
            roles[t] = "auto"
            continue
        cols = info.get("columns", [])
        meas = info.get("measures", [])
        if meas and len(cols) == 0:
            roles[t] = "measures"
            continue
        timehits = sum(1 for c in cols if RE_TIMECOL.search(c))
        if timehits >= 2 or (timehits >= 1 and t in one_side):
            roles[t] = "time"
        elif t in many_side:
            roles[t] = "fact"
        elif t in one_side:
            roles[t] = "dimension"
        else:
            roles[t] = "measures" if meas else "unknown"
    return roles


def is_html_measure(name):
    low = name.lower()
    return ("html" in low or low.startswith("donut")
            or low.startswith(("m_html", "m_json", "m_css")))


def detect_translation(tables, measures_index, translation_measures, bodies, param_tables):
    """Detect the i18n strategy. Three patterns coexist in the wild:
      lookup   -> dim_traduccion(id/idioma/texto) + per-string measures (CdP).
      switch   -> a language table [Sigla] + measures using SWITCH(SELECTEDVALUE(lang)) and/or
                  Field Parameters that swap per-language columns (GESPRO).
      metadata -> a 'Localized Labels' table (Translations Builder; viewer-locale).
    """
    strategy = []
    # language table: has columns Idioma + Sigla, or a known name.
    lang_table, lang_col = None, None
    for t, info in tables.items():
        cols = {c.lower() for c in info.get("columns", [])}
        if ("idioma" in cols and "sigla" in cols) or t in ("TL__Idiomas", "TablaIdiomas", "dim_idioma"):
            lang_table = t
            lang_col = "Sigla" if "sigla" in cols else ("id_idioma" if "id_idioma" in cols else None)
            break
    # lookup table (CdP-style dictionary)
    lookup = None
    for t, info in tables.items():
        cols = {c.lower() for c in info.get("columns", [])}
        if "texto_traducido" in cols or t.lower() == "dim_traduccion" or \
                ("id_traduccion" in cols and "id_idioma" in cols):
            lookup = t
            break
    if lookup or translation_measures:
        strategy.append("lookup")
    # metadata (Translations Builder)
    localized = any(t.lower() == "localized labels" for t in tables)
    if localized:
        strategy.append("metadata")
    # field parameters (mark language ones: have an 'Idioma' column)
    field_parameters = sorted(param_tables or [])
    lang_field_params = [t for t in field_parameters
                         if any(c.lower() == "idioma" for c in tables.get(t, {}).get("columns", []))]
    # switch measures: body uses SELECTEDVALUE(langtable) or SWITCH(SELECTEDVALUE(...[Sigla]/[Idioma]))
    switch_measures = []
    for (tbl, m), lines in (bodies or {}).items():
        b = "\n".join(lines)
        if "SELECTEDVALUE" not in b:
            continue
        if (lang_table and lang_table in b) or ("[Sigla]" in b or "[Idioma]" in b):
            if "SWITCH" in b or (lang_table and lang_table in b):
                switch_measures.append(f"{tbl}.{m}")
    switch_measures.sort()
    if switch_measures or lang_field_params:
        strategy.append("switch")
    # active-language measure (Idioma_Activo / Idioma Ativo ...)
    active = next((f"{measures_index[m]}.{m}" for m in measures_index
                   if m.lower().replace(" ", "_").startswith("idioma_activ")), None)
    return {
        "strategy": strategy,
        "language_table": lang_table,
        "language_column": lang_col,
        "active_language_measure": active,
        "lookup_table": lookup,
        "switch_measures": switch_measures,
        "field_parameters": field_parameters,
        "language_field_parameters": lang_field_params,
        "localized_labels": localized,
    }


def build_catalog(definition_dir, translation_folder="traduccion"):
    tables, rels, folders, formats = {}, [], {}, {}
    bodies, param_tables = {}, set()
    for root, _d, files in os.walk(definition_dir):
        for fn in files:
            if not fn.endswith(".tmdl"):
                continue
            path = os.path.join(root, fn)
            parse_tmdl_file(path, tables, folders, formats, bodies, param_tables)
            if "relationship" in fn.lower() or fn.lower() == "model.tmdl":
                parse_relationships(path, rels)
    measures_index = {m: t for t, info in tables.items() for m in info["measures"]}
    # Flag auto-generated local date tables so the designer can ignore them.
    auto = [t for t in tables if t.startswith("LocalDateTable_") or t.startswith("DateTableTemplate_")]
    table_roles = classify_tables(tables, rels, auto)
    # Measures living in the translation displayFolder = source of dynamic (multilingual) titles.
    tf = translation_folder.lower()
    translation_measures = sorted(f"{t}.{m}" for (t, m), fld in folders.items()
                                  if tf in fld.lower())
    # formatString per measure (empty if none) so the designer/validator can enforce % formats.
    measure_formats = {f"{t}.{m}": fs for (t, m), fs in formats.items()}
    # Measures that render HTML (feed the HTML Content custom visual).
    html_measures = sorted(f"{t}.{m}" for t, info in tables.items()
                           for m in info["measures"] if is_html_measure(m))
    translation = detect_translation(tables, measures_index, translation_measures,
                                     bodies, param_tables)
    return {"tables": tables, "measures_index": measures_index,
            "relationships": rels, "auto_generated_tables": auto,
            "table_roles": table_roles, "translation_measures": translation_measures,
            "measure_formats": measure_formats, "html_measures": html_measures,
            "translation": translation}


def main():
    ap = argparse.ArgumentParser(description="Build a JSON catalog from a TMDL model.")
    ap.add_argument("definition_dir", help="Path to *.SemanticModel/definition")
    ap.add_argument("-o", "--out")
    ap.add_argument("--translation-folder", default="traduccion",
                    help="displayFolder name that marks translation measures (default: traduccion)")
    args = ap.parse_args()
    if not os.path.isdir(args.definition_dir):
        print(f"ERROR: not a directory: {args.definition_dir}", file=sys.stderr)
        sys.exit(2)
    cat = build_catalog(args.definition_dir, args.translation_folder)
    text = json.dumps(cat, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        roles = cat["table_roles"]
        nf = sum(1 for r in roles.values() if r == "fact")
        nd = sum(1 for r in roles.values() if r == "dimension")
        nt = sum(1 for r in roles.values() if r == "time")
        strat = ",".join(cat["translation"]["strategy"]) or "none"
        print(f"Wrote {args.out}: {len(cat['tables'])} tables "
              f"({nf} fact, {nd} dim, {nt} time), "
              f"{len(cat['measures_index'])} measures "
              f"({len(cat['translation_measures'])} translation), "
              f"{len(cat['relationships'])} relationships; i18n=[{strat}].", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
