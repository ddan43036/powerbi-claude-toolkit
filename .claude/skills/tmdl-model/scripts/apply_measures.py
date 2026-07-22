#!/usr/bin/env python3
"""
apply_measures.py — Safely ADD or MODIFY DAX measures in a TMDL table file (e.g. Medidas.tmdl).

Why this exists: the analyst PROPOSES measure ideas but never writes DAX. When the user approves
an idea (and the DAX has been authored following the team's Medidas.tmdl conventions), this
script performs the mechanical, token-safe file mutation — the same role insert_visuals.py plays
for report.json. It never loads the .tmdl into the model's context: Python reads, splices and
writes; the model only sees a short summary.

This script does NOT invent or validate DAX. The `expression` you pass is written verbatim with
correct TMDL indentation. Authoring/correctness of the DAX follows the toolkit's own rules in
tmdl-model/reference/dax-authoring.md. Behavior is an UPSERT: an "add" that already exists is
replaced (with a warning); a "modify" that's missing is added (with a warning).

Approval gate: run only AFTER the user approved the measure(s). Always writes a .bak first.

Usage:
    python apply_measures.py --tmdl <...\\tables\\Medidas.tmdl> --measures measures.json [--dry-run]
    python apply_measures.py --model <...\\X.SemanticModel\\definition> --table Medidas \\
                             --measures measures.json [--dry-run]

measures.json:
{
  "table": "Medidas",                 // informational; --tmdl/--table decide the file
  "measures": [
    {
      "name": "Adherencia YoY %",
      "expression": "DIVIDE([Adherencia] - [Adherencia PY], [Adherencia PY])",
      "formatString": "0.0%",         // optional
      "displayFolder": "KPIs",        // optional
      "description": "Variación interanual de adherencia",  // optional (/// comment)
      "mode": "add"                    // "add" | "modify"  (upsert either way)
    }
  ]
}

After a real run, re-run model_catalog.py so catalog.json picks up the new/changed measures.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

RE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def leading_ws(line):
    return line[: len(line) - len(line.lstrip())]


def quote_name(name):
    return name if RE_IDENT.match(name) else "'" + name.replace("'", "''") + "'"


def build_block(m, ind):
    """Render a TMDL measure block. prop lines = ind+1 tab; multi-line expr = ind+2 tabs
    (deeper than properties, as TMDL requires)."""
    prop_ind = ind + "\t"
    expr_ind = ind + "\t\t"
    name = m["name"]
    expr = str(m.get("expression", "")).rstrip("\n")
    if not expr.strip():
        raise ValueError(f"measure '{name}' has empty 'expression'.")
    lines = []
    desc = m.get("description")
    if desc:
        for d in str(desc).split("\n"):
            lines.append(f"{ind}/// {d.strip()}")
    if "\n" in expr:
        lines.append(f"{ind}measure {quote_name(name)} =")
        for ln in expr.split("\n"):
            lines.append(f"{expr_ind}{ln.rstrip()}" if ln.strip() else "")
    else:
        lines.append(f"{ind}measure {quote_name(name)} = {expr.strip()}")
    if m.get("formatString"):
        lines.append(f"{prop_ind}formatString: {m['formatString']}")
    if m.get("displayFolder"):
        lines.append(f"{prop_ind}displayFolder: {m['displayFolder']}")
    return lines


def block_span(lines, start):
    """Given the measure declaration at `start`, return (end_exclusive) trimming trailing blanks.
    The block is the declaration plus all deeper-indented / blank lines that follow."""
    ws = leading_ws(lines[start])
    j = start + 1
    while j < len(lines):
        s = lines[j]
        if s.strip() == "":
            j += 1
            continue
        if len(leading_ws(s)) <= len(ws):
            break
        j += 1
    end = j
    while end - 1 > start and lines[end - 1].strip() == "":
        end -= 1
    return end


def find_measure(lines, name):
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s*)measure\s+('([^']+)'|[^\s=]+)\s*=", ln)
        if m:
            mname = m.group(3) if m.group(3) else m.group(2)
            if mname == name:
                # Absorb the measure's preceding /// description lines so a modify replaces them
                # instead of duplicating.
                start = i
                while start - 1 >= 0 and lines[start - 1].lstrip().startswith("///"):
                    start -= 1
                return start, block_span(lines, i), leading_ws(ln)
    return None


def child_indent(lines):
    for ln in lines:
        m = re.match(r"^(\s*)(measure|column)\s+", ln)
        if m:
            return m.group(1)
    return "\t"


def last_measure_end(lines):
    end = None
    for i, ln in enumerate(lines):
        if re.match(r"^\s*measure\s+", ln):
            end = block_span(lines, i)
    return end


def resolve_tmdl(args):
    if args.tmdl:
        return args.tmdl
    if args.model and args.table:
        cand = os.path.join(args.model, "tables", f"{args.table}.tmdl")
        if os.path.isfile(cand):
            return cand
        # case-insensitive fallback
        tdir = os.path.join(args.model, "tables")
        if os.path.isdir(tdir):
            for fn in os.listdir(tdir):
                if fn.lower() == f"{args.table}.tmdl".lower():
                    return os.path.join(tdir, fn)
    return None


def main():
    ap = argparse.ArgumentParser(description="Add/modify DAX measures in a TMDL table file.")
    ap.add_argument("--tmdl", help="Path to the table .tmdl (e.g. Medidas.tmdl).")
    ap.add_argument("--model", help="Path to *.SemanticModel/definition (with --table).")
    ap.add_argument("--table", help="Table name to resolve under --model/tables.")
    ap.add_argument("--measures", required=True, help="Path to measures.json.")
    ap.add_argument("--dry-run", action="store_true", help="Report changes, do not write.")
    ap.add_argument("--allow-mirror", action="store_true",
                    help="Permite escribir fuera de definition/ (copias espejo). No recomendado.")
    ap.add_argument("--no-qa", action="store_true", help="Omite el QA post-escritura (dax_qa.py).")
    args = ap.parse_args()

    tmdl = resolve_tmdl(args)
    if not tmdl or not os.path.isfile(tmdl):
        print("ERROR: could not resolve the .tmdl file. Use --tmdl or --model + --table.",
              file=sys.stderr)
        sys.exit(2)

    # Guarda de COPIA ESPEJO: solo se edita bajo .../SemanticModel/definition/.
    # Lo que está fuera lo regenera Power BI y tu cambio se perdería.
    if "/definition/" not in tmdl.replace("\\", "/").lower() and not args.allow_mirror:
        print("ERROR: esa ruta NO está bajo `definition/` → es una COPIA ESPEJO que Power BI "
              "regenera. Edita `...SemanticModel/definition/tables/<Tabla>.tmdl` "
              "(o usa --allow-mirror si sabes lo que haces).", file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(args.measures):
        print(f"ERROR: measures file not found: {args.measures}", file=sys.stderr)
        sys.exit(2)

    with open(args.measures, encoding="utf-8") as f:
        spec = json.load(f)
    measures = spec.get("measures", [])
    if not measures:
        print("ERROR: measures.json has no 'measures'.", file=sys.stderr)
        sys.exit(2)

    with open(tmdl, encoding="utf-8") as f:
        text = f.read()
    had_final_nl = text.endswith("\n")
    lines = text.split("\n")
    if had_final_nl and lines and lines[-1] == "":
        lines.pop()

    ind = child_indent(lines)
    actions = []
    try:
        for m in measures:
            name = m.get("name")
            if not name:
                raise ValueError("each measure needs a 'name'.")
            block = build_block(m, ind)
            found = find_measure(lines, name)
            mode = str(m.get("mode", "add")).lower()
            if found:
                start, end, ws = found
                block = build_block(m, ws)  # match the existing measure's indentation exactly
                lines[start:end] = block
                verb = "replace" if mode == "modify" else "replace (already existed)"
                actions.append((verb, name))
            else:
                pos = last_measure_end(lines)
                insert_at = pos if pos is not None else len(lines)
                lines[insert_at:insert_at] = [""] + block
                verb = "add" if mode == "add" else "add (was missing)"
                actions.append((verb, name))
    except ValueError as e:
        print(f"MEASURE ERROR (nothing written): {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Target: {tmdl}")
    for verb, name in actions:
        print(f"  {verb}: {name}")

    new_text = "\n".join(lines) + ("\n" if had_final_nl else "")

    if args.dry_run:
        print("\nDRY RUN: no file written.")
        return

    backup = tmdl + ".bak"
    shutil.copy2(tmdl, backup)
    with open(tmdl, "w", encoding="utf-8") as f:
        f.write(new_text)
    # round-trip read so we never leave a file we can't re-open
    with open(tmdl, encoding="utf-8") as f:
        f.read()

    # QA post-escritura (comillas impares / VAR huérfana / indentación). Si hay bloqueantes,
    # restaura el .bak: una medida rota bloquea TODO el modelo aunque "no se use".
    if not args.no_qa:
        qa = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dax_qa.py")
        if os.path.isfile(qa):
            r = subprocess.run([sys.executable, qa, "--tmdl", tmdl],
                               capture_output=True, text=True)
            if r.returncode != 0:
                shutil.copy2(backup, tmdl)
                print(r.stdout)
                print(f"\nQA FALLÓ → se restauró {backup}. No se aplicaron los cambios.",
                      file=sys.stderr)
                sys.exit(1)

    print(f"\nWrote {tmdl} ({len(actions)} measures). Backup: {backup}")
    print("QA OK (comillas/VARs/indentación). Next: re-run model_catalog.py, then Power BI Desktop.")


if __name__ == "__main__":
    main()
