# `visualType` nativos de Power BI + heurística de selección

Usar nativos por defecto. Confirmar la grafía exacta calcando un visual existente del informe
(los visuales del marketplace usan ids opacos y exigen registro aparte: evitarlos salvo
necesidad real).

## Catálogo de tipos nativos

Comparación / ranking (categórico)
- `clusteredColumnChart`, `clusteredBarChart`
- `stackedColumnChart`, `stackedBarChart`
- `hundredPercentStackedColumnChart`, `hundredPercentStackedBarChart`
- `barChart`, `columnChart`

Tendencia (tiempo)
- `lineChart`, `areaChart`, `stackedAreaChart`
- `lineClusteredColumnComboChart`, `lineStackedColumnComboChart`

Composición (una dimensión)
- `pieChart`, `donutChart`, `treemap`, `funnel`

Valor único / KPI
- `cardVisual` (card MODERNA — preferida para KPIs), `card` (clásica), `multiRowCard`, `kpi`, `gauge`

Detalle
- `tableEx` (tabla plana), `pivotTable` (matriz)

Distribución / relación
- `scatterChart`, `waterfallChart`, `ribbonChart`

Filtro / layout (sin query de datos)
- `slicer`, `shape`, `image`, `textbox`, `actionButton` (navegación entre páginas en informes multipágina)

Custom visual (HTML)
- `htmlContent<GUID>` — "HTML Content": rol de datos **`content`** ← una **medida** que retorna
  HTML. Para tarjetas/visuales ricos por DAX. `insert_visuals.py` lo registra en
  `publicCustomVisuals`. Dos usos: **mini-tarjetas** (composición de objetos) o **1 a página
  completa** (`M_HTML_*`, página HTML).

> **Regla fija:** los **slicers/filtros** son SIEMPRE objetos visuales nativos (`slicer`), nunca HTML.

## Cómo se ve BIEN (prácticas de un informe nativo profesional)

Observado en un informe real (181 visuales, 100% nativos). Estándar recomendado:
- **KPIs con `cardVisual`** (card moderna); charts nativos para tendencias/ranking.
- **Títulos ligados a MEDIDA por defecto** (traducción dinámica), no texto fijo.
- **Color por `ThemeDataColor`** (paleta del tema), no hex fijo (salvo que el usuario lo pida).
- **Grupos** (`singleVisualGroup`/`parentGroupName`) para estructurar el layout.
- **Chrome de contenedor consistente**: `vcObjects` `background` + `border` + `visualHeader` (off)
  + `dropShadow` + `title`.
- **Multipágina con `actionButton`** de navegación; **lienzo por página variable** (más alto para
  contenido con scroll).
- `report_anatomy.py` reporta estas métricas (`report.practices`: % título-medida, % ThemeDataColor,
  grupos, tipos) para replicar el nivel del original.

## Roles por familia (claves de `projections` / `bindings`)

- Cartesiano (column/bar/line/area/combo): `Category`, `Y`, `Series` (leyenda); combo añade `Y2`.
- Pie/Donut/Treemap: `Category`, `Y`.
- Card / multiRowCard / Slicer: `Values`.
- KPI: `Indicator`, `TrendLine`, `Goal`.
- Tabla (`tableEx`): `Values`. Matriz (`pivotTable`): `Rows`, `Columns`, `Values`.
- Mapa: `Category`/`Location`, `Series`, `Size`, `Latitude`, `Longitude`.
- Scatter: `Category`, `X`, `Y`, `Size`, `Series`.

Ante la duda del rol exacto de un tipo, **leer un visual existente de ese tipo** en el
informe; no adivinar.

## Heurística de selección (mapeo por defecto)

- 1 medida → `card`. 1 medida + meta → `kpi`. 1 medida en rango → `gauge`.
- 1 medida × dimensión de tiempo → `lineChart`.
- 1 medida × categoría de baja cardinalidad (≤ ~12) → `clusteredColumnChart`
  (o `clusteredBarChart` si las etiquetas son largas).
- 1 medida × categoría de alta cardinalidad → `clusteredBarChart` ordenado desc (ranking).
- Parte-del-todo, pocas categorías → `donutChart`; muchas → `treemap`.
- 2 medidas, correlación → `scatterChart`.
- Aporte aditivo a un total → `waterfallChart`.
- Mucho detalle (varias medidas × filas) → `pivotTable` o `tableEx`.

## Jerarquía de la página (orden de lectura)

1. Segmentadores (`slicer`) arriba — contexto global.
2. KPIs (`card`/`kpi`) — resumen "¿cómo vamos?".
3. Tendencias/ranking (líneas/barras) — desviaciones.
4. Detalle (`tableEx`/`pivotTable`) abajo — drill-down operativo.
