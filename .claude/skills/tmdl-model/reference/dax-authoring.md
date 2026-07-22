# Autoría de medidas DAX (reglas internas del toolkit)

Reglas INVIOLABLES para escribir/editar medidas en `*.tmdl` (capa de datos). Autocontenido: el
toolkit NO depende de skills externas. El analista PROPONE; el DAX se escribe siguiendo esto y se
aplica con `apply_measures.py` (backup + dry-run + **QA automático**). Errores reales que motivan
estas reglas: ver `ERRORES-COMPILACION-DAX.md` y la estructura/trampas del proyecto real en
`ESTRUCTURA-PBIP-Y-TRAMPAS.md` (este mismo folder). HTML-en-DAX:
`../../report-json-visuals/reference/html-in-dax.md`.

## R0 — Editar SOLO bajo `definition/` (copias espejo)
El modelo vive en `...SemanticModel/definition/` (`model.tmdl`, `relationships.tmdl`,
`tables/<Tabla>.tmdl`). Lo que hay **fuera** de `definition/` (p. ej. `.SemanticModel/tables/`) son
**copias espejo que Power BI regenera**: editarlas pierde el cambio. `apply_measures.py` y
`dax_qa.py` **rechazan** rutas fuera de `definition/` (override: `--allow-mirror`).

## R0b — Formato TMDL de una medida
```
	measure NombreMedida = SUM(Tabla[col])          ← 1 tab
		formatString: 0                              ← 2 tabs (props)
		displayFolder: responsabilidades/_compartido
```
Multilínea con backticks y **3 tabs** para `VAR`/`RETURN`:
```
	measure Nombre = ```
			VAR _e = ""
			VAR _x = CALCULATE(COUNTROWS(tabla))
			RETURN _x
			```
		formatString: 0
```
Una indentación mal puesta rompe el parseo. `dax_qa.py` lo verifica.

## R0c — QA ANTES de compilar (no se compila fuera de Desktop)
```
python .claude/skills/tmdl-model/scripts/dax_qa.py --tmdl "<...>\definition\tables\Medidas.tmdl"
python ... dax_qa.py --tmdl <...> --count "<ancla>"     # verificar antes/después de un replace_all
```
Detecta: **comillas impares** (string roto), **VAR usada sin definir** (bloquea TODO el modelo
aunque la medida "no se use"), **indentación**, y la **copia espejo**.

## R1 — Comillas simples en nombres de TABLA no-ASCII/especiales  (ERR-001)
DAX exige `'comillas simples'` alrededor de un nombre de **tabla** que tenga acentos
(`á ã é í ó ú ê ô ç ñ …`), espacios, `/`, o que empiece por dígito.
```dax
-- MAL:  SUMMARIZE(fRetornoProjeto, dCalendário[Mês/Ano], ...)
-- BIEN: SUMMARIZE(fRetornoProjeto, 'dCalendário'[Mês/Ano], ...)
```
- **Columnas y medidas van en `[ ]`** → admiten cualquier carácter sin nada extra: `tabla[Gerência]`, `[Plano de Ação]`.
- **Cadenas `"…"`** admiten cualquier carácter (texto/HTML/JSON seguro).
- El peligro es **solo** el nombre de tabla "desnudo" (fuera de `[ ]` y de `"…"`).
- **Antes de escribir, iguala la convención del modelo:** `grep` del nombre de la tabla en los
  `.tmdl` y copia cómo ya se cita. Por defecto, **citar siempre** `'dCalendário'`, `d*/f*/TL_*` con acentos.
- Diagnóstico "línea N, desplazamiento M": N se cuenta desde la 1.ª línea de la EXPRESIÓN (tras `= ```\``);
  el carácter citado al final (p. ej. `á`) es el token ofensivo → casi siempre tabla sin `' '`.

## R2 — String vacío como VAR, no `""` literal en ramas
Declarar `VAR _e = ""` y usar `_e` en las ramas de `IF/SWITCH`; evita el bug del parser con cadenas
vacías literales. (Si no hay ramas con `""`, la regla se cumple de forma vacía.)

## R3 — `!important` (CSS dentro de DAX) vía VAR
No incrustar `!important` como literal suelto problemático; construirlo en una VAR y concatenar.

## R4 — Color: hex con alfa, NO `rgba()`
En CSS/HTML generado por DAX usar hex de 8 dígitos `#RRGGBBAA` (no `rgba(...)`). (En visuales
NATIVOS el literal de color es hex de 6 dígitos `#RRGGBB`.)

## R5 — Escape de comillas con comillas dobles `""`
Dentro de una cadena DAX, una comilla doble se escapa duplicándola: `"el ""valor"" x"`.

## R6 — Límite de literales (PLACEHOLDER) → trocear
El parser DAX limita la longitud total de literales **sumada en todo el call graph** de una medida
(error real: *"La función 'PLACEHOLDER' encontró una cadena de texto que supera la longitud máxima"*).
Para HTML/CSS/JS grandes: **trocear en varias medidas** y consolidar (ver
`../../report-json-visuals/reference/html-in-dax.md`).

## R7 — Métricas escalares centralizadas (§14 de la guía HTML)
Si una métrica aparece en varios visuales/páginas, **defínela UNA vez** y reúsala (no la recalcules
en cada HTML): convención `M_X_Tot` / `M_X_Cerr|Cub` (conteos) + `M_X_Pct` (%), con **`-1` = "sin
datos"** que el HTML/JS traduce a "S/D". Así los visuales quedan sincronizados por construcción.

## R8 — Organización por carpetas (§20)
`displayFolder: responsabilidades/M_HTML_<Pagina>` para lo propio de una página;
`responsabilidades/_compartido` para lo reutilizado por 2+ páginas (métricas centralizadas,
componentes, `Idioma_Activo`). Una medida usada por 2+ HTML se **mueve** a `_compartido`, no se duplica.

## R9 — Trampas de filtrado y performance
- **Selección de un slicer que vive en una dimensión** (§16): `ISFILTERED(hecho[col])` es FALSO;
  usa `VALUES(dim[col])` (1 fila = selección única) para detectar la selección.
- **`SUMMARIZE(tablaA, tablaB[col])`** requiere relación formal muchos→uno de A hacia B; sin
  relación, usa `SUMMARIZE(tablaB, tablaB[col])` (el contexto filtra igual).
- **`LOOKUPVALUE` en `M_JSON_*`** (§19): `FILTER` primero y busca después; guarda de blanco
  (`IF(ISBLANK(_x), _x, COALESCE(IFERROR(LOOKUPVALUE(…),BLANK()), …))`). Cada lookup multiplica por filas.

## Flujo de escritura
1. Proponer (analista) → aprobar (Portón A).
2. Escribir el DAX siguiendo R1–R6 → `measures.json`.
3. `apply_measures.py --tmdl <Medidas.tmdl> --measures measures.json` (backup + `--dry-run`).
4. Re-correr `model_catalog.py` para refrescar `catalog.json`.

## Preflight rápido (grep)
```bash
# tablas acentuadas SIN comillas simples (revisar hits)
grep -nE "[ (,]d[A-Za-z]*[À-ÿ][A-Za-z]*\[" Medidas.tmdl
# contraste con la convención del modelo
grep -oE "'?dCalendário'?\[" Medidas.tmdl | sort | uniq -c
```
