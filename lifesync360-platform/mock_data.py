import hashlib
import json
from pathlib import Path

_PW_HASH = hashlib.sha256('password123'.encode('utf-8')).hexdigest()

_PRODUCTS_DIR = Path(__file__).parent.parent / 'data' / 'products'

# ── 사용자 (3명) ──────────────────────────────────────────────────
# DynamoDB lifesync_customer_result 매핑: global_id, dynamic_grade, vip_prob, signup_prob, rec_prob, next_best_action
# 온프레 customer_360_profile 매핑: gender, age_band, region, income_grade, asset_grade, wearable_flag, risk_score, finance_score, asset_score, lifesync_score
# 온프레 master_customer 매핑: customer_status, vip_grade, customer_type, first_created_dt
MOCK_USERS = {
    'test@lifesync.com': {
        'ls_user_id':    'LS-AABBCC11-000001',
        'global_id':     'G000297409',
        'name':          '김철수',
        'email':         'test@lifesync.com',
        'password_hash': _PW_HASH,
        'grade':         'VIP',
        # 인구통계 (customer_360_profile)
        'gender':        'M',
        'age_band':      '40s',
        'region':        'SEOUL',
        'income_grade':  'HIGH',
        'asset_grade':   'HIGH',
        'wearable_flag': 'Y',
        # 마스터 (master_customer)
        'customer_status': 'ACTIVE',
        'vip_grade':       'GOLD',
        'customer_type':   'INDIVIDUAL',
        'first_created_dt':'2022-03-15',
        'last_login_dt':   '2026-05-13 18:24',
        # ML 확률 (DynamoDB)
        'vip_prob':         0.85,
        'signup_prob':      0.72,
        'rec_prob':         0.91,
        'next_best_action': '프리미엄 건강검진 예약하기',
    },
    'test2@lifesync.com': {
        'ls_user_id':    'LS-DDEEFF22-000002',
        'global_id':     'G000672689',
        'name':          '이수진',
        'email':         'test2@lifesync.com',
        'password_hash': _PW_HASH,
        'grade':         'GOLD',
        'gender':        'F',
        'age_band':      '30s',
        'region':        'GYEONGGI',
        'income_grade':  'MID',
        'asset_grade':   'MID',
        'wearable_flag': 'Y',
        'customer_status': 'ACTIVE',
        'vip_grade':       'SILVER',
        'customer_type':   'INDIVIDUAL',
        'first_created_dt':'2023-08-02',
        'last_login_dt':   '2026-05-14 09:11',
        'vip_prob':         0.58,
        'signup_prob':      0.66,
        'rec_prob':         0.79,
        'next_best_action': 'ETF 적립식 투자 시작',
    },
    'test3@lifesync.com': {
        'ls_user_id':    'LS-99AABB33-000003',
        'global_id':     'G000115282',
        'name':          '박지훈',
        'email':         'test3@lifesync.com',
        'password_hash': _PW_HASH,
        'grade':         'SILVER',
        'gender':        'M',
        'age_band':      '50s',
        'region':        'BUSAN',
        'income_grade':  'MID',
        'asset_grade':   'LOW',
        'wearable_flag': 'N',
        'customer_status': 'ACTIVE',
        'vip_grade':       'NORMAL',
        'customer_type':   'INDIVIDUAL',
        'first_created_dt':'2024-01-20',
        'last_login_dt':   '2026-05-12 22:48',
        'vip_prob':         0.32,
        'signup_prob':      0.51,
        'rec_prob':         0.64,
        'next_best_action': '실손 의료보험 가입 검토',
    },
}

# ── 건강 데이터 (ls_user_id 기준) ─────────────────────────────────
# breakdown: 심혈관 max 35 / 활동 max 35 / 신체지표 max 20 / 임상 max 10
_HEALTH_BY_USER = {
    'LS-AABBCC11-000001': {
        # DynamoDB 점수
        'dynamic_score': 92.4, 'health_score': 88, 'fin_score': 85, 'behavior_score': 76,
        # customer_360_profile 점수 (운영 시 onprem)
        'risk_score':     22.5,
        'finance_score':  85.0,
        'asset_score':    78.5,
        'lifesync_score': 91.2,
        # DynamoDB ML 확률 + NBA
        'vip_prob':         0.85,
        'signup_prob':      0.72,
        'rec_prob':         0.91,
        'next_best_action': '프리미엄 건강검진 예약하기',
        'breakdown': [
            {'label': '심혈관',   'score': 32, 'max': 35},
            {'label': '활동',     'score': 31, 'max': 35},
            {'label': '신체지표', 'score': 17, 'max': 20},
            {'label': '임상',     'score': 8,  'max': 10},
        ],
        'indicators': [
            {'label': '혈당',   'status': 'NORMAL'},
            {'label': '지질',   'status': 'CAUTION'},
            {'label': '간기능', 'status': 'NORMAL'},
            {'label': '신장',   'status': 'NORMAL'},
        ],
        'spending': [
            {'label': '식품',   'pct': 38},
            {'label': '쇼핑',   'pct': 22},
            {'label': '의료',   'pct': 15},
            {'label': '교통',   'pct': 14},
            {'label': '여가',   'pct': 11},
        ],
    },
    'LS-DDEEFF22-000002': {
        'dynamic_score': 74.0, 'health_score': 72, 'fin_score': 68, 'behavior_score': 81,
        'risk_score':     35.0,
        'finance_score':  68.0,
        'asset_score':    62.5,
        'lifesync_score': 73.2,
        'vip_prob':         0.58,
        'signup_prob':      0.66,
        'rec_prob':         0.79,
        'next_best_action': 'ETF 적립식 투자 시작',
        'breakdown': [
            {'label': '심혈관',   'score': 24, 'max': 35},
            {'label': '활동',     'score': 26, 'max': 35},
            {'label': '신체지표', 'score': 14, 'max': 20},
            {'label': '임상',     'score': 8,  'max': 10},
        ],
        'indicators': [
            {'label': '혈당',   'status': 'CAUTION'},
            {'label': '지질',   'status': 'CAUTION'},
            {'label': '간기능', 'status': 'NORMAL'},
            {'label': '신장',   'status': 'NORMAL'},
        ],
        'spending': [
            {'label': '식품',   'pct': 42},
            {'label': '쇼핑',   'pct': 25},
            {'label': '의료',   'pct': 12},
            {'label': '교통',   'pct': 13},
            {'label': '여가',   'pct': 8},
        ],
    },
    'LS-99AABB33-000003': {
        'dynamic_score': 55.2, 'health_score': 53, 'fin_score': 58, 'behavior_score': 61,
        'risk_score':     58.0,
        'finance_score':  58.0,
        'asset_score':    48.0,
        'lifesync_score': 54.8,
        'vip_prob':         0.32,
        'signup_prob':      0.51,
        'rec_prob':         0.64,
        'next_best_action': '실손 의료보험 가입 검토',
        'breakdown': [
            {'label': '심혈관',   'score': 18, 'max': 35},
            {'label': '활동',     'score': 19, 'max': 35},
            {'label': '신체지표', 'score': 11, 'max': 20},
            {'label': '임상',     'score': 5,  'max': 10},
        ],
        'indicators': [
            {'label': '혈당',   'status': 'DANGER'},
            {'label': '지질',   'status': 'CAUTION'},
            {'label': '간기능', 'status': 'CAUTION'},
            {'label': '신장',   'status': 'NORMAL'},
        ],
        'spending': [
            {'label': '식품',   'pct': 35},
            {'label': '쇼핑',   'pct': 18},
            {'label': '의료',   'pct': 25},
            {'label': '교통',   'pct': 12},
            {'label': '여가',   'pct': 10},
        ],
    },
}

# ── 등급별 활성 캠페인 배너 (campaign_master 기반) ─────────────────
MOCK_CAMPAIGNS_BY_GRADE = {
    'VIP': [
        {'icon': '👑', 'title': 'VIP 프리미엄 자산관리',
         'desc': 'PB 예금·WM·VIP 카드·상속 보험 통합 추천',
         'period': '2026-04-15 ~ 2026-07-15', 'cta': '자산 컨설팅 받기'},
        {'icon': '🏥', 'title': 'VIP 라이프케어',
         'desc': '고액자산가 통합 라이프케어 — 금융+건강 동시 관리',
         'period': '2026-05-01 ~ 2026-07-31', 'cta': '신청하기'},
        {'icon': '📜', 'title': '상속/절세 설계',
         'desc': '상속·절세 포트폴리오 무료 컨설팅',
         'period': '2026-05-10 ~ 2026-08-10', 'cta': '예약하기'},
    ],
    'GOLD': [
        {'icon': '🌐', 'title': '글로벌 투자 캠페인',
         'desc': 'ETF·펀드·달러자산 우대 수수료',
         'period': '2026-05-01 ~ 2026-07-31', 'cta': '투자 시작'},
        {'icon': '✈️', 'title': '프리미엄 카드 혜택',
         'desc': '여행·마일리지·라운지 이용 한도 2배',
         'period': '2026-04-20 ~ 2026-06-20', 'cta': '카드 신청'},
        {'icon': '💪', 'title': '프리미엄 건강보장',
         'desc': '건강과 금융을 함께 관리하는 우량 고객 캠페인',
         'period': '2026-05-05 ~ 2026-08-05', 'cta': '상담 받기'},
    ],
    'SILVER': [
        {'icon': '💰', 'title': '생활금융 혜택',
         'desc': '적금·카드·배당 ETF 통합 혜택',
         'period': '2026-05-01 ~ 2026-07-31', 'cta': '혜택 보기'},
        {'icon': '🩺', 'title': '건강보장 시작',
         'desc': '건강관리와 보장성 상품을 함께 추천',
         'period': '2026-04-25 ~ 2026-07-25', 'cta': '시작하기'},
        {'icon': '🎯', 'title': '목적자금 만들기',
         'desc': '여행·교육·결혼 목적 적금 우대',
         'period': '2026-05-10 ~ 2026-08-10', 'cta': '플랜 만들기'},
    ],
    'BASIC': [
        {'icon': '🌱', 'title': '금융 시작 캠페인',
         'desc': '청년 적금·체크카드·간편 보험',
         'period': '2026-05-01 ~ 2026-07-31', 'cta': '시작하기'},
        {'icon': '💳', 'title': '생활비 절약',
         'desc': '캐시백·할인 카드·생활비 절약 적금',
         'period': '2026-04-20 ~ 2026-06-20', 'cta': '신청'},
        {'icon': '📱', 'title': '간편보험 시작',
         'desc': '모바일 3분 가입 간편 보험',
         'period': '2026-05-10 ~ 2026-08-10', 'cta': '가입하기'},
    ],
    'CARE': [
        {'icon': '🧬', 'title': 'AI 건강관리',
         'desc': 'AI 리포트·식단·운동 맞춤 추천',
         'period': '2026-05-01 ~ 2026-07-31', 'cta': '시작하기'},
        {'icon': '🌿', 'title': '웰니스 보험연계',
         'desc': '건강관리 이력 기반 보험 우대',
         'period': '2026-04-25 ~ 2026-07-25', 'cta': '추천 받기'},
        {'icon': '💬', 'title': '비대면 건강상담',
         'desc': '화상진료·건강상담 서비스 무료 1회',
         'period': '2026-05-10 ~ 2026-08-10', 'cta': '예약'},
    ],
}

def get_mock_campaigns(grade):
    return MOCK_CAMPAIGNS_BY_GRADE.get(grade, MOCK_CAMPAIGNS_BY_GRADE['BASIC'])


_DEFAULT_UID = 'LS-AABBCC11-000001'

def get_mock_health(ls_user_id):
    return _HEALTH_BY_USER.get(ls_user_id, _HEALTH_BY_USER[_DEFAULT_UID])

# ── 포인트 ─────────────────────────────────────────────────────────
MOCK_POINTS = {'balance': 12500, 'next_grade': None, 'next_grade_points': 0, 'next_grade_percent': 100}

MOCK_POINT_HISTORY = [
    {'date': '2026.05.06', 'desc': '걷기 챌린지 달성',     'points': '+200', 'type': 'earn'},
    {'date': '2026.05.03', 'desc': '건강데이터 제공',       'points': '+50',  'type': 'earn'},
    {'date': '2026.05.01', 'desc': '정밀 건강검진 할인',    'points': '-800', 'type': 'use'},
    {'date': '2026.04.28', 'desc': '월간 목표 달성',        'points': '+300', 'type': 'earn'},
    {'date': '2026.04.25', 'desc': '보험료 자동이체',       'points': '+100', 'type': 'earn'},
    {'date': '2026.04.20', 'desc': '건강점수 10점 향상',    'points': '+500', 'type': 'earn'},
    {'date': '2026.04.15', 'desc': 'ETF 자동적립 신청',     'points': '+150', 'type': 'earn'},
    {'date': '2026.04.10', 'desc': '건강데이터 제공',       'points': '+50',  'type': 'earn'},
]

# ── 등급 업그레이드 액션 가이드 ────────────────────────────────────
UPGRADE_ACTIONS = [
    {'icon': '👟', 'title': '걷기 챌린지 참여',    'desc': '매일 8,000보 × 30일',     'points': '+5,000P', 'badge': '충성도 +10'},
    {'icon': '🏥', 'title': '건강검진 수검',        'desc': '당해 연도 건강검진 완료', 'points': '+500P',   'badge': '건강점수 +7'},
    {'icon': '📡', 'title': '웨어러블 연동',        'desc': '기기 데이터 연결하기',    'points': '+200P',   'badge': '건강점수 +5'},
    {'icon': '💳', 'title': '보험 납입 6개월 유지', 'desc': '연속 정상납입 유지',      'points': '+300P',   'badge': '충성도 +10'},
    {'icon': '🔗', 'title': '계열사 3개 이상 연동', 'desc': '데이터 동의 확대',        'points': '+150P',   'badge': '충성도 +18'},
]

# ── 상품 JSON 로딩 ────────────────────────────────────────────────
def _desc(cat, raw):
    if cat in ('deposit_product', 'savings_product'):
        r, m = raw.get('기준금리(연)', ''), raw.get('최고금리(연)', '')
        return f"{r} / 최고 {m}" if r else raw.get('상품유형', '')
    if cat == 'loan_product':
        r, l = raw.get('최저금리(연)', ''), raw.get('대출한도', '')
        return f"최저 {r} / 한도 {l}" if r else raw.get('상품유형', '')
    if cat == 'card_product':
        fee, pct = raw.get('연회비(원)', ''), raw.get('기본적립률(%)', '')
        return f"연회비 {fee}원 / 기본적립 {pct}%" if fee else ''
    if cat in ('insurance_product', 'internet_insurance_product'):
        pm, tg = raw.get('월 보험료(평균)', ''), raw.get('대상고객', '')
        return f"월 {pm} / {tg}" if pm else raw.get('카버리지', '')
    if cat == 'exercise_recommendation':
        ev, ia = raw.get('운동유형', ''), raw.get('활동강도 (분/칼로리)', '')
        return f"{ev} / {ia}" if ev else ''
    if cat == 'health_checkup':
        cnt, pt = raw.get('항목수', ''), raw.get('가격트랙', '')
        return f"{cnt}개 항목 / {pt}" if cnt else ''
    if cat == 'portfolio_product':
        tend, ret = raw.get('투자성향', ''), raw.get('연수익률 (평균/목표)', '')
        return f"투자성향 {tend} / 목표수익 {ret}" if tend else ''
    return ''

def _detail(cat, raw):
    keys_map = {
        'deposit_product':            ['우대금리조건', 'AI 추천 조건', '가입기간', '비고'],
        'savings_product':            ['우대금리조건', 'AI 추천 조건', '납입기간', '비고'],
        'loan_product':               ['우대금리 조건', 'AI 추천 조건', '상환방식', '비고'],
        'card_product':               ['다시 보기', '포인트 적립 조건', '추가 혜택', '연회비(원)'],
        'insurance_product':          ['카버리지', '대상고객', '주요 보장 내용', '가입기간'],
        'internet_insurance_product': ['카버리지', '대상고객', '주요 보장 내용', '가입기간'],
        'exercise_recommendation':    ['활동강도 (분/칼로리)', '추천 시 조건', '추천 이유 (우선순위)', '최대 횟수'],
        'health_checkup':             ['패키지트리거', '권장타겟그룹', '항목수', '가격트랙'],
        'portfolio_product':          ['주요 국내 주식 ETF', '해외주식 ETF', '채권/대안자산', '연수익률 (평균/목표)'],
    }
    items = []
    for k in keys_map.get(cat, []):
        v = str(raw.get(k, '')).strip()
        if v and v != 'nan':
            items.append(v)
    return items[:4] or ['상세 정보를 앱에서 확인하세요']

def _type_label(cat, raw):
    m = {
        'deposit_product':            lambda r: r.get('상품유형', '예금'),
        'savings_product':            lambda r: r.get('상품유형', '적금'),
        'loan_product':               lambda r: r.get('대출유형', r.get('상품유형', '대출')),
        'card_product':               lambda r: '신용카드',
        'insurance_product':          lambda r: r.get('카버리지', '보험'),
        'internet_insurance_product': lambda r: r.get('카버리지', '온라인보험'),
        'exercise_recommendation':    lambda r: r.get('운동유형', '헬스케어'),
        'health_checkup':             lambda r: '건강검진',
        'portfolio_product':          lambda r: r.get('투자성향', '포트폴리오'),
    }
    return m.get(cat, lambda r: '상품')(raw)

def _load_json_products(company_key, filename, max_products=4):
    path = _PRODUCTS_DIR / f'{filename}.json'
    if not path.exists():
        return []
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        result = []
        for i, p in enumerate(data.get('products', [])):
            if len(result) >= max_products:
                break
            name = p.get('product_name', '').strip()
            if not name:
                continue
            raw = p.get('raw', {})
            cat = p.get('category', '')
            d = _desc(cat, raw)
            result.append({
                'id':     p.get('product_code', str(i)),
                'type':   _type_label(cat, raw),
                'name':   name,
                'desc':   d or '상세 정보 확인',
                'tag':    '맞춤추천' if i == 0 else '',
                'detail': _detail(cat, raw),
            })
        return result
    except Exception:
        return []

# ── 폴백 상품 (JSON 로딩 실패 시) ────────────────────────────────
_FALLBACK = {
    'bank': [
        {'id': 'bank_f01', 'type': '예금', 'name': 'LifeSync 정기예금 12개월', 'desc': '기준금리 3.50% / 최고 3.90%', 'tag': '맞춤추천',
         'detail': ['LifeSync 앱 가입 +0.1% / 건강점수≥70 +0.2%', '최소 가입금액 100만원', '만기일시지급', '세금우대 가능']},
        {'id': 'bank_f02', 'type': '예금', 'name': '건강점수 연동 우대예금', 'desc': '건강점수 구간별 자동우대 최고 3.90%', 'tag': '',
         'detail': ['건강점수 ≥90 +0.5% / ≥75 +0.3% / ≥60 +0.1%', '최소 가입금액 50만원', 'AI 핵심 연동 예금', '12개월']},
        {'id': 'bank_f03', 'type': '적금', 'name': '건강목표 달성 적금', 'desc': '기준금리 3.50% / 최고 4.30%', 'tag': '',
         'detail': ['걸음수 8,000보 30일 연속 +0.5%', '건강점수 10점 향상 +0.3%', '6개월 납입', 'AI 핵심: 건강+금융 교차']},
        {'id': 'bank_f04', 'type': '대출', 'name': 'LifeSync 직장인 신용대출', 'desc': '최저 4.50% / 한도 최대 1억원', 'tag': '',
         'detail': ['재직 1년 이상 직장인 대상', '건강점수≥70 -0.2%', '원리금균등 상환', '당일 심사 및 지급']},
    ],
    'card': [
        {'id': 'card_f01', 'type': '신용카드', 'name': 'The Black', 'desc': 'VIP 전용 프리미엄', 'tag': '맞춤추천',
         'detail': ['공항 라운지 무제한', '해외결제 수수료 면제', '전 가맹점 2% 적립', '연회비 15만원']},
        {'id': 'card_f02', 'type': '신용카드', 'name': 'The Blue', 'desc': '일상 특화 적립 카드', 'tag': '',
         'detail': ['식품·편의점 5% 적립', '대중교통 10% 할인', '전 가맹점 1.5% 적립', '연회비 3만원']},
        {'id': 'card_f03', 'type': '체크카드', 'name': '헬스케어 체크카드', 'desc': '병원·약국 5% 캐시백', 'tag': '',
         'detail': ['병원·약국 5% 캐시백', '편의점 3% 캐시백', '월 최대 3만원', '연회비 없음']},
    ],
    'insurance': [
        {'id': 'ins_f01', 'type': '건강보험', 'name': '건강지킴이 보험', 'desc': '심혈관 특약 / 건강점수 연동 할인', 'tag': '맞춤추천',
         'detail': ['심혈관 질환 특약 포함', '건강점수 연동 할인 최대 15%', '월 보험료 3.2만원부터', '비급여 실손 90% 보장']},
        {'id': 'ins_f02', 'type': '실손보험', 'name': '실손 플러스', 'desc': '월 15,000원부터 / 4세대 실손', 'tag': '',
         'detail': ['4세대 실손보험', '입원·통원 통합 보장', '자기부담금 20%', '갱신주기 5년']},
        {'id': 'ins_f03', 'type': '생명보험', 'name': '라이프 종신보험', 'desc': '사망+중증질환 / 건강점수 우대', 'tag': '',
         'detail': ['사망 및 중증질환 보장', '건강점수 연동 우대', '비과세 저축기능 포함', '중도해지환급금 있음']},
    ],
    'internet_insurance': [
        {'id': 'inet_f01', 'type': '여행보험', 'name': '다이렉트 여행자보험', 'desc': '하루 1,000원부터', 'tag': '맞춤추천',
         'detail': ['국내외 여행 중 상해·질병 보장', '출발 당일 가입 가능', '1일~90일 단기 선택', '비대면 청구 지원']},
        {'id': 'inet_f02', 'type': '펫보험', 'name': '반려동물 다이렉트', 'desc': '월 2만원대, 통원 포함', 'tag': '',
         'detail': ['통원·입원·수술 통합 보장', '연간 보장 한도 300만원', '강아지·고양이 공통', '가입 나이 생후 3개월~8세']},
        {'id': 'inet_f03', 'type': '운전자보험', 'name': '운전자보험 다이렉트', 'desc': '연 3만원대, 형사합의금 포함', 'tag': '',
         'detail': ['형사합의금 최대 3,000만원', '벌금 및 방어비용 지원', '자동차보험과 중복 가능', '비대면 가입 즉시 보장']},
    ],
    'securities': [
        {'id': 'sec_f01', 'type': 'ISA', 'name': 'ISA 통합계좌', 'desc': '비과세 한도 연 200만원', 'tag': '맞춤추천',
         'detail': ['연간 200만원 비과세', '국내주식·ETF·펀드 통합', '의무가입기간 3년', '서민형 400만원 비과세']},
        {'id': 'sec_f02', 'type': '해외주식', 'name': '해외주식 직구', 'desc': '수수료 0.07%, 환전 우대 90%', 'tag': '',
         'detail': ['미국·일본·중국·홍콩', '수수료 0.07%', '환전 우대율 90%', '실시간 AI 리포트 제공']},
        {'id': 'sec_f03', 'type': 'ETF적립', 'name': 'ETF 자동적립', 'desc': '월 1만원부터 자동 분산투자', 'tag': '',
         'detail': ['월 1만원부터', '국내·해외 ETF 100종', '매월 지정일 자동 매수', '수수료 무료']},
    ],
    'healthcare': [
        {'id': 'hc_f01', 'type': '검진', 'name': 'VIP 종합 건강검진', 'desc': '제휴병원 30% 할인 / 150개 항목', 'tag': '맞춤추천',
         'detail': ['전국 제휴병원 30% 할인', '150개 항목 종합검진', '검진 결과 AI 분석 제공', '예약 후 2주 내 진행']},
        {'id': 'hc_f02', 'type': '챌린지', 'name': '걷기 챌린지', 'desc': '30일 달성 시 5,000P', 'tag': '진행중',
         'detail': ['매일 8,000보 달성 시 인정', '30일 완주 시 5,000P 지급', '웨어러블 자동 연동', '중도 이탈 후 재참여 가능']},
        {'id': 'hc_f03', 'type': '건강관리', 'name': '체중관리 AI 코칭', 'desc': 'BMI 기반 맞춤 운동 추천', 'tag': '',
         'detail': ['AI 맞춤 운동 처방', '주 3회 이상 달성 시 포인트', '영양사 1:1 상담 월 1회', '건강점수 연동']},
    ],
    'hospital': [
        {'id': 'hosp_f01', 'type': '건강검진', 'name': '정밀 건강검진 패키지', 'desc': 'AI 판독 포함, 건강점수 연동', 'tag': '맞춤추천',
         'detail': ['200개 항목 정밀검진', 'AI 영상 판독 포함', '검진 결과 → 건강점수 자동 반영', '당일 결과 확인 가능']},
        {'id': 'hosp_f02', 'type': '비급여할인', 'name': '비급여 진료 할인', 'desc': '도수치료·영양주사 20% 할인', 'tag': '',
         'detail': ['도수치료·체외충격파 20% 할인', '영양주사·미용의료 할인', '월 최대 10만원 할인 한도', 'LS 회원 전용 우선 예약']},
        {'id': 'hosp_f03', 'type': '만성질환', 'name': '만성질환 관리 프로그램', 'desc': '고혈압·당뇨 월 정기 케어', 'tag': '',
         'detail': ['매월 전담 간호사 1:1 상담', '혈압·혈당 원격 모니터링', '처방전 비대면 발급', '건강점수 연동 할인 최대 20%']},
    ],
}

def _build_recommendations():
    config = [
        ('bank',       '은행',      'bank',               5),
        ('card',       '카드',      'card',               4),
        ('insurance',  '보험',      'insurance',          4),
        ('internet_insurance',   '온라인보험', 'internet_insurance', 3),
        ('securities', '증권',      'securities',         3),
        ('healthcare', '헬스케어',  'healthcare',         3),
        ('hospital',   'LS 병원',   'hospital',           3),
    ]
    recs = []
    for key, name, filename, max_p in config:
        products = _load_json_products(key, filename, max_p)
        if not products:
            products = _FALLBACK.get(key, [])
        recs.append({'key': key, 'name': name, 'products': products})
    return recs

MOCK_RECOMMENDATIONS = _build_recommendations()

PRODUCTS_MAP = {
    p['id']: {**p, 'category': rec['name']}
    for rec in MOCK_RECOMMENDATIONS
    for p in rec['products']
}

