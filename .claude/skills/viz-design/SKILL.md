---
name: viz-design
description: >-
  Usar al DECIDIR qué visualizaciones construir y cómo distribuirlas: elección de tipo de
  visual por forma del dato, jerarquía de lectura de la página, layout y coordenadas, y el
  criterio nativo-primero / HTML-solo-si-hace-falta. Disparadores: "qué gráfico conviene",
  "diseña la página", "cómo visualizo esto", "propón el dashboard". Produce un PLAN, no
  ejecuta cambios.
---

# Diseño de visualización (nativo primero)

> **Guías canónicas** (en `report-json-visuals/reference/`): `GUIA_Tablero_Nativo.md` (tableros de
> objetos nativos: composición, coloreado lienzo/slicer/gráficos, títulos por medida, grilla,
> performance) y `GUIA_Tablero_HTML_DAX.md` (tableros HTML-en-DAX). En ambos, **slicers/filtros = nativos**.

## Elegir paradigma (de un tablero profesional)

- **Página HTML**: barra de **slicers nativos** + **UN visual `htmlContent` a página completa**
  (← medida `M_HTML_*`). Úsala cuando el cuerpo es un dashboard HTML a medida.
- **Página de objetos**: composición de **mini-tarjetas `htmlContent`** + **charts nativos** +
  **slicers** + shape/image/textbox, en **grupos anidados**. Úsala para layouts ricos y modulares.

Si hay `anatomy.json`/`skeletons` (de `report_anatomy.py`), **calca** esos esqueletos. **Regla
fija: slicers/filtros SIEMPRE nativos.**

> **Páginas HTML — tamaño fijo:** todas al **mismo tamaño de visual** (p. ej. 1278×638, 16:9) con el
> *shell* en el CSS compartido y **scroll solo en la tabla** (acotar la raíz, no `body`). Ver
> `report-json-visuals/reference/html-in-dax.md` §5b y la guía §22. Color por `ThemeDataColor` o hex según `intent.theme.palette`;
títulos por **medida** (traducción) cuando aplica.

## Estándar nativo profesional (de un informe real, 100% nativo)

`report_anatomy.py --report <ref>` resume las prácticas (`report.practices`). Estándar recomendado:
- **KPIs con `cardVisual`** (card moderna); `actionButton` para navegar entre páginas (multipágina).
- **Títulos ligados a MEDIDA por defecto** (traducción), no texto fijo.
- **`ThemeDataColor`** por defecto (paleta del tema) salvo que el usuario pida hex.
- **Grupos** para estructurar el layout; **chrome** consistente (background/border/visualHeader off/
  dropShadow/title) vía `formatting`.
- Lienzo por página variable (más alto si hay scroll). El toolkit edita el **`report.json`** del
  proyecto PBIP; si el informe está en carpeta-por-visual, es solo análisis.

## Coloreado nativo (slicers + gráficos + fondo del lienzo)

Un tablero nativo SIEMPRE va coloreado: **slicers** (fondo+texto), **gráficos** (paleta) y el
**fondo del lienzo** (página). `insert_visuals.py` aplica **defaults** si no se especifica; si
`intent.theme` define colores, usa esos:
- `theme.background` → fondo del lienzo (página).
- `theme.slicer {fill,font}` → fondo y texto de los slicers.
- `theme.dataColors` / `formatting.themeColorId` → colores de los gráficos.

## Principio: nativo primero, HTML solo si hace falta

Por defecto, **visual nativo de Power BI**: mejor rendimiento, menos tokens, sin dependencias
ni recálculo de medidas HTML pesadas. Recurrir a HTML (la pista DAX/`htmlContent` del equipo)
**solo** cuando lo nativo no puede expresar el requerimiento, p. ej.:

- Layout/composición a medida imposible con un visual nativo.
- Texto enriquecido o tarjetas muy personalizadas (íconos dinámicos, formato condicional más
  allá de lo nativo).
- El patrón existente de títulos/contenidos por medida de traducción multilenguaje.

En el plan, marcar cada visual con `render: "native"` o `render: "html"`. Solo los `native`
se insertan vía `insert_visuals.py`; los `html` se enrutan a la pista de `Medidas.tmdl`.

## Selección por forma del dato

(Ver `report-json-visuals/reference/native-visual-types.md` para el mapeo completo.)
Regla rápida: 1 medida → card/kpi/gauge; medida × tiempo → línea; medida × categoría →
columnas (o barras si etiquetas largas / ranking); parte-del-todo → dona/treemap; correlación
→ dispersión; detalle → tabla/matriz.

## Ofrecer opciones (no imponer un solo gráfico)

Si `intent.yaml chart_preferences.offer_alternatives`, por cada visual presenta el **recomendado +
1–2 alternativas** (de `native-visual-types.md`), respetando `chart_preferences.by_shape` y los
overrides (`pages[].visuals[].type` / `visual_overrides`). El `plan.json` usa el recomendado; el
usuario puede pedir el cambio.

## Filtros y cantidad (de intent.yaml)

- `filters`: cada `{ field, control, title }` → un slicer. `control` ∈
  `dropdown|list|between|relative_date|search|tile`. El modo nativo exacto del slicer se logra
  **calcando un slicer existente** de ese modo (REGLA 3); no inventar la propiedad.
- `pages[].counts` (slicers/kpis/charts/tables) y/o `pages[].visuals` (lista explícita, manda sobre
  counts) fijan la cantidad. Respeta `performance.max_visuals_per_page`.

## Título por propiedad ⇒ sin caption por defecto

Si un visual/slicer lleva título propio, NO dejes además el nombre de la medida/columna. En
slicers, `insert_visuals.py` apaga el header automáticamente cuando hay `title`.

## Jerarquía de lectura (zonas por defecto)

1. Slicers (contexto global) arriba.
2. KPIs (resumen) debajo.
3. Tendencias / ranking (comparación) al centro (hero).
4. Detalle (tablas/matrices) abajo.

Son las `zones` por defecto de `intent.yaml layout.zones`; una página puede declarar excepciones.

## Layout sobre grilla (tipo bootstrap) + UX moderno

- **Grilla de 12 columnas** (de `intent.yaml layout.grid`: `columns`, `margin`, `gutter`,
  `row_h`). Calcula el ancho de columna: `col_w = (canvas_w − 2·margin − (cols−1)·gutter) / cols`;
  `x` de la columna n = `margin + n·(col_w + gutter)`. Un visual ocupa N columnas → su `width` =
  `N·col_w + (N−1)·gutter`. Alinea filas a `row_h`. Default: 12 col / 24 margin / 12 gutter en
  1280×720.
- **UX moderno:** jerarquía clara, agrupación con sentido, espacio en blanco, consistencia. Nada
  de posiciones al azar ni visuales que se pisen.
- Respetar límites: `x+width ≤ canvas_w`, `y+height ≤ canvas_h`.
- **Tema:** colores/fuentes de `intent.yaml theme` → bloque `formatting` por visual del plan (6
  dígitos para nativo). Reutiliza el estilo del informe leyendo `objects`/`vcObjects` de un visual
  existente.

## Layout por áreas (lo más fácil de ordenar) y ver el existente

Si `intent.yaml` trae `layout.areas` (estilo CSS `grid-template-areas`), resuélvelo a posiciones:

```
python report-json-visuals/scripts/layout_map.py --areas intent.yaml
```

Devuelve cada área → `x/y/width/height` sobre la grilla de 12 col y dibuja el mapa. Mapea cada
área a un visual (`pages[].visuals[].area`) y usa esas posiciones en el plan.

Para ver el layout **existente** sin cargar `report.json` al contexto:

```
python report-json-visuals/scripts/layout_map.py --report "<...>\report.json" --intent intent.yaml
```

Añade `--plan plan.json` para superponer tu propuesta y detectar colisiones (`#`) y
fuera-de-límites antes de insertar.

## Performance (criterio de diseño, no solo estética)

- Respeta `intent.yaml performance.max_visuals_per_page` (cada visual = una consulta DAX).
- Alta cardinalidad → `top_n` + orden, no listar todo; evita tablas/matrices enormes.
- Prefiere **medidas** sobre agregaciones inline; **nativo** sobre HTML (las medidas HTML-en-DAX
  recalculan y pesan).

## Entregable: el PLAN

Producir `plan.json` (formato en `report-json-visuals/reference/legacy-visual-anatomy.md`) +
una tabla resumen legible (página | visual | tipo | render | campos | posición | razón).
**Detenerse y pedir aprobación** antes de cualquier inserción.
