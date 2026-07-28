$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$Config = if ($args.Count -gt 0) { $args[0] } else { "config/project.yml" }

if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m granjas_anomalias.cli run --config $Config

Write-Host "Pipeline finalizado. La salida anterior muestra el dashboard de la granja." -ForegroundColor Green
