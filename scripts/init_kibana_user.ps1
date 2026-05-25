<#
.SYNOPSIS
  Bootstrap the kibana_system password in local Elasticsearch.

.DESCRIPTION
  Kibana 8.x refuses to use the 'elastic' superuser. It requires the built-in
  'kibana_system' user, which has no password by default. This script sets
  that password via the ES Security API. Idempotent: safe to run multiple times.

.PREREQUISITE
  Local ES is up and healthy:  cd local_es; docker compose up -d elasticsearch

.USAGE
  .\scripts\init_kibana_user.ps1
#>

param(
    [string]$EsHost = "127.0.0.1",
    [int]   $EsPort = 9200,
    [string]$EsPass = "z47O5lJxA1M30lB35tV8Xa4y",
    [string]$KibanaSystemPass = "kibana_local_pass_2026"
)

$base = "http://${EsHost}:${EsPort}"
$pair = "elastic:${EsPass}"
$bytes = [System.Text.Encoding]::ASCII.GetBytes($pair)
$auth = [System.Convert]::ToBase64String($bytes)
$headers = @{ Authorization = "Basic $auth"; "Content-Type" = "application/json" }

# 1. Wait until ES is reachable
Write-Host "Checking ES at $base ..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "$base/_cluster/health" -Headers $headers -Method Get -TimeoutSec 5
        if ($health.status -in @("yellow","green")) {
            Write-Host "  ES status: $($health.status)" -ForegroundColor Green
            $ready = $true
            break
        }
    } catch {
        Write-Host "  ES not ready yet (attempt $($i+1)/30) ..."
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) {
    throw "ES is not reachable at $base after 60s. Run: cd local_es; docker compose up -d elasticsearch"
}

# 2. Set kibana_system password
Write-Host "Setting password for kibana_system ..."
$body = @{ password = $KibanaSystemPass } | ConvertTo-Json
try {
    Invoke-RestMethod -Uri "$base/_security/user/kibana_system/_password" `
                      -Method Post -Headers $headers -Body $body | Out-Null
    Write-Host "kibana_system password set successfully." -ForegroundColor Green
} catch {
    throw "Failed to set kibana_system password: $($_.Exception.Message)"
}

# 3. Verify kibana_system can authenticate
Write-Host "Verifying kibana_system credential ..."
$kibanaPair = "kibana_system:${KibanaSystemPass}"
$kibanaAuth = [System.Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($kibanaPair))
try {
    Invoke-RestMethod -Uri "$base/_security/_authenticate" `
                      -Headers @{ Authorization = "Basic $kibanaAuth" } -Method Get | Out-Null
    Write-Host "kibana_system can authenticate. OK to start Kibana." -ForegroundColor Green
} catch {
    throw "kibana_system authentication failed: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Next step: restart Kibana to pick up the new password:" -ForegroundColor Cyan
Write-Host "  docker compose -f local_es\docker-compose.yml restart kibana"
