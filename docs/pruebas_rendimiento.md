# Pruebas de rendimiento y escalabilidad

Protocolo reproducible: `python -m agents.orquestador` ejecuta el agente
`revisor_rendimiento`, que genera datos sintéticos MB51 (sin datos sensibles)
y mide las rutas críticas. Resultados en
`reports/agentes/<timestamp>/revisor_rendimiento.json`.

## Matriz de escalabilidad (medida 2026-07-06)

Referencia: el kardex real actual tiene 46,755 filas (~12.7 MB xlsx).

| Escenario | Filas | normalizar_mb51 | calcular_llaves | Pico RAM | Resultado |
|---|---:|---:|---:|---:|---|
| 1x (actual) | 50,000 | 2.5 s | 2.0 s | 37 MB | ✅ |
| 2x | 100,000 | 5.0 s | 3.9 s | 75 MB | ✅ |
| 5x | 250,000 | 11.8 s | 9.5 s | 188 MB | ✅ |
| 10x | 500,000 | 23.3 s | 19.7 s | 376 MB | ✅ lineal |

SQLite (índice único de llave de negocio):

| Operación | Filas | Tiempo |
|---|---:|---:|
| Inserción inicial | 100,000 | 3.4 s |
| Reingesta idempotente (todo duplicado) | 100,000 | 1.7 s |

Pipeline completo con datos reales (del log, corrida `20260706_102702`):
**12 s** de kardex a dashboard (ver desglose en `rendimiento_big_o.md`).

## Límites operativos iniciales

| Límite | Valor | Fundamento | Acción al excederlo |
|---|---|---|---|
| Tamaño máximo de archivo | 100 MB (`max_file_mb` + `maxUploadSize`) | validado en ingesta y en servidor | rechazo con mensaje; dividir la exportación por periodo |
| Filas por carga recomendadas | ≤ 500,000 | escalado lineal medido hasta ahí | dividir por rango de fechas |
| Tiempo de corrida aceptable | ≤ 2 min | operación interactiva desde la UI | revisar etapa dominante; recomputo parcial |
| Memoria de proceso | ≤ 1 GB | 10x datos ≈ 376 MB pico en la etapa más pesada | procesar por bloques (chunking) |
| Concurrencia | 1 carga a la vez | eventos serializados por `eventId` en la app | esperar; escalar a servidor propio si se requiere multiusuario |

## Casos de entrada probados (suite `pytest`, 107 pruebas)

Cubiertos con fixtures sintéticos (sin datos sensibles): archivo válido,
duplicado exacto (hash), periodo traslapado, columnas faltantes, extensión
inválida, archivo vacío, sin fechas válidas, fechas futuras, duplicados
legítimos (ocurrencia), reporte mensual no soportado, consumo cero, stock
negativo, inventario cero con aves, historia insuficiente, ICA con denominador
cero (semana no evaluable), ciclo de vida de alertas y revisión manual.

Pendientes que requieren archivos reales del negocio: centros/almacenes/
materiales nuevos de otras granjas y unidades distintas de KG/UN
(documentado en `docs/limitaciones.md`).
