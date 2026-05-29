from playwright.sync_api import sync_playwright
import os

BASE = 'http://localhost:5002'
OUT  = os.path.join(os.path.dirname(__file__), 'screenshots')
os.makedirs(OUT, exist_ok=True)

def shot(page, name, wait_ms=3000):
    page.wait_for_timeout(wait_ms)
    path = os.path.join(OUT, name)
    page.screenshot(path=path, full_page=True)
    print('saved:', name)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = browser.new_context(viewport={'width': 1440, 'height': 900})

    # 로그인
    page = ctx.new_page()
    page.goto(BASE + '/login', wait_until='load', timeout=20000)
    page.fill('input[name=username]', 'admin')
    page.fill('input[name=password]', 'admin123')
    page.click('button[type=submit]')
    page.wait_for_url(f'{BASE}/**', timeout=10000)

    # 전체현황 (대시보드)
    page.goto(BASE + '/', wait_until='load', timeout=20000)
    shot(page, '01_dashboard.png', 4000)

    # AI 추천
    page.goto(BASE + '/ai', wait_until='load', timeout=20000)
    shot(page, '02_ai.png', 4000)

    # Network/Ops
    page.goto(BASE + '/ops', wait_until='load', timeout=20000)
    shot(page, '03_ops.png', 3000)

    # Customer 360
    page.goto(BASE + '/users', wait_until='load', timeout=20000)
    shot(page, '04_users.png', 3000)

    page.close()
    browser.close()

print('done')
