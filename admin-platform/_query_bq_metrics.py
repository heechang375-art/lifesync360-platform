import os, boto3, json, tempfile
os.environ['AWS_DEFAULT_REGION'] = 'ap-northeast-2'
sm = boto3.client('secretsmanager', region_name='ap-northeast-2')
r = sm.get_secret_value(SecretId='lifesync/gcp/service-account-key')
k = json.loads(r['SecretString'])
t = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
json.dump(k, t); t.close()
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = t.name
proj = k['project_id']

from google.cloud import bigquery
bq = bigquery.Client(project=proj)

for table in ['model_metrics']:
    sql = f'SELECT * FROM `{proj}.lifesync_ml.{table}` LIMIT 20'
    try:
        rows = list(bq.query(sql).result())
        if not rows:
            print(f'{table}: EMPTY')
        else:
            print(f'{table}: {len(rows)} rows')
            for row in rows[:5]:
                print(' ', {k: v for k, v in row.items()})
    except Exception as e:
        print(f'{table}: ERROR - {e}')
