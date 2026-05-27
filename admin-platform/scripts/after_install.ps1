$ErrorActionPreference = 'Continue'
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Process cmd -ArgumentList '/c C:\start-admin.bat' -WindowStyle Hidden
Write-Host "Flask restarted via start-admin.bat"
