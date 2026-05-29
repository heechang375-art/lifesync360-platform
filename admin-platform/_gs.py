import urllib.request, urllib.parse, json, http.cookiejar
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.open('http://127.0.0.1:5001/login', urllib.parse.urlencode({'username':'admin','password':'admin123'}).encode())
resp = opener.open('http://127.0.0.1:5001/api/cloud/status')
d = json.loads(resp.read())
gcp = d.get('gcp', [])
with open('C:/temp/gcp_status.json','w',encoding='utf-8') as f:
    json.dump(gcp, f, ensure_ascii=False, indent=2)
print('GCP entries:', len(gcp))
for g in gcp:
    print(g.get('service','?'), '|', g.get('state','?'), '|', str(g.get('note',''))[:60])
