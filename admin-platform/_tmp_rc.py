import pymysql
host = "auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com"
conn = pymysql.connect(host=host, user="admin", password="ChangeMe123!", database="lifesync360", connect_timeout=15, cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()
tables = ["customer_recommend_daily","customer_recommend_history","ml_model_evaluation_daily","master_customer","users","customer_dashboard_log"]
for t in tables:
    try:
        cur.execute("SELECT COUNT(*) AS n FROM " + t)
        print(t + ":", cur.fetchone()["n"])
    except Exception as e:
        print(t + ": ERR", e)
conn.close()