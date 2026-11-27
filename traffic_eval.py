"""교통량을 바꾼 평가 — 학습 때와 같은 경로에서, 주변 차의 양만 바꿔 도착·충돌을 센다.

    python traffic_eval.py models/ppo_track.pt expert --episodes 100
    python traffic_eval.py models/ppo_track.pt --scales 0.5 1.5 --episodes 50

모델은 다시 학습하지 않는다. 환경 파일도 바꾸지 않는다: SUMO 를 띄울 때 --scale (모든 차량 흐름의 배수)만 더한다.
1.0 이 학습·최종 평가 때의 교통량이다. 'expert' 는 시범 운전자 (그 교통량에서의 기준).
결과는 화면과 traffic_eval/<운전자>.txt 에 쓴다.
"""
import argparse
import collections
import multiprocessing as mp
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))


def job(args):
    model, scale, seed, episodes = args
    os.chdir(BASE)
    sys.path.insert(0, BASE)
    from env import daehakro_env
    tr = daehakro_env.traci
    if not hasattr(tr, "_scale_box"):           # 한 프로세스가 묶음을 여러 개 돌린다: 한 번만 감싸고 배수만 바꾼다
        tr._scale_box = [1.0]
        start = tr.start

        def scaled(cmd, *a, **k):               # SUMO 명령에 교통량 배수를 더한다 (이 프로세스 안에서만)
            return start(list(cmd) + ["--scale", str(tr._scale_box[0])], *a, **k)
        tr.start = scaled
    tr._scale_box[0] = scale
    import occ_report
    c, sir = occ_report.job((model, seed, episodes, ()))
    c["sir_runs"] = len(sir["seen"]) + len(sir["hidden"])
    c["sir_steps"] = sum(sir["seen"]) + sum(sir["hidden"])
    return scale, c


def main():
    p = argparse.ArgumentParser(description="교통량을 바꾼 평가")
    p.add_argument("drivers", nargs="+", help="모델 파일 또는 'expert'")
    p.add_argument("--scales", nargs="+", type=float, default=[0.5, 0.75, 1.0, 1.25, 1.5])
    p.add_argument("--episodes", type=int, default=100, help="교통량마다 판 수")
    p.add_argument("--procs", type=int, default=8)
    p.add_argument("--seed", type=int, default=6000)
    a = p.parse_args()
    out_dir = os.path.join(BASE, "traffic_eval")
    os.makedirs(out_dir, exist_ok=True)
    per = max(1, a.procs // 2)
    for driver in a.drivers:
        path = driver if driver == "expert" or os.path.isabs(driver) else os.path.join(BASE, driver)
        jobs = []
        for s in a.scales:
            share = [a.episodes // per + (1 if i < a.episodes % per else 0) for i in range(per)]
            jobs += [(path, s, a.seed + i, n) for i, n in enumerate(share) if n > 0]
        print(f"{driver}: 교통량 {len(a.scales)}가지 × {a.episodes}판 (묶음 {len(jobs)}개, SUMO {a.procs}개)", flush=True)
        tot = {s: collections.Counter() for s in a.scales}
        with mp.get_context("spawn").Pool(a.procs) as pool:
            for i, (s, c) in enumerate(pool.imap_unordered(job, jobs)):
                tot[s].update(c)
                print(f"   {i + 1}/{len(jobs)} 묶음 끝", flush=True)
        lines = [f"운전자: {driver}   (교통량마다 {a.episodes}판, seed {a.seed}~)",
                 f"{'교통량':>6s} {'도착':>14s} {'차 충돌':>7s} {'보행자 충돌':>9s} {'그 밖(멈춤 등)':>12s} {'신호 위반':>12s} {'횡단보도 위반':>12s} {'양보 위반':>8s} {'평균 스텝':>8s} {'긴급차 양보 평균(초)':>16s}"]
        for s in a.scales:
            c = tot[s]
            n = max(c["episodes"], 1)
            other = c["episodes"] - c["arrive"] - c["crash_car"] - c["crash_ped"]
            tv, tp = c["tls_viol_seen"] + c["tls_viol_hid"], c["tls_pass_seen"] + c["tls_pass_hid"]
            cv, cp = c["cw_viol_seen"] + c["cw_viol_hid"], c["cw_pass_seen"] + c["cw_pass_hid"]
            sir = c["sir_steps"] * 0.5 / c["sir_runs"] if c["sir_runs"] else 0.0
            lines.append(f"{s:>6.2f}배 {c['arrive']:>4d}/{c['episodes']:<3d} ({c['arrive'] / n:>4.0%}) {c['crash_car']:>7d} {c['crash_ped']:>9d} {other:>12d} "
                         f"{tv:>5d}/{tp:<5d} {cv:>6d}/{cp:<5d} {c['yield_viol']:>8d} {c['steps'] / n:>8.0f} {sir:>12.1f} ({c['sir_runs']}번)")
        text = "\n".join(lines)
        print("\n" + text + "\n", flush=True)
        name = "expert" if driver == "expert" else os.path.splitext(os.path.basename(path))[0]
        with open(os.path.join(out_dir, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
