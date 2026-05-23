import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'C:\admin-platform\app.py'
c = open(path, encoding='utf-8').read()

OLD_MARKER = "result = _call_onprem('list_by_age_band') or {}"
if OLD_MARKER not in c:
    print('ALREADY PATCHED or marker not found')
    idx = c.find('def _ai_age_perf_2step()')
    print('func idx:', idx)
    print(c[idx:idx+120])
    sys.exit(0)

old = (
    "    try:\n"
    "        result = _call_onprem('list_by_age_band') or {}\n"
    "        age_groups = result.get('age_groups', {})\n"
    "        if age_groups and all(age_groups.get(b) for b in ['20s', '30s', '40s', '50s', '60s+']):\n"
    "            out = []\n"
    "            with get_db() as db, db.cursor() as cur:\n"
    "                for age_band in ['20s', '30s', '40s', '50s', '60s+']:\n"
    "                    gids = age_groups.get(age_band, [])\n"
    "                    if not gids:\n"
    "                        out.append({'age_band': age_band, 'recommended': 0,\n"
    "                                    'clicked': 0, 'purchased': 0, 'ctr': 0, 'cvr': 0})\n"
    "                        continue\n"
    "                    placeholders = ','.join(['%s'] * len(gids))\n"
    "                    cur.execute(\n"
    "                        f\"SELECT COUNT(*) AS recommended, \"\n"
    "                        f\"       SUM(clicked_flag IN ('Y','1')) AS clicked, \"\n"
    "                        f\"       SUM(purchased_flag IN ('Y','1')) AS purchased \"\n"
    "                        f\"FROM customer_recommend_history \"\n"
    "                        f\"WHERE global_id IN ({placeholders}) \"\n"
    "                        f\"  AND recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)\",\n"
    "                        tuple(gids)\n"
    "                    )\n"
    "                    row = cur.fetchone() or {}\n"
    "                    rec = int(row.get('recommended') or 0)\n"
    "                    clk = int(row.get('clicked') or 0)\n"
    "                    pur = int(row.get('purchased') or 0)\n"
    "                    out.append({\n"
    "                        'age_band': age_band, 'recommended': rec, 'clicked': clk, 'purchased': pur,\n"
    "                        'ctr': round(clk * 100.0 / rec, 1) if rec else 0,\n"
    "                        'cvr': round(pur * 100.0 / clk, 1) if clk else 0,\n"
    "                    })\n"
    "            return out\n"
    "    except Exception:\n"
    "        pass"
)

new = (
    "    try:\n"
    "        if not ONPREM_BASE_URL:\n"
    "            raise ValueError('ONPREM_BASE_URL not set')\n"
    "        age_groups = {}\n"
    "        after = ''\n"
    "        for _ in range(10):\n"
    "            qs = 'size=500' + (f'&after={after}' if after else '')\n"
    "            url = f'{ONPREM_BASE_URL.rstrip(\"/\")}/internal/profile/list-all?{qs}'\n"
    "            with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as resp:\n"
    "                data = _j.loads(resp.read())\n"
    "            for item in data.get('items', []):\n"
    "                gid = item.get('global_id')\n"
    "                ab  = item.get('age_band')\n"
    "                if gid and ab:\n"
    "                    age_groups.setdefault(ab, []).append(gid)\n"
    "            after = data.get('next_after', '')\n"
    "            if not after:\n"
    "                break\n"
    "        if not age_groups:\n"
    "            raise ValueError('no age_band data from on-prem')\n"
    "        out = []\n"
    "        with get_db() as db, db.cursor() as cur:\n"
    "            for age_band in ['20s', '30s', '40s', '50s', '60s+']:\n"
    "                gids = age_groups.get(age_band, [])\n"
    "                if not gids:\n"
    "                    out.append({'age_band': age_band, 'recommended': 0,\n"
    "                                'clicked': 0, 'purchased': 0, 'ctr': 0, 'cvr': 0})\n"
    "                    continue\n"
    "                placeholders = ','.join(['%s'] * len(gids))\n"
    "                cur.execute(\n"
    "                    f\"SELECT COUNT(*) AS recommended, \"\n"
    "                    f\"       SUM(clicked_flag IN ('Y','1')) AS clicked, \"\n"
    "                    f\"       SUM(purchased_flag IN ('Y','1')) AS purchased \"\n"
    "                    f\"FROM customer_recommend_history \"\n"
    "                    f\"WHERE global_id IN ({placeholders}) \"\n"
    "                    f\"  AND recommended_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)\",\n"
    "                    tuple(gids)\n"
    "                )\n"
    "                row = cur.fetchone() or {}\n"
    "                rec = int(row.get('recommended') or 0)\n"
    "                clk = int(row.get('clicked') or 0)\n"
    "                pur = int(row.get('purchased') or 0)\n"
    "                out.append({\n"
    "                    'age_band': age_band, 'recommended': rec, 'clicked': clk, 'purchased': pur,\n"
    "                    'ctr': round(clk * 100.0 / rec, 1) if rec else 0,\n"
    "                    'cvr': round(pur * 100.0 / clk, 1) if clk else 0,\n"
    "                })\n"
    "        return out\n"
    "    except Exception:\n"
    "        pass"
)

if old not in c:
    print('ERROR: old block not found exactly')
    sys.exit(1)

c2 = c.replace(old, new, 1)
open(path, 'w', encoding='utf-8').write(c2)
print('PATCH OK - verify:')
idx2 = c2.find('def _ai_age_perf_2step()')
print(c2[idx2:idx2+100])
