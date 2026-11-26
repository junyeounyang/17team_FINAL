"""사이렌 차 양보 진단 — 왜 비켜 주는 데 오래 걸리는가를 가른다.

    python siren_diag.py oracle expert results/bc_track_on_s0/model.pt results/ppo_track_on/last.pt --episodes 150 --procs 8

기준 운전자 둘과 모델을 같은 조건에서 견준다. 모델 파일은 평가 때와 같이 결정적으로 운전한다.
  oracle  모든 것을 아는 운전자. 사이렌 차가 가려져 있어도 실제 차로를 알고 비킨다 → '이 도로에서 낼 수 있는 값'
  expert  시범 운전자. AV 와 같은 것만 안다 (관측 [44] 에 보일 때만 비킨다) → '같은 정보로 낼 수 있는 값'
  (사이렌 관측을 고치기 전의 환경에서는 expert 가 곧 oracle 이다.)
잘 비키는가를 보는 지표
  · 비킬 수 있었는데 막은 시간: 비킬 차로가 있는 스텝인데도 사이렌 차 앞을 막고 있던 시간 (100판당 초). 작을수록 좋다
  · 5초 안에 비킨 비율: 비킬 차로가 생긴 구간 가운데, 생긴 뒤 5초 안에 내가 차로를 바꿔 끝낸 비율. 클수록 좋다
  · 괜히 옮긴 횟수: 사이렌 차가 내 차로가 아닌데 차로를 바꾼 횟수 (100판당). 작을수록 좋다

사이렌 차의 차로 앞을 막고 있는 구간(막는 구간)마다 다음을 본다.
  · 길이 (막기 시작해서 끝날 때까지)
  · 시작할 때 사이렌 차가 가려져 있었는가
  · 어떻게 끝났는가: 내가 차로를 바꿔서 / 그 밖 (사이렌 차가 차로를 바꿈·지나감·사라짐, 판이 끝남)
  · 그 구간에 '비켜 갈 차로가 있는 스텝'이 있었는가 (시범 운전자의 기준: 옆 차로가 차가 다니는 차로이고 실선이 아니며
    내 경로로 150 m 이상 이어짐. 차로 안내가 다른 차로를 가리키는 중이거나 교차로 안이면 없음)
결과는 화면과 siren_diag.txt 에 쓴다.
"""
import argparse
import collections
import multiprocessing as mp
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
MEMORY_WINDOW = 10.0      # s. '기억이 알려 줄 순간'을 세는 기준 (환경의 SIREN_MEMORY 와 같은 값)


def job(args):
    model, seed, episodes, no_memory = args
    os.chdir(BASE)
    sys.path.insert(0, BASE)
    try:
        from test import REWARD
    except ImportError:
        from env.mdp_config import REWARD
    from env.mdp_config import SIMULATION, OBSERVATION, ACTION
    from env import daehakro_env
    from env.daehakro_env import DaehakroEnv
    expert = model in ("expert", "oracle")
    if no_memory:                              # 기억 끄기: 가려지는 순간 잊는다 (모델·환경의 나머지는 그대로)
        daehakro_env.SIREN_MEMORY = -1.0
    if model == "oracle":                      # 시범 운전자가 실제 차로를 보고 비키게 한다 (가려져 있어도)
        daehakro_env._sir_mine = lambda sir: bool(sir[1])
    env = DaehakroEnv(daehakro_env.build(), None, None, SIMULATION, OBSERVATION, ACTION, REWARD, demo=expert)
    env.demo_noise = 0.0
    c = collections.Counter()
    runs = []                    # (스텝 수, 시작할 때 가려짐, 한 번이라도 가려짐, 내가 차로를 바꿔 끝남, 비킬 차로가 있던 스텝 수)
    try:
        agent = None
        if not expert:
            from occ_report import load_policy
            agent = load_policy(model, env.observation_space.shape[0], env.action_space.shape[0])
        np.random.seed(seed)
        for _ in range(episodes):
            obs, _ = env.reset()
            run, done, rem_run = None, False, None
            while not done:
                s = env._snap or {}
                sir = s.get("siren")
                if not sir:
                    state = "none"
                elif sir[1]:
                    state = "mine_hid" if sir[2] else "mine_seen"
                else:
                    state = "other_hid" if sir[2] else "other_seen"
                room = False
                if sir and sir[1] and s.get("lane"):
                    try:
                        room = env._yield_lane(dict(s, siren=(min(sir[0], 99.0), True, False))) != 0
                    except Exception:
                        room = False
                # '기억이 알려 줄 순간': 지금은 안 보이는데, 10초 안에 본 적이 있다. 환경의 기억을 꺼도 같은 기준으로 센다.
                rem = None
                mem = getattr(env, "_sir_mem", None)
                if sir and len(sir) > 2 and sir[2] and mem:
                    try:
                        fresh = daehakro_env.traci.simulation.getTime() - mem["t"] <= MEMORY_WINDOW
                    except Exception:
                        fresh = False
                    if fresh:
                        rem = "rem_mine" if mem["mine"] else "rem_other"
                rem_room = False
                if rem == "rem_mine" and s.get("lane"):
                    try:
                        rem_room = env._yield_lane(dict(s, siren=(min(sir[0], 99.0), True, False))) != 0
                    except Exception:
                        rem_room = False
                lane0 = s.get("lane")
                act = [0.0, 0.0] if expert else agent.predict(obs, deterministic=True)
                obs, _, term, trunc, info = env.step(act)
                done = term or trunc
                after = env._snap or {}
                lane1 = after.get("lane")
                moved = bool(lane0 and lane1 and lane0 != lane1 and lane0.rsplit("_", 1)[0] == lane1.rsplit("_", 1)[0])
                c["steps_" + state] += 1
                if sir and len(sir) > 4 and sir[2] and not sir[4]:      # 지금은 안 보이는데 기억으로 차로를 알고 있다
                    c["mem_steps"] += 1
                    c["mem_mine"] += bool(sir[3])
                    c["mem_right"] += bool(sir[3]) == bool(sir[1])
                c["moved_" + state] += moved
                cmd = (not expert) and abs(float(np.asarray(act).ravel()[1])) > 0.5
                c["cmd_" + state] += cmd
                if rem:
                    c["steps_" + rem] += 1
                    c["cmd_" + rem] += cmd
                    c["moved_" + rem] += moved
                    c["truth_" + rem] += bool(sir[1])
                    if rem_room:
                        c["steps_rem_room"] += 1
                        c["cmd_rem_room"] += cmd
                        c["moved_rem_room"] += moved
                # '내 차로 뒤'로 기억할 구간 (이어진 스텝 묶음): 그 안에서 내가 차로를 바꿨는가
                if rem == "rem_mine":
                    if rem_run is None:
                        rem_run = [0, False, False]
                    rem_run[0] += 1
                    rem_run[1] = rem_run[1] or moved
                    rem_run[2] = rem_run[2] or rem_room
                if rem_run is not None and (rem != "rem_mine" or done):
                    c["rem_runs"] += 1
                    c["rem_runs_moved"] += rem_run[1]
                    c["rem_runs_room"] += rem_run[2]
                    c["rem_runs_room_moved"] += rem_run[1] and rem_run[2]
                    rem_run = None
                if state.startswith("mine"):
                    if run is None:
                        run = [0, state == "mine_hid", False, False, 0, None]
                    run[0] += 1
                    run[2] = run[2] or state == "mine_hid"
                    run[4] += room
                    if room and run[5] is None:
                        run[5] = run[0]              # 비킬 차로가 처음 생긴 스텝
                    c["room_steps"] += room
                    still = bool(after.get("siren") and after["siren"][1]) and not done
                    if not still:
                        run[3] = moved
                        run[5] = None if run[5] is None else run[0] - run[5] + 1   # 비킬 차로가 생긴 뒤 끝날 때까지 스텝
                        runs.append(tuple(run))
                        run = None
            c["episodes"] += 1
            c["arrive"] += bool(info.get("arrived")) and not info.get("collided")
            c["crash"] += bool(info.get("collided"))
    finally:
        env.close()
    return dict(c), runs


def describe(model, c, runs):
    sec = lambda v: f"평균 {np.mean(v) * 0.5:4.1f}초, 가운데값 {np.median(v) * 0.5:4.1f}초, 10초 넘음 {sum(1 for x in v if x > 20):3d}번" if v else "-"
    out = [f"모델: {model}",
           f"{c['episodes']}판, 도착 {c['arrive']}, 충돌 {c['crash']} | 막는 구간 {len(runs)}번"]
    groups = (("전체", runs),
              ("시작할 때 보이던 것", [r for r in runs if not r[1]]),
              ("시작할 때 가려져 있던 것", [r for r in runs if r[1]]),
              ("비킬 차로가 있던 것", [r for r in runs if r[4] > 0]),
              ("   그중 시작할 때 보이던 것", [r for r in runs if r[4] > 0 and not r[1]]),
              ("   그중 시작할 때 가려져 있던 것", [r for r in runs if r[4] > 0 and r[1]]),
              ("비킬 차로가 한 번도 없던 것", [r for r in runs if r[4] == 0]))
    for name, g in groups:
        mine = sum(1 for r in g if r[3])
        out.append(f"   {name:<28s} {len(g):4d}번 | {sec([r[0] for r in g])} | 내가 차로를 바꿔 끝난 것 {mine:3d}번"
                   + (f" ({mine / len(g):.0%})" if g else ""))
    n = max(c["episodes"], 1)
    roomy = [r for r in runs if r[4] > 0]
    quick = sum(1 for r in roomy if r[3] and r[5] is not None and r[5] <= 10)
    out.append(f"   ▶ 비킬 수 있었는데 막은 시간   100판당 {c['room_steps'] * 0.5 / n * 100:6.1f}초")
    out.append(f"   ▶ 5초 안에 비킨 비율           {quick}/{len(roomy)}" + (f" ({quick / len(roomy):.0%})" if roomy else ""))
    out.append(f"   ▶ 괜히 옮긴 횟수               100판당 {(c['moved_other_seen'] + c['moved_other_hid']) / n * 100:6.1f}번")
    out.append(f"   ▶ 사이렌 차 앞을 막은 시간 전체 100판당 {(c['steps_mine_seen'] + c['steps_mine_hid']) * 0.5 / n * 100:6.1f}초")
    heard = sum(c["steps_" + k] for k in ("other_seen", "other_hid", "mine_seen", "mine_hid"))
    if c["mem_steps"]:
        out.append(f"   ▶ 기억이 쓰인 스텝              {c['mem_steps']:,} (사이렌이 들리는 스텝의 {c['mem_steps'] / max(heard, 1):.1%}) | "
                   f"그중 '내 차로'로 기억 {c['mem_mine']:,} | 기억이 실제와 같았던 비율 {c['mem_right'] / c['mem_steps']:.0%}")
    else:
        out.append("   ▶ 기억이 쓰인 스텝              0")
    pct = lambda a, b: f"{a / b:.1%}" if b else "-"
    out.append("   기억이 겨냥한 순간 — 방금까지 보이던 사이렌 차가 가려진 뒤 10초 (기억을 꺼도 같은 기준으로 센다)")
    m, o = c["steps_rem_mine"], c["steps_rem_other"]
    out.append(f"      '내 차로 뒤'였던 차   {m:6,d} 스텝 | 차로변경 명령 {pct(c['cmd_rem_mine'], m)} | 실제로 옮김 {pct(c['moved_rem_mine'], m)} | 실제로도 내 차로 뒤 {pct(c['truth_rem_mine'], m)}")
    out.append(f"         그중 비킬 차로가 있던 {c['steps_rem_room']:6,d} 스텝 | 차로변경 명령 {pct(c['cmd_rem_room'], c['steps_rem_room'])} | 실제로 옮김 {pct(c['moved_rem_room'], c['steps_rem_room'])}")
    out.append(f"         구간으로 세면 {c['rem_runs']}번 | 그 안에 스스로 차로를 바꾼 것 {c['rem_runs_moved']}번 ({pct(c['rem_runs_moved'], c['rem_runs'])}) | "
               f"비킬 차로가 있던 구간 {c['rem_runs_room']}번 중 {c['rem_runs_room_moved']}번 ({pct(c['rem_runs_room_moved'], c['rem_runs_room'])})")
    out.append(f"      '다른 차로'였던 차    {o:6,d} 스텝 | 차로변경 명령 {pct(c['cmd_rem_other'], o)} | 실제로 옮김 {pct(c['moved_rem_other'], o)}")
    out.append("   스텝마다 차로를 바꾼 비율 (괄호 안은 차로변경 명령을 낸 비율)")
    for key, name in (("none", "사이렌 없음"), ("other_seen", "사이렌 차가 다른 차로 (보임)"), ("other_hid", "사이렌 차가 다른 차로 (가려짐)"),
                      ("mine_seen", "사이렌 차가 내 차로 (보임)"), ("mine_hid", "사이렌 차가 내 차로 (가려짐)")):
        n = c["steps_" + key]
        if n:
            cmd = f" ({c['cmd_' + key] / n:.1%})" if model not in ("expert", "oracle") else ""
            out.append(f"      {name:<26s} {n:7,d} 스텝 | {c['moved_' + key] / n:6.2%}{cmd}")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description="사이렌 차 양보 진단")
    p.add_argument("models", nargs="+", help="'oracle' (다 아는 운전자), 'expert' (시범 운전자) 또는 모델 파일")
    p.add_argument("--episodes", type=int, default=150)
    p.add_argument("--procs", type=int, default=8)
    p.add_argument("--seed", type=int, default=3000)
    p.add_argument("--seeds", type=int, nargs="+", default=None,
                   help="최종 평가와 같은 방법: seed 마다 SUMO 하나, 각 --episodes 판 (예: --seeds 110 120 130 140 150 --episodes 300)")
    p.add_argument("--out", default="siren_diag.txt", help="결과 파일 이름")
    p.add_argument("--no-memory", action="store_true", help="사이렌 차의 차로 기억을 끄고 돌린다 (기억의 효과를 볼 때)")
    a = p.parse_args()
    if a.seeds:
        plan = [(s, a.episodes) for s in a.seeds]
        total = a.episodes * len(a.seeds)
    else:
        k = max(1, min(a.procs, a.episodes))
        plan = [(a.seed + i, a.episodes // k + (1 if i < a.episodes % k else 0)) for i in range(k)]
        total = a.episodes
    procs = max(1, min(a.procs, len(plan)))
    texts = []
    for model in a.models:
        path = model if model in ("expert", "oracle") or os.path.isabs(model) else os.path.join(BASE, model)
        print(f"{model}: {total}판을 SUMO {procs}개로 돌립니다", flush=True)
        c, runs = collections.Counter(), []
        with mp.get_context("spawn").Pool(procs) as pool:
            for i, (ci, ri) in enumerate(pool.imap_unordered(job, [(path, sd, n, a.no_memory) for sd, n in plan if n > 0])):
                c.update(ci)
                runs += ri
                print(f"   {i + 1}/{len(plan)} 묶음 끝", flush=True)
        texts.append(describe(model + (" (기억 끔)" if a.no_memory else ""), c, runs))
        print("\n" + texts[-1] + "\n", flush=True)
    with open(os.path.join(BASE, a.out), "w", encoding="utf-8") as f:
        f.write("\n\n".join(texts) + "\n")


if __name__ == "__main__":
    main()
