# -*- coding: utf-8 -*-
import os, datetime
os.environ.setdefault('JWT_SECRET','test-secret-lifesync-mock-32bytes!!')
os.environ.setdefault('AWS_REGION','ap-northeast-2')
os.environ.setdefault('ONPREM_QUERY_LAMBDA','')
os.environ.setdefault('DB_USER','mock'); os.environ.setdefault('DB_PASS','mock')
import app
import unittest.mock as M

DOMAINS=['BANK','CARD','INS','SEC','ONINS','HLT','HOS','WBL']
CONSENTS_Y=[{'consent_flag':'Y','revoke_dt':None,'domain':d} for d in DOMAINS]

app._call_onprem=lambda action,**kw:{
 'login':{'ls_user_id':'USER-001','global_id':'GLOBAL-001'},
 'get_user':{'ls_user_id':'USER-001','global_id':'GLOBAL-001','login_email':'choi@lifesync.com'},
 'get_all':{'consents':CONSENTS_Y,'customer':{'profile':{'phone':'01012345678'}}},
 'get_pii':{'name':'최하솔'},
 'get_consent':{'consents':CONSENTS_Y},
 'save_consent':{'status':'ok'},
 'get_user_by_global':{'ls_user_id':'USER-001'},
}.get(action,{})

app._ddb_get_latest=lambda gid:{'global_id':gid,'dynamic_grade':'SILVER','dynamic_score':'79','health_score':'72','vip_prob':'0.4','next_best_action':'CROSS_SELL','update_time':'2026-05-26T10:00:00'}
app._fetch_ddb_meta=lambda gid:('SILVER',79.0,72.0,0.4,'CROSS_SELL',True)
app._get_consents_with_fallback=lambda gid,has:(list(DOMAINS),'cache')
app._match_rules=lambda *a,**k:(['SAVINGS','WELLNESS'],{})

def P(pid,code,name,comp_c,comp,cat_c,cat,score,rank,tg):
    return {'product_id':pid,'product_code':code,'product_name':name,'description':name+' 상품',
            'target_grade':tg,'risk_level':'적금' if cat=='적금' else '맞춤추천','priority_rank':10,
            'company_code':comp_c,'company_name':comp,'category_code':cat_c,'category_name':cat,
            'reason':'SILVER 등급 · VIP 후보','rec_rank':rank,'recommendation_score':score}
PRODUCTS=[
 P(1,'EDU-VIP','자녀 교육 적금 VIP 전용','BANK','LS 은행','SAVINGS','적금',38,1,'VIP'),
 P(2,'WGT-VIP','체중 감량 챌린지 VIP 전용','HLT','LS 헬스케어','WELLNESS','건강관리/웰니스',38,2,'VIP'),
 P(3,'EDU-AI','자녀 교육 적금 AI 추천형','BANK','LS 은행','SAVINGS','적금',37,3,'VIP'),
 P(4,'WGT-AI','체중 감량 챌린지 AI 추천형','HLT','LS 헬스케어','WELLNESS','건강관리/웰니스',37,4,'VIP'),
]
app._fetch_products=lambda *a,**k:[dict(p) for p in PRODUCTS]

app.get_redis=lambda:M.Mock(get=M.Mock(return_value=None),setex=M.Mock(),delete=M.Mock())

PROD_DETAIL={'product_id':1,'product_code':'EDU-VIP','product_name':'자녀 교육 적금 VIP 전용',
 'description':'자녀 교육비 마련을 위한 VIP 전용 고금리 적금. AI 추천 매칭.',
 'target_grade':'VIP','risk_level':'적금','company_code':'BANK','company_name':'LS 은행',
 'category_code':'SAVINGS','category_name':'적금','company_id':1,'category_id':1}
PROD_OPTS=[{'option_name':'interest_rate','option_value':'3.5 PERCENT'},
 {'option_name':'term_month','option_value':'36'},
 {'option_name':'monthly_premium','option_value':'300000 KRW'}]
MY_APPS=[
 {'application_id':'APP-20260526120530-001','product_code':'EDU-VIP','product_name':'자녀 교육 적금 VIP 전용','company_name':'LS 은행','category_name':'적금','status':'RECEIVED','created_at':'2026-05-26 12:05:30'},
 {'application_id':'APP-20260526110000-001','product_code':'WGT-VIP','product_name':'체중 감량 챌린지 VIP 전용','company_name':'LS 헬스케어','category_name':'건강관리/웰니스','status':'IN_REVIEW','created_at':'2026-05-26 11:00:00'},
 {'application_id':'APP-20260525150000-001','product_code':'PB-001','product_name':'PB 자산관리','company_name':'LS 증권','category_name':'투자','status':'APPROVED','created_at':'2026-05-25 15:00:00'},
]
def mk_db():
    cur=M.MagicMock()
    def ex(sql,params=None):
        s=sql.lower()
        if 'product_option' in s: cur.fetchall.return_value=list(PROD_OPTS)
        elif 'customer_product_application' in s and ('join' in s or 'left join' in s): cur.fetchall.return_value=list(MY_APPS)
        elif 'product_master' in s: cur.fetchone.return_value=dict(PROD_DETAIL); cur.fetchall.return_value=list(MY_APPS)
        else: cur.fetchone.return_value=None; cur.fetchall.return_value=[]
    cur.execute.side_effect=ex
    cur.fetchone.return_value=dict(PROD_DETAIL); cur.fetchall.return_value=[]
    cur.__enter__=M.Mock(return_value=cur); cur.__exit__=M.Mock(return_value=False)
    db=M.MagicMock(); db.cursor.return_value=cur; db.close.return_value=None; db.commit.return_value=None
    return db
app.get_db=lambda:mk_db()

app.app.run(port=5000, use_reloader=False, threaded=True)
