# setup_task.ps1 — Cria as tarefas agendadas no Windows Task Scheduler
# Execute como Administrador: clique direito > "Executar como administrador"

$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$runScript   = Join-Path $projectDir "run.ps1"

if (-not (Test-Path $runScript)) {
    Write-Error "run.ps1 nao encontrado em: $projectDir"
    exit 1
}

# ---------- Tarefa 1: acorda o PC às 11h55 ----------
$wakeAction   = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c echo wake"

$wakeTrigger  = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "09:55AM"

$wakeSettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -MultipleInstances IgnoreNew

$wakeTask = New-ScheduledTask `
    -Action $wakeAction `
    -Trigger $wakeTrigger `
    -Settings $wakeSettings `
    -Description "Acorda o PC para rodar o Morning Call Digest"

Register-ScheduledTask `
    -TaskName "MorningCallDigest_Wake" `
    -InputObject $wakeTask `
    -Force | Out-Null

Write-Host "Tarefa de acordar criada: MorningCallDigest_Wake (09:55, seg-sex)"

# ---------- Tarefa 2: roda o script ao meio-dia ----------
$runAction   = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$runScript`"" `
    -WorkingDirectory $projectDir

$runTrigger  = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "10:00AM"

$runSettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

$runPrincipal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
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

Write-Host "Tarefa principal criada:  MorningCallDigest_Run  (10:00, seg-sex)"
Write-Host ""
Write-Host "Configuracao concluida. Verifique no Task Scheduler (taskschd.msc)."
Write-Host "Para testar agora: Right-click em MorningCallDigest_Run > Run"
