$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$py = Join-Path $root "finprobe_env\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py -m uvicorn src.backend.app.main:app --host 127.0.0.1 --port 8000