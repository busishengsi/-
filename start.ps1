$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".venv\Scripts\python.exe" manage.py check
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& ".venv\Scripts\python.exe" manage.py serve --port 5003
