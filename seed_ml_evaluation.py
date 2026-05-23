"""
Aurora ml_model_evaluation_daily 테이블 생성 + 시드.
app.py _aurora_pr_models() 쿼리: model_name, precision_score, recall_score, eval_date
"""
import pymysql
from datetime import date, timedelta

conn = pymysql.connect(
    host='auroracluster-db.cluster-cghecq7cbwln.ap-northeast-2.rds.amazonaws.com',
    user='admin', password='ChangeMe123!', database='lifesync360',
    cursorclass=pymysql.cursors.DictCursor, charset='utf8mb4'
)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS ml_model_evaluation_daily (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    model_name    VARCHAR(64) NOT NULL,
    precision_score FLOAT NOT NULL,
    recall_score  FLOAT NOT NULL,
    eval_date     DATE NOT NULL,
    INDEX idx_eval_date (eval_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")
conn.commit()
print("CREATE TABLE OK")

cur.execute("SELECT COUNT(*) AS cnt FROM ml_model_evaluation_daily")
existing = cur.fetchone()['cnt']
print(f"existing rows: {existing}")

if existing == 0:
    today = date.today()
    rows = []
    # 4개 모델 × 7일
    models = [
        ('VIP Predictor',       0.88, 0.84),
        ('Churn Predictor',     0.81, 0.79),
        ('Product Recommender', 0.76, 0.82),
        ('CLTV Estimator',      0.83, 0.77),
    ]
    import random
    random.seed(7)
    for day_offset in range(6, -1, -1):
        d = (today - timedelta(days=day_offset)).isoformat()
        for name, base_p, base_r in models:
            p = round(min(0.99, max(0.60, base_p + random.uniform(-0.03, 0.03))), 4)
            r = round(min(0.99, max(0.60, base_r + random.uniform(-0.03, 0.03))), 4)
            rows.append((name, p, r, d))

    cur.executemany(
        "INSERT INTO ml_model_evaluation_daily (model_name, precision_score, recall_score, eval_date) "
        "VALUES (%s, %s, %s, %s)",
        rows
    )
    conn.commit()
    print(f"inserted {len(rows)} rows")
else:
    print("skip, already seeded")

cur.execute("SELECT model_name, precision_score, recall_score, eval_date FROM ml_model_evaluation_daily ORDER BY eval_date DESC LIMIT 8")
for r in cur.fetchall():
    print(f"  {r['eval_date']} | {r['model_name']:25s} | P={r['precision_score']:.4f} R={r['recall_score']:.4f}")

cur.close()
conn.close()
print("done")
