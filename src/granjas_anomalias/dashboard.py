from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import ProjectConfig
from .dashboard_payload import (
    build_dashboard_payload,
    validate_dashboard_payload,
)


PAYLOAD_MARKER = "__PAYLOAD_JSON__"
LOGO_MARKER = "__LOGO_DATA_URI__"
LOGO_FILENAME = "crio.png"
TEMPLATE_FILENAME = "dashboard_productivo.html"


def _logo_data_uri(template_path: Path) -> str:
    """
    Devuelve el logo CRÍO como data URI base64 para incrustarlo en el
    dashboard (documento autocontenido y portable).

    El archivo se busca en src/crio.png, relativo a la plantilla.
    Si no existe, se devuelve una cadena vacía y el HTML usa el
    respaldo textual definido en la plantilla.
    """

    logo_path = (
        template_path.parent.parent.parent / LOGO_FILENAME
    )

    if not logo_path.exists():
        return ""

    encoded = base64.b64encode(
        logo_path.read_bytes()
    ).decode("ascii")

    return f"data:image/png;base64,{encoded}"


def _default_template_path() -> Path:
    """Devuelve la ruta de la plantilla incluida en el proyecto."""

    return (
        Path(__file__).resolve().parent
        / "templates"
        / TEMPLATE_FILENAME
    )


def _read_template(
    template_path: str | Path | None = None,
) -> tuple[str, Path]:
    """
    Lee y valida la plantilla HTML.

    La plantilla debe contener exactamente una vez
    el marcador __PAYLOAD_JSON__.
    """

    if template_path is None:
        path = _default_template_path()
    else:
        path = Path(template_path).resolve()

    if not path.exists():
        raise FileNotFoundError(
            "No se encontró la plantilla del dashboard:\n"
            f"{path}"
        )

    template = path.read_text(
        encoding="utf-8"
    )

    normalized_template = template.lower()

    if (
        "<html" not in normalized_template
        or "</html>" not in normalized_template
    ):
        raise ValueError(
            "La plantilla no parece ser un documento "
            f"HTML completo:\n{path}"
        )

    marker_count = template.count(
        PAYLOAD_MARKER
    )

    if marker_count != 1:
        raise ValueError(
            "La plantilla debe contener exactamente "
            f"una vez {PAYLOAD_MARKER!r}. "
            f"Se encontraron {marker_count}."
        )

    return template, path


def _serialize_payload(
    payload: dict[str, Any],
) -> str:
    """
    Serializa el payload como JSON válido para JavaScript.

    También protege el contenido contra un cierre accidental
    de la etiqueta script.
    """

    json_text = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )

    json_text = json_text.replace(
        "</",
        "<\\/",
    )

    json_text = json_text.replace(
        "\u2028",
        "\\u2028",
    )

    json_text = json_text.replace(
        "\u2029",
        "\\u2029",
    )

    return json_text


def render_dashboard_html(
    payload: dict[str, Any],
    template_path: str | Path | None = None,
) -> str:
    """
    Inserta el payload en la plantilla y devuelve
    el documento HTML completo.
    """

    validate_dashboard_payload(
        payload
    )

    template, resolved_path = _read_template(
        template_path
    )

    payload_json = _serialize_payload(
        payload
    )

    html_content = template.replace(
        PAYLOAD_MARKER,
        payload_json,
        1,
    )

    if PAYLOAD_MARKER in html_content:
        raise RuntimeError(
            "El marcador del payload no fue "
            "reemplazado correctamente."
        )

    html_content = html_content.replace(
        LOGO_MARKER,
        _logo_data_uri(resolved_path),
    )

    return html_content


def write_dashboard_html(
    html_content: str,
    output_path: str | Path,
) -> Path:
    """
    Escribe el dashboard de forma segura.

    Primero genera un archivo temporal y después
    reemplaza el destino final.
    """

    path = Path(
        output_path
    ).resolve()

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary_path.write_text(
        html_content,
        encoding="utf-8",
    )

    temporary_path.replace(
        path
    )

    return path


def build_dashboard(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    stock_global: pd.DataFrame,
    scored: pd.DataFrame,
    cycles: pd.DataFrame,
    kardex: pd.DataFrame,
    config: ProjectConfig,
    *,
    output_path: str | Path | None = None,
    template_path: str | Path | None = None,
) -> Path:
    """
    Construye el dashboard productivo completo.

    Flujo:
    1. Construye el payload.
    2. Valida su estructura y conciliaciones.
    3. Lee la plantilla HTML.
    4. Inserta el JSON.
    5. Escribe el dashboard final.
    """

    payload = build_dashboard_payload(
        daily=daily,
        weekly=weekly,
        stock_global=stock_global,
        scored=scored,
        cycles=cycles,
        kardex=kardex,
        config=config,
    )

    html_content = render_dashboard_html(
        payload,
        template_path=template_path,
    )

    if output_path is None:
        destination = (
            config.root
            / "reports"
            / "dashboard.html"
        )
    else:
        destination = Path(
            output_path
        )

    return write_dashboard_html(
        html_content,
        destination,
    )