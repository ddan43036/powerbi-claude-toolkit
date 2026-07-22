#!/usr/bin/env python3
"""
validate_report.py — Sanity-check a legacy report.json after edits.

Checks (token-light, runs locally on the user's machine):
  1. JSON well-formedness (round-trip).
  2. Every visualContainer.config is valid JSON and has name + singleVisual.visualType.
  3. Referential integrity: every prototypeQuery From Entity exists in the model catalog,
     and every Select Property exists as a column/measure of that table.
  4. Position sanity: visuals fall within their page width/height when those are present.
  5. No duplicate visual ids across the report.

Usage:
    python validate_report.py --report <report.json> [--catalog <catalog.json>]

Exit code 0 = no blocking issues. Non-zero = blocking issues found.
"""
import argparse
import json
import re
import sys

NO_DATA_TYPES = {"shape", "image", "textbox", "actionButton"}
PCT_NAME = re.compile(r"%|adher|cumpl|tasa|ratio|porcentaje", re.IGNORECASE)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_custom_visual(vtype):
    return bool(re.search(r"[A-Fa-f0-9]{20,}", vtype or ""))


def is_pbir_path(p):
    import os
    if os.path.isdir(p):
        return (os.path.isfile(os.path.join(p, "pages", "pages.json"))
                or os.path.isfile(os.path.join(p, "definition", "pages", "pages.json")))
    return os.path.isfile(os.path.join(os.path.dirname(p), "pages", "pages.json"))


def field_table_of(entity, alias_map):
    return alias_map.get(entity, entity)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--catalog")
    args = ap.parse_args()

    blocking, warnings = [], []

    if is_pbir_path(args.report):
        print("El informe está en carpeta-por-visual, no como report.json único. Este validador "
              "trabaja sobre report.json; para analizar el informe en carpeta usa report_anatomy.py.")
        sys.exit(2)

    try:
        report = load(args.report)
    except Exception as e:
        print(f"BLOCKING: report.json is not valid JSON: {e}")
        sys.exit(1)

    catalog = load(args.catalog) if args.catalog else None
    tables = catalog.get("tables", {}) if catalog else {}

    sections = report.get("sections", [])
    if not sections:
        warnings.append("report has no 'sections'.")

    registered = set(report.get("publicCustomVisuals", []))
    group_ids = set()        # ids of singleVisualGroup containers
    parent_refs = []         # (page, vid, parentGroupName) to validate after the loop
    used_measures = set()    # "Table.Measure" referenced by any visual

    seen_ids = {}
    for sec in sections:
        page = sec.get("displayName", "?")
        pw = sec.get("width")
        ph = sec.get("height")
        for vc in sec.get("visualContainers", []):
            raw = vc.get("config")
            if not isinstance(raw, str):
                blocking.append(f"[{page}] a visualContainer has no string 'config'.")
                continue
            try:
                cfg = json.loads(raw)
            except Exception as e:
                blocking.append(f"[{page}] config is not valid JSON: {e}")
                continue

            vid = cfg.get("name", "?")
            if vid in seen_ids:
                blocking.append(f"duplicate visual id '{vid}' (pages {seen_ids[vid]} & {page}).")
            else:
                seen_ids[vid] = page

            if cfg.get("parentGroupName"):
                parent_refs.append((page, vid, cfg["parentGroupName"]))

            sv = cfg.get("singleVisual")
            if not sv:
                # groups (singleVisualGroup) are fine; record their id
                if "singleVisualGroup" not in cfg:
                    warnings.append(f"[{page}] {vid}: no singleVisual/singleVisualGroup.")
                else:
                    group_ids.add(vid)
                continue
            vtype = sv.get("visualType")
            if not vtype:
                blocking.append(f"[{page}] {vid}: singleVisual has no visualType.")
            else:
                # Custom visuals must be registered or the report won't load them.
                if is_custom_visual(vtype) and vtype not in registered:
                    blocking.append(
                        f"[{page}] {vid}: custom visual '{vtype}' not in publicCustomVisuals.")
                # Data visual with no fields bound (e.g. an empty table).
                if vtype not in NO_DATA_TYPES and not sv.get("projections"):
                    warnings.append(f"[{page}] {vid}: {vtype} has no fields bound (empty visual).")

            # Position sanity
            try:
                pos = cfg["layouts"][0]["position"]
                if pw and pos.get("x", 0) + pos.get("width", 0) > pw + 1:
                    warnings.append(f"[{page}] {vid}: extends past page width.")
                if ph and pos.get("y", 0) + pos.get("height", 0) > ph + 1:
                    warnings.append(f"[{page}] {vid}: extends past page height.")
            except Exception:
                pass

            # Referential integrity against the catalog
            if catalog:
                pq = sv.get("prototypeQuery", {})
                alias_map = {f.get("Name"): f.get("Entity") for f in pq.get("From", [])}
                for ent_alias, entity in alias_map.items():
                    if entity not in tables:
                        blocking.append(f"[{page}] {vid}: table '{entity}' not in model.")
                for sel in pq.get("Select", []):
                    expr = sel.get("Column") or sel.get("Measure")
                    is_measure = "Measure" in sel
                    if not expr:
                        # Aggregation wraps a Column
                        agg = sel.get("Aggregation", {})
                        expr = agg.get("Expression", {}).get("Column")
                        is_measure = False
                    if not expr:
                        continue
                    prop = expr.get("Property")
                    src_alias = expr.get("Expression", {}).get("SourceRef", {}).get("Source")
                    entity = alias_map.get(src_alias, src_alias)
                    if is_measure and prop:
                        used_measures.add(f"{entity}.{prop}")
                    if entity in tables and prop:
                        bucket = "measures" if is_measure else "columns"
                        if prop not in tables[entity].get(bucket, []):
                            blocking.append(
                                f"[{page}] {vid}: {bucket[:-1]} '{entity}.{prop}' not in model.")

    # parentGroupName must point to an existing group.
    for page, vid, parent in parent_refs:
        if parent not in group_ids and parent not in seen_ids:
            warnings.append(f"[{page}] {vid}: parentGroupName '{parent}' has no matching group.")

    # Percentage measures USED in the report whose formatString isn't a percent (render as decimals).
    if catalog:
        formats = catalog.get("measure_formats") or {}
        for mref in sorted(used_measures):
            name = mref.split(".", 1)[-1]
            fmt = formats.get(mref, "")
            if PCT_NAME.search(name) and "%" not in (fmt or ""):
                warnings.append(f"measure '{mref}' looks like a percentage but its formatString "
                                f"is not '%' ({fmt or 'none'}) — fix formatString.")

    print(f"Visuals checked: {len(seen_ids)}")
    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
    if blocking:
        print(f"\nBLOCKING ISSUES ({len(blocking)}):")
        for b in blocking:
            print(f"  - {b}")
        sys.exit(1)
    print("\nOK: no blocking issues.")


if __name__ == "__main__":
    main()
