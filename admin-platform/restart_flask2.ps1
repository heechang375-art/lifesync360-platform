Get-Process python* | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$env:FLASK_ENV = 'production'
$env:AURORA_HOST = 'lifesync-db-cluster.cluster-ro-cxkes6gu2cse.ap-northeast-2.rds.amazonaws.com'
$env:DB_USER = 'admin'
$env:DB_PASS = 'Lifesync2024!'
$env:DB_NAME = 'lifesync'
Set-Location C:/lifesync-admin
$proc = Start-Process C:/Python311/python.exe -ArgumentList 'app.py' -WindowStyle Hidden -PassThru -RedirectStandardOutput C:/lifesync-admin/flask_stdout.log -RedirectStandardError C:/lifesync-admin/flask_stderr.log
Start-Sleep -Seconds 5
if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
    "Flask running PID=$($proc.Id)"
} else {
    "Flask exited. stderr:"
    Get-Content C:/lifesync-admin/flask_stderr.log -ErrorAction SilentlyContinue | Select-Object -Last 30
}
