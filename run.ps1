# run.ps1 - Carrega segredos e executa o Morning Call Digest
Set-Location $PSScriptRoot

$logsDir  = Join-Path $PSScriptRoot "logs"
$hoje     = Get-Date -Format "yyyy-MM-dd"
$logFile  = Join-Path $logsDir "$hoje.log"
$errFile  = Join-Path $logsDir "$hoje.error.log"

if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }

function Write-Log ($msg) {
    $linha = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $linha
    Add-Content -Path $logFile -Value $linha -Encoding UTF8
}

function Abort ($motivo) {
    $linha = "[$(Get-Date -Format 'HH:mm:ss')] ERRO FATAL: $motivo"
    Write-Host $linha
    Add-Content -Path $errFile -Value $linha -Encoding UTF8
    Start-Sleep -Seconds 10
    rundll32.exe powrprof.dll,SetSuspendState 0,1,0
    exit 1
}

# Guard: evita segunda execucao no mesmo dia
if ((Test-Path $logFile) -and (Get-Content $logFile -Raw -Encoding UTF8) -match "Script finalizado") {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Execucao do dia ja concluida - abortando."
    Start-Sleep -Seconds 10
    rundll32.exe powrprof.dll,SetSuspendState 0,1,0
    exit 0
}

# Valida e carrega secrets.env
$secretsFile = Join-Path $PSScriptRoot "secrets.env"
if (-not (Test-Path $secretsFile)) { Abort "secrets.env nao encontrado em $PSScriptRoot" }

try {
    Get-Content $secretsFile -Encoding UTF8 | ForEach-Object {
        if ($_ -match '^([^#\s][^=]+)=(.+)$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
        }
    }
} catch {
    Abort "Falha ao carregar secrets.env: $_"
}

# Valida variaveis obrigatorias
foreach ($var in @('GEMINI_API_KEY', 'EMAIL_REMETENTE', 'EMAIL_SENHA_APP')) {
    if (-not [System.Environment]::GetEnvironmentVariable($var, 'Process')) {
        Abort "Variavel $var ausente em secrets.env"
    }
}

# Localiza Python
$_cmd = Get-Command py -ErrorAction SilentlyContinue
$python = if ($_cmd) { $_cmd.Source } else { $null }
if (-not $python) {
    $_cmd = Get-Command python -ErrorAction SilentlyContinue
    $python = if ($_cmd) { $_cmd.Source } else { $null }
}
if (-not $python) { Abort "Python nao encontrado no PATH (py / python)" }

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8       = '1'

Write-Log "Iniciando Morning Call Digest | python=$python"

# Roda o pipeline - sem 2>&1 para evitar NativeCommandError no PowerShell 5.1
# stderr do Python vai para o console (capturado pelo Task Scheduler nos logs de evento)
& $python main.py | Tee-Object -FilePath $logFile -Append

Write-Log "Script finalizado"

Start-Sleep -Seconds 30
rundll32.exe powrprof.dll,SetSuspendState 0,1,0
