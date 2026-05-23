import urllib.request, urllib.parse, http.cookiejar, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')

base = 'http://127.0.0.1:5001'
jar = http.cookiejar.CookieJar()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None

opener2 = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect())
req = urllib.request.Request(base + '/login',
      data=urllib.parse.urlencode({'username':'admin','password':'admin123'}).encode(),
      method='POST')
req.add_header('Content-Type', 'application/x-www-form-urlencoded')
try:
    opener2.open(req, timeout=5)
except urllib.error.HTTPError:
    pass

opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def check(label, url, timeout=30):
    t0 = time.time()
    try:
        resp = opener.open(base + url, timeout=timeout)
        raw = resp.read()
        elapsed = time.time() - t0
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                print(f'[OK] {label} ({elapsed:.1f}s) items={len(data)}')
                for i, d in enumerate(data[:3]):
                    print(f'     [{i}] {str(d)[:100]}')
            elif isinstance(data, dict):
                print(f'[OK] {label} ({elapsed:.1f}s) keys={list(data.keys())[:6]}')
        except:
            print(f'[OK] {label} ({elapsed:.1f}s) html={len(raw)}bytes snippet={raw[:80]}')
    except Exception as e:
        elapsed = time.time() - t0
        print(f'[FAIL] {label} ({elapsed:.1f}s) {e}')

# kpi4
check('kpi4', '/api/ai/kpi4')

# trend chart
check('trend (html)', '/api/ai/chart/trend', timeout=15)

# age chart (slow - on-prem pagination)
check('age (html)', '/api/ai/chart/age', timeout=60)

# donut
check('donut (html)', '/api/ai/chart/donut', timeout=15)

# histogram
check('histogram (html)', '/api/ai/chart/histogram', timeout=15)

# summary
check('summary', '/api/ai/summary', timeout=15)
