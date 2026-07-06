# Operaciones CRUD

Inventario de entidades con operaciones de creación/lectura/actualización y su
política. Los datos crudos SAP son **inmutables**: ninguna operación CRUD toca
el kardex original (copias en `data/raw/` y `data/raw/cargas/`).

| Entidad | Almacén | Create | Read | Update | Delete | Identificador |
|---|---|---|---|---|---|---|
| Cargas de archivos | SQLite `cargas` | ingesta (UI/CLI) | UI/CSV | estado por pipeline | ❌ (histórico permanente) | `id` (timestamp+uuid) |
| Movimientos | SQLite `movimientos` | ingesta idempotente | pipeline | ❌ | ❌ | `llave_negocio` (hash de negocio + ocurrencia) |
| Ejecuciones | SQLite `ejecuciones` | pipeline | UI | cierre (resultado) | ❌ | `run_id` |
| Alertas | SQLite `alertas` | pipeline | UI/CSV | estado de ciclo de vida por corrida | ❌ | `alerta_id`+`run_id` |
| Revisiones de alertas | SQLite `alertas_revision` | UI (shell) | UI | reemplaza estado vigente | lógico (nuevo estado, nunca borra) | `clave_seguimiento` |
| Auditoría de revisiones | SQLite `revision_eventos` | automática en cada cambio | UI/CSV | ❌ | ❌ | autoincremental |
| Configuración | `config/project.yml` | manual | pipeline | manual + git | git | ruta |
| Umbrales | `config/project.yml` (`coverage`, `anomaly_detection`) | manual | pipeline | manual + git | git | clave YAML |

## Validaciones y auditoría

- **Create (cargas)**: extensión, tamaño (≤ `max_file_mb`), hoja, columnas
  mínimas MB51, fechas, granularidad, duplicado por hash, traslape por rango.
  Rechazos van a `data/rejected/` con motivo persistido.
- **Update (revisiones)**: estados válidos `CONFIRMADA | FALSO_POSITIVO |
  PROBLEMA_DE_DATOS | DESCARTADA`; usuario y comentario obligatorios en el
  evento; cada cambio queda en `revision_eventos` con valor anterior, valor
  nuevo, usuario y timestamp (responde quién/qué/cuándo/antes/después).
- **Delete**: solo lógico. No existe borrado físico desde la UI por diseño.
- **Concurrencia**: SQLite serializa escrituras; la app procesa un evento de
  componente a la vez (`eventId` deduplicado en `st.session_state`).

## Brechas conocidas

- **Identidad**: el campo usuario de la revisión es texto libre (sin
  autenticación); la auditoría registra lo declarado. Ligar a identidad real
  antes de producción (ver `docs/seguridad.md`).
- **Permisos**: no hay control de roles; toda persona con acceso a la app
  puede cargar y revisar. Decisión de negocio pendiente.
