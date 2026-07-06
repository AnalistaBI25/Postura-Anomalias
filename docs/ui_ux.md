# Revisión UI/UX

Superficie evaluada: componente `streamlit_components/dashboard_shell/index.html`
(dock de carga + estado + revisión experta + iframe del dashboard) y el
dashboard HTML autocontenido (`reports/dashboard.html`, Chart.js).

## Evaluación

| Criterio | Estado | Evidencia |
|---|---|---|
| Navegación | ✅ | Una sola página: dock compacto arriba (desplegable) y dashboard siempre visible; dentro del dashboard, pestañas por dominio (alimento, casetas, anomalías, control técnico). |
| Flujo de carga | ✅ | Dropzone + selector de archivo, botón explícito "Analizar con Python" (previene cargas accidentales), barra de progreso y estados con título+mensaje. |
| Estados vacíos | ✅ | Sin dashboard: página "Dashboard pendiente" con instrucción; sin config: "Modo consulta" con causa. |
| Mensajes de error | ✅ | Validación devuelve errores concretos (columnas faltantes, formato no soportado, duplicado) en lenguaje operativo; reporte de errores descargable en el flujo CLI/validador. |
| Mensajes de éxito | ✅ | "Dashboard actualizado" / "Sin registros nuevos" con duración de la corrida. |
| Indicadores de carga | ✅ | Progreso en el dock durante validación/pipeline. |
| Prevención de acciones accidentales | ✅ | Un solo archivo por carga (límite configurado), confirmación explícita, revisión de alertas sin borrado físico. |
| Consistencia visual | ✅ | Paleta corporativa (azules #1A428A/#00B2E3) compartida entre shell y dashboard; tarjetas y tipografía consistentes. |
| Formato de números/fechas | ✅ | Moneda no aplica; kg y aves con separador de miles en el dashboard; fechas dd/mm/aaaa en tooltips del reproductor. |
| Tooltips y leyendas | ✅ | Tooltip compacto en todas las gráficas; leyendas por serie; gestos documentados en MANUAL_USUARIO.md (doble clic = zoom / declutter). |
| Accesibilidad | ⚠ parcial | `aria-expanded` en el dock, `role="button"` + `tabindex` en la dropzone, `escapeHtml` en todo render dinámico. Pendiente: revisión de contraste AA formal y navegación completa por teclado dentro del dashboard Chart.js. |
| Diseño responsivo | ⚠ parcial | Existe captura móvil (reports/dashboard_mobile.png) y el shell usa layout fluido; el dashboard denso favorece escritorio. Uso previsto: escritorio. |
| Volúmenes grandes | ✅ | Pestañas pesadas se renderizan bajo demanda (patrón dirty-workspace, CHANGELOG 0.2.0); payload ~2 años carga en el navegador sin peticiones de red. |
| Tiempo de respuesta al filtrar | ✅ | Filtros/reproductor operan del lado del cliente sobre el payload embebido (sin ida al servidor). |

## Recomendaciones (no aplicadas, por prioridad)

1. Autenticación/identidad visible en la barra del shell (ligada a seguridad).
2. Auditoría de contraste AA con herramienta (axe/lighthouse) sobre el HTML.
3. Mensaje de error de carga sin traceback técnico (ver `docs/seguridad.md`).

No se rediseñó nada por preferencia estética: los cambios manuales del dock
compacto y el shell HTML/JS cumplen claridad, consistencia y prevención de
errores, y se conservan tal cual.
