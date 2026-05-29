# 로컬 admin-platform → EC2 C:/admin-platform/ 배포
# 사용: & .\deploy_to_ec2.ps1

$ErrorActionPreference = 'Stop'
$INSTANCE_ID = 'i-0099e31b62d8a8ceb'
$S3_BUCKET   = 'lifesync-raw'
$S3_KEY      = 'deploy/app_deploy.zip'
$ZIP_PATH    = '.\app_deploy.zip'

Write-Host "=== 1/3 zip 생성 ==="
if (Test-Path $ZIP_PATH) { Remove-Item $ZIP_PATH }

# app.py, templates/, static/, wearable_engine.py 포함
Compress-Archive -Path app.py, templates, static, wearable_engine.py -DestinationPath $ZIP_PATH
Write-Host "zip: $((Get-Item $ZIP_PATH).Length) bytes"

Write-Host "=== 2/3 S3 업로드 ==="
aws s3 cp $ZIP_PATH "s3://$S3_BUCKET/$S3_KEY"

Write-Host "=== 3/3 EC2 배포 (SSM) ==="
python -c @"
import boto3, time, sys

ssm = boto3.client('ssm', region_name='ap-northeast-2')
instance_id = '$INSTANCE_ID'
bucket      = '$S3_BUCKET'
key         = '$S3_KEY'

commands = [
    'New-Item -ItemType Directory -Force -Path C:/temp | Out-Null',
    'New-Item -ItemType Directory -Force -Path C:/admin-platform/templates | Out-Null',
    'New-Item -ItemType Directory -Force -Path C:/admin-platform/static | Out-Null',
    f'Read-S3Object -BucketName {bucket} -Key {key} -File C:/temp/app_deploy.zip',
    'Expand-Archive -Force -Path C:/temp/app_deploy.zip -DestinationPath C:/temp/app_deploy/',
    'Copy-Item -Force C:/temp/app_deploy/app.py C:/admin-platform/app.py',
    'Copy-Item -Force -Recurse C:/temp/app_deploy/templates/* C:/admin-platform/templates/',
    'Copy-Item -Force -Recurse C:/temp/app_deploy/static/* C:/admin-platform/static/',
    'if (Test-Path C:/temp/app_deploy/wearable_engine.py) { Copy-Item -Force C:/temp/app_deploy/wearable_engine.py C:/admin-platform/wearable_engine.py }',
    'Write-Output Deploy_done; (Get-Item C:/admin-platform/app.py).LastWriteTime.ToString() + \" \" + (Get-Item C:/admin-platform/app.py).Length',
]

resp = ssm.send_command(
    InstanceIds=[instance_id],
    DocumentName='AWS-RunPowerShellScript',
    Parameters={'commands': commands},
)
cmd_id = resp['Command']['CommandId']
print('SSM Command:', cmd_id)

for _ in range(24):
    time.sleep(5)
    inv = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=instance_id)
    status = inv['Status']
    if status not in ('Pending', 'InProgress'):
        break

print('Status:', status)
print(inv.get('StandardOutputContent', ''))
if inv.get('StandardErrorContent','').strip():
    print('STDERR:', inv['StandardErrorContent'])
if status != 'Success':
    sys.exit(1)
"@

if ($LASTEXITCODE -eq 0) {
    Write-Host "배포 완료. Flask가 app.py 변경을 감지해 자동 리로드됩니다."
} else {
    Write-Error "배포 실패"
}
