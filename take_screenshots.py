import sys, json, os, urllib.request
sys.path.insert(0, '/opt/ls360_venv/lib/python3.12/site-packages')

from playwright.sync_api import sync_playwright

BASE = 'http://localhost:5000'
OUT  = '/tmp/screenshots'
os.makedirs(OUT, exist_ok=True)

# Get JWT token
login_data = json.dumps({'email': 'user1@lifesync.com', 'password': 'Test1234!'}).encode()
req = urllib.request.Request(BASE + '/api/login', data=login_data,
                              headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req, timeout=15)
token = json.loads(resp.read()).get('token', '')
print('Token:', token[:20] + '...')

SET_TOKEN_JS = f"localStorage.setItem('ls_token', '{token}')"

def open_page_with_token(ctx, url, filename, wait_ms=3000):
    page = ctx.new_page()
    # Navigate to base first so localStorage is accessible
    page.goto(BASE + '/login', wait_until='load', timeout=30000)
    page.evaluate(SET_TOKEN_JS)
    page.goto(url, wait_until='load', timeout=30000)
    page.wait_for_timeout(wait_ms)
    page.screenshot(path=os.path.join(OUT, filename), full_page=True)
    print(f'Saved: {filename}')
    page.close()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = browser.new_context(viewport={'width': 1400, 'height': 900})

    # 1. Login page (no token needed)
    page = ctx.new_page()
    page.goto(BASE + '/login', wait_until='load', timeout=30000)
    page.wait_for_timeout(1000)
    page.screenshot(path=os.path.join(OUT, 'ls360_01_login.png'), full_page=True)
    print('Saved: ls360_01_login.png')
    page.close()

    # 2. Home / recommendations
    open_page_with_token(ctx, BASE + '/', 'ls360_02_home.png', wait_ms=4000)

    # 3. Consent page
    open_page_with_token(ctx, BASE + '/consent', 'ls360_03_consent.png')

    # 4. Settings page
    open_page_with_token(ctx, BASE + '/settings', 'ls360_04_settings.png')

    # 5. My applications
    open_page_with_token(ctx, BASE + '/api/my-applications', 'ls360_05_myapps_api.png')

    browser.close()

import subprocess
result = subprocess.run(
    ['aws', 's3', 'cp', OUT, 's3://lifesync-732-raw/screenshots/ls360/',
     '--recursive', '--region', 'ap-northeast-2'],
    capture_output=True, text=True
)
print(result.stdout)
if result.returncode != 0:
    print('S3 error:', result.stderr)
else:
    print('All screenshots uploaded')
