"""가려진 순간의 행동 — 평소 주행에서 무언가 가려진 스텝마다, 같은 순간에 가려지지 않았다면 냈을 행동과 견준다.

    python occ_moment.py models/ppo_track.pt --episodes 600
    python occ_moment.py models/ppo_track.pt models/bc_track.pt --episodes 300

주행은 평소 그대로다 (가림 켬, 정책은 가려진 관측으로 운전한다). 가려진 스텝에서만, 같은 시뮬레이션 상태에서
가림을 끄고 관측을 한 번 더 만들어 같은 정책에 넣어 본다. 그 행동은 기록만 하고 쓰지 않는다.
가려진 장면의 결과(위반·충돌)는 occ_report.py 와 같은 방법으로 센다.
결과는 화면과 occ_moment/<모델>.txt 에 쓴다.
"""
import argparse
import collections
import copy
import multiprocessing as mp
import os
import pickle
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
KINDS = (("sig_red", "신호가 가려져 있고 실제로는 빨강·노랑"), ("sig_green", "신호가 가려져 있고 실제로는 초록"),
         ("ped", "기다려야 할 보행자가 가려져 있음"), ("foe", "겹치는 차가 가려져 있음"),
         ("sir_unknown", "내 차로 뒤의 긴급차가 가려져 있고 기억 없음"), ("sir_memory", "내 차로 뒤의 긴급차가 가려져 있고 기억 있음"))
SIMPLE = (dict, list, set, tuple, collections.deque, np.ndarray, int, float, bool, str, type(None))


def job(args):
    model, seed, episodes = args
    os.chdir(BASE)
    sys.path.insert(0, BASE)
    from env import daehakro_env
    from env.daehakro_env import DaehakroEnv
    import occ_report
    envs, st = [], collections.Counter()
    init = DaehakroEnv.__init__

    def remember(self, *a, **k):
        init(self, *a, **k)
        envs.append(self)
    DaehakroEnv.__init__ = remember
    skip = set()

    def full_obs(env):
        """같은 순간, 가림이 없을 때의 관측. 환경의 상태는 그대로 되돌려 놓는다."""
        saved = {}
        for k, v in vars(env).items():
            if k in skip or not isinstance(v, SIMPLE):
                continue
            if k not in saved and isinstance(v, (dict, list, set, tuple, collections.deque, np.ndarray)):
                try:
                    if len(pickle.dumps(v)) > 200_000:      # 큰 표(지도 등)는 관측을 만들 때 바뀌지 않는다
                        skip.add(k)
                        continue
                except Exception:
                    skip.add(k)
                    continue
            saved[k] = copy.deepcopy(v)
        try:
            env.occlusion = False
            return np.array(env._get_obs(), np.float32)
        finally:
            for k, v in saved.items():
                setattr(env, k, v)

    load = occ_report.load_policy

    class Watch:
        def __init__(self, agent):
            self.agent = agent

        def predict(self, obs, deterministic=True):
            act = self.agent.predict(obs, deterministic=True)
            env = envs[-1]
            s = env._snap or {}
            tls, cw, sir = s.get("tls"), s.get("cw"), s.get("siren")
            kinds = []
            if tls and s.get("tls_hidden"):
                kinds.append("sig_red" if tls[2] in occ_report.RED else "sig_green")
            if cw and cw[2] and not s.get("cw_seen"):
                kinds.append("ped")
            if s.get("foe_hidden"):
                kinds.append("foe")
            if sir and sir[1] and sir[2]:
                kinds.append("sir_memory" if sir[3] else "sir_unknown")
            st["steps"] += 1
            if not kinds or not env.occlusion:
                return act
            try:
                act2 = self.agent.predict(full_obs(env), deterministic=True)
            except Exception:
                st["errors"] += 1
                return act
            a1, a2, l1, l2 = float(act[0]), float(act2[0]), abs(float(act[1])) > 0.5, abs(float(act2[1])) > 0.5
            try:
                v = daehakro_env.traci.vehicle.getSpeed(env.ego_id)
            except Exception:
                v = 0.0
            for k in kinds:
                st[k + "_n"] += 1
                st[k + "_a_occ"] += a1
                st[k + "_a_full"] += a2
                st[k + "_abs"] += abs(a1 - a2)
                st[k + "_differ"] += abs(a1 - a2) > 0.1 or l1 != l2
                st[k + "_brake_occ"] += a1 < -0.1
                st[k + "_brake_full"] += a2 < -0.1
                st[k + "_stop_or_slow"] += v < 2.0 or a1 < -0.1
                st[k + "_lane_occ"] += l1
                st[k + "_lane_full"] += l2
                st[k + "_v"] += v
            return act

    occ_report.load_policy = lambda *a, **k: Watch(load(*a, **k))
    c, sir = occ_report.job((model, seed, episodes, ()))
    return c, sir, dict(st)


def main():
    p = argparse.ArgumentParser(description="가려진 순간의 행동")
    p.add_argument("models", nargs="+")
    p.add_argument("--episodes", type=int, default=600)
    p.add_argument("--procs", type=int, default=8)
    p.add_argument("--seed", type=int, default=7000)
    a = p.parse_args()
    import occ_report
    out_dir = os.path.join(BASE, "occ_moment")
    os.makedirs(out_dir, exist_ok=True)
    procs = max(1, min(a.procs, a.episodes))
    share = [a.episodes // procs + (1 if i < a.episodes % procs else 0) for i in range(procs)]
    for model in a.models:
        path = model if os.path.isabs(model) else os.path.join(BASE, model)
        jobs = [(path, a.seed + i, n) for i, n in enumerate(share) if n > 0]
        print(f"{model}: {a.episodes}판을 SUMO {len(jobs)}개로 돌립니다", flush=True)
        c, sir, st = collections.Counter(), {"seen": [], "hidden": []}, collections.Counter()
        with mp.get_context("spawn").Pool(procs) as pool:
            for i, (ci, si, sti) in enumerate(pool.imap_unordered(job, jobs)):
                c.update(ci)
                st.update(sti)
                for k in sir:
                    sir[k] += si[k]
                print(f"   {i + 1}/{len(jobs)} 묶음 끝", flush=True)
        lines = [occ_report.report(model, c, sir), "",
                 "가려진 순간의 행동 (같은 순간, 가려진 관측에서 낸 행동 | 가려지지 않았다면 냈을 행동)",
                 f"   {'상황':<34s} {'스텝':>7s} {'가감속 평균':>14s} {'감속한 비율':>14s} {'차로변경 명령':>14s} {'행동이 달랐던 비율':>10s} {'AV 속도':>8s} {'멈춰 있거나 감속':>9s}"]
        for k, name in KINDS:
            n = st[k + "_n"]
            if not n:
                lines.append(f"   {name:<34s} {0:>7d}")
                continue
            lines.append(f"   {name:<34s} {n:>7d} {st[k + '_a_occ'] / n:>+6.2f} | {st[k + '_a_full'] / n:>+5.2f} "
                         f"{st[k + '_brake_occ'] / n:>6.0%} | {st[k + '_brake_full'] / n:>4.0%} "
                         f"{st[k + '_lane_occ'] / n:>6.1%} | {st[k + '_lane_full'] / n:>5.1%} "
                         f"{st[k + '_differ'] / n:>10.0%} {st[k + '_v'] / n * 3.6:>6.1f} km/h {st[k + '_stop_or_slow'] / n:>8.0%}")
        lines.append(f"   (전체 {st['steps']:,}스텝, 견주지 못한 스텝 {st['errors']})")
        text = "\n".join(lines)
        print("\n" + text + "\n", flush=True)
        name = os.path.splitext(os.path.basename(path))[0]
        with open(os.path.join(out_dir, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
