import urllib.request, urllib.parse, json, http.cookiejar, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
data = urllib.parse.urlencode({'username':'admin','password':'admin123'}).encode()
opener.open('http://127.0.0.1:5001/login', data)
resp = opener.open('http://127.0.0.1:5001/api/ai/kpi4')
result = json.loads(resp.read())
for kpi in result:
    print(kpi['label'].encode('ascii','replace').decode(), '|', kpi['value'], '|', str(kpi['sub'])[:60].encode('ascii','replace').decode())
