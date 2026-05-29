import urllib.request, urllib.parse, json, http.cookiejar
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
data = urllib.parse.urlencode({'username':'admin','password':'admin123'}).encode()
opener.open('http://127.0.0.1:5001/login', data)
resp = opener.open('http://127.0.0.1:5001/api/ai/kpi4')
result = json.loads(resp.read())
with open('C:/temp/kpi_result.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print('saved', len(result), 'kpis')
