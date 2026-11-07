$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$statePath = Join-Path $projectRoot '.local/processes.json'
if (!(Test-Path $statePath)) { Write-Host 'No hay servicios registrados por este proyecto.'; return }
$owned = @(Get-Content -Raw $statePath | ConvertFrom-Json)
foreach ($entry in ($owned | Sort-Object id -Descending)) {
    $process = Get-Process -Id $entry.id -ErrorAction SilentlyContinue
    if (!$process) { continue }
    $expectedStart = ([datetime]$entry.startTime).ToUniversalTime()
    if ($process.Path -ne $entry.path -or [math]::Abs(($process.StartTime.ToUniversalTime() - $expectedStart).TotalSeconds) -gt 1) {
        throw "El proceso $($entry.id) no coincide con el registrado. No se detuvo."
    }
    Stop-Process -Id $entry.id
    Write-Host "Detenido: $($entry.name)"
}
# Only remove this script's process registry; preserve the database, model and logs.
Remove-Item -LiteralPath $statePath
Write-Host 'Servicios detenidos. Los datos locales se conservan.'
