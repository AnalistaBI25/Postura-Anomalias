# Evaluación del sistema de agentes

Tres corridas completas del orquestador el 2026-07-06 sobre la rama
`deploy-dashboard-chencopo` (Fase 1, solo lectura).

## Resultados por corrida

| Métrica | Corrida 1 (`_143339`) | Corrida 2 (`_144309`) | Corrida 3 (`_145319`, final) |
|---|---:|---:|---:|
| Agentes ejecutados | 8/8 OK | 8/8 OK | 8/8 OK |
| Hallazgos totales | 40 | 41 | 41 |
| critical / high / medium / low | 1 / 6 / 6 / 6 | 1 / 3 / 5 / 5 | 1 / 3 / 4 / 4 |
| Falsos positivos detectados | **3 high** (ver abajo) | 0 conocidos | 0 conocidos |
| pytest reportado | exit 0 (conteo no capturado) | exit 0 (conteo no capturado) | **107 passed, 0 failed** |
| Consistencia del payload | no evaluada (estructura) | parcial | **stock final 7,185.0 = 7,185.0 kg (0.0)** |
| Duración total | ~41 s | ~2 min (benchmark 10x) | ~2 min |
| Costo computacional | local, sin servicios externos | ídem | ídem |

Los hallazgos no informativos de la corrida 3 son exactamente las decisiones
de negocio y deudas documentadas en `plan_mejoras.md` (repo público, falta de
autenticación, nulos de almacén, nube efímera, outputs versionados y 4 bajos),
más el árbol con los archivos nuevos de esta misma revisión aún sin commitear.

## Falsos positivos de la corrida 1 (confirmados y corregidos)

Los tres hallazgos "high" del revisor DS resultaron ser errores del *validador*
(supuestos de ventana/fórmula), no del pipeline. Se confirmaron contra la
fuente y se corrigió el agente:

1. **Consumo neto (desvío 1.04%)** — el agente comparaba desde la preventana
   de análisis; el stock inicia en el ancla MB5B. Alineando ventanas:
   795,890 vs 795,890 kg (0.0000%).
2. **Entradas netas (3.18%)** — misma causa; 832,190 vs 832,190 kg (0.0000%).
3. **ICA semanal (desvío máx 996)** — el agente usaba
   `consumo_real/produccion_real`; la definición documentada es
   `consumo_productivo/produccion_productiva` (excluye arranque). Con la
   fórmula correcta: desvío máx 0.0000 en 258 semanas.

Lección incorporada: los agentes de validación deben usar las definiciones de
negocio documentadas, y todo hallazgo cuantitativo se confirma contra la
fuente antes de tratarse como defecto (regla ya reflejada en el flujo: la
corrida 1 nunca se presentó como veredicto).

## Métricas de evaluación (definidas y medidas)

| Métrica | Valor | Fórmula |
|---|---:|---|
| Hallazgos confirmados | 16/19 no-info (84%) | confirmados / no-info emitidos (corrida 1) |
| Tasa de falsos positivos | 3/19 (16%) corrida 1 → 0 conocidos corrida 2 | FP / no-info |
| Falsos negativos conocidos | 0 detectados por revisión humana posterior | — |
| Cobertura de archivos | git ls-files completo + módulos críticos | — |
| Consistencia entre corridas | hallazgos estables módulo correcciones | comparación 1 vs 2 |
| Recomendaciones aplicadas | 2 (`.streamlit/config.toml`, correcciones del validador) | — |
| Recomendaciones que requieren negocio | 5 (`requires_business_validation`) | — |
| Regresiones introducidas por agentes | 0 (no escriben código) | — |
| Tiempo humano ahorrado (estimado) | conciliación de 8 KPIs + escaneo de secretos + inventario docs por corrida | cualitativo |

## Cuándo NO se usaron agentes (cumplido)

No decidieron reglas de negocio (los umbrales siguen en YAML con dueño
humano), no aprobaron resultados, no hicieron merge/push/deploy, no eliminaron
registros, no tocaron datos crudos ni credenciales, y no sustituyen a las 107
pruebas deterministas: las ejecutan y las reportan.
