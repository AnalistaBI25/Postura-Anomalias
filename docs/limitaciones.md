# Limitaciones conocidas

Registro honesto de lo que el sistema NO hace todavía y su impacto.

## Datos y alcance

1. **Una granja, un almacén de alimento**: el procesamiento productivo cubre
   el centro configurado (`config/project.yml`) con almacén único de alimento.
   Multi-granja está preparado en el registro/almacén lógico (columna centro),
   pero cada granja requiere su YAML y su corrida. Multialmacén: fuera de alcance.
2. **Fuente única MB51 en la carga web**: la UI acepta solo el crudo MB51.
   Estándar, organización y MB5B se actualizan sustituyendo los archivos
   configurados (fuera de la UI). Punto de integración listo en
   `ingestion.detectar_fuente`.
3. **Sin inventario físico ni tránsito**: no hay fuente de pedidos programados
   ni alimento en tránsito; la cobertura se estima con consumo reciente.
   Umbrales de cobertura provisionales (`PREGUNTAS_PENDIENTES.md`).
4. **Capacidad de silos desconocida**: no existe la alerta "sobre capacidad
   física" por falta del dato.
5. **9 movimientos con almacén nulo** en el kardex actual (0.02%): se
   conservan pero no afectan el stock del almacén configurado.
6. **Producción/mortalidad fuera de ciclos**: 1.46% de la producción y la
   mortalidad previa a los ciclos detectados existen en SAP pero no se asignan
   a ningún ciclo del análisis (por diseño; pendiente confirmar con negocio).

## Plataforma

7. **Persistencia efímera en Streamlit Cloud**: cargas, warehouse.db y
   dashboards regenerados no sobreviven reinicios del contenedor; solo
   persiste lo commiteado. Adecuado para validación, no para operación.
8. **Sin autenticación** en la app de validación (ver `docs/seguridad.md`).
9. **Repositorio público con datos reales**: decisión de negocio pendiente
   (hallazgo crítico de la revisión).

## Analítica

10. **Anomalías = señales, no conclusiones**: el score prioriza revisión
    experta; no hay etiquetas validadas todavía (plantilla de validación en
    `reports/tables/05_*.csv`).
11. **Modelos sombra sin promoción**: IF/LOF por edad son evidencia
    comparativa hasta que la validación experta los respalde.
12. **Estándar corporativo estático**: una política por granja; si cambia por
    lote/genética, hay que recargarla.

## Pruebas

13. Casos que requieren archivos reales de otras granjas (centros, almacenes,
    materiales y unidades nuevas) están preparados pero no ejecutados con
    datos reales; el detector de fuente los reportará como advertencia.
