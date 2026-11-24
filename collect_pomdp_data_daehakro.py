"""대학로 POMDP 데이터 수집 — 수업의 collect_pomdp_data.py 에 대학로 기록 항목 23개를 더한 수정본.

수업 원본(collect_pomdp_data.py)은 그대로 두고 이 파일을 새로 만들었다. 저장 형식은 원본과 같고, 아래만 더했다.
관측(51차원)·행동·보상·학습·평가 코드는 바꾸지 않는다. 더한 항목은 기록용 state 라서 정책 입력에 들어가지 않는다.

더한 항목 (매 스텝, state 는 그 스텝에 행동을 정할 때의 상태)
    state.sim_time                 float  그 state 를 읽은 시뮬레이션 시각 (s)
    state.tls.<신호 id> × 15        신호마다 연결별 숫자 리스트: G,g → 1 / y,Y,o,O → 0 / r,u,s → -1
                                    순서는 tls_index.json 의 order (대학로 남→북 IH M O I H F E D C, 로터리 A RS J_SW J_NWp J_NW J_NE)
    state.junction_foes            [[상대 id, AV 가 상충 지점까지 m, 상대가 상충 지점까지 m, AV 가 양보해야 하면 1], ...]
                                    (이미 지나간 차는 뺀다)
    state.persons                  AV 50 m 안 보행자 [[id, 어린이 1 / 어른 0, x, y, 속도 m/s, 있는 곳(횡단보도·보도 id)], ...]
    state.vehicles[].type_id       차종 이름 (vType)
    state.vehicles[].stopped       경로의 정차(<stop>) 중이면 true — 버스 정류장, 학부모 차 정차. 신호·정체 대기는 false
    state.vehicles[].signals       방향지시등·브레이크등 비트 (traci.vehicle.getSignals)
    state.vehicles[].assist        긴급차 보조가 그 차에 하는 일: 0 없음 / 1 긴급차에 비켜 줌 / 2 꼬리물기 대기 /
                                    3 횡단보도·교차로 앞에서 줄이거나 세운 사이렌 긴급차 / 4 버스 끼워 주기 / 5 긴급차 통과 대기
                                    (여러 개면 작은 번호)
    event.collision_with           충돌한 상대 id (없으면 null)
    vehicles[] 에는 배경 차량만 넣는다 (AV 는 ego_* 항목에 있다).
    값은 모두 숫자다. 예외: id 와 차종 이름, 차로·도로 id 는 문자열, ego_alive·stopped 는 true/false.

수집 시작 때 데이터와 같은 폴더에 한 번 저장
    tls_index.json      {"order": 신호 15개, "code": 글자 → 숫자, "links": {신호 id: [{"i","from","to","via"} 또는 null, ...]}}
    daehakro.tll.xml    신호 프로그램 사본 (신호 남은 시간은 저장하지 않고 sim_time 과 이 파일로 계산한다)
    시작할 때 traci 로 신호 목록·신호별 연결 수를 읽어 기록 형식과 다르면 멈춘다 (env.record_check_tls).

NPZ 에 더한 것 (고정 길이만): sim_time (N,), tls (N, 137) float32 (order 순서로 이어 붙임), collided (N,) bool.
길이가 변하는 persons, junction_foes, vehicles[] 는 JSONL 에만 있다.

예시:
    python collect_pomdp_data_daehakro.py --episodes 2
    python collect_pomdp_data_daehakro.py --model results/ppo_v2/best.pt --episodes 100 --workers 6

아래는 수업 원본 설명 그대로 (관측 차원만 대학로 기준 51 로 고침).

저장 단위는 POMDP transition 하나다:
    (o_t, a_t, r_t, o_{t+1}, terminated, truncated, s_t, s_{t+1})

- o_t / o_{t+1}: agent가 실제로 보는 부분관측 (51차원)
- a_t: [가감속 raw, 차선변경 raw]
- lane_change: 실제 환경에 적용된 {-1, 0, +1}
- s_t / s_{t+1}: SUMO 내부의 privileged simulator state.
  정책 입력에는 쓰지 않고 데이터 검증/representation/belief 학습용으로만 저장한다.

용량을 줄이기 위해:
- JSONL은 gzip으로 압축해서 쓰고(.jsonl.gz), observation/state/detected_vehicles의
  float는 --ndigits 자리로 반올림한다 (NPZ는 float32 그대로).
- next_observation / next_state는 다음 레코드의 observation / state와 같으므로
  에피소드 마지막 스텝(terminated or truncated)에만 기록한다.
  읽을 때는 iter_transitions()가 채워서 돌려준다.
- NPZ의 감지 차량 좌표는 object 배열(pickle) 대신 flat (M, 2) + offsets로 저장한다.

출력:
    data/pomdp_YYYYMMDD_HHMMSS.jsonl.gz
    data/pomdp_YYYYMMDD_HHMMSS.npz
    data/tls_index.json, data/daehakro.tll.xml

읽기:
    from collect_pomdp_data_daehakro import iter_transitions
    for rec in iter_transitions("data/pomdp_....jsonl.gz"):
        rec["observation"], rec["next_observation"], rec["state"], rec["next_state"], ...

    d = np.load("data/pomdp_....npz")          # allow_pickle 불필요
    off = d["detected_offsets"]
    xy_i = d["detected_xy"][off[i]:off[i + 1]]  # 스텝 i의 감지 차량 (N_i, 2)
    d["tls"][i]                                  # 스텝 i의 신호 137칸 (tls_index.json 의 order 순서)
"""
import argparse
import gzip
import json
import multiprocessing
import os
import shutil
import time
from datetime import datetime

import numpy as np

from env.road_config import ROAD, EGO, TRAFFIC
from env.mdp_config import SIMULATION, OBSERVATION, ACTION
from env import daehakro_env as road_builder
from env.daehakro_env import DaehakroEnv as SumoHighwayEnv
from train import HPARAMS, REWARD  # 학습과 같은 보상 조건 + PPO 네트워크 구조

BASE = os.path.dirname(os.path.abspath(__file__))


def detect_algorithm(model_path: str) -> str:
    """model.pt가 어느 학습 스크립트 출력인지 파일 내용으로 판별한다.

    train.py(PPO)  : policy.state_dict()를 그대로 저장 → 텐서만 있는 dict
    train_bc.py(BC): {"algorithm": "bc", "state_dim", ..., "state_dict"} dict
    """
    import torch
    ck = torch.load(model_path, map_location="cpu", weights_only=True)
    return "bc" if isinstance(ck, dict) and ck.get("algorithm") == "bc" else "ppo"


def make_policy(args, env, worker_seed: int):
    """args.policy에 맞는 obs -> action_raw(np.float32, shape (2,)) 함수를 만든다.

    ppo / bc 출력은 [-1, 1]로 클리핑해 저장한다. 환경의 입력 범위이기도 하고,
    train_bc.py가 |action_raw| <= 1을 검증하므로 이 데이터로 바로 BC를 돌릴 수 있다.
    """
    if args.policy == "ppo":
        # test.py와 동일: train.py의 HPARAMS로 같은 구조를 만든 뒤 가중치만 덮어쓴다.
        # seed는 워커마다 다르게 (--stochastic 샘플링이 워커 간에 겹치지 않도록).
        from algorithms.ppo import PPO
        agent = PPO(obs_dim=env.observation_space.shape[0],
                    act_dim=env.action_space.shape[0],
                    **{**HPARAMS, "device": args.device, "seed": worker_seed})
        agent.load(args.model)
        deterministic = not args.stochastic   # hybrid: (μ, argmax 차선) / 샘플링

        def act(obs):
            a = agent.predict(obs, deterministic=deterministic)
            return np.clip(a, -1.0, 1.0).astype(np.float32)
        return act

    if args.policy == "bc":
        from algorithms.bc import BCPolicy
        model = BCPolicy.load(args.model, device=args.device)

        def act(obs):
            return np.clip(model.predict(obs), -1.0, 1.0).astype(np.float32)
        return act

    if args.policy == "keep-lane":
        # 완만한 가속 + 차선 유지. GUI/파이프라인 점검용.
        return lambda obs: np.asarray([0.25, 0.0], dtype=np.float32)

    # random: 가감속은 연속 uniform[-1,1], 차선변경은 {-1,0,+1} 직접 샘플링 (유지를 더 자주)
    rng = np.random.default_rng(worker_seed)

    def act(obs):
        accel = rng.uniform(-1.0, 1.0)
        lane = rng.choice(np.asarray([-1.0, 0.0, 1.0]), p=[0.15, 0.70, 0.15])
        return np.asarray([accel, lane], dtype=np.float32)
    return act


def compact(obj, ndigits: int):
    """중첩 dict/list/ndarray를 float가 ndigits 자리로 반올림된 순수 Python 객체로 바꾼다.

    float32 값을 그대로 json.dumps하면 0.10000000149011612처럼 17자리로 찍히는데,
    반올림하면 0.1이 되어 텍스트 길이가 크게 준다. numpy 스칼라/배열도 함께 변환한다.
    """
    if isinstance(obj, (float, np.floating)):
        return round(float(obj), ndigits)
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return compact(obj.tolist(), ndigits)
    if isinstance(obj, dict):
        return {k: compact(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [compact(v, ndigits) for v in obj]
    return obj


def write_tls_files(env, sumocfg, out_dir):
    """수집 시작 때 한 번: tls_index.json 과 신호 프로그램 사본(daehakro.tll.xml)을 데이터 폴더에 저장한다."""
    index = env.record_tls_index()
    with open(os.path.join(out_dir, "tls_index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    shutil.copyfile(os.path.join(os.path.dirname(os.path.abspath(sumocfg)), "daehakro.tll.xml"),
                    os.path.join(out_dir, "daehakro.tll.xml"))


def iter_transitions(jsonl_path: str):
    """저장된 JSONL(.gz 또는 평문)을 읽어, 생략된 next_observation / next_state를
    다음 레코드에서 채운 완전한 transition dict를 순서대로 yield한다.

    (수집이 중간에 끊긴 파일이면 마지막 레코드에만 next_*가 없을 수 있다.)
    """
    opener = gzip.open if jsonl_path.endswith(".gz") else open
    with opener(jsonl_path, "rt", encoding="utf-8") as f:
        prev = None
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if prev is not None:
                # done 레코드는 next_*를 이미 갖고 있으므로 setdefault가 건드리지 않는다.
                prev.setdefault("next_observation", rec["observation"])
                prev.setdefault("next_state", rec["state"])
                yield prev
            prev = rec
        if prev is not None:
            yield prev


def collect(args, sumocfg, episodes, worker_id, jsonl_path, npz_path, tag=""):
    """SUMO 인스턴스 하나로 episodes(전역 에피소드 번호 목록)를 수집해 두 파일로 저장한다.

    --workers > 1이면 이 함수가 프로세스마다 하나씩 돌고, main()이 결과를 합친다.
    반환값: 수집한 transition 수.
    """
    worker_seed = (args.seed * 1000 + worker_id) % 2**32
    if args.workers > 1:
        # 프로세스마다 torch가 코어 수만큼 스레드를 띄우면 서로 뺏는다. 관측 1개씩
        # 추론이라 1스레드면 충분.
        try:
            import torch
            torch.set_num_threads(1)
        except ImportError:
            pass

    env = SumoHighwayEnv(
        cfg_path=sumocfg,
        road=ROAD, ego=EGO,
        mdp_sim=SIMULATION, mdp_obs=OBSERVATION,
        action=ACTION, reward=REWARD,
        traffic=TRAFFIC,
        gui=args.gui,
        gui_autostart=True,
    )
    act = make_policy(args, env, worker_seed)
    # sumo_env가 SUMO --seed를 np.random(전역)에서 뽑는다. PPO 생성자가 전역 시드를
    # HPARAMS["seed"]로 되돌려 놓으므로 정책을 만든 "뒤에" 워커별로 다시 시드해야
    # 워커들이 같은 교통 패턴을 반복하지 않는다.
    np.random.seed(worker_seed)

    # NPZ는 학습에서 바로 쓰기 좋은 고정 크기 값만 모은다.
    obs_buf, next_obs_buf, action_raw_buf = [], [], []
    lane_cmd_buf, reward_buf = [], []
    term_buf, trunc_buf, episode_buf, step_buf = [], [], [], []
    # 스텝별 감지 차량 (x,y)는 한 줄로 이어 붙이고, 스텝 경계는 offsets로 기록한다.
    detected_xy_buf, detected_offsets = [], [0]

    total = 0
    tls_links = None
    # 대학로 기록 항목 중 NPZ 에 넣는 고정 길이 값
    sim_time_buf, tls_buf, collided_buf = [], [], []
    try:
        # compresslevel 6: 9와 크기 차이는 거의 없고 훨씬 빠르다.
        # 더 줄이고 싶으면 gzip.open 대신 lzma.open(..., "wt") (.jsonl.xz) —
        # 느린 대신 보통 20~30% 추가 절감.
        with gzip.open(jsonl_path, "wt", encoding="utf-8", compresslevel=6) as jf:
            for ep in episodes:
                obs, _ = env.reset(seed=args.seed + ep)
                if tls_links is None:
                    # 신호 목록·연결 수를 traci 로 읽어 기록 형식과 맞춰 본다 (다르면 멈춤)
                    tls_links = env.record_check_tls()
                    if worker_id == 0:
                        write_tls_files(env, sumocfg, os.path.dirname(os.path.abspath(jsonl_path)))
                state_t = env.get_privileged_state_daehakro()
                done = False
                t = 0
                ep_return = 0.0

                while not done:
                    # 이번 관측 시점에 시야(W) 안에 들어온 차량들의 좌표.
                    # 관측 벡터와 별도로 저장하는 부가 데이터 (분석/시각화용).
                    detected = env.get_detected_vehicles()
                    action = act(obs)
                    next_obs, reward, terminated, truncated, info = env.step(action)
                    state_tp1 = env.get_privileged_state_daehakro()
                    done = terminated or truncated

                    record = {
                        "episode": int(ep),
                        "t": t,
                        "observation": compact(obs, args.ndigits),
                        # 스칼라 몇 개는 용량에 영향이 없으니 반올림하지 않는다.
                        "action_raw": np.asarray(action, dtype=float).tolist(),
                        "action": {
                            "accel_raw": float(info["accel_raw"]),
                            "lane_change_raw": float(info["lane_change_raw"]),
                            "lane_change": int(info["lane_change"]),
                            "lane_change_applied": bool(info["lane_change_applied"]),
                        },
                        "reward": float(reward),
                        "terminated": bool(terminated),
                        "truncated": bool(truncated),
                        "state": compact(state_t, args.ndigits),
                        # 감지 차량 좌표 (관측과 같은 시점 t 기준)
                        "detected_vehicles": compact(detected, args.ndigits),
                        "event": {
                            "collided": bool(info["collided"]),
                            "arrived": bool(info["arrived"]),
                            "lane_before": info["lane_before"],
                            "lane_after": info["lane_after"],
                            "collision_with": info.get("collision_with"),
                        },
                    }
                    if done:
                        # 중간 스텝의 next_*는 다음 레코드의 observation/state와 같으므로
                        # 에피소드 마지막 스텝에만 기록한다 (iter_transitions가 복원).
                        record["next_observation"] = compact(next_obs, args.ndigits)
                        record["next_state"] = compact(state_tp1, args.ndigits)
                    jf.write(json.dumps(record, ensure_ascii=False,
                                        separators=(",", ":")) + "\n")

                    obs_buf.append(np.asarray(obs, dtype=np.float32))
                    next_obs_buf.append(np.asarray(next_obs, dtype=np.float32))
                    action_raw_buf.append(np.asarray(action, dtype=np.float32))
                    lane_cmd_buf.append(int(info["lane_change"]))
                    reward_buf.append(float(reward))
                    term_buf.append(bool(terminated))
                    trunc_buf.append(bool(truncated))
                    episode_buf.append(int(ep))
                    step_buf.append(t)
                    detected_xy_buf.extend((d["x"], d["y"]) for d in detected)
                    detected_offsets.append(len(detected_xy_buf))
                    sim_time_buf.append(float(state_t["sim_time"]))
                    tls_buf.append([x for tid in env.RECORD_TLS_ORDER for x in state_t["tls"][tid]])
                    collided_buf.append(bool(info["collided"]))

                    total += 1
                    ep_return += reward
                    t += 1
                    obs = next_obs
                    state_t = state_tp1  # 스텝 끝의 상태 = 다음 스텝 시작의 상태

                print(f"{tag}episode {ep + 1:4d}/{args.episodes} | "
                      f"steps={t:4d} return={ep_return:8.3f}", flush=True)
    finally:
        env.close()

    np.savez_compressed(
        npz_path,
        observation=np.asarray(obs_buf, dtype=np.float32).reshape(total, -1),
        action_raw=np.asarray(action_raw_buf, dtype=np.float32).reshape(total, -1),
        lane_change=np.asarray(lane_cmd_buf, dtype=np.int8),
        reward=np.asarray(reward_buf, dtype=np.float32),
        next_observation=np.asarray(next_obs_buf, dtype=np.float32).reshape(total, -1),
        terminated=np.asarray(term_buf, dtype=np.bool_),
        truncated=np.asarray(trunc_buf, dtype=np.bool_),
        episode=np.asarray(episode_buf, dtype=np.int32),
        t=np.asarray(step_buf, dtype=np.int32),
        # 감지 차량 (x,y)를 전 스텝에 걸쳐 이어 붙인 (M, 2) float32.
        # 스텝 i의 좌표: detected_xy[detected_offsets[i]:detected_offsets[i+1]]
        detected_xy=np.asarray(detected_xy_buf, dtype=np.float32).reshape(-1, 2),
        detected_offsets=np.asarray(detected_offsets, dtype=np.int64),
        # 대학로 기록 항목 (고정 길이)
        sim_time=np.asarray(sim_time_buf, dtype=np.float64),
        tls=np.asarray(tls_buf, dtype=np.float32).reshape(total, sum(tls_links.values()) if tls_links else 0),
        collided=np.asarray(collided_buf, dtype=np.bool_),
    )
    return total


def merge_parts(parts, jsonl_path, npz_path):
    """워커별 부분 파일들을 하나로 합치고 부분 파일은 지운다."""
    # gzip은 멤버를 이어 붙인 파일도 유효하므로 바이트 그대로 연결한다.
    with open(jsonl_path, "wb") as out:
        for part_jsonl, _ in parts:
            with open(part_jsonl, "rb") as f:
                shutil.copyfileobj(f, out)
            os.remove(part_jsonl)

    arrays, xy, offsets, base = {}, [], [], 0
    for _, part_npz in parts:
        with np.load(part_npz) as d:
            for key in d.files:
                if key not in ("detected_xy", "detected_offsets"):
                    arrays.setdefault(key, []).append(d[key])
            xy.append(d["detected_xy"])
            off = d["detected_offsets"]
            offsets.append(off[:-1] + base)   # 부분 파일의 offset을 전체 기준으로 옮김
            base += int(off[-1])
        os.remove(part_npz)
    merged = {key: np.concatenate(v) for key, v in arrays.items()}
    merged["detected_xy"] = np.concatenate(xy).reshape(-1, 2)
    merged["detected_offsets"] = np.concatenate(
        offsets + [np.asarray([base], dtype=np.int64)]).astype(np.int64)
    np.savez_compressed(npz_path, **merged)


def main():
    parser = argparse.ArgumentParser(description="대학로 POMDP 데이터 수집 (수업 collect_pomdp_data.py + 대학로 기록 항목)")
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--policy", choices=["random", "keep-lane", "ppo", "bc"], default=None,
                        help="행동 정책. 생략 시 --model이 있으면 파일을 보고 ppo/bc 자동 판별, "
                             "없으면 random")
    parser.add_argument("--model", default=None,
                        help="train.py(PPO) 또는 train_bc.py(BC)가 저장한 model.pt. "
                             "주면 그 학습된 정책으로 수집한다")
    parser.add_argument("--stochastic", action="store_true",
                        help="ppo: 결정적(μ, argmax 차선) 대신 분포에서 샘플링해서 행동. "
                             "상태 다양성이 필요할 때")
    parser.add_argument("--device", default="cpu",
                        help="정책 추론 장치 (cpu/cuda). 관측 1개씩 추론이라 cpu로 충분")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--gui", action="store_true",
                        help="SUMO GUI로 수집. 기본은 headless")
    parser.add_argument("--workers", type=int, default=1,
                        help="병렬 SUMO 인스턴스 수. 코어 수만큼 주면 거의 그 배수로 빨라진다. "
                             "(--gui면 1로 고정)")
    parser.add_argument("--out-dir", default=os.path.join(BASE, "data"))
    parser.add_argument("--name", default=None,
                        help="출력 basename. 생략 시 날짜/시각 자동 생성")
    parser.add_argument("--ndigits", type=int, default=4,
                        help="JSONL의 observation/state/detected float 소수 자릿수 "
                             "(NPZ에는 영향 없음)")
    args = parser.parse_args()
    if args.policy in ("ppo", "bc") and args.model is None:
        parser.error(f"--policy {args.policy}에는 --model이 필요합니다.")
    if args.model is not None and not os.path.exists(args.model):
        parser.error(f"모델 파일이 없습니다: {args.model}")
    if args.policy is None:
        args.policy = detect_algorithm(args.model) if args.model else "random"
    if args.model:
        print(f"정책: {args.policy} ({args.model})"
              + (" [stochastic]" if args.stochastic and args.policy == "ppo" else ""))
    workers = 1 if args.gui else max(1, min(args.workers, args.episodes))

    os.makedirs(args.out_dir, exist_ok=True)
    name = args.name or datetime.now().strftime("pomdp_%Y%m%d_%H%M%S")
    jsonl_path = os.path.join(args.out_dir, name + ".jsonl.gz")
    npz_path = os.path.join(args.out_dir, name + ".npz")

    # 도로 파일은 부모에서 한 번만 생성한다 (워커들이 동시에 쓰면 파일이 깨진다).
    sumocfg = road_builder.build(ROAD, EGO, TRAFFIC,
                                 os.path.join(BASE, "env", "sumo"))

    t0 = time.time()
    if workers == 1:
        total = collect(args, sumocfg, list(range(args.episodes)), 0,
                        jsonl_path, npz_path)
    else:
        chunks = [c.tolist() for c in np.array_split(np.arange(args.episodes), workers)]
        parts = [(os.path.join(args.out_dir, f".{name}.w{w}.jsonl.gz"),
                  os.path.join(args.out_dir, f".{name}.w{w}.npz"))
                 for w in range(workers)]
        jobs = [(args, sumocfg, chunks[w], w, parts[w][0], parts[w][1], f"[w{w}] ")
                for w in range(workers)]
        # spawn: 워커마다 깨끗한 프로세스에서 SUMO(libsumo)를 하나씩 띄운다.
        with multiprocessing.get_context("spawn").Pool(workers) as pool:
            total = sum(pool.starmap(collect, jobs))
        merge_parts(parts, jsonl_path, npz_path)
    elapsed = time.time() - t0

    mb = lambda p: os.path.getsize(p) / 2**20  # noqa: E731
    print("\n수집 완료")
    print(f"  transitions: {total}  ({elapsed:.1f}s, {total / max(elapsed, 1e-9):.0f} step/s, "
          f"workers={workers})")
    print(f"  JSONL(full POMDP + privileged state): {jsonl_path} ({mb(jsonl_path):.1f} MB)")
    print(f"  NPZ(training-friendly):               {npz_path} ({mb(npz_path):.1f} MB)")
    print(f"  신호 정보: {os.path.join(args.out_dir, 'tls_index.json')}, {os.path.join(args.out_dir, 'daehakro.tll.xml')}")


if __name__ == "__main__":
    main()