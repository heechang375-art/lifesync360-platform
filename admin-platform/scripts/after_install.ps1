$ErrorActionPreference = 'Continue'
$proc = Get-Process -Name python -ErrorAction SilentlyContinue
if (-not $proc) {
    Start-ScheduledTask -TaskName "AdminApp" -ErrorAction SilentlyContinue
    Write-Host "AdminApp task started"
} else {
    Write-Host "Python running - Flask auto-reload picks up changes"
}
