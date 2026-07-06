# Rendimiento y complejidad Big O

Mediciones reales (no intuición): `agents/agent_rendimiento.py`, log del
pipeline (`logs/pipeline.log`) y benchmarks sintéticos. Equipo de referencia:
Windows 11, Python 3.12. Datos actuales: kardex de **46,755 movimientos**
(42,900 en ventana de análisis), 6 ciclos, 1,965 días-ciclo.

## Tiempo medido por etapa (última corrida completa, 42.9k filas)

| Etapa | Tiempo | % |
|---|---:|---:|
| 1–4 · Carga, normalización, clasificación, calidad | ~1 s | 8% |
| 5–6 · Ciclos + línea diaria/semanal | ~1 s | 8% |
| 7 · Stock global | ~1 s | 8% |
| 8–9 · Features, reglas, IF + sombra, consenso | ~2 s | 17% |
| 9b · Cobertura + alertas | <1 s | ~4% |
| **10 · EDA + dashboard (figuras + payload + HTML)** | **6 s** | **50%** |
| 11 · Manifiesto + exportación outputs | ~1 s | 8% |
| **Total** | **~12 s** | 100% |

El cuello de botella es la generación de figuras/EDA y el payload del
dashboard, no el procesamiento de datos. A este tamaño **no se justifica
optimizar**: el costo de una corrida completa es de segundos.

## Complejidad por proceso (n = movimientos; d = días; c = ciclos)

| Proceso | Operación dominante | Tiempo | Espacio | Evidencia |
|---|---|---|---|---|
| Lectura Excel MB51 | parse openpyxl | O(n) constante alto | O(n) | 12 MB xlsx ≈ decenas de s; por eso existe cache CSV (s) |
| Normalización | operaciones vectorizadas + `map(parse)` | O(n) | O(n) | 10x datos → 9.3x tiempo |
| Llave de negocio + ocurrencia | concat string + `groupby.cumcount` + sha256 | O(n) | O(n) | 10x → 9.8x |
| Inserción SQLite | `executemany` + índice único | O(n log n) | O(1) extra | 100k en 3.4 s; reingesta idempotente 1.7 s |
| Clasificación SAP | máscaras vectorizadas | O(n) | O(n) | <1 s a 43k |
| Ciclos | groupby por caseta/lote | O(n) | O(c) | <1 s |
| Línea diaria | merge/groupby por ciclo-día | O(n + d·c) | O(d·c) | <1 s (1,965 filas) |
| Stock diario | cumsum por material | O(d·m) | O(d·m) | <1 s |
| Features móviles | rolling por ciclo | O(d·c·w) w=ventana | O(d·c) | <1 s |
| Isolation Forest | entrenamiento 400 árboles | O(t·s·log s) | O(t·s) | ~2 s |
| Cobertura | rolling + flags por material | O(d·m) | O(d·m) | <1 s |
| Alertas + ciclo de vida | groupby + lookup SQLite | O(a) | O(a) | <1 s |
| Dashboard payload + HTML | serialización JSON + template | O(d·c) | O(payload) | ~6 s, archivo ~15 MB |

## Escalabilidad medida (síntesis de `pruebas_rendimiento.md`)

| Filas | ≈ escala | normalizar | llaves | pico RAM (normalizar) |
|---:|---:|---:|---:|---:|
| 50,000 | 1x | 2.5 s | 2.0 s | 37 MB |
| 100,000 | 2x | 5.0 s | 3.9 s | 75 MB |
| 250,000 | 5x | 11.8 s | 9.5 s | 188 MB |
| 500,000 | 10x | 23.3 s | 19.7 s | 376 MB |

Crecimiento lineal en tiempo y memoria (10x datos → 9.3–9.8x tiempo). Con el
límite de carga de 100 MB y archivos anuales (~23k filas/año por granja), el
diseño soporta holgadamente varios años y varias granjas.

## Deuda de diseño conocida (aceptada y documentada)

1. **Recalculo completo por corrida**: el pipeline es O(historial), no
   O(incremento). A 12 s por corrida es la opción correcta (simplicidad +
   reproducibilidad). Umbral de reevaluación: cuando una corrida supere ~2 min
   (≈ 400–500k filas), recomputar solo ciclos activos.
2. **`_ops_status` lee todas las alertas** de todas las corridas en cada rerun
   de Streamlit: O(corridas·alertas). Hoy ~10 alertas/corrida; filtrar por
   última corrida en SQL cuando el historial crezca (>10k filas).
3. **Optimizaciones descartadas por no medibles aquí**: cambiar pandas por
   polars/duckdb, paralelizar, categorías de pandas — el cuello (6 s de
   dashboard) no se beneficia y agregarían mantenimiento sin evidencia.
