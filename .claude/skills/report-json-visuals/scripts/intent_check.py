#!/usr/bin/env python3
"""
intent_check.py — PREFLIGHT: validate intent.yaml against the model catalog BEFORE designing.

Why this exists: the previous render bound slicers to wrong fields, showed % as decimals and left
tables empty because nobody reconciled the friendly names in intent.yaml with the real model. This
catches those issues up front so the designer never binds to a non-existent/incorrect field.

Checks (compact report):
  - Name resolution: every field/measure/dimension referenced in intent (filters, pages, visuals,
    primary/kpi measures, time_dimension, title_measure) must resolve to a real catalog entry.
    UNRESOLVED -> BLOCKING (the designer must fix names or create the measure first).
  - % format: referenced measures that look like percentages but whose formatString isn't '%'.
  - Tables without fields: a visual role:table with no fields/columns -> empty visual risk.
  - counts vs visuals: per-page mismatch between counts{} and the explicit visuals[] list.

Reads intent.yaml with PyYAML if available; otherwise falls back to a tolerant regex scan that
still resolves names (structural checks are skipped with a note). catalog.json is small JSON.

Usage:
    python intent_check.py --intent intent.yaml --catalog catalog.json
Exit code 0 = no blocking; non-zero = unresolved names (blocking).
"""
import argparse
import json
import re
import sys

PCT = re.compile(r"%|adher|cumpl|tasa|ratio|porcentaje", re.IGNORECASE)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_index(catalog):
    cols, meas, by_leaf = set(), set(), {}
    for t, info in catalog.get("tables", {}).items():
        for c in info.get("columns", []):
            cols.add(f"{t}.{c}"); by_leaf.setdefault(c.lower(), []).append(f"{t}.{c}")
        for m in info.get("measures", []):
            meas.add(f"{t}.{m}"); by_leaf.setdefault(m.lower(), []).append(f"{t}.{m}")
    return cols, meas, by_leaf


def resolve(name, idx):
    cols, meas, by_leaf = idx
    name = str(name).strip().strip('"').strip("'")
    if not name:
        return "empty", None
    if "." in name:
        if name in cols or name in meas:
            return "ok", name
        low = name.lower()
        for ref in cols | meas:
            if ref.lower() == low:
                return "ok", ref
        return "unresolved", None
    hits = by_leaf.get(name.lower())
    if not hits:
        return "unresolved", None
    return ("ok", hits[0]) if len(hits) == 1 else ("ambiguous", hits)


def refs_from_yaml(data):
    """Yield (kind, name) references from a parsed intent dict."""
    out = []

    def add(kind, v):
        if isinstance(v, str) and v.strip():
            out.append((kind, v))

    for f in data.get("filters", []) or []:
        if isinstance(f, dict):
            add("filter.field", f.get("field"))
    for pg in data.get("pages", []) or []:
        if not isinstance(pg, dict):
            continue
        for m in pg.get("primary_measures", []) or []:
            add("primary_measure", m)
        for m in pg.get("kpi_measures", []) or []:
            add("kpi_measure", m)
        for d in pg.get("primary_dimensions", []) or []:
            add("primary_dimension", d)
        add("time_dimension", pg.get("time_dimension"))
        for v in pg.get("visuals", []) or []:
            if not isinstance(v, dict):
                continue
            add(f"visual[{v.get('area', v.get('role', '?'))}].field", v.get("field"))
            add(f"visual[{v.get('area', v.get('role', '?'))}].measure", v.get("measure"))
            add(f"visual[{v.get('area', v.get('role', '?'))}].dimension", v.get("dimension"))
            add(f"visual[{v.get('area', v.get('role', '?'))}].title_measure", v.get("title_measure"))
    return out


def refs_from_text(text):
    """Fallback: regex-extract references when PyYAML isn't available."""
    out = []
    for key in ("field", "measure", "dimension", "time_dimension", "title_measure"):
        for m in re.finditer(rf"\b{key}:\s*([^,}}\n]+)", text):
            val = m.group(1).strip().strip('"').strip("'").strip()
            if val and not val.startswith(("[", "{")):
                out.append((key, val))
    # any quoted qualified ref "Table.field" (covers inline lists like ["Medidas.X"])
    for m in re.finditer(r"[\"']([A-Za-z_]\w*\.[\w%]+)[\"']", text):
        out.append(("ref", m.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser(description="Preflight: validate intent.yaml vs catalog.json")
    ap.add_argument("--intent", required=True)
    ap.add_argument("--catalog", required=True)
    args = ap.parse_args()

    catalog = load_json(args.catalog)
    idx = build_index(catalog)
    formats = catalog.get("measure_formats", {})

    text = open(args.intent, encoding="utf-8").read()
    data, structural = None, True
    try:
        import yaml
        data = yaml.safe_load(text)
    except Exception:
        structural = False

    refs = refs_from_yaml(data) if (data is not None) else refs_from_text(text)

    unresolved, ambiguous, pct_warn = [], [], []
    seen = set()
    for kind, name in refs:
        key = (kind, name)
        if key in seen:
            continue
        seen.add(key)
        status, sugg = resolve(name, idx)
        if status == "unresolved":
            unresolved.append((kind, name))
        elif status == "ambiguous":
            ambiguous.append((kind, name, sugg))
        # % format check on resolved measures
        ref = sugg if isinstance(sugg, str) else None
        if ref and ref in idx[1]:
            leaf = ref.split(".", 1)[-1]
            if PCT.search(leaf) and "%" not in (formats.get(ref, "") or ""):
                pct_warn.append(ref)

    tables_no_fields, counts_mismatch = [], []
    if data is not None:
        for pg in data.get("pages", []) or []:
            if not isinstance(pg, dict):
                continue
            vis = pg.get("visuals", []) or []
            for v in vis:
                if isinstance(v, dict) and v.get("role") == "table" and not v.get("fields"):
                    tables_no_fields.append(v.get("area", v.get("title", "?")))
            counts = pg.get("counts") or {}
            if counts and vis:
                fam = {"slicer": "slicers", "kpi": "kpis", "chart": "charts", "table": "tables"}
                got = {}
                for v in vis:
                    g = fam.get(v.get("role"))
                    if g:
                        got[g] = got.get(g, 0) + 1
                for g, n in counts.items():
                    if got.get(g, 0) != n:
                        counts_mismatch.append(f"{pg.get('name','?')}: {g} counts={n} vs visuals={got.get(g,0)}")

    # ---- report (compact) ----
    print(f"refs checked: {len(seen)}")
    if not structural:
        print("note: PyYAML no instalado → solo resolución de nombres (sin chequeos estructurales).")
    if pct_warn:
        print(f"\n% sin formato ({len(set(pct_warn))}): " + ", ".join(sorted(set(pct_warn))))
    if tables_no_fields:
        print(f"\nTablas sin 'fields' ({len(tables_no_fields)}): " + ", ".join(map(str, tables_no_fields)))
    if counts_mismatch:
        print("\ncounts vs visuals:")
        for c in counts_mismatch:
            print(f"  - {c}")
    if ambiguous:
        print(f"\nAmbiguos ({len(ambiguous)}) — califica Tabla.campo:")
        for kind, name, sugg in ambiguous:
            print(f"  - {kind}: '{name}' -> {sugg}")
    if unresolved:
        print(f"\nBLOQUEANTE — nombres NO resueltos ({len(unresolved)}):")
        for kind, name in unresolved:
            print(f"  - {kind}: '{name}'")
        sys.exit(1)
    print("\nOK: nombres resueltos.")


if __name__ == "__main__":
    main()
