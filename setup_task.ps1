# setup_task.ps1 — Cria as tarefas agendadas no Windows Task Scheduler
# Execute como Administrador: clique direito > "Executar como administrador"

$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$runScript   = Join-Path $projectDir "run.ps1"

if (-not (Test-Path $runScript)) {
    Write-Error "run.ps1 nao encontrado em: $projectDir"
    exit 1
}

# ---------- Tarefa 1: acorda o PC às 10h25 ----------
# A acao roda wake_hold.ps1, que segura o PC acordado por 10min (ES_SYSTEM_REQUIRED).
# Sem isso, o WakeToRun acorda o PC e ele volta a dormir sozinho em ~2-3min -
# antes da _Run disparar as 10:30 -, derrubando o digest para a tarde. Ver
# comentario no topo de wake_hold.ps1 para o diagnostico completo.
$wakeScript   = Join-Path $projectDir "wake_hold.ps1"
$wakeAction   = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$wakeScript`"" `
    -WorkingDirectory $projectDir

$wakeTrigger  = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "10:25AM"

# ExecutionTimeLimit precisa cobrir os 10min de hold do wake_hold.ps1 + margem,
# senao o Task Scheduler mata o processo antes do hold terminar.
$wakeSettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 12) `
    -MultipleInstances IgnoreNew

# S4U = "Executar estando o usuario conectado ou nao". Sem isso, um reboot de
# atualizacao do Windows desloga o usuario e a tarefa nao roda (nem arma o wake).
$wakePrincipal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType S4U `
    -RunLevel Limited

$wakeTask = New-ScheduledTask `
    -Action $wakeAction `
    -Trigger $wakeTrigger `
    -Settings $wakeSettings `
    -Principal $wakePrincipal `
    -Description "Acorda o PC para rodar o Morning Call Digest"

Register-ScheduledTask `
    -TaskName "MorningCallDigest_Wake" `
    -InputObject $wakeTask `
    -Force | Out-Null

Write-Host "Tarefa de acordar criada: MorningCallDigest_Wake (10:25, seg-sex)"

# ---------- Tarefa 2: roda o script ao meio-dia ----------
$runAction   = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$runScript`"" `
    -WorkingDirectory $projectDir

$runTrigger  = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "10:30AM"

# StartWhenAvailable = roda assim que possivel se o horario for perdido
# (ex.: PC dormindo/desligado no momento do gatilho).
$runSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

# S4U: roda mesmo sem o usuario logado (ex.: tela de bloqueio pos-atualizacao).
# O main.py e headless (yt-dlp, SMTP), nao precisa de sessao de desktop.
$runPrincipal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType S4U `
    -RunLevel Highest

$runTask = New-ScheduledTask `
    -Action $runAction `
    -Trigger $runTrigger `
    -Settings $runSettings `
    -Principal $runPrincipal `
    -Description "Roda o Morning Call Digest e envia email"

Register-ScheduledTask `
    -TaskName "MorningCallDigest_Run" `
    -InputObject $runTask `
    -Force | Out-Null

Write-Host "Tarefa principal criada:  MorningCallDigest_Run  (10:30, seg-sex)"
Write-Host ""
Write-Host "Configuracao concluida. Verifique no Task Scheduler (taskschd.msc)."
Write-Host "Para testar agora: Right-click em MorningCallDigest_Run > Run"
