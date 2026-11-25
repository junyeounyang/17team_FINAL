"""버스·소방차 가림 (2026-11-25) — 키가 큰 차 뒤에 있는 것은 AV 의 관측에서 빠진다.

가리는 차   버스(bus), 소방차(fire_siren · fire_normal), 택배 탑차(car_van. 일반 차량의 4%, daehakro_config.VAN_SHARE).
            일반 승용차·구급차·보행자는 아무것도 가리지 않는다.
가려지는 것 (env/daehakro_env.py 가 관측을 만들 때 이 파일의 함수로 판단한다)
    1. 신호 색            내 차로 바로 앞차가 버스·소방차이고, AV 의 눈에서 신호등으로 그은 시선이 그 차 지붕보다 낮게 지날 때
                          앞차 뒷면까지 거리 ≤ k × 신호등까지 거리,  k = (차 높이 − 눈 높이) / (신호등 높이 − 눈 높이)
    2. 횡단보도 보행자    기다려야 할 보행자가 모두 버스·소방차 뒤에 있을 때
    3. 겹치는 차          그 차가 버스·소방차 뒤에 있을 때
    4. 옆옆 차로의 차     그 차가 버스·소방차 뒤에 있을 때 (옆 차로에 나란히 선 버스 너머)
    5. 사이렌 차의 차로   사이렌 차가 버스·소방차 뒤에 있을 때 (거리는 소리로 알므로 그대로)
2~5 는 땅 위에서 본 직선으로 판단한다: AV 의 눈과 대상을 이은 선분이 버스·소방차의 차체(직사각형)를 지나면 가려진 것.
차는 앞끝·가운데·뒤끝 세 점이 모두 가려져야 가려진 것으로 본다 (일부라도 보이면 보인다).

끄기: 환경변수 DAEHAKRO_OCCLUSION=0  (기본은 켬). 꺼도 관측의 칸 수는 같다 (가림 칸이 늘 0).
위반 판정·보상·시범 운전자는 가림과 상관없이 실제 상황을 쓴다.
"""
import math
import os

ENABLED = os.environ.get("DAEHAKRO_OCCLUSION", "1").strip().lower() not in ("0", "off", "false", "no")

EYE_HEIGHT = 1.5            # m. AV 의 눈(카메라) 높이
EYE_BACK = 2.0              # m. AV 앞 범퍼에서 눈까지 (뒤쪽으로)
SIGNAL_HEIGHT = 5.0         # m. 차량 신호등 높이
SIGNAL_BEHIND_LINE = 20.0   # m. 신호등은 정지선에서 이만큼 더 가서 달려 있다 (교차로 건너편)
TALL = {"bus": 3.2, "fire": 3.0, "van": 2.6}   # m. 가리는 차의 높이 (van = 택배 탑차, daehakro_config.VAN_TYPE)
TALL_WIDTH = {"bus": 2.5, "fire": 2.5, "van": 1.8}   # m. 가리는 차의 폭


def tall_kind(type_id):
    """SUMO 차종 id → 'bus' / 'fire' / None (가리지 않는 차)."""
    t = str(type_id or "").split("@")[0]         # 'car_van@차이름' 처럼 그 차 전용으로 바뀐 차종도 있다 (daehakro_emergency)
    if t == "bus" or t.startswith("bus"):
        return "bus"
    if t.startswith("fire"):
        return "fire"
    if t == "car_van":
        return "van"
    return None


def signal_hidden(kind, bumper_gap, stop_line_dist):
    """내 차로 바로 앞의 버스·소방차(kind)가 신호등을 가리는가.
    bumper_gap: 내 앞 범퍼 ~ 그 차 뒷면 (m). stop_line_dist: 내 앞 범퍼 ~ 정지선 (m)."""
    height = TALL.get(kind)
    if height is None:
        return False
    k = (height - EYE_HEIGHT) / (SIGNAL_HEIGHT - EYE_HEIGHT)
    to_car = max(bumper_gap, 0.0) + EYE_BACK
    to_signal = max(stop_line_dist, 0.0) + EYE_BACK + SIGNAL_BEHIND_LINE
    return to_car <= k * to_signal


def heading(angle_deg):
    """SUMO 각도(북 0°, 시계 방향) → 진행 방향 단위벡터 (x, y)."""
    a = math.radians(angle_deg)
    return math.sin(a), math.cos(a)


def body(front_xy, angle_deg, length, width=2.5):
    """차체 직사각형의 네 꼭짓점. front_xy 는 SUMO 가 주는 위치(앞 범퍼 가운데)."""
    fx, fy = heading(angle_deg)
    rx, ry = fy * width / 2.0, -fx * width / 2.0
    x0, y0 = front_xy
    x1, y1 = x0 - fx * length, y0 - fy * length
    return ((x0 + rx, y0 + ry), (x0 - rx, y0 - ry), (x1 - rx, y1 - ry), (x1 + rx, y1 + ry))


def points(front_xy, angle_deg, length):
    """차의 앞끝·가운데·뒤끝 (가운데 선 위)."""
    fx, fy = heading(angle_deg)
    x0, y0 = front_xy
    return [(x0 - fx * length * t, y0 - fy * length * t) for t in (0.0, 0.5, 1.0)]


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_meet(p, q, a, b):
    d1, d2 = _cross(a, b, p), _cross(a, b, q)
    d3, d4 = _cross(p, q, a), _cross(p, q, b)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def _inside(pt, quad):
    sign = None
    for i in range(4):
        c = _cross(quad[i], quad[(i + 1) % 4], pt)
        if abs(c) < 1e-12:
            continue
        if sign is None:
            sign = c > 0
        elif (c > 0) != sign:
            return False
    return True


def blocked(eye, target, bodies, skip=None):
    """eye 와 target 을 이은 선분이 bodies ({id: 네 꼭짓점}) 가운데 하나라도 지나는가. skip 은 빼고 본다 (대상 자신)."""
    for key, quad in bodies.items():
        if key == skip:
            continue
        if _inside(target, quad) or _inside(eye, quad):
            return True
        for i in range(4):
            if _segments_meet(eye, target, quad[i], quad[(i + 1) % 4]):
                return True
    return False
