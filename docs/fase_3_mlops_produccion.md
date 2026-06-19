# Fase 3 - MLOps, producción y despliegue

## Estado

Futura. Inicia solo después de cerrar la Fase 2 con un modelo candidato validado y criterios operativos aceptados.

## Objetivo

Industrializar entrenamiento, scoring, monitoreo y retroalimentación humana para operar un modelo de anomalías de forma controlada, auditable y mantenible.

## Arquitectura propuesta

```text
Fuentes controladas
  -> validación de datos
  -> generación de features
  -> entrenamiento versionado
  -> registro de modelo
  -> scoring batch
  -> alertas y dashboard
  -> revisión experta
  -> monitoreo y reentrenamiento
```

## Entrenamiento

- Separar código de entrenamiento de código de scoring.
- Congelar ventanas de entrenamiento.
- Registrar parámetros, features, versión de datos y métricas no supervisadas.
- Guardar artefactos y metadata.
- Usar validación temporal y criterios definidos en Fase 2.

## Scoring

- Ejecutar con datos nuevos validados.
- Reutilizar el mismo preprocesamiento del entrenamiento.
- Guardar score, severidad, motivos y versión de modelo.
- No sobrescribir predicciones históricas sin trazabilidad.

## Registro y versionamiento

Versionar:

- datasets de entrenamiento o hashes;
- definición de features;
- parámetros;
- artefacto de modelo;
- código;
- configuración;
- resultados de validación experta.

## Ambientes

Separar al menos:

- desarrollo;
- validación;
- producción.

Cada ambiente debe tener configuración propia y controles de acceso.

## Pruebas antes del despliegue

- Pruebas unitarias del pipeline.
- Pruebas de esquema de datos.
- Pruebas de compatibilidad de features.
- Pruebas de serialización del modelo.
- Pruebas de volumen de alertas.
- Validación del dashboard o consumo downstream.

## Despliegue

La primera versión productiva debería ser batch y controlada. Una operación más frecuente solo debe considerarse si el negocio define latencia, responsables y acuerdos de servicio.

## Monitoreo

Monitorear:

- calidad de datos;
- nulos y rangos;
- distribución de variables;
- drift;
- estabilidad del score;
- volumen de alertas;
- concentración por ciclo, caseta, edad o fase;
- tiempos de revisión;
- tasa de confirmación experta.

## Deriva y reentrenamiento

Definir umbrales de deriva y reglas de reentrenamiento. El reentrenamiento no debe ser automático sin revisión; debe producir una versión nueva y comparable contra la versión activa.

## Auditoría y rollback

Cada predicción debe conservar:

- fecha de scoring;
- versión de código;
- versión de modelo;
- configuración;
- features principales;
- score;
- motivo;
- estado de revisión.

Debe existir rollback a la versión anterior si el modelo nuevo degrada operación o genera alertas no confiables.

## Seguridad

- No exponer datos reales en repositorios públicos.
- No publicar dashboards con payload real.
- Controlar acceso a modelos y salidas.
- Anonimizar o sintetizar datos para demostraciones.
- Evitar credenciales en configuración versionable.

## Responsables

Definir responsables por:

- extracción de fuentes;
- operación del pipeline;
- revisión de alertas;
- aprobación de modelos;
- monitoreo;
- respuesta ante incidentes.

## Criterios de entrada

- Fase 2 cerrada con modelo candidato.
- Criterios de aceptación documentados.
- Validación experta mínima.
- Pipeline de Fase 1 estable.
- Política de seguridad y datos aprobada.

## Criterios de salida

- Scoring reproducible.
- Modelo versionado.
- Monitoreo activo.
- Dashboard o salida operativa integrada.
- Proceso de revisión experta.
- Procedimiento de rollback.
- Runbook productivo.

## Entregables

- Pipeline de entrenamiento.
- Pipeline de scoring.
- Registro de experimentos/modelos.
- Validadores de datos y features.
- Monitoreo de drift y alertas.
- Dashboard productivo o integración BI.
- Documentación operativa y auditoría.
