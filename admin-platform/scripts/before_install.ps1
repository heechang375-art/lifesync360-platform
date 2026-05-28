$ErrorActionPreference = 'Continue'
Stop-ScheduledTask -TaskName AdminApp -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
$still = Get-Process -Name python -ErrorAction SilentlyContinue
if ($still) {
    $still | ForEach-Object { $_.Kill() }
    Start-Sleep -Seconds 2
}
Write-Host "AdminApp stopped before install"
