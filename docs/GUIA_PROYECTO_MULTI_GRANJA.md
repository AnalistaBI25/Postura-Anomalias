# Guía del proyecto y operación multi-granja

## Explicación simple

El proyecto transforma datos operativos de una granja en ciclos productivos,
consumo, producción, inventario, anomalías, alertas y un dashboard.

Desde la Fase 1 de conversión multi-granja existe un solo motor de cálculo, pero
cada granja tiene su propio espacio de trabajo:

```text
código compartido + configuración + farm_id
  = datos y resultados aislados en farms/<farm_id>/
```

En términos sencillos: el motor es común, pero cada granja tiene un cajón
separado. La caché, base de datos, modelos, reportes, resultados y logs de dos
granjas no se deben mezclar.

## Qué se consiguió en esta fase

- `project.farm_id` es obligatorio.
- Todas las rutas operativas se resuelven dentro de `farms/<farm_id>/`.
- La base SQLite, los modelos, los datos y los resultados quedan separados.
- Los scripts aceptan un archivo de configuración mediante `--config`.
- Chencopo quedó migrado a `farms/chencopo_2/`.
- Las carpetas antiguas se movieron a
  `legacy/chencopo_pre_multigranja/`; no se borraron.
- No se modificaron cálculos, reglas de negocio, umbrales ni algoritmos.

## Qué significa y qué no significa “genérico”

El proyecto ya es genérico en la separación técnica por granja: cambiar
`farm_id` cambia todo el espacio de datos y resultados sin cambiar el código.

Todavía no significa que cualquier archivo de cualquier granja pueda entrar sin
preparación. Para agregar otra granja se necesita:

- una configuración propia;
- archivos con el contrato de columnas esperado;
- materiales, almacenes, casetas, fechas y centro correctamente configurados;
- un modelo aprobado propio o una decisión explícita de entrenamiento.

Esta fase no incluye extracción automática de SAP, selector dinámico de granja
en el dashboard, branding por granja ni nuevas reglas de anomalías.

## Estructura

```text
proyecto_bi_anomalias_chencopo/
├── .github/                     automatización de GitHub
├── .streamlit/                  configuración de la aplicación
├── .venv/                       entorno Python local, no versionado
├── .vscode/                     configuración local del editor
├── agents/                      revisores automáticos del proyecto
├── config/
│   ├── project.yml
│   └── project.example.yml
├── docs/                        documentación
├── legacy/                      respaldos y componentes históricos
├── notebooks/                   análisis reproducibles
├── src/granjas_anomalias/       código compartido
├── scripts/                     ejecución y validación
├── tests/                       pruebas automáticas
├── streamlit_components/        frontend del dashboard
├── .gitignore                   exclusiones de Git
├── CHANGELOG.md                 historial de cambios
├── README.md                    entrada documental
├── requirements.txt             dependencias de despliegue
├── streamlit_app.py             entrada de Streamlit
├── pyproject.toml               paquete y dependencias
└── farms/                       único runtime operativo
    └── chencopo_2/
        ├── data/
        │   ├── raw/cargas/
        │   ├── incoming/
        │   ├── rejected/
        │   ├── cache/
        │   ├── interim/
        │   ├── processed/
        │   └── warehouse.db
        ├── models/
        ├── reports/
        │   ├── dashboard.html
        │   ├── run_manifest.json
        │   ├── figures/
        │   ├── tables/
        │   └── agentes/
        ├── outputs/
        │   ├── latest/
        │   ├── dashboard/
        │   └── history/
        └── logs/
            └── pipeline.log
```

## Configuración de `farm_id`

La configuración activa de Chencopo contiene:

```yaml
project:
  farm_id: chencopo_2
  center_id: "1217"
  farm_name: "CHENCOPO 2"
```

Reglas de `farm_id`:

- debe ser único para cada granja;
- usa minúsculas, números, guion o guion bajo;
- no admite espacios, diagonales, rutas absolutas ni `..`;
- admite como máximo 64 caracteres;
- no debe cambiarse después de comenzar a operar una granja, porque identifica
  su carpeta histórica.

Ejemplos válidos: `chencopo_2`, `granja-norte`, `centro_1217`.

## Cómo ejecutar Chencopo

Desde la raíz del proyecto:

```powershell
uv run python -m granjas_anomalias.cli run --config config/project.yml
```

El modo actual es `model_lifecycle.mode: score_existing`. La corrida usa el
modelo aprobado de Chencopo y no lo reentrena en silencio.

El dashboard queda en:

```text
farms/chencopo_2/reports/dashboard.html
```

Para abrirlo en Windows:

```powershell
Start-Process .\farms\chencopo_2\reports\dashboard.html
```

## Carga incremental

Validar un MB51 sin cargarlo:

```powershell
uv run python scripts/validate_input.py --input "archivo.xlsx" --config config/project.yml
```

Cargar un MB51 y recalcular:

```powershell
uv run python scripts/run_incremental.py --input "archivo.xlsx" --config config/project.yml
```

Los archivos aceptados, rechazados, la caché y la base resultante permanecen
dentro de `farms/chencopo_2/data/`.

## Validaciones

```powershell
uv run pytest -q
uv run python scripts/validar_dashboard_payload.py --config config/project.yml
uv run python scripts/validar_dashboard_html.py --config config/project.yml
uv run python scripts/check_reference_results.py --config config/project.yml
```

La validación de la migración de Chencopo confirmó:

- 42,900 movimientos;
- 6 ciclos;
- 1,965 filas diarias;
- 285 filas semanales;
- 115 anomalías;
- 10 alertas;
- CSV 01 a 09 y 12 idénticos al legado;
- las 159 columnas anteriores de scoring iguales valor por valor;
- mismo archivo de modelo por SHA-256;
- payload, conciliaciones, HTML y referencias en estado correcto.

La estructura puede comprobarse en cualquier momento con:

```powershell
.\.venv\Scripts\python.exe scripts/validar_estructura_proyecto.py --config config/project.yml
```

Los archivos de scoring actuales añaden tres campos de trazabilidad ya
producidos por el ciclo de vida del modelo: `modelo_estado`,
`modelo_version` y `modelo_motivo`. No cambian el score ni la clasificación.

En una nueva corrida, una alerta existente puede pasar de `nueva` a
`persistente`; eso es historial operativo normal, no un cambio en su regla de
negocio.

## Cómo preparar otra granja

1. Copiar `config/project.example.yml` como, por ejemplo,
   `config/project_granja_norte.yml`.
2. Asignar un `project.farm_id` único.
3. Configurar centro, nombre, zona horaria, casetas, materiales, almacenes,
   fechas y fuentes.
4. Colocar las fuentes bajo `farms/<farm_id>/data/raw/` o ajustar sus rutas
   relativas en el YAML.
5. Colocar el modelo y su metadata aprobados en
   `farms/<farm_id>/models/`. Nunca copiar automáticamente el modelo de otra
   granja sin validación.
6. Ejecutar el pipeline con `--config config/project_granja_norte.yml`.
7. Ejecutar las pruebas y los tres validadores.
8. Confirmar que ningún archivo nuevo apareció dentro de la carpeta de otra
   granja.

Ejemplo:

```powershell
uv run python -m granjas_anomalias.cli run --config config/project_granja_norte.yml
```

## Entrenamiento controlado

El entrenamiento es explícito:

```powershell
uv run python scripts/train_model.py --config config/project_granja_norte.yml
```

No debe ejecutarse para una granja nueva hasta contar con datos suficientes y
autorización para crear o reemplazar su modelo.

## Respaldo anterior a la migración

Las antiguas carpetas `data/`, `models/`, `reports/`, `outputs/` y `logs/` se
conservan en `legacy/chencopo_pre_multigranja/`. El código nuevo no las usa como
destino operativo. No deben borrarse hasta una autorización separada.

## Alcance pendiente

- extracción automática desde SAP;
- selección dinámica de granja en Streamlit o dashboard;
- branding por granja;
- reglas o umbrales nuevos;
- gobierno central de configuraciones y modelos;
- promoción automática de modelos.

La siguiente evolución puede trabajar esos temas, pero no forma parte de esta
Fase 1.
