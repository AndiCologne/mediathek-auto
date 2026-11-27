# Entfernt den wöchentlichen Zeitplan (Skript, Logs und Filme bleiben erhalten).
#   powershell -ExecutionPolicy Bypass -File "D:\Movies\.mediathek-auto\uninstall.ps1"
$TaskName = 'Mediathek-Auto'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "✔ Zeitplan entfernt."
} else {
    Write-Host "ℹ️  Kein Zeitplan '$TaskName' vorhanden."
}
