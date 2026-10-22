Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) 'src\frontend')
if (-not (Test-Path 'node_modules')) { npm install }
npm run dev