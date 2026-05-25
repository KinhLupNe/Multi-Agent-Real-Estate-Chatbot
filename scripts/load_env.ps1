<#
.SYNOPSIS
  Load environment variables from a .env file into current PowerShell session.

.USAGE
  . .\scripts\load_env.ps1 .env.local
  # Note the leading dot+space (dot-source) so vars stay in session.
#>
param(
    [Parameter(Mandatory=$true)][string]$EnvFile
)

if (-not (Test-Path $EnvFile)) {
    throw "File $EnvFile not found."
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { return }
    if ($line -match '^([^=]+)=(.*)$') {
        $name = $Matches[1].Trim()
        $value = $Matches[2].Trim()
        if ($value -match '^"(.*)"$' -or $value -match "^'(.*)'$") { $value = $Matches[1] }
        Set-Item "env:$name" $value
        Write-Host "  $name = $value"
    }
}
Write-Host "Loaded env from $EnvFile" -ForegroundColor Green
