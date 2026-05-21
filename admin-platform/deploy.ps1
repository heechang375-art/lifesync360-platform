# CodeCommit에서 최신 코드 pull 후 Flask 재시작
# 사용: & C:\admin-platform\deploy.ps1

$ErrorActionPreference = 'Stop'
$PYTHON = 'C:\Program Files\Python311\python.exe'

Write-Host "=== Pulling from CodeCommit ==="
& $PYTHON C:\deploy_from_cc.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "CodeCommit pull failed (exit $LASTEXITCODE)"
    exit 1
}

Write-Host "=== Restarting Flask ==="
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NonInteractive -File C:\admin-platform\start-admin.ps1" -WindowStyle Hidden
Start-Sleep -Seconds 5

$proc = Get-Process python -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "Flask started: PID $($proc.Id)"
} else {
    Write-Error "Flask did not start"
    exit 1
}
