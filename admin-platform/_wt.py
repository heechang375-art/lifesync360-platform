import pymysql, json
conn = pymysql.connect(host='auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com',
    user='admin', password='ChangeMe123!', database='lifesync360',
    connect_timeout=10, cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()
cur.execute('SHOW TABLES')
tables = [list(r.values())[0] for r in cur.fetchall()]
wearable = [t for t in tables if 'wear' in t.lower() or 'device' in t.lower() or 'health' in t.lower() or 'vital' in t.lower() or 'sensor' in t.lower() or 'iot' in t.lower()]
print('All tables:', tables)
print('Wearable-related:', wearable)
conn.close()
