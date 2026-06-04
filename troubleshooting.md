# LifeSync360 트러블슈팅 (온프레미스 + 플랫폼)

증상별 즉시 해결 가이드. 온프레미스 인프라와 플랫폼/앱 이슈를 모두 다룹니다.

> **다른 트러블슈팅 위치**
> - 클라우드 CI/CD (CodeBuild·ECS·IAM): [`docs/cicd-troubleshooting-and-iac-tasks.md`](docs/cicd-troubleshooting-and-iac-tasks.md)
> - 앱 함수별 인라인 팁: [`docs/lifesync360-platform-app-guide.md`](docs/lifesync360-platform-app-guide.md) · [`docs/admin-platform-app-guide.md`](docs/admin-platform-app-guide.md)
> - admin 쿼리·스키마 정합 감사: [`admin-platform-query-audit-2026-05-23.md`](admin-platform-query-audit-2026-05-23.md)

---

## 증상: ansible all -m ping 전부 UNREACHABLE

```
Permission denied (publickey,password)
```

**원인**: 공개키를 터미널에서 수동 복붙할 때 개행/공백이 붙어 `authorized_keys` 키 손상.

**해결**:
```bash
# 키 파일로 직접 등록 (ls-vpngw에서)
ssh-copy-id -i ~/.ssh/lifesync360-onprem.pem.pub ansible@192.168.56.11
ssh-copy-id -i ~/.ssh/lifesync360-onprem.pem.pub ansible@192.168.56.12
ssh-copy-id -i ~/.ssh/lifesync360-onprem.pem.pub ansible@192.168.56.13

# 홈 디렉토리 권한 문제일 때 (각 VM에서)
chmod 755 /home/ansible
chmod 700 /home/ansible/.ssh
chmod 600 /home/ansible/.ssh/authorized_keys
```

---

## 증상: MySQL root 비밀번호 변경 태스크 실패

```
ERROR 1045 (28000): Access denied for user 'root'@'localhost'
```

**원인**: Ubuntu 24.04 MySQL 신규 설치 시 root에 비밀번호가 설정돼 있고, unix socket 인증도 차단됨.

**해결**: `/etc/mysql/debian.cnf`의 `debian-sys-maint` 계정으로 먼저 접속 후 root 비밀번호 변경.

```bash
# ls-db VM에서
sudo cat /etc/mysql/debian.cnf | grep password | head -1
# → password = xxxxxxxx  (이 값 사용)

mysql -u debian-sys-maint -p<위의_패스워드> \
  -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '<설정할_패스워드>'; FLUSH PRIVILEGES;"
```

Ansible task에 적용된 해결 코드 (`mysql/tasks/main.yml`):
```yaml
- name: Get debian-sys-maint password
  shell: awk '/^password/{print $3; exit}' /etc/mysql/debian.cnf
  register: debian_maint_password
  no_log: true

- name: Set MySQL root password
  shell: |
    mysql -u debian-sys-maint -p"{{ debian_maint_password.stdout }}" \
    -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '{{ mysql_root_password }}'; FLUSH PRIVILEGES;"
  no_log: true
```

---

## 증상: pip install 태스크 실패 (externally-managed-environment)

```
error: externally-managed-environment
This environment is externally managed
```

**원인**: Ubuntu 24.04 Python 3.12부터 PEP 668로 시스템 pip 직접 설치 차단.

**해결**: venv 생성 후 venv 경로로 설치. systemd ExecStart도 venv 경로로 변경.

```yaml
- name: Install python3-venv
  apt:
    name: python3-venv
    state: present

- name: Create virtualenv
  command: python3 -m venv /opt/tokenization/venv
  args:
    creates: /opt/tokenization/venv

- name: Install Python dependencies
  pip:
    name:
      - fastapi
      - uvicorn
    virtualenv: /opt/tokenization/venv
```

systemd 서비스 파일:
```
# 변경 전
ExecStart=/usr/local/bin/uvicorn token_service:app ...

# 변경 후
ExecStart=/opt/tokenization/venv/bin/uvicorn token_service:app ...
```

---

## 증상: curl http://192.168.56.13/health → 404

```
<html><body><h1>404 Not Found</h1></body></html>
```

포트 8000 직접 호출은 정상(`curl http://192.168.56.13:8000/health → {"status":"ok"}`).

**원인**: Ubuntu Nginx 기본 설치 시 `sites-enabled/default`가 80포트를 먼저 점유. `conf.d/private-api.conf`가 배포됐어도 `default`에 가로막혀 적용 안 됨.

**해결**:
```bash
# ls-api VM에서 즉시 해결
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl reload nginx
curl http://127.0.0.1/health
# → {"status":"ok"}
```

Ansible task에 영구 반영 (`private_api/tasks/main.yml`):
```yaml
- name: Remove default Nginx site
  file:
    path: /etc/nginx/sites-enabled/default
    state: absent
  notify: Reload nginx
```

---

## 증상: Ansible 재배포 시 MySQL 비밀번호 태스크 충돌

```
ERROR 1045: Access denied (재배포 시 구 패스워드로 접속 시도)
```

**원인**: 이미 비밀번호가 설정된 상태에서 Ansible이 재실행되면 `debian-sys-maint`로 다시 비밀번호 변경 시도.

**해결**: 비밀번호 설정 태스크에 `when` 조건 추가.

```yaml
- name: Set MySQL root password
  shell: ...
  when: mysql_password_changed is not defined
```

---

## 증상: ls-token 서비스 재배포 후 DB 자격증명 초기화

**원인**: Ansible이 systemd 서비스 파일을 덮어쓰면서 수동으로 설정했던 `DB_USER`, `DB_PASS` 환경변수 사라짐.

**해결**: `tokenization.service.j2`에 Ansible 변수로 환경변수 주입.

`tokenization.service.j2`:
```
Environment="DB_USER={{ mysql_app_user }}"
Environment="DB_PASS={{ mysql_app_password }}"
```

`inventory/hosts.yml`:
```yaml
ls-token:
  ansible_host: 192.168.56.12
  mysql_app_user: lifesync
  mysql_app_password: "{{ vault_mysql_app_password }}"
```

---

## 증상: trigger_ansible.sh 실행 시 호스트 변수 undefined

```
fatal: [ls-api]: FAILED! => {"msg": "The task includes an option with an undefined variable..."}
```

**원인**: `ansible-playbook` 명령에 `-i` 플래그 누락. 인벤토리 지정 없으면 호스트 변수 전부 undefined.

**해결**: `trigger_ansible.sh`에 `-i ansible/inventory/hosts.yml` 추가.

```bash
# 변경 전
ansible-playbook ansible/site.yml

# 변경 후
ansible-playbook ansible/site.yml -i ansible/inventory/hosts.yml --vault-password-file ~/.vault_pass
```

---

## 증상: Ansible 실행 시 ImportError: No module named 'six.moves'

```
ImportError: No module named 'six.moves'
TASK [Gathering Facts] FAILED
```

**원인**: Amazon Linux + Python 3.8 환경에서 특정 Ansible 버전이 `six` 패키지에 의존하는데, Python 3 환경에는 기본 포함이 안 된 경우.

**해결**:
```bash
# Control Node에서 six 설치
pip3 install six

# 또는 ansible_python_interpreter 명시 (hosts.yml)
# vars:
#   ansible_python_interpreter: /usr/bin/python3
# → 이미 설정돼 있으면 python3 경로에 six 설치

# Ubuntu 22.04 Control Node 사용 시 Ansible 버전 최신화 권장
sudo apt-get install -y ansible  # Ubuntu 레포 기본 버전
# 또는
pip3 install ansible --upgrade
```

**참고**: EC2 Control Node는 Ubuntu 22.04 기준으로 IaC가 작성됨. Amazon Linux 환경이면 위 방법으로 해결하되, 장기적으로 Ubuntu로 전환 고려.

---

## 증상: Deploy Server 기동 실패 — EnvironmentFile not found

```
systemctl status deploy-server
● deploy-server.service — LifeSync360 Deploy Server
   Active: failed
   ...
   deploy-server.service: Failed to load environment files: /etc/deploy-server/env: No such file or directory
```

**원인**: `deploy-server.service`가 `EnvironmentFile=/etc/deploy-server/env`를 참조하는데, 파일이 생성되지 않은 상태에서 서비스 시작 시도.

**해결**: Secrets Manager에서 토큰을 가져와 파일 생성 후 서비스 재시작.
```bash
# EC2 Control Node에서
sudo mkdir -p /etc/deploy-server

DEPLOY_TOKEN=$(aws secretsmanager get-secret-value \
  --secret-id lifesync/deploy-token \
  --region ap-northeast-2 \
  --query SecretString --output text \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo "DEPLOY_TOKEN=${DEPLOY_TOKEN}" | sudo tee /etc/deploy-server/env > /dev/null
sudo chmod 600 /etc/deploy-server/env

sudo systemctl daemon-reload
sudo systemctl start deploy-server
sudo systemctl status deploy-server
```

---

## 증상: LOAD DATA INFILE 실패 — Table doesn't exist

```
ERROR 1146 (42S02): Table 'lifesync_onprem.master_customer' doesn't exist
```

**원인**: 스키마 적용 전에 데이터 적재 시도.

**해결**: 스키마 먼저 적용 후 LOAD DATA 실행.

```bash
# 스키마 적용
mysql -u root -p lifesync_onprem < /mnt/downloads/onprem_schema.sql

# 이후 데이터 적재
mysql -u root -p lifesync_onprem
```

```sql
LOAD DATA INFILE '/var/lib/mysql-files/customer_master.csv' ...
```

---

## 증상: LOAD DATA INFILE 실패 — secure_file_priv 경로 오류

```
ERROR 1290: --secure-file-priv option
```

**원인**: MySQL `secure_file_priv` 기본값이 `/var/lib/mysql-files/`. 다른 경로 파일은 읽기 거부.

**해결**: 파일을 `/var/lib/mysql-files/`로 복사 후 실행.

```bash
sudo cp /mnt/downloads/customer_master.csv /var/lib/mysql-files/
sudo cp /mnt/downloads/customer_identity_map.csv /var/lib/mysql-files/
sudo cp /mnt/downloads/customer_profile.csv /var/lib/mysql-files/
```

---

## 증상: Ansible 배포 후 서비스 파일 환경변수 미치환

```
Environment=DEPLOY_TOKEN=배포 트리거 토큰 입력
```

서비스 재시작해도 토큰 값이 리터럴 텍스트로 남아 있음.

**원인**: Ansible이 `service.j2` 템플릿을 배포할 때 `{{ deploy_token }}` 변수가 치환되지 않은 채 저장됨. vars.yml 값은 로컬에서 정상이어도 EC2 Control Node의 레포가 `git pull`되지 않은 상태면 구버전 템플릿이 사용됨.

**확인**:
```bash
# ls-api VM에서
sudo cat /etc/systemd/system/private-api.service | grep DEPLOY_TOKEN
# 리터럴 텍스트가 보이면 미반영 상태
```

**해결**:
```bash
# EC2 Control Node에서
cd /opt/ansible/onprem-prod-repo
git pull

ansible-playbook ansible/site.yml \
  -i ansible/inventory/hosts.yml \
  --vault-password-file ~/.vault_pass \
  --limit ls-api

# ls-api에서 확인
sudo systemctl status private-api
```

---

## 증상: ansible ping UNREACHABLE — ls-db / ls-token (during banner)

```
UNREACHABLE! => {"msg": "Failed to connect to the host via ssh: ssh: connect to host 192.168.56.11 port 22: Connection timed out\nReceived disconnect from ... during banner exchange"}
```

ls-api(192.168.56.13)는 정상인데 ls-db / ls-token만 UNREACHABLE.

**원인**: EC2 Control Node에서 192.168.56.11 / 192.168.56.12는 직접 라우팅이 안 되고 ls-api를 경유해야 함. `hosts.yml`에 ProxyJump 설정 없으면 SSH가 직접 연결 시도하다 타임아웃.

**해결**: `hosts.yml`에 `ansible_ssh_common_args` 추가.

```yaml
mysql:
  hosts:
    ls-db:
      ansible_host: 192.168.56.11
      ansible_ssh_common_args: '-o StrictHostKeyChecking=no -o ProxyJump=ansible@172.16.1.73'
tokenization:
  hosts:
    ls-token:
      ansible_host: 192.168.56.12
      ansible_ssh_common_args: '-o StrictHostKeyChecking=no -o ProxyJump=ansible@172.16.1.73'
```

ProxyJump가 동작하려면 ls-api에 SSH 키가 먼저 배포돼 있어야 함 (setup-ssh-keys.sh 실행 순서 참고).

---

## 증상: PII 복호화 실패 (500 에러)

```
cryptography.fernet.InvalidToken
```

**원인**: `PII_AES_KEY` 환경변수가 서비스에 반영되지 않았거나, 마이그레이션에 사용한 키와 다른 키로 복호화 시도.

**확인**:
```bash
# ls-api에서
sudo systemctl status private-api
sudo journalctl -u private-api -n 30

# 환경변수 확인
sudo cat /etc/systemd/system/private-api.service | grep PII
```

**해결**:
```bash
# 서비스 재시작 (환경변수 반영)
sudo systemctl daemon-reload
sudo systemctl restart private-api
```

키가 다를 경우 → 마이그레이션 때 사용한 키로 `vault.yml` 수정 후 Ansible 재배포.

---

## 증상: 회원가입 후 JWT에 global_id가 NULL / 빈값

**발생 조건**: `USE_MOCK=false` 클라우드 연동 모드에서 회원가입 시.

**원인 1 — global_id 미생성**
`api_register`에서 `global_id`를 생성하는 코드가 없어 DB에 NULL로 저장됨.

**원인 2 — master_customer INSERT 누락**
`users` 테이블에만 INSERT하고 `master_customer`는 건너뜀. `master_customer.representative_name NOT NULL` 제약으로 온프레미스 스키마 무결성 위반.

**원인 3 — JWT gid 클레임 오입력**
`make_jwt(ls_user_id, global_id)` 호출 시 두 번째 인자에 `ls_user_id`를 넣어 `gid` 클레임이 틀린 값으로 발급됨.

**수정 내용** (`app.py` `api_register` 함수):
```python
ls_user_id = f"LS-{datetime.datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
global_id  = f"G-{uuid.uuid4().hex[:12].upper()}"

cur.execute('INSERT INTO master_customer (global_id, representative_name) VALUES (%s, %s)',
            (global_id, name))
cur.execute('INSERT INTO users (ls_user_id, global_id, email, name, password_hash) VALUES (%s, %s, %s, %s, %s)',
            (ls_user_id, global_id, email, name, generate_password_hash(password)))
db.commit()

token = make_jwt(ls_user_id, global_id)   # global_id 올바르게 전달
```

**확인 방법**:
```bash
# 회원가입 후 JWT 디코드 (base64로 payload 부분 확인)
TOKEN="eyJ..."
echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | python3 -m json.tool
# → "gid" 값이 "G-XXXX..." 형태여야 함 (ls_user_id 형태 LS-YYYYMMDD-XXXX면 버그)

# DB 직접 확인 (ls-db VM)
mysql -u lifesync -p lifesync_onprem \
  -e "SELECT ls_user_id, global_id, name FROM users ORDER BY created_at DESC LIMIT 5;"

mysql -u lifesync -p lifesync_onprem \
  -e "SELECT global_id, representative_name FROM master_customer ORDER BY created_at DESC LIMIT 5;"
```

---

## 증상: 회원가입 시 온프레미스 users 테이블 없음 오류

```
Table 'lifesync_onprem.users' doesn't exist
```

**원인**: `onprem-prod-repo/ansible/roles/mysql/files/schema.sql` (실제 배포 파일)에 `users` 테이블이 없었음. `db/onprem_schema.sql`에는 있었지만 Ansible이 배포하는 파일은 별개.

**해결**: Ansible 배포 파일에 users 테이블 추가 후 재배포.
```bash
# EC2 Control Node에서
cd /opt/ansible/onprem-prod-repo
git pull

ansible-playbook ansible/site.yml \
  -i ansible/inventory/hosts.yml \
  --vault-password-file ~/.vault_pass \
  --limit ls-db

# ls-db에서 테이블 확인
mysql -u lifesync -p lifesync_onprem -e "SHOW TABLES;"
# users 테이블이 목록에 있어야 함
```

이미 배포된 DB에는 Ansible 재배포로 자동 추가됨 (`CREATE TABLE IF NOT EXISTS` 사용 중).

---

## 증상: IaC 재배포 후 VPN 터널 끊김

매일 9AM IaC 재배포로 AWS VPN Connection이 재생성되면 터널 IP가 바뀌어 StrongSwan 연결이 끊김.

**원인**: `/etc/ipsec.conf`의 `right=` 값이 구 터널 IP로 남아있어 AWS 측 응답이 없음.

**해결**: 로컬 PC에서 `scripts/update-vpn-tunnel.sh` 실행.

```bash
# 사전 조건: AWS CLI 설치 및 인증 완료 (aws configure)
cd /path/to/LS
bash scripts/update-vpn-tunnel.sh

# VPN Connection ID를 직접 지정하는 경우
VPN_CONNECTION_ID=vpn-xxxxxxxxx bash scripts/update-vpn-tunnel.sh
```

스크립트 동작:
1. `aws ec2 describe-vpn-connections`로 새 터널 IP 조회
2. ls-api SSH → `/etc/ipsec.conf` `right=` 업데이트
3. `/etc/ipsec.secrets` IP 업데이트
4. `sudo systemctl restart strongswan-starter`
5. `sudo ipsec status` 출력으로 ESTABLISHED 확인

**PSK 문제 (IaC 팀 고정 전)**: IaC 재배포 시 PSK도 바뀌는 경우 스크립트가 ls-api 기존 ipsec.secrets에서 PSK를 읽지만 이미 무효화된 값임. 이 경우:
```bash
# CF 설정 파일 다운로드(AWS 콘솔 → VPN Connection → Download Config)에서 PSK 확인 후
# ls-api에서 직접 수정
sudo nano /etc/ipsec.secrets
# <leftid> <새터널IP> : PSK "<새PSK값>"
sudo systemctl restart strongswan-starter
```

**근본 해결**: IaC팀이 CF에서 `PreSharedKey`를 Secrets Manager 고정값으로 지정하면 PSK는 불변 → 스크립트만으로 완전 자동화.

---

## 증상: `git checkout` 으로 미커밋 working tree 변경분 손실 (CSS 정리 사고 — 2026-05-18)

```
직전 라운드에 admin.css 에 다크테마 80여 줄 추가 (working tree only, 미커밋)
→ CSS 정리 스크립트 사고로 git checkout 실행
→ 다크테마 80여 줄 통째 손실
```

**원인**:
- CSS 자동 정리 스크립트가 동적 prefix 미보호로 `.grade-vip/gold/silver/basic/care` (JS `grade-${grade}` 생성) 등 살아있는 클래스를 unused 판정 → 삭제
- 복구하려고 `git checkout admin-platform/static/css/admin.css` 실행 → HEAD 의 169줄로 강제 복원되면서 working tree 의 265줄 (다크테마 포함) 손실
- `git fsck --lost-found` dangling blob 104건 중 다크테마 포함 0건 (working tree 만 변경된 파일은 git 객체로 저장 안 됨)
- PyCharm LocalHistory 도 4월 2일 마지막 (사고 시점보다 이전)

**복구 — claude conversation jsonl 활용**:

```bash
# 1. 이번 프로젝트 jsonl 탐색
ls ~/.claude/projects/C--Users-campus3S026-ls/*.jsonl

# 2. dark-theme 패턴 포함 메시지 위치 찾기
python3 -c "
import json
fp = '~/.claude/projects/C--Users-campus3S026-ls/bf8516c4-...jsonl'
for i, line in enumerate(open(fp, encoding='utf-8')):
    obj = json.loads(line)
    msg = obj.get('message', {})
    for c in msg.get('content', []):
        if c.get('type') == 'tool_use' and c.get('name') == 'Edit':
            inp = c.get('input', {})
            if 'admin.css' in inp.get('file_path', '') and 'dark-theme' in inp.get('new_string', ''):
                # NEW string 통째 추출
                open('/tmp/admin_css_dark_block.txt', 'w', encoding='utf-8').write(inp['new_string'])
                print(f'line {i}: {len(inp[\"new_string\"])} bytes 복원')
"
# → line 8735: 4438 bytes (98줄) 통째 추출

# 3. 현재 admin.css 끝에 OLD 매칭 위치 찾아서 NEW 로 교체
python3 -c "
new = open('/tmp/admin_css_dark_block.txt', encoding='utf-8').read()
fp = 'admin-platform/static/css/admin.css'
css = open(fp, encoding='utf-8').read().replace('\r\n', '\n')
old = '.btn-full { width: 100%; ... }\n.error-msg { ... }'   # 실제 OLD 첫줄들
pos = css.find(old)
open(fp, 'w', encoding='utf-8', newline='').write(css[:pos] + new)
"
```

**재발 방지**:
- working tree 손실 위험 있는 `git checkout`/`git restore --source=HEAD`/`git reset --hard` 전 반드시 `git status` 로 미커밋 변경 확인
- 라운드 마다 work-in-progress 라도 `git stash` 또는 임시 commit (`wip:` prefix) 해두기
- jsonl 의 `tool_use` 호출 (특히 `Edit`/`Write` 의 `new_string` 필드) 이 작업 복구의 마지막 기록일 수 있음

**CSS 정리 스크립트 보강 — 동적 prefix 강제 보호**:
```python
DYN_PREFIXES = (
    'grade-', 'rank-', 'sc-', 'status-', 'tab-', 'rec-',
    'badge-', 'fill-', 'ladder-', 'view-rank-',
)
for c in classes_defined:
    if c.startswith(DYN_PREFIXES): continue   # 동적 생성 클래스는 unused 후보에서 제외
    if not re.search(r'\b' + re.escape(c) + r'\b', all_text):
        unused.add(c)
```

---

## 증상: Edge headless 캡처 — 인증/다크모드 페이지 안 잡힘 (2026-05-18)

```
Flask app (platform :5000, admin :5001) USE_MOCK=true 기동 후
Edge headless 로 / (홈), /dashboard, 다크모드 캡처 시도 → light 만 잡히거나
인증 페이지로 redirect 되어 캡처 실패
```

**원인 / 해결 — 3가지 패턴**:

### A. 인증 필요 페이지 (platform 홈/settings — JS localStorage 토큰 체크)

JS 가 `localStorage.getItem('ls_token')` 없으면 `/login` 으로 즉시 redirect.

**해결 — `static/_seed.html` 임시 작성 후 같은 origin 으로 진입**:
```html
<!-- lifesync360-platform/static/_seed.html (임시, 캡처 후 삭제) -->
<script>
fetch('/api/register', {method:'POST'}).then(r=>r.json()).then(d=>{
  localStorage.setItem('ls_token', d.token);
  location.replace(new URLSearchParams(location.search).get('to') || '/');
});
</script>
```
```bash
"$EDGE" --headless=new --window-size=480,800 --virtual-time-budget=10000 \
  --screenshot=home.png "http://127.0.0.1:5000/static/_seed.html?to=/"
# virtual-time-budget=10000 으로 fetch + redirect + 추가 fetch 다 기다림
```

### B. 인증 필요 페이지 (admin — Flask session cookie)

SSR 페이지라 fetch 안 쓰고 cookie 기반 인증. file:// origin 으로 캡처해야 토큰/세션 우회 가능.

**해결 — curl cookie + `<base href>` 삽입 + file:// 캡처**:
```bash
# 1. cookie jar 생성
curl -s -c /tmp/admin_cookie.txt -X POST \
  -d "username=admin&password=admin1234" \
  http://127.0.0.1:5001/login -o /dev/null

# 2. SSR HTML 받아서 base href 삽입 (상대경로 → http://127.0.0.1:5001/ 으로 resolve)
curl -s -b /tmp/admin_cookie.txt http://127.0.0.1:5001/dashboard | \
  python3 -c "import sys; t=sys.stdin.read(); print(t.replace('<head>','<head><base href=\"http://127.0.0.1:5001/\">'))" \
  > /tmp/admin_dashboard.html

# 3. file:// 로 캡처 (Windows 경로 형식 주의: file:///C:/...)
"$EDGE" --headless=new --window-size=1440,900 --virtual-time-budget=3000 \
  --screenshot=admin.png "file:///C:/Users/.../admin_dashboard.html"
```

> ⚠️ Windows 에서 file:// 경로는 `file:///C:/...` 대문자 드라이브 형식. bash `/c/Users/...` 직접 전달하면 Edge 가 못 받음.

### C. 다크모드 캡처가 라이트로 보임

`base.html` body 끝 toggle script 가 file:// origin 의 빈 localStorage 보고 `apply('light')` 호출 → 서버가 SSR cookie 로 붙여둔 `body.dark-theme` 클래스를 제거함.

**해결 — toggle script 통째 제거 + admin.css inline embed**:
```python
import re
html = open('admin_dashboard_dark.html', encoding='utf-8').read()
css  = open('admin-platform/static/css/admin.css', encoding='utf-8').read()
# <link rel="stylesheet"> 통째로 <style> 로 교체 (file:// origin 자원 로드 의존성 제거)
html = re.sub(r'<link rel="stylesheet"[^>]*admin\.css[^>]*>', f'<style>{css}</style>', html)
# 토글 script 통째 제거 (localStorage 빈 값 → light 강제 적용 방지)
html = re.sub(r'<script>\s*//\s*테마 토글.*?</script>', '', html, flags=re.DOTALL)
open('admin_dashboard_dark_inline.html', 'w', encoding='utf-8').write(html)
```
```bash
"$EDGE" --headless=new --window-size=1440,900 --virtual-time-budget=3000 \
  --user-data-dir=/tmp/edge_dark \
  --screenshot=dark.png "file:///C:/.../admin_dashboard_dark_inline.html"
```

**추가 주의사항**:
- 병렬로 Edge headless 동시 실행 시 같은 user-data-dir 충돌 가능 → 각 호출마다 `--user-data-dir` 분리
- 캡처 안 됐는데 동일 사이즈/md5 결과 나오면 caching 의심 → `--user-data-dir=/tmp/edge_$$` 같이 매번 새 dir
- 검증 완료 후 `static/_seed.html`, `/tmp/admin_*.html`, `/tmp/edge_*/` 등 임시 파일 정리


## 증상: Jinja2 `dict.items` 메서드 충돌 — `TypeError: 'builtin_function_or_method' object is not iterable` (2026-05-18)

admin `/ai` `/ops` 페이지 렌더 시 500 + Flask traceback:
```
File "templates/ai.html", line 186, in block 'content'
TypeError: 'builtin_function_or_method' object is not iterable
```

**원인**

Jinja2 attribute resolution은 `obj.attr` 표현에서 `getattr(obj, attr)` 우선 → `getitem(obj, attr)` fallback. mockup dict 의 키 이름이 `items` 면 dict 의 `.items()` 메서드(callable)가 잡혀서 for 루프에서 iterable 아님:

```python
MOCKUP_AI_INSIGHT = { 'items': [...] }     # ← 키 이름이 'items'
```
```jinja2
{% for it in insight.items %}              # ← dict.items() 메서드가 잡힘
```

**해결**

mockup dict 의 키 이름 자체를 변경 (`items` → `rows` 또는 `lines`) + 템플릿 동시 수정:

| 파일 | 변경 |
|---|---|
| `mockup_data.py` `MOCKUP_AI_INSIGHT` | `'items'` → `'rows'` |
| `mockup_data.py` `MOCKUP_NET_*` (VPC 6 카드) | `'items'` → `'rows'` |
| `mockup_data.py` `MOCKUP_NET_TOPOLOGY.aws[i]/gcp/onprem` | `'items'` → `'lines'` |
| `templates/ai.html` | `insight.items` → `insight.rows` |
| `templates/ops.html` | `c.items` → `c.rows`, `a.items` → `a.lines`, `topology.gcp.items` → `topology.gcp.lines` |

**재발 방지**

- mockup/context dict 에 **`items` / `keys` / `values` / `update` / `pop` / `get` / `copy` 등 dict 메서드명을 key 로 쓰지 말 것** (Jinja에서 호출 시 메서드 우선)
- 명시 접근 `dict['items']` 도 가능: `{% for it in insight['items'] %}` — 다만 일관성 위해 키 이름 변경 권장
- 충돌 가능 키 확인:
  ```bash
  python -c "print([m for m in dir({}) if not m.startswith('_')])"
  # ['clear','copy','fromkeys','get','items','keys','pop','popitem','setdefault','update','values']
  ```


## 증상: PrivateAPI `pymysql.connect()` 매 요청 새 connection — handler 시간의 50~70% (2026-05-18)

PrivateAPI 단순 GET 응답이 13~50ms — 분해해보면 connect setup 이 8~25ms 차지.

**원인**

`get_db()` 가 매 요청 새 connection 생성 → TCP handshake + MySQL auth 4-way (greeting/handshake/auth/OK). LAN 환경(192.168.56.x)이라 빠른 편이지만 매 요청 누적 부담.

```python
def get_db():
    return pymysql.connect(host=..., user=..., password=..., database=DB_NAME, cursorclass=DictCursor)
```

**해결 — DBUtils PooledDB 도입** (`onprem-prod-repo/ansible/roles/private_api/`)

```python
from dbutils.pooled_db import PooledDB

_db_pool = PooledDB(
    creator        = pymysql,
    mincached      = int(os.environ.get('DB_POOL_MIN', '2')),
    maxcached      = int(os.environ.get('DB_POOL_MAXIDLE', '5')),
    maxconnections = int(os.environ.get('DB_POOL_MAX', '10')),
    blocking       = True,        # 고갈 시 drop 대신 대기
    ping           = 1,           # 매 checkout 시 SELECT 1 (stale 방지)
    host           = os.environ['DB_HOST'],
    user           = os.environ['DB_USER'],
    password       = os.environ['DB_PASS'],
    database       = DB_NAME,
    cursorclass    = pymysql.cursors.DictCursor,
    charset        = 'utf8mb4',
    autocommit     = False,
)

def get_db():
    return _db_pool.connection()    # 기존 호출자 0줄 변경. db.close()는 pool 반환으로 동작
```

ansible role `Install Python dependencies` task 에 `DBUtils` pip 추가.

**효과**

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| `pymysql.connect()` setup | 8~25ms (매번 handshake) | 0.5ms (pool 재사용) |
| `ping=1` overhead | — | +0.5~1ms |
| 순 효과 | — | 7~24ms 단축 / 요청 (50~60% 단축) |

**운영 주의**

- `mincached=2` → systemd start 시 즉시 2 connection MySQL 에 붙음. `max_connections` (기본 151) 확인
- uvicorn workers > 1 이면 총 connection = workers × DB_POOL_MAX
- 트래픽 많아지면 `ping=1` 오버헤드 줄이려면 `ping=0` 으로 조정


## 증상: 로컬 캡처 시 `apply.html` 이 `/login` 으로 redirect — JWT 토큰 부재 (2026-05-18)

`file:///apply.html` 로 띄우면 `<script>` 가 `localStorage.getItem('ls_token')` 확인 → 빈 값이면 `window.location.href = '/login'`. 캡처가 로그인 페이지로 가버림.

**원인**

브라우저 직접 접근(http://localhost:5000)이면 localStorage 가 origin 단위 유지되어 token 있음. 캡처용으로 받은 HTML 을 file:// 로 띄우면 origin 이 `file:` 라 localStorage 비어있음.

**해결 — `<body>` 직후 token inline 주입**

```bash
TOKEN=$(curl -s -X POST -H "Content-Type: application/json" \
    -d '{"email":"test@lifesync.com","password":"password123"}' \
    http://127.0.0.1:5000/api/login | python -c "import json,sys; print(json.load(sys.stdin)['token'])")

curl -s "http://127.0.0.1:5000/product/DEP-001/apply" -o /tmp/platform_shots/apply_raw.html

python -c "
src = open(r'/tmp/platform_shots/apply_raw.html', encoding='utf-8').read()
src = src.replace('/static/css/style.css', 'http://127.0.0.1:5000/static/css/style.css')
src = src.replace('<body>', '<body><script>localStorage.setItem(\"ls_token\",\"$TOKEN\");</script>')
open(r'/tmp/platform_shots/apply.html','w',encoding='utf-8').write(src)
"
```

Edge headless 실행:
```bash
WIN_HTML=$(cygpath -w /tmp/platform_shots/apply.html)
WIN_HTML_SLASH=$(echo "$WIN_HTML" | tr '\\' '/')        # backslash → slash (sed 는 quoting 까다로움)
URL="file:///${WIN_HTML_SLASH}"
"$EDGE" --headless=new --window-size=560,1200 \
        --user-data-dir="$(cygpath -w /tmp/edge_apply)" \
        --screenshot="$WIN_PNG" "$URL"
```

→ `/api/me` fetch 는 file:// origin 이라 CORS 차단되어 "로딩 중..." 그대로지만 약관 동의 박스/CTA 등 SSR + JS 동작 부분은 정상 렌더. 폼 구조 검증에는 무관.

**재발 방지**

- 인증 필요 페이지 file:// 캡처 → token inline 주입 패턴 표준
- bash 에서 Windows 경로 변환은 `tr '\\' '/'` 권장 (sed 는 quoting 까다로움)
- 캐싱 충돌 방지 `--user-data-dir` 매번 새 dir


## 증상: Service-DB v3 슬림화 따른 코드 잔재 — INSERT 11컬럼 / SELECT 17컬럼 (2026-05-18)

`customer_product_application` v3 가 16 → 9 컬럼으로 슬림화 (`applicant_name/phone/email`, `apply_amount`, `contact_time`, `memo`, `agree_marketing` 7개 제거 + `status` ENUM 화). 운영 적용 시 platform INSERT / admin SELECT 가 제거된 컬럼 참조해서 500 발생 위험.

**해결 — 코드 동시 정합화**

| 파일 | 변경 |
|---|---|
| `lifesync360-platform/app.py` `api_product_apply` | INSERT 11컬럼 → **4컬럼** (`application_id, global_id, ls_user_id, product_id`). `_call_onprem('get_user')` 로 applicant 가져오는 14줄 블록 통째 제거. `data = request.get_json()` 도 제거 |
| `admin-platform/app.py` `/api/admin/applications` | SELECT 17컬럼 → **12컬럼** (제거된 7컬럼 빼고 `reviewer_id`/`reviewed_at` 추가) |
| `lifesync360-platform/app.py` `/api/my-applications` | `a.product_code` → `p.product_code` (v2 정규화로 product_master JOIN 컬럼) |
| `lifesync360-platform/templates/apply.html` | 마케팅 동의 체크박스(`row-mkt`) 행 + `cbMkt` JS 변수 + `payload.agree_marketing` 필드 제거 |

**검증 명령**

```bash
# customer_product_application 의 v3 제거 컬럼 잔재 확인 (기대: 0)
grep -n "a\.applicant_\|a\.apply_amount\|a\.contact_time\|a\.memo\|a\.agree_marketing" \
    admin-platform/app.py lifesync360-platform/app.py

# JS 폼 잔재
grep -n "agree_marketing\|cbMkt\|row-mkt" lifesync360-platform/templates/apply.html

# ast 통과
python -c "
import ast
for f in ['admin-platform/app.py','lifesync360-platform/app.py']:
    ast.parse(open(f, encoding='utf-8').read()); print('OK', f)
"
```

**재발 방지**

- DB 스키마 변경 시 `Service-DB/CHANGELOG.md` 확인 → 영향 받는 SQL 호출 grep → 코드 동시 수정
- 인라인 `CREATE TABLE IF NOT EXISTS` 같은 자동 복구 안전망은 단일 출처 원칙에 어긋남 — 운영은 Service-DB sql 만 신뢰


## 증상: 코드/Mockup 에 `ls-vpngw` / `lc-api` / `lc-db` / `lc-tokenz` 표기 잔재 (2026-05-18)

테스트 단계에서 들어간 `ls-vpngw` (VPN 게이트웨이 VM, 운영 미사용) 와 잘못된 `lc-*` 접두 표기가 PrivateAPI 코드 + Lambda docstring + admin mockup 에 흩어져 있음.

**원인**

- `ls-vpngw` 는 테스트용으로 운영 환경 미사용 (실제 VM 3종: `ls-db` / `ls-token` / `ls-api`)
- `lc-*` 는 표기 오기 (실제는 `ls-*`)
- 시연 mockup (MOCKUP_LOCAL_LAB / MOCKUP_DASH_CLOUD3 / MOCKUP_NET_TOPOLOGY) 에 반영되어 admin 화면에서 잘못된 호스트명 노출

**해결**

| 파일 | 변경 |
|---|---|
| `onprem-prod-repo/ansible/roles/private_api/files/app.py` | `VM_HOSTS` dict 에서 `'ls-vpngw'` 행 제거 → 3 VM (`ls-db`/`ls-token`/`ls-api`) |
| `lambda/onprem_customer_query/handler.py` | docstring 의 `vm_id in (ls-db, ls-token, ls-api, ls-vpngw)` → `(ls-db, ls-token, ls-api)` |
| `admin-platform/mockup_data.py` | (a) `MOCKUP_LOCAL_LAB` 의 ls-vpngw 행 제거 (4 환경으로) <br>(b) `MOCKUP_DASH_CLOUD3` On-Premises sub `'lc-db · lc-tokenz · lc-api'` → `'ls-db · ls-token · ls-api'` <br>(c) `MOCKUP_NET_TOPOLOGY.onprem` lines `'lc-db (MySQL) / lc-tokenz / lc-api (PrivateAPI)'` → `'ls-db (MySQL) / ls-token (Tokenization) / ls-api (PrivateAPI)'` |

**검증**

```bash
# 코드 잔재 grep (기대: 0)
grep -n "ls-vpngw\|lc-api\|lc-db\|lc-tokenz" \
    onprem-prod-repo/ansible/roles/private_api/files/app.py \
    lambda/onprem_customer_query/handler.py \
    admin-platform/mockup_data.py
```

**유의** — 과거 기록 문서 (`troubleshooting.md`, `project-progress.md`, `pii-encryption-guide.md`, `test-reference.md`, `lambda-to-onprem-network.md`, `local-test-remaining.md`) 에 남은 `ls-vpngw`/`lc-*` 표기는 **history 보존을 위해 그대로 둠** (이력 추적 가치).

**재발 방지**

- 새 VM/서비스 호스트명 추가 시 코드 + mockup + 문서 동시 갱신
- PrivateAPI 라우트 명세는 `docs/private-api.md` 단일 출처 (2026-05-18 신규)
- VM_HOSTS env override (`VM_LS_DB_HOST` 등 + `_PORT`) — 운영 IP 변경 시 코드 수정 없이 env 만 갱신


## 증상: USE_MOCK=true / false 응답 스키마 불일치 — 시연 검증 후 운영 전환 시 화면 깨질 위험 (2026-05-18 ③)

admin 라우트 3개에서 시연(USE_MOCK=true) 응답과 운영(USE_MOCK=false) 응답의 키/형태가 다름:

| API | 시연 응답 | 운영 응답 |
|---|---|---|
| `/api/dashboard/summary` | `{kpi_top: [...], kpi_mid: [...]}` | `{master_customer: {count}, users_active: {count}, users_consented: {count}}` |
| `/api/customer/profile/{gid}` | 평면 dict (`{ls_user_id, global_id, name, email, grade}`) | 중첩 (`{customer: {profile, identities, ...}, consents: [...]}`) |
| `/api/s3/status` | 5 카드 list | dict (`{raw_bucket_files, today_ingested, ...}`) |

→ 프론트가 `data.kpi_top` vs `data.master_customer.count` 분기. 시연에서 검증한 화면이 운영 전환 시 깨질 가능성.

**해결 — 백엔드가 양쪽 동일 구조 반환** (admin app.py)

```python
# /api/dashboard/summary — 양쪽 모두 9 카드 list
def _stub_aurora_summary():
    if USE_MOCK:
        return MOCKUP_DASH_KPI   # 9 카드 list
    cards = [dict(c) for c in MOCKUP_DASH_KPI]   # baseline deep copy
    # 운영 실 호출 결과로 value 만 덮어쓰기 (부분 실패 mockup fallback)
    try:
        mc = _call_onprem('count_master_customer').get('count')
        if mc is not None: cards[0]['value'] = f'{int(mc):,}'
    except Exception: pass
    # ... 9 카드 모두 실 호출 + fallback
    return cards


# /api/s3/status — 운영 dict → 5 카드 list 매핑 헬퍼
def _s3_status_cards():
    if USE_MOCK:
        return MOCKUP_DASH_S3_5
    raw = _ping_s3_ingestion() or {}
    cards = [dict(c) for c in MOCKUP_DASH_S3_5]
    cards[0]['value'] = f"{raw.get('raw_bucket_files', 0):,}"
    # ...
    return cards


# /api/customer/profile/{gid} — 시연 mockup 을 운영 구조로 재구성
def _profile_full_mock(global_id):
    user  = next((u for u in MOCK_USERS if u.get('global_id') == global_id), None) or {}
    score = MOCK_SCORES.get(global_id, {}) or {}
    return {
        'global_id': global_id,
        'customer': {
            'customer_status': 'ACTIVE',
            'vip_grade':       user.get('grade', 'BASIC'),
            'first_created_dt':'2023-01-15T10:00:00',
            'identities':      MOCK_IDENTITIES.get(global_id, []),
            'profile': {
                'lifesync_score': float(score.get('dynamic_score', 0) or 0),
                'health_score':   float(score.get('health_score', 0)   or 0),
                'finance_score':  float(score.get('fin_score', 0)      or 0),
                'asset_score':    75.0, 'risk_score': 12.0,
                'last_calc_dt':   score.get('update_time', ''),
            },
        },
        'consents': MOCK_CONSENTS.get(global_id, []),
    }
```

**검증** — USE_MOCK=true 라이브 호출로 3 API 응답 구조 확인:
```bash
curl -s -b cookie.txt http://127.0.0.1:5001/api/dashboard/summary | python -m json.tool | head -5
# [{"label": "통합 고객 수", "value": "1,000,000", "sub": ..., "accent": ..., "is_status": false}, ...]
```

**재발 방지**

- USE_MOCK 분기마다 같은 응답 스키마 보장 — 시연 mockup 을 운영 구조와 1:1 매핑하거나, 운영 응답을 시연 mockup 구조로 가공
- 신규 API 추가 시 시연/운영 두 분기 모두 동일 키 사용 검증
- 응답 스키마 변경 시 `docs/admin-api.md` 의 JSON 예시 + `docs/admin-data-flow.md` 의 read source 표 동시 갱신


## 증상: PrivateAPI `/internal/pii/{global_id}` 평문 5필드 반환 — admin 운영자도 RRN 포함 평문 PII 노출 (2026-05-18 ③)

PII 마스킹 처리 위치가 없어서 PrivateAPI 가 복호화 후 평문 그대로 응답:

```python
# onprem-prod-repo/.../app.py
@app.get('/internal/pii/{global_id}')
def get_pii(global_id: str):
    ...
    return {
        'global_id': global_id,
        'name':      decrypt_pii(row['customer_name_enc']),   # ← 평문 김철수
        'rrn':       decrypt_pii(row['rrn_enc']),             # ← 평문 주민번호
        'mobile':    decrypt_pii(row['mobile_enc']),
        'email':     decrypt_pii(row['email_enc']),
        'address':   decrypt_pii(row['address_enc']),
    }
```

운영 USE_MOCK=false 전환 시 admin → Lambda → PrivateAPI → admin 화면에 평문 5필드 그대로 전달. **주민번호 평문 노출은 보안 사고**.

**해결 옵션**

| 옵션 | 위치 | 평가 |
|---|---|---|
| A. PrivateAPI 단 마스킹 | `/internal/pii` 응답이 처음부터 마스킹된 값 + RRN 기본 제외 | ★★★ 최소 신뢰 영역 (운영자도 평문 못 받음) |
| B. admin app.py 단 마스킹 | admin 이 평문 받아서 마스킹 (warm pool 에 평문 잔존 가능) | ★★ |
| C. 평문 유지 (현재) | 운영 정책 위반 가능 | ✗ |

**권장 — A 옵션** (PrivateAPI 한 함수만 수정):
```python
def _mask_name(s):    return s[0] + '*' * (len(s)-1) if s else None
def _mask_phone(s):   return s[:3] + '-****-' + s[-4:] if s and len(s)>=10 else None
def _mask_email(s):   return s.split('@')[0][:2] + '***@' + s.split('@')[1] if s and '@' in s else None
def _mask_address(s): return ' '.join(s.split()[:2]) + ' ...' if s else None    # 시/도 + 시/군/구만

@app.get('/internal/pii/{global_id}')
def get_pii(global_id: str):
    ...
    return {
        'global_id': global_id,
        'name':      _mask_name(decrypt_pii(row['customer_name_enc'])),
        'rrn':       None,                                              # ← 기본 응답 X
        'mobile':    _mask_phone(decrypt_pii(row['mobile_enc'])),
        'email':     _mask_email(decrypt_pii(row['email_enc'])),
        'address':   _mask_address(decrypt_pii(row['address_enc'])),
    }
```

**RRN 별도 권한 엔드포인트** — `/internal/pii/{global_id}/rrn` (X-Internal-Token 인증 + audit log)

**재발 방지**

- PII 복호화는 가장 깊은 레이어 (PrivateAPI) 에서 즉시 마스킹
- 평문 PII 가 admin/Lambda warm pool 에 머무는 시간 최소화
- 운영 정책상 admin 운영자도 기본은 RRN 못 봄. 필요 시 별도 권한 + audit
- `docs/admin-data-flow.md` 의 "외부 공유 안전 영역" 5건 외에는 모두 권한 통제


## 증상: `count_users_consented` 설계서 SQL vs 운영 코드 정의 차이 — `users.consent_completed` sync 부재 (2026-05-18 ③)

설계서 V4 P1 row 5: `WHERE user_status='ACTIVE' AND consent_completed='Y'` (users 단일 컬럼)
PrivateAPI `/internal/count/users_consented` 구현: `users JOIN consent ... consent_flag='Y' AND revoke_dt IS NULL`

→ 결과 값이 다를 수 있음.

**원인 — `users.consent_completed` 가 모두 'N' 고정**

`auth_save_consent` Lambda 및 `auth_register` 가 consent 테이블만 UPSERT 하고 **`users.consent_completed` 컬럼 UPDATE 하지 않음**:
```python
# onprem-prod-repo/.../app.py auth_register
cur.execute(
    'INSERT INTO users (ls_user_id, global_id, login_email, password_hash, mobile) VALUES (...)',
    ...
)
# ← consent_completed 명시 X → DDL `NOT NULL DEFAULT 'N'` 적용
```

`auth_save_consent` 도 consent 테이블 UPSERT 만, users 안 건드림.

**결과**

| 옵션 | 현재 결과 | 의미 |
|---|---|---|
| 설계서 SQL (`consent_completed='Y'`) | **0** (모두 'N') | 무용지물 — sync 없음 |
| PrivateAPI 구현 (consent JOIN) | 정상 (예: 60K) | 실제 동의 분석대상 |

**해결 — B 옵션 유지 (consent JOIN)** ⭐ 사용자 결정

PrivateAPI 구현이 진실 — `users.consent_completed` 컬럼은 사실상 죽은 컬럼. 설계서 SQL 만 갱신해서 운영 정의와 통일하면 됨.

**대안 (A 옵션 가려면)**

추후 결정 시:
1. `auth_save_consent` 끝에 `UPDATE users SET consent_completed='Y'/'N' WHERE global_id=?` 추가
2. 기존 회원 일괄 백필: `UPDATE users u SET consent_completed='Y' WHERE EXISTS (SELECT 1 FROM consent c WHERE c.global_id=u.global_id AND c.consent_flag='Y' AND c.revoke_dt IS NULL)`
3. `users(user_status, consent_completed)` 복합 인덱스 추가

**재발 방지**

- 컬럼 정의만 두고 sync 코드 없으면 default 값 고정 — `NOT NULL DEFAULT 'N'` 같은 컬럼은 작성 흐름 점검
- 설계서 SQL 과 운영 코드 SQL 이 다르면 어느 쪽이 진실인지 명확히 결정 (이번엔 코드 진실)
- `docs/admin-data-flow.md` "결정 사항" 표에 명시


## 증상: PrivateAPI `/internal/profile/list-all` MySQL JSON_ARRAYAGG 응답 — Python dict vs JSON 문자열 혼재 (2026-05-18 ③)

`consent/list-all` 신규 엔드포인트가 `JSON_ARRAYAGG(JSON_OBJECT(...))` 로 user 당 consents 묶음 반환:

```sql
SELECT u.global_id, u.ls_user_id, u.user_status,
       (SELECT JSON_ARRAYAGG(JSON_OBJECT(
            'domain', c.domain,
            'consent_flag', c.consent_flag,
            'consent_dt', c.consent_dt,
            'revoke_dt', c.revoke_dt))
        FROM consent c WHERE c.global_id = u.global_id) AS consents
FROM users u
WHERE u.user_status = 'ACTIVE'
ORDER BY u.global_id LIMIT %s OFFSET %s
```

**문제** — pymysql 이 `consents` 컬럼을 **JSON 문자열로 반환** (dict 변환 X). consent_snapshot_aggregator 가 받으면 string 그대로 S3 PutObject — admin 이 GetObject 후 `consents[0].domain` 접근 시 `string index out of range` 또는 `unhashable type` 에러.

**해결 — PrivateAPI 응답 시 dict 로 정규화**

```python
for r in rows:
    if isinstance(r.get('consents'), str):
        r['consents'] = json.loads(r['consents']) if r['consents'] else []
    elif r.get('consents') is None:
        r['consents'] = []
```

PrivateAPI app.py 의 `list_consent_all` 함수 마지막에 추가. Lambda / admin / S3 모두 dict 로 통일.

**재발 방지**

- pymysql + MySQL 8 JSON 컬럼은 driver/버전에 따라 dict 자동 변환 / 문자열 둘 다 가능 — 응답 직전에 명시적 `json.loads` 정규화
- 새 엔드포인트가 JSON 컬럼 반환 시 같은 패턴 적용

---

## Control Node / SSM 부트스트랩 (초기 구축, 2026-05-11)

### Ansible Control Node SSH 키 미생성

**증상**
- `/home/ansible/.ssh/id_rsa` 파일이 생성되지 않음
- 14c SSM Association이 공개키를 SSM Parameter Store에 올리지 못함

**원인 1 — 14b UserData 실행 순서 버그**
- 원래 순서: `git clone` → `SSH 키 생성`
- `set -euo pipefail` 상태에서 git clone 실패 시 `exit 1` → SSH 키 생성 코드 미실행
- 수정: SSH 키 생성 블록을 git clone **앞으로** 이동

**원인 2 — sudo env_reset으로 인한 git PATH 문제**
- UserData에서 `sudo -u ansible git clone ...` 실행 시 sudo가 PATH 초기화
- git이 `/usr/bin/git`에 설치돼 있어도 초기화된 PATH에서 못 찾아 `env: 'git': No such file or directory` 발생
- 수정: `sudo -u ansible git` → `sudo -u ansible /usr/bin/git` 전체 경로 지정

**원인 3 — 14c에서 STS 엔드포인트 필요**
- `aws sts get-caller-identity` 호출이 퍼블릭 STS 엔드포인트로 나가 VPC Endpoint 없이 실패 가능
- 수정: 해당 사전 체크 제거 (ssm:PutParameter 자체가 IAM 없으면 어차피 실패)

**확인 방법**
```bash
# SSM 세션 접속
aws ssm start-session --target <AnsibleControlInstanceId> --region ap-northeast-2

# UserData 로그 확인
sudo tail -100 /var/log/ansible-bootstrap.log

# 키 존재 여부
ls -la /home/ansible/.ssh/

# SSM에 공개키 올라갔는지
aws ssm get-parameter \
  --name /lifesync/dev/ansible/public-key \
  --region ap-northeast-2 \
  --query Parameter.Value --output text
```

**재배포 순서**
```
14a → 14b → 14b 출력(AnsibleControlInstanceId) 확인 → 14c
```

---

### SSM start-session 오류 모음

| 에러 | 원인 | 해결 |
|------|------|------|
| `Could not connect to endpoint URL: ssm.ap-northease-2...` | 리전명 오타 (`northease` → `northeast`) | `aws configure set region ap-northeast-2` |
| `403 Forbidden` | 로컬 IAM 자격증명에 `ssm:StartSession` 권한 없음 | IAM 정책에 ssm:StartSession 추가 또는 admin 프로파일 사용 |
| `Session Manager plugin not found` | Session Manager Plugin 미설치 | [SessionManagerPluginSetup.exe](https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe) 설치 후 터미널 재시작 |
