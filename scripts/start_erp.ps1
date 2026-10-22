$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$env:ERP_API_KEY = "qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f"
$env:ERP_BASE_URL = "http://127.0.0.1:8081"
$py = Join-Path $root "finprobe_env\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py mock-erp/server.py