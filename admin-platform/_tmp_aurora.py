import pymysql, json
host = "auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com"
conn = pymysql.connect(host=host, user="admin", password="ChangeMe123!", connect_timeout=15, cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()
cur.execute("SHOW DATABASES")
dbs = [r["Database"] for r in cur.fetchall()]
print("DBs:", dbs)
skip = {"information_schema","mysql","performance_schema","sys"}
for db in dbs:
    if db in skip: continue
    cur.execute("USE " + db)
    cur.execute("SHOW TABLES")
    tables = [list(r.values())[0] for r in cur.fetchall()]
    print("DB:", db, "tables:", tables)
conn.close()