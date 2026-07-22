# Tablero Confirmación de Procesos — PBIP

## Qué es este proyecto

Tablero Power BI en formato **PBIP** (Power BI Project). Es una carpeta con archivos de texto
plano que Power BI Desktop lee como si fuera un `.pbix`. Todo el modelo semántico (tablas,
medidas DAX, relaciones) se edita directamente en los archivos `.tmdl`.

---

## Estructura de carpetas

```
Archivos tablero CdP/                                    ← raíz del proyecto
│
├── CLAUDE.md                                            ← este archivo
├── .gitignore
│
├── Tablero Confirmacion de Procesos_test.pbip           ← punto de entrada (abrir en PBI Desktop)
│
├── Tablero Confirmacion de Procesos_test.Report/        ← capa visual (páginas, visuales)
│   ├── report.json                                      ← definición de páginas y visuales
│   ├── definition.pbir
│   ├── .platform
│   ├── .pbi/localSettings.json
│   └── StaticResources/                                 ← imágenes embebidas (no editar)
│
└── Tablero Confirmacion de Procesos_test.SemanticModel/ ← modelo de datos
    ├── definition.pbism
    ├── diagramLayout.json
    ├── .platform
    ├── .pbi/
    │   ├── editorSettings.json
    │   └── localSettings.json
    │
    ├── definition/                    ← CARPETA EDITABLE — todos los cambios van aquí
    │   ├── model.tmdl                 ← configuración del modelo + lista de tablas
    │   ├── database.tmdl              ← nombre de la base
    │   ├── relationships.tmdl         ← todas las relaciones
    │   ├── cultures/es-ES.tmdl        ← localización
    │   └── tables/                    ← UN ARCHIVO POR TABLA
    │       ├── Medidas.tmdl           ← *** ARCHIVO PRINCIPAL — todas las medidas DAX ***
    │       ├── cv_procesos.tmdl
    │       ├── cv_filtros_cdp.tmdl
    │       ├── DimOrg.tmdl
    │       ├── DimDate.tmdl
    │       ├── DimSemana.tmdl
    │       ├── FatoConfirmaciones.tmdl
    │       ├── FatoSemanalAdherencia.tmdl
    │       ├── FatoSemanalCumplimiento.tmdl
    │       ├── ResultadoSemanalConfirmaciones.tmdl
    │       ├── Fecha_Actual.tmdl
    │       ├── Calendario_MultiIdioma.tmdl
    │       ├── TablaIdiomas.tmdl
    │       ├── dim_traduccion.tmdl
    │       ├── Tbl_1.tmdl / Tbl_2.tmdl
    │       └── LocalDateTable_<guid>.tmdl  (×9, auto-generadas por PBI — no editar)
    │
    ├── tables/          ← COPIA ESPEJO — NO EDITAR (Power BI la regenera)
    ├── model.tmdl       ← COPIA ESPEJO — NO EDITAR
    └── relationships.tmdl  ← COPIA ESPEJO — NO EDITAR
```

> **Regla crítica:** Solo editar archivos dentro de `definition/`. Los archivos en la raíz de
> `.SemanticModel/` (sin `definition/`) son copias que Power BI regenera automáticamente.

---

## Archivo principal: Medidas.tmdl

**Ruta completa:**
`Tablero Confirmacion de Procesos_test.SemanticModel\definition\tables\Medidas.tmdl`

Contiene **todas** las medidas DAX del proyecto. Arquitectura de medidas HTML:

| Medida | Responsabilidad |
|--------|----------------|
| `M_CSS_Tablero` | Estilos CSS del tablero (divididos en css1..css4) |
| `M_HTML_Tablero` | Fragmento HTML + VARs de cómputo + inyección de datos JSON |
| `M_JS_Tablero` | Bloque `<script>` con toda la lógica JavaScript |
| `html_final_consolidado` | Ensamblaje final: `CSS + HTML + JS` → visual del informe |
| `html_tablero_final` | Medida standalone completa (backup independiente) |
| `M_JSON_Estandares` | Serializa datos de estándares como `<script>var _EST=[...];</script>` |
| `JSON_CdP_Filas_v3` | Serializa filas de confirmaciones como `<script>var __D3=[...];</script>` |

`M_HTML_Tablero` y `html_tablero_final` comparten bloques de VARs idénticos.
Al editar con `replace_all:true`, **ambas medidas se actualizan simultáneamente**. Los bloques
RETURN son distintos y deben editarse con strings únicos sin `replace_all`.

---

## Tablas del modelo

### Tablas de hechos / transacciones
| Tabla | Descripción | Clave de relación |
|-------|-------------|-------------------|
| `cv_procesos` | Confirmaciones de proceso (registro principal) | `Key_relacion`, `Site_usuario_key`, `ISOYearWeekNum`, `id_cdp` |
| `FatoConfirmaciones` | Confirmaciones individuales | `Site_usuario_key`, fecha |
| `FatoSemanalAdherencia` | Adherencia semanal agregada | `Site_usuario_key`, `ISOYearWeekNum` |
| `FatoSemanalCumplimiento` | Cumplimiento semanal agregado | `Site_usuario_key`, `ISOYearWeekNum` |
| `ResultadoSemanalConfirmaciones` | Resultados semanales | `Site_usuario_key` |

### Tablas de referencia / dimensión
| Tabla | Descripción |
|-------|-------------|
| `cv_filtros_cdp` | Universo de estándares a confirmar (Negocio, Site, Proceso, Estandar_critico, criticidad, Key_relacion) |
| `DimOrg` | Organización: empleados, sites, jerarquía. Columnas clave: `Site`, `Site_usuario_key` |
| `DimDate` | Calendario diario con campos `Data`, `Inicio do Mês`, `Inicio da Semana`, `ISOYearWeekNum` |
| `DimSemana` | Dimensión semana con `ISOYearWeekNum`, `Inicio da Semana`, `Fim da Semana` |
| `Fecha_Actual` | Tabla de un registro con la fecha actual |
| `Calendario_MultiIdioma` | Nombres de mes/semana en varios idiomas, enlaza con `TablaIdiomas` |
| `TablaIdiomas` | Catálogo de idiomas (`id_idioma`) |
| `dim_traduccion` | Traducciones de términos |

### Relaciones clave
```
cv_procesos.Key_relacion        → cv_filtros_cdp.Key_relacion    (muchos→uno)
cv_procesos.Site_usuario_key    → DimOrg.Site_usuario_key        (muchos→uno)
cv_procesos.ISOYearWeekNum      → DimSemana.ISOYearWeekNum       (muchos→uno)
FatoConfirmaciones.Site_usuario_key → DimOrg.Site_usuario_key   (muchos→uno)
FatoSemanalAdherencia.Site_usuario_key → DimOrg.Site_usuario_key
FatoSemanalCumplimiento.Site_usuario_key → DimOrg.Site_usuario_key
ResultadoSemanalConfirmaciones.Site_usuario_key → DimOrg.Site_usuario_key
DimDate.ISOYearWeekNum          → DimSemana.ISOYearWeekNum       (auto-detected)
```

> **Sin relación directa** entre `cv_procesos[site]` y `DimOrg[Site]` como columna de texto.
> Para contar sites únicos usar `COUNTROWS(SUMMARIZE(FILTER(DimOrg, NOT ISBLANK(DimOrg[Site])), DimOrg[Site]))`.

---

## Cómo editar medidas DAX

### Medida de una línea
```
measure NombreMedida = SUM(Tabla[columna])
    formatString: 0
    displayFolder: Carpeta
    lineageTag: <guid>
```

### Medida multilínea (backticks)
```
measure NombreMedida = ```
        VAR _e = ""
        VAR _resultado = CALCULATE(COUNTROWS(cv_procesos))
        RETURN _resultado
        ```
    formatString: 0
    displayFolder: Carpeta
    lineageTag: <guid>
```

### Flujo de trabajo
1. Editar `definition/tables/Medidas.tmdl` con las herramientas de archivo (Read/Edit/Write)
2. Guardar el archivo
3. Abrir Power BI Desktop → detecta los cambios y recarga automáticamente
4. Si no recarga: cerrar y reabrir el `.pbip`
5. Verificar en Power BI Desktop que no haya errores de compilación DAX

---

## Trampas críticas DAX

### PLACEHOLDER — límite de string constants
Error: `"La función 'PLACEHOLDER' encontró una cadena de texto que supera la longitud máxima"`

`html_final_consolidado` referencia `M_CSS_Tablero` + `M_HTML_Tablero` + `M_JS_Tablero`.
El presupuesto de literales se suma en todo el call graph. Si se agrega otra medida con
CONCATENATEX o strings largos, se desborda.

**Regla:** `M_JSON_Estandares` y medidas con `CONCATENATEX` sobre tablas grandes NO se
referencian desde `html_final_consolidado`. Se usan solo en `html_tablero_final` (standalone).

### String vacío en IF anidados
```dax
VAR _e = ""   -- declarar SIEMPRE al inicio
-- MAL:  IF(cond, "x", "")
-- BIEN: IF(cond, "x", _e)
```

### !important en CSS
```dax
VAR _imp = "!important"   -- nunca literal dentro del string
```

### rgba() con paréntesis anidados
```
rgba(0,0,0,.1) → #0000001A
```

### Columna no encontrada en SUMMARIZE
`SUMMARIZE(tablaA, tablaB[columna])` solo funciona si existe relación formal muchos→uno
de tablaA hacia tablaB. Sin relación, usar `SUMMARIZE(tablaB, tablaB[columna])` con filtro
de contexto aplicado automáticamente.

---

## Variables globales del tablero HTML

Las medidas HTML inyectan datos en el DOM como variables JS globales:

| Variable JS | Fuente DAX | Contenido |
|-------------|-----------|-----------|
| `window.__D3` | `JSON_CdP_Filas_v3` | Array de filas de confirmaciones |
| `window._EST` | `M_JSON_Estandares` | Array de estándares con conteo de confirmaciones |

El JavaScript del tablero lee estas variables y renderiza. No filtra — los datos ya
vienen filtrados por el contexto de slicers de Power BI.
