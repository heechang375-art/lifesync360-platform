import os
import subprocess
import logging
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO
)

DEPLOY_TOKEN = os.environ['DEPLOY_TOKEN']
ANSIBLE_DIR  = os.environ.get('ANSIBLE_DIR',     '/opt/ansible/onprem-prod-repo/ansible')
VAULT_PASS   = os.environ.get('VAULT_PASS_FILE', '/home/ubuntu/.vault_pass')
DEPLOY_LOG   = os.environ.get('DEPLOY_LOG',      '/var/log/ansible-deploy.log')


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/deploy', methods=['POST'])
def deploy():
    if request.headers.get('X-Deploy-Token', '') != DEPLOY_TOKEN:
        logging.warning('배포 요청 거부 — 토큰 불일치')
        return jsonify({'error': '토큰 불일치'}), 401

    log_fd = open(DEPLOY_LOG, 'a')
    subprocess.Popen(
        ['ansible-playbook', 'site.yml',
         '-i', 'inventory/hosts.yml',
         f'--vault-password-file={VAULT_PASS}'],
        cwd=ANSIBLE_DIR,
        stdout=log_fd,
        stderr=log_fd,
    )
    logging.info('ansible-playbook 트리거됨')
    return jsonify({'status': 'triggered'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000)
