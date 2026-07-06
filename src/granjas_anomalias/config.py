from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    raw: dict[str, Any]

    @property
    def project(self) -> dict[str, Any]:
        return self.raw["project"]

    @property
    def paths(self) -> dict[str, Any]:
        return self.raw["paths"]

    @property
    def sap(self) -> dict[str, Any]:
        return self.raw["sap"]

    @property
    def stock(self) -> dict[str, Any]:
        return self.raw["stock"]

    @property
    def anomaly(self) -> dict[str, Any]:
        return self.raw["anomaly_detection"]

    @property
    def outputs(self) -> dict[str, Any]:
        return self.raw["outputs"]

    @property
    def ingestion(self) -> dict[str, Any]:
        """Parámetros de ingesta incremental; vacío si el YAML aún no los define."""
        return self.raw.get("ingestion", {}) or {}

    @property
    def coverage(self) -> dict[str, Any]:
        """Umbrales de cobertura de alimento; vacío si el YAML aún no los define."""
        return self.raw.get("coverage", {}) or {}

    def resolve(self, path_key: str) -> Path:
        return (self.root / self.paths[path_key]).resolve()

    def ensure_directories(self) -> None:
        for key in [
            "interim_dir",
            "processed_dir",
            "figures_dir",
            "tables_dir",
            "models_dir",
            "logs_dir",
        ]:
            self.resolve(key).mkdir(parents=True, exist_ok=True)


def _strip_comment(line: str) -> str:
    in_quote: str | None = None
    for index, char in enumerate(line):
        if char in {'"', "'"}:
            if in_quote == char:
                in_quote = None
            elif in_quote is None:
                in_quote = char
        elif char == "#" and in_quote is None:
            return line[:index].rstrip()
    return line.rstrip()


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    if value in {"null", "None", "~"}:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        line = _strip_comment(raw_line)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            raise ValueError(f"Linea YAML no soportada: {raw_line}")

        key, value = stripped.split(":", 1)
        key = _parse_scalar(key)
        if not isinstance(key, str):
            key = str(key)

        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        value = value.strip()
        if value:
            parent[key] = _parse_scalar(value)
        else:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))

    return root


def _load_yaml_text(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return _parse_simple_yaml(text)
    raw = yaml.safe_load(text)
    return raw or {}


def load_config(config_path: str | Path) -> ProjectConfig:
    config_path = Path(config_path).resolve()
    raw = _load_yaml_text(config_path.read_text(encoding="utf-8"))

    root = config_path.parent.parent
    config = ProjectConfig(root=root, raw=raw)
    config.ensure_directories()
    return config
