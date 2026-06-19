from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(
        0,
        str(SRC),
    )


from granjas_anomalias.config import load_config
from granjas_anomalias.dashboard import build_dashboard


def load_csv(path: Path) -> pd.DataFrame:
    """Carga un CSV requerido por el dashboard."""

    if not path.exists():
        raise FileNotFoundError(
            "No se encontró el archivo requerido:\n"
            f"{path}"
        )

    frame = pd.read_csv(
        path,
        low_memory=False,
    )

    print(
        f"[CARGADO] {path.name}: "
        f"{len(frame):,} filas"
    )

    return frame


def main() -> None:
    print("=" * 70)
    print("GENERACIÓN DE DASHBOARD HTML DE PRUEBA")
    print("=" * 70)

    config_path = (
        ROOT
        / "config"
        / "project.yml"
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

    print("\n1. Cargando datos procesados...")

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

    output_path = (
        ROOT
        / "reports"
        / "dashboard_prueba.html"
    )

    print("\n2. Construyendo dashboard...")

    generated_path = build_dashboard(
        daily=daily,
        weekly=weekly,
        stock_global=stock_global,
        scored=scored,
        cycles=cycles,
        kardex=kardex,
        config=config,
        output_path=output_path,
    )

    print(
        f"[OK] Dashboard generado:\n"
        f"{generated_path}"
    )

    print("\n3. Validando el archivo HTML...")

    html_content = generated_path.read_text(
        encoding="utf-8"
    )

    if "__PAYLOAD_JSON__" in html_content:
        raise ValueError(
            "El marcador __PAYLOAD_JSON__ "
            "continúa dentro del HTML."
        )

    if "const PAYLOAD = {" not in html_content:
        raise ValueError(
            "No se encontró el PAYLOAD "
            "insertado en JavaScript."
        )

    if "<html" not in html_content.lower():
        raise ValueError(
            "El archivo generado no contiene "
            "una etiqueta HTML."
        )

    if "</html>" not in html_content.lower():
        raise ValueError(
            "El archivo generado no contiene "
            "el cierre HTML."
        )

    file_size_mb = (
        generated_path.stat().st_size
        / 1024
        / 1024
    )

    if file_size_mb < 0.10:
        raise ValueError(
            "El HTML generado parece demasiado pequeño. "
            f"Tamaño: {file_size_mb:.2f} MB."
        )

    print("[OK] Marcador reemplazado")
    print("[OK] PAYLOAD insertado")
    print("[OK] Documento HTML completo")

    print(
        f"[OK] Tamaño del archivo: "
        f"{file_size_mb:.2f} MB"
    )

    print("\n" + "=" * 70)
    print("DASHBOARD DE PRUEBA GENERADO CORRECTAMENTE")
    print("=" * 70)

    print(
        "\nÁbrelo con este comando:\n"
        "Start-Process "
        r".\reports\dashboard_prueba.html"
    )


if __name__ == "__main__":
    main()