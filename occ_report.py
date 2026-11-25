"""가림 장면 집계 — 버스·소방차에 가려진 장면에서 모델이 얼마나 틀리는지 센다.

도착률 전체로는 가림의 영향이 잘 보이지 않는다 (가림은 전체 스텝의 몇 % 뿐이다). 그래서 장면을 나눠서 센다:
    신호      빨강·노랑이던 신호를 지나간 횟수 → 그중 신호위반.   직전 3초 안에 신호가 '가려져 있던' 통과와 '보이던' 통과를 따로
    횡단보도  기다려야 할 보행자가 있던 횡단보도를 지나간 횟수 → 그중 횡단보도 위반·보행자 충돌.   보행자가 '가려져 있던' / '보이던'
    양보      양보 위반 횟수.   직전 3초 안에 가려진 양보 대상이 있었는가
    사이렌    사이렌 차가 내 차로 뒤에 온 횟수 → 비켜 줄 때까지 걸린 시간.   그 차가 '가려져 있던' / '보이던'
    충돌      차·보행자 충돌 횟수.   직전 3초 안에 무엇이든 가려져 있었는가

사용 (가림을 켠 환경에서):
    python occ_report.py results/bc_occ_on_s0/model.pt                       # BC 모델, 300판
    python occ_report.py results/ppo_occ_on/last.pt --episodes 300 --procs 8
    python occ_report.py results/bc_occ_on_s0/model.pt results/ppo_occ_on/last.pt     # 여러 모델을 같은 판으로
결과는 화면과 <모델 폴더>/occ_report.txt 에 쓴다. 환경·모델 파일은 바꾸지 않는다.

'항상 가린' 평가 (--hide): 모델이 그 정보에 실제로 얼마나 기대는지 본다. 학습은 다시 하지 않는다.
    python occ_report.py results/ppo_van_on/last.pt --hide signal        # 신호 색을 내내 가린다 ([33][34]=0, [48]=1)
    python occ_report.py results/ppo_van_on/last.pt --hide ped           # 횡단보도 보행자를 내내 가린다 ([36]=0)
    python occ_report.py results/ppo_van_on/last.pt --hide cross         # 겹치는 차를 내내 가린다 ([37..42] 없음)
    python occ_report.py results/ppo_van_on/last.pt --hide siren         # 사이렌 차의 차로를 내내 가린다 ([44]=0, [49]=1)
    python occ_report.py results/ppo_van_on/last.pt --hide signal,ped    # 여러 개 함께
  관측만 가린다. 위반 판정은 실제 상황으로 한다. 결과는 occ_report_hide_<이름>.txt 에 쓴다.
"""
import argparse
import collections
import json
import multiprocessing as mp
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
WINDOW = 6            # 스텝. '직전 3초' (한 스텝 0.5초)
PASS_NEAR = 20.0      # m. 이 거리 안에 있던 신호·횡단보도가 '다음 것'으로 바뀌면 지나간 것으로 본다
RED = "ruyY"


def load_policy(path, obs_dim, act_dim):
    """팀의 모델 파일(BC·PPO)을 읽는다. train_bc_ppo.py --no-torch 가 만든 numpy 파일이면 numpy 로 읽는다 (시험용)."""
    s = None
    try:
        with np.load(path, allow_pickle=False) as d:
            if "trunk.0.weight" in d.files:
                s = {k: np.asarray(d[k], np.float32) for k in d.files}
    except Exception:
        s = None
    if s is None:
        from test import load_agent
        return load_agent(path, obs_dim, act_dim)
    lane = np.array([1.0, 0.0, -1.0], np.float32)

    class Net:
        def predict(self, obs, deterministic=True):
            h = np.maximum(s["trunk.0.weight"] @ np.asarray(obs, np.float32) + s["trunk.0.bias"], 0)
            h = np.maximum(s["trunk.2.weight"] @ h + s["trunk.2.bias"], 0)
            mu = np.tanh(s["mu_head.weight"] @ h + s["mu_head.bias"])[0]
            return np.array([mu, lane[int(np.argmax(s["lane_head.weight"] @ h + s["lane_head.bias"]))]], np.float32)
    return Net()


def force_hide(env_class, hide):
    """관측을 만들 때 쓰는 상황(_look 의 결과)에서 hide 에 든 정보를 '가려진 것'으로 바꾼다. 실제 상황(판정·보상)은 그대로다."""
    look = env_class._look

    def forced(self):
        s = look(self)
        if s:
            if "signal" in hide and s.get("tls"):
                s["tls_hidden"] = True
            if "ped" in hide:
                s["cw_seen"] = False
            if "cross" in hide:
                s["cross"] = []
            if "siren" in hide and s.get("siren"):
                s["siren"] = (s["siren"][0], s["siren"][1], True)
        return s
    env_class._look = forced


def job(args):
    model, seed, episodes, hide = args
    os.chdir(BASE)
    sys.path.insert(0, BASE)
    try:
        from test import REWARD
    except ImportError:
        from env.mdp_config import REWARD
    from env.mdp_config import SIMULATION, OBSERVATION, ACTION
    from env import daehakro_env
    from env.daehakro_env import DaehakroEnv
    if hide:
        force_hide(DaehakroEnv, hide)
    env = DaehakroEnv(daehakro_env.build(), None, None, SIMULATION, OBSERVATION, ACTION, REWARD)
    c = collections.Counter()
    sir_wait = {"seen": [], "hidden": []}
    try:
        agent = load_policy(model, env.observation_space.shape[0], env.action_space.shape[0])
        np.random.seed(seed)                     # eval_daehakro.evaluate 와 같은 방법
        for _ in range(episodes):
            obs, _ = env.reset()
            hist = collections.deque(maxlen=WINDOW)     # 최근 스텝의 상황 (행동을 정할 때 본 것)
            flags = collections.deque(maxlen=WINDOW)    # 최근 스텝의 위반
            sir_run = None                              # 지금 진행 중인 '사이렌 차가 내 차로 뒤' 구간: [스텝 수, 가려져 있었는가]
            done = False
            while not done:
                s = env._snap or {}
                tls, cw, sir = s.get("tls"), s.get("cw"), s.get("siren")
                now = {"tls": tls[0] if tls else None, "tls_d": tls[1] if tls else None,
                       "tls_red": bool(tls and tls[2] in RED), "tls_hid": bool(tls and s.get("tls_hidden")),
                       "cw": cw[0] if cw else None, "cw_d": cw[1] if cw else None,
                       "cw_wait": bool(cw and cw[2]), "cw_hid": bool(cw and cw[2] and not s.get("cw_seen")),
                       "foe_hid": bool(s.get("foe_hidden")),
                       "sir_hid": bool(sir and sir[2])}
                hist.append(now)
                c["steps"] += 1
                c["step_tls_hid"] += now["tls_hid"]
                c["step_cw_hid"] += now["cw_hid"]
                c["step_foe_hid"] += now["foe_hid"]
                c["step_sir_hid"] += now["sir_hid"]
                c["step_any_hid"] += now["tls_hid"] or now["cw_hid"] or now["foe_hid"] or now["sir_hid"]

                # 사이렌 차가 내 차로 뒤에 있는 구간: 몇 스텝 만에 비켜 주는가
                if sir and sir[1]:
                    if sir_run is None:
                        sir_run = [0, False]
                    sir_run[0] += 1
                    sir_run[1] = sir_run[1] or bool(sir[2])
                elif sir_run is not None:
                    sir_wait["hidden" if sir_run[1] else "seen"].append(sir_run[0])
                    sir_run = None

                obs, _, term, trunc, info = env.step(agent.predict(obs, deterministic=True))
                done = term or trunc
                flags.append({"red": bool(info.get("red_light")), "cw": bool(info.get("crosswalk_violation")),
                              "yield": bool(info.get("yield_violation"))})
                after = env._snap or {}
                on_foot = bool(info.get("collided")) and (
                    info.get("collision_type") in ("crossing", "walkingarea", "sharedLane")
                    or str(info.get("collision_with") or "").startswith("ped_"))

                # 신호를 지나갔다: 가까이 있던 신호가 다음 것으로 바뀌었다
                nxt = after.get("tls")
                if now["tls"] and now["tls_d"] <= PASS_NEAR and (done or not nxt or nxt[0] != now["tls"]) \
                        and not info.get("collided"):
                    mine = [h for h in hist if h["tls"] == now["tls"]]
                    if any(h["tls_red"] for h in mine):
                        k = "hid" if any(h["tls_hid"] for h in mine) else "seen"
                        c[f"tls_pass_{k}"] += 1
                        c[f"tls_viol_{k}"] += any(f["red"] for f in flags)

                # 횡단보도를 지나갔다 (또는 그 앞에서 보행자와 부딪혔다)
                nxt = after.get("cw")
                if now["cw"] and now["cw_d"] <= PASS_NEAR and (on_foot or done or not nxt or nxt[0] != now["cw"]) \
                        and (on_foot or not info.get("collided")):
                    mine = [h for h in hist if h["cw"] == now["cw"]]
                    if any(h["cw_wait"] for h in mine):
                        k = "hid" if any(h["cw_hid"] for h in mine) else "seen"
                        c[f"cw_pass_{k}"] += 1
                        c[f"cw_viol_{k}"] += any(f["cw"] for f in flags) or on_foot
                        c[f"cw_hit_{k}"] += on_foot

                if info.get("yield_violation"):
                    c["yield_viol"] += 1
                    c["yield_viol_hid"] += any(h["foe_hid"] for h in hist)
                if info.get("collided"):
                    any_hid = any(h["tls_hid"] or h["cw_hid"] or h["foe_hid"] for h in hist)
                    c["crash_ped" if on_foot else "crash_car"] += 1
                    c["crash_ped_hid" if on_foot else "crash_car_hid"] += any_hid
            if sir_run is not None:
                sir_wait["hidden" if sir_run[1] else "seen"].append(sir_run[0])
            c["episodes"] += 1
            c["arrive"] += bool(info.get("arrived")) and not info.get("collided")   # 부딪혀 사라진 차도 SUMO 는 '도착'으로 센다
    finally:
        env.close()
    return dict(c), sir_wait


def rate(a, b):
    return f"{a}/{b} ({a / b:.0%})" if b else f"{a}/{b}"


def report(model, c, sir):
    n = max(c["steps"], 1)
    out = [f"모델: {model}",
           f"{c['episodes']}판, {c['steps']:,}스텝, 도착 {rate(c['arrive'], c['episodes'])}",
           "",
           "가림이 있던 스텝 (전체 스텝 중)",
           f"   무엇이든 {c['step_any_hid'] / n:.1%} | 신호 {c['step_tls_hid'] / n:.1%} | 보행자 {c['step_cw_hid'] / n:.1%} | "
           f"양보 대상 {c['step_foe_hid'] / n:.1%} | 사이렌 차 {c['step_sir_hid'] / n:.1%}",
           "",
           "                               보이던 장면            가려져 있던 장면",
           f"신호 (빨강·노랑이던 신호 통과)   위반 {rate(c['tls_viol_seen'], c['tls_pass_seen']):<16s}  위반 {rate(c['tls_viol_hid'], c['tls_pass_hid'])}",
           f"횡단보도 (보행자가 있던 통과)    위반 {rate(c['cw_viol_seen'], c['cw_pass_seen']):<16s}  위반 {rate(c['cw_viol_hid'], c['cw_pass_hid'])}",
           f"   그중 보행자 충돌              {c['cw_hit_seen']:<21d}  {c['cw_hit_hid']}",
           "",
           f"양보 위반 {c['yield_viol']}건, 그중 직전 3초 안에 가려진 양보 대상이 있던 것 {c['yield_viol_hid']}건",
           f"차 충돌 {c['crash_car']}건 (직전 3초 안에 가림 {c['crash_car_hid']}건) | "
           f"보행자 충돌 {c['crash_ped']}건 (직전 3초 안에 가림 {c['crash_ped_hid']}건)",
           ""]
    for k, name in (("seen", "보이던"), ("hidden", "가려져 있던")):
        v = sir[k]
        if v:
            out.append(f"사이렌 차가 내 차로 뒤에 온 것 ({name} 차) {len(v)}번: 비켜 줄 때까지 평균 {np.mean(v) * 0.5:.1f}초, "
                       f"가운데값 {np.median(v) * 0.5:.1f}초, 10초 넘게 막은 것 {sum(1 for x in v if x > 20)}번")
        else:
            out.append(f"사이렌 차가 내 차로 뒤에 온 것 ({name} 차) 0번")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description="가림 장면 집계")
    p.add_argument("models", nargs="+")
    p.add_argument("--episodes", type=int, default=300)
    p.add_argument("--procs", type=int, default=8)
    p.add_argument("--seed", type=int, default=3000, help="평가 seed 의 시작 번호 (학습·다른 평가와 겹치지 않는 번호)")
    p.add_argument("--hide", default="", help="내내 가릴 정보 (쉼표로 여러 개): signal, ped, cross, siren")
    a = p.parse_args()
    hide = tuple(x for x in a.hide.replace(" ", "").split(",") if x)
    bad = [x for x in hide if x not in ("signal", "ped", "cross", "siren")]
    if bad:
        sys.exit(f"--hide 에 쓸 수 있는 것은 signal, ped, cross, siren 입니다: {bad}")
    from env import occlusion
    print(f"가림: {'켬' if occlusion.ENABLED else '끔 (DAEHAKRO_OCCLUSION=0)'}"
          + (f" | 내내 가리는 정보: {', '.join(hide)}" if hide else ""), flush=True)
    procs = max(1, min(a.procs, a.episodes))
    share = [a.episodes // procs + (1 if i < a.episodes % procs else 0) for i in range(procs)]
    for model in a.models:
        path = model if os.path.isabs(model) else os.path.join(BASE, model)
        jobs = [(path, a.seed + i, n, hide) for i, n in enumerate(share) if n > 0]
        print(f"{model}: {a.episodes}판을 SUMO {len(jobs)}개로 돌립니다 (끝날 때까지 조용합니다)", flush=True)
        results = []
        with mp.get_context("spawn").Pool(procs) as pool:
            for r in pool.imap_unordered(job, jobs):
                results.append(r)
                print(f"   {len(results)}/{len(jobs)} 묶음 끝", flush=True)
        c, sir = collections.Counter(), {"seen": [], "hidden": []}
        for ci, si in results:
            c.update(ci)
            for k in sir:
                sir[k] += si[k]
        text = report(model, c, sir)
        if hide:
            text = (f"※ 내내 가린 정보: {', '.join(hide)}  (이 정보에 대해서는 모든 장면이 '가려져 있던 장면'이다)\n" + text)
        print("\n" + text, flush=True)
        tag = "occ_report" + ("_hide_" + "_".join(hide) if hide else "")
        with open(os.path.join(os.path.dirname(path), tag + ".txt"), "a", encoding="utf-8") as f:
            f.write(text + "\n\n")
        with open(os.path.join(os.path.dirname(path), tag + ".json"), "w", encoding="utf-8") as f:
            json.dump({"model": model, "counts": dict(c), "siren_block_steps": sir}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
