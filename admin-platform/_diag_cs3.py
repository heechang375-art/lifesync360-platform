import json, os, boto3, pymysql

OUT = []
def log(s): OUT.append(str(s))

d = json.loads(boto3.client('secretsmanager', region_name='ap-northeast-2')
    .get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])
for src, dst in {'host':'AURORA_HOST','username':'DB_USER','password':'DB_PASS','dbname':'DB_NAME'}.items():
    os.environ[dst] = d[src]

conn = pymysql.connect(host=d['host'], user=d['username'], password=d['password'],
    database=d['dbname'], charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor, connect_timeout=10)
cur = conn.cursor()
GID = 'G000106253'

ONPREM_LAMBDA = os.environ.get('ONPREM_QUERY_LAMBDA', '')
log(f'ONPREM_LAMBDA={ONPREM_LAMBDA or "(not set)"}')

consent_domains = []
if ONPREM_LAMBDA:
    try:
        lam = boto3.client('lambda', region_name='ap-northeast-2')
        resp = lam.invoke(FunctionName=ONPREM_LAMBDA, InvocationType='RequestResponse',
                          Payload=json.dumps({'action':'get_consent','global_id':GID}))
        result = json.loads(resp['Payload'].read())
        log(f'consent_status={result.get("statusCode")}')
        body = result.get('body','{}')
        consent = json.loads(body) if isinstance(body,str) else body
        active = [c for c in (consent.get('consents') or [])
                  if c.get('consent_flag')=='Y' or c.get('agreed')]
        log(f'active_count={len(active)}')
        log(f'active_domains={[c.get("domain") or c.get("key") for c in active]}')
        consent_domains = [c.get('domain') or c.get('key','') for c in active
                           if c.get('domain') or c.get('key')]
    except Exception as e:
        log(f'consent_error={e}')
else:
    log('no lambda -> consent_domains empty')

log(f'consent_domains={consent_domains}')

if consent_domains:
    _cd_fmt = ','.join(['%s'] * len(consent_domains))
    _company_filter = (f'AND p.company_id IN '
                       f'(SELECT company_id FROM company_master WHERE company_code IN ({_cd_fmt}))')
    _cd_params = tuple(consent_domains)
else:
    _company_filter = ''
    _cd_params = ()

log(f'company_filter="{_company_filter}"')
log(f'cd_params={_cd_params}')

_CS_SQL = (
    'SELECT r.target_category, '
    '(SELECT p.product_name FROM product_master p '
    ' JOIN category_master c2 ON p.category_id = c2.category_id '
    ' WHERE c2.category_code = r.target_category AND p.active_flag = "Y" '
    f' {_company_filter}'
    ' ORDER BY p.priority_rank ASC LIMIT 1) AS product_name, '
    '(SELECT c3.category_name FROM category_master c3 WHERE c3.category_code = r.target_category LIMIT 1) AS category_name '
    'FROM cross_sell_rule r WHERE r.active_flag = "Y" '
    '  AND r.base_category IN ('
    '    SELECT cat.category_code FROM customer_recommend_history h '
    '    JOIN product_master p ON h.product_id = p.product_id '
    '    JOIN category_master cat ON p.category_id = cat.category_id '
    '    WHERE h.global_id = %s {flag_filter}'
    '  ) '
    'ORDER BY r.priority_rank ASC LIMIT 3'
)

try:
    sql_p = _CS_SQL.format(flag_filter="AND h.purchased_flag IN ('Y', '1')")
    cur.execute(sql_p, _cd_params + (GID,))
    rows_p = cur.fetchall()
    log(f'purchased_rows={len(rows_p)} non_null={len([r for r in rows_p if r["product_name"]])}')
    for r in rows_p:
        log(f'  p: target={r["target_category"]} name_null={r["product_name"] is None}')

    crosssell = [r for r in rows_p if r['product_name']]
    if not crosssell:
        sql_f = _CS_SQL.format(flag_filter='')
        cur.execute(sql_f, _cd_params + (GID,))
        rows_f = cur.fetchall()
        log(f'fallback_rows={len(rows_f)} non_null={len([r for r in rows_f if r["product_name"]])}')
        for r in rows_f:
            log(f'  f: target={r["target_category"]} name_null={r["product_name"] is None}')
        crosssell = [r for r in rows_f if r['product_name']]

    log(f'FINAL_crosssell_count={len(crosssell)}')
    for c in crosssell:
        log(f'  -> target={c["target_category"]}')
except Exception as e:
    import traceback
    log(f'ERROR={e}')
    log(traceback.format_exc())

conn.close()

with open('C:/admin-platform/_diag_cs3_out.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(OUT))
print('DONE')
