import urllib.request, urllib.parse, json, http.cookiejar
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.open('http://127.0.0.1:5001/login', urllib.parse.urlencode({'username':'admin','password':'admin123'}).encode())
for kind in ['model_metrics', 'recommendation_mart']:
    try:
        resp = opener.open('http://127.0.0.1:5001/api/bigquery/analytics?kind=' + kind)
        rows = json.loads(resp.read())
        print(kind + ': ' + str(len(rows)) + ' rows')
        if rows:
            print('  sample:', str(rows[0])[:120])
    except Exception as e:
        print(kind + ': ERR ' + str(e))
