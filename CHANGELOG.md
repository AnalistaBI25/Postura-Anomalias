# Changelog

## 0.2.0 - refinamiento del dashboard y documentación de usuario

Frontend del dashboard (`templates/dashboard_productivo.html`):

- Motor de reproducción unificado: un solo `setInterval`; el reproductor de
  alimento es un espejo sincronizado del cursor global (sin timer ni fecha
  propios).
- Rendimiento: las pestañas pesadas (técnica, anomalías, ciclos) se renderizan
  bajo demanda (patrón dirty-workspace), no en cada tick.
- Corrección de la escala vacía del ICA semanal (desajuste de etiquetas del eje).
- Gráficas de consumo por fase como área apilada.
- Análisis histórico reubicado por dominio: gráficas globales en "Cobertura de
  alimento" y gráficas por caseta en cada pestaña de caseta; se oculta la
  pestaña histórica separada.
- Logo PNG (`src/crio.png`) incrustado como data URI por el pipeline; encabezado
  compactado con más presencia del logo.
- Gestos de doble clic: zoom por gráfica (con borde de color, independiente) y
  declutter de descripciones en tarjetas.
- Tooltip de datos compacto en todas las gráficas.
- Corrección del error `Cannot read properties of null (reading 'closest')` al
  hacer zoom tras recrear gráficas (se resuelve la instancia actual con
  `Chart.getChart`).
- Se retiran el modo noche, el botón de imprimir y la tarjeta de Conciliación
  redundante (la conciliación permanece en Control técnico).

Documentación:

- Nuevo [Manual de usuario](docs/MANUAL_USUARIO.md) del dashboard.
- README con índice de documentación y nota sobre `--config`.

## 0.1.0 - conversión del prototipo a proyecto reproducible

- Modularización de las celdas en paquete Python.
- Configuración YAML.
- Carga de MB51, MB5B, política y organización.
- Detección y validación de ciclos productivos.
- Reconstrucción diaria por ciclo y stock global.
- Política preparada con fórmulas por aves disponibles.
- EDA, dashboard, catálogo SAP y controles de calidad.
- Reglas de anomalía e Isolation Forest baseline.
- Plantilla de validación experta para Fase 2.
- Pruebas unitarias, manifiesto, logs y CI.
- Preservación del código del prototipo.
