# wake_hold.ps1 - Acao da tarefa MorningCallDigest_Wake (10:25).
#
# O WakeToRun acorda o PC, mas so mantem o sistema ligado enquanto ESTA tarefa
# esta rodando. A acao antiga era so "echo wake", que termina em menos de 1s -
# sem mais nenhuma tarefa segurando o estado de energia, o Windows voltava a
# suspender sozinho em ~2-3min, antes da MorningCallDigest_Run disparar as
# 10:30. Resultado: a tarefa _Run era perdida e so rodava via StartWhenAvailable
# quando alguem ligava o PC manualmente na tarde/noite (confirmado no
# Visualizador de Eventos em 17/06, 25/06, 09/07, 10/07, 17/07, 22/07, 30/07).
#
# Este script segura o PC acordado (ES_SYSTEM_REQUIRED) por 10min - cobrindo
# com folga a lacuna ate a _Run assumir as 10:30 e o main.py travar a
# suspensao por conta propria (_impedir_suspensao em main.py). Nao ha risco
# de atrasar o desligamento no fim do dia: a suspensao forcada do run.ps1
# (SetSuspendState) ignora bloqueios de ES_SYSTEM_REQUIRED, entao mesmo que
# este script ainda esteja "segurando" o PC, o desligamento programado
# continua funcionando normalmente.

# Log proprio (nao compartilha arquivo com o run.ps1, que so comeca a
# escrever quando a _Run dispara) - e o unico jeito de confirmar, dia a dia,
# se esta correcao esta realmente segurando o PC acordado, sem repetir a
# investigacao manual no Visualizador de Eventos.
$logsDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }
$wakeLog = Join-Path $logsDir "$(Get-Date -Format 'yyyy-MM-dd').wake.log"

function Write-WakeLog ($msg) {
    Add-Content -Path $wakeLog -Value "[$(Get-Date -Format 'HH:mm:ss')] $msg" -Encoding UTF8
}

Write-WakeLog "wake_hold.ps1 iniciado"
try {
    $lastwake = (powercfg /lastwake) -join " | "
    Write-WakeLog "powercfg /lastwake: $lastwake"
} catch {
    Write-WakeLog "Nao foi possivel obter powercfg /lastwake: $_"
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WakeHold {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@

$ES_CONTINUOUS      = 0x80000000
$ES_SYSTEM_REQUIRED = 0x00000001

$resultado = [WakeHold]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
if ($resultado -eq 0) {
    Write-WakeLog "⚠️  SetThreadExecutionState retornou 0 - hold pode nao ter sido aplicado"
} else {
    Write-WakeLog "PC segurado acordado ate ~$((Get-Date).AddSeconds(600).ToString('HH:mm:ss'))"
}

# 10:25 -> 10:35: cobre com folga o gatilho da _Run (10:30) mais o tempo de
# o Task Scheduler despachar o processo e o main.py iniciar.
Start-Sleep -Seconds 600

[WakeHold]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
Write-WakeLog "Hold liberado - suspensao por ociosidade volta ao normal"
