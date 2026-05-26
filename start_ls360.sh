#!/bin/bash
set -e

# Secrets에서 DB 자격 로드 (master secret JSON keys: host/username/password)
SECRET=$(aws secretsmanager get-secret-value --secret-id /lifesync/dev/db/master --region ap-northeast-2 --query SecretString --output text)
export AURORA_HOST=$(echo $SECRET | python3 -c "import sys,json;print(json.load(sys.stdin)['host'])")
export DB_USER=$(echo $SECRET | python3 -c "import sys,json;print(json.load(sys.stdin)['username'])")
export DB_PASS=$(echo $SECRET | python3 -c "import sys,json;print(json.load(sys.stdin)['password'])")

# Redis endpoint 별도 secret (lifesync/dev/redis JSON keys: host/port)
REDIS_SECRET=$(aws secretsmanager get-secret-value --secret-id lifesync/dev/redis --region ap-northeast-2 --query SecretString --output text)
export REDIS_HOST=$(echo $REDIS_SECRET | python3 -c "import sys,json;print(json.load(sys.stdin)['host'])")
export DB_NAME="lifesync360"
export REDIS_PORT="6379"
JWT_SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id ecs-jwt-signing --region ap-northeast-2 --query SecretString --output text)
export JWT_SECRET=$(echo $JWT_SECRET_JSON | python3 -c "import sys,json;print(json.load(sys.stdin)['jwt'])")
export USE_MOCK="false"
export AWS_REGION="ap-northeast-2"
export DYNAMO_TABLE="lifesync_customer_result"
export ONPREM_QUERY_LAMBDA="lifesync-onprem-customer-query"
export PROFILE_SYNC_LAMBDA="customer-profile-sync"

# 기존 프로세스 종료
pkill -f "python3 /opt/ls360/app.py" 2>/dev/null || true
sleep 1

# 시작
cd /opt/ls360
nohup /opt/ls360_venv/bin/python app.py >> /opt/ls360.log 2>&1 &
echo $! > /opt/ls360.pid
echo "Started PID=$(cat /opt/ls360.pid)"
sleep 4
curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:5000/login
