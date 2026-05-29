"""
시드 스크립트 — 1회성 실행용
  1. DynamoDB analytics_segment_performance (오늘 날짜)
  2. DynamoDB analytics_demographic_information (오늘 날짜)
  3. Aurora ml_model_evaluation_daily
"""
import os, sys, json
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, 'C:/admin-platform')

os.environ['AURORA_HOST'] = 'auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com'
os.environ['DB_USER']     = 'admin'
os.environ['DB_PASS']     = 'ChangeMe123!'
os.environ['DB_NAME']     = 'lifesync360'
os.environ['AWS_DEFAULT_REGION'] = 'ap-northeast-2'

import boto3
import pymysql

TODAY = date.today().isoformat()
REGION = 'ap-northeast-2'

# ── 1. DynamoDB analytics_segment_performance ─────────────────────────────
def seed_segment_performance():
    ddb = boto3.resource('dynamodb', region_name=REGION)
    tbl = ddb.Table('analytics_segment_performance')

    segments = [
        # gender
        ('gender#M',      'M',      12034, 2166,  649),
        ('gender#F',      'F',      12017, 2283,  685),
        # age_band
        ('age_band#20s',  '20s',     4851,  921,  256),
        ('age_band#30s',  '30s',     6214, 1118,  367),
        ('age_band#40s',  '40s',     5503,  990,  317),
        ('age_band#50s',  '50s',     4187,  711,  213),
        ('age_band#60s+', '60s+',    3296,  528,  181),
        # region
        ('region#Seoul',    'Seoul',    7242, 1376,  434),
        ('region#Gyeonggi', 'Gyeonggi', 5481,  986,  296),
        ('region#Busan',    'Busan',    3197,  575,  172),
        ('region#Incheon',  'Incheon',  2803,  476,  141),
        ('region#Other',    'Other',    5328, 1036,  321),
        # income
        ('income#H',  'H',  7218, 1515,  505),
        ('income#M',  'M',  9987, 1797,  539),
        ('income#L',  'L',  6846, 1095,  290),
        # asset
        ('asset#A',  'A',  5012, 1052,  351),
        ('asset#B',  'B',  8503, 1615,  468),
        ('asset#C',  'C', 10536, 1896,  515),
    ]

    with tbl.batch_writer() as bw:
        for sk, val, rec, clk, pur in segments:
            ctr = round(clk * 100.0 / rec, 2) if rec else 0
            cvr = round(pur * 100.0 / rec, 2) if rec else 0
            bw.put_item(Item={
                'snapshot_date': TODAY,
                'segment_key':   sk,
                'value':         val,
                'recommended':   rec,
                'clicked':       clk,
                'purchased':     pur,
                'ctr':           Decimal(str(ctr)),
                'cvr':           Decimal(str(cvr)),
            })

    print(f'[OK] segment_performance: {len(segments)} items / {TODAY}')


# ── 2. DynamoDB analytics_demographic_information ─────────────────────────
def seed_demographic_information():
    ddb = boto3.resource('dynamodb', region_name=REGION)
    tbl = ddb.Table('analytics_demographic_information')

    demographics = [
        # gender
        ('gender#M',  'M',  12034, 4821, 7213, Decimal('38.4'), Decimal('1.2')),
        ('gender#F',  'F',  12017, 5108, 6909, Decimal('41.2'), Decimal('1.8')),
        # age_band
        ('age_band#20s',  '20s',   4851, 2134, 2717, Decimal('24.3'), Decimal('0.8')),
        ('age_band#30s',  '30s',   6214, 2874, 3340, Decimal('31.7'), Decimal('1.5')),
        ('age_band#40s',  '40s',   5503, 2301, 3202, Decimal('44.1'), Decimal('2.1')),
        ('age_band#50s',  '50s',   4187, 1551, 2636, Decimal('54.8'), Decimal('2.6')),
        ('age_band#60s+', '60s+',  3296,  969, 2327, Decimal('63.4'), Decimal('2.9')),
        # income
        ('income#H',  'H',   7218, 3247, 3971, Decimal('51.3'), Decimal('3.5')),
        ('income#M',  'M',   9987, 4148, 5839, Decimal('42.2'), Decimal('2.3')),
        ('income#L',  'L',   6846, 2534, 4312, Decimal('34.8'), Decimal('0.9')),
        # asset
        ('asset#A',  'A',  5012, 2508, 2504, Decimal('58.4'), Decimal('4.1')),
        ('asset#B',  'B',  8503, 3701, 4802, Decimal('43.1'), Decimal('2.6')),
        ('asset#C',  'C', 10536, 3720, 6816, Decimal('33.7'), Decimal('1.1')),
    ]

    with tbl.batch_writer() as bw:
        for sk, val, total, active, inactive, avg_age, avg_asset in demographics:
            bw.put_item(Item={
                'snapshot_date':  TODAY,
                'demographic_key': sk,
                'value':          val,
                'total':          total,
                'active':         active,
                'inactive':       inactive,
                'avg_age':        avg_age,
                'avg_asset_score': avg_asset,
            })

    print(f'[OK] demographic_information: {len(demographics)} items / {TODAY}')


# ── 3. Aurora ml_model_evaluation_daily ───────────────────────────────────
def seed_ml_model_evaluation():
    conn = pymysql.connect(
        host=os.environ['AURORA_HOST'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASS'],
        database=os.environ['DB_NAME'],
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )
    cur = conn.cursor()

    eval_date = TODAY
    train_date = (date.today() - timedelta(days=3)).isoformat()

    models = [
        ('REC_NBA',    'v2.3.1', 0.8741, 0.8203, 0.7921, 0.9012, 0.8055, 24051),
        ('VIP_PRED',   'v1.8.2', 0.8512, 0.8456, 0.8134, 0.8876, 0.8292, 18734),
        ('CHURN_RISK', 'v3.1.0', 0.8124, 0.7891, 0.7634, 0.8543, 0.7760, 21203),
        ('CROSS_SELL', 'v1.2.4', 0.7923, 0.7712, 0.7498, 0.8312, 0.7602, 15892),
    ]

    cur.execute('DELETE FROM ml_model_evaluation_daily WHERE eval_date = %s', (eval_date,))

    sql = """
        INSERT INTO ml_model_evaluation_daily
            (eval_date, model_name, model_version, accuracy, precision_score, recall_score,
             auc, f1_score, sample_count, training_date, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'GCP_BIGQUERY')
    """
    for name, ver, acc, prec, rec, auc, f1, cnt in models:
        cur.execute(sql, (eval_date, name, ver, acc, prec, rec, auc, f1, cnt, train_date))

    conn.commit()
    conn.close()
    print(f'[OK] ml_model_evaluation_daily: {len(models)} rows / {eval_date}')


if __name__ == '__main__':
    seed_segment_performance()
    seed_demographic_information()
    seed_ml_model_evaluation()
    print('Done.')
