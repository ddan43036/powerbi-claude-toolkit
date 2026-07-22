# Cómo evolucionar los agentes y skills de este toolkit

Guía de mantenimiento para mejorar agentes/skills con eficiencia de tokens, basada en las **fuentes
oficiales de Anthropic** (verificadas el 2026-06-20). Úsala al crear/editar cualquier `SKILL.md`,
agente o `reference/*.md` del toolkit.

## Principios oficiales (resumen accionable)

1. **Progressive disclosure.** Solo los `name`+`description` de cada skill se precargan; el `SKILL.md`
   se lee al activarse y los `reference/*.md` solo cuando se necesitan. → Mantén `SKILL.md` corto y
   mueve el detalle a `reference/`. (Skill best practices.)
2. **Conciso = clave.** El contexto es un bien común. No expliques lo que el modelo ya sabe; cada
   párrafo debe justificar su costo de tokens.
3. **`SKILL.md` < 500 líneas**; si crece, divídelo en `reference/`. **Referencias a 1 nivel** desde
   el `SKILL.md` (no anidar refs dentro de refs). Archivos de referencia > 100 líneas → con índice.
4. **Descripciones específicas, en 3ª persona, con qué + cuándo + disparadores.** Es lo que decide
   el discovery. Evita "ayuda con documentos"; usa "Hace X; usar cuando Y / al mencionar Z".
5. **Grados de libertad según fragilidad.** Tarea con un solo camino seguro (p. ej. escribir
   report.json) → instrucciones/scripts exactos (baja libertad). Tarea con varios caminos → guía
   general (alta libertad).
6. **Subagentes:** contexto aislado + `tools` mínimas por rol + **devolver solo el resumen** (no
   volcar archivos). Descripción clara para auto-delegación. Modelos baratos (Haiku) para tareas
   mecánicas. (Custom subagents.)
7. **Scripts > pedir código.** Para operaciones deterministas/frágiles, un script es más fiable y
   ahorra tokens (su salida es lo único que entra al contexto). Maneja errores en el script, no
   "punt" al modelo; nada de "voodoo constants".
8. **Eval-first + iterar con uso real.** Define 3 casos de prueba ANTES de documentar; observa cómo
   el agente usa la skill en tareas reales y refina (no por suposiciones). Rutas Unix (`/`), sin
   info con fecha de caducidad, terminología consistente.

## Mapa principio → este toolkit

| Principio | Cómo se aplica aquí |
|---|---|
| Progressive disclosure | `SKILL.md` cortos; el detalle vive en `report-json-visuals/reference/*` y `tmdl-model/reference/*`; `CLAUDE.md` apunta a ellos sin duplicar. |
| Conciso / < 500 líneas | Recortar `CLAUDE.md` (se carga cada sesión) y los `SKILL.md`; ejemplos largos → `reference/`. |
| Scripts deterministas | TODO archivo grande (`report.json`, `*.tmdl`) se toca vía scripts Python; el modelo solo ve resúmenes. |
| Subagentes con tools mínimas + resumen | `pbi-model-analyst` (RO+Bash/Write), `pbi-report-designer` (RO+Write/Bash), `pbi-report-writer` (Read/Write/Edit/Bash), `pbi-report-editor` (Read/Bash), `pbi-validator` (Read/Bash). DoD compacto = "Contrato de brevedad" de `CLAUDE.md`. |
| Token-light en MODIFICAR | `report_anatomy.py --find` localiza; `edit_visual.py` parchea nativos; `apply_measures.py` edita medidas HTML. |
| Eval-first | Cada cambio se prueba con Python real sobre proyectos de referencia (CdP, GESPRO) antes de cerrar la ronda. |

## Checklist al crear/editar una skill o agente
- [ ] `description` en 3ª persona, específica, con qué + cuándo + disparadores.
- [ ] `SKILL.md`/agente corto y accionable; detalle largo → `reference/` (1 nivel).
- [ ] El agente NO relee archivos grandes; confía en `catalog.json`/`anatomy.json`/resúmenes.
- [ ] `tools:` mínimas para el rol; devuelve SOLO el resumen (DoD compacto).
- [ ] Operaciones frágiles/repetitivas → script Python (no generar código al vuelo).
- [ ] Sin referencias a skills externas (toolkit autocontenido); sin fechas que caduquen.
- [ ] Probado con Python real sobre un proyecto de referencia.

## Ciclo de mejora continua
1. Usa el toolkit en una tarea real; observa dónde el agente duda, relee de más o falla.
2. Registra el caso (p. ej. en `tmdl-model/reference/ERRORES-COMPILACION-DAX.md`).
3. Ajusta la skill/agente/reglas (mover detalle, reforzar una regla, acortar).
4. Re-prueba con Python real; mide tokens y correctitud, no suposiciones.

## Fuentes oficiales (Anthropic / GitHub anthropics) — verificadas 2026-06-20
- Skill authoring best practices — https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Create custom subagents (Claude Code) — https://code.claude.com/docs/en/sub-agents
- Equipping agents for the real world with Agent Skills — https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Writing effective tools for AI agents — https://www.anthropic.com/engineering/writing-tools-for-agents
- Agent Skills (repo oficial) — https://github.com/anthropics/skills
- Claude Code docs — https://code.claude.com/docs

> Nota: los dominios `docs.claude.com`/`docs.anthropic.com` redirigen a `platform.claude.com` y
> `code.claude.com`. Verifica las URLs al actualizar esta guía.
