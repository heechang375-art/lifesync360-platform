#!/bin/bash
# EC2 Control Node에서 실행
# SSH 키 생성 후 온프레미스 VM 3대에 공개키 배포
# 환경변수 ANSIBLE_PASS가 설정돼 있으면 non-interactive로 동작 (UserData용)

KEY_PATH=~/.ssh/lifesync360-onprem.pem
ANSIBLE_USER=ansible
BRIDGE_HOST=192.168.56.13
INTERNAL_HOSTS=(192.168.56.11 192.168.56.12)

# ── 1. SSH 키 생성 ────────────────────────────────────
mkdir -p ~/.ssh && chmod 700 ~/.ssh

if [ ! -f "$KEY_PATH" ]; then
    echo "[1/3] SSH 키 생성 중..."
    ssh-keygen -t rsa -b 4096 -f "$KEY_PATH" -N ""
    echo "      생성 완료: $KEY_PATH"
else
    echo "[1/3] 기존 키 사용: $KEY_PATH"
fi

# ── 2. ansible 계정 패스워드 확인 ─────────────────────
if [ -z "$ANSIBLE_PASS" ]; then
    read -s -p "[2/3] ansible 계정 패스워드 입력: " ANSIBLE_PASS
    echo
fi

if [ -z "$ANSIBLE_PASS" ]; then
    echo "ERROR: 패스워드가 없습니다. ANSIBLE_PASS 환경변수 또는 직접 입력이 필요합니다."
    exit 1
fi

# sshpass 설치 확인
if ! command -v sshpass &> /dev/null; then
    echo "      sshpass 설치 중..."
    sudo apt-get install -y sshpass -q
fi

# ── 3. 공개키 배포 ────────────────────────────────────
echo "[3/3] 공개키 배포 시작..."

# ls-api: EC2에서 직접
echo "  → $BRIDGE_HOST (직접 연결)"
sshpass -p "$ANSIBLE_PASS" ssh-copy-id \
    -i "${KEY_PATH}.pub" \
    -o StrictHostKeyChecking=no \
    "${ANSIBLE_USER}@${BRIDGE_HOST}"

if [ $? -ne 0 ]; then
    echo "  ✗ $BRIDGE_HOST 실패 — ProxyJump 배포 중단"
    exit 1
fi
echo "  ✓ $BRIDGE_HOST 완료"

# ls-db, ls-token: ls-api 경유
for HOST in "${INTERNAL_HOSTS[@]}"; do
    echo "  → $HOST (ProxyJump via $BRIDGE_HOST)"
    sshpass -p "$ANSIBLE_PASS" ssh-copy-id \
        -i "${KEY_PATH}.pub" \
        -o StrictHostKeyChecking=no \
        -o "ProxyJump=${ANSIBLE_USER}@${BRIDGE_HOST}" \
        "${ANSIBLE_USER}@${HOST}"

    if [ $? -eq 0 ]; then
        echo "  ✓ $HOST 완료"
    else
        echo "  ✗ $HOST 실패"
    fi
done

echo ""
echo "배포 완료. 연결 테스트 중..."
if [ ! -f ~/.vault_pass ]; then
    echo "WARNING: ~/.vault_pass 없음 — ansible ping 스킵. 수동으로 확인하세요."
    echo "  ansible all -m ping -i /opt/ansible/onprem-prod-repo/ansible/inventory/hosts.yml --vault-password-file ~/.vault_pass"
    exit 0
fi
ansible all -m ping \
    -i /opt/ansible/onprem-prod-repo/ansible/inventory/hosts.yml \
    --vault-password-file ~/.vault_pass
