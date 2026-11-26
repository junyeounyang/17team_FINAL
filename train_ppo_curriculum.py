"""PPO 처음부터 (BC 없이) — 단계별 보상 일정(커리큘럼) + SUMO 여러 개 병렬 학습.

실행 (프로젝트 폴더에서):
    # 1) 5분짜리 동작 확인 (꼭 먼저)
    python train_ppo_curriculum.py --run smoke --workers 2 --total 16384 --n-steps 512 --eval-every 8192 --eval-episodes 1

    # 2) 본 학습 (SUMO 4개, 400만 스텝, 10만 스텝마다 seed 99 로 20판 평가)
    python train_ppo_curriculum.py --run ppo_cur1

    # 3) 끊겼을 때 이어서 (같은 --run 이름 + --resume)
    python train_ppo_curriculum.py --run ppo_cur1 --resume

결과 (results/<run>/):
    train_log.csv   업데이트마다: 단계, 벌점 배율, 최근 에피소드 도착·충돌·멈춤·위반, 학습 지표
    eval_log.csv    평가마다 (결정적 행동, 같은 seed): 도착·충돌·위반·위반 없이 도착 — 까먹는지 여기서 본다
    events.log      단계 전환, 배율 올림/되돌림, 최고 기록 갱신
    best.pt         평가 도착 수가 가장 많은 모델 (같으면 위반 없이 도착이 많은 것)
    ckpt_<스텝>.pt  평가한 모든 모델, last.pt / optimizer.pt / state.json (이어서 학습용)
    모델 파일은 train.py 의 PPO 와 같은 형식이라 eval_daehakro.py, test.py 로 그대로 평가·재생할 수 있다.

단계 (보상 일정):
    1 달리기        사고·위반 벌점 0.1배. 출발·가속·경로 차로 따라가기를 먼저 배운다.
    2 끝까지 가기    충돌·보행자 충돌·경로 이탈 벌점(에피소드가 끝나는 실패)을 0.1배씩 1배까지 올리고, 앞차 간격 감점을 강화한다.
    3 규칙 지키기    신호·횡단보도·양보 벌점을 0.1배씩 1배까지 올린다.
    4 굳히기        모든 보상을 최종값으로 고정하고 학습률을 낮춘다.
    한 번 켠 보상은 끄거나 줄이지 않는다 (앞 단계에서 배운 것을 잊지 않게).
    단, 벌점이 커져서 차가 얼어붙으면 (진행이 단계 시작 때의 절반 아래, 또는 오래 멈춤 25% 이상) 배율을 한 칸 되돌린다.

고친 내용 (v3, 11/20):
    · 배율을 올리는 기준을 '도착률'에서 '진행(거리)·오래 멈춤'으로 바꿨다. 학습 중 도착률이 0% 근처일 때는
      이전 기준(도착 10% 이상)으로는 배율이 영영 오르지 않아 2·3단계가 마감 스텝까지 멈춰 있게 된다.
      (진행은 거리라서 도착한 판일수록 크다. 차가 얼어붙으면 진행이 줄고 오래 멈춤이 는다.)
    · 경로 이탈 벌점을 2단계(충돌과 함께)로 옮겼다. 충돌 벌점만 20까지 오르고 이탈은 1로 남으면,
      위험한 순간에 '이탈로 끝내기'가 더 싼 선택이 되기 때문이다.
    · 1단계 → 2단계 진행 기준 15 → 9 (경로의 약 40%). 2·3단계는 배율 1에서 10만 스텝을 지내면 다음 단계로 간다.
    · 단계별 마감 스텝을 줄였다 (토요일까지 4단계에 충분한 시간을 남기려고).
    이전 기록(state.json)에서 --resume 으로 그대로 이어서 학습할 수 있다.

고친 내용 (v4, 11/20 아침):
    · 차로 안내 감점 0.05 → 0.15 (스텝당). 평가 실패의 대부분이 로터리 이탈이었는데, 다시 돌려 보니
      AV가 I 교차로부터 로터리까지 약 400 m를 3차로로 달리다가(안내는 4차로) 로터리 바로 앞 정체 줄에서야
      차로를 바꾸려 해서 실패했다. 0.05 는 진행 보상(스텝당 최대 0.1)에 비해 약해서 미리 옮길 이유가 되지 못했다.

고친 내용 (v5, 11/20 오후 — 목표 80~85%):
    · '필요한 만큼 밟지 않음' 감점 (BRAKE_SHAPING). 관측 [46](서야 할 곳)·[47](앞차)이 알려 주는 필요한 감속보다
      덜 밟으면 그만큼 감점한다. 120만 스텝 평가 재현에서 로터리 이탈은 '경로가 끊기는 차로 끝이 다가오는데도
      시속 50km까지 가속'해서 차로변경이 거절된 경우였다. 충돌은 대부분 앞차에 늦게 밟은 추돌이다.
    · 경로 이탈 벌점 10 → 20 (충돌과 같게).
    · 4단계 학습률을 5e-5 로 낮추지 않고 1e-4 로 유지 (새 보상을 배울 여유).

고친 내용 (v5b, 11/20 저녁):
    · '필요한 만큼 밟지 않음' 감점을 끈다 (BRAKE_SHAPING 0). v5 180만 스텝 모델을 4개 seed 로 평가하니 경로 이탈은
      16% → 10% 로 줄었지만 충돌이 11% → 26% 로 늘었다 (출발 직후 SZ_X 횡단보도 위에 멈춰 선 AV 에 보행자가 부딪힘,
      교차로 안 충돌). 경로 이탈 벌점 20 과 학습률 1e-4 는 그대로 둔다.
    · 이 판(ppo_cur2)은 v4 의 최고 모델(ppo_cur1/ckpt_1400832.pt, 4개 seed 평균 72.5%)에서 이어서 시작한다.

고친 내용 (v6, 11/20 밤):
    · '경로가 끊기는 차로 끝' 앞에서만 필요한 만큼 밟지 않으면 감점 (DEAD_BRAKE 0.3). v5 와 달리 신호·횡단보도·
      양보선·앞차에는 걸지 않는다. v5b 150만·160만 스텝 모델의 남은 실패 대부분이 로터리 arcN2 이탈이었다.

고친 내용 (v7, 11/21 새벽):
    · v6 감점을 끈다 (DEAD_BRAKE 0). 170만→180만→190만 스텝 4개 seed 평균 75→71→66%, 학습 중 이탈 23→33%.
      모든 '끊기는 차로 끝'(arcE_0~2, nb_O_I_4, U턴 차로 …)에 걸려서, 차로를 옮겨야 할 곳에서 브레이크를 밟게 됐다
      (190만 스텝에서 arcE 이탈이 새로 7번). 또 필요한 감속이 0.95 를 넘으면 감점이 꺼져 정작 마지막 순간엔 없었다.
    · 160만 스텝 모델의 실패 16판을 다시 돌려 보니 경로 이탈 13판 중 10판이 arcN2_1(12.8 m, 반드시 왼쪽으로
      옮겨야 하는 짧은 차로)이었다: 7판은 시속 42~50km 로 들어가 옆 차로 앞차 때문에 변경이 거절된 채 끝까지 감,
      3판은 차로 끝에 멈춘 뒤 가속 명령을 내서 끝을 넘으려다 이탈 처리.
    · 그래서 두 가지만, 좁게 건다 (환경·평가는 그대로, 학습 보상에만):
      ① 짧은 막힌 차로(SHORT_DEAD_LEN 이하, 이 경로에서는 arcN2_1·arcW1b_1·arcW1b_2 등)로 이어지는 차로에서
         끝까지 SHORT_ZONE 안으로 들어오면, 편안한 감속(최대의 SHORT_DECEL)으로 끝 앞에 설 수 있는 속도를 넘은 만큼 감점.
      ② 막힌 차로의 끝을 넘어가려 한 거리 1 m 당 OVERRUN_COST 감점 (환경은 이 거리가 1 m 를 넘으면 '경로 이탈'로 끝낸다).
    · 이 판(ppo_cur3)은 v5b 의 160만 스텝 모델(ppo_cur2/ckpt_1603584.pt, 4개 seed 평균 80%)에서 이어서 시작한다.

고친 내용 (v8, 11/21 아침):
    · v7 은 그대로 둔다 (250만 스텝: 8개 seed 160판 도착 92.5%, 경로 이탈 0). 남은 실패는 충돌 11판(6.9%)이고
      230만(10판)과 차이가 없다. 11판 모두 AV 가 박았다:
      - 6판: 합류 구간(nb_UBAY_A→A 교차로, 로터리 입구 J_NE_9)에 빠르게 들어가다 앞차·버스를 1~2 스텝 전에야
        알아채고 급제동 (그 전 '앞차 필요 감속' 은 0.1~0.2 로 낮았다)
      - 2판: 막힌 길에서 앞차에 1 m 안쪽까지 붙어 기어가다 추돌
      - 3판: 교차로 안 횡단보도(:M_4, :SZ_X)에 차 몸이 걸친 채 멈춰 있거나 기어가다 보행자와 부딪힘
    · 그래서 두 가지를 더한다 (환경·평가는 그대로, 학습 보상에만):
      ③ 앞차와의 충돌 예상 시간(TTC = 범퍼 사이 거리 ÷ 다가가는 속도)이 TTC_REF 초보다 짧으면
         TTC_COST × (1 − TTC/TTC_REF) 감점. 늦게 급제동하지 말고 미리 줄이도록.
      ④ 차 몸(앞범퍼부터 길이 4.6 m)이 횡단보도에 걸친 채 시속 CW_SLOW_KMH 아래로 멈춰 있거나 기어가면 CW_STOP_COST 감점.
    · 이 판(ppo_cur4)은 v7 의 250만 스텝 모델(ppo_cur3/ckpt_2500608.pt)에서 이어서 시작한다.
"""
import argparse
import csv
import json
import math
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time
from collections import deque

# torch·numpy 가 CPU 코어를 여러 개 붙잡고 돌면 SUMO 작업자들이 느려진다 → 계산 스레드는 1개만 (torch 를 불러오기 전에)
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)

# ══════════════════════════════ 보상 일정 설정 ══════════════════════════════
FULL = {                              # 최종 벌점 (env/daehakro_env.py REWARD 와 같은 값)
    "crash_penalty": 20.0, "crash_pedestrian_penalty": 40.0,
    "red_light_penalty": 15.0, "crosswalk_penalty": 10.0, "yield_penalty": 8.0,
    "solid_line_penalty": 3.0,        # 실선 침범 (환경이 막지 않고 감점한다)
    "off_route_penalty": 20.0,        # v5: 10 → 20 (충돌과 같게). 남은 실패의 가장 큰 몫이 로터리 경로 이탈이다
}
# v5: '필요한 만큼 밟지 않음' 감점 (보상 모양 잡기. 관측 [46] [47] 만 쓴다 — 정책이 보는 값과 같다)
#   need = max(관측[46] 서야 할 곳에 서려면 필요한 감속, 관측[47] 앞차에 닿지 않으려면 필요한 감속)  (최대 감속 4.5 m/s² = 1)
#   NEED_LO ≤ need ≤ NEED_HI 인 스텝에서, 정책의 가감속 값이 −need 보다 덜 밟은 만큼 BRAKE_SHAPING 배로 감점한다.
#   need > NEED_HI (이미 늦음) 이면 주지 않는다 — 그때는 충돌·위반 벌점이 맡는다.
#   40만 스텝 평가 재현: 로터리 이탈은 '멈춰야 할 곳(경로가 끊기는 차로 끝)이 다가오는데도 시속 50km까지 가속'해서
#   차로변경이 거절된 경우였고, 충돌 대부분은 서 있거나 느린 앞차에 늦게 브레이크를 밟은 추돌이었다.
BRAKE_SHAPING = 0.0                    # v5b: 끔 (v5 에서 0.3 — 충돌·보행자 충돌이 늘어서 되돌림)
NEED_LO, NEED_HI = 0.3, 0.95
I_STOP_NEED, I_CLOSE_NEED = 46, 47     # 관측에서의 위치 (env/daehakro_env.py 맨 위 관측 표. 관측 51차원 기준)


def brake_shortfall(prev_obs, accel_cmd):
    """감점할 '덜 밟은 양' (0 이상). prev_obs 는 이 행동을 고를 때 본 관측."""
    if prev_obs is None or BRAKE_SHAPING <= 0:
        return 0.0
    need = max(float(prev_obs[I_STOP_NEED]), float(prev_obs[I_CLOSE_NEED]))
    if not (NEED_LO <= need <= NEED_HI):
        return 0.0
    acc = min(max(float(accel_cmd), -1.0), 1.0)
    return max(0.0, acc + need)


# v6: '경로가 끊기는 차로 끝' 앞에서만 필요한 만큼 밟지 않으면 감점 (신호·횡단보도·양보선·앞차에는 주지 않는다)
#   v5 의 감점은 모든 '서야 할 곳'에 걸려서 횡단보도 위에서 서 버리는 버릇과 교차로 안 충돌을 키웠다.
#   남은 실패의 대부분(로터리 arcN2 이탈)은 '끊기는 차로 끝이 다가오는데 시속 50km까지 가속 → 차로변경 거절'이다.
#   필요한 감속은 환경 내부 상태(지금 차로가 경로에서 끊기는 곳까지의 거리, 내 속도)로 계산한다. 보상에만 쓴다.
DEAD_BRAKE = 0.0          # v7: 끔 (v6 에서 0.3)


def dead_end_need(env):
    """지금 상태에서 '경로가 끊기는 차로 끝' 앞에 서려면 필요한 감속 / 최대 감속 (0~1). 해당 없으면 0."""
    try:
        from env.daehakro_env import LANE_END_GAP
        st = env._snap
        if not st or st.get("reach") is None or st["reach"] > env.visibility:
            return 0.0
        return float(env._need(st["v"], st["reach"] - LANE_END_GAP))
    except Exception:
        return 0.0


def dead_end_shortfall(need, accel_cmd):
    if DEAD_BRAKE <= 0 or not (NEED_LO <= need <= NEED_HI):
        return 0.0
    acc = min(max(float(accel_cmd), -1.0), 1.0)
    return max(0.0, acc + need)
# v7: 짧은 '반드시 옮겨야 하는' 막힌 차로(arcN2_1 12.8 m 등) 앞에서만 과속 감점 + 막힌 차로 끝을 넘으려 하면 감점
SHORT_DEAD_LEN = 20.0     # m. 경로가 끊기는 차로 가운데 이보다 짧은 것만 (arcE_0~2 41 m, nb_O_I_4 32 m 는 빠진다)
SHORT_ZONE = 40.0         # m. 그 차로 끝까지 이만큼 남았을 때부터
SHORT_DECEL = 0.5         # 편안한 감속 = 최대 감속(4.5 m/s²) × 이 비율. 이 감속으로 끝 앞에 설 수 있는 속도까지는 괜찮다
SHORT_SPEED = 1.0         # 그 속도를 넘은 만큼 ÷ vmax 를 스텝마다 감점 (시속 50km, 끝까지 20 m 이면 스텝당 약 0.33)
OVERRUN_COST = 5.0        # 막힌 차로 끝을 넘어가려 한 거리 1 m 당 감점 (멈춘 채 가속 명령 0.8 이면 스텝당 약 2.6)


def short_dead_table(env):
    """이번 경로의 차로 → 차로변경 없이 따라가면 끝나는 '짧은 막힌 차로' (끝까지 이어지거나 긴 막힌 차로면 빠진다)."""
    m, route, reach = env.map, list(env._route), env._reach
    end, last = {}, len(route) - 1
    for i in range(last, -1, -1):
        for lane in m.lanes_of.get(route[i], ()):
            if lane not in reach:
                continue
            if i == last:
                end[lane] = None
                continue
            best, bv = None, -1.0
            for to, inside in m.links.get((lane, route[i + 1]), ()):
                if to in reach and inside + reach[to] > bv:
                    best, bv = to, inside + reach[to]
            end[lane] = end.get(best) if best is not None else lane
    return {k: e for k, e in end.items() if e is not None and m.length.get(e, 1e9) <= SHORT_DEAD_LEN}


def short_dead_speed_excess(env, table):
    """지금(스텝 뒤) 상태가 짧은 막힌 차로 끝 SHORT_ZONE 안이면 '편안히 설 수 있는 속도'를 넘은 만큼 ÷ vmax. 아니면 0."""
    try:
        from env.daehakro_env import LANE_END_GAP
        st = env._snap
        if not st or st.get("reach") is None or st["reach"] > SHORT_ZONE:
            return 0.0
        lane, hops = st["lane"], 0
        while lane and lane.startswith(":") and hops < 8:      # 교차로 안이면 이어질 차로로
            lane, hops = env.map._next.get(lane), hops + 1
        if not lane or lane not in table:
            return 0.0
        v_ok = math.sqrt(2.0 * SHORT_DECEL * env.max_decel * max(st["reach"] - LANE_END_GAP, 0.0))
        return max(0.0, st["v"] - v_ok) / env.vmax
    except Exception:
        return 0.0


# v8: ③ 충돌 예상 시간(TTC) 감점  ④ 횡단보도 위에 멈춰 있기 감점
TTC_REF = 3.0             # 초. 앞차와의 TTC 가 이보다 짧으면 감점 시작
TTC_COST = 0.5            # TTC 0 에 가까울 때 스텝당 최대 감점
TTC_MIN_CLOSE = 0.3       # m/s. 이보다 천천히 다가가면 TTC 를 따지지 않는다
CW_STOP_COST = 0.2        # 차 몸이 횡단보도에 걸친 채 느리게 있을 때 스텝당 감점 (멈춰 61초 서 있으면 약 24)
CW_SLOW_KMH = 5.0         # 이 속도 아래면 '멈춰 있거나 기어감'
AV_LENGTH = 4.6           # m
MIN_GAP = 2.5             # m. SUMO 의 앞차 간격 = 범퍼 사이 거리 − minGap


def ttc_penalty(env):
    """스텝 뒤 상태에서 앞차와의 TTC 감점 (0 이상). 앞차가 없거나 다가가지 않으면 0."""
    try:
        st = env._snap
        if not st or st.get("gap") is None:
            return 0.0
        close = float(st["v"]) - float(st.get("lead_v") or 0.0)
        if close < TTC_MIN_CLOSE:
            return 0.0
        dist = max(float(st["gap"]) + MIN_GAP, 0.0)          # 범퍼 사이 거리
        ttc = dist / close
        return TTC_COST * max(0.0, 1.0 - ttc / TTC_REF)
    except Exception:
        return 0.0


def crosswalk_stop_penalty(env):
    """스텝 뒤 상태에서 차 몸이 지금 차로의 횡단보도에 걸쳐 있고 느리면 CW_STOP_COST, 아니면 0."""
    try:
        st = env._snap
        if not st or st["v"] * 3.6 >= CW_SLOW_KMH:
            return 0.0
        front = float(st["pos"])
        rear = front - AV_LENGTH
        for p, _cid, _s, half in env.map.hits.get(st["lane"], ()):
            if p - half < front and p + half > rear:
                return CW_STOP_COST
        return 0.0
    except Exception:
        return 0.0


CRASH_KEYS = ("crash_penalty", "crash_pedestrian_penalty", "off_route_penalty")   # 2단계에서 올림 (에피소드가 끝나는 실패)
RULE_KEYS = ("red_light_penalty", "crosswalk_penalty", "yield_penalty", "solid_line_penalty")   # 3단계에서 올림
# 에 환경에 생긴 스텝당 감점 — 과속(speeding_penalty 0.3)·버스전용차로(bus_lane_penalty 0.3) — 은 환경 기본값을
# 처음부터 그대로 쓴다 (ALWAYS 에 적으면 값을 바꿀 수 있다). 환경이 속도·버스전용차로를 더는 막아 주지 않으므로,
# 이 감점이 없으면 보호구역에서 50 km/h 로 달리고 버스전용차로를 지름길로 쓰는 것을 배운다.
ALWAYS = {                            # 처음부터 끝까지 그대로 (기본값과 다른 것만)
    "lane_guide_penalty": 0.15,       # 경로가 이어지는 차로에 있지 않은 동안 스텝당 (옮겨야 하는 차로 수만큼). v4: 0.05 → 0.15
    "refused_lane_change_cost": 0.01, # 실행되지 않은 차로변경 명령 1회당 (마구 누르기 방지)
}
TAILGATE_1 = {"tailgate_penalty": 0.05, "tailgate_gap": 1.0}   # 1단계 (기본값)
TAILGATE_2 = {"tailgate_penalty": 0.10, "tailgate_gap": 2.0}   # 2단계부터: 서 있을 때 범퍼 사이 4.5 m 이상 유지 유도
START_SCALE, STEP_SCALE = 0.1, 0.1    # 벌점 배율 시작값, 한 번에 올리는 폭

# 단계 전환·배율 조절 기준 (학습 중 에피소드 = 확률적 행동 기준이라 평가보다 낮게 나온다)
WINDOW = 150                # 최근 이만큼의 에피소드로 판단 (마지막 변경 뒤의 에피소드만)
MIN_EPISODES = 40           # 판단에 필요한 최소 에피소드 수
P1_MIN_STEPS = 150_000      # 1단계 최소 스텝
P1_ARRIVE = 0.30            #   → 도착 30% 이상이거나
P1_PROGRESS = 9.0           #     진행 보상 합 평균 9 이상 (경로의 약 40%. 끝까지 가면 약 23)
RAMP_WAIT = 30_000          # 배율을 바꾼 뒤 다음 판단까지 최소 스텝
# 배율 올림·되돌림: '얼마나 멀리 가는가(진행)'와 '오래 멈춤'으로 본다 (벌점이 커져 얼어붙으면 진행이 줄고 멈춤이 는다)
RAMP_KEEP = 0.8             # 진행이 단계 시작 때의 80% 이상이고
STUCK_OK = 0.10             #   오래 멈춤이 10% 이하면 한 칸 올림
ROLLBACK = 0.5              # 진행이 단계 시작 때의 절반 아래이거나
STUCK_BAD = 0.25            #   오래 멈춤이 25% 이상이면 한 칸 되돌림 (되돌린 뒤에는 RAMP_WAIT 의 2배를 기다렸다 다시 올림)
P2_MIN_STEPS = 200_000
P2_CRASH = 0.15             # 2단계 → 3단계: 충돌·이탈 배율 1 이고, 충돌(차+보행자) 15% 이하이거나
P2_HOLD = 100_000           #   배율 1 로 이만큼 지냈으면
P3_MIN_STEPS = 300_000
P3_VIOL = 0.5               # 3단계 → 4단계: 두 배율 모두 1 이고, 에피소드당 위반 0.5건 이하이거나
P3_HOLD = 100_000           #   규칙 배율 1 로 이만큼 지냈으면
PHASE_MAX_STEPS = {1: 400_000, 2: 700_000, 3: 700_000}   # 이만큼 지나면 기준을 못 넘어도 다음 단계로 (마감용)
LR_PHASE4 = (1e-4, 1e-4, 500_000)   # 4단계 학습률. v5: 계속 1e-4 (v4 까지는 50만 스텝 뒤 5e-5 로 낮췄다 — 새 보상을 배울 여유를 둔다)
# ══════════════════════════════════════════════════════════════════════════

END_NAMES = ("arrived", "crash", "ped_crash", "stuck", "off_route", "timeout", "error")
END_KO = {"arrived": "도착", "crash": "차충돌", "ped_crash": "보행자", "stuck": "멈춤", "off_route": "이탈",
          "timeout": "시간초과", "error": "오류"}
VIOL_KEYS = ("red_light", "crosswalk_violation", "yield_violation", "bus_lane_violation", "solid_line_violation")


def stamp():
    return time.strftime("%m-%d %H:%M:%S")


# ───────────────────────────── 환경 작업자 (SUMO 1개) ─────────────────────────────
def env_worker(conn, wid, seed, sumocfg):
    """SUMO 하나를 맡아 명령대로 움직인다. 에피소드가 끝나면 스스로 reset 하고 요약을 함께 보낸다."""
    os.chdir(BASE)
    sys.path.insert(0, BASE)
    from env.mdp_config import SIMULATION, OBSERVATION, ACTION, REWARD
    from env.daehakro_env import DaehakroEnv

    np.random.seed((seed * 1000 + wid) % 2**32)          # 환경이 SUMO 시드를 여기서 뽑는다

    def make():
        return DaehakroEnv(sumocfg, None, None, SIMULATION, OBSERVATION, ACTION, REWARD, gui=False)

    env, overrides = make(), {}
    ep = None

    def fresh():
        return {"ret": 0.0, "len": 0, "progress": 0.0, "red_light": 0, "crosswalk_violation": 0,
                "yield_violation": 0, "bus_lane_violation": 0, "solid_line_violation": 0,
                "brake_short": 0.0, "short_excess": 0.0, "overrun": 0.0,
                "ttc_pen": 0.0, "cw_stop": 0.0}

    prev_obs = None                                       # 지금 행동을 고를 때 정책이 본 관측 (v5 감점용)
    sd_table = {}                                         # v7: 차로 → 짧은 막힌 차로 (에피소드마다)

    def reset():
        nonlocal ep, prev_obs, sd_table
        obs, _ = env.reset()
        ep = fresh()
        prev_obs = obs
        try:
            sd_table = short_dead_table(env) if (SHORT_SPEED > 0 or OVERRUN_COST > 0) else {}
        except Exception:
            sd_table = {}
        return obs

    try:
        while True:
            cmd, arg = conn.recv()
            if cmd == "reset":
                conn.send(reset())
            elif cmd == "set_reward":
                overrides = dict(arg)
                for k, v in overrides.items():
                    if k in env.drw:
                        env.drw[k] = float(v)
                conn.send({k: env.drw[k] for k in overrides if k in env.drw})
            elif cmd == "step":
                c0 = time.perf_counter()                  # 이 작업자가 실제로 계산한 시간 (기다린 시간 제외)
                dneed = dead_end_need(env) if DEAD_BRAKE > 0 else 0.0     # 행동을 고를 때의 상태 (v6)
                ov0 = getattr(env, "_overrun", (None, 0.0))                 # v7: 막힌 차로 끝을 넘으려 한 거리 (스텝 전)
                try:
                    obs, r, term, trunc, info = env.step(arg)
                except Exception as exc:                  # SUMO 가 죽는 등: 환경을 새로 만들고 이어 간다
                    try:
                        env.close()
                    except Exception:
                        pass
                    env = make()
                    for k, v in overrides.items():
                        if k in env.drw:
                            env.drw[k] = float(v)
                    summary = {**(ep or fresh()), "end": "error", "msg": repr(exc)[:200]}
                    o = reset()
                    conn.send((o, 0.0, False, True, None, summary, time.perf_counter() - c0))
                    continue
                short = brake_shortfall(prev_obs, arg[0])
                if short > 0.0:
                    r = float(r) - BRAKE_SHAPING * short
                    ep["brake_short"] += short
                dshort = dead_end_shortfall(dneed, arg[0])
                if dshort > 0.0:
                    r = float(r) - DEAD_BRAKE * dshort
                    ep["brake_short"] += dshort
                if SHORT_SPEED > 0 and sd_table:                          # v7 ①
                    excess = short_dead_speed_excess(env, sd_table)
                    if excess > 0.0:
                        r = float(r) - SHORT_SPEED * excess
                        ep["short_excess"] += excess
                if OVERRUN_COST > 0:                                       # v7 ②
                    ov1 = getattr(env, "_overrun", (None, 0.0))
                    push = ov1[1] - (ov0[1] if ov0[0] == ov1[0] else 0.0)
                    if push > 0.0:
                        r = float(r) - OVERRUN_COST * push
                        ep["overrun"] += push
                if not (term and info.get("collided")):                   # v8 ③④ (충돌한 스텝은 충돌 벌점만)
                    tp = ttc_penalty(env) if TTC_COST > 0 else 0.0
                    cp = crosswalk_stop_penalty(env) if CW_STOP_COST > 0 else 0.0
                    if tp > 0.0 or cp > 0.0:
                        r = float(r) - tp - cp
                        ep["ttc_pen"] += tp
                        ep["cw_stop"] += cp
                prev_obs = obs
                ep["ret"] += float(r)
                ep["len"] += 1
                ep["progress"] += float((info.get("reward_terms") or {}).get("progress", 0.0))
                for k in VIOL_KEYS:
                    ep[k] += int(bool(info.get(k)))
                if term or trunc:
                    if info.get("collided"):
                        on_foot = info.get("collision_type") in ("crossing", "walkingarea", "sharedLane") \
                            or str(info.get("collision_with") or "").startswith("ped_")
                        end = "ped_crash" if on_foot else "crash"
                    elif info.get("arrived"):
                        end = "arrived"
                    elif info.get("off_route"):
                        end = "off_route"
                    elif info.get("stuck"):
                        end = "stuck"
                    else:
                        end = "timeout"
                    summary = {**ep, "end": end}
                    o = reset()
                    conn.send((o, float(r), bool(term), bool(trunc), obs, summary, time.perf_counter() - c0))
                else:
                    conn.send((obs, float(r), False, False, None, None, time.perf_counter() - c0))
            elif cmd == "close":
                break
    finally:
        try:
            env.close()
        except Exception:
            pass
        conn.close()


class Workers:
    """SUMO 작업자 여러 개를 한꺼번에 움직인다 (모두 같은 스텝에 맞춰 진행)."""

    def __init__(self, n, seed, sumocfg):
        self.ctx = mp.get_context("spawn")
        self.n, self.seed, self.sumocfg = n, seed, sumocfg
        self.conns, self.procs = [None] * n, [None] * n
        for w in range(n):
            self._start(w)
        self.rewards = {}

    def _start(self, w):
        parent, child = self.ctx.Pipe()
        p = self.ctx.Process(target=env_worker, args=(child, w, self.seed, self.sumocfg), daemon=True)
        p.start()
        child.close()
        self.conns[w], self.procs[w] = parent, p

    def reset_all(self):
        for c in self.conns:
            c.send(("reset", None))
        return np.stack([np.asarray(c.recv(), dtype=np.float32) for c in self.conns])

    def set_rewards(self, rewards):
        self.rewards = dict(rewards)
        for c in self.conns:
            c.send(("set_reward", self.rewards))
        return [c.recv() for c in self.conns]

    def step(self, actions):
        for c, a in zip(self.conns, actions):
            c.send(("step", a))
        out = []
        for w, c in enumerate(self.conns):
            try:
                out.append(c.recv())
            except (EOFError, ConnectionError, BrokenPipeError):      # 작업자가 죽었다 → 새로 띄운다
                print(f"[{stamp()}] 작업자 {w} 가 멈춰서 새로 시작합니다", flush=True)
                self._start(w)
                self.conns[w].send(("set_reward", self.rewards))
                self.conns[w].recv()
                self.conns[w].send(("reset", None))
                obs = self.conns[w].recv()
                out.append((obs, 0.0, False, True, None, {"ret": 0.0, "len": 0, "progress": 0.0,
                                                          "red_light": 0, "crosswalk_violation": 0,
                                                          "yield_violation": 0, "end": "error"}, 0.0))
        return out

    def close(self):
        for c in self.conns:
            try:
                c.send(("close", None))
            except Exception:
                pass
        for p in self.procs:
            p.join(timeout=30)
            if p.is_alive():
                p.terminate()


# ───────────────────────────── 보상 일정 ─────────────────────────────
class Curriculum:
    def __init__(self, gate_scale=1.0):
        self.g = gate_scale                       # 시험용: 스텝 기준을 줄일 때만 1 보다 작게
        self.phase = 1
        self.s_crash = START_SCALE
        self.s_rules = START_SCALE
        self.phase_start = 0                      # 이 단계를 시작한 스텝
        self.last_change = 0                      # 배율·단계를 마지막으로 바꾼 스텝
        self.start_arrive = None                  # 이 단계를 시작할 때의 도착률
        self.start_progress = None                # 이 단계를 시작할 때의 진행 (배율 판단의 기준)
        self.last_rollback = None                 # 배율을 마지막으로 되돌린 스텝
        self.window = deque(maxlen=WINDOW)

    # 저장·복원
    def state(self):
        return {k: getattr(self, k) for k in ("phase", "s_crash", "s_rules", "phase_start", "last_change",
                                               "start_arrive", "start_progress", "last_rollback")}

    def load(self, st):
        for k, v in st.items():
            setattr(self, k, v)

    def rewards(self):
        r = dict(ALWAYS)
        r.update(TAILGATE_2 if self.phase >= 2 else TAILGATE_1)
        for k in CRASH_KEYS:
            r[k] = FULL[k] * self.s_crash
        for k in RULE_KEYS:
            r[k] = FULL[k] * self.s_rules
        return r

    def add(self, summary):
        self.window.append(summary)

    def stats(self):
        eps = list(self.window)
        n = len(eps)
        if n == 0:
            return {"n": 0}
        cnt = {e: sum(1 for s in eps if s["end"] == e) for e in END_NAMES}
        viol = sum(sum(s.get(k, 0) for k in VIOL_KEYS) for s in eps)
        return {"n": n, **{e: cnt[e] / n for e in END_NAMES},
                "viol": viol / n, "progress": float(np.mean([s["progress"] for s in eps])),
                "ret": float(np.mean([s["ret"] for s in eps])), "len": float(np.mean([s["len"] for s in eps]))}

    def _changed(self, steps):
        self.last_change = steps
        self.window.clear()                       # 바뀐 보상 아래에서 다시 판단

    def _ramp(self, attr, steps, st, msgs, label):
        """진행(거리)·오래 멈춤을 보고 배율을 한 칸 올리거나 되돌린다.
        되돌린 뒤에는 RAMP_WAIT 의 2배를 기다렸다가 다시 올린다 (얼어붙음 ↔ 회복을 빠르게 오가지 않게)."""
        cur = getattr(self, attr)
        if self.start_progress is None:           # v2 기록에서 이어 온 경우: 지금 값을 기준으로 삼는다
            self.start_progress = st["progress"]
        bp = self.start_progress
        down = st["progress"] < ROLLBACK * bp or st["stuck"] >= STUCK_BAD
        up = st["progress"] >= RAMP_KEEP * bp and st["stuck"] <= STUCK_OK \
            and steps - (self.last_rollback if self.last_rollback is not None else -10 ** 12) >= 2 * RAMP_WAIT * self.g
        how = f"진행 {st['progress']:.1f} (기준 {bp:.1f}), 멈춤 {st['stuck']:.0%}, 도착 {st['arrived']:.0%}"
        if down and cur > START_SCALE + 1e-9:
            setattr(self, attr, round(max(START_SCALE, cur - STEP_SCALE), 2))
            msgs.append(f"{label} 벌점 배율 되돌림 {cur:.1f} → {getattr(self, attr):.1f} ({how})")
            self.last_rollback = steps
            self._changed(steps)
        elif up and not down and cur < 1.0 - 1e-9:
            setattr(self, attr, round(min(1.0, cur + STEP_SCALE), 2))
            msgs.append(f"{label} 벌점 배율 {cur:.1f} → {getattr(self, attr):.1f} ({how})")
            self._changed(steps)

    def _next_phase(self, steps, st, msgs, why):
        self.phase += 1
        self.phase_start = steps
        self.start_arrive = st.get("arrived", 0.0)
        # 배율 판단 기준 진행: 지금 값과 앞 단계 기준 가운데 큰 값 (나쁜 순간에 넘어와도 기준이 낮아지지 않게).
        # 둘 다 없으면 None → 첫 판단 때 정한다
        self.start_progress = max(st.get("progress") or 0.0, self.start_progress or 0.0) or None
        msgs.append(f"── {self.phase}단계 시작 ({why}) — 시작 도착률 {self.start_arrive:.0%}"
                    + (f", 진행 {self.start_progress:.1f}" if self.start_progress is not None else ""))
        self._changed(steps)

    def update(self, steps):
        """스텝마다 한 번씩 불러서 단계·배율을 정한다. 바뀐 내용을 글로 돌려준다."""
        msgs = []
        st = self.stats()
        in_phase = steps - self.phase_start
        if st["n"] < MIN_EPISODES or steps - self.last_change < RAMP_WAIT * self.g:
            # 마감 기준은 에피소드 수와 상관없이 본다
            if self.phase in PHASE_MAX_STEPS and in_phase >= PHASE_MAX_STEPS[self.phase] * self.g:
                self._next_phase(steps, st if st["n"] else {"arrived": 0.0}, msgs, "시간 기준")
            return msgs
        if self.phase == 1:
            if in_phase >= P1_MIN_STEPS * self.g and (st["arrived"] >= P1_ARRIVE or st["progress"] >= P1_PROGRESS):
                self._next_phase(steps, st, msgs, f"도착 {st['arrived']:.0%}, 진행 {st['progress']:.1f}")
        elif self.phase == 2:
            full = self.s_crash >= 1.0 - 1e-9
            held = steps - self.last_change >= P2_HOLD * self.g        # 배율 1 로 지낸 스텝 (마지막 변경 뒤)
            crash = st["crash"] + st["ped_crash"]
            if full and ((in_phase >= P2_MIN_STEPS * self.g and crash <= P2_CRASH) or held):
                self._next_phase(steps, st, msgs, f"충돌 {crash:.0%}, 이탈 {st['off_route']:.0%}"
                                 + ("" if crash <= P2_CRASH else f", 배율 1 로 {P2_HOLD * self.g:,.0f} 스텝"))
            else:
                self._ramp("s_crash", steps, st, msgs, "충돌·이탈")
        elif self.phase == 3:
            full = self.s_crash >= 1.0 - 1e-9 and self.s_rules >= 1.0 - 1e-9
            held = steps - self.last_change >= P3_HOLD * self.g
            if full and ((in_phase >= P3_MIN_STEPS * self.g and st["viol"] <= P3_VIOL) or held):
                self._next_phase(steps, st, msgs, f"위반 {st['viol']:.2f}건/판"
                                 + ("" if st["viol"] <= P3_VIOL else f", 배율 1 로 {P3_HOLD * self.g:,.0f} 스텝"))
            elif self.s_crash < 1.0 - 1e-9:
                self._ramp("s_crash", steps, st, msgs, "충돌·이탈")
            else:
                self._ramp("s_rules", steps, st, msgs, "규칙")
        else:
            # 4단계: 마감 기준으로 넘어와 배율이 1 이 아니면 마저 올린다 (얼어붙으면 되돌림)
            if self.s_crash < 1.0 - 1e-9:
                self._ramp("s_crash", steps, st, msgs, "충돌·이탈")
            elif self.s_rules < 1.0 - 1e-9:
                self._ramp("s_rules", steps, st, msgs, "규칙")
        if not msgs and self.phase in PHASE_MAX_STEPS and in_phase >= PHASE_MAX_STEPS[self.phase] * self.g:
            self._next_phase(steps, st, msgs, "시간 기준")
        return msgs


# ───────────────────────────── 정책 (torch PPO / 시험용 무작위) ─────────────────────────────
class TorchLearner:
    """algorithms/ppo.py 의 PPO 를 그대로 쓰되, 여러 SUMO 의 경험으로 업데이트하고 KL 한도를 둔다."""

    def __init__(self, args, obs_dim, act_dim):
        import torch
        from torch import nn
        from algorithms.ppo import PPO
        from train import HPARAMS                 # 신경망 모양을 train.py 와 같게 (test.py 가 이걸로 불러온다)
        self.torch, self.nn = torch, nn
        hp = dict(HPARAMS)
        hp.update(lr=args.lr, n_steps=args.n_steps * args.workers, n_epochs=args.epochs,
                  minibatch_size=args.minibatch, lane_keep_bias=args.lane_keep_bias,
                  init_log_std=args.init_log_std, seed=args.seed, device="cpu")
        torch.set_num_threads(max(1, args.torch_threads))
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        self.agent = PPO(obs_dim=obs_dim, act_dim=act_dim, **hp)
        self.args = args

    def act(self, obs):
        torch = self.torch
        with torch.no_grad():
            a, logp, v = self.agent.policy.sample(torch.as_tensor(obs, dtype=torch.float32))
        return a.numpy().astype(np.float32), logp.numpy().astype(np.float32), v.numpy().astype(np.float32)

    def value(self, obs):
        torch = self.torch
        with torch.no_grad():
            return self.agent.policy(torch.as_tensor(obs, dtype=torch.float32))[-1].numpy().astype(np.float32)

    def set_lr(self, lr):
        for g in self.agent.optimizer.param_groups:
            g["lr"] = lr

    def update(self, obs, act, logp, adv, ret, target_kl):
        """PPO.update 와 같은 계산 + 에폭마다 KL 이 한도를 넘으면 멈춘다."""
        torch, nn, ag = self.torch, self.nn, self.agent
        dev = ag.device
        obs_t = torch.as_tensor(obs, dtype=torch.float32, device=dev)
        act_t = torch.as_tensor(act, dtype=torch.float32, device=dev)
        old_t = torch.as_tensor(logp, dtype=torch.float32, device=dev)
        adv_t = torch.as_tensor(adv, dtype=torch.float32, device=dev)
        ret_t = torch.as_tensor(ret, dtype=torch.float32, device=dev)
        if ag.normalize_advantage:
            adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)
        T = len(obs)
        idx = np.arange(T)
        st = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "approx_kl": 0.0, "clip_frac": 0.0}
        nb, epochs = 0, 0
        for _ in range(ag.n_epochs):
            np.random.shuffle(idx)
            kls = []
            for s in range(0, T, ag.minibatch_size):
                mb = idx[s:s + ag.minibatch_size]
                log_prob, entropy, value = ag.policy.evaluate_actions(obs_t[mb], act_t[mb])
                ratio = torch.exp(log_prob - old_t[mb])
                s1 = ratio * adv_t[mb]
                s2 = torch.clamp(ratio, 1 - ag.clip_eps, 1 + ag.clip_eps) * adv_t[mb]
                policy_loss = -torch.min(s1, s2).mean()
                value_loss = ((value - ret_t[mb]) ** 2).mean()
                loss = policy_loss + ag.value_coef * value_loss - ag.entropy_coef * entropy.mean()
                if ag.lane_entropy_coef > 0 and hasattr(ag.policy, "lane_entropy"):
                    loss = loss - ag.lane_entropy_coef * ag.policy.lane_entropy(obs_t[mb]).mean()
                ag.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(ag.policy.parameters(), ag.max_grad_norm)
                ag.optimizer.step()
                with torch.no_grad():
                    kl = (old_t[mb] - log_prob).mean().item()
                    cf = ((ratio - 1).abs() > ag.clip_eps).float().mean().item()
                st["policy_loss"] += policy_loss.item()
                st["value_loss"] += value_loss.item()
                st["entropy"] += entropy.mean().item()
                st["approx_kl"] += kl
                st["clip_frac"] += cf
                kls.append(kl)
                nb += 1
            epochs += 1
            if target_kl and np.mean(kls) > 1.5 * target_kl:
                break                                    # 정책이 한 번에 너무 많이 바뀌지 않게
        out = {k: v / max(nb, 1) for k, v in st.items()}
        out["epochs"] = epochs
        with torch.no_grad():
            ag.policy.log_std.clamp_(min=math.log(self.args.min_std))   # 탐험 폭 하한
            if hasattr(ag.policy, "lane_change_prob"):
                out["p_lane"] = float(ag.policy.lane_change_prob(obs_t).mean().item())
        out["std"] = float(ag.policy.current_std)
        return out

    def save(self, path, opt_path=None):
        self.torch.save(self.agent.policy.state_dict(), path)
        if opt_path:
            self.torch.save(self.agent.optimizer.state_dict(), opt_path)

    def load(self, path, opt_path=None):
        torch = self.torch
        self.agent.policy.load_state_dict(torch.load(path, map_location="cpu"))
        if opt_path and os.path.exists(opt_path):
            self.agent.optimizer.load_state_dict(torch.load(opt_path, map_location="cpu"))


class RandomLearner:
    """--dry: torch 없이 환경·보상 일정·기록만 점검할 때 쓰는 무작위 정책 (학습하지 않음)."""

    def __init__(self, args, obs_dim, act_dim):
        self.rng = np.random.default_rng(args.seed)

    def act(self, obs):
        n = len(obs)
        a = np.stack([np.clip(self.rng.normal(0.4, 0.5, n), -1, 1),
                      self.rng.choice([-1.0, 0.0, 1.0], n, p=[0.05, 0.9, 0.05])], axis=1).astype(np.float32)
        return a, np.zeros(n, np.float32), np.zeros(n, np.float32)

    def value(self, obs):
        return np.zeros(len(obs), np.float32)

    def set_lr(self, lr):
        pass

    def update(self, obs, act, logp, adv, ret, target_kl):
        return {"policy_loss": 0.0, "value_loss": float(np.mean(ret ** 2)), "entropy": 0.0, "approx_kl": 0.0,
                "clip_frac": 0.0, "epochs": 0, "p_lane": 0.1, "std": 0.5}

    def save(self, path, opt_path=None):
        with open(path, "w") as f:
            f.write("dry")

    def load(self, path, opt_path=None):
        pass


# ───────────────────────────── GAE ─────────────────────────────
def gae(rew, val, ended, last_val, gamma, lam):
    """[T, N] 배열. ended = 이 스텝에서 에피소드가 끝남(도착·충돌·멈춤·시간초과 모두). 끝난 뒤로는 이어 붙이지 않는다."""
    T, N = rew.shape
    adv = np.zeros((T, N), np.float32)
    g = np.zeros(N, np.float32)
    for t in reversed(range(T)):
        nv = last_val if t == T - 1 else val[t + 1]
        nonterm = 1.0 - ended[t]
        delta = rew[t] + gamma * nv * nonterm - val[t]
        g = delta + gamma * lam * nonterm * g
        adv[t] = g
    return adv, adv + val


# ───────────────────────────── 평가 (별도 프로세스) ─────────────────────────────
class Evaluator:
    """체크포인트를 run_all_BC.py --job 으로 평가한다 (eval_daehakro.py 와 같은 방법). 학습은 멈추지 않는다."""

    def __init__(self, run_dir, seed, episodes):
        self.run_dir, self.seed, self.episodes = run_dir, seed, episodes
        self.proc, self.cur = None, None
        self.path = os.path.join(run_dir, "eval_log.csv")

    def busy(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, ckpt, steps, phase):
        out_json = os.path.join(self.run_dir, f"eval_{steps}.json")
        log = open(os.path.join(self.run_dir, f"eval_{steps}.txt"), "w", encoding="utf-8")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        self.proc = subprocess.Popen([sys.executable, os.path.join(BASE, "run_all_BC.py"), "--job", ckpt,
                                      str(self.seed), str(self.episodes), out_json],
                                     cwd=BASE, stdout=log, stderr=subprocess.STDOUT, env=env)
        self.cur = (ckpt, steps, phase, out_json, log)

    def poll(self):
        """끝난 평가가 있으면 결과 dict 를 돌려준다."""
        if self.proc is None or self.proc.poll() is None:
            return None
        ckpt, steps, phase, out_json, log = self.cur
        log.close()
        self.proc, self.cur = None, None
        if not os.path.exists(out_json):
            return {"steps": steps, "phase": phase, "ckpt": ckpt, "failed": True}
        with open(out_json, encoding="utf-8") as f:
            r = json.load(f)
        ends, ev, n = r.get("ends", {}), r.get("events", {}), r.get("episodes", 1)
        row = {"steps": steps, "phase": phase, "episodes": n,
               "arrive": ends.get("도착", 0) / n, "clean": r.get("clean", 0) / n,
               "crash": ends.get("차와 충돌", 0) / n, "ped_crash": ends.get("보행자와 충돌", 0) / n,
               "stuck": ends.get("오래 멈춤", 0) / n, "off_route": ends.get("경로 이탈", 0) / n,
               "timeout": ends.get("시간초과", 0) / n,
               "red": ev.get("red_light", 0) / n, "crosswalk": ev.get("crosswalk_violation", 0) / n,
               "yield": ev.get("yield_violation", 0) / n,
               "bus_lane": ev.get("bus_lane_violation", 0) / n, "solid_line": ev.get("solid_line_violation", 0) / n,
               "speeding_eps": r.get("speed_episodes", 0) / n, "speed": r.get("speed", 0.0),
               "return": r.get("return", 0.0), "length": r.get("length", 0.0), "ckpt": os.path.basename(ckpt)}
        new = not os.path.exists(self.path)
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row))
            if new:
                w.writeheader()
            w.writerow(row)
        return row

    def wait(self, timeout):
        if self.proc is not None:
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        return self.poll()


# ───────────────────────────── 메인 ─────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="PPO 처음부터 — 단계별 보상 일정 + SUMO 병렬")
    ap.add_argument("--run", default=time.strftime("ppo_cur_%m%d_%H%M"), help="results/ 아래 폴더 이름")
    ap.add_argument("--resume", action="store_true", help="같은 --run 폴더에서 이어서 학습")
    ap.add_argument("--workers", type=int, default=4, help="동시에 돌릴 SUMO 수 (코어 수 - 3 이하 권장)")
    ap.add_argument("--total", type=int, default=4_000_000, help="총 학습 스텝")
    ap.add_argument("--n-steps", type=int, default=1024, help="업데이트 1번에 SUMO 하나가 모으는 스텝")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--minibatch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=2e-4, help="1~3단계 학습률 (4단계는 자동으로 낮춤)")
    ap.add_argument("--gamma", type=float, default=0.99)
    ap.add_argument("--lam", type=float, default=0.95)
    ap.add_argument("--target-kl", type=float, default=0.02, help="업데이트 1번에 정책이 바뀌는 폭 한도")
    ap.add_argument("--init-log-std", type=float, default=-0.5, help="가감속 탐험 폭 σ = e^값")
    ap.add_argument("--min-std", type=float, default=0.10, help="가감속 탐험 폭 하한")
    ap.add_argument("--lane-keep-bias", type=float, default=1.0, help="처음 차로 '유지' 쪽 편향 (1.0 → 변경 시도 약 32%%)")
    ap.add_argument("--eval-every", type=int, default=100_000)
    ap.add_argument("--eval-episodes", type=int, default=20)
    ap.add_argument("--eval-seed", type=int, default=99)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--torch-threads", type=int, default=1, help="학습 프로세스의 torch 계산 스레드 수")
    ap.add_argument("--dry", action="store_true", help=argparse.SUPPRESS)        # torch 없이 점검
    ap.add_argument("--gate-scale", type=float, default=1.0, help=argparse.SUPPRESS)
    args = ap.parse_args()

    from env import daehakro_env
    from env.mdp_config import OBSERVATION  # noqa: F401  (환경 설정을 읽어 둔다)

    run_dir = os.path.join(BASE, "results", args.run)
    if os.path.exists(os.path.join(run_dir, "state.json")) and not args.resume:
        sys.exit(f"{run_dir} 에 이미 학습 기록이 있습니다. 이어서 하려면 --resume, 새로 하려면 다른 --run 이름을 쓰세요.")
    os.makedirs(run_dir, exist_ok=True)
    shutil.copy(os.path.abspath(__file__), os.path.join(run_dir, os.path.basename(__file__)))
    events = open(os.path.join(run_dir, "events.log"), "a", encoding="utf-8")

    def note(msg):
        line = f"[{stamp()}] {msg}"
        print(line, flush=True)
        events.write(line + "\n")
        events.flush()

    sumocfg = daehakro_env.build()            # 도로 파일 확인 (필요할 때만 다시 만든다) — 작업자보다 먼저 한 번
    cur = Curriculum(gate_scale=args.gate_scale)
    steps, updates, best, resumed = 0, 0, None, 0
    state_path = os.path.join(run_dir, "state.json")
    if args.resume and os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as f:
            saved = json.load(f)
        steps, updates, best = saved["steps"], saved["updates"], saved.get("best")
        resumed = saved.get("resumed", 0) + 1
        cur.load(saved["curriculum"])

    # 작업자 (이어서 할 때는 다른 시드로 → 같은 교통을 되풀이하지 않게)
    seed = args.seed + 7919 * resumed
    workers = Workers(args.workers, seed, sumocfg)
    obs = workers.reset_all()
    obs_dim, act_dim = obs.shape[1], 2

    learner = (RandomLearner if args.dry else TorchLearner)(args, obs_dim, act_dim)
    if resumed:
        if os.path.exists(os.path.join(run_dir, "last.pt")) and not args.dry:
            learner.load(os.path.join(run_dir, "last.pt"), os.path.join(run_dir, "optimizer.pt"))
        note(f"이어서 학습: {steps:,} 스텝, {cur.phase}단계, 충돌 배율 {cur.s_crash:.1f}, 규칙 배율 {cur.s_rules:.1f}")
    else:
        note(f"새로 학습: SUMO {args.workers}개, 총 {args.total:,} 스텝, 업데이트당 {args.n_steps * args.workers:,} 스텝")
    applied = workers.set_rewards(cur.rewards())
    note(f"보상: {cur.phase}단계 {json.dumps(applied[0], ensure_ascii=False)}")

    evaluator = None if args.dry else Evaluator(run_dir, args.eval_seed, args.eval_episodes)
    next_eval = (steps // args.eval_every + 1) * args.eval_every
    train_csv = os.path.join(run_dir, "train_log.csv")
    fields = ["time", "steps", "update", "phase", "s_crash", "s_rules", "lr", "n_ep", "arrive", "crash", "ped_crash",
              "stuck", "off_route", "timeout", "error", "viol", "progress", "ret", "len", "std", "p_lane",
              "approx_kl", "clip_frac", "epochs", "value_loss", "entropy", "sps",
              "t_env", "t_busy_mean", "t_busy_max", "t_act", "t_upd"]
    new_csv = not os.path.exists(train_csv)
    fcsv = open(train_csv, "a", newline="", encoding="utf-8")
    wcsv = csv.DictWriter(fcsv, fieldnames=fields)
    if new_csv:
        wcsv.writeheader()

    T, N = args.n_steps, args.workers
    D = obs_dim
    buf_obs = np.zeros((T, N, D), np.float32)
    buf_act = np.zeros((T, N, 2), np.float32)
    buf_logp = np.zeros((T, N), np.float32)
    buf_val = np.zeros((T, N), np.float32)
    buf_rew = np.zeros((T, N), np.float32)
    buf_end = np.zeros((T, N), np.float32)

    def save_state():
        learner.save(os.path.join(run_dir, "last.pt"), os.path.join(run_dir, "optimizer.pt"))
        with open(state_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"steps": steps, "updates": updates, "best": best, "resumed": resumed,
                       "curriculum": cur.state(), "args": vars(args)}, f, ensure_ascii=False, indent=1)
        os.replace(state_path + ".tmp", state_path)

    def handle_eval(row):
        nonlocal best
        if row is None:
            return
        if row.get("failed"):
            note(f"평가 실패 ({row['steps']:,} 스텝) — eval_{row['steps']}.txt 확인")
            return
        note(f"평가 {row['steps']:,} 스텝 ({row['phase']}단계): 도착 {row['arrive']:.0%}, 위반 없이 도착 {row['clean']:.0%}, "
             f"충돌 {row['crash'] + row['ped_crash']:.0%}, 멈춤 {row['stuck']:.0%}, 이탈 {row['off_route']:.0%}, "
             f"위반/판 신호 {row['red']:.2f} 횡단 {row['crosswalk']:.2f} 양보 {row['yield']:.2f} "
             f"버스차로 {row.get('bus_lane', 0):.2f} 실선 {row.get('solid_line', 0):.2f}, 과속한 판 {row.get('speeding_eps', 0):.0%}")
        key = (row["arrive"], row["clean"], -(row["crash"] + row["ped_crash"]))
        if best is None or key > tuple(best["key"]):
            best = {"key": list(key), "steps": row["steps"], "ckpt": row["ckpt"], "arrive": row["arrive"],
                    "clean": row["clean"]}
            shutil.copy(os.path.join(run_dir, row["ckpt"]), os.path.join(run_dir, "best.pt"))
            note(f"★ 최고 기록 갱신: {row['ckpt']} (도착 {row['arrive']:.0%}, 위반 없이 {row['clean']:.0%}) → best.pt")

    t_last, s_last, sps_avg = time.time(), steps, None
    try:
        while steps < args.total:
            # 학습률: 1~3단계 고정, 4단계에서 낮춤
            if cur.phase >= 4:
                lr = LR_PHASE4[0] if steps - cur.phase_start < LR_PHASE4[2] else LR_PHASE4[1]
            else:
                lr = args.lr
            learner.set_lr(lr)

            # 1) 경험 모으기 (SUMO N개를 같은 스텝에 맞춰)
            t_env = t_act = 0.0
            busy = np.zeros(N)
            for t in range(T):
                c0 = time.perf_counter()
                act, logp, val = learner.act(obs)
                c1 = time.perf_counter()
                res = workers.step(act)
                c2 = time.perf_counter()
                t_act += c1 - c0
                t_env += c2 - c1
                buf_obs[t], buf_act[t], buf_logp[t], buf_val[t] = obs, act, logp, val
                nxt = np.empty_like(obs)
                for w, (o, r, term, trunc, final_obs, summary, dt) in enumerate(res):
                    nxt[w] = o
                    busy[w] += dt
                    if trunc and not term and final_obs is not None:
                        r += args.gamma * float(learner.value(np.asarray(final_obs, np.float32)[None])[0])   # 잘린 에피소드는 이어질 가치를 더한다
                    buf_rew[t, w] = r
                    buf_end[t, w] = float(term or trunc)
                    if summary is not None:
                        cur.add(summary)
                        if summary["end"] == "error":
                            note(f"작업자 {w} 환경 오류로 에피소드를 다시 시작: {summary.get('msg', '')}")
                obs = nxt
            steps += T * N
            last_val = learner.value(obs)
            adv, ret = gae(buf_rew, buf_val, buf_end, last_val, args.gamma, args.lam)

            # 2) 업데이트
            c3 = time.perf_counter()
            info = learner.update(buf_obs.reshape(T * N, D), buf_act.reshape(T * N, 2), buf_logp.reshape(-1),
                                  adv.reshape(-1), ret.reshape(-1), args.target_kl)
            t_upd = time.perf_counter() - c3
            updates += 1

            # 3) 기록
            st = cur.stats()
            now = time.time()
            sps = (steps - s_last) / max(now - t_last, 1e-6)
            t_last, s_last = now, steps
            sps_avg = sps if sps_avg is None else 0.9 * sps_avg + 0.1 * sps
            eta_h = (args.total - steps) / max(sps_avg, 1e-6) / 3600
            row = {"time": stamp(), "steps": steps, "update": updates, "phase": cur.phase,
                   "s_crash": cur.s_crash, "s_rules": cur.s_rules, "lr": lr, "n_ep": st.get("n", 0),
                   **{k: round(st.get(k, 0.0), 4) for k in END_NAMES},
                   "viol": round(st.get("viol", 0.0), 3), "progress": round(st.get("progress", 0.0), 2),
                   "ret": round(st.get("ret", 0.0), 2), "len": round(st.get("len", 0.0), 1),
                   "std": round(info.get("std", 0.0), 3), "p_lane": round(info.get("p_lane", 0.0), 3),
                   "approx_kl": round(info["approx_kl"], 4), "clip_frac": round(info["clip_frac"], 3),
                   "epochs": info["epochs"], "value_loss": round(info["value_loss"], 3),
                   "entropy": round(info["entropy"], 3), "sps": round(sps, 1),
                   "t_env": round(t_env, 1), "t_busy_mean": round(float(busy.mean()), 1),
                   "t_busy_max": round(float(busy.max()), 1), "t_act": round(t_act, 2), "t_upd": round(t_upd, 2)}
            row["arrive"] = row.pop("arrived")
            wcsv.writerow(row)
            fcsv.flush()
            if st.get("n", 0):
                print(f"[{stamp()}] {steps:>9,} 스텝 | {cur.phase}단계 충돌·이탈×{cur.s_crash:.1f} 규칙×{cur.s_rules:.1f} | "
                      f"최근 {st['n']}판: 도착 {st['arrived']:.0%} 충돌 {st['crash'] + st['ped_crash']:.0%} "
                      f"멈춤 {st['stuck']:.0%} 이탈 {st['off_route']:.0%} 위반 {st['viol']:.2f}/판 진행 {st['progress']:.1f} | "
                      f"σ {info.get('std', 0):.2f} 차로 {info.get('p_lane', 0):.2f} kl {info['approx_kl']:.3f}"
                      f"({info['epochs']}) | {sps:.0f} 스텝/s, 남은 시간 약 {eta_h:.1f}시간", flush=True)
            else:
                print(f"[{stamp()}] {steps:>9,} 스텝 | {cur.phase}단계 | 아직 끝난 에피소드 없음 | {sps:.0f} 스텝/s", flush=True)
            print(f"           시간: SUMO 대기 {t_env:.0f}초 (작업자 계산 평균 {busy.mean():.0f}초, 최대 {busy.max():.0f}초) | "
                  f"추론 {t_act:.1f}초 | 업데이트 {t_upd:.1f}초", flush=True)

            # 4) 보상 일정
            msgs = cur.update(steps)
            if msgs:
                for m in msgs:
                    note(m)
                applied = workers.set_rewards(cur.rewards())
                note(f"보상: {cur.phase}단계 {json.dumps(applied[0], ensure_ascii=False)}")

            # 5) 평가 (따로 돌고, 끝나면 기록)
            if evaluator is not None:
                handle_eval(evaluator.poll())
                if steps >= next_eval:
                    ckpt = os.path.join(run_dir, f"ckpt_{steps}.pt")
                    learner.save(ckpt)
                    if evaluator.busy():
                        note(f"이전 평가가 아직 진행 중이라 {steps:,} 스텝 평가는 건너뜀 (모델은 {os.path.basename(ckpt)} 로 저장)")
                    else:
                        evaluator.start(ckpt, steps, cur.phase)
                    next_eval = (steps // args.eval_every + 1) * args.eval_every
                    save_state()
            elif steps >= next_eval:
                next_eval = (steps // args.eval_every + 1) * args.eval_every
                save_state()
    except KeyboardInterrupt:
        note("Ctrl+C — 저장하고 끝냅니다")
    finally:
        save_state()
        workers.close()
        fcsv.close()
        if evaluator is not None and evaluator.busy():
            note("진행 중인 평가가 끝나기를 기다립니다 (최대 30분)")
            handle_eval(evaluator.wait(1800))
        note(f"끝: {steps:,} 스텝, {cur.phase}단계. 최고 기록: {best}")
        events.close()


if __name__ == "__main__":
    main()
