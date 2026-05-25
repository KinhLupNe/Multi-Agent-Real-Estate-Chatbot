<#
.SYNOPSIS
  Dump 4 BDS indices from AWS Elasticsearch (via kubectl port-forward + SSH tunnel)
  into NDJSON files locally.

.PREREQUISITE
  1. SSH tunnel + kubectl port-forward active (Windows localhost:9200 -> EC2 -> ES)
  2. Node.js + elasticdump (npm install -g elasticdump)

.USAGE
  $env:ES_PASS = "z47O5lJxA1M30lB35tV8Xa4y"
  .\scripts\dump_es.ps1
#>

param(
    [string]$EsHost = "127.0.0.1",
    [int]   $EsPort = 9200,
    [string]$EsUser = "elastic",
    [string]$EsPass = $env:ES_PASS,
    [string]$OutDir = "es_dump",
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

if (-not $EsPass) {
    throw "ES_PASS not set. Run:  `$env:ES_PASS = 'z47O5lJxA1M30lB35tV8Xa4y'  before calling."
}

if (-not (Get-Command elasticdump -ErrorAction SilentlyContinue)) {
    throw "elasticdump not installed. Run:  npm install -g elasticdump"
}

$ES = "http://${EsUser}:${EsPass}@${EsHost}:${EsPort}"
New-Item -ItemType Directory -Force $OutDir | Out-Null

Write-Host "Target ES: http://${EsHost}:${EsPort}"
Write-Host "Output dir: $OutDir"
Write-Host "Indices  : $($Indices -join ', ')"
Write-Host ""

foreach ($idx in $Indices) {
    Write-Host "==> Dumping [$idx]" -ForegroundColor Cyan
    # Remove stale files first - elasticdump refuses to overwrite by default
    Remove-Item -ErrorAction SilentlyContinue `
        "$OutDir/${idx}_settings.json", `
        "$OutDir/${idx}_mapping.json", `
        "$OutDir/${idx}_data.json"

    elasticdump --input="$ES/$idx" --output="$OutDir/${idx}_settings.json" --type=settings
    if ($LASTEXITCODE -ne 0) { throw "Failed dumping settings for $idx" }
    elasticdump --input="$ES/$idx" --output="$OutDir/${idx}_mapping.json"  --type=mapping
    if ($LASTEXITCODE -ne 0) { throw "Failed dumping mapping for $idx" }
    elasticdump --input="$ES/$idx" --output="$OutDir/${idx}_data.json"     --type=data --limit=$Limit
    if ($LASTEXITCODE -ne 0) { throw "Failed dumping data for $idx" }
    Write-Host "    Done." -ForegroundColor Green
}

Write-Host ""
Write-Host "All indices dumped into $OutDir/" -ForegroundColor Green
Get-ChildItem $OutDir | Measure-Object Length -Sum | Select-Object @{n='TotalMB';e={[math]::Round($_.Sum / 1MB, 2)}}
