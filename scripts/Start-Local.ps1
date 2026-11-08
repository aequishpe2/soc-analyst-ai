param([switch]$WithAI)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimeRoot = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Force $runtimeRoot | Out-Null
$statePath = Join-Path $runtimeRoot 'processes.json'
if (Test-Path $statePath) {
    throw 'Existe un registro de servicios. Ejecuta scripts/Stop-Local.ps1 antes de iniciar otra sesión.'
}
$pythonExe = Join-Path $projectRoot 'apps/api/.venv/Scripts/python.exe'
$nodeExe = Get-ChildItem (Join-Path $projectRoot '.tools') -Filter node.exe -Recurse |
    Where-Object FullName -NotMatch 'node_modules' | Select-Object -First 1 -ExpandProperty FullName
if (!$nodeExe) { $nodeExe = (Get-Command node -ErrorAction SilentlyContinue).Source }
$ollamaExe = Join-Path $projectRoot '.tools/ollama/ollama.exe'
if (!(Test-Path $ollamaExe)) { $ollamaExe = (Get-Command ollama -ErrorAction SilentlyContinue).Source }
if (!(Test-Path $pythonExe) -or !$nodeExe) { throw 'Faltan Python (.venv) o Node. Consulta docs/LOCAL_SETUP.md.' }
if (!(Test-Path (Join-Path $projectRoot 'apps/web/.next/BUILD_ID'))) { throw 'Primero compila la interfaz: npm run build en apps/web.' }
if ($WithAI -and !$ollamaExe) { throw 'No se encontró Ollama. Consulta docs/LOCAL_SETUP.md.' }

function Assert-FreePort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        if ($task.Wait(500) -and $client.Connected) { throw "El puerto $Port está ocupado. Detén el servicio anterior antes de iniciar." }
    } catch [System.AggregateException] {
        # Connection refused means no listener.
    } finally { $client.Dispose() }
}
Assert-FreePort 8000
Assert-FreePort 3000
if ($WithAI) { Assert-FreePort 11434 }

$started = [System.Collections.Generic.List[object]]::new()
function Start-Owned([string]$Name, [string]$Executable, [string[]]$Arguments, [string]$Directory) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $Directory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtimeRoot "$Name.out.log") -RedirectStandardError (Join-Path $runtimeRoot "$Name.err.log")
    $started.Add([pscustomobject]@{ name=$Name; id=$process.Id; path=$Executable; startTime=$process.StartTime.ToUniversalTime().ToString('o') })
    ConvertTo-Json -InputObject @($started.ToArray()) | Set-Content $statePath
}
function Wait-Healthy([string]$Url) {
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest $Url -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Seconds 1 }
    }
    throw "No respondió $Url. Revisa los logs en .local y ejecuta Stop-Local.ps1 antes de reintentar."
}

$env:DATABASE_URL = 'sqlite:///' + (Join-Path $runtimeRoot 'soc.db').Replace('\','/')
$env:OLLAMA_URL = 'http://127.0.0.1:11434'
$env:AI_MODEL = 'qwen3:8b'
$env:API_URL = 'http://127.0.0.1:8000'
$env:STORAGE_DIR = Join-Path $runtimeRoot 'ingestion'
$env:NEXT_TELEMETRY_DISABLED = '1'
Push-Location (Join-Path $projectRoot 'apps/api')
try {
    & $pythonExe -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Falló la migración de la base local.' }
} finally { Pop-Location }

if ($WithAI) {
    $env:OLLAMA_NO_CLOUD = '1'
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $env:OLLAMA_MODELS = Join-Path $runtimeRoot 'models'
    $env:OLLAMA_CONTEXT_LENGTH = '8192'
    $env:OLLAMA_NUM_PARALLEL = '1'
    Start-Owned 'ollama' $ollamaExe @('serve') $projectRoot
    Wait-Healthy 'http://127.0.0.1:11434/api/tags'
}
Start-Owned 'api' $pythonExe @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') (Join-Path $projectRoot 'apps/api')
Wait-Healthy 'http://127.0.0.1:8000/health/ready'
$nextCli = Join-Path $projectRoot 'apps/web/node_modules/next/dist/bin/next'
# Quote paths passed through Start-Process so checkouts with spaces also work.
Start-Owned 'web' $nodeExe @(('"' + $nextCli + '"'),'start',('"' + (Join-Path $projectRoot 'apps/web') + '"'),'--hostname','127.0.0.1') $projectRoot
Wait-Healthy 'http://127.0.0.1:3000'
Write-Host 'Aplicación lista: http://127.0.0.1:3000'
Write-Host 'API: http://127.0.0.1:8000/docs'
Write-Host 'Para detener: abre Detener-SOC.cmd o ejecuta powershell -File scripts/Stop-Local.ps1'
if ($WithAI) { Write-Host 'Si falta el modelo, descárgalo con .tools/ollama/ollama.exe pull qwen3:8b (con el servidor iniciado).' }
