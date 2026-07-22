# PBI Claude Toolkit — visuales nativos en PBIP con Claude Code

Forma de trabajo para que **Claude Code** ayude a desarrollar tableros Power BI en formato
**PBIP heredado** (informe = un único `report.json`): tú defines tablas, medidas y
relaciones; Claude Code analiza el modelo, **propone** las mejores visualizaciones nativas y,
**tras tu aprobación**, las inserta en `report.json`. Pensado para compartirse y mejorarse en
equipo vía Git.

## Qué hace y qué NO hace

- ✔️ Lee el modelo TMDL y arma un catálogo de tablas/columnas/medidas/relaciones.
- ✔️ Elige visuales **nativos** por forma del dato y los distribuye con jerarquía de lectura.
- ✔️ Inserta los visuales en `report.json` de forma **mediada por Python** (con backup y
  validación), sin cargar el archivo gigante al contexto ni editar strings escapados a mano.
- ✔️ **Portón de aprobación**: nunca aplica cambios sin tu OK explícito sobre el plan.
- ✔️ Convive con tu enfoque HTML-en-DAX: nativo primero, HTML solo cuando hace falta.
- ❌ No renderiza Power BI: la verificación visual la haces tú abriendo Desktop.
- ❌ No autoría DAX por su cuenta: eso sigue las convenciones del equipo en `Medidas.tmdl`.

## Requisitos

- **Power BI Desktop** en modo Desarrollador / proyecto guardado como **PBIP** (informe = un
  `report.json`; es lo que el toolkit edita).
- **Claude Code** instalado.
- **Python 3** en el PATH (los scripts usan solo librería estándar). Si falta, el toolkit **ofrece
  instalarlo** (`winget install -e --id Python.Python.3.12`): si aceptas continúa, si rechazas es
  bloqueante (los scripts no corren).
- **Autocontenido:** no requiere skills externas; las reglas DAX/HTML viven en los `reference/*.md`
  del toolkit.

## Instalación (una vez por proyecto)

Copia, en la **raíz del proyecto PBIP** (donde está el `.pbip` junto a `*.Report/` y
`*.SemanticModel/`):

```
<NombreProyecto>/
├── <NombreProyecto>.pbip
├── <NombreProyecto>.Report/
├── <NombreProyecto>.SemanticModel/
├── .claude/              ← de este toolkit (skills + agents)
├── CLAUDE.md             ← de este toolkit
└── intent.yaml           ← copia de intent.template.yaml, rellenada
```

Luego:
1. `cp intent.template.yaml intent.yaml` y rellénalo (opcional pero recomendado).
2. **Reinicia Claude Code** en la carpeta del proyecto (los agentes/skills se cargan al
   iniciar sesión).
3. Commitea `.claude/`, `CLAUDE.md` e `intent.yaml` para que el equipo los comparta.

> Recomendación de equipo: decidan un formato único para `report.json` (p. ej. `indent=2`) y,
> si quieren, normalícenlo en un pre-commit, para que los diffs de Git sean revisables.
> Decidan también si `catalog.json` / `plan.json` / `*.bak` se versionan o van a `.gitignore`.

> El **orden canónico, robusto e inequívoco** (con Entrada/Acción/Salida/Portón por paso y la regla
> de no-desviación) y el **contrato de brevedad** de los agentes viven en `CLAUDE.md` — es la fuente
> de verdad; agentes y este README apuntan ahí. `intent.yaml` centraliza tema, **grilla por áreas**
> (estilo CSS), **preferencias de gráfico**, **filtros**, **cantidad de visuales**, **performance**
> y **traducción** (títulos multiidioma).
>
> **Dos paradigmas** (el toolkit los domina): **página HTML** (slicers nativos + 1 visual
> `htmlContent` a página completa ← medida `M_HTML_*`) y **página de objetos** (mini-tarjetas
> `htmlContent` + charts nativos + slicers + shape/image/textbox en **grupos**). `report_anatomy.py`
> aprende la estructura de un proyecto real y genera esqueletos; `intent_check.py` valida los
> nombres del `intent.yaml` contra el modelo antes de diseñar. **Slicers/filtros = siempre nativos.**
>
> **PBIP = el proyecto; el informe que editamos es `report.json`** (un archivo). Si el `*.Report`
> está guardado como carpeta-por-visual, `report_anatomy.py` puede analizarlo, pero insertar/validar
> es siempre sobre `report.json` (no confundir el proyecto con esa variante de almacenamiento).
> **Traducción i18n** en 3 patrones detectados por el catálogo: `lookup` (dim_traduccion), `switch`
> (tabla idiomas + medidas SWITCH + Field Parameters), `metadata` (Localized Labels).

## Flujo de trabajo (orden inequívoco, con portones de aprobación)

1. **Analizar** — "Analiza el modelo de este proyecto" → `pbi-model-analyst` deja `catalog.json`
   (con roles dimensión/hecho/tiempo) + resumen. Si `intent.yaml measures.allow_new`, además
   propone **ideas de medidas** según el contexto (sin escribir DAX).
   - *(opcional, Portón A)* apruebas las medidas → se autora el DAX (reglas internas en
     `tmdl-model/reference/dax-authoring.md`) → `apply_measures.py` las escribe en `Medidas.tmdl` →
     se refresca `catalog.json`.
2. **Diseñar** — "Diseña la página 'Confirmaciones de Procesos'" → `pbi-report-designer` mira el
   layout actual (`layout_map.py`), aplica tema/grilla/performance de `intent.yaml`, y entrega
   `plan.json` + mapa ASCII + tabla resumen y **te pide aprobación**.
3. **Aprobar (Portón B)** — revisas `plan.json` y respondes "aprobado".
4. **Ejecutar** — `pbi-report-writer` corre la inserción (con backup, aplica el tema) y valida.
5. **Verificar** — abres Power BI Desktop y confirmas el render.

Ejemplo de arranque:

> "Lee el modelo, propón visuales nativos para la página 'Confirmaciones de Procesos' usando
> `intent.yaml`, y muéstrame el plan antes de tocar nada."

Claude Code: analiza → diseña → **se detiene con el plan** → (apruebas) → inserta → valida →
te dice que abras Desktop.

### Modificar un tablero existente (por prompt, token-light)

Para cambios puntuales NO uses `intent.yaml`: pídelo por prompt y lo resuelve `pbi-report-editor`:

> "Cambia el color de las barras del ranking a rojo" · "Edita el título del slicer de Semana" ·
> "Mueve el KPI de adherencia a la derecha" · "Cambia el fondo del lienzo a azul oscuro".

El editor **localiza** el objetivo (`report_anatomy.py --find`), detecta si es **nativo**
(`edit_visual.py`) o **HTML** (`apply_measures.py` sobre la medida `M_*`), aplica solo ese cambio
(con backup) y valida. No recrea la página ni carga el `report.json` entero.

## Por qué es eficiente en tokens

El `report.json` heredado es el formato menos amigable en tokens (un blob con JSON escapado
dentro de JSON). El toolkit lo evita: el archivo lo manipula un script Python
(`insert_visuals.py`), el modelo se resume una vez en `catalog.json`, y se usan lecturas
dirigidas (`Grep`/offset+limit). Claude Code casi nunca "ve" el archivo grande.

## Nativo vs HTML (convivencia)

El diseñador marca cada visual como `native`, `html-visual` o `html-dax`. Los `native` y los
`html-visual` (custom visual HTML Content ← medida `M_HTML_*`) se insertan por este toolkit; el
patrón HTML-en-DAX (5 medidas + variante del visual + `esc()`/guards) está en
`report-json-visuals/reference/html-in-dax.md`. Los **tableros nativos van coloreados** (slicers +
gráficos + fondo del lienzo) con defaults o con `intent.theme`.

## Limitaciones honestas

- **Sin render**: schema-válido no garantiza que se vea bien; verifica en Desktop.
- **Desktop puede reformatear** `report.json` al guardar, generando ruido de diff; acuerden
  una convención de formato como equipo.
- El parser de TMDL es **pragmático** (extrae nombres y relaciones, no es un parser completo);
  si una medida/columna no aparece en el catálogo, revísalo antes de insertar.
- El toolkit edita el `report.json` único. Si el informe se guarda como carpeta-por-visual,
  `report_anatomy.py` lo analiza, pero la inserción exige `report.json` (guardar en ese formato).

## Estructura del toolkit

```
.claude/
├── skills/
│   ├── report-json-visuals/   # núcleo: inserción de visuales nativos en report.json
│   │   ├── SKILL.md
│   │   ├── reference/         # anatomía + tipos nativos + html-in-dax + GUIA_Tablero_Nativo + GUIA_Tablero_HTML_DAX (§1-26)
│   │   └── scripts/           # model_catalog, report_anatomy(+--find), intent_check, insert_visuals, edit_visual, validate_report, layout_map
│   ├── tmdl-model/            # análisis del modelo + propuesta de medidas
│   │   ├── SKILL.md
│   │   ├── reference/         # dax-authoring + ERRORES-COMPILACION-DAX + ESTRUCTURA-PBIP-Y-TRAMPAS
│   │   └── scripts/           # apply_measures.py (escribe medidas) + dax_qa.py (QA sin compilar)
│   └── viz-design/            # visual + jerarquía + grilla/UX + performance (nativo primero)
├── agents/
│   ├── pbi-model-analyst.md   # modelo → catálogo + ideas de medidas (solo lectura del proyecto)
│   ├── pbi-report-designer.md # catálogo+intent → plan con tema/grilla (pide aprobación; no ejecuta)
│   ├── pbi-report-writer.md   # plan aprobado → inserción (backup + validación)
│   ├── pbi-report-editor.md   # MODIFICAR por prompt (nativo/HTML, token-light)
│   └── pbi-validator.md       # validación del report.json
└── EVOLUCION-AGENTES-Y-SKILLS.md  # cómo mejorar el toolkit (fuentes oficiales Anthropic)

intent.template.yaml           # manifiesto de CREACIÓN → copiar a intent.yaml
```
