#!/usr/bin/env python3
"""Post-inserción: fija el modo de los slicers nativos (Dropdown por defecto) en un
report.json heredado, sin cargar el blob al contexto de Claude. Edita solo los
visualContainers cuyo singleVisual.visualType == 'slicer' en la página indicada.

Uso:
    python set_slicer_mode.py --report <ruta/report.json> [--page "Página 2"] [--mode Dropdown]

Crea backup .slicerbak antes de escribir y re-valida el round-trip JSON.
"""
import argparse, json, shutil, sys


def lit(value):  # literal Power Fx string: 'Dropdown'
    return {"expr": {"Literal": {"Value": "'" + str(value).replace("'", "''") + "'"}}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--page", default=None, help="displayName de la sección; omitir = todas")
    ap.add_argument("--mode", default="Dropdown", help="Dropdown | Basic")
    args = ap.parse_args()

    with open(args.report, encoding="utf-8") as f:
        report = json.load(f)

    changed = []
    for section in report.get("sections", []):
        if args.page and section.get("displayName") != args.page:
            continue
        for vc in section.get("visualContainers", []):
            cfg = json.loads(vc["config"])
            sv = cfg.get("singleVisual", {})
            if sv.get("visualType") != "slicer":
                continue
            objs = sv.setdefault("objects", {})
            objs["data"] = [{"properties": {"mode": lit(args.mode)}}]
            vc["config"] = json.dumps(cfg, ensure_ascii=False)
            changed.append(cfg.get("name"))

    if not changed:
        print("No se encontraron slicers para modificar.", file=sys.stderr)
        sys.exit(1)

    backup = args.report + ".slicerbak"
    shutil.copy2(args.report, backup)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(args.report, encoding="utf-8") as f:
        json.load(f)  # re-valida round-trip

    print(f"Slicers fijados a modo '{args.mode}': {len(changed)}")
    for n in changed:
        print(f"  - {n}")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
