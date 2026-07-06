from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .alerts import aplicar_consenso_capas, procesar_alertas
from .anomaly_rules import apply_rule_anomalies
from .classify import classify_movements
from .config import ProjectConfig, load_config
from .coverage import build_coverage, eventos_cobertura
from .cycles import associate_orders_and_end_dates, detect_cycles
from .daily import build_daily_cycles
from .dashboard import build_dashboard
from .db import Warehouse
from .eda import generate_eda_figures, write_eda_report
from .exports import exportar_salidas
from .features import build_anomaly_features
from .io import load_kardex, load_organization, load_standard
from .logging_utils import configure_logging
from .models import apply_isolation_forest, combine_scores, train_shadow_models_by_age
from .quality import build_labeling_template, build_quality_outputs
from .normalize import normalize_kardex, normalize_organization
from .standards import prepare_standard
from .stock import build_feed_stock
from .utils import save_csv


def _save(df: pd.DataFrame, directory: Path, name: str) -> Path:
    return save_csv(df, directory / name)


def run_pipeline(config_path: str | Path, model_mode: str | None = None) -> dict[str, Path]:
    config: ProjectConfig = load_config(config_path)
    logger = configure_logging(config.resolve("logs_dir"))
    outputs: dict[str, Path] = {}

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    db = Warehouse(config.root / config.ingestion.get("db_path", "data/warehouse.db"))
    db.iniciar_ejecucion(run_id, str(Path(config_path).resolve()), "fase1+alertas")

    logger.info("1/11 Cargando fuentes")
    kardex_raw, kardex_source = load_kardex(config)
    standard_raw = load_standard(config)
    organization_raw, materials_raw = load_organization(config)

    logger.info("2/11 Normalizando MB51, organización y política")
    kardex = normalize_kardex(kardex_raw, config)
    organization, materials = normalize_organization(organization_raw, materials_raw)
    standard = prepare_standard(standard_raw)

    logger.info("3/11 Clasificando movimientos SAP")
    kardex = classify_movements(kardex, config)

    interim = config.resolve("interim_dir")
    processed = config.resolve("processed_dir")
    outputs["kardex_normalizado"] = _save(kardex, interim, "01_kardex_normalizado_clasificado.csv")
    outputs["organizacion"] = _save(organization, interim, "02_organizacion_normalizada.csv")
    outputs["materiales"] = _save(materials, interim, "03_materiales_normalizados.csv")
    outputs["politica"] = _save(standard, processed, "04_politica_preparada.csv")

    logger.info("4/11 Generando controles de calidad y catálogo SAP")
    outputs.update(build_quality_outputs(kardex, organization, standard, config))

    logger.info("5/11 Detectando ciclos biológicos")
    cycles = detect_cycles(kardex, config)
    cycles = associate_orders_and_end_dates(cycles, kardex, organization, config)
    outputs["ciclos"] = _save(cycles, processed, "05_ciclos_detectados.csv")

    logger.info("6/11 Construyendo línea diaria y semanal por ciclo")
    daily, weekly = build_daily_cycles(cycles, kardex, standard, config)
    outputs["linea_diaria"] = _save(daily, processed, "06_linea_diaria_ciclos.csv")
    outputs["resumen_semanal"] = _save(weekly, processed, "07_resumen_semanal_ciclos.csv")

    logger.info("7/11 Reconstruyendo stock global de alimento")
    stock_material, stock_global = build_feed_stock(kardex, config)
    outputs["stock_material"] = _save(stock_material, processed, "08_stock_alimento_diario_por_material.csv")
    outputs["stock_global"] = _save(stock_global, processed, "09_stock_alimento_diario_global.csv")

    logger.info("8/11 Construyendo features y reglas de anomalía")
    features = build_anomaly_features(daily, stock_global, cycles, config)
    scored = apply_rule_anomalies(features, config)

    logger.info("9/11 Aplicando baseline no supervisado")
    scored, model_path = apply_isolation_forest(scored, config, mode=model_mode)
    scored = train_shadow_models_by_age(scored, config)
    scored = combine_scores(scored, config)
    scored = aplicar_consenso_capas(scored, config)
    outputs["features"] = _save(scored, processed, "10_features_y_scores_diarios.csv")
    anomalies = scored.loc[scored["es_anomalia"]].sort_values("score_anomalia", ascending=False)
    outputs["anomalias"] = _save(anomalies, processed, "11_anomalias_consumo.csv")
    outputs["plantilla_validacion"] = build_labeling_template(anomalies, config)
    if model_path is not None:
        outputs["modelo"] = model_path

    logger.info("9b/11 Cobertura de alimento, consenso y alertas")
    try:
        cobertura = build_coverage(stock_material, stock_global, daily, config)
        outputs["cobertura"] = _save(cobertura, processed, "12_cobertura_alimento_diaria.csv")
        eventos = eventos_cobertura(cobertura, config)
        alertas = procesar_alertas(scored, weekly, eventos, config, db, run_id)
        outputs["alertas_consolidadas"] = _save(
            alertas, processed, "13_alertas_consolidadas.csv"
        )
    except Exception:
        db.cerrar_ejecucion(run_id, "ERROR", "Fallo en cobertura/alertas")
        logger.exception("Error construyendo cobertura y alertas")
        raise

    logger.info("10/11 Generando EDA, reporte y dashboard")
    if config.outputs.get("generate_figures", True):
        generate_eda_figures(daily, weekly, stock_global, scored, config)
    outputs["reporte_eda"] = write_eda_report(kardex, cycles, daily, weekly, scored, config)
    if config.outputs.get("build_dashboard", True):
        outputs["dashboard"] = build_dashboard(
        daily=daily,
        weekly=weekly,
        stock_global=stock_global,
        scored=scored,
        cycles=cycles,
        kardex=kardex,
        config=config,
    )
    logger.info("11/11 Guardando manifiesto reproducible")
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
        "config": str(Path(config_path).resolve()),
        "kardex_source": kardex_source,
        "rows": {
            "kardex": len(kardex),
            "cycles": len(cycles),
            "daily": len(daily),
            "weekly": len(weekly),
            "anomalies": len(anomalies),
            "alertas": len(alertas),
        },
        "outputs": {key: str(value) for key, value in outputs.items()},
        "model": {
            "mode": str(model_mode or config.raw.get("model_lifecycle", {}).get("mode", "train")),
            "status": str(scored.get("modelo_estado", pd.Series([""])).iloc[0]),
            "version": str(scored.get("modelo_version", pd.Series([""])).iloc[0]),
            "artifact": str(model_path) if model_path is not None else "",
        },
    }
    manifest_path = config.root / "reports" / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    outputs["manifest"] = manifest_path

    logger.info("11b/11 Exportando salidas de operación (outputs/)")
    rutas_export = exportar_salidas(config, db, run_id, alertas, cobertura, weekly, manifest)
    outputs["outputs_latest"] = rutas_export["execution_manifest"]
    db.cerrar_ejecucion(run_id, "OK", f"{len(alertas)} alertas")
    logger.info("Pipeline completado")
    return outputs
