$ErrorActionPreference = "Stop"

$taskName = "WNBA Dice Poker Real-Time"
$projectDir = $PSScriptRoot
$runner = Join-Path $projectDir "realtime_runner.py"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$python = (Get-Command python.exe -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"

if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "pythonw.exe was not found beside $python"
}

$actionOptions = @{
    Execute = $pythonw
    Argument = ('"{0}"' -f $runner)
    WorkingDirectory = $projectDir
}
$action = New-ScheduledTaskAction @actionOptions
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser

$settingsOptions = @{
    AllowStartIfOnBatteries = $true
    DontStopIfGoingOnBatteries = $true
    ExecutionTimeLimit = (New-TimeSpan -Days 3650)
    MultipleInstances = "IgnoreNew"
    RestartCount = 999
    RestartInterval = (New-TimeSpan -Minutes 1)
    StartWhenAvailable = $true
}
$settings = New-ScheduledTaskSettingsSet @settingsOptions

$principalOptions = @{
    UserId = $currentUser
    LogonType = "Interactive"
    RunLevel = "Limited"
}
$principal = New-ScheduledTaskPrincipal @principalOptions

$taskOptions = @{
    Action = $action
    Trigger = $trigger
    Settings = $settings
    Principal = $principal
}
$task = New-ScheduledTask @taskOptions

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Write-Host "Installed scheduled task: $taskName"
Write-Host "Runner: $runner"
Write-Host "Log: $(Join-Path $projectDir 'logs\realtime.log')"
