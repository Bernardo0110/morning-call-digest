# run.ps1 — Carrega segredos e executa o Morning Call Digest
Set-Location $PSScriptRoot

$secretsFile = Join-Path $PSScriptRoot "secrets.env"
if (-not (Test-Path $secretsFile)) {
    Write-Error "Arquivo secrets.env nao encontrado. Copie secrets.env.example e preencha."
    exit 1
}

Get-Content $secretsFile | ForEach-Object {
    if ($_ -match '^([^#\s][^=]+)=(.+)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
    }
}

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8       = '1'

# Cria pasta de logs se nao existir
$logsDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }

$logFile = Join-Path $logsDir ("{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))
$inicio  = Get-Date -Format "HH:mm:ss"

"[$inicio] Iniciando Morning Call Digest" | Tee-Object -FilePath $logFile -Append

python main.py 2>&1 | Tee-Object -FilePath $logFile -Append

$fim = Get-Date -Format "HH:mm:ss"
"[$fim] Script finalizado" | Tee-Object -FilePath $logFile -Append

# Volta a suspender após o script terminar
Start-Sleep -Seconds 30
rundll32.exe powrprof.dll,SetSuspendState 0,1,0
