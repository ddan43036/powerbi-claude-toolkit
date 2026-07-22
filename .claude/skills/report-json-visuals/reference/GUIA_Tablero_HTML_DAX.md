# Guía: Cómo construir un tablero HTML profesional dentro de medidas DAX (Power BI)

> Documento de arquitectura. El **diseño y los colores cambian** según el cliente/proyecto;
> lo que **NO cambia** es la estructura de medidas y el flujo de datos descrito aquí.
> Si entiendes esta estructura, puedes rehacer el tablero con cualquier estética.

---

## 1. La idea central: separar responsabilidades en medidas distintas

Un tablero HTML embebido en Power BI es **una sola cadena de texto gigante** que un visual
(ej. *HTML Content*) renderiza. El error de principiante es meter CSS + HTML + JS + datos en
**una sola medida**. Eso es imposible de mantener y **revienta el límite de literales de DAX**
(error `PLACEHOLDER`).

La solución es dividir el tablero en medidas con **una responsabilidad cada una**:

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   M_JSON_*          │     │   M_CSS_Tablero     │     │   M_HTML_Tablero    │
│  (DATOS → JSON)     │     │  (ESTILOS)          │     │  (ESTRUCTURA + IDs) │
└─────────┬───────────┘     └──────────┬──────────┘     └──────────┬──────────┘
          │                            │                           │
          │  inyecta <script>var X=[]  │                           │  define <div id=...>
          └────────────┐               │                           │
                        ▼               ▼                           ▼
                 ┌──────────────────────────────────────────────────────┐
                 │              html_final_consolidado                   │
                 │   = "<html>" & M_CSS & "<body>" & M_HTML & M_JS ...    │  ← ESTE va al visual
                 └──────────────────────────────────────────────────────┘
                                          ▲
                              ┌───────────┴───────────┐
                              │     M_JS_Tablero       │
                              │  (LÓGICA: lee var X,   │
                              │   filtra y renderiza)  │
                              └────────────────────────┘
```

### Roles (de este proyecto)

| Medida | Responsabilidad | Regla |
|---|---|---|
| `M_CSS_Tablero` | Solo `<style>…</style>`. Aquí viven **colores, fuentes, tamaños**. | Es lo único que tocas para cambiar la estética. |
| `M_HTML_Tablero` | Estructura: `<div>`, tarjetas, contenedores **con `id=`**. Sin lógica. | Los `id` son el "contrato" con el JS. |
| `M_JS_Tablero` | `<script>`: lee las variables `window.*`, filtra, calcula y escribe en los `id`. | No genera datos; solo los consume. |
| `M_JSON_*` | Serializa datos del modelo a JSON: `<script>var _MIS_DATOS=[…]</script>`. | Una medida JSON por conjunto de datos. |
| `html_final_consolidado` | **Ensamblaje**: `CSS + HTML + JS`. Es la medida que se pone en el visual. | No contiene lógica ni literales propios pesados. |
| `html_tablero_final` | Copia *standalone* (todo en una medida) como respaldo. | No se usa en el informe; solo backup. |

> **Por qué funciona:** cada medida tiene su propio presupuesto de literales. Al separarlas,
> ninguna supera el máximo. Al consolidar con `&`, las referencias a otras medidas **no suman**
> al presupuesto de literales de la medida que ensambla.

---

## 2. Flujo de datos de inicio a fin

```
1. Modelo (tablas)  ──►  2. M_JSON_*  ──►  serializa filas a JSON
                                            <script>var _EST=[{...},{...}]</script>

3. M_HTML inyecta ese JSON + define <tbody id='est-body'></tbody>

4. M_JS lee window._EST, recorre el array y hace:
       document.getElementById('est-body').innerHTML = filas

5. html_final_consolidado = CSS + HTML(+JSON) + JS  ──►  visual HTML del informe
```

**Orden de inyección (crítico):** el `<script>var _EST=…>` de `M_JSON` debe ir **antes** del
`<script>` de `M_JS` en el body, porque el JS lee `window._EST` al ejecutarse.

```dax
RETURN "…<body>" & _HTML & [M_JSON_Estandares] & _JS & "</body></html>"
                            └── define _EST ──┘   └── lo usa ──┘
```

---

## 3. Patrón `M_JSON_*` (datos → JSON)

Convierte filas del modelo en un array JS. Reglas:

```dax
M_JSON_Estandares =
VAR _e = ""                          -- string vacío SIEMPRE como variable (ver §6)
VAR _datos = ADDCOLUMNS( SUMMARIZE(tabla, tabla[clave]), "@col", CALCULATE(...) )
VAR _json =
    CONCATENATEX(
        _datos,
        "{""campo"":""" & SUBSTITUTE(tabla[texto], """", "'") & """,""n"":" & [@col] & "}",
        ",",                          -- separador entre objetos
        tabla[orden], ASC
    )
RETURN "<script>var _EST=[" & _json & "];</script>"
```

- **Fechas** en ISO o formato fijo: `FORMAT(col, "yyyy-MM-dd")`.
- **Números** sin separador de miles: `SUBSTITUTE(FORMAT(v,"0.00"), ",", ".")` (fuerza punto decimal).
- **Texto** saneado: `SUBSTITUTE(texto, """", "'")` (las comillas dobles rompen el JSON).
- **Comillas dobles en DAX se duplican**: `""campo""` produce `"campo"`.
- **`top N`** si la tabla es enorme, para no reventar el visual ni el tiempo de consulta.

---

## 4. Patrón `M_HTML_*` (estructura)

Solo estructura y `id`. **Atributos HTML con comillas simples** `'` para no chocar con las
comillas dobles del string DAX:

```dax
VAR _html =
"<div class='card'>
   <div class='hd'>… <b id='est-tot'>&mdash;</b> …</div>
   <table>
     <thead><tr><th>Site</th><th>Proceso</th>…</tr></thead>
     <tbody id='est-body'><tr><td colspan='7'>Cargando…</td></tr></tbody>
   </table>
 </div>"
```

- Cada dato dinámico = un `<b id='…'>` o `<tbody id='…'>` que el JS rellenará.
- Reutiliza estilos repetidos en una VAR (`VAR _th = "…estilo th…"`) para **ahorrar literales**.

---

## 5. Patrón `M_JS_*` (render) — JS dentro de un string DAX

```dax
VAR _js = "<script>(function(){
  var E = window._EST || [];
  var g = function(i){ return document.getElementById(i); };
  var esc = function(s){ s=String(s==null?'':s);
      return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); };
  var b = g('est-body'); if(!b) return;        // guarda: si no existe el destino, no hace nada
  b.innerHTML = E.map(function(x){
      return '<tr><td>'+esc(x.s)+'</td>…</tr>';
  }).join('');
})();</script>"
```

### Comillas dentro del JS (regla de oro)
El `_js` es un string DAX delimitado por `"`. Dentro:
- Las **cadenas JS** usan comillas simples `'…'`.
- Los **atributos HTML que llevan espacios** (ej. `class="badge bcer"`, `title="…"`) necesitan
  comillas dobles → en DAX se escriben duplicadas: `class=""badge bcer""`.
- Atributos **sin espacios** (`style=font-size:11px`) pueden ir sin comillas (HTML5 lo acepta) y
  así evitas el escape.
- Para clases con varios tokens, define **una sola clase** (`class=bcer`) que incluya todo el
  estilo, así evitas comillas.

---

## 6. Trampas de strings DAX (qué SÍ y qué NO)

| Problema | ❌ Mal | ✅ Bien |
|---|---|---|
| String vacío en `IF`/separadores | `IF(c,"x","")` | `VAR _e="" … IF(c,"x",_e)` |
| `!important` literal | `"…!important}"` | `VAR _imp="!important" … & _imp &` |
| `rgba()` con paréntesis | `rgba(0,0,0,.1)` | hex con alfa: `#0000001A` |
| Comilla doble dentro del string | `"…"campo"…"` | duplicar: `"…""campo""…"` |
| `{` al inicio de un valor | rompe el YAML/parse | envolver: `If(true,{…},Blank())` |
| Medida JSON pesada en el consolidado | referenciar `M_JSON_*` desde `html_final_consolidado` | dejarla en un **visual dedicado** (ver §8) |

> **Límite PLACEHOLDER** (`"…cadena que supera la longitud máxima"`): el presupuesto de
> literales se suma en todo el *call graph*. Si una medida ensambladora referencia muchas
> medidas con literales grandes, se desborda. **Solución:** dividir (CSS/HTML/JS separados) y
> sacar lo pesado a un visual dedicado.

---

## 7. Trampa del renderizado HTML: `esc()` y entidades

`esc()` escapa `& < >` para proteger contra inyección de los **datos**. Pero NO debes pasar por
`esc()` los textos que YA son HTML/entidades (`&mdash;`, `&aacute;`, iconos `&#x2713;`),
porque `esc('&mdash;')` → `'&amp;mdash;'` → el navegador muestra el **texto literal** `&mdash;`.

```js
// ❌ muestra el texto "&mdash;"
'<td>'+esc(x.a||'&mdash;')+'</td>'
// ✅ escapa el dato; el guion de relleno queda como entidad y se renderiza "—"
'<td>'+(esc(x.a)||'&mdash;')+'</td>'
```

Regla: **datos del usuario → `esc()`**. **Etiquetas/entidades fijas → sin `esc()`**.

---

## 8. Visual dedicado para tablas/datos pesados

Cuando un bloque (ej. una tabla detallada con su propio JSON) es grande, **no lo metas en el
consolidado** (revienta PLACEHOLDER). Crea una **medida autocontenida** con su propio
`CSS + HTML + JS + JSON` y ponla en **otro visual / otra página**:

```dax
M_HTML_Salud_Estandares =
VAR _css = "<style>…</style>"
VAR _html = "<div>… <tbody id='est-body'></tbody></div>"
VAR _js = "<script>…lee window._EST…</script>"
RETURN "<!DOCTYPE html>…" & _css & "…<body>" & _html & [M_JSON_Estandares] & _js & "…"
```

Su *call graph* es pequeño (solo ella + su JSON) → nunca toca el límite del tablero principal.

---

## 9. Traducción (multi-idioma)

Driver único: una medida que devuelve el idioma activo desde el slicer.

```dax
Idioma_Activo = COALESCE(SELECTEDVALUE(TablaIdiomas[id_idioma]), "es")   -- "es" / "pt" / …
```

En la medida HTML, define cada etiqueta condicionada al idioma y úsala en HTML/JS:

```dax
VAR _pt = ([Idioma_Activo] = "pt")
VAR _L_estado = IF(_pt, "Status", "Estado")
-- HTML:  "…<th>" & _L_estado & "</th>…"
-- JS:    inyecta un objeto  var T={est:'" & _L_estado & "'}  y usa T.est en el render
```

- Los textos pueden vivir **inline en la medida** (rápido) o en `dim_traduccion` (centralizado).
- Lo importante: **un solo disparador** (`Idioma_Activo` ligado al slicer de idioma).

---

## 10. Filtrado nativo de Power BI

El visual HTML se filtra porque **la medida se recalcula en el contexto de filtro** del informe.
Claves:

- Una medida que itera una tabla (`SUMMARIZE`, `ADDCOLUMNS(tabla,…)`) **respeta** los slicers
  que filtran esa tabla. **No uses `ALL`** salvo que quieras ignorar el contexto.
- Cuidado con la **dirección de las relaciones**: si la relación es unidireccional, un slicer
  sobre la tabla "muchos" **no** filtra la tabla "uno". Para forzar el filtro al universo sin
  romper la dirección, usa `ISFILTERED` + `IN VALUES(...)`:

```dax
VAR _univ =
    FILTER( universo,
        ( NOT ISFILTERED(Dim[Col]) || universo[Col] IN VALUES(Dim[Col]) )
    )
```

- El filtro de **fecha** suele afectar solo a los **conteos** (la tabla de hechos), no al
  universo de dimensiones — y normalmente eso es lo deseado.

---

## 11. Dónde cambiar el DISEÑO (lo que sí cambia entre proyectos)

| Quiero cambiar… | Lo toco en… |
|---|---|
| Colores, fuentes, tamaños, bordes, sombras | **`M_CSS_Tablero`** (las variables `--xxx` y las clases) |
| Qué tarjetas/columnas se muestran y su orden | **`M_HTML_*`** (la estructura y los `id`) |
| Cómo se calcula/formatea cada celda, badges, búsqueda | **`M_JS_*`** (las funciones de render) |
| Qué datos llegan (campos, filtros, orden) | **`M_JSON_*`** |
| Textos / idiomas | etiquetas con `Idioma_Activo` |

> Mientras mantengas los **`id` del HTML** y los **nombres de las variables `window.*`**, puedes
> rehacer todo el CSS sin tocar el JS, y viceversa.

---

## 12. Checklist antes de entregar

```
[ ] CSS, HTML, JS y JSON están en MEDIDAS SEPARADAS
[ ] html_final_consolidado solo ensambla (sin lógica ni literales pesados)
[ ] M_JSON_* pesados NO se referencian desde el consolidado (van a visual dedicado)
[ ] var _e="" declarada; nada de "" literal en ramas de IF
[ ] !important como variable; rgba() reemplazado por hex con alfa
[ ] Comillas dobles duplicadas dentro de strings DAX
[ ] El <script> del JSON va ANTES del <script> del JS
[ ] esc() solo sobre datos; entidades fijas sin esc()
[ ] Cada dato dinámico tiene su id en el HTML y su set en el JS
[ ] El JS tiene guarda: if(!g('destino')) return;
[ ] Traducción manejada por un único Idioma_Activo
[ ] La medida respeta el contexto de filtro (sin ALL innecesario)
[ ] Probado en Power BI Desktop (no se puede compilar DAX fuera de Desktop)
```

---

## 13. Errores conocidos → solución

| Síntoma | Causa | Solución |
|---|---|---|
| `La función 'PLACEHOLDER' … supera la longitud máxima` | Demasiados literales en una medida / call graph | Separar CSS/HTML/JS; sacar JSON pesado a visual dedicado |
| `La sintaxis de '' no es correcta` | `""` literal en un `IF` | `VAR _e="" ` y usar `_e` |
| Celda muestra `&mdash;` / `&aacute;` literal | Entidad pasada por `esc()` | `(esc(dato)||'&mdash;')`, no `esc(dato||'&mdash;')` |
| Tabla vacía / "Sin datos" | El `<script>var X` no se inyectó o va después del JS | Inyectar el JSON antes del `_js` |
| `Unexpected token` en consola | Comilla sin escapar en el JSON/JS | Duplicar comillas en DAX; sanear texto con `SUBSTITUTE` |
| El visual no se filtra | Se usó `ALL`, o la relación es unidireccional | Quitar `ALL`; usar `ISFILTERED`+`IN VALUES` |
| Columna de texto vacía pese a haber datos | `MAXX` sobre texto poco fiable | Usar `CONCATENATEX(filtro, [col])` para una sola fila |
| Un slicer afecta a otro al cambiarlo | `syncGroup.groupName` repetido por error | Dar a cada slicer su grupo correcto (o uno único) |

---

## 14. Medidas escalares centralizadas (una sola fuente de verdad)

Cuando una métrica (ej. **% cumplimiento de planes**, **% cobertura**) se muestra en **varios
visuales / páginas**, NO la recalcules en cada HTML. Defínela **una vez** como medida escalar y
reúsala en todos lados:

```dax
M_Plan_Tot  = COUNTROWS(...planes...)
M_Plan_Cerr = M_Plan_Tot - vencidos
M_Plan_Pct  = IF([M_Plan_Tot]=0, -1, ROUND(DIVIDE([M_Plan_Cerr],[M_Plan_Tot])*100, 0))   -- -1 = "sin datos"
```

| Dónde se usa la métrica | Cómo se consume |
|---|---|
| Gauge renderizado en **DAX** (HTML server-side) | `VAR _pp = [M_Plan_Pct]` y se dibuja el arco |
| Gauge renderizado en **JS** (otra hoja) | inyectar `"<script>window._PLNG={p:" & [M_Plan_Pct] & ",c:" & [M_Plan_Cerr] & ",t:" & [M_Plan_Tot] & "};</script>"` y leerlo en el JS |
| Serie de un **gráfico SVG** (tendencia) | `CALCULATE([M_Plan_Pct], DimSemana[Mes]=_mes)` por mes |

> **Beneficio (para skills/agentes):** editas la lógica en UN solo lugar y los 3 visuales quedan
> sincronizados por construcción. Convención: `M_X_Tot` / `M_X_Cub|Cerr` (conteos) + `M_X_Pct` (%),
> con `-1` como centinela de "sin datos" que el JS/HTML traduce a "S/D".

---

## 15. La copia gemela *standalone* — cuidado al editar con `replace_all`

`html_tablero_final` (§1) **duplica** los VAR y el JS de `M_HTML_Tablero` / `M_JS_Tablero`. Un
`replace_all` golpea **ambas copias**. Reglas para no romper la compilación:

- Si introduces un **VAR nuevo** que luego usas en el RETURN/JS, asegúrate de que ese VAR exista
  en **ambas** copias (haz el `replace_all` sobre una línea VAR común a las dos) **o** edita solo
  la activa con un ancla única.
- **Nunca** dejes una referencia a un VAR/medida en una copia donde no esté definido → error de
  compilación que **bloquea todo el modelo**, aunque la copia "no se use".
- La copia de respaldo no va al informe, pero **debe compilar**.

---

## 16. Detectar la selección de un slicer que vive en una tabla **relacionada**

`ISFILTERED(hecho[col])` es **FALSO** si el slicer filtra una **dimensión** relacionada (no la
columna del hecho). Para saber qué valor está seleccionado, mira los `VALUES` de la columna real
del slicer:

```dax
VAR _vals = VALUES(dim[col])
VAR _sel  = IF(COUNTROWS(_vals)=1, MAXX(_vals, dim[col]))   -- 1 fila = selección única; >1 = "todos"
VAR _sufijo = SWITCH(_sel, "Si", " críticos", "No", " no críticos", _e)
```

Úsalo para **sufijos dinámicos** en las tarjetas ("(críticos)" / "(no críticos)" / genérico cuando
están ambos). Síntoma del bug: el sufijo "nunca aparece" porque se detectaba sobre la columna del
hecho en vez de la del slicer.

---

## 17. Resaltar el "mínimo" sin pintar todo de rojo

Si coloreas el peor valor con `IF(valor = min, rojo, …)`, cuando **todos son iguales** (ej. todas
las preguntas en 100%) **todos** cumplen `valor = min` → **todo rojo** (siendo que es verde).
Guarda el resalte para cuando hay **dispersión real**:

```dax
VAR _min = MINX(lista, [Value])  VAR _max = MAXX(lista, [Value])
-- color del dato: resaltar el mínimo SOLO si hay variación
VAR _color = IF(valor = _min && _min < _max, "#e24b4a", <color por umbral 80/60>)
```

---

## 18. Gráfico SVG nativo (sin librerías) dentro de la medida

- Cada **serie** (barras, líneas, puntos) = un `CONCATENATEX` que arma `<rect>` / `<circle>` /
  `<polyline points=…>`.
- **Conteos** y **porcentajes** van en escalas distintas: barras de conteo escaladas por su máximo
  (`y = 115 - cnt/max*H`); líneas de % en escala fija (`y = 115 - pct/100*H`). Mezclar conteo y %
  en la misma escala hace que una serie se vea "plana".
- **Achurado** (hatch): `<defs><pattern id='hm'>…</pattern></defs>` + `fill='url(#hm)'`, aplicado
  **condicional** (ej. solo el mes actual *y* solo si tiene datos: `IF([Value]=_mesAct && [@cnt]>0, "url(#hm)", …)`).
- **Tooltips nativos**: atributos `data-*` en cada elemento + una función JS (`stt`) que lee
  `getBoundingClientRect()` y posiciona un `<div>` flotante.
- Para **reaprovechar series**: cada línea referencia una **medida aparte** (ej. cumplimiento =
  `KPI_Adherencia_%`, cumplimiento de planes = `M_Plan_Pct`), no se recalcula inline.

---

## 19. Rendimiento de `M_JSON_*` con búsquedas por fila

Si serializas filas que requieren `LOOKUPVALUE` (ej. mapear un email → nombre/site de `DimOrg`):

- **Filtra primero, busca después**: `SELECTCOLUMNS(FILTER(tabla, condición), …, LOOKUPVALUE(…))`
  para que el lookup corra solo sobre las filas necesarias.
- **Guarda de blanco**: `IF(ISBLANK(_x), _x, COALESCE(IFERROR(LOOKUPVALUE(…),BLANK()), …))` evita
  buscar en filas vacías y tolera multi-match (el `IFERROR` cae a blanco).
- **Cadena de respaldo** con `COALESCE`: intenta por `Correo`, luego por prefijo de email →
  `Nombre_usuario`, y si no, deja el valor crudo.
- Cada lookup extra por columna **multiplica** por nº de filas: si notas lentitud, reduce a una
  sola búsqueda.

---

## Checklist (ampliado)

```
[ ] Métricas repetidas en varios visuales → medida escalar única (M_X_Pct), reusada, no recalculada
[ ] Copia gemela standalone COMPILA (VARs definidos en ambas; sin referencias huérfanas)
[ ] Selección de slicer en dimensión → VALUES(dim[col]), no ISFILTERED(hecho[col])
[ ] Resaltado del mínimo guardado con (min < max) para no pintar todo de rojo
[ ] Conteos y % en escalas separadas en gráficos SVG
[ ] LOOKUPVALUE en M_JSON con FILTER previo + guarda de blanco + IFERROR
```

---

## 20. Organización de las medidas en carpetas (`displayFolder`)

Para que el tablero sea **mantenible y reutilizable** entre páginas, **todas** las medidas que
alimentan los HTML viven bajo una carpeta raíz **`responsabilidades`**, con esta estructura:

```
responsabilidades/
├── M_HTML_<Pagina>/          ← una subcarpeta por cada medida HTML (una por página/visual)
│     · M_JSON_<Pagina>        (datos SOLO de esa página)
│     · M_CSS_/M_JS_<Pagina>   (si son propios de esa página)
│     · cálculos/traducciones que SOLO usa ese HTML
│
├── _compartido/              ← medidas reutilizadas por 2+ HTML (una sola fuente de verdad)
│     · métricas centralizadas:  M_Plan_Pct, M_Cob_Pct, …
│     · componentes reutilizables: M_HTML_BtnVolver, …
│     · transversales: Idioma_Activo, traducciones globales
```

**Reglas (para el agente + skill):**
- El **nombre de la subcarpeta = el nombre de la medida HTML** que sirve
  (ej. `responsabilidades/M_HTML_Salud_Estandares`).
- Una medida usada por **2+ HTML** va a **`_compartido`** y NO se duplica (ver §14).
- Una medida nueva se crea **en la carpeta del HTML al que pertenece**; si luego la usa otra
  página, se **mueve a `_compartido`**.
- Así el agente sabe **dónde buscar** y **dónde crear** cada medida, y el modelo queda navegable.

En TMDL la carpeta se fija por medida con `displayFolder`:

```
measure M_JSON_Estandares = …
    displayFolder: responsabilidades/M_HTML_Salud_Estandares

measure M_Plan_Pct = …
    displayFolder: responsabilidades/_compartido
```

---

## 21. Editar sin tocar lo que no se pidió (disciplina de edición)

El modelo y el informe tienen partes hechas a mano por el usuario (**botones nativos** de
navegación, **medidas propias**, **hojas**) que **no se deben modificar** salvo petición explícita.
Cómo editar de forma quirúrgica:

1. **Analiza primero.** Antes de editar, lista lo que ya existe y de quién es: secciones del
   `report.json`, `actionButton`/`visualLink` (botones nativos del usuario), medidas (`measure …`)
   y sus carpetas. Identifica lo del usuario para **no pisarlo**.
2. **Ancla mínima y única.** Reemplaza la **subcadena más pequeña que identifica el cambio**.
   No reescribas bloques completos; cambia solo el fragmento pedido (así no reformateas lo demás).
3. **`replace_all` con intención.** Úsalo **solo** cuando quieres tocar *todas* las coincidencias
   (típico: la medida activa **y** su copia gemela `html_tablero_final`). Si es una sola, usa un
   ancla único. **Verifica el conteo** de coincidencias esperado antes/después con `grep`.
4. **Lo que vive en la medida, se edita en la medida.** Un botón *placeholder* va dentro del HTML
   de la medida (no como visual nativo del `report.json`) → así nunca tocas los botones nativos
   del usuario. Solo edita `report.json` cuando el cambio es realmente del informe (binding de un
   visual, una hoja nueva) y con ancla por `name`/`config` único.
5. **La copia gemela debe compilar.** Si agregas un VAR/medida referenciado, asegúrate de que
   exista en **ambas** copias o edita solo la activa con ancla único (ver §15). Una referencia
   huérfana en la copia rompe TODO el modelo aunque "no se use".
6. **Verifica y no toques de más.** Con `grep`/conteos confirma que el cambio entró donde debía y
   que **no cambió nada más**. No reordenes, no reformatees, no "mejores de paso" lo no solicitado.

> Regla de oro: **cambio mínimo, ancla único, analiza antes, verifica después.**

---

## 22. Layout de tamaño fijo (16:9 / contenedor 1278×638) — scroll SOLO en las tablas

El visual *HTML Content* NO renderiza tu HTML como un `<body>` a pantalla completa: lo inyecta
dentro de un **`<div>` anfitrión de alto fijo (= el tamaño del visual) con scroll propio**. Por eso
poner `overflow:hidden` en `body`/`html` **no** detiene el scroll de la página: el que scrollea es
ese div anfitrión, no `body`. **La solución es acotar la altura de TU elemento raíz** (el `<div>`
más externo de tu HTML: `.app`, `.card`, …), que es el que se desborda.

```css
html,body{height:100%;overflow:hidden}          /* refuerzo, pero NO basta por sí solo */
.app{height:100vh;max-height:100vh;overflow:hidden;display:flex;flex-direction:column}  /* ← la clave */
/* cadena flex: cabecera y KPIs fijos; SOLO la zona de tabla scrollea */
.bd{flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column}
.tw{flex:1;min-height:0;overflow:auto}          /* ← ÚNICO scroll (filas de la tabla) */
```

**Reglas:**
- Cada nivel intermedio necesita **`min-height:0`** para que el hijo flex pueda encogerse; sin él,
  el contenido empuja y el anfitrión vuelve a scrollear.
- El **único** elemento con `overflow:auto` es el contenedor de la tabla/lista.
- Si `body` tiene `padding`, usa `height:calc(100vh - <2×padding>)` en la raíz para que cuadre exacto.
- Si `100vh` no mapea al área del visual en tu versión del custom visual, **fija píxeles**:
  `height:<alto_del_visual>px` (ej. `622px` para un contenedor de 638). Inmune a cómo resuelva `vh`.
- **Mismo tamaño de visual para todas las páginas** → pon este *shell* en el **CSS compartido**
  (`M_CSS_Tablero`) y todas quedan 1278×638 por construcción.
- Para *aprovechar el alto* (que una card llene): dale al elemento raíz de esa card `flex:1` dentro
  de un padre flex-column; para **centrar** contenido compacto usa `align-content:center` +
  `justify-content:center` en un `display:flex;flex-wrap:wrap` (evita `grid-auto-rows:1fr`, que
  estira las celdas y "gasta" alto).

> Síntoma que delata el bug: "el scroll mueve TODA la hoja (KPIs, título y tabla juntos)" → el
> scroller es el anfitrión, no la tabla. Fix = acotar la raíz, no `body`.

---

## 23. Dividir una medida HTML grande en varias páginas

Cuando una página crece demasiado (o quieres separar secciones en hojas), divídela en varias
medidas HTML que **comparten el mismo `M_CSS_Tablero`**:

```dax
html_pagina_A = "<!DOCTYPE html>…" & [M_CSS_Tablero] & "<body>" & [M_HTML_A] & [M_JS_A] & "…"
html_pagina_B = "<!DOCTYPE html>…" & [M_CSS_Tablero] & "<body>" & [M_HTML_B]             & "…"
```

- **CSS compartido** ⇒ misma estética y mismo *shell* fijo (§22) para todas.
- **Corte limpio**: extrae el RETURN de la medida original y pártelo en **anclas HTML únicas**
  (ej. `<div class='card'>…>" & _t_<seccion>`), luego arma el RETURN de cada página concatenando
  `[topbar] + [card(s) de esa página] + [cierres </div>…]`.
- **VARs muertas**: si solo recortas el RETURN, las VARs de la sección removida quedan **definidas
  pero sin usar** — inofensivas (DAX no evalúa VARs no usadas). Muévelas a la nueva medida o déjalas.
- Cada página nueva = `M_HTML_<Pagina>` (+ `M_JS_<Pagina>` si hay interacción) + `html_<pagina>`
  (ensamblaje), todas bajo `responsabilidades/M_HTML_<Pagina>` (§20).

---

## 24. Motor de series seleccionables (toggle extensible)

Para que el usuario active/desactive series de un gráfico (o cualquier grupo de elementos), usa un
motor genérico basado en `data-s`:

```html
<!-- cada serie togglable envuelta en un grupo con su clave -->
<g class='ser' data-s='cmp'> … polyline + dots … </g>
<g class='ser' data-s='obj'> … </g>
<!-- las series FIJAS (ej. barras base) van FUERA de cualquier <g> -->
<!-- control por serie (switch estilizado; el <input> real va oculto) -->
<label class='swchip on' style='--sc:#22c55e'>
  <span class='swtr'><span class='swkn'></span></span> …
  <input type='checkbox' class='sck' data-s='cmp' checked>
</label>
```

```js
var ck=document.querySelectorAll('.sck');
function ap(){for(var i=0;i<ck.length;i++){var s=ck[i].getAttribute('data-s');
  var g=document.querySelectorAll('g.ser[data-s='+s+']');
  for(var j=0;j<g.length;j++)g[j].style.display=ck[i].checked?'':'none';
  var lb=ck[i].parentNode; if(lb){ if(ck[i].checked)lb.classList.add('on'); else lb.classList.remove('on'); }}}
for(var i=0;i<ck.length;i++)ck[i].addEventListener('change',ap); ap();
```

- **Extensible sin tocar el JS**: agregar una serie = un `<g class='ser' data-s='nueva'>` + un
  `<label class='swchip'><input class='sck' data-s='nueva'></label>`. El motor la toma sola.
- El switch (track `.swtr` + knob `.swkn`) se estiliza con `.swchip.on` (mueve el knob y colorea con
  `var(--sc)`, el color de la serie inyectado inline). El `<input>` real va oculto
  (`position:absolute;opacity:0`) pero sigue siendo la fuente de verdad del estado.
- Más intuitivo que checkboxes sueltos: swatch de color + nombre + interruptor, en un panel lateral.

---

## 25. Rescalar un gráfico SVG para *llenar el alto* (sin distorsión)

Si el gráfico deja mucho espacio vacío, para hacerlo más alto **NO** uses
`preserveAspectRatio='none'` (estira las letras y convierte los círculos de los puntos en óvalos).
En su lugar, **reescala coordinadamente** la geometría vertical y el alto del `viewBox`:

| Constante | Qué es | Ejemplo (140→270) |
|---|---|---|
| `viewBox='0 0 W H'` | lienzo del SVG | `0 0 730 140` → `0 0 730 270` |
| `baseline` | y del eje inferior (barras/líneas parten de aquí) | `115` → `235` |
| `_BH` | altura máxima de barra | `100` → `200` |
| `y` de etiquetas de mes | texto bajo el eje | `133` → `258` |
| piso de líneas `MAX(floor,…)` | tope superior (valores ≥100%) | `MAX(15,…)` → `MAX(35,…)` |

El **ancho (x, spacing) NO se toca**. Al subir solo el alto del `viewBox`, el SVG a `width:100%` se
dibuja más alto conservando nitidez de texto y puntos. Complétalo con `flex:1` en la card para que
ocupe todo el alto disponible (§22).

---

## 26. Metodología de edición segura (QA por comillas + `grep`, sin compilar)

El compilador DAX **solo corre en Power BI Desktop**; valida ANTES contra el archivo `.tmdl`:

- **Paridad de comillas por medida**: cuenta los `"` del bloque de cada medida → debe ser **par**
  (string balanceado). Impar = string roto. También revisa el total del archivo.
- **Conteo de anclas antes de `replace_all`**: `grep -c` la subcadena y confirma que el nº de
  coincidencias es el esperado (y que **no** toca otras medidas, ej. la V2 con VARs gemelas).
- **Construcción por piezas**: arma RETURN largos concatenando fragmentos guardados en archivos
  temporales (topbar, cada card, cierres). Verifica el conteo de comillas de cada pieza: un
  fragmento que **abre** string sin cerrarlo es impar; el ensamblado final debe ser **par**.
- **VARs usadas vs definidas**: tras dividir/editar, extrae los `_var` del RETURN y confirma que
  TODOS están definidos como `VAR` — una VAR usada sin definir **bloquea la compilación**.
- **Indentación TMDL**: `measure` = 1 tab · `VAR`/`RETURN` = 3 tabs · propiedades
  (`displayFolder`/`lineageTag`) = 2 tabs. Una indentación mal puesta rompe el parseo.
- **Backup antes de cirugía grande**: copia `Medidas.tmdl` a `_backup/<timestamp>/` antes de
  dividir/reescribir medidas.

---

*Resumen en una frase: **una medida = una responsabilidad** (CSS / HTML / JS / JSON), se
ensamblan con `&`, lo pesado va a un visual aparte, el diseño se cambia solo en el CSS, el layout
se fija acotando la raíz (no `body`), y todo se valida por paridad de comillas y `grep` antes de
compilar en Desktop.*
