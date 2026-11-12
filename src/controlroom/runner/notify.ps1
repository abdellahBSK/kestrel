# Windows notification for the King, with buttons that open URLs/files.
#   powershell -File notify.ps1 -Title "..." -Body "..." -Url "https://..." [-Url2 "file:///..." -Label2 "Brief"]
param(
    [string]$Title = "Control Room",
    [string]$Body = "",
    [string]$Url = "https://github.com/pulls",
    [string]$Label = "Open PRs",
    [string]$Url2 = "",
    [string]$Label2 = "Daily brief"
)
function Esc([string]$s) { [System.Security.SecurityElement]::Escape($s) }

[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$actions = "<action content=`"$(Esc $Label)`" activationType=`"protocol`" arguments=`"$(Esc $Url)`"/>"
if ($Url2) { $actions += "<action content=`"$(Esc $Label2)`" activationType=`"protocol`" arguments=`"$(Esc $Url2)`"/>" }
$xml = @"
<toast activationType="protocol" launch="$(Esc $Url)">
  <visual><binding template="ToastGeneric"><text>$(Esc $Title)</text><text>$(Esc $Body)</text></binding></visual>
  <actions>$actions</actions>
</toast>
"@
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
$toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
