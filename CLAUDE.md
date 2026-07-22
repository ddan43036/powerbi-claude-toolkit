# CLAUDE.md — Tablero Power BI (PBIP) · forma de trabajo del equipo

**PBIP = el proyecto** (carpetas `*.Report\` + `*.SemanticModel\` + `*.pbip`). El toolkit es
**autocontenido** (no usa skills externas) y trabaja EDITANDO dos capas del proyecto:

- **Capa de datos (TMDL)** — `*.SemanticModel/definition/*.tmdl`. Edición vía `apply_measures.py`.
  La autoría DAX sigue las reglas INTERNAS del toolkit en
  `.claude/skills/tmdl-model/reference/dax-authoring.md`; HTML-en-DAX en
  `.claude/skills/report-json-visuals/reference/html-in-dax.md`.
- **Capa de informe** — el informe del proyecto es **`*.Report/report.json`** (un solo archivo): es
  lo que el toolkit **inserta/edita** (skill `report-json-visuals`).

> **PBIP ≠ "PBIR".** No confundir el PROYECTO (PBIP) con la forma de almacenar el informe. El
> toolkit edita el **`report.json` único**. Si un `*.Report` está guardado como carpeta-por-visual,
> `report_anatomy.py` puede ANALIZARLO, pero la inserción/edición es siempre sobre `report.json`
> (guardar el informe en ese formato para editarlo).

**Guías canónicas de arquitectura** (en `.claude/skills/report-json-visuals/reference/`):
`GUIA_Tablero_Nativo.md` (tablero de objetos nativos: coloreado lienzo/slicer/gráficos, títulos por
medida, grilla, performance) y `GUIA_Tablero_HTML_DAX.md` (HTML-en-DAX). Reglas DAX en
`.claude/skills/tmdl-model/reference/dax-authoring.md`; casos en `.../ERRORES-COMPILACION-DAX.md`.

**Requisito — Python 3:** los scripts requieren Python en el PATH. **Antes de ejecutar cualquier
script**, verificar `python --version` (o `py --version`); si falta, **ofrecer instalarlo**
(`winget install -e --id Python.Python.3.12` o python.org). Si el usuario acepta → instalar y
continuar; si rechaza → es **bloqueante** (no editar `report.json`/`*.tmdl` a mano).

## Reglas de oro (inviolables)

1. **Aprobación humana antes de ejecutar.** Ningún cambio en `report.json` se aplica sin que
   el usuario apruebe explícitamente el plan. El flujo es: diseñar → presentar plan → ESPERAR
   "aprobado" → ejecutar. (Ver flujo abajo.)
2. **Nativo primero, HTML solo si hace falta.** Conviven ambos. Se prioriza el visual nativo;
   se recurre a HTML (pista DAX/`htmlContent`) solo cuando lo nativo no alcanza.
3. **Optimización de tokens.** Nunca cargar `report.json` entero al contexto ni editar sus
   strings escapados a mano. Toda mutación vía los scripts de `report-json-visuals`. El modelo
   se lee una vez a `catalog.json` y se razona sobre él.
4. **No tocar** `*.pbip`, `.platform`, `.pbi/` (`cache.abf`, `localSettings.json`),
   `StaticResources/` (salvo agregar un recurso), ni los `name` (ids) de visuales existentes.
5. **Verificación visual la hace el usuario** en Power BI Desktop. Claude Code no renderiza:
   schema-válido ≠ visualmente correcto.

## Contrato de brevedad (TODOS los agentes — fuente de verdad)

El mensaje final de cada subagente se devuelve al orquestador y CONSUME tokens. Por eso cada agente
entrega SOLO su Definition of Done en formato compacto: rutas de artefactos + una tabla/lista corta
+ 1 línea de veredicto/siguiente paso.
**Prohibido:** preámbulos, repetir el contexto o `intent.yaml`, narrar el proceso paso a paso,
volcar JSON o archivos completos, explicaciones largas. Razón ≤ 1 frase por ítem.
El **orquestador** no re-explica ni re-resume la salida de los subagentes: releva solo lo esencial.
Presentar el plan = tabla + pregunta de aprobación, sin prosa.

## Dos vías de trabajo

- **CREAR (de cero):** dirigido por `intent.yaml` (manifiesto de CREACIÓN) → sigue el ORDEN de abajo.
- **MODIFICAR (cambio puntual):** dirigido por **prompt** ("cambia/edita…") → agente
  **`pbi-report-editor`** (token-light): `report_anatomy.py --find` localiza → clasifica **nativo**
  (`edit_visual.py`) vs **HTML** (`apply_measures.py` sobre la medida `M_*`) → `validate_report.py`.
  No usa `intent.yaml` ni recrea la página; solo toca lo pedido (backup siempre).

## Orden de ejecución (vía CREAR) — ROBUSTO E INEQUÍVOCO (fuente de verdad)

**Regla de no-desviación:** ejecuta los pasos en ESTE orden exacto; no los saltes, no los
reordenes, no adelantes escrituras. Ante duda, detente y pregunta. Los agentes referencian este
orden; no lo redefinen.

**Precondiciones antes de CUALQUIER escritura:** (1) existe `catalog.json` del paso 1; (2) el
portón correspondiente fue aprobado EN LA CONVERSACIÓN; (3) el script crea `.bak` antes de tocar.

0. **ANATOMÍA** (si hay un proyecto PBIP de referencia) — `report_anatomy.py --report <ref>\report.json`
   → `anatomy.json` + `skeletons/*.json`. Enseña la estructura real (paradigmas, htmlContent,
   grupos, tema, títulos-medida) para calcar. Solo lectura.
1. **ANALIZAR** — `pbi-model-analyst`
   - Entrada: `paths.model` de `intent.yaml` (o la ruta dada).
   - Acción: `model_catalog.py` → clasificar; si `measures.allow_new`/se pide, proponer ideas. Solo lectura.
   - Salida: `catalog.json` (`table_roles`, `translation_measures`, `measure_formats`, `html_measures`)
     + resumen breve + **inventario `YA EXISTE` vs `FALTA CREAR`** contra la necesidad declarada
     (lo no resuelto del preflight y las `%` sin formato entran en FALTA).
   - **Portón A** (solo si hay medidas nuevas): el usuario aprueba qué construir.
   - 1b. (tras A) Autoría DAX (reglas internas `tmdl-model/reference/dax-authoring.md`; HTML-en-DAX
     en `report-json-visuals/reference/html-in-dax.md`) → `measures.json` → `apply_measures.py`
     (backup) → **re-correr `model_catalog.py`**.
   - 1c. **PREFLIGHT** — `intent_check.py --intent intent.yaml --catalog catalog.json`. Si hay
     nombres NO resueltos → **STOP** (corregir nombres/crear medidas antes de diseñar).
2. **DISEÑAR** — `pbi-report-designer`
   - Entrada: `catalog.json` + `intent.yaml` (+ `anatomy.json`/`skeletons` si existen).
   - Acción: elegir **paradigma** (página HTML full-page vs composición de objetos con grupos);
     resolver `layout.areas` (`layout_map.py --areas`); elegir visuales (ofrecer alternativas);
     aplicar tema/filtros/títulos-medida; usar esqueletos para htmlContent/slicers/grupos.
   - Salida: `plan.json` + mapa ASCII + tabla resumen.
   - **Portón B**: el usuario aprueba el plan. (STOP obligatorio.)
3. **EJECUTAR** — `pbi-report-writer` (SOLO tras Portón B)
   - Entrada: `plan.json` + `catalog.json` aprobados.
   - Acción: `insert_visuals.py` (backup, aplica tema; inserta nativo + `html-visual` + grupos y
     registra el custom visual) → `validate_report.py`. `render:"html-dax"` → pista DAX (no se inserta aquí).
   - Salida: ids insertados + ruta backup + veredicto.
4. **VALIDAR** — `pbi-validator` → veredicto apto/no apto (bloqueantes vs advertencias).
5. **VERIFICAR** — el usuario abre Power BI Desktop (schema-válido ≠ se ve bien).

**Dos paradigmas de tablero** (entiéndelos): (a) **página HTML** = barra de slicers nativos + UN
visual `htmlContent` a página completa alimentado por una medida `M_HTML_*`; (b) **página de
objetos** = composición de mini-tarjetas `htmlContent` + charts nativos + slicers + shapes/image/
textbox en **grupos anidados**. **Regla fija: slicers/filtros SIEMPRE son objetos visuales nativos.**

**3 patrones de traducción** (el catálogo los detecta en `translation.strategy`):
`lookup` (dim_traduccion+Idioma_Activo), `switch` (tabla idiomas [Sigla] + medidas SWITCH +
Field Parameters), `metadata` (`Localized Labels`/Translations Builder). Ante un proyecto de
referencia, estudiar SIEMPRE `.Report` + `.SemanticModel` (`report_anatomy.py` + `model_catalog.py`).

El orquestador NO delega al writer ni corre `apply_measures.py` sin aprobación explícita (Portón B
/ Portón A). "Hazlo todo" NO salta los portones: igual presento el plan y espero.

## Artefactos de trabajo (no son del proyecto PBIP)

`catalog.json`, `plan.json`, `measures.json`, `measure_ideas.md`, `report.json.bak` y
`*.tmdl.bak` son artefactos de trabajo. Decide como equipo si se versionan o van a `.gitignore`.

## Scripts

En `.claude/skills/report-json-visuals/scripts/`:
- `model_catalog.py` — TMDL → catálogo compacto (`table_roles`, `translation_measures`,
  `measure_formats`, `html_measures`).
- `report_anatomy.py` — report.json real → `anatomy.json` + `skeletons/*.json` (aprender/calcar).
- `intent_check.py` — preflight: resuelve nombres de `intent.yaml` vs catálogo (no-resueltos = STOP).
- `insert_visuals.py` — inserta nativo + `html-visual` (custom HTML, auto-registrado) + grupos en
  report.json (backup + round-trip; tema por hex o `ThemeDataColor`; títulos por medida).
- `validate_report.py` — round-trip + integridad + posiciones + ids dup + custom visual registrado
  + visual vacío + parentGroupName + % sin formato.
- `layout_map.py` — mapa ASCII del layout (report.json/plan.json/`--areas`) para ubicar sin colisiones.
- `report_anatomy.py --find "<q>"` — localiza visual(es) por id/título/tipo (para MODIFICAR, token-light).
- `edit_visual.py` — parche puntual de un visual NATIVO (título/colores/posición/lienzo/slicer) por
  selector; backup + round-trip. Lo usa la vía MODIFICAR.

En `.claude/skills/tmdl-model/scripts/`:
- `apply_measures.py` — agrega/modifica medidas en `Medidas.tmdl` (backup; no inventa DAX;
  **rechaza copias espejo** y corre **QA automático**, restaurando el `.bak` si falla).
- `dax_qa.py` — QA de TMDL **sin compilar**: comillas impares, **VAR usada sin definir**,
  indentación TMDL, guarda de copia espejo y `--count "<ancla>"` para verificar un `replace_all`.

> **Editar SOLO bajo `...SemanticModel/definition/`**: lo de fuera son **copias espejo** que Power BI
> regenera (el cambio se perdería).

Regla de tokens: archivos grandes (`report.json`, `*.tmdl`) SIEMPRE vía estos scripts; artefactos
compactos (`catalog.json`, `plan.json`, `measures.json`, `intent.yaml`) se leen directo. Para
mantener/mejorar agentes y skills con eficiencia de tokens: `.claude/EVOLUCION-AGENTES-Y-SKILLS.md`
(basado en fuentes oficiales de Anthropic). Requisitos: Power BI Desktop (modo PBIP) y Python 3.
