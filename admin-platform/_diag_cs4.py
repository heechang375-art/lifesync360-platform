import json, os, boto3, pymysql

OUT = []
def log(s): OUT.append(str(s))

d = json.loads(boto3.client('secretsmanager', region_name='ap-northeast-2')
    .get_secret_value(SecretId='/lifesync/dev/db/master')['SecretString'])

conn = pymysql.connect(host=d['host'], user=d['username'], password=d['password'],
    database=d['dbname'], charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor, connect_timeout=10)
cur = conn.cursor()

GID = 'G000106253'
ONPREM_LAMBDA = os.environ.get('ONPREM_QUERY_LAMBDA', 'lifesync-onprem-customer-query')
log(f'ONPREM_LAMBDA={ONPREM_LAMBDA}')

# 1) 실제 Lambda 호출 (app.py 동일 로직)
consent_domains = []
try:
    lam = boto3.client('lambda', region_name='ap-northeast-2')
    resp = lam.invoke(FunctionName=ONPREM_LAMBDA, InvocationType='RequestResponse',
                      Payload=json.dumps({'action':'get_consent','global_id':GID}))
    result = json.loads(resp['Payload'].read())
    log(f'lambda_status={result.get("statusCode")}')
    body = result.get('body','{}')
    consent = json.loads(body) if isinstance(body,str) else body
    log(f'consent_keys={list(consent.keys()) if consent else []}')
    ls_user_id = consent.get('ls_user_id','')
    log(f'ls_user_id={ls_user_id!r}')
    active = [c for c in (consent.get('consents') or [])
              if c.get('consent_flag')=='Y' or c.get('agreed')]
    log(f'active_count={len(active)}')
    for c in active:
        log(f'  consent_item_keys={list(c.keys())} domain={c.get("domain")} key={c.get("key")}')
    consent_domains = [c.get('domain') or c.get('key','') for c in active
                       if c.get('domain') or c.get('key')]
except Exception as e:
    import traceback
    log(f'lambda_error={e}')
    log(traceback.format_exc())

log(f'consent_domains={consent_domains}')

# 2) company_filter
if consent_domains:
    _cd_fmt = ','.join(['%s'] * len(consent_domains))
    _company_filter = (f'AND p.company_id IN '
                       f'(SELECT company_id FROM company_master WHERE company_code IN ({_cd_fmt}))')
    _cd_params = tuple(consent_domains)
else:
    _company_filter = ''
    _cd_params = ()

log(f'company_filter={_company_filter!r}')

# 3) cross-sell 쿼리
_CS_SQL = (
    'SELECT r.target_category, '
    '(SELECT p.product_name FROM product_master p '
    ' JOIN category_master c2 ON p.category_id = c2.category_id '
    ' WHERE c2.category_code = r.target_category AND p.active_flag = "Y" '
    f' {_company_filter}'
    ' ORDER BY p.priority_rank ASC LIMIT 1) AS product_name '
    'FROM cross_sell_rule r WHERE r.active_flag = "Y" '
    '  AND r.base_category IN ('
    '    SELECT cat.category_code FROM customer_recommend_history h '
    '    JOIN product_master p ON h.product_id = p.product_id '
    '    JOIN category_master cat ON p.category_id = cat.category_id '
    '    WHERE h.global_id = %s {flag_filter}'
    '  ) '
    'ORDER BY r.priority_rank ASC LIMIT 49'
)
try:
    cur.execute(_CS_SQL.format(flag_filter="AND h.purchased_flag IN ('Y','1')"), _cd_params+(GID,))
    rows = cur.fetchall()
    log(f'purchased rows={len(rows)} non_null={sum(1 for r in rows if r["product_name"])}')
    for r in rows:
        log(f'  target={r["target_category"]} null={r["product_name"] is None}')

    crosssell = [r for r in rows if r['product_name']]
    if not crosssell:
        cur.execute(_CS_SQL.format(flag_filter=''), _cd_params+(GID,))
        rows2 = cur.fetchall()
        log(f'fallback rows={len(rows2)} non_null={sum(1 for r in rows2 if r["product_name"])}')
        crosssell = [r for r in rows2 if r['product_name']]
    log(f'FINAL={len(crosssell)} items')
    for c in crosssell:
        log(f'  -> {c["target_category"]}')
except Exception as e:
    import traceback
    log(f'query_error={e}')
    log(traceback.format_exc())

conn.close()
with open('C:/admin-platform/_diag_cs4_out.txt','w',encoding='utf-8') as f:
    f.write('\n'.join(OUT))
print('DONE')
