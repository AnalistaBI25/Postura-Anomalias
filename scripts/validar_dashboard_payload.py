from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


# Permite ejecutar este script sin instalar el proyecto.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from granjas_anomalias.config import load_config
from granjas_anomalias.dashboard_payload import (
    build_dashboard_payload,
    validate_dashboard_payload,
)


def load_csv(path: Path) -> pd.DataFrame:
    """Carga un CSV y muestra información básica."""

    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo requerido:\n{path}"
        )

    frame = pd.read_csv(
        path,
        low_memory=False,
    )

    print(
        f"[CARGADO] {path.name}: "
        f"{len(frame):,} filas, "
        f"{len(frame.columns):,} columnas"
    )

    return frame


def main() -> None:
    print("=" * 70)
    print("VALIDACIÓN DEL PAYLOAD DEL DASHBOARD")
    print("=" * 70)

    config_path = (
        ROOT
        / "config"
        / "project.yml"
    )

    if not config_path.exists():
        raise FileNotFoundError(
            f"No se encontró la configuración:\n{config_path}"
        )

    config = load_config(
        config_path
    )

    processed_dir = config.resolve(
        "processed_dir"
    )

    interim_dir = config.resolve(
        "interim_dir"
    )

    print(
        f"\nProyecto: "
        f"{config.project.get('name', '-')}"
    )

    print(
        f"Granja: "
        f"{config.project.get('farm_name', '-')}"
    )

    print(
        f"Centro: "
        f"{config.project.get('center_id', '-')}"
    )

    print("\n1. Cargando archivos...")

    daily = load_csv(
        processed_dir
        / "06_linea_diaria_ciclos.csv"
    )

    weekly = load_csv(
        processed_dir
        / "07_resumen_semanal_ciclos.csv"
    )

    stock_global = load_csv(
        processed_dir
        / "09_stock_alimento_diario_global.csv"
    )

    scored = load_csv(
        processed_dir
        / "10_features_y_scores_diarios.csv"
    )

    cycles = load_csv(
        processed_dir
        / "05_ciclos_detectados.csv"
    )

    kardex = load_csv(
        interim_dir
        / "01_kardex_normalizado_clasificado.csv"
    )

    print("\n2. Construyendo PAYLOAD...")

    payload = build_dashboard_payload(
        daily=daily,
        weekly=weekly,
        stock_global=stock_global,
        scored=scored,
        cycles=cycles,
        kardex=kardex,
        config=config,
    )

    print("[OK] PAYLOAD construido")

    print("\n3. Validando estructura y conciliaciones...")

    validate_dashboard_payload(
        payload
    )

    print("[OK] Estructura válida")
    print("[OK] Consumo diario conciliado")
    print("[OK] Consumo por caseta conciliado")
    print("[OK] Consumo por fase conciliado")

    print("\n4. Validando compatibilidad JSON...")

    json_content = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
    )

    print(
        "[OK] JSON válido, sin NaN ni Infinity"
    )

    period_ids = payload[
        "period_ids"
    ]

    periods = payload[
        "periods"
    ]

    shared_store = payload[
        "shared_store"
    ]

    shared_weeks = shared_store[
        "weekly"
    ]

    first_period_id = period_ids[0]

    first_period = periods[
        first_period_id
    ]

    daily_consumption = sum(
        sum(
            float(
                row.get(
                    "consumo_real",
                    0.0,
                )
                or 0.0
            )
            for row in periods[
                period_id
            ]["daily"]
        )
        for period_id in period_ids
    )

    shared_consumption = sum(
        sum(
            float(value or 0.0)
            for value in week[
                "consumo_por_caseta"
            ].values()
        )
        for week in shared_weeks
    )

    phase_consumption = sum(
        sum(
            sum(
                float(value or 0.0)
                for value in phases.values()
            )
            for phases in week[
                "consumo_por_caseta_fase"
            ].values()
        )
        for week in shared_weeks
    )

    total_entries = sum(
        float(
            week.get(
                "entradas",
                0.0,
            )
            or 0.0
        )
        for week in shared_weeks
    )

    total_transfers = sum(
        float(
            week.get(
                "traspasos",
                0.0,
            )
            or 0.0
        )
        for week in shared_weeks
    )

    total_adjustments = sum(
        float(
            week.get(
                "ajustes",
                0.0,
            )
            or 0.0
        )
        for week in shared_weeks
    )

    total_logistics = sum(
        float(
            week.get(
                "logistica",
                0.0,
            )
            or 0.0
        )
        for week in shared_weeks
    )

    total_waste = sum(
        float(
            week.get(
                "mermas",
                0.0,
            )
            or 0.0
        )
        for week in shared_weeks
    )

    print("\n5. Resumen de resultados")
    print("-" * 70)

    print(
        f"Periodos productivos: "
        f"{len(period_ids):,}"
    )

    print(
        f"Semanas por ciclo: "
        f"{sum(len(period['weekly']) for period in periods.values()):,}"
    )

    print(
        f"Semanas del almacén compartido: "
        f"{len(shared_weeks):,}"
    )

    print(
        f"Casetas: "
        f"{shared_store['casetas']}"
    )

    print(
        f"Fases: "
        f"{shared_store['phases']}"
    )

    print(
        f"Modo de separación de fases: "
        f"{shared_store['phase_split_mode']}"
    )

    print(
        f"Consumo diario total: "
        f"{daily_consumption:,.2f} kg"
    )

    print(
        f"Consumo por caseta: "
        f"{shared_consumption:,.2f} kg"
    )

    print(
        f"Consumo por fase: "
        f"{phase_consumption:,.2f} kg"
    )

    print(
        f"Entradas globales: "
        f"{total_entries:,.2f} kg"
    )

    print(
        f"Traspasos netos: "
        f"{total_transfers:,.2f} kg"
    )

    print(
        f"Ajustes netos: "
        f"{total_adjustments:,.2f} kg"
    )

    print(
        f"Logística neta: "
        f"{total_logistics:,.2f} kg"
    )

    print(
        f"Mermas netas: "
        f"{total_waste:,.2f} kg"
    )

    print(
        f"Tamaño del JSON: "
        f"{len(json_content.encode('utf-8')) / 1024 / 1024:,.2f} MB"
    )

    print("\n6. Primer periodo")
    print("-" * 70)

    print(
        f"ID: {first_period_id}"
    )

    print(
        f"Metadatos: "
        f"{first_period['meta']}"
    )

    print(
        f"Registros diarios: "
        f"{len(first_period['daily']):,}"
    )

    print(
        f"Registros semanales: "
        f"{len(first_period['weekly']):,}"
    )

    print(
        f"Puntos de dispersión: "
        f"{len(first_period['scatter']):,}"
    )

    print(
        f"Regresión: "
        f"{first_period['regression_stats']}"
    )

    debug_path = (
        ROOT
        / "reports"
        / "dashboard_payload_debug.json"
    )

    debug_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    debug_path.write_text(
        json_content,
        encoding="utf-8",
    )

    print(
        f"\n[OK] JSON de revisión guardado en:\n{debug_path}"
    )

    print("\n" + "=" * 70)
    print("VALIDACIÓN COMPLETADA CORRECTAMENTE")
    print("=" * 70)


if __name__ == "__main__":
    main()