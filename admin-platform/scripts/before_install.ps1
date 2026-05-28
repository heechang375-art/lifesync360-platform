$ErrorActionPreference = 'Continue'

# 1. AdminApp 스케줄 태스크 + Python 프로세스 종료
Stop-ScheduledTask -TaskName AdminApp -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Get-WmiObject Win32_Process -Filter "Name='cmd.exe'" |
    Where-Object { $_.CommandLine -like '*start-admin*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$remaining = Get-Process -Name python -ErrorAction SilentlyContinue
if ($remaining) { $remaining | ForEach-Object { $_.Kill() }; Start-Sleep -Seconds 2 }

# 2. C:\admin-platform 디렉토리 내용 삭제 (dir 자체는 남김)
# CodeDeploy Ruby 에이전트가 Dir.rmdir 로 비재귀 제거 시도 — 비어있어야 성공
if (Test-Path "C:\admin-platform") {
    Remove-Item -Path "C:\admin-platform\*" -Recurse -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

Write-Host "AdminApp stopped and C:\admin-platform cleared"
