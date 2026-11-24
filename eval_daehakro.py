"""대학로 평가 — 학습된 모델(BC / PPO)을 여러 번 주행시켜 대학로용 지표를 센다.

test.py 는 충돌·완주·시간초과만 알려 준다. 대학로에서는 그것만으로는 부족해서
(끝까지 갔어도 빨간불을 지났을 수 있다) 아래를 함께 센다.

    끝난 이유   도착 / 차와 충돌 / 보행자와 충돌 / 경로 이탈 / 오래 멈춤(240초 넘게 서 있음) / 시간초과
                경로 이탈 = 차로를 제때 옮기지 못해, 경로로 이어지지 않는 차로의 끝을 지나치려 함
    위반        신호위반, 보행자 있는 횡단보도 진입, 양보 위반, 버스전용차로(실선) 통행, 실선 침범, 과속
                (건수와 '위반 없이 도착'한 비율. 과속은 제한속도를 1.8 km/h 넘게 넘은 스텝 수와 그런 에피소드 수)
                버스전용차로: 들어갈 때마다 1건 (사이렌 차를 비켜 주려고 들어간 것은 세지 않는다)
    차로변경    실제로 일어난 횟수. 모두 정책이 낸 차로변경 값으로 일어난 것인지도 확인한다
    실패 위치   도착하지 못한 에피소드가 끝난 도로 구간

사용:
    python eval_daehakro.py results/bc_1114_1530/model.pt --episodes 100
    python eval_daehakro.py                       ← 최근 모델, 30 에피소드
    python eval_daehakro.py --gui --episodes 3    ← 화면으로 보기
    python eval_daehakro.py --no-lane --episodes 10   ← 확인용: 정책의 차로변경 출력을 0 으로 막고 주행.
                                                     SUMO 가 대신 차로를 바꿔 주지 않으므로 로터리 입구에서 멈춰야 한다
    python eval_daehakro.py results/my_run/model.pt --loader my_loader.py --episodes 300 --seed 110
                                                  ← BC·PPO 가 아닌 형식의 모델. my_loader.py 에
                                                     load_agent(model_path, obs_dim, act_dim) 함수를 두고, 돌려주는 객체에
                                                     predict(obs, deterministic=True) → [가감속, 차로변경] 이 있으면 된다.
                                                     (이 파일·test.py 를 고치지 않고 평가하기 위한 옵션. 예: example_loader.py)
"""
import argparse
import collections
import os
import time

import numpy as np

from env.mdp_config import SIMULATION, OBSERVATION, ACTION
from env import daehakro_env
from env.daehakro_env import DaehakroEnv

BASE = os.path.dirname(os.path.abspath(__file__))
EVENTS = {"red_light": "신호위반", "crosswalk_violation": "횡단보도", "yield_violation": "양보",
          "bus_lane_violation": "버스전용차로", "solid_line_violation": "실선 침범"}


def evaluate(policy, env, episodes, seed=0, verbose=True, no_lane=False):
    """policy.predict(obs, deterministic=True) 로 episodes 번 주행한다. Returns: 요약 dict.

    no_lane=True 면 정책의 차로변경 출력을 0 으로 바꿔서 넘긴다 (확인용).
    """
    np.random.seed(seed)                      # 환경이 SUMO 시드를 여기서 뽑는다 → 같은 seed 면 같은 교통 상황
    ends, events, where = collections.Counter(), collections.Counter(), collections.Counter()
    returns, lengths, speeds, clean = [], [], [], 0
    lane_changes, lane_unasked = 0, 0
    speed_steps, speed_eps, bus_steps, total_steps = 0, 0, 0, 0
    t0 = time.time()
    for ep in range(episodes):
        obs, _ = env.reset()
        done, ret, steps, violated, lane = False, 0.0, 0, collections.Counter(), ""
        over = 0                              # 이 에피소드의 과속 스텝 수
        while not done:
            if env._snap is not None:
                lane = env._snap["lane"]
            action = policy.predict(obs, deterministic=True)
            if no_lane:
                action = np.array(action, dtype=np.float32)
                action[1] = 0.0
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            ret += reward
            steps += 1
            if info.get("speed") is not None:
                speeds.append(info["speed"])
            for key in EVENTS:
                if info[key]:
                    violated[key] += 1
            over += int(bool(info.get("speeding")))
            bus_steps += int(bool(info.get("bus_lane")))
            if info["lane_changed"]:
                lane_changes += 1
                # 정책이 그 방향으로 값을 내지 않았는데 차로가 바뀌었다면 환경이 잘못된 것이다 (0 이어야 한다)
                lane_unasked += int(info["lane_changed"] != info["lane_change"])
        if info["collided"]:
            on_foot = info.get("collision_type") in ("crossing", "walkingarea", "sharedLane") \
                or str(info.get("collision_with") or "").startswith("ped_")
            end = "보행자와 충돌" if on_foot else "차와 충돌"
        elif info["arrived"]:
            end = "도착"
        elif info["off_route"]:
            end = "경로 이탈"
        elif info["stuck"]:
            end = "오래 멈춤"
        else:
            end = "시간초과"
        ends[end] += 1
        events.update(violated)
        speed_steps, speed_eps, total_steps = speed_steps + over, speed_eps + int(over > 0), total_steps + steps
        clean += int(end == "도착" and not violated and not over)
        if end != "도착":
            where[lane.rsplit("_", 1)[0]] += 1
        returns.append(ret)
        lengths.append(steps)
        if verbose:
            note = ", ".join([f"{EVENTS[k]} {n}" for k, n in violated.items()] + ([f"과속 {over} 스텝"] if over else []))
            print(f"  {ep + 1:3d} | {steps:4d} 스텝 | {end:8s} | 보상 {ret:7.1f}" + (f" | 위반: {note}" if note else ""),
                  flush=True)
    return {"episodes": episodes, "ends": ends, "events": events, "where": where, "clean": clean,
            "lane_changes": lane_changes, "lane_unasked": lane_unasked,
            "speed_steps": speed_steps, "speed_episodes": speed_eps, "bus_steps": bus_steps, "steps": total_steps,
            "return": float(np.mean(returns)), "length": float(np.mean(lengths)),
            "speed": float(np.mean(speeds)) if speeds else 0.0, "seconds": time.time() - t0}


def report(r):
    n = r["episodes"]
    print(f"\n─── 대학로 주행 지표 ({n} 에피소드) ───")
    for end in ("도착", "차와 충돌", "보행자와 충돌", "경로 이탈", "오래 멈춤", "시간초과"):
        print(f"  {end:9s}: {r['ends'][end]:3d} 회 ({r['ends'][end] / n:.0%})")
    print(f"  위반 없이 도착: {r['clean']} 회 ({r['clean'] / n:.0%})")
    print("  위반 건수     : " + ", ".join(f"{label} {r['events'][key]}" for key, label in EVENTS.items()))
    print(f"  과속          : {r['speed_steps']} 스텝 (전체 스텝의 {r['speed_steps'] / max(r['steps'], 1):.1%}), "
          f"과속한 에피소드 {r['speed_episodes']} 회 ({r['speed_episodes'] / n:.0%})")
    print(f"  버스전용차로를 달린 스텝: {r['bus_steps']}")
    print(f"  차로변경      : {r['lane_changes']} 번 (에피소드당 {r['lane_changes'] / n:.1f} 번), "
          f"정책이 내지 않았는데 바뀐 경우 {r['lane_unasked']} 번")
    if r["where"]:
        print("  실패한 구간   : " + ", ".join(f"{k} {v}" for k, v in r["where"].most_common()))
    print(f"  평균 보상 {r['return']:.1f} | 평균 길이 {r['length']:.0f} 스텝 | 평균 속도 {r['speed'] * 3.6:.1f} km/h"
          f" | {r['seconds'] / 60:.1f} 분")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="대학로 평가 (BC / PPO 모델)")
    ap.add_argument("model", nargs="?", default=None, help="model.pt 경로 (생략 시 최근 모델)")
    ap.add_argument("--episodes", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0, help="같은 값이면 같은 교통 상황으로 평가한다 (모델끼리 비교할 때)")
    ap.add_argument("--gui", action="store_true", help="sumo-gui 로 보기")
    ap.add_argument("--no-lane", action="store_true",
                    help="확인용: 정책의 차로변경 출력을 0 으로 막고 주행한다 (SUMO 가 대신 바꿔 주지 않는지 볼 때)")
    ap.add_argument("--loader", default=None,
                    help="BC·PPO 가 아닌 형식의 모델일 때: load_agent(model_path, obs_dim, act_dim) 가 든 .py 파일")
    args = ap.parse_args()

    # 모델 불러오기는 test.py 의 것을 그대로 쓴다 (BC / PPO 자동 판별). --loader 가 있으면 그 파일의 것을 쓴다.
    from test import load_agent, find_latest_model, REWARD
    if args.loader:
        import importlib.util
        _spec = importlib.util.spec_from_file_location("custom_loader", os.path.abspath(args.loader))
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        load_agent = _mod.load_agent
        print(f"모델 불러오기: {args.loader} 의 load_agent")

    model_path = args.model or find_latest_model()
    if not os.path.isabs(model_path):
        model_path = os.path.join(BASE, model_path)
    print(f"모델: {model_path}")

    env = DaehakroEnv(daehakro_env.build(), None, None, SIMULATION, OBSERVATION, ACTION, REWARD, gui=args.gui)
    try:
        agent = load_agent(model_path, env.observation_space.shape[0], env.action_space.shape[0])
        result = evaluate(agent, env, args.episodes, seed=args.seed, no_lane=args.no_lane)
    finally:
        env.close()
    report(result)
