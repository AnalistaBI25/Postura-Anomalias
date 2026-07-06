# Fase 2 - Investigación y selección del modelo de anomalías

## Estado

Pendiente. La Fase 2 debe ejecutarse como investigación no supervisada y validación experta. No reemplaza el pipeline productivo de Fase 1 hasta seleccionar y validar un candidato.

### Avance experimental actual

El pipeline calcula dos señales sombra segmentadas por edad: Isolation Forest y
Local Outlier Factor (LOF), con bandas 16-30, 31-55 y 56+ semanas. El dashboard
las presenta junto al Isolation Forest global y al score oficial para comparar
coincidencias, candidatos exclusivos y volumen de revisión. Estas señales no
participan en `score_anomalia`; su propósito es reunir evidencia y etiquetas
expertas antes de cualquier promoción.

## Objetivo

Comparar enfoques no supervisados para priorizar posibles anomalías de consumo, inventario, movimientos de alimento y comportamiento productivo sin depender de etiquetas reales inexistentes o incompletas.

## Hipótesis

- Las anomalías útiles deben ser raras, explicables y consistentes con la operación.
- Un modelo no supervisado debe complementar reglas de negocio, no sustituirlas.
- La revisión experta es necesaria para separar evento operativo legítimo, captura tardía, ajuste SAP, error de dato y anomalía real.

## Unidad de análisis

La unidad primaria propuesta es día-ciclo-caseta, usando la salida `data/processed/10_features_y_scores_diarios.csv`. Para revisiones específicas puede agregarse por ciclo, semana, fase alimenticia o material.

## Variables candidatas

Variables ya disponibles o derivables:

- consumo real y estándar;
- consumo por ave;
- brecha contra política;
- z-score robusto;
- cambio diario;
- promedio y desviación móvil;
- mortalidad por mil;
- producción contra estándar;
- edad semana y día;
- fases activas;
- stock global;
- entradas de alimento;
- diferencia de conciliación;
- flags de reglas;
- score de reglas.

No usar identificadores como orden, documento SAP o lote como variables predictivas si inducen fuga o memorización.

## Revisión del baseline

El baseline actual está en `models.py`:

- algoritmo: `IsolationForest`;
- preprocesamiento: `SimpleImputer(strategy="median")` y `RobustScaler`;
- elegibilidad: aves disponibles, consumo no negativo y días desde inicio suficientes;
- features: `MODEL_FEATURES`;
- salida: `score_ml` y `flag_ml`;
- artefactos: `models/isolation_forest_consumo.joblib` y metadata;
- integración: combinación con reglas mediante `combine_scores`.

Debe evaluarse como punto de partida, no como modelo final.

## Modelos candidatos

- Reglas robustas y estadísticas por segmento.
- Isolation Forest.
- Local Outlier Factor.
- One-Class SVM como opción exploratoria si el volumen y escalamiento lo permiten.
- Ensambles de acuerdo entre modelos.

## Metodología de experimentación

1. Cargar `10_features_y_scores_diarios.csv` sin modificar datos productivos.
2. Validar columnas, nulos, rangos y tipos.
3. Separar entrenamiento y análisis por tiempo o ciclo.
4. Definir segmentos por caseta, ciclo, edad y fase.
5. Reproducir baseline actual.
6. Entrenar modelos candidatos con diferentes parámetros.
7. Medir estabilidad entre semillas y sensibilidad a contaminación.
8. Comparar top-N alertas por modelo.
9. Revisar explicabilidad con variables dominantes y reglas activadas.
10. Preparar muestra para revisión experta.

## Evaluación sin etiquetas

No usar accuracy, precision, recall, F1 ni matriz de confusión como métricas principales sin etiquetas. Usar:

- estabilidad temporal;
- concentración de alertas;
- acuerdo entre modelos;
- consistencia por ciclo y fase;
- robustez ante perturbaciones sintéticas;
- proporción de alertas revisables por operación;
- explicabilidad y trazabilidad;
- tasa de alertas por ventana.

## Validación temporal

La validación debe respetar la secuencia del proceso. Evitar split aleatorio simple. Priorizar cortes por fecha, ciclo completo o bloques temporales.

## Perturbaciones sintéticas

Crear escenarios controlados en copias de trabajo:

- consumo artificialmente alto o bajo;
- consumo cero con aves;
- cambios abruptos;
- stock inconsistente;
- fase múltiple;
- mortalidad elevada.

Estos casos sirven para validar sensibilidad, no para entrenar con datos inventados como verdad.

## Revisión experta

La salida debe generar un paquete top-N con fecha, ciclo, caseta, edad, fase, consumo, estándar, score, motivo y contexto suficiente para que negocio clasifique el caso.

## Criterios de selección

Un modelo candidato debe:

- producir alertas explicables;
- ser estable entre semillas;
- no depender de identificadores sensibles;
- mantener volumen de alertas operativo;
- detectar perturbaciones sintéticas razonables;
- aportar valor adicional sobre reglas;
- poder integrarse al pipeline sin romper Fase 1;
- contar con aceptación experta documentada.

## Riesgos

- Fuga de información temporal.
- Sobreajuste a ciclos específicos.
- Alertas por cambios legítimos de operación.
- Sensibilidad excesiva a parámetros.
- Baja explicabilidad para usuarios de negocio.
- Publicación accidental de datos reales en notebooks.

## Entregables

- Notebook reproducible de experimentación.
- Comparación de modelos y parámetros.
- Tabla de top-N alertas para revisión.
- Recomendación de modelo candidato.
- Criterios de promoción a producción.
- Propuesta de etiquetas futuras.

## Criterios de cierre

- Baseline actual reproducido.
- Al menos dos enfoques comparados contra reglas.
- Validación temporal documentada.
- Revisión experta aplicada a una muestra.
- Modelo candidato seleccionado o descarte justificado.
- Riesgos y pasos a Fase 3 definidos.

## Etiquetas futuras

La plantilla `reports/tables/05_plantilla_validacion_anomalias.csv` debe enriquecerse con etiquetas revisadas por operación. Cuando exista volumen suficiente y consistencia de criterios, podrá evaluarse una etapa supervisada posterior.
