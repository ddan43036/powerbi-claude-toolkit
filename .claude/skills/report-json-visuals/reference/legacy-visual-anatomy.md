# Anatomía de un visual en `report.json` heredado + formato de `plan.json`

## Estructura de un `visualContainer`

Cada elemento de `report["sections"][i]["visualContainers"]` es:

```jsonc
{
  "config":  "<JSON serializado como string>",   // el detalle del visual
  "filters": "[]",                                 // filtros de nivel visual (string)
  "x": 24, "y": 120, "z": 6000,                    // posición (duplica config.layouts)
  "width": 480, "height": 300
}
```

`config`, ya parseado, tiene esta forma (visual de datos):

```jsonc
{
  "name": "b5354f9899841de8468f",                  // id de 20 hex == nombre lógico
  "layouts": [{ "id": 0, "position": {
      "x": 24, "y": 120, "z": 6000, "width": 480, "height": 300, "tabOrder": 0 } }],
  "singleVisual": {
    "visualType": "clusteredBarChart",
    "projections": {                               // rol -> queryRefs
      "Category": [{ "queryRef": "DimOrg.Subgerencia", "active": true }],
      "Y":        [{ "queryRef": "Medidas.adherencia_prom" }]
    },
    "prototypeQuery": {                            // la consulta semántica
      "Version": 2,
      "From": [
        { "Name": "d", "Entity": "DimOrg",  "Type": 0 },
        { "Name": "m", "Entity": "Medidas", "Type": 0 }
      ],
      "Select": [
        { "Column":  { "Expression": { "SourceRef": { "Source": "d" } }, "Property": "Subgerencia" },
          "Name": "DimOrg.Subgerencia", "NativeReferenceName": "Subgerencia" },
        { "Measure": { "Expression": { "SourceRef": { "Source": "m" } }, "Property": "adherencia_prom" },
          "Name": "Medidas.adherencia_prom", "NativeReferenceName": "adherencia_prom" }
      ],
      "OrderBy": [{ "Direction": 2, "Expression": {
        "Measure": { "Expression": { "SourceRef": { "Source": "m" } }, "Property": "adherencia_prom" } } }]
    },
    "objects":   { /* formato de datos: colores, etiquetas, ejes */ },
    "vcObjects": { /* formato del contenedor: title, background, border... */ },
    "drillFilterOtherVisuals": true
  },
  "parentGroupName": "<id-del-grupo>"               // opcional: si va dentro de un grupo
}
```

Claves del enlace de datos:
- `From[].Name` es un **alias** de tabla; `Entity` es la tabla real del modelo.
- En `Select`, `SourceRef.Source` referencia ese alias y `Property` el campo.
- `Name` de cada Select == el `queryRef` usado en `projections`.
- Un grupo es un contenedor con `singleVisualGroup` (no `singleVisual`); sus hijos lo
  referencian por `parentGroupName`.

`Direction` de OrderBy: `1` = ascendente, `2` = descendente.
`Aggregation.Function` (enum verificado): 0=Sum, 1=Average, 2=DistinctCount, 3=Min, 4=Max,
5=Count, 6=Median, 7=StdDev, 8=Variance. **Preferir medidas** sobre agregaciones inline.

## Formato de `plan.json` (lo que produce el diseñador y consume `insert_visuals.py`)

```jsonc
{
  "visuals": [
    {
      "page": "Confirmaciones de Procesos",   // displayName de la sección (requerido)
      "id": null,                              // null => id autogenerado
      "visualType": "clusteredBarChart",       // (requerido)
      "title": "Adherencia por Subgerencia",   // opcional (título del contenedor)
      "position": { "x": 24, "y": 120, "width": 480, "height": 300, "z": 6000, "tabOrder": 0 },
      "parentGroupName": null,                 // opcional
      "render": "native",                      // "native" | "html"  (solo native se inserta aquí)
      "bindings": {                            // rol -> lista de campos
        "Category": [{ "table": "DimOrg",  "field": "Subgerencia",     "kind": "column",  "active": true }],
        "Y":        [{ "table": "Medidas", "field": "adherencia_prom", "kind": "measure" }]
      },
      "sort": { "table": "Medidas", "field": "adherencia_prom", "kind": "measure", "direction": "desc" },
      "rationale": "Ranking de subgerencias; barras horizontales por etiquetas largas."
    }
  ]
}
```

`kind` de cada campo: `column` | `measure` | `aggregation`. Para `aggregation`, agregar
`"function"` (nombre como `"sum"`, `"average"`, `"distinctcount"`, o el entero del enum).

El script valida cada `table`/`field` contra `catalog.json` antes de escribir: si algo no
existe, no escribe nada y reporta el error exacto.

## Tema / formato (opcional) — `theme` del plan + `formatting` por visual

`insert_visuals.py` puede aplicar un subconjunto **verificado** de formato a cada visual nativo,
derivado de `intent.yaml theme`. Se puede declarar un `theme` a nivel de plan (default para todos)
y un `formatting` por visual (excepción que gana sobre el `theme`):

```jsonc
{
  "theme": { "fontFamily": "Segoe UI", "fontSize": 10, "dataLabels": true },   // default global
  "visuals": [
    {
      "page": "Página 2", "visualType": "clusteredBarChart", "render": "native",
      "bindings": { /* ... */ },
      "formatting": {
        "dataColors": ["#1B5E20"],     // 1er color = color por defecto de los datos (6 díg, sin alfa)
        "fontFamily": "Segoe UI",
        "fontSize": 10,
        "dataLabels": true,
        "background": "#FFFFFF",
        "title": { "fontColor": "#1B5E20", "fontSize": 12 }
      }
    }
  ]
}
```

Mapeo a `singleVisual`:
- `dataColors[0]` → `objects.dataPoint[0].properties.defaultColor` (cartesianos y pie/dona).
- `dataLabels` → `objects.labels[0].properties.show` (cartesianos y pie/dona).
- `fontFamily`/`fontSize` → `objects.categoryAxis`/`valueAxis`/`labels` (solo cartesianos).
- `background` → `vcObjects.background`. `title{fontColor,fontSize}` → se fusiona en `vcObjects.title`.

Notas:
- El formato es **aditivo y gated por tipo**: lo que no aplica a un tipo se omite (no rompe).
- Color: hex de **6 dígitos** (`#RRGGBB`); el literal del motor no admite alfa (eso es para HTML).
- `fontSize` se serializa como literal `"<n>D"` (double). Paletas multi-serie o propiedades menos
  comunes: calcar de un visual existente (REGLA 3) o usar un archivo de tema PBIP.
- **Título sin caption duplicado:** si un visual trae `title`, en **slicers** el script apaga el
  header de nombre-de-campo (`objects.header.show=false`); opt-out con `formatting.hideDefaultCaption: false`.

## HTML Content custom visual, grupos y títulos por medida (plan.json)

```jsonc
{
  "visuals": [
    // Tarjeta/visual HTML: una medida que retorna HTML va al rol "content".
    { "page": "Salud estandares", "visualType": "htmlContent443BE3AD55E043BF878BED274D3A6865",
      "position": {"x":24,"y":24,"width":300,"height":180},
      "bindings": { "content": [{ "table":"Medidas","field":"M_HTML_x","kind":"measure" }] },
      "parentGroupName": "grp1" },                 // opcional: dentro de un grupo

    // Grupo contenedor (layout anidado). Los hijos lo referencian por parentGroupName = su id.
    { "page": "...", "group": true, "id": "grp1", "displayName": "KPIs",
      "position": {"x":20,"y":20,"width":600,"height":200} },

    // Chart nativo con color del tema y título dinámico (medida de traducción).
    { "page":"...", "visualType":"clusteredBarChart",
      "title_measure":"Medidas.traduccion_titulo_8",          // título = medida (multiidioma)
      "formatting": { "themeColorId": 4 },                      // ThemeDataColor (paleta del tema)
      "bindings": {"Category":[...],"Y":[...]} },

    // Slicer nativo pro (siempre nativo): modo + título-medida + sincronización.
    { "page":"...", "visualType":"slicer", "title_measure":"Medidas.slicer_mes", "syncGroup":"Mes",
      "formatting": { "slicerMode": "Dropdown" }, "bindings": {"Values":[...]} }
  ]
}
```

- `insert_visuals.py` **registra** los `visualType` custom (GUID hex) en `report.publicCustomVisuals`.
- `formatting.themeColorId` (int) → `dataPoint.fill` `ThemeDataColor`; alternativa: `dataColors`(hex).
- `title_measure` "Tabla.medida" → `vcObjects.title.text` = `Measure(...)` (vs `title` literal).
- Grupos: `singleVisualGroup`; los hijos llevan `parentGroupName` = id del grupo.

## Layout por áreas (intent.yaml → posiciones)

`intent.yaml layout.areas` (estilo CSS `grid-template-areas`) se resuelve a `x/y/width/height` con
`layout_map.py --areas intent.yaml`. El diseñador mapea cada área a un visual y usa esas posiciones
en `plan.json[].position`. El catálogo también expone `translation_measures` (medidas-string en la
carpeta `traduccion`) para títulos multilingües.
