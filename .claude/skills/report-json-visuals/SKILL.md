---
name: report-json-visuals
description: >-
  Usar SIEMPRE que haya que crear o modificar VISUALES en la capa de informe de un proyecto
  Power BI PBIP en formato heredado (un único archivo `report.json` dentro de `*.Report/`).
  Disparadores: "agrega un gráfico/visual", "arma la página", "muestra esta medida en un
  visual", "inserta KPIs", "visualiza los datos del modelo". Cubre la selección de visuales
  NATIVOS de Power BI, su enlace a tablas/columnas/medidas del modelo, y la inserción segura
  en report.json mediada por Python (sin cargar el archivo entero ni editar strings escapados
  a mano). NO usar para la capa de datos (eso es TMDL: skill tmdl-model). NO asumir el formato
  PBIR de carpeta-por-visual; aquí el informe es un solo report.json.
---

# Visuales nativos en `report.json` (formato PBIP heredado)

En este formato el informe es UN archivo `report.json` dentro de `*.Report/`. Las páginas son
`report["sections"]`; cada sección tiene `visualContainers` (array). Cada contenedor es
`{ config, filters, x, y, z, width, height }`, donde `config` y `filters` son **JSON
serializado como string**. El detalle del visual vive dentro de `config.singleVisual`.

La capa de datos (TMDL) NO se toca desde aquí; el modelo se lee con la skill `tmdl-model`.

**Dos formatos de informe:** (1) **heredado** = un `report.json` único (lo que insertan/validan los
scripts); (2) **PBIR** = `*.Report/definition/` carpeta-por-visual (`pages/<id>/visuals/<id>/visual.json`,
JSON real). `report_anatomy.py` ANALIZA ambos; **insertar/validar es solo heredado**. Los scripts de
escritura detectan PBIR y avisan (no rompen). Migrar inserción a PBIR sería una ronda futura.

---
## REGLA 0 — OPTIMIZACIÓN DE TOKENS (obligatoria)
---

`report.json` puede pesar cientos de KB con strings escapados anidados. **Nunca** se carga
entero al contexto ni se editan los strings a mano.

1. Toda mutación se hace con `scripts/insert_visuals.py` (Python lee/parsea/serializa el
   archivo; el modelo solo ve el script y un resumen corto).
2. El modelo del negocio se lee UNA vez con `scripts/model_catalog.py` → `catalog.json`
   (compacto). Se razona sobre ese catálogo, no releyendo los `.tmdl`.
3. Lecturas dirigidas: `Grep` por nombre de medida/columna; `Read` con offset+limit. Ignorar
   `LocalDateTable_*` / `DateTableTemplate_*` (ruido autogenerado) y `cache.abf` (binario).
4. Planificar primero, insertar en lote: un solo `plan.json` aprobado → una sola corrida del
   script (menos round-trips).
5. **Inspeccionar el layout** sin abrir el blob: `scripts/layout_map.py` imprime un mapa ASCII de
   las posiciones (existentes y/o propuestas). **Escribir medidas** (capa de datos): el mutador
   seguro es `tmdl-model/scripts/apply_measures.py` (nunca cargar `Medidas.tmdl` al contexto).
   Regla general: cualquier archivo que pueda ser grande (`report.json`, `*.tmdl`) se toca vía
   Python; los artefactos compactos (`catalog.json`, `plan.json`, `measures.json`, `intent.yaml`)
   se leen directo.

---
## REGLA 1 — APROBACIÓN HUMANA ANTES DE EJECUTAR (obligatoria)
---

No se inserta NADA sin aprobación explícita del usuario.

- El diseño produce primero un **plan** (`plan.json` + tabla resumen legible). El agente se
  detiene y pide al usuario revisar y aprobar.
- `insert_visuals.py` es el paso de EJECUCIÓN: solo se corre después de un "aprobado" claro
  en la conversación. Siempre crea backup `.bak` y re-valida el round-trip JSON.

---
## REGLA 2 — NATIVO PRIMERO, HTML SOLO SI HACE FALTA
---

Prioridad: visual **nativo** de Power BI (rendimiento, menos tokens, sin dependencias).
Recurrir a HTML solo cuando lo nativo no alcanza (ver `viz-design` skill para los criterios).
Para HTML hay dos vías: `render:"html-visual"` (custom visual HTML Content ← medida `M_HTML_*`, lo
inserta este toolkit) y `render:"html-dax"` (no se inserta aquí). El patrón completo (5 medidas
`M_JSON/M_CSS/M_JS/M_HTMLBody/M_HTML`, variante del visual, rol `content`, `esc()`/guards) está en
**`reference/html-in-dax.md`** (interno, autocontenido). Las reglas DAX en
`tmdl-model/reference/dax-authoring.md`.

---
## ARQUITECTURA PROFESIONAL (dos paradigmas)
---

Aprendido de un tablero real (`report_anatomy.py` lo extrae a `anatomy.json` + `skeletons/`):

- **Página HTML**: barra de **slicers nativos** + **UN visual `htmlContent` a página completa**
  alimentado por una medida `M_HTML_*` (todo el cuerpo es DAX→HTML).
- **Página de objetos**: composición de **mini-tarjetas `htmlContent`** (← medidas `Donut_*`/HTML)
  + **charts nativos** + **slicers** + **shape/image/textbox**, en **grupos anidados**.

Bloques (calcar de `skeletons/`):
- **HTML Content custom visual**: `visualType` = GUID (p. ej. `htmlContent443BE3…`), rol de datos
  **`content`** ← una **medida** HTML. `insert_visuals.py` lo inserta y **registra el GUID** en
  `report.publicCustomVisuals`.
- **Slicers SIEMPRE nativos** (regla fija): modo `Dropdown`, `header.show=false`, **título =
  medida** (traducción), `syncGroup` para sincronizar entre páginas.
- **Charts**: color por **`ThemeDataColor`** (paleta del tema) **o** hex (según `intent.theme.palette`);
  **título = medida** (`traduccion_titulo_*`) para multiidioma.
- **Grupos**: `singleVisualGroup` + `parentGroupName` (anidables) para el layout.

---
## REGLA 3 — VERDAD DE TERRENO (calcar un visual existente)
---

El formato escapado es frágil y algunos detalles (p. ej. el enum de agregación, los nombres
de rol por tipo de visual) no son fiables de memoria. Antes de generar un tipo de visual:

- Leer **un visual existente de tipo parecido** en `report.json` (vía Python o lectura
  dirigida) y calcar la forma de su `config` — incluidos `objects`/`vcObjects` para heredar la
  paleta y el estilo del informe.
- **Preferir enlazar medidas del modelo** en vez de agregaciones inline; evita el enum de
  funciones y reutiliza la lógica DAX. (El motor soporta `kind: "aggregation"` con enum
  verificado 0=Sum,1=Avg,2=DistinctCount,3=Min,4=Max,5=Count,6=Median,7=StdDev,8=Variance,
  pero la medida es la opción segura.)

---
## FLUJO ESTÁNDAR
---

0. **Anatomía** (si hay proyecto de referencia): `python scripts/report_anatomy.py --report <ref>\report.json -o anatomy.json --skeletons skeletons` → aprender la estructura real y calcar.
1. **Catálogo**: `python scripts/model_catalog.py <ruta>\<Proj>.SemanticModel\definition -o catalog.json`
   (`table_roles`, `translation_measures`, `measure_formats`, `html_measures`).
   **Preflight**: `python scripts/intent_check.py --intent intent.yaml --catalog catalog.json`
   (nombres no resueltos = STOP antes de diseñar).
2. **Diseño** (agente `pbi-report-designer`): catálogo + `intent.yaml` → resuelve el layout
   (`python scripts/layout_map.py --areas intent.yaml`) y/o revisa el actual
   (`--report <...>\report.json --intent intent.yaml`) → produce `plan.json` (con
   `formatting`/`theme` y posiciones de las áreas) + mapa ASCII + resumen. *Detenerse y pedir
   aprobación.*
3. **Ejecución** (agente `pbi-report-writer`, solo tras aprobación):
   `python scripts/insert_visuals.py --report <...>\report.json --plan plan.json --catalog catalog.json`
   (aplica el tema a `objects`; usar `--dry-run` para previsualizar sin escribir).
4. **Validación**: `python scripts/validate_report.py --report <...>\report.json --catalog catalog.json`
5. **Verificación humana**: el usuario abre Power BI Desktop y confirma el render.
   *Claude Code no puede renderizar Power BI: schema-válido no es lo mismo que visualmente
   correcto.*

> Medidas nuevas (capa de datos) son un flujo aparte y previo al diseño: el analista PROPONE →
> el usuario aprueba → se autora el DAX (reglas internas `tmdl-model/reference/dax-authoring.md`) →
> `tmdl-model/scripts/apply_measures.py` escribe en `Medidas.tmdl` → re-correr `model_catalog.py`.
>
> **Modificar (cambio puntual, por prompt)** = vía aparte, token-light (agente `pbi-report-editor`):
> `report_anatomy.py --find` localiza → nativo `edit_visual.py` / HTML `apply_measures.py` → validar.
> No recrea la página ni carga el `report.json` entero.

---
## ANATOMÍA Y FORMATO DEL PLAN
---

Ver `reference/legacy-visual-anatomy.md` para la estructura exacta de un `visualContainer`
y el formato de `plan.json` que consume `insert_visuals.py`. Ver `reference/native-visual-types.md`
para los `visualType` nativos y la heurística de selección por forma del dato.

---
## LÍMITES / NO HACER
---

- No cargar `report.json` entero al contexto; no editar los strings escapados a mano.
- No tocar el `name` (id de 20 hex) de visuales existentes.
- No tocar `*.pbip`, `.platform`, `.pbi/` (`cache.abf`, `localSettings.json`), ni
  `StaticResources/` salvo que se pida agregar un recurso.
- No editar la capa de datos desde aquí (TMDL → skill `tmdl-model`; reglas DAX →
  `tmdl-model/reference/dax-authoring.md`).
- Backup antes de escribir; validar después; y siempre dejar la verificación visual al usuario.
