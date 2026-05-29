$env:SECRET_KEY = "dev-secret-32bytes-lifesync!!"
$env:ADMIN_USER = "admin"
$env:ADMIN_PASSWORD = "admin123"
$env:USE_MOCK = "false"
$env:AWS_DEFAULT_REGION = "ap-northeast-2"
$env:ONPREM_BASE_URL = "http://172.16.1.73"
$env:LIFESYNC_RAW_S3_BUCKET = "lifesync-raw"
$env:AURORA_HOST = "auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com"
$env:DB_USER = "admin"
$env:DB_PASS = "ChangeMe123!"
$env:DB_NAME = "lifesync360"
Set-Location C:/admin-platform
& "C:/Python311/python.exe" app.py *>> C:/admin-platform/app.log
