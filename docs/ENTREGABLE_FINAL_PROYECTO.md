# Entregable final del proyecto

## Executive Summary

- **La solucion queda preparada para pre-deploy controlado.** El usuario opera una sola entrada: el archivo crudo SAP MB51. Streamlit funciona como host/backend, mientras que la experiencia visible vive en HTML, CSS y JavaScript.
- **El flujo productivo separa scoring y entrenamiento.** La carga diaria usa el modelo activo versionado cuando existe; el reentrenamiento solo se ejecuta con un comando explicito y genera metadata auditable.
- **La revision operativa queda trazable.** Las alertas pueden marcarse como confirmadas, falsos positivos, problemas de datos o descartadas sin borrar datos fisicos; cada cambio queda en auditoria.
- **El seguimiento queda definido.** La operacion exporta metricas de calidad de datos, ejecucion, alertas, revision experta y estado del modelo para monitoreo de largo plazo.

## Objetivo y alcance

El objetivo de esta fase es cerrar una version pre-productiva que aplique buenas practicas de Data Science, UI/UX, CRUD operativo, despliegue y monitoreo. El sistema prioriza anomalias operativas de consumo, inventario, produccion, ICA y calidad de datos a partir de SAP MB51 y maestros configurados.

El alcance incluye:

- carga incremental idempotente de un MB51;
- validacion de estructura, fechas, fuente, duplicados y traslapes;
- scoring con reglas, modelo oficial y consenso de 4 capas;
- modelos sombra IF/LOF por edad como evidencia comparativa;
- dashboard HTML embebido en Streamlit;
- revision experta con auditoria;
- metricas operativas y documentacion de despliegue.

Queda fuera del alcance:

- borrado fisico de archivos crudos desde UI;
- publicacion de datos reales o payloads sensibles en repositorios publicos;
- reentrenamiento automatico no revisado;
- sustitucion del score oficial por modelos sombra sin validacion experta.

## Arquitectura operativa

```text
Usuario -> MB51 crudo
  -> Streamlit host
  -> componente HTML/CSS/JS
  -> validacion Python
  -> SQLite operacional
  -> cache MB51 deduplicado
  -> pipeline de features, reglas y scoring
  -> consenso de 4 capas y alertas
  -> dashboard HTML autocontenido
  -> revision experta y monitoreo
```

### Superficie de usuario

La UI visible vive en `streamlit_components/dashboard_shell/index.html`. El componente recibe un solo archivo MB51, muestra estado compacto y mantiene el dashboard visible. Streamlit no presenta controles nativos al usuario final; solo recibe eventos del shell HTML y ejecuta Python.

### Backend y persistencia

SQLite (`data/warehouse.db`) conserva:

- cargas y estado de ingesta;
- movimientos deduplicados;
- ejecuciones del pipeline;
- alertas generadas;
- revision manual vigente;
- auditoria de eventos de revision.

Los archivos crudos validos se copian como evidencia inmutable; los rechazados se guardan con motivo.

## Data Science y modelo

### Score oficial

El score oficial se mantiene como:

```text
score_anomalia = 65% score_reglas + 35% score_ml
```

Las reglas cubren desviaciones robustas, brechas contra politica, cambios abruptos, consumo cero, consumo negativo, consumo sin orden, fase multiple, conciliacion de stock y mortalidad alta.

### Modelo oficial

El modelo oficial es Isolation Forest con preprocesamiento por imputacion mediana y escalamiento robusto. En modo productivo (`model_lifecycle.mode = score_existing`) el sistema carga el artefacto activo configurado y calcula `score_ml`/`flag_ml`. Si el artefacto no existe, no entrena silenciosamente; registra estado `MODEL_MISSING` y conserva trazabilidad.

### Entrenamiento controlado

El entrenamiento se ejecuta solo con:

```powershell
python scripts/train_model.py
```

Ese comando fuerza `model_mode="train"`, regenera el pipeline, guarda el artefacto y escribe metadata con:

- version del modelo;
- fecha de generacion;
- features;
- parametros;
- filas elegibles;
- hash de datos de entrenamiento;
- rango de decision function;
- volumen de filas marcadas;
- estado de aprobacion;
- politica de promocion.

### Modelos sombra

Los modelos sombra por edad (Isolation Forest segmentado y LOF) se conservan como evidencia comparativa. No modifican el score oficial ni promueven alertas por si solos.

## Consenso de 4 capas

| Capa | Funcion | Ejemplos |
|---|---|---|
| 1. Calidad | Detectar problemas estructurales o conciliacion | consumo negativo, sin orden, diferencia de stock |
| 2. Estadistica robusta | Detectar extremos contra historial | z robusto, cambio abrupto |
| 3. Contextual | Contrastar contra edad, fase y operacion | brecha politica, consumo cero con aves, mortalidad alta |
| 4. Multivariada | Detectar combinaciones inusuales | Isolation Forest oficial |

La severidad de consenso puede elevar prioridad cuando varias capas coinciden, pero no degrada la severidad oficial.

## CRUD operativo

El CRUD se aplica sobre entidades operativas, no sobre archivos crudos.

| Operacion | Implementacion | Regla |
|---|---|---|
| Crear | carga MB51, revision experta | conserva auditoria |
| Leer | historial de cargas, alertas, modelo, ejecuciones | vistas acotadas en UI y exports |
| Actualizar | estado manual, comentario, usuario | registra estado anterior y nuevo |
| Eliminar | estado `DESCARTADA` | no borra fisicamente |

Estados de revision:

- `CONFIRMADA`;
- `FALSO_POSITIVO`;
- `PROBLEMA_DE_DATOS`;
- `DESCARTADA`.

## UI/UX

La experiencia se enfoca en decisiones operativas:

- una sola accion primaria: subir MB51;
- panel compacto que se despliega solo cuando hay carga, estado o revision;
- dashboard siempre visible;
- mensajes claros para validacion, rechazo, duplicado, sin registros nuevos y exito;
- panel operativo con metricas, estado del modelo y revision experta;
- sin controles tecnicos innecesarios para el usuario final.

## Metricas de seguimiento

### Calidad de datos

- cargas totales;
- cargas rechazadas;
- duplicados exactos;
- traslapes;
- registros nuevos;
- columnas faltantes o fuente no reconocida.

### Operacion

- resultado de la ultima ejecucion;
- fecha maxima cargada;
- duracion de carga/pipeline;
- errores de app;
- disponibilidad del dashboard.

### Modelo

- version activa;
- existencia de artefacto;
- estado de aprobacion;
- volumen de alertas;
- distribucion por severidad/familia;
- concentracion por caseta, edad, fase y ciclo;
- estabilidad de score y candidatos sombra.

### Revision experta

- alertas revisadas;
- confirmadas;
- falsos positivos;
- problemas de datos;
- descartadas;
- eventos de auditoria;
- tiempo entre alerta y revision cuando el proceso tenga usuarios nominales.

Las metricas operativas quedan en `outputs/latest/operational_metrics.json` y el manifiesto de ejecucion.

## Deploy y seguridad

El deploy se realiza desde la rama `deploy-dashboard-chencopo`. La rama `main` no se toca durante pruebas de publicacion.

Controles previos:

- usar `requirements.txt` como fuente de dependencias;
- evitar `uv.lock` en la rama de Streamlit Cloud;
- no versionar datos crudos reales;
- no publicar modelos privados;
- mantener `config/project.example.yml` seguro y documentado;
- revisar que `reports/dashboard.html` no exponga informacion no autorizada antes de publicarlo.

## Runbook resumido

### Pipeline productivo

```powershell
python -m granjas_anomalias.cli run --config config/project.yml
```

### Entrenamiento manual

```powershell
python scripts/train_model.py
```

### Validaciones

```powershell
uv run --with pytest --with pandas --with openpyxl pytest -q
python scripts/validar_dashboard_payload.py
python scripts/validar_dashboard_html.py
python -m streamlit run streamlit_app.py --server.headless true --server.port 8508 --server.address 127.0.0.1
```

### Rollback

1. Restaurar artefacto y metadata del modelo anterior.
2. Reejecutar pipeline en modo `score_existing`.
3. Validar alertas, payload y dashboard.
4. Registrar motivo del rollback en documentacion operativa.

## Criterios de aceptacion

- La app acepta un solo MB51 por carga.
- Las cargas duplicadas no duplican movimientos.
- El modelo productivo no reentrena automaticamente.
- El entrenamiento manual genera metadata.
- Las alertas conservan 4 capas y score oficial.
- La revision experta deja auditoria.
- Se generan metricas operativas.
- Las pruebas y validadores pasan.
- El deploy se hace desde `deploy-dashboard-chencopo`.

## Riesgos y mitigaciones

| Riesgo | Mitigacion |
|---|---|
| Modelo activo ausente en deploy | No entrenar en silencio; operar con estado visible y resolver promocion del artefacto |
| Datos SAP con nueva estructura | Rechazo con motivo y actualizacion controlada de alias/reglas |
| Exceso de alertas | Monitorear volumen, severidad y confirmacion experta |
| Publicacion de datos sensibles | Revisar `.gitignore`, payloads y configuracion antes de push |
| Cambios no auditados en revision | Usar `alertas_revision_eventos` como bitacora |

## Siguientes pasos

1. Ejecutar validacion completa pre-deploy.
2. Revisar con responsable de negocio los estados de revision experta.
3. Definir politica de promocion del primer modelo activo.
4. Establecer cadencia de monitoreo y umbrales de drift.
5. Congelar una version candidata para despliegue controlado.
