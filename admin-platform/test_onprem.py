import urllib.request, json, traceback

url = "http://172.16.1.73/internal/health/local-lab"
try:
    with urllib.request.urlopen(urllib.request.Request(url), timeout=8) as r:
        data = r.read()
        print("STATUS:", r.status)
        print("CONTENT_TYPE:", r.headers.get("Content-Type"))
        try:
            parsed = json.loads(data)
            print("JSON_OK:", list(parsed.keys()))
        except Exception as je:
            print("JSON_ERR:", je, "RAW:", data[:200])
except Exception as e:
    print("ERR:", traceback.format_exc())
