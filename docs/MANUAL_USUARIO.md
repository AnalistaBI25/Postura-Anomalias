# Manual de usuario · Dashboard productivo CRÍO

Guía para **leer y operar el dashboard**
(`farms/<farm_id>/reports/dashboard.html`). No requiere
conocimientos de programación. Para regenerarlo o cargar otra granja, ver la
sección [Generar o actualizar el dashboard](#7-generar-o-actualizar-el-dashboard)
y el [Runbook operativo](runbook.md).

---

## 1. Qué es

El dashboard es un **reporte productivo diario** de la granja (por defecto
CHENCOPO 2, centro 1217). Un solo archivo HTML autocontenido —incluye los datos
y el logo embebidos— que se abre en cualquier navegador moderno, sin internet ni
servidor.

Responde, sobre todo, preguntas de **alimento**:

- ¿Cuánto alimento hay y para cuántos días alcanza?
- ¿Cuánto entró y cuánto se consumió?
- ¿Cuánto consumió cada caseta?
- ¿El stock cuadra (conciliación)?
- ¿Hay anomalías de consumo, producción o mortalidad?

El **almacén de alimento es compartido** por las tres casetas (1007, 1008, 1009).
Por eso el stock es **global**, mientras que aves, mortalidad, producción e ICA
se analizan **por caseta**.

---

## 2. Cómo abrirlo

1. Abre `farms/<farm_id>/reports/dashboard.html` con doble clic (Chrome, Edge o
   Firefox actualizados).
2. No necesita conexión a internet salvo la primera carga de las librerías de
   gráficas (Chart.js) desde su CDN; con internet la primera vez, luego funciona.
3. Si aparece una **franja roja** arriba con un mensaje de error, recarga la
   página; si persiste, avisa al equipo técnico (ver
   [Solución de problemas](#8-solución-de-problemas)).

---

## 3. Anatomía de la pantalla

### Encabezado (barra superior fija)

| Elemento | Para qué sirve |
|---|---|
| **Logo CRÍO + título** | Identidad del reporte. |
| **Granja / Centro / Estado / Escala temporal** | Filtros globales. "Estado" filtra ciclos abiertos/cerrados. "Escala temporal" cambia entre **Ciclo completo**, **Semana** y **Día específico**. |
| **Ciclo / parvada** | Selector del ciclo productivo a mostrar. |
| **◀ / ▶** | Retroceder / avanzar un día (o una semana, según la escala). |
| **Fecha seleccionada** | Calendario para saltar a una fecha. |
| **Última fecha** | Salta al último día con datos. |
| **▶ Reproducir** | Inicia la animación temporal (ver abajo). |
| **Barra deslizante (slider)** | Mueve la fecha manualmente. |

### Pestañas

- **Cobertura de alimento** — pantalla principal del almacén compartido.
- **Caseta 1007 / 1008 / 1009** — análisis individual de cada caseta.
- **Ciclos productivos** — catálogo de parvadas (abiertas y cerradas).
- **Anomalías** — eventos detectados hasta la fecha seleccionada.
- **Control técnico** — línea de tiempo SAP, validador y conciliación de stock.

> El análisis histórico **ya no es una pestaña aparte**: las gráficas del
> almacén están al final de **Cobertura de alimento** y las gráficas por caseta
> al final de cada pestaña de **Caseta**.

---

## 4. El reproductor temporal (animación)

Es el corazón del dashboard: **una sola línea de tiempo** controla todo.

- **▶ Reproducir / ⏸ Pausar:** avanza la fecha automáticamente. Al reproducir,
  verás cambiar el nivel de la tolva, los KPIs, las gráficas y las alertas.
- **Slider y botones ◀ ▶:** mueven la fecha manualmente; la reproducción se
  detiene.
- **Reproductor de alimento** (dentro de "Cobertura de alimento"): es un
  **espejo** del reproductor global. Comparte la misma fecha y el mismo botón;
  no es un segundo reloj independiente.
- **Escala temporal** (filtro del encabezado):
  - **Día específico:** los KPIs usan solo ese día.
  - **Semana:** acumula de lunes a la fecha de corte (no incluye días futuros).
  - **Ciclo completo:** acumula desde el inicio del ciclo.
- La reproducción **se detiene al final del ciclo** y **no salta** solo al
  siguiente. Cambiar de ciclo detiene la reproducción de forma segura.
- Cambiar de pestaña **no detiene** la reproducción; al abrir una pestaña se
  actualiza con la fecha actual.

---

## 5. Gestos ocultos (atajos)

El dashboard tiene dos gestos de **doble clic** (no hay botones para ellos):

| Gesto | Resultado |
|---|---|
| **Doble clic sobre una gráfica** | Activa el **zoom** de esa gráfica. Se enmarca con un **borde azul** y aparece un 🔍 junto al título. Luego usa la **rueda** del ratón para acercar y **arrastra** para desplazarte. Doble clic de nuevo para salir. El zoom es **independiente** en cada gráfica. |
| **Doble clic sobre una tarjeta** (KPI, caseta, balance) | Oculta sus **descripciones secundarias** para una vista más limpia. Doble clic de nuevo para restaurarlas. |

---

## 6. Guía por pestaña

### 6.1 Cobertura de alimento (pantalla principal)

- **KPIs del almacén:** stock al cierre, entradas del día, consumo global, días
  estimados.
- **Insignia de estado:** "Almacén conciliado" o "Diferencia por validar".
- **Tolva (silo) animada:** el nivel sube con las entradas y baja con el
  consumo. Muestra stock, % visual respecto al máximo histórico, días estimados,
  material/fase y estado (Normal / Preventivo / Bajo / Crítico). La capacidad
  física no está configurada: el nivel es **relativo al máximo observado**.
- **Flujo histórico de inventario:** stock diario con entradas y consumo global.
- **Balance de conciliación:** apertura + entradas − consumo ± otros = cierre.
- **Histórico del almacén compartido** (abajo): stock, movimientos, consumo por
  caseta y consumo por fase.

### 6.2 Casetas 1007 / 1008 / 1009

Una pestaña por caseta. Cada una muestra **solo** los datos de esa caseta:

- Identidad: orden, lote, estado.
- Ciclo de aves: inicio, fin/corte, primera producción, duración, avance.
- Tarjetas con aves, mortalidad (día y acumulada), consumo (día, acumulado,
  esperado, gramos por ave), producción (día, acumulada, cumplimiento) e ICA.
- **Análisis histórico de la caseta** (abajo): producción, consumo, ICA, aves y
  relación consumo–producción.

> El stock global **no** se duplica aquí; se consulta en "Cobertura de alimento".

### 6.3 Ciclos productivos

Catálogo de todas las parvadas: fechas, casetas, duración, aves iniciales y
estado (🔵 cerrado / 🟢 en proceso). Al hacer clic en un ciclo, el dashboard
cambia a ese ciclo y muestra su detalle con las líneas de tiempo por caseta.
Los ciclos abiertos **no inventan** fecha de cierre: muestran "En proceso".

### 6.4 Anomalías

- Resumen por caseta con score, severidad y motivo.
- Histórico de anomalías **hasta la fecha seleccionada** (no cuenta el futuro).
- El número en la pestaña ("badge") indica cuántas hay activas.

> Alcance actual: el sistema contiene **detección histórica** de anomalías. La
> **predicción a futuro aún no está implementada** (corresponde a la Fase 2).

### 6.5 Control técnico

- **Línea de tiempo y eventos SAP:** inicios/cierres, reabastos, traspasos,
  ajustes, mermas, logística y primera producción.
- **Resumen semanal ejecutivo.**
- **Validador técnico y conciliación:** día seleccionado, histórico y
  **conciliación de stock** (stock calculado vs. reconstruido, con diferencia y
  validación "Conciliado / Revisar").

---

## 7. Generar o actualizar el dashboard

El dashboard se genera con el pipeline. Con el entorno preparado
(ver [Runbook](runbook.md)):

```powershell
$env:PYTHONPATH="src"
python -m granjas_anomalias.cli run --config config/project.yml
```

Esto regenera `reports/dashboard.html` con los datos y el logo más recientes.

### Cambiar el logo

El logo se incrusta automáticamente desde `src/crio.png`. Para cambiarlo,
reemplaza ese archivo (mismo nombre) y regenera. Si tienes el logo en **vector**
(`.svg`), pídelo al equipo técnico para incrustarlo con mejor calidad.

### Cargar OTRA granja

1. Coloca los 4 archivos de entrada de esa granja en `data/raw/`: kárdex MB51,
   estándar SAP, organización y MB5B (stock inicial).
2. Copia `config/project.example.yml` a `config/<granja>.yml` y ajusta:
   `center_id`, `farm_name`, `houses`, `feed_materials`, almacenes, fechas,
   stock inicial y las rutas a los archivos.
3. Ejecuta:
   ```powershell
   $env:PYTHONPATH="src"
   python -m granjas_anomalias.cli run --config config/<granja>.yml
   ```
   > Usa el **CLI del módulo** (respeta `--config`). El script
   > `scripts/run_pipeline.py` usa siempre `config/project.yml`.

**Límite importante:** el dashboard está diseñado para **hasta 3 casetas** (tres
pestañas y tres gráficas de fase). El pipeline soporta más casetas, pero la
plantilla solo muestra bien tres.

---

## 8. Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| Franja roja "No fue posible completar el dashboard…" | Recarga la página. Si persiste, regenera el pipeline y avisa al equipo técnico. |
| Las gráficas no cargan | Necesitas internet la primera vez (Chart.js se baja del CDN). |
| El nivel de la tolva no cambia | Pulsa ▶ Reproducir o mueve el slider; revisa que la escala temporal sea la deseada. |
| Una gráfica se queda "atrapada" en zoom | Doble clic sobre ella para salir del modo zoom. |
| Veo fechas que no coinciden entre secciones | Asegúrate de que la reproducción esté en pausa y mueve a una fecha concreta; el reproductor de alimento siempre refleja la fecha global. |
| Datos desactualizados | Regenera el dashboard (sección 7). |

---

## 9. Siguientes pasos (para el usuario)

1. **Operación diaria:** abrir el dashboard, revisar "Cobertura de alimento"
   (días estimados y conciliación) y la pestaña "Anomalías".
2. **Revisión por caseta:** entrar a cada caseta para validar consumo vs.
   esperado, producción e ICA.
3. **Validación experta:** registrar en `reports/tables/05_plantilla_validacion_anomalias.csv`
   si cada anomalía priorizada es real, esperada o falsa alarma. Esa
   retroalimentación alimentará la **Fase 2** (modelado de anomalías).
4. **Automatización futura (Fase 2/3):** comparación de modelos, validación
   experta y, más adelante, scoring productivo y monitoreo. Ver
   [docs/roadmap.md](roadmap.md).

---

## 10. Notas y alcance

- El dashboard **no afirma** fraude ni error: **prioriza** eventos para revisión
  operativa, con trazabilidad.
- Las salidas con datos reales (dashboard, CSV, reportes) **no deben publicarse**
  en repositorios públicos. Ver la sección de Seguridad del
  [README](../README.md).
