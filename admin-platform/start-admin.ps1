$env:USE_MOCK = 'false'
$env:SECRET_KEY = 'admin-dev-secret-32bytes-lifesync!!'
$env:ADMIN_USER = 'admin'
$env:ADMIN_PASSWORD = 'admin1234'
$env:PYTHONIOENCODING = 'utf-8'

Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Start-Process -FilePath 'C:\Python311\python.exe' `
  -ArgumentList 'C:\admin-platform\app.py' `
  -WorkingDirectory 'C:\admin-platform' `
  -RedirectStandardOutput 'C:\admin-platform\stdout.log' `
  -RedirectStandardError 'C:\admin-platform\stderr.log' `
  -WindowStyle Hidden

Start-Sleep -Seconds 5
Get-Process python -ErrorAction SilentlyContinue | Format-Table Id,CPU,Path -AutoSize
