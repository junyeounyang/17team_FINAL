r"""BC 학습과 평가를 한 번에 돌린다.

    1. 학습       seed 0, 10, 20, 30, 40 으로 train_bc.py (하나씩 차례로)
    2. 가벼운 평가  다섯 모델 모두 seed 99, 50 에피소드 (모델마다 SUMO 하나, 동시에)
    3. 중간 평가    가벼운 평가 상위 3개를 seed 100, 100 에피소드
    4. 최종 평가    중간 평가 1등 모델을 seed 110, 120, 130, 140, 150 에서 각 300 에피소드 (seed 마다 SUMO 하나, 동시에)

순위: 도착 수 → 위반 없이 도착한 수 → 충돌이 적은 쪽 → 평균 보상 (같은 seed 라 모든 모델이 같은 교통 상황을 만난다)
평가는 eval_daehakro.py 의 평가 함수(evaluate)와 모델 불러오기(test.py 의 load_agent)를 그대로 쓴다.

이미 끝난 일은 건너뛴다 (model.pt, 평가 결과 .json 이 있으면) → 중간에 멈추거나 PC 가 꺼져도
같은 명령을 다시 실행하면 이어서 돈다.

사용 (프로젝트 폴더에서):
    python run_all.py --data data\demo_600.npz
    python run_all.py --data data\demo_600.npz --top 2           ← 중간 평가에 2개만
    python run_all.py --data data\demo_600.npz --until mid       ← 중간 평가까지만

결과:
    results\bc_600_s0 ... results\bc_600_s40      학습한 모델 (train_bc.py 출력 그대로)
    logs_600\train_s0.txt ...                      학습 로그
    logs_600\light_s0.txt / .json ...              평가마다 에피소드별 로그와 지표
    logs_600\summary.txt                           단계별 순위, 고른 모델, 최종 성능 (95% 신뢰구간 포함)
"""
import argparse
import concurrent.futures
import json
import math
import os
import subprocess
import sys
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ENDS = ("도착", "차와 충돌", "보행자와 충돌", "경로 이탈", "오래 멈춤", "시간초과")


# ───────────────────────── 평가 한 건 (자식 프로세스) ─────────────────────────
def run_job(model, seed, episodes, out_json):
    """eval_daehakro.py 와 같은 방법으로 평가하고 지표를 json 으로 남긴다."""
    os.chdir(BASE)
    sys.path.insert(0, BASE)
    from env.mdp_config import SIMULATION, OBSERVATION, ACTION
    from env import daehakro_env
    from env.daehakro_env import DaehakroEnv
    import eval_daehakro
    from test import load_agent, REWARD

    print(f"모델: {model}\nseed {seed}, {episodes} 에피소드", flush=True)
    env = DaehakroEnv(daehakro_env.build(), None, None, SIMULATION, OBSERVATION, ACTION, REWARD)
    try:
        agent = load_agent(model, env.observation_space.shape[0], env.action_space.shape[0])
        r = eval_daehakro.evaluate(agent, env, episodes, seed=seed)
    finally:
        env.close()
    eval_daehakro.report(r)
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in r.items()}
    out.update(model=model, seed=seed)
    tmp = out_json + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_json)          # 끝까지 돈 평가만 결과 파일이 생긴다


# ───────────────────────── 부모: 학습·평가 진행 ─────────────────────────
def child_env():
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"    # 로그 파일을 UTF-8 로
    e["PYTHONUNBUFFERED"] = "1"
    return e


def stamp():
    return time.strftime("%H:%M:%S")


_PRINT = threading.Lock()


def log(text):
    with _PRINT:                       # 동시에 끝난 평가의 출력이 한 줄에 섞이지 않게
        print(text, flush=True)


def train(args, seed, model_dir, log_path):
    model = os.path.join(model_dir, "model.pt")
    if os.path.exists(model):
        log(f"[{stamp()}] 학습 seed {seed}: 이미 있음 ({model})")
        return model
    log(f"[{stamp()}] 학습 seed {seed} 시작 → {model_dir}")
    t0 = time.time()
    cmd = [sys.executable, os.path.join(BASE, "train_bc.py"), "--data", args.data, "--epochs", str(args.epochs),
           "--seed", str(seed), "--out-dir", model_dir]
    with open(log_path, "w", encoding="utf-8") as fh:
        rc = subprocess.run(cmd, cwd=BASE, stdout=fh, stderr=subprocess.STDOUT, env=child_env()).returncode
    if rc != 0 or not os.path.exists(model):
        log(f"[{stamp()}] 학습 seed {seed} 실패 (로그: {log_path})")
        return None
    log(f"[{stamp()}] 학습 seed {seed} 끝 ({(time.time() - t0) / 60:.0f}분)")
    return model


def evaluate_many(jobs, workers):
    """jobs: [(이름, 모델, seed, 에피소드, json, 로그)] 를 동시에 workers 개까지 돌린다. Returns {이름: 지표 dict}."""
    def one(job):
        name, model, seed, episodes, out_json, log_path = job
        if os.path.exists(out_json):
            log(f"[{stamp()}] {name}: 이미 있음")
        else:
            log(f"[{stamp()}] {name} 시작 (seed {seed}, {episodes} 에피소드)")
            cmd = [sys.executable, os.path.abspath(__file__), "--job", model, str(seed), str(episodes), out_json]
            with open(log_path, "w", encoding="utf-8") as fh:
                subprocess.run(cmd, cwd=BASE, stdout=fh, stderr=subprocess.STDOUT, env=child_env())
            if not os.path.exists(out_json):
                log(f"[{stamp()}] {name} 실패 — 로그: {log_path}")
                return name, None
        with open(out_json, encoding="utf-8") as f:
            r = json.load(f)
        log(f"[{stamp()}] {name} 끝: {line(r)}")
        return name, r

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for name, r in pool.map(one, jobs):
            if r is not None:
                results[name] = r
    return results


def rank_key(r):
    e = r["ends"]
    crashes = e.get("차와 충돌", 0) + e.get("보행자와 충돌", 0)
    return (e.get("도착", 0), r["clean"], -crashes, r["return"])


def line(r):
    n, e = r["episodes"], r["ends"]
    return (f"도착 {e.get('도착', 0)}/{n} ({e.get('도착', 0) / n:.0%}) | 위반 없이 도착 {r['clean'] / n:.0%} | "
            f"충돌 {e.get('차와 충돌', 0) + e.get('보행자와 충돌', 0)} | 이탈 {e.get('경로 이탈', 0)} | "
            f"멈춤 {e.get('오래 멈춤', 0)} | 시간초과 {e.get('시간초과', 0)} | 보상 {r['return']:.1f}")


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def main():
    ap = argparse.ArgumentParser(description="BC 학습 → 가벼운 평가 → 중간 평가 → 최종 평가를 한 번에")
    ap.add_argument("--job", nargs=4, metavar=("MODEL", "SEED", "EPISODES", "OUT_JSON"), help=argparse.SUPPRESS)
    ap.add_argument("--data", help=r"시범 데이터 (예: data\demo_600.npz)")
    ap.add_argument("--tag", default=None, help="결과 이름 (생략 시 데이터 이름에서: demo_600 → 600)")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 10, 20, 30, 40], help="학습 seed")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--light-seed", type=int, default=99)
    ap.add_argument("--light-episodes", type=int, default=50)
    ap.add_argument("--top", type=int, default=3, help="중간 평가에 올릴 모델 수")
    ap.add_argument("--mid-seed", type=int, default=100)
    ap.add_argument("--mid-episodes", type=int, default=100)
    ap.add_argument("--final-seeds", type=int, nargs="+", default=[110, 120, 130, 140, 150])
    ap.add_argument("--final-episodes", type=int, default=300)
    ap.add_argument("--workers", type=int, default=5, help="동시에 돌릴 평가 수 (SUMO 수)")
    ap.add_argument("--until", choices=["train", "light", "mid", "final"], default="final", help="이 단계까지만")
    args = ap.parse_args()

    if args.job:
        model, seed, episodes, out_json = args.job
        run_job(model, int(seed), int(episodes), out_json)
        return
    if not args.data:
        ap.error("--data 가 필요합니다 (예: --data data\\demo_600.npz)")
    if not os.path.isabs(args.data):
        args.data = os.path.join(BASE, args.data)
    if not os.path.exists(args.data):
        ap.error(f"데이터 파일이 없습니다: {args.data}")
    tag = args.tag or os.path.splitext(os.path.basename(args.data))[0].replace("demo_", "")
    logs = os.path.join(BASE, f"logs_{tag}")
    os.makedirs(logs, exist_ok=True)
    summary = []

    def say(text=""):
        log(text)
        summary.append(text)

    t_all = time.time()
    say(f"BC 학습·평가 ({stamp()} 시작) | 데이터 {args.data}")

    # 1. 학습
    models = {}
    for s in args.seeds:
        m = train(args, s, os.path.join(BASE, "results", f"bc_{tag}_s{s}"), os.path.join(logs, f"train_s{s}.txt"))
        if m:
            models[f"s{s}"] = m
    if not models:
        say("학습한 모델이 없습니다. 학습 로그를 확인하세요.")
        return
    if args.until == "train":
        return

    # 2. 가벼운 평가
    jobs = [(f"가벼운 평가 {k}", m, args.light_seed, args.light_episodes,
             os.path.join(logs, f"light_{k}.json"), os.path.join(logs, f"light_{k}.txt")) for k, m in models.items()]
    light = {name.split()[-1]: r for name, r in evaluate_many(jobs, min(args.workers, len(jobs))).items()}
    order = sorted(light, key=lambda k: rank_key(light[k]), reverse=True)
    say(f"\n[가벼운 평가] seed {args.light_seed}, {args.light_episodes} 에피소드")
    for i, k in enumerate(order, 1):
        say(f"  {i}. {k:4s} {line(light[k])}")
    picked = order[:args.top]
    say(f"  → 중간 평가: {', '.join(picked)}")
    if args.until == "light" or not picked:
        open(os.path.join(logs, "summary.txt"), "w", encoding="utf-8").write("\n".join(summary) + "\n")
        return

    # 3. 중간 평가
    jobs = [(f"중간 평가 {k}", models[k], args.mid_seed, args.mid_episodes,
             os.path.join(logs, f"mid_{k}.json"), os.path.join(logs, f"mid_{k}.txt")) for k in picked]
    mid = {name.split()[-1]: r for name, r in evaluate_many(jobs, min(args.workers, len(jobs))).items()}
    order = sorted(mid, key=lambda k: (rank_key(mid[k]), rank_key(light[k])), reverse=True)
    say(f"\n[중간 평가] seed {args.mid_seed}, {args.mid_episodes} 에피소드")
    for i, k in enumerate(order, 1):
        say(f"  {i}. {k:4s} {line(mid[k])}")
    if not order:
        say("중간 평가 결과가 없습니다. 로그를 확인하세요.")
        open(os.path.join(logs, "summary.txt"), "w", encoding="utf-8").write("\n".join(summary) + "\n")
        return
    best = order[0]
    say(f"  → 최종 평가 모델: {best} ({models[best]})")
    if args.until == "mid":
        open(os.path.join(logs, "summary.txt"), "w", encoding="utf-8").write("\n".join(summary) + "\n")
        return

    # 4. 최종 평가
    jobs = [(f"최종 평가 seed{s}", models[best], s, args.final_episodes,
             os.path.join(logs, f"final_{best}_seed{s}.json"), os.path.join(logs, f"final_{best}_seed{s}.txt"))
            for s in args.final_seeds]
    final = evaluate_many(jobs, min(args.workers, len(jobs)))
    say(f"\n[최종 평가] 모델 {best}, seed {' '.join(map(str, args.final_seeds))} 에서 각 {args.final_episodes} 에피소드")
    tot = {"episodes": 0, "ends": {}, "events": {}, "clean": 0, "ret": 0.0, "len": 0.0, "lc": 0,
           "speed_eps": 0, "speed_steps": 0}
    for s in args.final_seeds:
        r = final.get(f"최종 평가 seed{s}")
        if r is None:
            say(f"  seed {s}: 실패 (로그 확인)")
            continue
        say(f"  seed {s}: {line(r)}")
        n = r["episodes"]
        tot["episodes"] += n
        tot["clean"] += r["clean"]
        tot["ret"] += r["return"] * n
        tot["len"] += r["length"] * n
        tot["lc"] += r["lane_changes"]
        tot["speed_eps"] += r.get("speed_episodes", 0)
        tot["speed_steps"] += r.get("speed_steps", 0)
        for k, v in r["ends"].items():
            tot["ends"][k] = tot["ends"].get(k, 0) + v
        for k, v in r["events"].items():
            tot["events"][k] = tot["events"].get(k, 0) + v
    n = tot["episodes"]
    if n:
        say(f"\n  합계 {n} 에피소드")
        for end in ENDS:
            k = tot["ends"].get(end, 0)
            lo, hi = wilson(k, n)
            say(f"    {end:9s}: {k:4d} 회 ({k / n:6.1%})  95% 신뢰구간 {lo:.1%} ~ {hi:.1%}")
        lo, hi = wilson(tot["clean"], n)
        say(f"    위반 없이 도착: {tot['clean']:4d} 회 ({tot['clean'] / n:6.1%})  95% 신뢰구간 {lo:.1%} ~ {hi:.1%}")
        ev = tot["events"]
        say(f"    위반 건수: 신호위반 {ev.get('red_light', 0)}, 횡단보도 {ev.get('crosswalk_violation', 0)}, "
            f"양보 {ev.get('yield_violation', 0)}, 버스전용차로 {ev.get('bus_lane_violation', 0)}, "
            f"실선 침범 {ev.get('solid_line_violation', 0)}")
        say(f"    과속: {tot['speed_steps']} 스텝, 과속한 에피소드 {tot['speed_eps']} 회 ({tot['speed_eps'] / n:.1%})")
        say(f"    평균 보상 {tot['ret'] / n:.1f} | 평균 길이 {tot['len'] / n:.0f} 스텝 | 차로변경 에피소드당 {tot['lc'] / n:.1f} 번")
    say(f"\n전체 걸린 시간 {(time.time() - t_all) / 3600:.1f} 시간 ({stamp()} 끝)")
    open(os.path.join(logs, "summary.txt"), "w", encoding="utf-8").write("\n".join(summary) + "\n")
    print(f"요약: {os.path.join(logs, 'summary.txt')}")


if __name__ == "__main__":
    main()
