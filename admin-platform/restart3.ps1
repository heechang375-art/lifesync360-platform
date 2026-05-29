Get-Process python* | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Set-Location C:/lifesync-admin
$proc = Start-Process C:/Python311/python.exe -ArgumentList 'C:/lifesync-admin/app.py' -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 5
if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
    "Flask started OK PID=$($proc.Id)"
} else {
    "Flask failed to start"
}
