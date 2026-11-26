"""제출용 주행 데이터 수집 — 최종 모델이 달린 기록을 숫자 배열로 묶음 파일에 저장한다.

    python collect_fast.py --machine 1 --test      # 먼저: 속도·용량 시험 (2~3분). 오류가 없는지 본다
    python collect_fast.py --machine 1             # 본 수집. 이 기기의 몫을 다 모으면 스스로 끝난다
    python collect_fast.py --status                # 지금까지 모은 양

기기 번호와 몫 (세 대가 서로 다른 주행을 모은다. 번호가 같으면 같은 주행이 두 번 저장된다)
    1번  윈도우 (시험 194 스텝/s) 4,800,000 스텝
    2번  맥북 (시험 133 스텝/s)   3,300,000 스텝
    3번  윈도우 (시험  98 스텝/s) 2,400,000 스텝        합계 10,500,000 스텝, 세 대가 거의 같은 시각(약 7시간 뒤)에 끝난다
  몫을 바꾸려면 --target 스텝수. 한 대가 못 채우면 다른 기기에서 --target 을 늘려 다시 실행하면 이어서 모은다.

· 모델은 기본으로 models/ppo_track.pt (최종 PPO). 다른 모델을 쓰려면 파일을 맨 앞에 적는다.
· SUMO 를 --workers 개 띄우고, 각자 --episodes 판(기본 20)을 달릴 때마다 파일 하나를 쓴다:
      data_final/final_m<기기>_w<워커>_c<묶음>.npz
  중간에 끊겨도 끝난 묶음은 남는다. 같은 명령을 다시 실행하면 끝난 묶음은 건너뛰고 이어서 한다.
· 멈추기: Ctrl+C. 지금 묶음까지만 하고 멈추려면 이 폴더에 STOP 이라는 빈 파일을 만든다.
· 디스크 여유가 --min-free-gb (기본 5) 아래로 내려가면 스스로 멈춘다.
· 윈도우에서는 도는 동안 절전으로 들어가지 않게 막는다 (덮개를 닫으면 잠든다. 열어 둔다). 맥은 앞에 caffeinate -i 를 붙인다.
· Parquet 으로는 수집이 끝난 뒤 한 번에 바꾼다 (정보 손실 없음. 수집 중에는 numpy 만 쓴다).

수업 수집기(collect_pomdp_data_daehakro.py)와 다른 점
  1. 문자열(차량 id, 차로 id, 차종)을 번호로 바꿔 저장한다. 번호표는 파일마다 같이 들어 있다 (names / lanes / types / places).
  2. 길이를 0.01 m, 속도를 0.01 m/s 단위의 정수로 저장한다 (수업 수집기는 소수 넷째 자리).
  3. 모든 차의 상태를 SUMO 에서 한 번에 받아 온다 (구독). 수업 수집기는 차 한 대, 값 하나마다 따로 물어서 느리다.
     값이 같은지는 --check 로 확인한다 (50 스텝마다 수업 방식으로도 읽어 견준다).
  4. next_observation 과 next_state 는 수업 수집기처럼 판의 마지막 스텝 것만 저장한다 (final_observation, fin_*).
     나머지 스텝의 next_* 는 다음 줄의 observation / state 와 같다.

파일 안의 배열 (N = 스텝 수, 한 줄이 한 스텝)
  스텝        episode, t, observation(N,50), action_raw(N,2), accel_raw, lane_change_raw, lane_change, lane_change_applied,
              reward, terminated, truncated, collided, arrived, lane_before, lane_after (없으면 -1), collision_with(이름 번호, 없으면 -1),
              sim_time, tls(N,137: 1 초록 / 0 노랑 / -1 빨강, tls_index.json 의 순서)
  AV          ego_x, ego_y, ego_lane_pos (cm), ego_speed (cm/s), ego_lane (차로 번호), ego_lane_code (lanes 의 번호)
  다른 차     veh_off(N+1): 스텝 i 의 차는 veh_*[veh_off[i]:veh_off[i+1]]
              veh_name, veh_x, veh_y, veh_lane_pos (cm), veh_speed (cm/s), veh_lane, veh_lane_code, veh_type, veh_stopped,
              veh_signals, veh_assist      (road_id 는 lane_id 에서 마지막 '_번호' 를 뗀 것)
  보행자      per_off(N+1), per_name, per_child, per_x, per_y (cm), per_speed (cm/s), per_place (places 의 번호)   — AV 둘레 50 m
  상충 차량   foe_off(N+1), foe_name, foe_my_dist, foe_dist (cm), foe_i_yield
  감지 차량   det_off(N+1), det_name, det_rel_pos (cm), det_lane_offset      — 관측 시야에 든 차 (x, y, 속도는 '다른 차'에 있다)
  판          ep_id(E), ep_steps(E), final_observation(E,50)
  판이 끝난 뒤의 state (마지막 스텝의 next_state. 한 줄이 한 판)
              fin_ego_alive, fin_sim_time, fin_tls(E,137), fin_ego_x, fin_ego_y, fin_ego_lane_pos, fin_ego_speed,
              fin_ego_lane, fin_ego_lane_code      — AV 가 도로에 없으면(도착해서 사라짐) fin_ego_alive = 0 이고 AV 값은 0, 차로 번호는 -1
              fin_veh_off(E+1) + fin_veh_*, fin_per_off(E+1) + fin_per_*, fin_foe_off(E+1) + fin_foe_*
              — AV 가 도로에 남아 있을 때만 채운다 (수업 수집기의 get_privileged_state 와 같다)
  번호표      names, lanes, types, places (문자열 배열), meta (json 문자열: 모델, 기기, seed, 가림 설정 등)
"""
import argparse
import glob
import json
import multiprocessing as mp
import os
import shutil
import sys
import time

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = "data_final"
CM = 100.0
DEFAULT_MODEL = os.path.join("models", "ppo_track.pt")
TARGET = {1: 4_800_000, 2: 3_300_000, 3: 2_400_000}      # 기기 번호 → 모을 스텝 수 (시험 속도 194 : 133 : 98 에 맞춘 몫)
COUNT = None                                               # 이 기기가 지금까지 모은 스텝 수 (워커들이 같이 쓴다)


def _init(count):
    global COUNT
    COUNT = count


def to_cm(x):
    return int(round(float(x) * CM))


class Table:
    """문자열 → 번호 (처음 나온 순서)."""

    def __init__(self, items=()):
        self.idx, self.items = {}, []
        for it in items:
            self(it)

    def __call__(self, s):
        i = self.idx.get(s)
        if i is None:
            i = self.idx[s] = len(self.items)
            self.items.append(s)
        return i


class Flat:
    """길이가 스텝마다 다른 목록을 한 줄로 이어 붙인다."""

    def __init__(self, cols):
        self.cols = {name: [] for name in cols}
        self.off = [0]

    def close_step(self):
        self.off.append(len(next(iter(self.cols.values()))))


VEH = {"veh_name": np.int32, "veh_x": np.int32, "veh_y": np.int32, "veh_lane_pos": np.int32, "veh_speed": np.int16,
       "veh_lane": np.int8, "veh_lane_code": np.int16, "veh_type": np.int16, "veh_stopped": np.bool_,
       "veh_signals": np.int16, "veh_assist": np.int8}
PER = {"per_name": np.int32, "per_child": np.int8, "per_x": np.int32, "per_y": np.int32, "per_speed": np.int16,
       "per_place": np.int16}
FOE = {"foe_name": np.int32, "foe_my_dist": np.int32, "foe_dist": np.int32, "foe_i_yield": np.int8}
DET = {"det_name": np.int32, "det_rel_pos": np.int32, "det_lane_offset": np.int8}
FIN = {"fin_ego_alive": np.bool_, "fin_sim_time": np.float32, "fin_ego_x": np.int32, "fin_ego_y": np.int32,
       "fin_ego_lane_pos": np.int32, "fin_ego_speed": np.int16, "fin_ego_lane": np.int8, "fin_ego_lane_code": np.int16}
STEP = {"episode": np.int64, "t": np.int32, "accel_raw": np.float32, "lane_change_raw": np.float32, "lane_change": np.int8,
        "lane_change_applied": np.bool_, "reward": np.float32, "terminated": np.bool_, "truncated": np.bool_,
        "collided": np.bool_, "arrived": np.bool_, "lane_before": np.int8, "lane_after": np.int8,
        "collision_with": np.int32, "sim_time": np.float32, "ego_x": np.int32, "ego_y": np.int32,
        "ego_lane_pos": np.int32, "ego_speed": np.int16, "ego_lane": np.int8, "ego_lane_code": np.int16}


def worker(a):
    model, machine, wid, chunks, episodes, check, radius, policy_kind, out_dir, test, min_free, target = a
    os.chdir(BASE)
    sys.path.insert(0, BASE)
    try:
        import torch
        torch.set_num_threads(1)
    except ImportError:
        pass
    import collect_pomdp_data_daehakro as C          # 수업 수집기의 환경 설정·정책 불러오기를 그대로 쓴다
    from env import daehakro_env
    traci = daehakro_env.traci
    tc = traci.constants
    VARS = [tc.VAR_POSITION, tc.VAR_SPEED, tc.VAR_LANE_INDEX, tc.VAR_LANE_ID, tc.VAR_LANEPOSITION, tc.VAR_TYPE,
            tc.VAR_SIGNALS, tc.VAR_STOPSTATE]

    sumocfg = daehakro_env.build()
    env = C.SumoHighwayEnv(cfg_path=sumocfg, road=C.ROAD, ego=C.EGO, mdp_sim=C.SIMULATION, mdp_obs=C.OBSERVATION,
                           action=C.ACTION, reward=C.REWARD, traffic=C.TRAFFIC, gui=False, gui_autostart=True)
    kind = policy_kind or C.detect_algorithm(model)
    pargs = argparse.Namespace(policy=kind, model=model, device="cpu", stochastic=False)
    act = C.make_policy(pargs, env, (machine * 1000 + wid) % 2**32)
    obs_dim = env.observation_space.shape[0]

    subscribed, last_time = set(), [-1.0]

    def all_vehicles():
        """구독으로 모든 차의 상태를 한 번에 받는다. Returns {id: {변수: 값}} (AV 제외)."""
        now = traci.simulation.getTime()
        if now < last_time[0]:                       # SUMO 를 다시 띄웠다 → 구독이 사라졌다
            subscribed.clear()
        last_time[0] = now
        ids = traci.vehicle.getIDList()
        for vid in ids:
            if vid != env.ego_id and vid not in subscribed:
                traci.vehicle.subscribe(vid, VARS)
                subscribed.add(vid)
        res = traci.vehicle.getAllSubscriptionResults()
        if len(subscribed) > 4 * len(ids) + 200:
            subscribed.intersection_update(ids)
        return {vid: r for vid, r in res.items() if vid != env.ego_id and r}

    done_steps = 0
    try:
        tls_ok = False
        for c in range(chunks):
            if os.path.exists(os.path.join(BASE, "STOP")):
                print(f"[w{wid}] STOP 파일이 있어 멈춥니다", flush=True)
                break
            if shutil.disk_usage(out_dir).free < min_free * 2**30:
                print(f"[w{wid}] 디스크 여유가 부족해 멈춥니다", flush=True)
                break
            path = os.path.join(out_dir, f"final_m{machine:02d}_w{wid:02d}_c{c:04d}.npz")
            if os.path.exists(path):
                continue
            if target and COUNT is not None and COUNT.value >= target:
                print(f"[w{wid}] 이 기기의 몫 {target:,} 스텝을 채워 멈춥니다", flush=True)
                break
            seed = (machine * 1_000_000 + wid * 10_000 + c) % 2**32
            np.random.seed(seed)                     # sumo_env 가 SUMO 의 seed 를 여기서 뽑는다
            names, lanes, types, places = Table(), Table(), Table(), Table()
            S = {k: [] for k in STEP}
            obs_buf, act_buf, tls_buf, final_obs, ep_id, ep_steps = [], [], [], [], [], []
            veh, per, foe, det = Flat(VEH), Flat(PER), Flat(FOE), Flat(DET)
            fveh, fper, ffoe = Flat(VEH), Flat(PER), Flat(FOE)       # 판이 끝난 뒤의 state
            FS, fin_tls = {k: [] for k in FIN}, []
            t0, checked, worst = time.time(), 0, 0.0
            for e in range(episodes):
                gid = machine * 10_000_000 + wid * 100_000 + c * 100 + e
                obs, _ = env.reset(seed=seed * 100 + e)
                if not tls_ok:
                    env.record_check_tls()
                    if wid == 0:
                        C.write_tls_files(env, sumocfg, out_dir)
                    tls_ok = True
                done, t = False, 0
                while not done:
                    # ── 시점 t 의 state (행동을 정하기 전) ──
                    ego = env.ego_id
                    ex, ey = traci.vehicle.getPosition(ego)
                    lane_id = traci.vehicle.getLaneID(ego)
                    S["ego_x"].append(to_cm(ex)); S["ego_y"].append(to_cm(ey))
                    S["ego_speed"].append(to_cm(traci.vehicle.getSpeed(ego)))
                    S["ego_lane"].append(traci.vehicle.getLaneIndex(ego))
                    S["ego_lane_code"].append(lanes(lane_id))
                    S["ego_lane_pos"].append(to_cm(traci.vehicle.getLanePosition(ego)))
                    S["sim_time"].append(traci.simulation.getTime())
                    row = []
                    for tl in env.RECORD_TLS_ORDER:
                        row.extend(env.RECORD_TLS_CODE[ch] for ch in traci.trafficlight.getRedYellowGreenState(tl))
                    tls_buf.append(row)
                    vs = all_vehicles()
                    for vid, r in vs.items():
                        x, y = r[tc.VAR_POSITION]
                        if radius > 0 and (x - ex) ** 2 + (y - ey) ** 2 > radius * radius:
                            continue
                        cc = veh.cols
                        cc["veh_name"].append(names(vid)); cc["veh_x"].append(to_cm(x)); cc["veh_y"].append(to_cm(y))
                        cc["veh_speed"].append(to_cm(r[tc.VAR_SPEED])); cc["veh_lane"].append(r[tc.VAR_LANE_INDEX])
                        cc["veh_lane_code"].append(lanes(r[tc.VAR_LANE_ID]))
                        cc["veh_lane_pos"].append(to_cm(r[tc.VAR_LANEPOSITION]))
                        cc["veh_type"].append(types(r[tc.VAR_TYPE])); cc["veh_stopped"].append(bool(r[tc.VAR_STOPSTATE] & 1))
                        cc["veh_signals"].append(r[tc.VAR_SIGNALS]); cc["veh_assist"].append(env.record_assist(vid))
                    veh.close_step()
                    try:
                        persons, foes = env.record_persons(), env.record_junction_foes()
                    except traci.TraCIException:
                        persons, foes = [], []
                    for p, child, x, y, v, place in persons:
                        cc = per.cols
                        cc["per_name"].append(names(p)); cc["per_child"].append(child); cc["per_x"].append(to_cm(x))
                        cc["per_y"].append(to_cm(y)); cc["per_speed"].append(to_cm(v)); cc["per_place"].append(places(place))
                    per.close_step()
                    for f, my_d, f_d, i_yield in foes:
                        cc = foe.cols
                        cc["foe_name"].append(names(f)); cc["foe_my_dist"].append(to_cm(my_d))
                        cc["foe_dist"].append(to_cm(f_d)); cc["foe_i_yield"].append(i_yield)
                    foe.close_step()
                    for d in env.get_detected_vehicles():
                        cc = det.cols
                        cc["det_name"].append(names(d["id"])); cc["det_rel_pos"].append(to_cm(d["rel_pos"]))
                        cc["det_lane_offset"].append(int(d["lane_offset"]))
                    det.close_step()
                    if check and t % 50 == 0:        # 수업 방식으로도 읽어 견준다
                        ref = {v["id"]: v for v in env.get_privileged_state_daehakro().get("vehicles", [])}
                        if set(ref) != set(vs):
                            raise RuntimeError(f"차 목록이 다릅니다: 수업 방식 {len(ref)}대, 구독 {len(vs)}대")
                        for vid, v in ref.items():
                            r = vs[vid]
                            worst = max(worst, abs(v["x"] - r[tc.VAR_POSITION][0]), abs(v["y"] - r[tc.VAR_POSITION][1]),
                                        abs(v["speed"] - r[tc.VAR_SPEED]), abs(v["lane_pos"] - r[tc.VAR_LANEPOSITION]))
                            if (v["lane_id"] != r[tc.VAR_LANE_ID] or v["type_id"] != r[tc.VAR_TYPE]
                                    or v["stopped"] != bool(r[tc.VAR_STOPSTATE] & 1) or v["signals"] != r[tc.VAR_SIGNALS]):
                                raise RuntimeError(f"{vid} 의 값이 수업 방식과 다릅니다")
                        if worst > 1e-3:
                            raise RuntimeError(f"수업 방식과 값이 {worst} 만큼 다릅니다")
                        checked += 1
                    # ── 행동 ──
                    action = act(obs)
                    nxt, reward, term, trunc, info = env.step(action)
                    done = term or trunc
                    obs_buf.append(np.asarray(obs, np.float32)); act_buf.append(np.asarray(action, np.float32))
                    S["episode"].append(gid); S["t"].append(t)
                    S["accel_raw"].append(info["accel_raw"]); S["lane_change_raw"].append(info["lane_change_raw"])
                    S["lane_change"].append(info["lane_change"]); S["lane_change_applied"].append(info["lane_change_applied"])
                    S["reward"].append(reward); S["terminated"].append(term); S["truncated"].append(trunc)
                    S["collided"].append(info["collided"]); S["arrived"].append(info["arrived"])
                    S["lane_before"].append(-1 if info["lane_before"] is None else int(info["lane_before"]))
                    S["lane_after"].append(-1 if info["lane_after"] is None else int(info["lane_after"]))
                    who = info.get("collision_with")
                    S["collision_with"].append(names(who) if who else -1)
                    obs, t = nxt, t + 1
                final_obs.append(np.asarray(obs, np.float32)); ep_id.append(gid); ep_steps.append(t)
                # ── 판이 끝난 뒤의 state (마지막 스텝의 next_state) ──
                ego = env.ego_id
                alive = ego in traci.vehicle.getIDList()
                FS["fin_ego_alive"].append(alive); FS["fin_sim_time"].append(traci.simulation.getTime())
                row = []
                for tl in env.RECORD_TLS_ORDER:
                    row.extend(env.RECORD_TLS_CODE[ch] for ch in traci.trafficlight.getRedYellowGreenState(tl))
                fin_tls.append(row)
                n_fin = 0
                if alive:
                    ex, ey = traci.vehicle.getPosition(ego)
                    FS["fin_ego_x"].append(to_cm(ex)); FS["fin_ego_y"].append(to_cm(ey))
                    FS["fin_ego_speed"].append(to_cm(traci.vehicle.getSpeed(ego)))
                    FS["fin_ego_lane"].append(traci.vehicle.getLaneIndex(ego))
                    FS["fin_ego_lane_code"].append(lanes(traci.vehicle.getLaneID(ego)))
                    FS["fin_ego_lane_pos"].append(to_cm(traci.vehicle.getLanePosition(ego)))
                    for vid, r in all_vehicles().items():
                        x, y = r[tc.VAR_POSITION]
                        if radius > 0 and (x - ex) ** 2 + (y - ey) ** 2 > radius * radius:
                            continue
                        cc = fveh.cols
                        cc["veh_name"].append(names(vid)); cc["veh_x"].append(to_cm(x)); cc["veh_y"].append(to_cm(y))
                        cc["veh_speed"].append(to_cm(r[tc.VAR_SPEED])); cc["veh_lane"].append(r[tc.VAR_LANE_INDEX])
                        cc["veh_lane_code"].append(lanes(r[tc.VAR_LANE_ID]))
                        cc["veh_lane_pos"].append(to_cm(r[tc.VAR_LANEPOSITION]))
                        cc["veh_type"].append(types(r[tc.VAR_TYPE])); cc["veh_stopped"].append(bool(r[tc.VAR_STOPSTATE] & 1))
                        cc["veh_signals"].append(r[tc.VAR_SIGNALS]); cc["veh_assist"].append(env.record_assist(vid))
                        n_fin += 1
                    try:
                        persons, foes = env.record_persons(), env.record_junction_foes()
                    except traci.TraCIException:
                        persons, foes = [], []
                    for p, child, x, y, v, place in persons:
                        cc = fper.cols
                        cc["per_name"].append(names(p)); cc["per_child"].append(child); cc["per_x"].append(to_cm(x))
                        cc["per_y"].append(to_cm(y)); cc["per_speed"].append(to_cm(v)); cc["per_place"].append(places(place))
                    for f, my_d, f_d, i_yield in foes:
                        cc = ffoe.cols
                        cc["foe_name"].append(names(f)); cc["foe_my_dist"].append(to_cm(my_d))
                        cc["foe_dist"].append(to_cm(f_d)); cc["foe_i_yield"].append(i_yield)
                else:
                    for k in ("fin_ego_x", "fin_ego_y", "fin_ego_speed", "fin_ego_lane", "fin_ego_lane_pos"):
                        FS[k].append(0)
                    FS["fin_ego_lane_code"].append(-1)
                fveh.close_step(); fper.close_step(); ffoe.close_step()
                if check:                            # 수업 방식의 next_state 와 견준다
                    ref = env.get_privileged_state_daehakro()
                    if bool(ref.get("ego_alive")) != alive:
                        raise RuntimeError("판이 끝난 뒤 AV 가 남아 있는지가 수업 방식과 다릅니다")
                    if alive and radius <= 0 and len(ref.get("vehicles", [])) != n_fin:
                        raise RuntimeError(f"판이 끝난 뒤의 차 수가 다릅니다: 수업 방식 {len(ref.get('vehicles', []))}, 구독 {n_fin}")
            n = len(S["t"])
            data = {k: np.asarray(v, STEP[k]) for k, v in S.items()}
            data["observation"] = np.asarray(obs_buf, np.float32).reshape(n, obs_dim)
            data["action_raw"] = np.asarray(act_buf, np.float32).reshape(n, 2)
            data["tls"] = np.asarray(tls_buf, np.int8)
            for flat, spec, key in ((veh, VEH, "veh_off"), (per, PER, "per_off"), (foe, FOE, "foe_off"), (det, DET, "det_off")):
                data[key] = np.asarray(flat.off, np.int64)
                for k, dt in spec.items():
                    data[k] = np.asarray(flat.cols[k], dt)
            data["ep_id"] = np.asarray(ep_id, np.int64); data["ep_steps"] = np.asarray(ep_steps, np.int32)
            for k, dt in FIN.items():
                data[k] = np.asarray(FS[k], dt)
            data["fin_tls"] = np.asarray(fin_tls, np.int8)
            for flat, spec, key in ((fveh, VEH, "fin_veh_off"), (fper, PER, "fin_per_off"), (ffoe, FOE, "fin_foe_off")):
                data[key] = np.asarray(flat.off, np.int64)
                for k, dt in spec.items():
                    data["fin_" + k] = np.asarray(flat.cols[k], dt)
            data["final_observation"] = np.asarray(final_obs, np.float32).reshape(len(final_obs), obs_dim)
            for k, tb in (("names", names), ("lanes", lanes), ("types", types), ("places", places)):
                data[k] = np.asarray(tb.items if tb.items else [""], dtype=str)
            data["meta"] = np.asarray(json.dumps({
                "model": os.path.relpath(model, BASE) if os.path.isabs(model) else model, "policy": kind, "machine": machine,
                "worker": wid, "chunk": c, "seed": seed, "episodes": episodes, "radius": radius,
                "occlusion": bool(getattr(env, "occlusion", True)), "obs_dim": obs_dim, "format": 2,
                "length_unit": "cm", "speed_unit": "cm/s", "created": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False))
            tmp = path + ".tmp.npz"
            np.savez_compressed(tmp, **data)
            os.replace(tmp, path)
            dt = time.time() - t0
            done_steps += n
            total = None
            if COUNT is not None:
                with COUNT.get_lock():
                    COUNT.value += n
                    total = COUNT.value
            arrive = int(np.sum(data["arrived"] & ~data["collided"]))
            print(f"[w{wid}] 묶음 {c}: {episodes}판 {n:,} 스텝, {dt:.0f}초 ({n / dt:.1f} 스텝/s), 도착 {arrive}/{episodes}, "
                  f"파일 {os.path.getsize(path) / 2**20:.1f} MB ({os.path.getsize(path) / max(n, 1) / 1024:.2f} KB/스텝), "
                  f"차 {len(data['veh_name']) / max(n, 1):.0f}대/스텝" + (f", 수업 방식과 견준 {checked}번 모두 같음" if check else "")
                  + (f" | 이 기기 합계 {total:,}" + (f" / {target:,} ({total / target:.1%})" if target else "") if total is not None else ""),
                  flush=True)
            if test:
                break
    finally:
        env.close()
    return done_steps



def count_machine(out_dir, machine):
    n = 0
    for p in glob.glob(os.path.join(out_dir, f"final_m{machine:02d}_w*_c*.npz")):
        try:
            with np.load(p) as d:
                n += len(d["t"])
        except Exception:
            print(f"  읽지 못한 파일 (지우고 다시 실행하면 그 묶음을 다시 모은다): {p}", flush=True)
    return n


def ensure_road():
    """도로·교통 파일을 SUMO 들을 띄우기 전에 한 번만 준비한다.
    (처음 받은 폴더에서는 도로 파일을 새로 만든다. 여러 SUMO 가 동시에 만들면 쓰는 중인 파일을 읽어 죽는다.)"""
    import xml.etree.ElementTree as ET
    sys.path.insert(0, BASE)
    from env import daehakro_env, daehakro_builder
    cfg = daehakro_env.build()
    folder = os.path.dirname(cfg)
    try:
        for name in ("daehakro.net.xml", "daehakro.rou.xml", "daehakro.sumocfg"):
            ET.parse(os.path.join(folder, name))
    except Exception:
        print("도로 파일이 깨져 있어 다시 만듭니다", flush=True)
        cfg = daehakro_builder.build(verbose=False)
    return cfg


def keep_awake():
    """윈도우: 도는 동안 절전으로 들어가지 않게 한다. 다른 곳에서는 아무 일도 하지 않는다."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        except Exception:
            pass


def status(out_dir):
    files = sorted(glob.glob(os.path.join(out_dir, "final_m*_w*_c*.npz")))
    per = {}
    for p in files:
        m = os.path.basename(p).split("_")[1]
        with np.load(p) as d:
            n, e, a = len(d["t"]), len(d["ep_id"]), int(np.sum(d["arrived"] & ~d["collided"]))
        s = per.setdefault(m, [0, 0, 0, 0, 0])
        s[0] += n; s[1] += e; s[2] += a; s[3] += os.path.getsize(p); s[4] += 1
    tot = [sum(s[i] for s in per.values()) for i in range(5)]
    for m, s in sorted(per.items()):
        goal = TARGET.get(int(m[1:]))
        print(f"  기기 {m}: {s[0]:>11,} 스텝 | {s[1]:>6,}판 (도착 {s[2] / max(s[1], 1):.1%}) | {s[3] / 2**30:6.2f} GB | 파일 {s[4]}개"
              + (f" | 몫 {goal:,} 의 {s[0] / goal:.1%}" if goal else ""))
    print(f"  합계   : {tot[0]:>11,} 스텝 | {tot[1]:>6,}판 (도착 {tot[2] / max(tot[1], 1):.1%}) | {tot[3] / 2**30:6.2f} GB | 파일 {tot[4]}개"
          f" | 10,000,000 스텝의 {tot[0] / 1e7:.1%}")
    return tot[0]


def main():
    ap = argparse.ArgumentParser(description="제출용 주행 데이터 수집 (빠른 판)")
    ap.add_argument("model", nargs="?", default=None, help=f"모델 파일 (BC·PPO). 생략하면 {DEFAULT_MODEL}")
    ap.add_argument("--machine", type=int, default=None, help="기기 번호 (노트북마다 다르게: 1, 2, 3, ...)")
    ap.add_argument("--workers", type=int, default=max(2, min(8, (os.cpu_count() or 4) - 2)), help="동시에 돌릴 SUMO 수")
    ap.add_argument("--episodes", type=int, default=20, help="묶음 하나(파일 하나)에 담는 판 수 (SUMO 하나당)")
    ap.add_argument("--chunks", type=int, default=100000, help="SUMO 하나가 모을 묶음 수 (기본: 멈출 때까지)")
    ap.add_argument("--radius", type=float, default=0.0, help="AV 둘레 이 거리(m) 안의 차만 기록한다 (0 = 모든 차)")
    ap.add_argument("--check", action="store_true", help="50 스텝마다 수업 방식으로도 읽어 값이 같은지 확인한다 (느려진다)")
    ap.add_argument("--test", action="store_true", help="속도·용량 시험: SUMO 마다 2판만 모으고 끝낸다 (data_final_test/ 에 쓴다)")
    ap.add_argument("--policy", default=None, choices=["ppo", "bc", "keep-lane", "random"], help=argparse.SUPPRESS)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--min-free-gb", type=float, default=5.0)
    ap.add_argument("--status", action="store_true", help="지금까지 모은 양만 보여 주고 끝낸다")
    ap.add_argument("--target", type=int, default=None, help="이 기기가 모을 스텝 수 (생략하면 기기 번호의 몫. 0 이면 멈출 때까지)")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(errors="replace")      # 윈도우 콘솔이 못 찍는 글자가 있어도 멈추지 않게
    except Exception:
        pass
    out_dir = os.path.abspath(a.out_dir or os.path.join(BASE, OUT + ("_test" if a.test else "")))
    os.makedirs(out_dir, exist_ok=True)
    if a.status:
        status(out_dir)
        return
    if a.machine is None:
        ap.error("--machine 번호가 필요합니다 (1, 2, 3)")
    model = "" if (a.policy in ("keep-lane", "random") and not a.model) else os.path.abspath(os.path.join(BASE, a.model or DEFAULT_MODEL) if not (a.model and os.path.isabs(a.model)) else a.model)
    if model and not os.path.exists(model):
        sys.exit(f"모델 파일이 없습니다: {model}")
    target = 0 if a.test else (TARGET.get(a.machine, 0) if a.target is None else a.target)
    keep_awake()
    episodes = 2 if a.test else a.episodes
    check = a.check or a.test
    if a.test:                                       # 시험은 늘 새로 한다
        for p in glob.glob(os.path.join(out_dir, f"final_m{a.machine:02d}_w*_c0000.npz")):
            os.replace(p, p + ".old")
    have = 0 if a.test else count_machine(out_dir, a.machine)
    print(f"수집 시작 ({time.strftime('%m-%d %H:%M:%S')}): 기기 {a.machine}, SUMO {a.workers}개, 묶음당 {episodes}판, "
          f"{'모든 차' if a.radius <= 0 else f'AV 둘레 {a.radius:.0f} m 안의 차'} 기록 → {out_dir}", flush=True)
    print(f"모델 {os.path.relpath(model, BASE) if model else a.policy} | 이 기기의 몫 "
          + (f"{target:,} 스텝 (지금까지 {have:,})" if target else "없음 (멈출 때까지)"), flush=True)
    if target and have >= target:
        print("이미 몫을 다 모았습니다. 더 모으려면 --target 을 늘려 주세요.")
        status(out_dir)
        return
    ensure_road()
    t0 = time.time()
    ctx = mp.get_context("spawn")
    count = ctx.Value("q", have)
    jobs = [(model, a.machine, w, a.chunks, episodes, check, a.radius, a.policy, out_dir, a.test, a.min_free_gb, target)
            for w in range(a.workers)]
    try:
        with ctx.Pool(a.workers, initializer=_init, initargs=(count,)) as pool:
            got = pool.map(worker, jobs)
    except KeyboardInterrupt:
        print("\n멈췄습니다. 끝난 묶음은 남아 있습니다.", flush=True)
        got = []
    dt = time.time() - t0
    if got:
        n = sum(got)
        print(f"\n이번 실행: {n:,} 스텝, {dt / 60:.1f}분, 전체 {n / max(dt, 1):.0f} 스텝/s", flush=True)
        if a.test and n:
            size = sum(os.path.getsize(p) for p in glob.glob(os.path.join(out_dir, f"final_m{a.machine:02d}_w*_c0000.npz")))
            rate = n / max(dt, 1)
            print(f"시험 결과: {rate:.0f} 스텝/s, {size / n / 1024:.2f} KB/스텝 → 이 기기 혼자 1,000만 스텝이면 "
                  f"{1e7 / rate / 3600:.1f}시간, {size / n * 1e7 / 2**30:.0f} GB (SUMO 를 띄우는 시간이 섞여 실제는 조금 더 빠르다)")
    print("지금까지:")
    status(out_dir)


if __name__ == "__main__":
    main()
