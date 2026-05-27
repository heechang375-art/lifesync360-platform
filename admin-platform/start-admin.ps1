$env:USE_MOCK = 'false'
$env:SECRET_KEY = 'admin-dev-secret-32bytes-lifesync!!'
$env:ADMIN_USER = 'admin'
$env:ADMIN_PASSWORD = 'admin1234'
$env:PYTHONIOENCODING = 'utf-8'
$env:ONPREM_BASE_URL = 'http://172.16.1.73'
$env:AWS_DEFAULT_REGION = 'ap-northeast-2'
$env:LIFESYNC_RAW_S3_BUCKET = 'lifesync-raw'

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
