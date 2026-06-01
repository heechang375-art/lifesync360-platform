#!/bin/bash
LOG=/opt/private-api/ansible-deploy.log

if [ "${ANSIBLE_ENV}" != "production" ]; then
  echo "$(date) ERROR: ANSIBLE_ENV != production — 컨트롤노드 트리거 불가 (cron 환경변수 누락 의심)" >&2
  exit 1
fi

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "${CONTROL_NODE_URL}/deploy" \
  -H "X-Deploy-Token: ${DEPLOY_TOKEN}" \
  --max-time 10)

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -1)

if [ "$HTTP_CODE" != "200" ]; then
  echo "$(date) ERROR: Control Node 호출 실패 (HTTP $HTTP_CODE): $BODY" >&2
  exit 1
fi
echo "$(date) 배포 트리거 완료: $BODY" >> $LOG
