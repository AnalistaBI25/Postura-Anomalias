# Diccionario de datos

Este diccionario describe estructuras principales del proyecto sin valores reales.

## Datos de entrada

### Kardex MB51

Columnas esperadas por `io.py` y normalizadas por `normalize.py`:

- material;
- descripción de material;
- centro;
- almacén;
- lote;
- documento material;
- cantidades y unidades;
- clase de movimiento;
- texto de movimiento;
- fecha de contabilización;
- referencia;
- usuario;
- orden;
- centro receptor;
- clase de transacción/evento;
- indicador debe/haber;
- textos de cabecera y posición;
- motivo de movimiento.

### Estándar productivo

Preparado por `standards.py`. Incluye semana de edad, consumo, producción, peso de huevo, ICA, mortalidad acumulada, viabilidad y peso corporal.

### Organización y materiales

Normalizados por `normalize_organization`. Incluyen centro, granja, módulo, almacén/caseta, orden y catálogo de materiales cuando existen en la fuente.

### MB5B

Fuente opcional para ancla de inventario inicial.

## Datos intermedios

### `01_kardex_normalizado_clasificado.csv`

Incluye llaves normalizadas, fechas, cantidades, bloque de material, rol de movimiento, regla aplicada, métricas netas de aves, consumo, producción y stock.

### `02_organizacion_normalizada.csv`

Maestro de organización normalizado.

### `03_materiales_normalizados.csv`

Catálogo de materiales normalizado.

## Datos procesados

### `04_politica_preparada.csv`

Política productiva semanal con columnas canónicas y métricas calculadas.

### `05_ciclos_detectados.csv`

- `cycle_id`: llave técnica del ciclo.
- `centro`, `caseta`, `lote`: identidad operativa.
- `fecha_inicio_ciclo`: inicio detectado.
- `aves_iniciales`: entrada neta.
- `orden_operativa`: conector operativo.
- `fecha_fin_ciclo`: cierre o corte.
- `estado_ciclo`: estado del ciclo.
- `motivo_fin_ciclo`: evidencia de cierre.

### `06_linea_diaria_ciclos.csv`

Contiene una fila por día y ciclo con edad, aves, mortalidad, consumo, producción, fase, estándar, brechas, ICA y contexto SAP.

### `07_resumen_semanal_ciclos.csv`

Agregación semanal de consumo, producción, ICA y brechas.

### `08_stock_alimento_diario_por_material.csv`

Stock diario por material/fase con entradas, consumo, ajustes y conciliación.

### `09_stock_alimento_diario_global.csv`

Stock global diario, entradas, consumo total, movimientos netos y diferencia de conciliación.

### `10_features_y_scores_diarios.csv`

Dataset principal para anomalías. Incluye features, flags de reglas, `score_reglas`, `score_ml`, `score_anomalia`, `severidad`, `es_anomalia` y `motivo_anomalia`.

### `11_anomalias_consumo.csv`

Subconjunto de filas con `es_anomalia = True`, ordenado por score.

## Características para anomalías

Variables principales calculadas:

- `consumo_g_ave_dia_real`;
- `produccion_g_ave_dia_real`;
- `mortalidad_por_1000`;
- `consumo_rolling_median_28`;
- `consumo_robust_z_28`;
- `cambio_consumo_pct_dia`;
- `consumo_promedio_7d`;
- `consumo_std_7d`;
- `ratio_consumo_vs_estandar`;
- `ratio_produccion_vs_estandar`;
- `consumo_cero_con_aves`;
- `consumo_negativo`;
- `consumo_sin_orden`;
- `orden_fuera_maestro`;
- `fase_multiple_dia`.

## Resultados del modelo

- `score_ml`: score normalizado del baseline no supervisado.
- `flag_ml`: indicador del modelo.
- `score_reglas`: score por reglas explicables.
- `score_anomalia`: combinación ponderada.
- `severidad`: baja, media, alta o crítica.
- `motivo_anomalia`: explicación textual combinada.

## Campos utilizados por dashboard

El payload usa datos diarios, semanales, stock, ciclos, scores y movimientos SAP preparados por `dashboard_payload.py`. No se debe publicar un payload real.
