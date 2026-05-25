<#
.SYNOPSIS
  Restore 4 BDS indices into local Docker Elasticsearch from dump files.

.PREREQUISITE
  1. Local ES is running:  cd local_es; docker compose up -d
  2. es_dump/ folder exists with 12 files (4 index x 3 type)
  3. Node.js + elasticdump (npm install -g elasticdump)

.USAGE
  .\scripts\restore_es.ps1
#>

param(
    [string]$EsHost = "127.0.0.1",
    [int]   $EsPort = 9200,
    [string]$EsUser = "elastic",
    [string]$EsPass = "z47O5lJxA1M30lB35tV8Xa4y",
    [string]$InDir  = "es_dump",
    [string[]]$Indices = @(
        "nhamatpho_index",
        "nharieng_index",
        "chungcu_index",
        "bietthu_index",
        "dat_index",
        "khac_index"
    ),
    [int]$Limit = 1000
)

if (-not (Test-Path $InDir)) {
    throw "Dump folder '$InDir' not found. Run dump_es.ps1 first."
}
if (-not (Get-Command elasticdump -ErrorAction SilentlyContinue)) {
    throw "elasticdump not installed. Run:  npm install -g elasticdump"
}

$ES = "http://${EsUser}:${EsPass}@${EsHost}:${EsPort}"

foreach ($idx in $Indices) {
    Write-Host "==> Restoring [$idx]" -ForegroundColor Cyan

    $settingsFile = Join-Path $InDir "${idx}_settings.json"
    $mappingFile  = Join-Path $InDir "${idx}_mapping.json"
    $dataFile     = Join-Path $InDir "${idx}_data.json"

    $missing = @($settingsFile, $mappingFile, $dataFile) | Where-Object { -not (Test-Path $_) }
    if ($missing.Count -gt 0) {
        Write-Host "    Skipped (no dump found, likely chưa crawl): $idx" -ForegroundColor Yellow
        continue
    }

    elasticdump --input="$settingsFile" --output="$ES/$idx" --type=settings
    if ($LASTEXITCODE -ne 0) { throw "Failed restoring settings for $idx" }
    elasticdump --input="$mappingFile"  --output="$ES/$idx" --type=mapping
    if ($LASTEXITCODE -ne 0) { throw "Failed restoring mapping for $idx" }
    elasticdump --input="$dataFile"     --output="$ES/$idx" --type=data --limit=$Limit
    if ($LASTEXITCODE -ne 0) { throw "Failed restoring data for $idx" }
    Write-Host "    Done." -ForegroundColor Green
}

Write-Host ""
Write-Host "All indices restored. Verify:" -ForegroundColor Green
Write-Host "  curl.exe -u ${EsUser}:${EsPass} http://${EsHost}:${EsPort}/_cat/indices?v"
