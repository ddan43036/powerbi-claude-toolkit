# Cómo el toolkit LEE y EDITA un tablero (guía para el equipo)

Guía práctica para entender **qué hace la herramienta cuando lee un proyecto y cuando le pides un
cambio**. No cubre la creación de tableros desde cero (eso está en `README.md` / `CLAUDE.md`); aquí
solo **leer (analizar)** y **editar (modificar por prompt)**.

---

## 1. En una frase

Editas un tablero **Power BI PBIP** hablándole a Claude Code en lenguaje natural
("cambia el color de las barras a rojo"). La herramienta **localiza** lo que pediste, **aplica solo
ese cambio** con un script Python (con copia de seguridad) y lo **valida** — sin cargar los archivos
gigantes, así gasta pocos tokens.

## 2. Qué toca (dos capas del proyecto)

- **Informe → `*.Report/report.json`** (un solo archivo): los **visuales** (gráficos, tarjetas,
  slicers, tablas, paneles HTML). Es lo que se inserta/edita.
- **Modelo → `*.SemanticModel/definition/*.tmdl`**: las **medidas** DAX (incluidas las que generan
  HTML, `M_CSS_/M_HTML_/M_JS_/M_JSON_`).

> **PBIP = el proyecto** (carpetas `.Report` + `.SemanticModel`). No confundir con "PBIR"
> (una forma de guardar el informe carpeta-por-visual). El toolkit **edita el `report.json` único**.

## 3. Idea clave (por qué es seguro y barato en tokens)

- **Nunca** carga `report.json` ni los `.tmdl` completos al contexto de la IA: los **lee y edita un
  script Python**; el modelo solo ve un **resumen corto**.
- **Copia de seguridad siempre** (`.bak`) antes de tocar, y **round-trip** (re-lee el archivo para
  confirmar que quedó válido).
- **La verificación visual la haces tú** abriendo Power BI Desktop: que el JSON sea válido no
  garantiza que se vea bien.

---

## 4. Cómo LEE (analizar) — solo lectura

Produce artefactos compactos que luego se reutilizan (no se relee lo grande):

| Script | Qué hace | Salida |
|---|---|---|
| `model_catalog.py` | Indexa el modelo TMDL | `catalog.json`: tablas/columnas/medidas, roles (dim/hecho/tiempo), formatos, estrategia de traducción, medidas HTML |
| `report_anatomy.py` | Radiografía del informe (funciona con `report.json` o carpeta-por-visual) | `anatomy.json` (inventario por página) + `skeletons/` |
| `report_anatomy.py --find "<texto\|id\|tipo>"` | **Localiza** un visual puntual | solo el/los visuales que coinciden (id, tipo, posición, campos, título) |

Con esto, la IA "sabe" qué existe y dónde está **sin abrir el archivo enorme**.

---

## 5. Cómo EDITA (modificar por prompt) — el foco

Le pides el cambio en lenguaje natural y lo resuelve el agente **`pbi-report-editor`**:

```
Tu prompt: "cambia el color de las barras del ranking a rojo"
        │
        ▼
1) ¿Python disponible?  (si falta, te ofrece instalarlo; si dices no, se detiene)
2) LOCALIZA     report_anatomy.py --find "ranking"     → id + estado actual
3) CLASIFICA    ¿es NATIVO o HTML?
        ├── NATIVO (gráfico/slicer/tarjeta/tabla: color, título, posición, campo)
        │        → edit_visual.py  (parche puntual por selector)
        └── HTML (contenido/estilo/lógica de un panel HTML ← medida M_*)
                 → apply_measures.py  (edita la submedida: M_CSS_/M_JS_/M_HTMLBody_/M_JSON_)
4) APLICA       cambio mínimo + copia .bak
5) VALIDA       validate_report.py
        │
        ▼
Te devuelve: "qué cambió + ruta del backup + apto/no apto" → abre Desktop para ver
```

### 5.1 Cambios NATIVOS (`edit_visual.py`)
Selecciona el visual por **id**, **título** o **tipo+página** y cambia:
- **Título** (texto fijo o una **medida** de traducción).
- **Colores**: de datos (paleta del tema o hex), de **slicer** (fondo/texto), **fondo del lienzo** (página).
- **Posición / tamaño** (x, y, ancho, alto).
- Propiedad avanzada (`objects.<grupo>.<prop>`).

### 5.2 Cambios HTML (`apply_measures.py`)
Un panel HTML está hecho de **medidas separadas por responsabilidad** (una para el CSS, otra para el
JS, otra para los datos JSON, otra para la estructura, y una consolidadora que las ensambla). Para
modificarlo se edita **solo la submedida** correspondiente (es pequeña → barato). Reglas en
`.claude/skills/report-json-visuals/reference/html-in-dax.md` y `.../tmdl-model/reference/dax-authoring.md`.

### 5.3 Ejemplos de prompts
- "Cambia el color de las barras del ranking a rojo." → nativo, color de datos.
- "Ponle título 'Adherencia por proceso' al gráfico X." → nativo, título.
- "Mueve el KPI de adherencia 200px a la derecha." → nativo, posición.
- "Fondo del lienzo azul oscuro y texto de los slicers en blanco." → nativo, lienzo + slicer.
- "En el panel HTML de resumen, cambia el color de las tarjetas." → HTML, editar `M_CSS_*`.

---

## 6. Reglas fijas que conviene saber

- **Slicers/filtros son SIEMPRE visuales nativos** (nunca HTML), en cualquier tablero.
- **Un cambio = una edición mínima**: no recrea la página; toca solo lo pedido.
- **Autocontenido**: no usa skills externas; las reglas DAX/HTML viven en `reference/*.md`.
- Si el informe está guardado **carpeta-por-visual**, la herramienta lo **analiza** pero para
  **editar** necesita el `report.json` único (guardarlo en ese formato en Desktop).

## 7. Seguridad / reversibilidad

- Antes de cualquier escritura se crea `report.json.bak` / `Medidas.tmdl.bak`.
- Si la validación marca algo **bloqueante**, se restaura desde `.bak` y se reporta.
- Nada se aplica "a ciegas": el editor enuncia el cambio; ante ambigüedad, pregunta.

## 8. Glosario corto

| Término | Qué es |
|---|---|
| `report.json` | El informe (todas las páginas y visuales) en un archivo |
| `*.tmdl` | Definición del modelo/medidas (capa de datos) |
| `catalog.json` | Resumen del modelo (lo que la IA lee en vez del TMDL) |
| `anatomy.json` | Radiografía del informe (visuales, posiciones, títulos) |
| medida `M_*` | Medida DAX que genera HTML/CSS/JS/JSON para un panel |
| `ThemeDataColor` | Color tomado de la paleta del tema del informe |
| `.bak` | Copia de seguridad automática antes de editar |

> ¿Necesitas **crear** un tablero de cero (no solo editar)? Eso usa `intent.yaml` + los agentes de
> diseño; está documentado en `README.md` y `CLAUDE.md`.
