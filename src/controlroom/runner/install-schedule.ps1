# Registers the daily run in Windows Task Scheduler (current user, no admin needed).
# Triggers (all immediate): logon, unlock, wake from sleep, and daily 10:00 as a fallback.
# The runner makes sure it runs only ONCE per day and waits for the network itself,
# so extra triggers are harmless.
#
#   Install:   powershell -ExecutionPolicy Bypass -File install-schedule.ps1 [-HomeDir <folder>] [-Python <python.exe>]
#   Remove:    powershell -ExecutionPolicy Bypass -File install-schedule.ps1 -Remove
#
#   -HomeDir the home folder (config.toml, teams/, state/). Default: $env:CONTROLROOM_HOME, else ~/.controlroom
#   -Python  an interpreter that has the controlroom package installed. Default: `python` on PATH
param(
    [switch]$Remove,
    [string]$HomeDir = "",
    [string]$Python = ""
)

$TaskName = "Control Room runner"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed '$TaskName'."
    return
}

$hq = if ($HomeDir) { $HomeDir } elseif ($env:CONTROLROOM_HOME) { $env:CONTROLROOM_HOME } else { Join-Path $HOME ".controlroom" }
$hq = (Resolve-Path -LiteralPath $hq -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath (Join-Path $hq "config.toml"))) {
    throw "No config.toml in $hq. Copy config.example.toml there first."
}
# The real interpreter, not the WindowsApps alias.
$py = if ($Python) { $Python } else { (& python -c "import sys; print(sys.executable)").Trim() }
& $py -c "import controlroom" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "$py cannot import controlroom. Pass -Python with the interpreter you installed it into."
}
$user = "$env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"`$env:CONTROLROOM_HOME='$hq'; & '$py' -m controlroom run`"" `
    -WorkingDirectory $hq

$logon = New-ScheduledTaskTrigger -AtLogOn -User $user
$daily = New-ScheduledTaskTrigger -Daily -At 10:00
$cls = Get-CimClass -Namespace Root/Microsoft/Windows/TaskScheduler -ClassName MSFT_TaskSessionStateChangeTrigger
$unlock = New-CimInstance -CimClass $cls -ClientOnly
$unlock.StateChange = 8   # SessionUnlock
$unlock.UserId = $user
$evc = Get-CimClass -Namespace Root/Microsoft/Windows/TaskScheduler -ClassName MSFT_TaskEventTrigger
$wake = New-CimInstance -CimClass $evc -ClientOnly
$wake.Enabled = $true
$wake.Subscription = "<QueryList><Query Id='0' Path='System'><Select Path='System'>*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and EventID=1]]</Select></Query></QueryList>"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($logon, $unlock, $wake, $daily) `
    -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered '$TaskName' for $hq with $py"
Write-Host "It starts as soon as you log on, unlock or wake the computer (once per day)."
