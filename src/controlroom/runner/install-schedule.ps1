# Registers the daily Kingdom run in Windows Task Scheduler (current user, no admin needed).
# Triggers (all immediate): logon, unlock, wake from sleep, and daily 10:00 as a fallback.
# kingdom.py makes sure it runs only ONCE per day and waits for the network itself,
# so extra triggers are harmless.
#   Install:   powershell -ExecutionPolicy Bypass -File hq\install-schedule.ps1
#   Remove:    powershell -ExecutionPolicy Bypass -File hq\install-schedule.ps1 -Remove
param([switch]$Remove)

$TaskName = "Control Room runner"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed '$TaskName'."
    return
}

# Home folder: $env:CONTROLROOM_HOME, or ~/.controlroom (same rule as the Python code).
$hq = if ($env:CONTROLROOM_HOME) { $env:CONTROLROOM_HOME } else { Join-Path $HOME ".controlroom" }
$python = (& python -c "import sys; print(sys.executable)").Trim()   # real interpreter, not the WindowsApps alias
$user = "$env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"`$env:CONTROLROOM_HOME='$hq'; & '$python' -m controlroom run`"" `
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
Write-Host "Registered '$TaskName': starts as soon as you log on, unlock or wake the laptop (once per day)."
