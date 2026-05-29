import pymysql, json
host = 'auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com'
conn = pymysql.connect(host=host, user='admin', password='ChangeMe123!',
                       database='lifesync360', connect_timeout=15, cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()

tables = ['base_product_pool','campaign_master','campaign_seed','category_master',
          'company_master','cross_sell_rule','customer_dashboard_log',
          'customer_product_application','customer_recommend_daily',
          'customer_recommend_history','ml_model_evaluation_daily','product_master',
          'product_option','product_option_template','product_variant',
          'recommend_rule']

for t in tables:
    cur.execute('SELECT COUNT(*) AS n FROM ' + t)
    n = cur.fetchone()['n']
    print(f'{t}: {n}')

conn.close()
