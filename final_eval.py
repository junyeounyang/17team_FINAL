"""팀의 최종 평가 — 모델 하나를 seed 110, 120, 130, 140, 150 에서 각 300 에피소드 (모두 1,500판).

    python final_eval.py results/ppo_track_on/last.pt

run_all_BC.py 의 '4. 최종 평가'와 같은 방법이다 (eval_daehakro.py 의 평가, seed 마다 SUMO 하나, 동시에).
BC 모델과 PPO 모델을 모두 받는다. 결과는 logs_final/<이름>/ 에 seed 별 json·로그와 summary.txt 로 남는다.
끊겨도 같은 명령을 다시 실행하면 끝난 seed 는 건너뛴다.
"""
import argparse
import os
import sys
import time

import run_all_BC as R


def main():
    ap = argparse.ArgumentParser(description="최종 평가 (seed 110~150, 각 300판)")
    ap.add_argument("model")
    ap.add_argument("--seeds", type=int, nargs="+", default=[110, 120, 130, 140, 150])
    ap.add_argument("--episodes", type=int, default=300)
    ap.add_argument("--workers", type=int, default=5, help="동시에 돌릴 SUMO 수")
    ap.add_argument("--name", default=None, help="결과 폴더 이름 (생략 시 모델 경로에서)")
    a = ap.parse_args()
    model = os.path.abspath(a.model)
    if not os.path.exists(model):
        sys.exit(f"모델 파일이 없습니다: {model}")
    name = a.name or (os.path.basename(os.path.dirname(model)) + "_" + os.path.splitext(os.path.basename(model))[0])
    logs = os.path.join(R.BASE, "logs_final", name)
    os.makedirs(logs, exist_ok=True)
    summary = []

    def say(text=""):
        summary.append(text)
        print(text, flush=True)

    t0 = time.time()
    say(f"최종 평가 ({R.stamp()} 시작) | 모델 {model}")
    jobs = [(f"seed {s}", model, s, a.episodes, os.path.join(logs, f"seed{s}.json"), os.path.join(logs, f"seed{s}.txt"))
            for s in a.seeds]
    done = R.evaluate_many(jobs, min(a.workers, len(jobs)))
    tot = {"episodes": 0, "ends": {}, "events": {}, "clean": 0, "ret": 0.0, "len": 0.0, "lc": 0, "speed_eps": 0, "speed_steps": 0}
    say()
    for s in a.seeds:
        r = done.get(f"seed {s}")
        if r is None:
            say(f"  seed {s}: 실패 (로그: {os.path.join(logs, f'seed{s}.txt')})")
            continue
        say(f"  seed {s}: {R.line(r)}")
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
        for end in R.ENDS:
            k = tot["ends"].get(end, 0)
            lo, hi = R.wilson(k, n)
            say(f"    {end:9s}: {k:4d} 회 ({k / n:6.1%})  95% 신뢰구간 {lo:.1%} ~ {hi:.1%}")
        crash = tot["ends"].get("차와 충돌", 0) + tot["ends"].get("보행자와 충돌", 0)
        lo, hi = R.wilson(crash, n)
        say(f"    충돌 합계  : {crash:4d} 회 ({crash / n:6.1%})  95% 신뢰구간 {lo:.1%} ~ {hi:.1%}")
        lo, hi = R.wilson(tot["clean"], n)
        say(f"    위반 없이 도착: {tot['clean']:4d} 회 ({tot['clean'] / n:6.1%})  95% 신뢰구간 {lo:.1%} ~ {hi:.1%}")
        ev = tot["events"]
        say(f"    위반 건수: 신호위반 {ev.get('red_light', 0)}, 횡단보도 {ev.get('crosswalk_violation', 0)}, "
            f"양보 {ev.get('yield_violation', 0)}, 버스전용차로 {ev.get('bus_lane_violation', 0)}, "
            f"실선 침범 {ev.get('solid_line_violation', 0)}")
        say(f"    과속: {tot['speed_steps']} 스텝, 과속한 에피소드 {tot['speed_eps']} 회 ({tot['speed_eps'] / n:.1%})")
        say(f"    평균 보상 {tot['ret'] / n:.1f} | 평균 길이 {tot['len'] / n:.0f} 스텝 | 차로변경 에피소드당 {tot['lc'] / n:.1f} 번")
    say(f"\n걸린 시간 {(time.time() - t0) / 60:.0f}분 ({R.stamp()} 끝)")
    with open(os.path.join(logs, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(summary) + "\n")
    print(f"요약: {os.path.join(logs, 'summary.txt')}")


if __name__ == "__main__":
    main()
