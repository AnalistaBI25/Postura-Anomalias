# Pauta de extracción de datos SAP

## 1. Kardex MB51 - fuente principal

Extraer por centro, rango de fechas completo y sin limitar prematuramente los tipos de movimiento. Para investigación de anomalías se recomienda cubrir al menos varios ciclos completos cuando el negocio disponga de histórico suficiente.

### Campos obligatorios

- Material y descripción.
- Centro y almacén.
- Lote.
- Documento material y posición.
- Fecha de contabilización y hora de entrada.
- Cantidad en unidad de entrada y unidad.
- Cantidad en unidad paralela y unidad.
- Clase y texto de movimiento.
- Clase de transacción/evento.
- Orden.
- Referencia.
- Indicador Debe/Haber.
- Centro receptor.
- Usuario y textos del documento.

### Filtros recomendados

- Centro SAP configurado para el sitio piloto.
- Periodo desde el inicio del histórico requerido hasta la fecha de corte.
- Mantener almacenes de aves, alimento, producción y tránsito.
- Mantener movimientos productivos, reversas, ajustes, traspasos, mermas, logística e inventario.
- Conservar cualquier movimiento nuevo para análisis, no eliminarlo en origen.

### Convención de nombre

Usar una convención local que no deba publicarse si contiene identificadores reales. El archivo real debe vivir en `data/raw/`.

## 2. MB5B - ancla de inventario

Extraer el saldo al cierre del día anterior al inicio operativo del periodo de alimento:

- centro SAP configurado;
- almacén de alimento configurado;
- materiales de alimento configurados;
- fecha de ancla documentada.

MB5B aporta el stock inicial; MB51 reconstruye los cambios posteriores.

## 3. Organización de granjas

Debe contener como mínimo:

- centro;
- granja;
- módulo;
- caseta o almacén de aves;
- orden vigente;
- vigencia desde/hasta, cuando esté disponible.

La orden se utiliza como conector operativo, no como llave biológica primaria.

## 4. Política productiva

Debe conservar una fila por semana de edad con:

- consumo g/ave/día;
- porcentaje de producción;
- peso promedio del huevo;
- ICA;
- mortalidad acumulada;
- viabilidad;
- peso corporal.

## 5. Extracción incremental futura

Para operación recurrente:

1. Cargar un histórico inicial completo.
2. Extraer MB51 diariamente desde la última fecha exitosa menos una ventana de seguridad.
3. Deduplicar por documento material, posición y ejercicio cuando esos campos estén disponibles.
4. Registrar fecha, usuario, filtros y hash del archivo en un control interno.
5. Ejecutar controles de volumen y movimientos desconocidos.
