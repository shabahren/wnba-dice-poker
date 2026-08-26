$ErrorActionPreference = "Stop"

$taskName = "WNBA Dice Poker Real-Time"
$projectDir = $PSScriptRoot
$runner = Join-Path $projectDir "realtime_runner.py"
$gamesFile = Join-Path $projectDir "games.json"
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

$nowUtc = [DateTimeOffset]::UtcNow
$systemTimeZone = Get-TimeZone
$triggers = @()
$scheduledGames = @()
$gamesJson = Get-Content -LiteralPath $gamesFile -Raw
$jsonOptions = @{ InputObject = $gamesJson }
if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey("DateKind")) {
    $jsonOptions.DateKind = "String"
}
$games = ConvertFrom-Json @jsonOptions

foreach ($game in $games) {
    $startUtc = [DateTimeOffset]::Parse([string]$game.start_utc).ToUniversalTime()
    $endUtc = $startUtc.AddMinutes(150)
    if ($endUtc -le $nowUtc) {
        continue
    }

    $triggerAtUtc = $startUtc.AddSeconds(5)
    while ($triggerAtUtc -le $nowUtc) {
        $triggerAtUtc = $triggerAtUtc.AddMinutes(5)
    }
    if ($triggerAtUtc -ge $endUtc) {
        continue
    }

    $triggerAtLocal = [TimeZoneInfo]::ConvertTime(
        $triggerAtUtc,
        $systemTimeZone
    ).DateTime
    $endLocal = [TimeZoneInfo]::ConvertTime(
        $endUtc,
        $systemTimeZone
    ).DateTime
    $remaining = $endUtc - $triggerAtUtc
    if ($remaining.TotalMinutes -ge 5) {
        $triggerOptions = @{
            Once = $true
            At = $triggerAtLocal
            RepetitionInterval = (New-TimeSpan -Minutes 5)
            RepetitionDuration = $remaining
        }
        $triggers += New-ScheduledTaskTrigger @triggerOptions
    } else {
        $triggers += New-ScheduledTaskTrigger -Once -At $triggerAtLocal
    }
    $scheduledGames += [PSCustomObject]@{
        Game = [string]$game.id
        FirstRunLocal = $triggerAtLocal
        EndLocal = $endLocal
    }
}

if ($triggers.Count -eq 0) {
    throw "No future or active games were found in games.json."
}

$settingsOptions = @{
    AllowStartIfOnBatteries = $true
    DontStopIfGoingOnBatteries = $true
    ExecutionTimeLimit = (New-TimeSpan -Minutes 4)
    MultipleInstances = "IgnoreNew"
    RestartCount = 3
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
    Trigger = $triggers
    Settings = $settings
    Principal = $principal
}
$task = New-ScheduledTask @taskOptions

Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Write-Host "Installed scheduled task: $taskName"
Write-Host "Runner: $runner"
Write-Host "Log: $(Join-Path $projectDir 'logs\realtime.log')"
Write-Host ""
Write-Host "Scheduled match windows:"
$scheduledGames | Format-Table -AutoSize
