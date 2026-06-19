# Metodología de detección de anomalías

## Taxonomía

1. **Cantidad:** consumo demasiado alto, bajo, negativo o cero.
2. **Cambio:** salto abrupto respecto al día anterior o historial móvil.
3. **Política:** brecha contra consumo esperado por edad y aves.
4. **Asignación:** consumo sin orden, orden fuera del maestro o ciclo incorrecto.
5. **Fase:** más de una fase simultánea o transición no explicada.
6. **Inventario:** diferencia de conciliación o stock negativo.
7. **Temporal:** consumo antes del inicio biológico o después del cierre.
8. **Estructural SAP:** combinación material/movimiento/evento no clasificada.

## Fase 1 - reglas explicables

Se utilizan umbrales, z-score robusto con mediana/MAD, cambios diarios, brechas contra política y controles de integridad. Cada regla suma puntos a un score de 0 a 100.

## Baseline no supervisado

Isolation Forest aprende patrones multivariables sin requerir etiquetas. Se entrena con variables de consumo por ave, brecha de política, cambio diario, comportamiento móvil, mortalidad, producción y edad.

## Interpretación

Una anomalía es una señal para revisión. La salida conserva fecha, ciclo, caseta, orden, movimiento SAP y motivo para que operación pueda confirmar o descartar.

## Fase 2

La Fase 2 debe comparar el baseline contra otros enfoques no supervisados, validar estabilidad temporal, revisar top-N alertas y documentar feedback experto antes de seleccionar un candidato.
