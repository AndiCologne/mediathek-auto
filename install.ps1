# Richtet den wöchentlichen Lauf unter Windows ein: jeden Mittwoch um 02:00 Uhr.
# Aufruf in PowerShell – am besten "Als Administrator ausführen", dann läuft der Film-Download
# auch, wenn niemand angemeldet ist (Pfad zum Code-Ordner anpassen):
#   powershell -ExecutionPolicy Bypass -File "D:\Movies\.mediathek-auto\install.ps1"
$ErrorActionPreference = 'Stop'
$Dir      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script   = Join-Path $Dir 'mediathek_auto.py'
$TaskName = 'Mediathek-Auto'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# --- Python 3.9+ finden (py-Launcher bevorzugt; der Store-Platzhalter "python" zählt nicht) ---
function Find-Python {
    $tries = @(
        @{ Exe = 'py';      Args = @('-3') },
        @{ Exe = 'python';  Args = @() },
        @{ Exe = 'python3'; Args = @() }
    )
    foreach ($t in $tries) {
        if (-not (Get-Command $t.Exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $a = @($t.Args) + @('-c', 'import sys; print(sys.executable if sys.version_info >= (3, 9) else str())')
            $out = & $t.Exe @a 2>$null | Select-Object -Last 1
            if ($LASTEXITCODE -eq 0 -and $out -and (Test-Path $out.Trim())) { return $out.Trim() }
        } catch {}
    }
    return $null
}
$Py = Find-Python
if (-not $Py) {
    Write-Host "❌ Kein Python 3.9+ gefunden. Bitte installieren: winget install Python.Python.3.12" -ForegroundColor Red
    exit 1
}
# pythonw.exe läuft ohne Konsolenfenster
$Pyw = Join-Path (Split-Path $Py) 'pythonw.exe'
if (-not (Test-Path $Pyw)) { $Pyw = $Py }
Write-Host "✔ Python: $Py"

New-Item -ItemType Directory -Force -Path (Join-Path $Dir 'logs') | Out-Null

# --- config.json anlegen bzw. ins beschriftete Format bringen (Werte bleiben erhalten) ---
$Cfg = Join-Path $Dir 'config.json'
if (-not (Test-Path $Cfg) -or -not (Select-String -Path $Cfg -Pattern '"ANPASSBAR"' -Quiet)) {
    & $Py $Script --config-erstellen
    Write-Host "✔ config.json angelegt – bitte zielordner, email_empfaenger und den Abschnitt EMAIL eintragen:"
    Write-Host "   notepad `"$Cfg`""
}

# --- Programme, Zielordner und E-Mail prüfen ---
Write-Host ""
& $Py $Script --pruefen
$checkOk = ($LASTEXITCODE -eq 0)
Write-Host ""

# --- Aufgabe in der Aufgabenplanung anlegen ---
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin  = ([Security.Principal.WindowsPrincipal]$identity).IsInRole(
                [Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    # S4U: läuft auch ohne Anmeldung, ohne gespeichertes Passwort (lokale Laufwerke und Internet gehen)
    $principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType S4U -RunLevel Limited
    $modeText  = 'auch wenn niemand angemeldet ist'
} else {
    $principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
    $modeText  = 'nur, wenn du angemeldet bist (für "auch ohne Anmeldung": install.ps1 als Administrator ausführen)'
}
$action   = New-ScheduledTaskAction -Execute $Pyw -Argument "`"$Script`"" -WorkingDirectory $Dir
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At '02:00'
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
                -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -ExecutionTimeLimit (New-TimeSpan -Hours 23) -MultipleInstances IgnoreNew -Priority 7
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Force `
    -Description 'Mediathek-Auto: Spielfilme aus ARD/ZDF laden und mit HandBrakeCLI umcodieren' | Out-Null
Write-Host "✔ Zeitplan aktiv: jeden Mittwoch 02:00 Uhr, $modeText"
Write-Host "  Der PC wird dafür aus dem Energiesparmodus geweckt; ein verpasster Lauf wird nachgeholt."
Write-Host "  Damit das Wecken klappt: Energieoptionen → Erweiterte Einstellungen → Energie sparen →"
Write-Host "  Zeitgeber zur Aktivierung zulassen → Aktivieren."

# --- Test-E-Mail ---
$hasMail = & $Py -c "import sys; sys.path.insert(0, sys.argv[1]); import mediathek_auto as M; print(1 if M.email_configured(M.load_config()) else 0)" $Dir
if ("$hasMail".Trim() -eq '1') {
    Write-Host ""
    Write-Host "✉️  Sende Test-E-Mail …"
    & $Py $Script --test-email
    if ($LASTEXITCODE -eq 0) { Write-Host "✔ Test-E-Mail gesendet – bitte Posteingang (und Spam-Ordner) prüfen." }
    else { Write-Host "⚠️  Test-E-Mail fehlgeschlagen – Details in logs\, Einstellungen unter EMAIL in config.json prüfen." -ForegroundColor Yellow }
} else {
    Write-Host "ℹ️  Keine E-Mail eingerichtet – Abschlussberichte per E-Mail sind aus."
}
if (-not $checkOk) {
    Write-Host ""
    Write-Host "⚠️  Die Prüfung oben hat Fehler gemeldet. Bitte beheben, sonst schlägt der Lauf fehl." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Nächste Schritte:"
Write-Host "  1) Testlauf ohne Download:"
Write-Host "     & `"$Py`" `"$Script`" --dry-run"
Write-Host "  2) Einen echten Film als Probe:"
Write-Host "     & `"$Py`" `"$Script`" --limit 1"
Write-Host "  3) Hintergrund-Lauf sofort auslösen:"
Write-Host "     Start-ScheduledTask -TaskName $TaskName"
