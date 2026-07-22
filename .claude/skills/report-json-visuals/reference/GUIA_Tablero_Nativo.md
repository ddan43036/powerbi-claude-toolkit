# Guía: Cómo construir un tablero NATIVO profesional en Power BI (PBIP)

> Documento de arquitectura, hermano de `GUIA_Tablero_HTML_DAX.md`. El **diseño y los colores
> cambian** por proyecto; lo que **NO cambia** es la composición de visuales nativos, el coloreado,
> los títulos por medida y el layout en grilla. El toolkit inserta estos visuales en el
> **`report.json`** del proyecto vía `insert_visuals.py` (no se edita el JSON a mano).

---

## 1. Idea central: composición de OBJETOS visuales nativos

Un tablero nativo es una **composición de visuales de Power BI** (no una cadena HTML). Cada visual
se enlaza a **medidas/columnas del modelo** y se posiciona en el lienzo. No hay CSS/JS: el estilo
sale del **tema** y de las propiedades del visual (`objects`/`vcObjects`).

**Bloques de construcción** (calcables desde `report_anatomy.py --skeletons`):

| Bloque | visualType | Uso |
|---|---|---|
| KPI | **`cardVisual`** (moderna) / `card` | un número grande; preferir `cardVisual` |
| Comparación / ranking | `clusteredBarChart` (etiquetas largas) / `clusteredColumnChart` | medida × categoría |
| Tendencia | `lineChart` / `columnChart` | medida × tiempo |
| Parte-del-todo | `donutChart` / `pieChart` / `treemap` | composición de una dimensión |
| Detalle | `tableEx` / `pivotTable` | filas × medidas |
| Medidor | `gauge` | medida vs meta |
| **Filtros** | **`slicer`** (SIEMPRE nativo) | contexto global |
| Chrome | `shape`, `image`, `textbox`, `actionButton` | fondo, logo, títulos, navegación |
| Layout | `group` (`singleVisualGroup` + `parentGroupName`) | agrupar/estructurar |

> **Regla fija:** los **slicers/filtros son SIEMPRE objetos visuales nativos**, también en tableros HTML.

---

## 2. Coloreado (lo que el usuario más nota): slicers + gráficos + FONDO DEL LIENZO

Un tablero nativo va **coloreado**. El toolkit aplica **defaults** si no especificas; si defines
`intent.theme`, usa lo tuyo. Tres superficies:

| Superficie | De dónde sale | Dónde se escribe (report.json) |
|---|---|---|
| **Fondo del lienzo (página)** | `theme.background` (o default blanco) | `section.config → objects.background` |
| **Slicers** (fondo + texto) | `theme.slicer {fill,font}` (o default gris claro) | `vcObjects.background` + `objects.items.fontColor` |
| **Gráficos** (color de datos) | `theme.palette: theme` → `ThemeDataColor`; `palette: hex` → `theme.dataColors` | `objects.dataPoint.fill` / `.defaultColor` |

- **`ThemeDataColor`** (paleta del tema PBIP) es el estándar profesional; hex fijo solo si lo pides.
- Hex de **6 dígitos** (`#RRGGBB`) en nativo (el alfa de 8 dígitos es solo para HTML/CSS).
- `insert_visuals.py` lo aplica automáticamente desde el tema; opt-out del fondo con `plan.page_background:false`.

---

## 3. Títulos por MEDIDA (traducción multi-idioma)

En nativo el **título de un visual puede ser una medida** (no solo texto fijo): así se traduce
solo según el idioma activo. Es lo que hacen los tableros reales.

- `plan.json`/`intent.yaml`: `title_measure: "Medidas.<medida_de_titulo>"` → el toolkit escribe
  `vcObjects.title.text = Measure(...)` en vez de un literal.
- Las medidas de traducción siguen el patrón del modelo (ver `catalog.translation.strategy`):
  `lookup` (dim_traduccion), `switch` (`SWITCH(SELECTEDVALUE(TablaIdiomas[Sigla]),…)`) o
  `metadata` (Localized Labels). El **slicer de idioma** es nativo y suele ir con `syncGroup`.
- Si das título por propiedad, **no dejes el caption por defecto** (en slicers el header se apaga).

---

## 4. Layout: grilla de 12 columnas + áreas

- Define el layout en `intent.yaml` con **`layout.areas`** (estilo CSS grid-template-areas): cada
  línea = una fila; cada token = un área; repetir = más columnas. `layout_map.py --areas` lo
  resuelve a `x/y/width/height` (preview ASCII, sin colisiones).
- **Jerarquía de lectura** (arriba→abajo): slicers → KPIs → hero (ranking/tendencia) → detalle.
- **Grupos** (`group:true` + `parentGroupName`) para estructurar; lienzo por página según contenido
  (1280×720, o más alto si hay scroll).

---

## 5. Performance (tablero usable, no lento)

- **Menos visuales, más densos** (`performance.max_visuals_per_page`): cada visual = 1 consulta DAX.
- Alta cardinalidad → `top_n` + orden; evitar tablas/matrices enormes.
- **Preferir medidas** sobre agregaciones inline; relaciones **unidireccionales**, evitar bidireccional.

---

## 6. Formato de medidas (trampa real)

- Una medida de **porcentaje** debe tener `formatString` de `%` en el modelo; si no, se ve como
  decimal (`0,98` en vez de `98%`). Corrige el `formatString` en la medida (vía `apply_measures.py`),
  no por visual. `intent_check.py` y `validate_report.py` marcan las `%` sin formato.
- Reglas DAX al crear/editar medidas: `tmdl-model/reference/dax-authoring.md`.

---

## 7. Cómo se construye con el toolkit (flujo)

```
1. ANALIZAR  model_catalog.py  → catalog.json (roles, formatos, traducción)
   (referencia)  report_anatomy.py → anatomy.json + skeletons (calcar el estilo real)
2. PREFLIGHT intent_check.py   → nombres de intent.yaml resueltos vs modelo (no-resueltos = STOP)
3. DISEÑAR   pbi-report-designer → plan.json (render:"native", bindings, formatting/tema, áreas, grupos)
4. (Portón)  el usuario aprueba el plan
5. EJECUTAR  insert_visuals.py  → inserta nativo + colorea (slicers/gráficos/lienzo) + grupos; backup
6. VALIDAR   validate_report.py → integridad + posiciones + % sin formato
7. VERIFICAR el usuario abre Power BI Desktop
```

`render:"native"` (chart/card/slicer/table) lo inserta el toolkit. `render:"html-visual"` usa el
custom visual HTML Content (ver `GUIA_Tablero_HTML_DAX.md`). **Slicers siempre nativos en ambos.**

---

## 8. Dónde cambiar el DISEÑO (lo que sí cambia entre proyectos)

| Quiero cambiar… | Lo toco en… |
|---|---|
| Colores (lienzo, slicers, gráficos), fuentes | `intent.yaml → theme` (`background`, `slicer`, `dataColors`/`palette`, `fontFamily`) |
| Qué visuales y dónde | `intent.yaml → pages[].visuals` + `layout.areas` |
| Tipo de gráfico preferido | `intent.yaml → chart_preferences.by_shape` (el diseñador igual ofrece alternativas) |
| Filtros (campos + tipo) | `intent.yaml → filters` (control: dropdown/list/between/…) |
| Títulos (fijos vs traducidos) | `title` (texto) o `title_measure` (medida i18n) |
| Cantidad / densidad | `intent.yaml → performance` + `pages[].counts` |

---

## 9. Checklist antes de entregar

```
[ ] Slicers/filtros = objetos NATIVOS (slicer), nunca HTML
[ ] Lienzo, slicers y gráficos COLOREADOS (tema o defaults)
[ ] ThemeDataColor (paleta del tema) salvo que se pida hex
[ ] KPIs con cardVisual; títulos por medida donde haya i18n (header de campo apagado)
[ ] Layout en grilla (layout.areas) sin colisiones (layout_map --areas)
[ ] Medidas % con formatString de % (intent_check/validate sin avisos)
[ ] Presupuesto de visuales por página respetado; top_n en alta cardinalidad
[ ] plan.json aprobado (Portón B) antes de insertar; backup .bak creado
[ ] Probado en Power BI Desktop (schema-válido ≠ se ve bien)
```

---

## 10. Errores conocidos → solución

| Síntoma | Causa | Solución |
|---|---|---|
| KPI `%` muestra `0,98` | medida sin `formatString` de % | corregir formatString (apply_measures.py) |
| Slicer muestra el nombre técnico de la columna | header de campo + título duplicado | dar `title`/`title_measure`; el toolkit apaga el header |
| Gráfico de tiempo saturado (muchos días) | alta cardinalidad en columnas | `lineChart` + sin data labels, o `top_n`/agrupar por mes |
| Visuales encimados / cortados | demasiadas filas para el lienzo | menos filas/áreas; verificar con `layout_map --areas` |
| Tabla vacía | `role: table` sin `fields` | declarar columnas en el visual (intent_check lo avisa) |
| Lienzo sin color | no se aplicó el fondo | `theme.background` (o default); revisar `section.config.objects.background` |

---

*Resumen en una frase: **componer visuales nativos** enlazados a medidas, **colorear** lienzo +
slicers + gráficos desde el tema, **títulos por medida** para i18n, **layout en grilla** y pocos
visuales densos — todo insertado en `report.json` por el toolkit tras tu aprobación.*
