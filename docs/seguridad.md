# Seguridad

Revisión ejecutada por `agents/agent_seguridad.py` (evidencia en
`reports/agentes/<timestamp>/revisor_seguridad.json`). Estado al 2026-07-06.

## Hallazgo crítico (decisión de negocio requerida antes del PR)

**El repositorio remoto es PÚBLICO** (`github.com/AnalistaBI25/Postura-Anomalias`)
y la rama versiona archivos con datos operativos reales:

- `config/project.yml`: centro, granja, materiales, almacenes y casetas reales.
- `reports/dashboard.html`: payload embebido con consumo, ciclos, órdenes y lotes.
- `outputs/*/execution_manifest.json`: rutas absolutas locales (incluye nombre
  de usuario del equipo).

Opciones (en orden recomendado):

1. **Hacer el repositorio privado** — Streamlit Community Cloud soporta repos
   privados; es el cambio de menor fricción y no rompe el deploy.
2. Retirar los archivos del índice **y del historial** (`git filter-repo`) y
   publicar el dashboard solo con datos sintéticos/anonimizados.
3. Aceptar la exposición de forma explícita y documentada (no recomendado).

## Resto de la revisión

| Área | Estado | Detalle |
|---|---|---|
| Secretos/credenciales | ✅ | Sin patrones de credenciales en archivos versionados; no hay `.env` trackeado. |
| Path traversal en carga | ✅ | El nombre se sanea con `Path(...).name`; el archivo se escribe solo en `data/incoming/`. |
| Extensión/tamaño de carga | ✅ | Ingesta valida extensión y `max_file_mb=100`; `.streamlit/config.toml` fija `maxUploadSize=100` para rechazar antes de transferir. |
| Inyección SQL | ✅ | Todas las consultas SQLite usan parámetros (`?`); los nombres de columna provienen de código, no de entrada de usuario. |
| Datos crudos inmutables | ✅ | Copia inmutable por carga; CRUD nunca modifica el kardex. |
| Auditoría | ✅ | Revisiones con borrado lógico + bitácora de eventos (usuario, antes/después, timestamp). |
| Autenticación | ❌ | La app no tiene login: cualquiera con la URL puede cargar archivos, ejecutar el pipeline y registrar revisiones. Mitigación mínima para validación: URL no difundida; recomendado: token simple vía `st.secrets` antes de aceptar eventos. |
| Identidad en auditoría | ⚠ | Usuario de revisión es texto libre; la auditoría registra lo declarado. |
| Divulgación de errores | ⚠ | En error de carga, la app devuelve `traceback` completo al frontend (revela rutas internas). Mover a logs y mostrar mensaje genérico. |
| Deserialización | ⚠ | `joblib.load` del modelo activo: solo cargar artefactos generados por el propio proyecto (los del repo/servidor), nunca subidos por usuarios. |
| Permisos de agentes | ✅ | Fase 1 solo lectura: sin push, sin merge, sin borrado, sin acceso a secretos (ver `docs/agentes_arquitectura.md`). |

## Principio de menor privilegio

- La app Streamlit solo escribe en `data/`, `reports/`, `outputs/`, `models/`, `logs/`.
- Los agentes solo escriben sus reportes en `reports/agentes/`.
- Nada en el proyecto requiere credenciales; si se agregan (correo,
  notificaciones), usar `st.secrets`/variables de entorno, nunca el YAML.
