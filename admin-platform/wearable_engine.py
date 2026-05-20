"""Wearable 실시간 데이터 — 메모리 엔진 (시연용).

운영 시 교체 포인트:
- `load_initial`     → Kinesis Stream consumer
- `_state['latest']` → DynamoDB `wearable_latest{global_id}`
- `_state['red/yellow/device']` → DynamoDB `anomaly_event` scan (최근 N)
- `tick`             → 실 Kinesis 이벤트 수신 핸들러
"""
import json
import random
import threading
import time
from collections import deque
from datetime import datetime, timezone, timedelta


_SURNAMES = ['김', '이', '박', '최', '정', '강', '조', '윤', '장', '임']

_lock = threading.Lock()
_state = {
    'latest':       {},              # global_id → record (payload + event_time)
    'red':          deque(maxlen=30),   # 시계열 알람 로그
    'yellow':       deque(maxlen=30),
    'active_count': 0,
    'registered':   0,
}


# ── PII 마스킹 — admin 도 풀네임/풀 ID 안 보이게 ─────────────────
def mask_name(global_id):
    n = int(''.join(c for c in global_id if c.isdigit()) or '0')
    return _SURNAMES[n % 10] + '**'


def mask_gid(global_id):
    # G00023*** (앞 5자리 + 마스킹)
    return global_id[:5] + '***' if len(global_id) > 5 else global_id


# ── 의학/표준 기준 분류 (AHA/WHO/Firstbeat) ────────────────────
def classify(rec):
    """RED / YELLOW 사유 list 반환. RED 발생 시 YELLOW 는 생략."""
    p = rec['payload']
    hr     = p['heart_rate']
    spo2   = p['spo2_pct']
    stress = p['stress_score']

    health_red, health_yellow = [], []

    # 건강 RED — AHA/WHO 임상 임계
    if hr < 50:        health_red.append(f'서맥 {hr}bpm (<50)')
    elif hr >= 120:    health_red.append(f'현저한 빈맥 {hr}bpm (≥120)')
    if spo2 < 90:      health_red.append(f'저산소증 {spo2}% (<90)')
    if stress >= 76:   health_red.append(f'스트레스 고위험 {stress}')

    # 건강 YELLOW — 경계 영역 (RED 없을 때만)
    if not health_red:
        if 50 <= hr < 60:      health_yellow.append(f'심박 낮음 {hr}bpm')
        elif 100 < hr < 120:   health_yellow.append(f'빈맥 {hr}bpm')
        if 90 <= spo2 < 95:    health_yellow.append(f'경증 저산소 {spo2}%')
        if 51 <= stress <= 75: health_yellow.append(f'스트레스 중등도 {stress}')

    return health_red, health_yellow


_KST = timezone(timedelta(hours=9))


def _to_kst_hms(iso_utc):
    """ISO UTC 문자열 → KST 'HH:MM:SS'."""
    if not iso_utc:
        return ''
    try:
        dt = datetime.fromisoformat(iso_utc.replace('Z', '+00:00'))
        return dt.astimezone(_KST).strftime('%H:%M:%S')
    except Exception:
        return iso_utc[11:19] if len(iso_utc) >= 19 else iso_utc


def _row_base(r):
    p = r['payload']
    return {
        'time':      _to_kst_hms(r.get('event_time', '')),
        'gid_full':  r['global_id'],
        'gid':       mask_gid(r['global_id']),
        'name':      mask_name(r['global_id']),
        'hr':        p['heart_rate'],
        'spo2':      p['spo2_pct'],
        'stress':    p['stress_score'],
        'batt':      p['battery_pct'],
    }


def _record_event(r):
    """현재 lock 보유 상태에서 호출 — deque 갱신."""
    red, yellow = classify(r)
    base = _row_base(r)
    if red:
        _state['red'].appendleft({**base, 'reasons': ' · '.join(red)})
    if yellow:
        _state['yellow'].appendleft({**base, 'reasons': ' · '.join(yellow)})


# ── 초기 적재 (mock_wearable_batch.json) ────────────────────
def load_initial(path):
    with open(path, encoding='utf-8') as f:
        batch = json.load(f)
    with _lock:
        for r in batch['records']:
            _state['latest'][r['global_id']] = r
        _state['registered']   = len(_state['latest'])
        _state['active_count'] = len(_state['latest'])


# ── 3초 tick — 30명 랜덤 + noise + 재분류 ───────────────────
def tick():
    with _lock:
        gids = list(_state['latest'].keys())
    if not gids:
        return
    sample = random.sample(gids, min(30, len(gids)))
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        for gid in sample:
            r = _state['latest'][gid]
            p = dict(r['payload'])
            p['heart_rate']   = max(40, min(140, p['heart_rate']   + random.randint(-5, 5)))
            p['spo2_pct']     = max(85, min(100, p['spo2_pct']     + random.randint(-1, 1)))
            p['stress_score'] = max(0,  min(100, p['stress_score'] + random.randint(-5, 5)))
            p['battery_pct']  = max(0,  min(100, p['battery_pct']  - random.randint(0, 1)))
            updated = {**r, 'payload': p, 'event_time': now}
            _state['latest'][gid] = updated
            _record_event(updated)
        _state['active_count'] = len(sample)


def snapshot():
    """KPI 4 + RED/YELLOW 표 데이터 — SSE/JSON 응답용."""
    with _lock:
        registered = _state['registered']
        active     = _state['active_count']
        red_n, yellow_n = 0, 0
        for r in _state['latest'].values():
            red, yellow = classify(r)
            if red:    red_n    += 1
            if yellow: yellow_n += 1
        send_rate = (active * 100 // registered) if registered else 0
        return {
            'kpi': [
                {'label': '활성 디바이스',   'value': f'{active}',  'sub': f'/ 등록 {registered} · 최근 1초', 'accent': '#3b82f6'},
                {'label': '송신율',         'value': f'{send_rate}%', 'sub': '활성 / 등록',                  'accent': '#16a34a'},
                {'label': '🔴 건강 RED',    'value': str(red_n),    'sub': 'AHA/WHO 임상 임계',             'accent': '#dc2626'},
                {'label': '🟡 건강 YELLOW', 'value': str(yellow_n), 'sub': '경계 영역 — 모니터링',           'accent': '#f59e0b'},
            ],
            'red':    list(_state['red'])[:10],
            'yellow': list(_state['yellow'])[:10],
        }


# ── 백그라운드 루프 ────────────────────────────────────────
_loop_started = False

def start_loop(interval=1.0):
    global _loop_started
    if _loop_started:
        return
    _loop_started = True

    def _run():
        while True:
            try:
                tick()
            except Exception:
                pass
            time.sleep(interval)

    threading.Thread(target=_run, daemon=True, name='wearable-tick').start()
