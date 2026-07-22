# HTML-en-DAX (patrón interno del toolkit)

Cómo construir tableros/tarjetas HTML alimentados por medidas DAX y renderizados con el custom
visual **"HTML Content"**, con **slicers nativos**. Autocontenido: no depende de skills externas.

> **Documento canónico (léelo): `GUIA_Tablero_HTML_DAX.md` §1–26** (este mismo folder) —
> arquitectura completa: el diseño/colores cambian por proyecto, la **estructura de medidas y el
> flujo de datos NO**. Casos de compilación: `../../tmdl-model/reference/ERRORES-COMPILACION-DAX.md`;
> estructura PBIP y trampas: `../../tmdl-model/reference/ESTRUCTURA-PBIP-Y-TRAMPAS.md`; reglas DAX:
> `../../tmdl-model/reference/dax-authoring.md`. Este archivo = resumen + integración con el toolkit.

## 1) Una medida = una responsabilidad (split + consolidadora)
NUNCA CSS+HTML+JS+datos en una sola medida (revienta el límite de literales: error `PLACEHOLDER`).
Separar; cada medida tiene su propio presupuesto de literales y las referencias `[ ]` no suman.

| Medida (naming guía) | Responsabilidad | Equivalente `_<Panel>` |
|---|---|---|
| `M_CSS_Tablero`  | Solo `<style>` (colores/fuentes/tamaños) — lo único que tocas para la estética | `M_CSS_<Panel>` |
| `M_HTML_Tablero` | Estructura: `<div>`/tarjetas/tablas **con `id=`** (contrato con el JS), sin lógica | `M_HTMLBody_<Panel>` |
| `M_JS_Tablero`   | `<script>`: lee `window.*`, filtra, calcula, escribe en los `id` | `M_JS_<Panel>` |
| `M_JSON_*`       | Serializa datos del modelo → `<script>var _X=[…]</script>` | `M_JSON_<Panel>` |
| `html_final_consolidado` | **Ensamblaje** `CSS + HTML(+JSON) + JS`. **Es la que va al visual.** Sin lógica ni literales pesados | `M_HTML_<Panel>` |

Usa el naming que ya exista en el proyecto (grep primero, como en `dax-authoring.md` R1). Opcional:
`html_tablero_final` standalone como respaldo (no se usa en el informe).

## 2) Flujo y orden de inyección (crítico)
El `<script>var _X=…>` de `M_JSON` debe ir **antes** del `<script>` de `M_JS` (el JS lee `window._X`
al ejecutar):
```
RETURN "…<body>" & _HTML & [M_JSON_*] & _JS & "</body></html>"
                           └ define _X ┘  └ lo usa ┘
```
**JSON pesado:** si la tabla es grande, NO lo referencies desde el consolidado → ponlo en una medida
**autocontenida** en un **visual dedicado** (su call graph es chico y no toca el límite).

## 3) `M_JSON_*` (datos → JSON) — saneo
- Texto: `SUBSTITUTE(texto, """", "'")` (las `"` rompen el JSON). Comillas dobles en DAX se duplican.
- Números sin miles, punto decimal: `SUBSTITUTE(FORMAT(v,"0.00"), ",", ".")`.
- Fechas: `FORMAT(col,"yyyy-MM-dd")`. Tablas enormes → `TOPN`.
- Itera con `SUMMARIZE/ADDCOLUMNS` **sin `ALL`** (respeta slicers nativos).

## 4) `M_HTML_*` y `M_JS_*` — comillas y esc()
- Atributos HTML con comillas simples `'`; los que llevan **espacios** (`class=""a b""`) van con
  comillas dobles **duplicadas** en DAX; truco: define **una sola clase** para evitar comillas.
- Cada dato dinámico = un `id` en el HTML que el JS rellena; toda función de render lleva guarda
  `var d=g('id'); if(!d) return;`.
- `esc()` (escapa `& < >`) **solo a datos del usuario**. Entidades/etiquetas fijas (`&mdash;`,
  `&aacute;`) **sin** `esc()`: usar `(esc(dato)||'&mdash;')`, no `esc(dato||'&mdash;')`.

## 5) Variante del visual "HTML Content"  (ERR-002)
- **Ejecuta JS** (`<script>`/Canvas/Chart.js) → `htmlContent443BE3AD55E043BF878BED274D3A6855`.
- **HTML/CSS/SVG estático** (sin JS) → `htmlContent443BE3AD55E043BF878BED274D3A6865`.
- **Rol de datos = `content`** (NO `values`). **Registrar el GUID** en `report.json → publicCustomVisuals`
  (`insert_visuals.py` lo hace al insertar `render:"html-visual"`).
- Diagnóstico: si el HTML/CSS pinta pero el JS no corre → estás en `…6865`; cambia a `…6855`.

## 5b) Layout fijo 16:9 — scroll SOLO en la tabla (§22)
El visual *HTML Content* inyecta tu HTML en un **div anfitrión de alto fijo con scroll propio**:
`overflow:hidden` en `body` **no basta**. Acota **TU elemento raíz**:
```css
.app{height:100vh;max-height:100vh;overflow:hidden;display:flex;flex-direction:column}
.bd{flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column}
.tw{flex:1;min-height:0;overflow:auto}   /* ÚNICO scroll */
```
Cada nivel intermedio necesita `min-height:0`. Si `100vh` no mapea, fija píxeles
(`height:622px` para un visual de 638). Pon el *shell* en el **CSS compartido** → todas las páginas
al mismo tamaño (p. ej. **1278×638**). Síntoma del bug: "scrollea toda la hoja" = scrollea el
anfitrión, no la tabla.

## 5c) Dividir una medida HTML grande (§23) y copia gemela (§15)
- Dividir = varias medidas HTML que **comparten `M_CSS_Tablero`**; corta por **anclas HTML únicas**;
  las VARs que queden sin usar son inofensivas (DAX no evalúa VARs no usadas).
- Si existe una **copia gemela standalone** (`html_tablero_final`), un `replace_all` golpea **ambas**:
  toda VAR/medida referenciada debe existir en las dos, o edita solo la activa con ancla única.
  **La copia debe compilar aunque no se use** (si no, bloquea todo el modelo).

## 5d) Organización y métricas (§20, §14)
Medidas bajo `responsabilidades/M_HTML_<Pagina>`; lo reutilizado en `responsabilidades/_compartido`.
Métricas repetidas → **una sola medida escalar** (`M_X_Pct`, `-1` = S/D) consumida por todas las páginas.

## 6) Traducción y filtrado nativo
- Driver único `Idioma_Activo = COALESCE(SELECTEDVALUE(TablaIdiomas[id_idioma]),"es")` (o el patrón
  switch del proyecto); etiquetas condicionadas al idioma, en HTML y JS.
- El visual HTML se filtra porque la medida **se recalcula en el contexto de filtro** (slicers
  nativos). No usar `ALL`; relación unidireccional → `ISFILTERED` + `IN VALUES`.

## 7) Integración con el toolkit
- `intent.yaml`/`plan.json`: visual `render:"html-visual"`, `customVisual:"…6855"` (o `…6865` estático),
  `measure:"Medidas.html_final_consolidado"` (la consolidadora), rol `content`.
- Crear las medidas con `apply_measures.py` (Portón A) respetando `../../tmdl-model/reference/dax-authoring.md`.
- Solo formato `report.json`; si el informe está en carpeta-por-visual, implementar en Desktop con este patrón.

## Checklist (de la guía §12)
CSS/HTML/JS/JSON en medidas separadas · consolidadora solo ensambla · JSON pesado en visual dedicado ·
`var _e=""` (sin `""` en ramas) · `!important` como VAR · `rgba()`→hex con alfa · comillas dobles
duplicadas · `<script>` del JSON antes del JS · `esc()` solo a datos · cada dato dinámico con su `id`
+ guarda `if(!d)return;` · un único `Idioma_Activo` · sin `ALL` innecesario · probar en Desktop.
