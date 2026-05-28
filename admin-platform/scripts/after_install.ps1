$ErrorActionPreference = 'Continue'
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName AdminApp
Start-Sleep -Seconds 5
$port = Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue
if ($port) {
    Write-Host "Flask listening on :5001"
} else {
    Write-Host "[WARN] :5001 not yet listening — check C:\admin-platform\app.log"
}
Write-Host "Flask restarted via AdminApp scheduled task"
