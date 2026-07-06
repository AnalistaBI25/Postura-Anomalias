# Despliegue

## Modelo de despliegue actual (rama `deploy-dashboard-chencopo`)

Streamlit Community Cloud apuntando a esta rama. La app (`streamlit_app.py`)
es un host invisible: toda la UI vive en el componente
`streamlit_components/dashboard_shell/index.html` con el dashboard HTML
embebido en un iframe.

```text
Comando de inicio : streamlit run streamlit_app.py
Puerto            : 8501 (default; la nube lo gestiona)
Python            : >= 3.11 (desarrollado y probado con 3.12)
Dependencias      : requirements.txt (todas fijadas o acotadas)
Config app        : .streamlit/config.toml (maxUploadSize=100, sin telemetría)
Config negocio    : config/project.yml (debe existir en la rama desplegada)
```

## Reproducibilidad desde ambiente limpio

```powershell
git clone https://github.com/AnalistaBI25/Postura-Anomalias.git
cd Postura-Anomalias
git checkout deploy-dashboard-chencopo
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q                       # 107 pruebas
streamlit run streamlit_app.py  # abre el dashboard en modo consulta
```

Notas de reproducibilidad verificadas:

- Sin rutas absolutas en código (todo relativo a `ROOT`/`config.root`).
- `config.py` incluye parser YAML de respaldo si PyYAML faltara en el arranque.
- El dashboard commiteado (`reports/dashboard.html`) permite abrir la app sin
  ejecutar el pipeline primero (modo consulta).
- La primera carga en un ambiente limpio requiere inicializar el histórico:
  `python scripts/run_incremental.py --bootstrap` (o cargar el MB51 completo
  desde la UI).

## Ambientes

| Aspecto | Desarrollo (local) | Validación (Streamlit Cloud) | Producción (pendiente) |
|---|---|---|---|
| Datos | reales locales | los commiteados en la rama | por definir |
| Persistencia | disco local | **efímera** (se pierde al reiniciar el contenedor) | requiere volumen/servidor |
| Autenticación | no aplica | ❌ ninguna | requerida |
| Salud | logs/pipeline.log | estado visible en la app | health check + monitoreo |

**Limitación clave de la nube**: `data/warehouse.db`, cargas y dashboards
regenerados **no sobreviven reinicios** del contenedor; solo persiste lo
commiteado en la rama. Aceptable para validación visual; para operación real
se necesita servidor propio (VM + systemd/Task Scheduler) o volumen persistente.

## Rollback

- **Código**: `git revert` del commit problemático en la rama (sin force-push).
- **Dashboard**: `reports/dashboard.html` está versionado; `git checkout
  <commit> -- reports/dashboard.html` restaura una versión previa.
- **Resultados**: `outputs/history/AAAA/MM/run_<id>/` conserva manifiestos y
  CSVs por ejecución.
- **Modelo**: artefactos versionados con metadata (`models/`), modo
  `score_existing` evita reentrenamientos accidentales.

## Qué NO se agregó (y por qué)

- **Docker/CI-CD/reverse proxy**: la plataforma de validación (Streamlit
  Cloud) ya resuelve build y ejecución; agregar infraestructura ahora sería
  sobrearquitectura. Reevaluar al pasar a servidor propio.
