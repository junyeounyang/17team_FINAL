"""평가의 특정 판을 다시 돌려 무슨 일이 있었는지 적는다 (예: '오래 멈춤' 으로 끝난 판의 원인 찾기).

    python replay_episode.py models/ppo_track.pt --seed 120 --episode 35

최종 평가(final_eval.py)와 같은 방법으로 seed 를 주고 1번째 판부터 차례로 돌린다 (한 시뮬레이션이 여러 판을 이어서 쓰므로
건너뛸 수 없다). 지정한 판에서는 스텝마다 AV 의 위치·속도·앞차·신호·관측·행동을 기록하고, 끝난 뒤 요약을
replay/seed<seed>_ep<판>.txt 에 쓴다. 판정용으로 시뮬레이터 값을 읽기만 한다.
"""
import argparse
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("model")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--episode", type=int, required=True, help="평가 로그에 찍힌 판 번호 (1부터)")
    a = p.parse_args()
    os.chdir(BASE)
    sys.path.insert(0, BASE)
    from env.mdp_config import SIMULATION, OBSERVATION, ACTION
    from env import daehakro_env
    from env.daehakro_env import DaehakroEnv
    from test import load_agent, REWARD
    tr = daehakro_env.traci
    model = a.model if os.path.isabs(a.model) else os.path.join(BASE, a.model)
    env = DaehakroEnv(daehakro_env.build(), None, None, SIMULATION, OBSERVATION, ACTION, REWARD)
    rows, out = [], []
    try:
        agent = load_agent(model, env.observation_space.shape[0], env.action_space.shape[0])
        np.random.seed(a.seed)
        for ep in range(1, a.episode + 1):
            obs, _ = env.reset()
            done, steps, info = False, 0, {}
            while not done:
                act = np.asarray(agent.predict(obs, deterministic=True), np.float32)
                if ep == a.episode:
                    r = {"t": steps, "obs": np.array(obs, np.float32), "act": act.copy()}
                    try:
                        e = env.ego_id
                        r["lane"], r["pos"], r["v"] = tr.vehicle.getLaneID(e), tr.vehicle.getLanePosition(e), tr.vehicle.getSpeed(e)
                        r["xy"] = tr.vehicle.getPosition(e)
                        ld = tr.vehicle.getLeader(e, 100.0)
                        if ld and ld[0]:
                            r["lead"] = (ld[0], round(ld[1], 1), tr.vehicle.getTypeID(ld[0]), round(tr.vehicle.getSpeed(ld[0]), 1),
                                         tr.vehicle.getStopState(ld[0]), tr.vehicle.getLaneID(ld[0]))
                        tls = tr.vehicle.getNextTLS(e)
                        if tls:
                            r["tls"] = (tls[0][0], round(tls[0][2], 1), tls[0][3])
                        near = []
                        x, y = r["xy"]
                        for v in tr.vehicle.getIDList():
                            if v == e:
                                continue
                            vx, vy = tr.vehicle.getPosition(v)
                            d = ((vx - x) ** 2 + (vy - y) ** 2) ** 0.5
                            if d < 15.0:
                                near.append((round(d, 1), v, tr.vehicle.getTypeID(v), tr.vehicle.getLaneID(v), round(tr.vehicle.getSpeed(v), 1)))
                        r["near"] = sorted(near)[:8]
                    except Exception as ex:
                        r["err"] = str(ex)
                    rows.append(r)
                obs, _, term, trunc, info = env.step(act)
                done = term or trunc
                steps += 1
                if ep == a.episode and rows:
                    rows[-1]["flags"] = [k for k in ("red_light", "crosswalk_violation", "yield_violation", "stuck", "collided", "arrived", "lane_changed")
                                         if info.get(k)]
            end = ("충돌" if info.get("collided") else "도착" if info.get("arrived") else "경로 이탈" if info.get("off_route")
                   else "오래 멈춤" if info.get("stuck") else "시간초과")
            print(f"  {ep:3d} | {steps:4d} 스텝 | {end}", flush=True)
            if ep == a.episode:
                out.append(f"seed {a.seed}, {ep}번째 판: {steps}스텝, 끝 = {end}")
    finally:
        env.close()

    # 마지막으로 멈춰 선 때
    stop = len(rows) - 1
    while stop > 0 and rows[stop - 1].get("v", 0.0) < 0.1:
        stop -= 1
    out.append(f"마지막으로 멈춰 선 스텝: {rows[stop]['t']} (끝까지 {len(rows) - stop}스텝 = {(len(rows) - stop) * 0.5:.0f}초 정지)")

    def show(r):
        o, ac = r["obs"], r["act"]
        s = [f"t={r['t']:4d} 속도 {r.get('v', 0) * 3.6:5.1f} km/h | 차로 {r.get('lane')} 위치 {r.get('pos', 0):6.1f} m | 행동 가감속 {ac[0]:+.2f} 차로 {ac[1]:+.0f} | 일어난 일 {r.get('flags')}",
             f"       앞차 {r.get('lead')} | 다음 신호 {r.get('tls')}",
             f"       관측: 내 차로 앞차 간격 {o[9]:+.2f} 상대속도 {o[10]:+.2f} | 차로 연결 [21..25] {np.round(o[21:26], 2).tolist()} | 신호 거리 {o[32]:+.2f} 빨강 {o[33]:.0f} 노랑 {o[34]:.0f} "
             f"| 횡단보도 거리 {o[35]:+.2f} 보행자 {o[36]:.0f} | 겹치는 차 {np.round(o[37:43], 2).tolist()} | 사이렌 {o[43]:.0f} 내 차로 {o[44]:.0f} | 버스차로 {o[45:48].astype(int).tolist()} | 신호 가림 {o[48]:.0f} 차로 모름 {o[49]:.0f}",
             f"       15 m 안의 차 (거리, id, 차종, 차로, 속도): {r.get('near')}"]
        return "\n".join(s)

    out.append("\n── 멈춰 서기 전 10초 (2초 간격)")
    for i in range(max(0, stop - 20), stop, 4):
        out.append(show(rows[i]))
    out.append("\n── 멈춰 선 뒤 (30초 간격)")
    for i in range(stop, len(rows), 60):
        out.append(show(rows[i]))
    out.append("\n── 마지막 스텝")
    out.append(show(rows[-1]))
    still = rows[stop:]
    acc = np.array([r["act"][0] for r in still])
    lane = np.array([abs(r["act"][1]) > 0.5 for r in still])
    out.append(f"\n정지해 있는 동안의 행동: 가속 명령(+0.1 초과) {np.mean(acc > 0.1):.0%}, 감속 명령(−0.1 미만) {np.mean(acc < -0.1):.0%}, 차로변경 명령 {np.mean(lane):.0%}")
    text = "\n".join(out)
    print("\n" + text)
    os.makedirs(os.path.join(BASE, "replay"), exist_ok=True)
    with open(os.path.join(BASE, "replay", f"seed{a.seed}_ep{a.episode}.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
