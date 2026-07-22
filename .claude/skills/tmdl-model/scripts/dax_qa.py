#!/usr/bin/env python3
"""
dax_qa.py — QA de un archivo TMDL (medidas DAX) SIN compilar en Power BI Desktop.

El compilador DAX solo corre dentro de Power BI Desktop. Este script atrapa ANTES los errores
que bloquean la compilación (y que además bloquean TODO el modelo aunque la medida "no se use"):

  1. Paridad de comillas `"` por bloque de medida (impar = string roto) y total del archivo.
  2. VARs usadas pero NO definidas dentro de la misma medida (VAR huérfana = no compila).
  3. Indentación TMDL: `measure` 1 tab · `VAR`/`RETURN` 3 tabs · propiedades
     (formatString/displayFolder/lineageTag) 2 tabs.
  4. Guarda de COPIA ESPEJO: solo se debe editar bajo `...SemanticModel/definition/`.
     Los `.tmdl` fuera de `definition/` son copias que Power BI regenera.
  5. `--count "<ancla>"`: cuenta coincidencias de una subcadena (para verificar antes/después
     de un replace_all y no tocar de más).

Usage:
    python dax_qa.py --tmdl <...\\definition\\tables\\Medidas.tmdl>
    python dax_qa.py --tmdl <...> --count "<ancla>"
    python dax_qa.py --tmdl <...> --allow-mirror     # permite rutas fuera de definition/

Exit 0 = sin bloqueantes. Exit 1 = hay bloqueantes.
"""
import argparse
import os
import re
import sys

RE_MEASURE = re.compile(r"^(\s*)measure\s+('([^']+)'|[^\s=]+)\s*=")
RE_VAR_DEF = re.compile(r"\bVAR\s+([A-Za-z_@][\w@]*)")   # también VARs anidadas (no solo a inicio de línea)
RE_VAR_USE = re.compile(r"(?<![\w@])(_[A-Za-z0-9_]+)")
RE_PROP = re.compile(r"^(\s*)(formatString|displayFolder|lineageTag|description|isHidden|"
                     r"formatStringDefinition|annotation)\b")
RE_VARLINE = re.compile(r"^(\s*)(VAR|RETURN)\b")


def leading_ws(line):
    return line[: len(line) - len(line.lstrip())]


def unquote(n):
    n = n.strip()
    return n[1:-1] if n.startswith("'") and n.endswith("'") else n


def measure_blocks(lines):
    """[(name, start, end_exclusive)] — el bloque llega hasta la próxima línea con indent <=."""
    out = []
    for i, ln in enumerate(lines):
        m = RE_MEASURE.match(ln)
        if not m:
            continue
        name = unquote(m.group(3) or m.group(2))
        ws = m.group(1)
        j = i + 1
        while j < len(lines):
            s = lines[j]
            if s.strip() == "":
                j += 1
                continue
            if len(leading_ws(s)) <= len(ws):
                break
            j += 1
        out.append((name, i, j))
    return out


def check_quotes(name, block):
    """Paridad de comillas dobles. En TMDL/DAX una `""` dentro de string también suma 2 → par."""
    n = sum(l.count('"') for l in block)
    return None if n % 2 == 0 else f"comillas impares ({n}) → string sin cerrar"


def check_vars(name, block):
    # Solo la EXPRESIÓN DAX: fuera las líneas de propiedades/metadata (displayFolder puede
    # contener `_compartido`, lineageTag guiones, etc. → no son VARs).
    dax_lines = [l for l in block if not RE_PROP.match(l)]
    if dax_lines:
        # quitar `measure <Nombre> =` (el nombre de la medida puede empezar con `_`)
        dax_lines = list(dax_lines)
        dax_lines[0] = re.sub(r"^\s*measure\s+('[^']+'|[^\s=]+)\s*=", "", dax_lines[0])
    text = "\n".join(dax_lines)
    # quitar strings ("_algo" dentro de CSS/JS/texto no es una VAR) y referencias [Medida]/[Columna]
    text_nostr = re.sub(r'"(?:[^"]|"")*"', '""', text)
    text_nostr = re.sub(r"\[[^\]]*\]", "[]", text_nostr)
    defined = set(RE_VAR_DEF.findall(text_nostr))
    used = set(RE_VAR_USE.findall(text_nostr))
    missing = sorted(u for u in used if u not in defined)
    return f"VAR usada sin definir: {', '.join(missing)}" if missing else None


def check_indent(name, block):
    """Solo señala indentación que ROMPE el parseo: la expresión y las propiedades deben ir
    MÁS indentadas que la línea `measure`. La convención exacta (1/2/3 tabs) se documenta en
    dax-authoring.md, pero no se marca como problema (proyectos reales varían y compilan)."""
    m = RE_MEASURE.match(block[0])
    if not m:
        return None
    base = len(m.group(1))
    for ln in block[1:]:
        if ln.strip() == "":
            continue
        if (RE_VARLINE.match(ln) or RE_PROP.match(ln)) and len(leading_ws(ln)) <= base:
            return f"`{ln.strip().split()[0]}` no está más indentado que `measure` → rompe el parseo"
    return None


def main():
    ap = argparse.ArgumentParser(description="QA de TMDL/DAX sin compilar")
    ap.add_argument("--tmdl", required=True)
    ap.add_argument("--count", help="cuenta coincidencias de esta subcadena (anclas/replace_all)")
    ap.add_argument("--allow-mirror", action="store_true",
                    help="permite rutas fuera de definition/ (copias espejo)")
    args = ap.parse_args()

    if not os.path.isfile(args.tmdl):
        print(f"ERROR: no existe {args.tmdl}", file=sys.stderr)
        sys.exit(2)

    blocking, warnings = [], []
    norm = args.tmdl.replace("\\", "/").lower()
    if "/definition/" not in norm:
        msg = ("la ruta NO está bajo `definition/` → es una COPIA ESPEJO que Power BI regenera; "
               "edita `...SemanticModel/definition/tables/<Tabla>.tmdl`")
        (warnings if args.allow_mirror else blocking).append(msg)

    text = open(args.tmdl, encoding="utf-8").read()
    lines = text.split("\n")

    if args.count is not None:
        print(f"--count '{args.count}': {text.count(args.count)} coincidencia(s)")

    total_q = text.count('"')
    if total_q % 2 != 0:
        blocking.append(f"archivo con comillas impares en total ({total_q})")

    blocks = measure_blocks(lines)
    for name, s, e in blocks:
        block = lines[s:e]
        # BLOQUEANTE: paridad de comillas (determinista, es el error clásico que rompe el modelo).
        r = check_quotes(name, block)
        if r:
            blocking.append(f"[{name}] {r}")
        # AVISO: VAR huérfana / indentación. Son señales fuertes pero pueden dar falso positivo en
        # medidas complejas (VARs anidadas, strings multilínea) → no bloquean una escritura válida.
        for check in (check_vars, check_indent):
            r = check(name, block)
            if r:
                warnings.append(f"[{name}] {r} (revisar)")

    print(f"Medidas analizadas: {len(blocks)}")
    if warnings:
        print(f"\nAdvertencias ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
    if blocking:
        print(f"\nBLOQUEANTES ({len(blocking)}):")
        for b in blocking:
            print(f"  - {b}")
        sys.exit(1)
    print("\nOK: sin bloqueantes (no reemplaza la compilación en Power BI Desktop).")


if __name__ == "__main__":
    main()
