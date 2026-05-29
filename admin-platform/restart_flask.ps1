Get-Process python* | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$env:FLASK_ENV = 'production'
$env:AURORA_HOST = 'lifesync-db-cluster.cluster-ro-cxkes6gu2cse.ap-northeast-2.rds.amazonaws.com'
$env:DB_USER = 'admin'
$env:DB_PASS = 'Lifesync2024!'
$env:DB_NAME = 'lifesync'
Set-Location C:/lifesync-admin
Start-Process python -ArgumentList 'app.py' -WindowStyle Hidden
Start-Sleep -Seconds 3
$p = Get-Process python* -ErrorAction SilentlyContinue
if ($p) { "Flask restarted PID=$($p.Id)" } else { "Flask NOT running" }
