# Compilación de errores DAX/TMDL — VPOI · GESPRO

Registro de errores reales de compilación encontrados al autoría de medidas (TMDL/DAX),
con **causa raíz, corrección y regla generalizable**. Las reglas vivas del toolkit (autocontenido)
están en `.claude/skills/tmdl-model/reference/dax-authoring.md` (DAX) y
`.claude/skills/report-json-visuals/reference/html-in-dax.md` (HTML-en-DAX); este archivo es el
**log de casos** que las alimenta. Formato fijo por entrada para ir agregando casos.

> Convención: cada entrada documenta 1 error. Mantener el bloque **Regla para agentes**
> conciso y accionable: es lo que se inyecta al reentrenamiento.

---

## ERR-001 · Nombre de tabla con acento sin comillas simples → "token no válido"

**Fecha:** 2026-06-20
**Medida:** `Medidas.M_JSON_Resumo_Executivo`
**Severidad:** Bloqueante (no compila)

### Mensaje exacto
```
Error de sintaxis durante el análisis: token no válido, línea 13, desplazamiento 58 y á.
```

### Código que falló (fragmento)
```dax
VAR _mesT =
    ADDCOLUMNS(
        SUMMARIZE(fRetornoProjeto, dCalendário[Mês/Ano], dCalendário[IDX_MesAno]),
        "@v", [RF - Ganho Obtido]
    )
```

### Diagnóstico
- `línea 13` / `desplazamiento 58` se cuentan sobre las **líneas de la EXPRESIÓN DAX**
  (no las del archivo `.tmdl`): se cuenta desde la primera línea de contenido dentro del
  bloque ` ``` `. La línea 13 de la expresión es la del `VAR _mesT`.
- El offset 58 cae exactamente sobre la **`á` de `dCalendário`**:
  `…SUMMARIZE(fRetornoProjeto, dCalendário[…` → posición 58 = `á`.
- El parser avanzó sin problema por las líneas 1–12 porque ahí **todos los acentos
  estaban dentro de `[corchetes]`** (columnas/medidas: `[Gerência]`, `[Plano de Ação …]`)
  **o dentro de cadenas `"…"`**. Reventó en el **primer nombre de TABLA acentuado sin
  comillas**.

### Causa raíz
DAX exige **comillas simples** alrededor de un nombre de **tabla** que contenga caracteres
fuera de `[A-Za-z0-9_]` (espacios, acentos `á ã é í ó ú ê ô ç ñ …`, `/`, etc.) o que empiece
por dígito. `dCalendário` lleva `á` → debe escribirse `'dCalendário'`.

Verificación contra la convención del propio modelo (decisivo):
```
'dCalendário'[  → 111 usos en medidas existentes   (correcto)
dCalendário[    →   4 usos                          (TODOS de la medida nueva = el bug)
```
El modelo ya tenía la convención; la medida nueva no la siguió.

### Corrección aplicada
Envolver el nombre de tabla acentuado en comillas simples (4 ocurrencias):
```dax
-- MAL
SUMMARIZE(fRetornoProjeto, dCalendário[Mês/Ano], dCalendário[IDX_MesAno])
-- BIEN
SUMMARIZE(fRetornoProjeto, 'dCalendário'[Mês/Ano], 'dCalendário'[IDX_MesAno])
```

### Regla para agentes (generalizable)
> **Siempre poner comillas simples en nombres de tabla con caracteres no-ASCII o especiales.**
> - Acentos/espacios/`/`/inicio numérico en el **nombre de tabla** ⇒ `'Tabla'[Columna]`.
> - Las **columnas y medidas van entre `[ ]`**, que ya admiten cualquier carácter ⇒ los
>   acentos DENTRO de corchetes NO necesitan nada extra: `tabla[Gerência]`, `[Plano de Ação]`.
> - Las **cadenas `"…"`** admiten cualquier carácter ⇒ acentos en texto/HTML/JSON son seguros.
> - El peligro está **solo** en el nombre de tabla "desnudo" (fuera de `[ ]` y de `"…"`).
> - **Antes de escribir referencias, igualar la convención del modelo**: `grep` del nombre
>   de la tabla en los `.tmdl` y copiar exactamente cómo ya se cita (quoted vs unquoted).
> - Por defecto, **citar siempre** las tablas `dCalendário`, `dProjeto`† y cualquier `d*/f*/TL_*`
>   que tenga acentos. (†`dProjeto` no lleva acento → opcional, pero citar no rompe nada.)

### Técnica de diagnóstico para "línea N, desplazamiento M"
1. `N` = línea dentro de la **expresión** (contar desde la 1.ª línea tras ` = ``` `).
2. `M` = columna/char en esa línea (los tabs de indentación pueden o no contar según el editor;
   localizar el token contando caracteres visibles del contenido).
3. El carácter citado al final del mensaje (aquí `á`) es el **token ofensivo** → buscar ese
   carácter en esa posición; casi siempre es un identificador que requiere `' '` o `[ ]`.

### Preflight para evitarlo (grep)
Detecta nombres de tabla acentuados SIN comillas simples antes de compilar:
```bash
# marca posibles tablas acentuadas sin comillar (revisar manualmente los hits)
grep -nE "[ (,]d[A-Za-z]*[À-ÿ][A-Za-z]*\[" Medidas.tmdl
# contraste con la convención existente del modelo
grep -oE "'?dCalendário'?\[" Medidas.tmdl | sort | uniq -c
```

### Relación con las reglas internas
Es la regla **R1** de `tmdl-model/reference/dax-authoring.md` (comillas simples en nombres de tabla
no-ASCII/acentuados), junto con R2–R6 (strings vacíos `_e`, `!important` en VAR, hex con alfa,
comillas dobles `""`, límite de PLACEHOLDER).

---

## ERR-002 · Visual "HTML Content" no ejecuta el `<script>` (variante/rol incorrectos)

**Fecha:** 2026-06-20
**Objeto:** Visual HTML en página `test_html` enlazado a `Medidas.M_HTML_Resumo_Executivo`
**Severidad:** Bloqueante funcional (compila, pero el panel sale en blanco)

### Síntoma
El contenedor HTML **sí pinta el HTML/CSS estático** (hero, barra de gradiente, cards vacías,
badge "EN VIVO"), pero **no aparece nada generado por JavaScript**: sin título, sin cards KPI
pobladas, sin gráficos Canvas, sin tabla. Es decir, el `<script>` **no se ejecuta**.

### Diagnóstico
Comparado contra el proyecto de referencia que SÍ funciona
(`…\PruebasPbip\Archivos tablero CdP`), que usa el mismo custom visual:
- Existen **dos variantes** del visual "HTML Content" registradas:
  - `htmlContent443BE3AD55E043BF878BED274D3A6865` → usado **solo** para HTML/SVG **estático**
    (donuts/gauges SVG, textos de traducción). **No ejecuta `<script>`.**
  - `htmlContent443BE3AD55E043BF878BED274D3A6855` → usado para las medidas con **lógica JS real**
    (`html_final_consolidado`, `M_HTML_Salud_Estandares`, que contienen `<script>`). **Ejecuta JS.**
- El **rol de datos** del visual es **`content`** (la medida se proyecta en `queryState.content`),
  no `values`.

Causa del fallo: la página `test_html` se había construido con la variante `…6865` (estática)
y el rol `values`. Por eso renderizaba el HTML pero ignoraba el `<script>`.

### Corrección aplicada
En `…/pages/test_html/visuals/<id>/visual.json`:
```jsonc
// MAL
"visualType": "htmlContent443BE3AD55E043BF878BED274D3A6865",
"query": { "queryState": { "values":  { "projections": [ … ] } } }
// BIEN
"visualType": "htmlContent443BE3AD55E043BF878BED274D3A6855",
"query": { "queryState": { "content": { "projections": [ … ] } } }
```
Y en `report.json` → `publicCustomVisuals`: registrar también `…6855` (dejar ambas variantes).

### Regla para agentes (generalizable)
> **Elegir la variante correcta del visual "HTML Content" según si hay `<script>`:**
> - Medida que **ejecuta JavaScript** (`<script>`, Canvas, Chart.js, listeners) ⇒
>   `htmlContent443BE3AD55E043BF878BED274D3A6855`.
> - Medida **estática** (HTML/CSS/SVG server-rendered por DAX, sin JS) ⇒
>   `htmlContent443BE3AD55E043BF878BED274D3A6865`.
> - **Rol de datos = `content`** (PBIR: `query.queryState.content.projections`;
>   legacy: `singleVisual.projections.content`). **No** `values`.
> - Registrar el GUID usado en `report.json → publicCustomVisuals`.
> - **Síntoma diagnóstico:** si el HTML/CSS pinta pero el JS no corre ⇒ variante de visual
>   equivocada (estás en `…6865`) **antes** de sospechar del JS.
> - **Validación cruzada:** ante un proyecto HTML nuevo, inspeccionar un proyecto hermano que
>   ya funcione (`grep` de `visualType`/`projections` en su `report.json`) y **copiar la variante,
>   el rol y la convención exactas**.

### Técnica de inspección usada (reutilizable)
```python
# parsear report.json legacy y listar visualType + rol + queryRef de los visuales HTML
import json
rep=json.load(open("report.json",encoding="utf-8"))
for sec in rep["sections"]:
    for vc in sec["visualContainers"]:
        sv=json.loads(vc["config"])["singleVisual"]
        if "html" in sv["visualType"].lower():
            print(sv["visualType"], list(sv["projections"].keys()),
                  [i["queryRef"] for r in sv["projections"].values() for i in r])
```

---

## PAT-001 · Separación de responsabilidades CSS / JS / HTML / JSON en medidas aparte

**Tipo:** Patrón obligatorio de arquitectura (no es un error; es la forma correcta de construir).
**Origen:** Proyecto de referencia que funciona — `…\PruebasPbip\Archivos tablero CdP`
(`M_CSS_Tablero`, `M_HTML_Tablero`, `M_JS_Tablero`, `html_final_consolidado`).

### Regla
> **Nunca** poner CSS + HTML + JS + datos en una sola medida gigante. **Siempre** separar en
> medidas con **una responsabilidad cada una**, y una medida **consolidadora** que ensambla el
> documento final. El visual HTML Content consume **solo la consolidadora**.

### Estructura canónica (aplicada en GESPRO · Resumo Executivo)
| Medida | Responsabilidad | Notas |
|---|---|---|
| `M_JSON_<Panel>`     | Serializa los datos → string JSON | `CONCATENATEX`+`SUMMARIZE`; respeta slicers |
| `M_CSS_<Panel>`      | Solo `<style>…</style>` | medida de una línea |
| `M_JS_<Panel>`       | Solo `<script>…</script>` (i18n, Canvas, tabla) | VARs `_js1.._jsN` → `RETURN _js1 & …` |
| `M_HTMLBody_<Panel>` | Fragmento HTML + inyección `var gData = [M_JSON_<Panel>]` | `RETURN _html & "<script>var gData=" & _json & ";</script>"` |
| `M_HTML_<Panel>`     | **CONSOLIDADORA**: `<!DOCTYPE>` + `[M_CSS]` + `</head><body>` + `[M_HTMLBody]` + `[M_JS]` + `</body></html>` | **es la que el visual enlaza** |

Equivalencia con CdP: `M_HTML_<Panel>` ≙ `html_final_consolidado`; `M_HTMLBody_<Panel>` ≙ `M_HTML_Tablero`.

### Por qué (motivos concretos)
1. **Límite de literales del parser DAX** (error real en CdP:
   *"La función 'PLACEHOLDER' encontró una cadena de texto que supera la longitud máxima"*).
   El presupuesto de literales se **suma en todo el call graph** de la consolidadora. Trocear
   CSS/JS/HTML en medidas distintas reparte ese presupuesto y evita el desborde.
2. **Mantenibilidad / edición aislada:** un agente puede tocar el CSS sin arriesgar el JS, etc.
3. **Depuración por capas:** validar `M_JSON` en una Tarjeta antes de mirar el HTML; aislar si
   el fallo es de datos, de estilo o de lógica.
4. **Reutilización:** `M_JSON` y `M_CSS` pueden alimentar varios paneles.

### Cuidado de presupuesto (regla fina heredada de CdP)
> Si `M_JSON_<Panel>` usa `CONCATENATEX` sobre tablas grandes y la consolidadora **se acerca al
> límite**, NO referenciar `M_JSON` desde la cadena consolidada: inyectarlo en una medida
> standalone separada. En GESPRO el JSON es pequeño (Top-15 + pocos grupos) → se referencia sin
> problema vía `M_HTMLBody`.

### Regla para agentes (generalizable)
> Al construir un panel HTML en DAX: crear **5 medidas** (`M_JSON_`, `M_CSS_`, `M_JS_`,
> `M_HTMLBody_`, `M_HTML_` consolidadora). El visual enlaza **siempre** a la consolidadora
> `M_HTML_*`. Mantener la consolidadora con **pocos literales** (solo etiquetas wrapper +
> referencias `[ ]` a las otras medidas). Combinar con ERR-002: la consolidadora va al visual
> `…6855` (ejecuta JS), rol `content`.

---

## DIF-GUIA-001 · Diferencias entre `GUIA_Tablero_HTML_DAX.md` y nuestra implementación

**Fecha:** 2026-06-20 · **Alcance:** panel `Resumo Executivo` (medidas `*_Resumo_Executivo`) vs. la guía.
**Para reentrenar:** registrar qué hicimos IGUAL, qué CORREGIMOS para alinear, y qué dejamos
DISTINTO a propósito (con su razón). Estado: ✅ alineado · 🔧 corregido para alinear · ➖ divergencia intencional.

| # | Tema (ref guía) | Lo que dice la guía | Lo que hicimos | Estado |
|---|---|---|---|---|
| 1 | Separación CSS/HTML/JS/JSON + consolidadora (§1) | 5 medidas, el visual usa solo la consolidadora | `M_JSON/M_CSS/M_JS/M_HTMLBody/M_HTML` (consolidadora) | ✅ (ver PAT-001) |
| 2 | **`esc()` sobre datos** (§5, §7) | Escapar `& < >` de los datos antes de `innerHTML` | Faltaba → **agregado** `esc()` y aplicado a título/status/gerência y pills de la tabla | 🔧 |
| 3 | **Inyección del JSON antes del JS, en el consolidado** (§2) | `… & _HTML & [M_JSON] & _JS & …` | Estaba dentro de `M_HTMLBody` → **movido** al consolidado `… & [M_HTMLBody] & "<script>var gData=" & _json & ";</script>" & [M_JS] …` | 🔧 |
| 4 | **Guardas en el JS** `if(!destino)return;` (§5, §12) | Cada render valida que exista su destino | Faltaba → **agregado** a `kpi/donut/barsH/cols/rTbl` | 🔧 |
| 5 | `M_JSON_*` devuelve `<script>var X=[…]</script>` (§3) | La medida JSON ya viene envuelta en `<script>` | Nuestra `M_JSON` devuelve **JSON crudo** `{…}`; lo envolvemos en el consolidado | ➖ (crudo = validable en una Tarjeta; mismo resultado) |
| 6 | `VAR _e=""` siempre (§6) | Declarar `_e` y nunca `""` literal en `IF` | `M_JSON` **no** declara `_e` porque no hay ramas `IF` con `""` (regla satisfecha de forma vacía) | ➖ |
| 7 | i18n con un único `Idioma_Activo` (§9) | Una medida driver del idioma | Resolvemos el idioma **inline** en `M_JSON` (`COALESCE(SELECTEDVALUE(TL__Idiomas[Sigla]),"pt")`) — único punto | ➖ |
| 8 | Backup `html_tablero_final` standalone (§1) | Copia standalone de respaldo | **No** la creamos (opcional) | ➖ |
| 9 | JSON pesado → visual dedicado (§8) | No referenciar JSON grande desde el consolidado | Nuestro JSON es chico (Top-15 + pocos grupos) → va en el consolidado sin riesgo | ✅ (n/a por tamaño) |
| 10 | Entidades HTML para acentos (§7) | `&mdash;`, `&aacute;`, etc. | Usamos **UTF-8 crudo** + `<meta charset='UTF-8'>` | ➖ (ambos válidos) |
| 11 | Filtrado: evitar `ALL`; unidireccional → `ISFILTERED`+`IN VALUES` (§10) | Respeta contexto; patrón para relaciones unidireccionales | `M_JSON` usa `SUMMARIZE/ADDCOLUMNS` **sin `ALL`** (respeta slicers). **No** aplicamos `ISFILTERED`+`IN VALUES` | ⚠️ a verificar en Desktop (si un slicer no filtra como se espera, aplicar §10) |
| 12 | `syncGroup` único por slicer (§13) | No repetir `groupName` por error | Solo el slicer **Idioma** tiene `syncGroup:"Idioma"`; los demás ninguno | ✅ |
| 13 | Render por `innerHTML` (tablas/tarjetas) (§4-5) | Ejemplos arman tablas con `innerHTML` | Tabla por `innerHTML` (con `esc`), pero **charts en Canvas** (donut/barras/colunas) | ➖ (Canvas es robusto; su `fillText` no necesita `esc`) |

### Reglas para agentes (derivadas)
> - **Aplicar `esc()` SIEMPRE** a cualquier dato del modelo que entre por `innerHTML`
>   (título, status, gerencia, celdas). El texto dibujado en **Canvas** (`fillText`) **no** lo necesita.
> - **Inyectar el JSON en la consolidadora, inmediatamente antes del `<script>` del JS**
>   (no en el fragmento HTML), calcando `… & [HTMLBody] & "<script>var gData=" & _json & ";</script>" & [JS] …`.
> - **Toda función de render lleva guarda** `if(!destino)return;` antes de tocar el DOM/Canvas.
> - Divergencias aceptables y por qué: `M_JSON` crudo (validable), idioma inline (1 punto),
>   Canvas en vez de innerHTML para gráficos, UTF-8 en vez de entidades. Documentarlas, no "corregirlas".
> - Pendiente de verificación: filtrado de slicers sobre dimensiones con relación unidireccional
>   (guía §10) — si falla, aplicar `ISFILTERED`+`IN VALUES`.

---

## Plantilla para nuevas entradas

```
## ERR-00X · <título corto>
**Fecha:** YYYY-MM-DD  ·  **Medida/Objeto:**  ·  **Severidad:**
### Mensaje exacto
### Código que falló
### Diagnóstico
### Causa raíz
### Corrección aplicada
### Regla para agentes (generalizable)
```
