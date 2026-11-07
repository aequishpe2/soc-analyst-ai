param([switch]$WithAI)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$ready = Invoke-RestMethod 'http://127.0.0.1:8000/health/ready' -TimeoutSec 10
if ($ready.status -ne 'ready') { throw 'API no preparada.' }
$web = Invoke-WebRequest 'http://127.0.0.1:3000' -UseBasicParsing -TimeoutSec 10
if ($web.StatusCode -ne 200) { throw 'La interfaz no responde.' }
$system = Invoke-RestMethod 'http://127.0.0.1:3000/api/v1/system' -TimeoutSec 10
Write-Host "API y web: OK. Ollama: $($system.ai_status)."
if ($WithAI) {
    if ($system.ai_status -ne 'ready') { throw 'El modelo local no está disponible.' }
    # Synthetic smoke prompt only; never include client records in this check.
    $body = @{
        model='qwen3:8b'; prompt='Responde solamente LOCAL_OK.'
        stream=$false; think=$false; keep_alive=0
        options=@{temperature=0; num_predict=32; num_ctx=8192}
    } | ConvertTo-Json -Depth 4
    $result = Invoke-RestMethod 'http://127.0.0.1:11434/api/generate' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 300
    if (!$result.done -or [string]::IsNullOrWhiteSpace($result.response)) { throw 'El modelo no produjo una respuesta completa.' }
    $summary = [pscustomobject]@{
        model=$result.model; response=$result.response; done=$result.done
        total_seconds=[math]::Round($result.total_duration / 1e9, 2)
        generated_tokens=$result.eval_count
        tokens_per_second=if ($result.eval_duration -gt 0) { [math]::Round($result.eval_count / ($result.eval_duration / 1e9), 2) } else { 0 }
    }
    New-Item -ItemType Directory -Force (Join-Path $projectRoot '.local') | Out-Null
    $summary | ConvertTo-Json | Set-Content (Join-Path $projectRoot '.local/ai-smoke.json')
    $summary | Format-List
    Write-Host 'Inferencia local comprobada. Esto no valida precisión analítica ni rendimiento con logs reales.'
}
