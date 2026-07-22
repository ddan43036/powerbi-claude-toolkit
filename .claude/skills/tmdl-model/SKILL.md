---
name: tmdl-model 
description: >-
  Usar para LEER y ANALIZAR el modelo semántico (capa de datos TMDL) de un proyecto PBIP con
  el fin de diseñar visuales: identificar tablas, columnas, medidas, relaciones, dimensiones y
  tablas de tiempo. Disparadores: "qué medidas/columnas hay", "analiza el modelo", "qué puedo
  graficar", "construye el catálogo". Para AUTORÍA de DAX/medidas, esta skill NO reemplaza las
  convenciones del equipo en `Medidas.tmdl` (ver CLAUDE.md): aquí el foco es el análisis de
  solo-lectura que alimenta el diseño del informe.
---

# Análisis del modelo TMDL (para diseñar visuales)

La capa de datos vive en `*.SemanticModel/definition/`:
`model.tmdl` (config global + lista de tablas), `database.tmdl`, `relationships.tmdl`,
`cultures/*.tmdl`, `tables/*.tmdl`. Las medidas DAX del equipo suelen estar todas en
`tables/Medidas.tmdl`.

## Construir el catálogo (paso 1, una sola vez)

```
python .claude/skills/report-json-visuals/scripts/model_catalog.py \
    "<ruta>\<Proyecto>.SemanticModel\definition" -o catalog.json
```

Produce un JSON compacto: `tables` (columnas + medidas por tabla), `measures_index`
(medida → tabla), `relationships` (con `isActive` y `crossFilteringBehavior`),
`auto_generated_tables` (las `LocalDateTable_*` a ignorar) y `table_roles` (rol por tabla).

## Clasificación para el diseño — dimensión vs hecho

`table_roles` ya viene calculado en el catálogo (heurística por cardinalidad de las relaciones):
- `measures` → tabla de medidas (sin columnas; normalmente `Medidas`).
- `dimension` → lado "uno"/lookup (toTable): categóricas filtrables → ejes de categoría, leyendas, slicers.
- `fact` → lado "muchos" (fromTable): transaccional → de aquí salen las medidas/agregaciones.
- `time` → calendario/fecha (año/mes/semana) → ejes temporales.
- `unknown` → sin relaciones; decídelo leyendo el TMDL puntualmente.

Reglas de cruce: respetar la dirección de filtro; **advertir** si un cruce propuesto no tiene
relación que lo soporte. Para la lectura: medidas en Valores (Y/KPIs/tarjetas), dimensiones en
categorías/leyendas, tiempo en el eje X.

## Proponer medidas (analista de datos senior) — sin escribir DAX

Cuando `intent.yaml measures.allow_new: true` o se pida:
- Propón **IDEAS de medidas accionables según el contexto** (audiencia/`purpose`/`emphasis`): qué
  decisión habilitan y de qué campos del catálogo dependen (p. ej. variación vs meta, YoY/MoM, %
  del total, deltas de ranking, medias móviles). No genéricas.
- **No escribas DAX aquí.** Flujo: proponer → el usuario aprueba → autoría DAX por las reglas
  internas del toolkit (`reference/dax-authoring.md`) → escritura mecánica con `apply_measures.py`
  (abajo) → re-correr `model_catalog.py` para refrescar el catálogo.
- También señala **mejoras** a medidas existentes (formato, claridad, performance) cuando aplique.

## Estrategia de traducción — medidas que retornan string

Una medida que retorna texto se usa como **título dinámico** de un gráfico/slicer (los títulos
nativos no admiten multiidioma). Viven en la subcarpeta `traduccion` de `Medidas`; el catálogo las
lista en `translation_measures`. El render del título dinámico va por la pista HTML/DAX.

**3 patrones de traducción** (el catálogo los detecta en `catalog.translation.strategy`):
- **A · Lookup (CdP):** tabla `dim_traduccion`(id_traduccion/id_idioma/texto_traducido) +
  `Idioma_Activo` + medidas por string (carpeta `traduccion`). Patrón canónico abajo.
- **B · Switch por idioma (GESPRO):** tabla de idiomas `TL__Idiomas[Sigla]` (PT/ES/EN) por slicer +
  medidas `SWITCH(SELECTEDVALUE(TL__Idiomas[Sigla]),"pt",..,"es",..,"en",..,default)` +
  **Field Parameters `TL_*`** que intercambian columnas por idioma (`dProjeto[Negócio (PT/ES/EN)]`,
  con columna `Idioma`) + diccionario `AuxTranslate` (ValorPT/ES/EN).
- **C · Metadata (Translations Builder):** tabla oculta `Localized Labels` con medidas placeholder
  cuyas captions se traducen por **cultura** → sigue el idioma del visor (no slicer).

**Patrón canónico (A)** (el agente escribe el DAX siguiéndolo; `apply_measures.py` lo guarda — el
analista NO lo escribe). Los nombres de tabla/columnas/medida y la carpeta salen de
`intent.yaml measures.i18n`:

```dax
<nombre_medida> =
    VAR Idioma = [<active_language_measure>]   -- ej. [Idioma_Activo]
    RETURN
    CALCULATE(
        MAX( '<table>'[<text_column>] ),       -- ej. 'dim_traduccion'[texto_traducido]
        REMOVEFILTERS( '<table>' ),
        TRIM( '<table>'[<id_column>] ) = "<ID_TRADUCCION>",   -- ej. "SLICER_1_CDP"
        TRIM( '<table>'[<lang_column>] ) = Idioma             -- ej. [id_idioma]
    )
```

Al crearlas, pasar `displayFolder` = la carpeta de traducción (default `traduccion`) en
`measures.json` para que queden en su subcarpeta.

## Clase de medida y formato (del catálogo)

El catálogo trae `html_measures` (medidas que retornan HTML: `M_HTML_*`, `Donut_*` — alimentan el
custom visual HTML Content), `translation_measures` (carpeta `traduccion`, títulos multiidioma) y
`measure_formats` (`formatString` por medida). **Enforcement de %**: una medida que parece
porcentaje (nombre con `%`/adherencia/cumplimiento) pero cuyo `formatString` no es de % se verá
como decimal (p. ej. `0,98`). Corrige el `formatString` en la medida (vía `apply_measures.py`),
no por visual — el preflight `intent_check.py` y `validate_report.py` lo marcan.

## Riesgos de performance del modelo

Señalar: columnas de alta cardinalidad, relaciones bidireccionales, columnas calculadas que
convendría como medida, y cruces sin relación. El objetivo es un tablero usable y rápido.

## Convenciones del modelo (de un proyecto real consolidado)

- **Editar SOLO bajo `definition/`**: lo de fuera (`.SemanticModel/tables/`, `model.tmdl` raíz) son
  **copias espejo que Power BI regenera**. `apply_measures.py`/`dax_qa.py` lo rechazan.
- **Métricas centralizadas**: una métrica usada en 2+ visuales se define **una vez**
  (`M_X_Tot`/`M_X_Cerr`/`M_X_Pct`, `-1` = sin datos) y se reúsa; no se recalcula por página.
- **Carpetas**: `displayFolder: responsabilidades/M_HTML_<Pagina>` (propio de una página) o
  `responsabilidades/_compartido` (reutilizado por 2+). Al reutilizarse, se **mueve**, no se duplica.
- **Trampas**: `ISFILTERED(hecho[col])` no detecta un slicer sobre la dimensión → usa
  `VALUES(dim[col])`; `SUMMARIZE(A, B[col])` exige relación formal A→B; `LOOKUPVALUE` en JSON con
  `FILTER` previo. Detalle en `reference/dax-authoring.md` y `reference/ESTRUCTURA-PBIP-Y-TRAMPAS.md`.

## QA antes de compilar — `dax_qa.py`

```
python .claude/skills/tmdl-model/scripts/dax_qa.py --tmdl "<...>\definition\tables\Medidas.tmdl"
python ... dax_qa.py --tmdl <...> --count "<ancla>"    # verificar un replace_all
```
Atrapa **comillas impares**, **VAR usada sin definir** (bloquea todo el modelo), **indentación TMDL**
y **copias espejo**. No reemplaza la compilación en Desktop, pero evita el 90% de los bloqueos.

## Escribir medidas aprobadas — `apply_measures.py` (mutador seguro)

```
python .claude/skills/tmdl-model/scripts/apply_measures.py \
    --tmdl "<...>\tables\Medidas.tmdl" --measures measures.json [--dry-run]
```

`measures.json`: `{ "table":"Medidas", "measures":[ { name, expression, formatString?,
displayFolder?, description?, mode:"add"|"modify" } ] }`. El script **no inventa DAX**: escribe la
`expression` aprobada con la indentación TMDL correcta (igual que `insert_visuals.py` para
report.json). Crea `.bak`, soporta `--dry-run`, y es UPSERT. SOLO tras aprobación humana. Nunca
carga el `.tmdl` al contexto.

## Reglas de tokens

- Construir el catálogo una vez y reutilizarlo; no releer los `.tmdl` repetidamente.
- Para detalles puntuales (p. ej. la definición DAX de una medida) usar `Grep` por el nombre
  de la medida y `Read` con offset+limit sobre `Medidas.tmdl`. Nunca volcar el archivo entero.
- Ignorar `LocalDateTable_*`, `DateTableTemplate_*` y `cache.abf`.

## Frontera

- **Análisis: solo-lectura.** Construir catálogo, clasificar y proponer no toca el proyecto.
- **Escritura de medidas: solo vía `apply_measures.py`, tras aprobación.** El DAX se autora con las
  reglas INTERNAS del toolkit en **`reference/dax-authoring.md`** (comillas en tablas acentuadas,
  string vacío `_e`, `!important` en VAR, hex con alfa, comillas dobles `""`, límite de PLACEHOLDER)
  — el script solo hace la mutación segura del archivo, no inventa DAX. Para HTML-en-DAX ver
  `report-json-visuals/reference/html-in-dax.md`.
- No editar la capa de informe desde aquí (eso es la skill `report-json-visuals`).
