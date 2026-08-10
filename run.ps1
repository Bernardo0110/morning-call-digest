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

# Guard: evita segunda execucao no mesmo dia. So bloqueia em cima de um SUCESSO
# de verdade ("Script finalizado OK") - uma execucao que terminou com erro nao
# ativa o guard, pra deixar uma proxima tentativa (manual ou StartWhenAvailable)
# rodar ainda hoje em vez de ficar travada ate amanha.
if ((Test-Path $logFile) -and (Get-Content $logFile -Raw -Encoding UTF8) -match "Script finalizado OK") {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Execucao do dia ja concluida com sucesso - abortando."
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

# Decodifica a saida UTF-8 do Python corretamente (senao acentos e emoji corrompem)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

Write-Log "Iniciando Morning Call Digest | python=$python"

# Diagnostico de wake/boot: ajuda a diferenciar "acordou pelo wake timer as
# 10:25" de "PC foi ligado na mao mais tarde" sem precisar ir no Visualizador
# de Eventos do Windows toda vez que o horario de inicio for atipico.
try {
    $boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
    Write-Log "Ultimo boot do PC: $($boot.ToString('yyyy-MM-dd HH:mm:ss'))"
} catch {
    Write-Log "Nao foi possivel obter o horario do ultimo boot: $_"
}
try {
    $lastwake = (powercfg /lastwake) -join " | "
    Write-Log "powercfg /lastwake: $lastwake"
} catch {
    Write-Log "Nao foi possivel obter powercfg /lastwake: $_"
}

# Roda o pipeline com timestamp por linha (facilita medir duracao de cada
# etapa/canal depois, sem ter que inferir pelo contexto). stderr vai para um
# arquivo separado (nao 2>&1 - mistura no stream de sucesso e vira
# NativeCommandError no PowerShell 5.1) e e' apensado ao log e ao .error.log
# no final, para que um crash real do main.py fique visível em vez de sumir
# no console de uma sessao sem interface (S4U).
$stderrTmp = Join-Path $logsDir "$hoje.stderr.tmp"
if (Test-Path $stderrTmp) { Remove-Item $stderrTmp -Force }

& $python main.py 2>$stderrTmp | ForEach-Object {
    $linha = "[$(Get-Date -Format 'HH:mm:ss')] $_"
    Write-Host $linha
    Add-Content -Path $logFile -Value $linha -Encoding UTF8
}
$exitCode = $LASTEXITCODE

if ((Test-Path $stderrTmp) -and (Get-Item $stderrTmp).Length -gt 0) {
    Write-Log "----- stderr do Python (exit code $exitCode) -----"
    Get-Content -Path $stderrTmp -Encoding UTF8 | ForEach-Object {
        Add-Content -Path $logFile -Value "[$(Get-Date -Format 'HH:mm:ss')] STDERR: $_" -Encoding UTF8
    }
    Add-Content -Path $errFile -Value (Get-Content -Path $stderrTmp -Raw -Encoding UTF8) -Encoding UTF8
}
Remove-Item $stderrTmp -Force -ErrorAction SilentlyContinue

if ($exitCode -ne 0) {
    Write-Log "Script finalizado COM ERRO (exit code $exitCode) - ver stderr acima e $($hoje).error.log"
} else {
    Write-Log "Script finalizado OK"
}

Start-Sleep -Seconds 30
rundll32.exe powrprof.dll,SetSuspendState 0,1,0
