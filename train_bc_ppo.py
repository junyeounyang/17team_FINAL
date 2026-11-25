"""BC → PPO 미세조정 (v4.1 센서 관측 116개) — 시범으로 사전학습한 정책을 PPO 로 고친다.

실행 (프로젝트 폴더에서):
    # 0) 계산 점검 (SUMO 없이 10초). 기울기·내보내기 식이 맞는지 숫자로 확인한다
    python train_bc_ppo.py --selfcheck

    # 1) 5분짜리 동작 확인 (꼭 먼저. 한 줄로 붙여 넣는다)
    python train_bc_ppo.py --run bcppo_smoke --demo data/v41_demo400.npz --bc-max-steps 300 --workers 2 --n-steps 256 --total 6144 --critic-warmup 2048 --actor-warmup 1024 --eval-every 2048 --eval-episodes 2 --eval-procs 1 --final-eval 2

    # 2) BC 사전학습만 하고 평가 (시범을 늘렸을 때 출발점이 얼마나 좋아지는지 볼 때)
    python train_bc_ppo.py --run bc_d6400 --demo data/v41_d6400.npz --bc-only --eval-episodes 50

    # 3) 본 학습: BC 사전학습 → 가치망 준비 → PPO
    python train_bc_ppo.py --run bcppo1 --demo data/v41_d6400.npz --workers 8

    # 4) 끊겼을 때 이어서 (같은 --run 이름 + --resume. 스텝을 늘리려면 --total 을 더 크게)
    python train_bc_ppo.py --run bcppo1 --resume --workers 8

    # 5) 팀의 BC 모델(train_bc.py · run_all_BC.py 가 만든 model.pt)에서 출발: PPO 신경망으로 옮긴 뒤 가치망 준비 → PPO
    python train_bc_ppo.py --run bcppo2 --from-bc results/bc_v41_d6400_s0/model.pt --demo data/v41_d6400.npz --workers 8
    #    옮긴 정책이 원래 모델만큼 달리는지만 볼 때 (PPO 는 하지 않는다)
    python train_bc_ppo.py --run conv_s0 --from-bc results/bc_v41_d6400_s0/model.pt --demo data/v41_d6400.npz --bc-only --eval-episodes 100 --eval-procs 6

    # 보상을 바꿔 볼 때 (예: 팀 v2 BC+PPO 가 쓴 값)
    python train_bc_ppo.py --run bcppo2 --demo data/v41_d6400.npz --workers 8 --reward crash_penalty=50 crash_pedestrian_penalty=80 tailgate_penalty=0.3 tailgate_time=0.6 yield_penalty=15 off_route_penalty=40

결과 (results/<run>/):
    bc_init.npz / bc_log.csv     사전학습한 정책과 그 학습 기록 (다시 실행하면 이 파일을 그대로 쓴다)
                                 --from-bc 로 시작하면 옮겨 온 BC 모델의 가중치도 여기에 함께 들어간다 (시범 닻의 정답으로 쓴다)
    ckpt_0.pt, eval_0.json       PPO 를 시작하기 전(= BC 만 한) 모델과 그 평가. PPO 가 실제로 올렸는지의 기준선
    train_log.csv, eval_log.csv, events.log, best.pt, ckpt_<스텝>.pt, last.pt
                                 train_ppo_curriculum.py 와 같은 형식
    final/summary.txt            학습이 끝난 뒤 처음(ckpt_0)·최고 기록(best)·마지막(last) 모델을 같은 100판으로 견준 결과 (--final-eval).
                                 학습 중 평가는 판 수가 적어 ±15%p 안팎으로 흔들린다. 모델을 고를 때는 이쪽을 본다
    bcppo_log.csv                업데이트마다: 학습률, 시범 닻 가중치, 가치망이 맞는 정도(ev), 시범과의 차이
    learner_state.npz            이어서 학습할 때 쓰는 내부 상태 (가치망·옵티마이저 포함)
    모델 파일(.pt)은 train.py 의 PPO 와 같은 형식이라 eval_daehakro.py, test.py, run_all_BC.py --job,
    collect_pomdp_data_daehakro.py 로 그대로 평가·재생·수집할 수 있다 (test.py 를 고치지 않는다).

──────────────────────────────────────────────────────────────────────────────
왜 이렇게 만들었나 (근거는 맨 아래 '참고한 자료')

  BC 만으로는 부족하다. 시범 400판 BC(v4.1)는 도착 14~28%, 실패는 전부 충돌이고 경로 이탈·멈춤은 0 이었다.
  차로는 맞게 고르는데 '언제 얼마나 밟을지'가 틀린다. 시범에는 사고 직전 장면이 없어서 그 근처로 밀려나면
  배운 적 없는 상태가 된다 [Ross 2011]. 드물고 위험한 장면은 보상으로 배우는 쪽이 낫다 [Lu 2023].
  반대로 PPO 를 처음부터 하면 차로 고르기·출발 같은 것부터 다시 배워야 해서 수백만 스텝이 든다.
  그래서 BC 로 출발점을 만들고 PPO 로 고친다. 다만 그대로 이어 붙이면 출발점이 무너진다.
  무너지는 이유마다 장치를 하나씩 두었다.

  ① 가치망이 엉터리인 채로 정책을 고치면 처음에 성능이 급락한다 [Ramrakhya 2023]
      → 가치망을 정책과 따로 두고 [Andrychowicz 2021], 처음 --critic-warmup 스텝은 정책을 고정한 채 가치망만 학습한다.
        가치망 마지막 층은 0 에서 시작하고, 정책 학습률은 0 에서 --actor-warmup 스텝에 걸쳐 올린다 [Ramrakhya 2023].
  ② 초반에 가 보지 못한 구간의 운전을 잊는다 [Wołczyk 2024]. BC 정책은 앞쪽 구간에서 자주 실패하므로
      PPO 는 한동안 앞쪽 경험만 받고, 그동안 뒤쪽(로터리) 운전이 망가진다. 우리 팀 v2 BC+PPO 에서도
      학습 중 경로 이탈이 0.7% → 3.7% 로 늘었다가 차선 닻을 키워서 잡았다.
      → 업데이트마다 시범 묶음으로 '시범 흉내 손실'을 함께 건다 (닻). 가중치는 서서히 줄이되 0 으로 내리지 않는다
        [Rajeswaran 2018 의 λ0·λ1^k 가중치, Lu 2023 의 BC 항].
  ③ BC 는 정답 하나를 내도록 배웠는데 PPO 는 확률로 행동을 뽑는다. 탐험 폭이 크면 정지선·앞차 앞에서 못 선다.
      → 가감속 σ 를 작게(--sigma 0.2) 시작하고, 차선 점수는 --lane-sharpen 배로 키워 '유지'일 때 엉뚱한 차로변경이
        거의 뽑히지 않게 한다. (400판 BC 로 재 보니 성능을 깎는 것은 가감속 쪽 흔들림이고 차선 뽑기는 거의 영향이 없었다.
        BC 가 약할수록 크게 깎인다. train_log.csv 의 도착률이 ckpt_0 평가보다 한참 낮으면 --sigma 를 0.1 로 낮춘다.)
  ④ 사전학습과 미세조정의 신경망·입력이 다르면 옮길 때 행동이 달라진다.
      → 처음부터 PPO 신경망(은닉 256-256, 가감속 tanh, 차선 3갈래)으로 BC 를 한다. 차선은 회귀가 아니라 분류로 배운다.
        입력 정규화(시범의 평균·표준편차)는 학습 내내 고정하고, 저장할 때 첫 층 가중치에 합친다 (W/σ, b − W·μ/σ).
  ⑤ 가감속 정답은 세 덩어리다 (브레이크 유지 −0.5 가 16%, 속도 유지 0 근처가 25%, 가속 +0.77 이 14%).
      제곱 오차만 쓰면 헷갈리는 장면에서 두 덩어리의 평균(= 슬금슬금 기어감)을 낸다.
      → 오차가 --bc-delta 를 넘으면 직선으로 바뀌는 손실(Huber)을 쓴다. 큰 오차에서 '평균'이 아니라 '많은 쪽'으로 간다.
      그래도 BC 는 평균 쪽으로 쏠려서 브레이크를 덜 밟는다. 시범 400판으로 학습해 처음 보는 40판에 대 보면,
      시범이 달리며 브레이크를 밟던 장면의 47% 에서 0.2 넘게 덜 밟았고 (평균 +0.24), 서 있어야 할 장면의 4% 에서 가속을 냈다.
      이 두 값을 사전학습 기록에 '브레이크 부족', '서 있다 가속'으로 찍는다. 충돌이 왜 나는지 평가 전에 보이는 숫자다.
      → --bc-caution 을 0.5 보다 크게 주면 '덜 밟은' 오차를 더 크게 벌줘서 헷갈릴 때 브레이크 쪽으로 기운다 (분위수 회귀).
        400판·같은 25판 평가에서: 0.5 → 도착 4·충돌 20·멈춤 1 / 0.65 → 도착 9·충돌 5·멈춤 10 / 0.75 → 도착 1·충돌 2·멈춤 22.
        충돌이 멈춤으로 바뀐다. PPO 가 경험을 모을 때처럼 행동을 뽑으면(σ 0.2) 0.65 는 멈춤이 풀려 도착 35% (20판),
        0.5 는 도착 2% (150판) 였다. 시범 1,900판에서도 같았다 (0.6: 도착 48% 충돌 28% 멈춤 24%, 25판).
        충돌을 멈춤으로 바꿀 뿐이라 기본값은 0.5 (양쪽 같게) 로 둔다.

  ⑥ 팀의 BC 모델에서 출발할 수 있다 (--from-bc). 시범 6,400판으로 재 보니 (Mac, 2026-11-25) 출발점이 이만큼 갈렸다.
        팀 BC (train_bc.py, 제곱 오차), 학습 seed 3개, 같은 100판:  도착 73% · 61% · 42%, 멈춤은 셋 다 0%
        이 파일의 사전학습 (꺾은 오차, --bc-delta 0.2), 30판:        도착 50%, 충돌 13%, 멈춤 33%
      이유는 관측에 없는 정보다. 시범 운전자는 보행자가 건널지(SUMO 내부 정보)를 알고 서거나 가는데 관측에는 보행자의 위치만 있어서,
      같은 관측에 '서 있기'와 '출발'이 섞여 있다 (시범 1,900판에서 횡단보도 3~12 m 앞·보행자가 정면 12 m 안인 장면 4,254개 중
      52% 는 세게 밟고 36% 는 가속이다). 꺾은 오차는 많은 쪽을 골라 횡단보도 앞에 서서 출발하지 않고, 제곱 오차는 평균을 내서
      조금만 가능성이 있어도 출발한다 — 멈추지 않는 대신 더 부딪힌다 (1,900판·50판 평가에서 꺾은 오차: 도착 54% 충돌 38% 멈춤 8%,
      제곱 오차(--bc-delta 0): 도착 42% 충돌 56% 멈춤 0%). 어느 쪽이든 학습 seed 에 따라 크게 갈린다.
      이 파일의 사전학습으로 시작해도 PPO 가 그 멈춤을 푼다 (Mac·6,400판: 학습 중 최근 150판의 도착 52% → 71%, 멈춤 7% → 0%,
      차 충돌 30% → 20%. 16만 스텝까지는 변화가 없다가 그 뒤 33만 스텝 사이에 올랐다).
      → 팀이 여러 seed 중에서 고른 BC 모델을 PPO 의 출발점으로 그대로 쓸 수 있게 했다 (convert_bc). 두 신경망의 은닉층이 같아서
        (256-256, ReLU, 같은 방식의 입력 정규화) 은닉층은 복사하고, 차선 출력은 환경의 ±0.5 규칙과 같게 만들고, 가감속 출력만
        tanh 에 맞춰 다시 맞춘다. 그 뒤 PPO 의 시범 닻은 시범 정답이 아니라 '옮겨 온 모델의 행동'을 정답으로 쓴다
        (시범 정답으로 당기면 고른 모델에서 멀어진다).
        검증 (6,400판에서 고른 s0 를 옮김): 옮긴 정책이 달리며 지나간 9,820 스텝에서 BC 모델과의 가감속 차이가 평균 0.015
        (99% 가 0.07 이내)였고, 차선 명령이 달랐던 스텝은 4개였다. 같은 seed 두 개로 100판씩 달리게 하면 옮긴 정책이 도착 68% ·
        차 충돌 23% · 보행자 충돌 9% · 멈춤 0%, 원래 모델이 도착 65% · 차 충돌 26% · 보행자 충돌 7% · 멈춤 2% 였다 (100판의 오차 범위 안에서 같다).

  보상은 train_ppo_curriculum.py 의 4단계(최종값)를 처음부터 쓴다. BC 정책은 이미 달리므로 벌점을 작게 시작할
  이유가 없다. 환경 작업자·GAE·기록·평가도 그 파일의 것을 그대로 불러 쓴다 (이 파일은 '정책을 고치는 계산'만 바꾼다).

  학습 계산은 numpy 로 직접 썼다 (신경망이 256-256 MLP 라 속도는 torch CPU 와 같다). 이유는 하나다:
  torch 가 없는 곳에서도 SUMO 까지 붙여 처음부터 끝까지 돌려 볼 수 있어서, 넘기기 전에 실제로 돌려 확인했다.
  기울기는 --selfcheck 가 수치 미분과 비교한다. torch 는 모델 파일을 팀 공통 형식으로 저장할 때만 쓴다.

참고한 자료
  [Ramrakhya 2023]   PIRLNav: Pretraining with Imitation and RL Finetuning for ObjectNav. CVPR. arXiv:2301.07302
  [Rajeswaran 2018]  Learning Complex Dexterous Manipulation with Deep RL and Demonstrations (DAPG). RSS. arXiv:1709.10087
  [Lu 2023]          Imitation Is Not Enough: Robustifying Imitation with RL for Challenging Driving Scenarios. IROS. arXiv:2212.11419
  [Wołczyk 2024]     Fine-tuning Reinforcement Learning Models is Secretly a Forgetting Mitigation Problem. ICML. arXiv:2402.02868
  [Andrychowicz 2021] What Matters In On-Policy Reinforcement Learning? ICLR. arXiv:2006.05990
  [Mandlekar 2021]   What Matters in Learning from Offline Human Demonstrations for Robot Manipulation. CoRL. arXiv:2108.03298
  [Ross 2011]        A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning (DAgger). AISTATS.
  [Schulman 2017]    Proximal Policy Optimization Algorithms. arXiv:1707.06347   /   [van Hasselt 2016] PopArt. arXiv:1602.07714
  팀 자료: jhtim1-eng/bc-ppo (v2 관측에서 BC 93.2% → BC+PPO 98.5%, 충돌 6.5% → 1.0%) 의 설정을 출발점으로 삼았다.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time

# 계산 스레드는 1개 (SUMO 작업자와 CPU 를 다투지 않게). numpy 를 불러오기 전에 정해야 한다.
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)

F32 = np.float32
HIDDEN = (256, 256)                                  # train.py HPARAMS 와 같아야 한다 (test.py 가 이 모양으로 불러온다)
LANE_CMDS = np.array([1.0, 0.0, -1.0], dtype=F32)    # 차선 번호 0 = 왼쪽(+1), 1 = 유지(0), 2 = 오른쪽(−1). utils/networks.py 와 같다
HALF_LOG_2PI = 0.5 * math.log(2.0 * math.pi)
ACCEL_CAP = 0.98                                     # 가감속 정답을 이 안으로 자른다 (tanh 는 ±1 에 닿지 못한다)
LANE_THRESHOLD = 0.5                                 # 환경이 차선 출력을 자르는 기준 (env/mdp_config.py 의 lane_change_threshold)
HOLD = -0.5                                          # 시범에서 '서서 브레이크 유지'의 정답 (env/daehakro_env.py 의 DEMO_HOLD)
CTX = {}                                             # main() 이 채운다: 설정, 학습기 (train_ppo_curriculum.main 이 만드는 객체들이 읽는다)


def stamp():
    return time.strftime("%m-%d %H:%M:%S")


def say(msg, run_dir=None):
    line = f"[{stamp()}] {msg}"
    print(line, flush=True)
    run_dir = run_dir or CTX.get("run_dir")
    if run_dir and os.path.isdir(run_dir):
        with open(os.path.join(run_dir, "events.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ══════════════════════════════ 신경망 (numpy) ══════════════════════════════
def _linear_init(rng, rows, cols, dtype):
    lim = 1.0 / math.sqrt(cols)                      # torch nn.Linear 의 기본 초기화와 같은 범위
    return rng.uniform(-lim, lim, (rows, cols)).astype(dtype), rng.uniform(-lim, lim, rows).astype(dtype)


def _orthogonal(rng, rows, cols, gain, dtype):
    a = rng.standard_normal((max(rows, cols), min(rows, cols)))
    q, r = np.linalg.qr(a)
    q = q * np.sign(np.diag(r))
    return (gain * (q if rows >= cols else q.T)).astype(dtype)


def log_softmax(z):
    m = z.max(axis=-1, keepdims=True)
    return z - m - np.log(np.exp(z - m).sum(axis=-1, keepdims=True))


class Net:
    """입력 정규화 → 은닉층(ReLU) → 선형 출력 여러 개. 가중치는 self.p (이름 → 배열)."""

    def __init__(self, obs_dim, hidden, heads, rng, dtype=F32):
        self.dtype, self.n_hidden, self.heads = dtype, len(hidden), tuple(h[0] for h in heads)
        self.mean, self.std = np.zeros(obs_dim, dtype), np.ones(obs_dim, dtype)
        self.p, last = {}, obs_dim
        for i, h in enumerate(hidden):
            self.p[f"W{i}"], self.p[f"b{i}"] = _linear_init(rng, h, last, dtype)
            last = h
        for name, out, gain in heads:
            self.p[f"{name}.W"] = _orthogonal(rng, out, last, gain, dtype)
            self.p[f"{name}.b"] = np.zeros(out, dtype)

    def forward(self, x):
        p = self.p
        hs = [(np.asarray(x, dtype=self.dtype) - self.mean) / self.std]
        for i in range(self.n_hidden):
            hs.append(np.maximum(hs[-1] @ p[f"W{i}"].T + p[f"b{i}"], 0))
        out = {name: hs[-1] @ p[f"{name}.W"].T + p[f"{name}.b"] for name in self.heads}
        out["_h"] = hs
        return out

    def backward(self, cache, g_out):
        """g_out: {출력 이름: d손실/d출력 [N, 출력 수]} (모든 출력) → {가중치 이름: 기울기}."""
        p, hs, g, gz = self.p, cache["_h"], {}, 0.0
        for name in self.heads:
            go = g_out[name]
            g[f"{name}.W"] = go.T @ hs[-1]
            g[f"{name}.b"] = go.sum(0)
            gz = gz + go @ p[f"{name}.W"]
        for i in reversed(range(self.n_hidden)):
            ga = gz * (hs[i + 1] > 0)
            g[f"W{i}"] = ga.T @ hs[i]
            g[f"b{i}"] = ga.sum(0)
            if i > 0:
                gz = ga @ p[f"W{i}"]
        return g


class Actor(Net):
    """정책: 가감속 평균 = tanh(mu), 표준편차 = exp(log_std) (상태와 무관), 차선 = 3갈래 점수.
    utils/networks.py 의 HybridActorCritic 과 같은 계산이다 (가치 출력만 뺐다 — 가치망은 따로 둔다)."""

    def __init__(self, obs_dim, rng, sigma=0.2, dtype=F32):
        super().__init__(obs_dim, HIDDEN, [("mu", 1, 0.01), ("lane", 3, 0.01)], rng, dtype)
        self.p["log_std"] = np.array([math.log(sigma)], dtype)

    def dist(self, x):
        c = self.forward(x)
        c["mean"] = np.tanh(c["mu"][:, 0])
        c["lsm"] = log_softmax(c["lane"])
        return c

    def log_prob(self, c, act):
        ls = float(self.p["log_std"][0])
        a = act[:, 0].astype(self.dtype)
        idx = np.clip(1 - np.round(act[:, 1]).astype(np.int64), 0, 2)     # 명령(−1/0/+1) → 번호(2/1/0)
        z = (a - c["mean"]) / math.exp(ls)
        return -0.5 * z * z - ls - HALF_LOG_2PI + c["lsm"][np.arange(len(a)), idx], z, idx

    def sample(self, x, rng):
        c = self.dist(x)
        n, ls = len(c["mean"]), float(self.p["log_std"][0])
        eps = rng.standard_normal(n).astype(self.dtype)
        a = c["mean"] + math.exp(ls) * eps
        cum = np.cumsum(np.exp(c["lsm"]), axis=1)
        idx = np.minimum((cum < rng.random(n)[:, None]).sum(1), 2)
        logp = -0.5 * eps * eps - ls - HALF_LOG_2PI + c["lsm"][np.arange(n), idx]
        return np.stack([a, LANE_CMDS[idx]], axis=1).astype(F32), logp.astype(F32)

    def best(self, x):
        """결정적 행동 [가감속 평균, 차선 명령] — 평가할 때의 행동."""
        c = self.dist(x)
        return np.stack([c["mean"], LANE_CMDS[np.argmax(c["lane"], axis=1)]], axis=1).astype(F32)


class Adam:
    """torch.optim.Adam 과 같은 식. weight_decay 는 가중치 행렬에만, 기울기와 따로 건다 (AdamW 방식)."""

    def __init__(self, params, keys=None):
        self.p, self.keys = params, list(keys or params)
        self.m = {k: np.zeros_like(params[k]) for k in self.keys}
        self.v = {k: np.zeros_like(params[k]) for k in self.keys}
        self.t = 0

    def step(self, grads, lr, max_norm=None, weight_decay=0.0):
        norm = math.sqrt(sum(float(np.sum(np.square(grads[k], dtype=np.float64))) for k in self.keys))
        scale = 1.0 if (max_norm is None or norm <= max_norm) else max_norm / (norm + 1e-6)
        self.t += 1
        c1, c2 = 1.0 - 0.9 ** self.t, 1.0 - 0.999 ** self.t
        for k in self.keys:
            g = grads[k] if scale == 1.0 else grads[k] * scale
            m, v, w = self.m[k], self.v[k], self.p[k]
            m *= 0.9
            m += 0.1 * g
            v *= 0.999
            v += 0.001 * (g * g)
            if weight_decay and w.ndim == 2:
                w *= 1.0 - lr * weight_decay
            w -= (lr / c1) * m / (np.sqrt(v / c2) + 1e-8)
        return norm

    def state(self, prefix):
        out = {f"{prefix}/m/{k}": self.m[k] for k in self.keys}
        out.update({f"{prefix}/v/{k}": self.v[k] for k in self.keys})
        out[f"{prefix}/t"] = np.array(self.t)
        return out

    def load(self, data, prefix):
        for k in self.keys:
            self.m[k][...] = data[f"{prefix}/m/{k}"]
            self.v[k][...] = data[f"{prefix}/v/{k}"]
        self.t = int(data[f"{prefix}/t"])


def grad_norm(grads):
    return math.sqrt(sum(float(np.sum(np.square(g, dtype=np.float64))) for g in grads.values()))


# ══════════════════════════════ 손실과 기울기 ══════════════════════════════
def bc_grads(actor, obs, accel, lane_idx, w_accel, w_lane, delta, caution=0.5):
    """시범 흉내 손실 = w_accel × 가감속 오차 + w_lane × 차선 교차엔트로피.
    가감속 오차: |오차| ≤ delta 면 제곱, 넘으면 직선 2·delta·|오차| − delta² (delta 가 None 이면 제곱만).
    caution: 시범보다 덜 밟은 오차(예측 > 정답)에 2·caution, 더 밟은 오차에 2·(1 − caution) 을 곱한다.
             0.5 면 양쪽이 같다. 0.5 보다 크면 헷갈릴 때 브레이크 쪽으로 기운다 (분위수 회귀와 같은 원리)."""
    n = len(obs)
    c = actor.dist(obs)
    r = c["mean"] - accel
    if delta is None:
        la, dr = r * r, 2.0 * r
    else:
        inside = np.abs(r) <= delta
        la = np.where(inside, r * r, 2.0 * delta * np.abs(r) - delta * delta)
        dr = np.where(inside, 2.0 * r, 2.0 * delta * np.sign(r))
    if caution != 0.5:
        side = np.where(r > 0, 2.0 * caution, 2.0 * (1.0 - caution))
        la, dr = la * side, dr * side
    rows = np.arange(n)
    ce = -c["lsm"][rows, lane_idx]
    g_lane = np.exp(c["lsm"])
    g_lane[rows, lane_idx] -= 1.0
    g_mu = (w_accel / n) * dr * (1.0 - c["mean"] ** 2)
    grads = actor.backward(c, {"mu": g_mu[:, None].astype(actor.dtype), "lane": (g_lane * (w_lane / n)).astype(actor.dtype)})
    grads["log_std"] = np.zeros_like(actor.p["log_std"])
    stats = {"accel": float(la.mean()), "lane": float(ce.mean()), "abs": float(np.abs(r).mean()),
             "lane_acc": float((np.argmax(c["lane"], axis=1) == lane_idx).mean())}
    return w_accel * stats["accel"] + w_lane * stats["lane"], grads, stats


def ppo_grads(actor, obs, act, old_logp, adv, clip):
    """PPO 의 잘린 대리 손실 −mean(min(r·A, clip(r, 1−ε, 1+ε)·A)) 과 기울기 (algorithms/ppo.py 와 같은 식)."""
    n = len(obs)
    c = actor.dist(obs)
    logp, z, idx = actor.log_prob(c, act)
    ratio = np.exp(logp - old_logp)
    s1, s2 = ratio * adv, np.clip(ratio, 1.0 - clip, 1.0 + clip) * adv
    g_logp = -(adv * ratio * (s1 <= s2)) / n                      # 잘린 쪽이 고른 표본은 기울기 0
    sd = math.exp(float(actor.p["log_std"][0]))
    g_mu = g_logp * (z / sd) * (1.0 - c["mean"] ** 2)
    g_lane = -np.exp(c["lsm"])
    g_lane[np.arange(n), idx] += 1.0
    g_lane *= g_logp[:, None]
    grads = actor.backward(c, {"mu": g_mu[:, None].astype(actor.dtype), "lane": g_lane.astype(actor.dtype)})
    grads["log_std"] = np.array([float(np.sum(g_logp * (z * z - 1.0)))], actor.dtype)
    p = np.exp(c["lsm"])
    stats = {"policy_loss": float(-np.minimum(s1, s2).mean()), "approx_kl": float((old_logp - logp).mean()),
             "clip_frac": float((np.abs(ratio - 1.0) > clip).mean()),
             "entropy": float(HALF_LOG_2PI + 0.5 + math.log(sd) - (p * c["lsm"]).sum(1).mean())}
    return stats["policy_loss"], grads, stats


def value_grads(critic, obs, target):
    """가치 손실 mean((V − 목표)²) 과 기울기. V 와 목표는 정규화한 값이다 (ValueNorm 참고)."""
    c = critic.forward(obs)
    d = c["v"][:, 0] - target
    grads = critic.backward(c, {"v": ((2.0 / len(obs)) * d)[:, None].astype(critic.dtype)})
    return float(np.mean(d * d)), grads


class ValueNorm:
    """보상 합(return)의 평균·표준편차를 따라가며 가치망이 '정규화한 값'을 맞히게 한다 (PopArt).
    통계를 바꿀 때 마지막 층을 같이 고쳐서, 가치망이 내는 실제 값은 바뀌지 않게 한다."""

    def __init__(self, beta=0.9):
        self.mu, self.sd, self.beta, self.ready = 0.0, 1.0, beta, False

    def update(self, critic, ret):
        m, s = float(np.mean(ret)), float(np.std(ret))
        if not self.ready:                              # 처음: 통계만 정한다 → 마지막 층이 0 인 가치망은 평균 보상 합을 낸다
            self.mu, self.sd, self.ready = m, max(s, 1e-3), True
            return
        else:
            mu = self.beta * self.mu + (1.0 - self.beta) * m
            var = self.beta * (self.sd ** 2 + self.mu ** 2) + (1.0 - self.beta) * (s * s + m * m) - mu * mu
            sd = math.sqrt(max(var, 1e-6))
        w, b = critic.p["v.W"], critic.p["v.b"]
        w *= self.sd / sd
        b[...] = (self.sd * b + self.mu - mu) / sd
        self.mu, self.sd = mu, sd


# ══════════════════════════════ 시범 데이터 ══════════════════════════════
def load_demos(paths):
    """collect_demo.py 가 만든 npz 여러 개를 이어 붙인다. Returns: 관측 [N,116], 가감속 정답 [N], 차선 번호 [N], 에피소드 [N]."""
    try:                                               # v4 환경에는 관측 형식 확인이 있다. v3 에는 없다
        from env.observation_schema import NAMES, require_data_schema
    except ImportError:
        NAMES, require_data_schema = None, (lambda d: None)
    key = ("demos", tuple(paths))
    if key in CTX:                                     # 사전학습 때 읽은 것을 학습기가 다시 쓴다
        return CTX[key]
    obs, act, eps, base_ep = [], [], [], 0
    for path in paths:
        path = path if os.path.isabs(path) else os.path.join(BASE, path)
        with np.load(path, allow_pickle=False) as d:
            require_data_schema(d)                     # 관측 형식·차로변경 검사 방식이 지금 환경과 같은지
            o, a = d["observation"].astype(F32, copy=False), d["action_raw"].astype(F32, copy=False)
            e = d["episode"].astype(np.int64)
        if o.ndim != 2 or (NAMES is not None and o.shape[1] != len(NAMES)) or a.shape != (len(o), 2):
            raise SystemExit(f"{path}: 시범 형식이 다릅니다 (관측 {o.shape}, 행동 {a.shape})")
        if not (np.isfinite(o).all() and np.isfinite(a).all()):
            raise SystemExit(f"{path}: NaN/Inf 가 있습니다")
        e = e - e.min() + base_ep
        base_ep = int(e.max()) + 1
        obs.append(o), act.append(a), eps.append(e)
        print(f"  시범 {os.path.basename(path)}: {len(o):,} 스텝, {len(np.unique(e))} 판", flush=True)
    if len(obs) == 1:                                  # 파일이 하나면 그대로 쓴다 (큰 배열을 한 번 더 복사하지 않게)
        obs, act, eps = obs[0], act[0], eps[0]
    else:
        obs, act, eps = np.concatenate(obs), np.concatenate(act), np.concatenate(eps)
    accel = np.clip(act[:, 0], -ACCEL_CAP, ACCEL_CAP).astype(F32)
    lane = np.clip(1 - np.round(act[:, 1]).astype(np.int64), 0, 2)
    CTX[key] = (obs, accel, lane, eps)
    return CTX[key]


def fit_normalizer(obs, floor=0.05):
    """입력 정규화 통계. 표준편차는 floor 이상으로 둔다. 시범에서 한 번도 바뀌지 않은 입력(const)은 표준편차 1 로 둔다
    (정규화하면 시범에서는 늘 0 이 된다)."""
    mean, std = obs.mean(0, dtype=np.float64), obs.std(0, dtype=np.float64)
    const = std < 1e-6
    std = np.where(const, 1.0, np.maximum(std, floor))
    return mean.astype(F32), std.astype(F32), const


def demo_metrics(actor, obs, accel, lane, cfg, chunk=16384):
    """시범 묶음에서 정책이 정답과 얼마나 다른가 (결정적 행동 기준)."""
    tot, n = {}, len(obs)
    for s in range(0, n, chunk):
        c = actor.dist(obs[s:s + chunk])
        a, l = accel[s:s + chunk], lane[s:s + chunk]
        r = c["mean"] - a
        la = r * r if cfg.bc_delta is None else np.where(np.abs(r) <= cfg.bc_delta, r * r,
                                                         2 * cfg.bc_delta * np.abs(r) - cfg.bc_delta ** 2)
        la = la * np.where(r > 0, 2.0 * cfg.bc_caution, 2.0 * (1.0 - cfg.bc_caution))
        pred = np.argmax(c["lane"], axis=1)
        hold = (a == F32(HOLD)) & (obs[s:s + chunk, 0] < 0.01)       # 시범 운전자가 서서 브레이크를 밟고 있던 장면
        brake = (a < -0.2) & ~hold                                    # 달리면서 브레이크를 밟던 장면
        part = {"accel": la.sum(), "sq": (r * r).sum(), "abs": np.abs(r).sum(),
                "lane": -c["lsm"][np.arange(len(a)), l].sum(), "acc": (pred == l).sum(),
                "chg": (l != 1).sum(), "chg_hit": ((l != 1) & (pred == l)).sum(),
                "keep": (l == 1).sum(), "keep_miss": ((l == 1) & (pred != 1)).sum(),
                "hold": hold.sum(), "hold_go": (hold & (c["mean"] > 0)).sum(),
                "brake": brake.sum(), "brake_weak": (brake & (r > 0.2)).sum(), "brake_bias": r[brake].sum()}
        for k, v in part.items():
            tot[k] = tot.get(k, 0.0) + float(v)
    return {"loss": (cfg.bc_accel_weight * tot["accel"] + tot["lane"]) / n, "accel": tot["accel"] / n,
            "rmse": math.sqrt(tot["sq"] / n), "mae": tot["abs"] / n, "lane_ce": tot["lane"] / n, "lane_acc": tot["acc"] / n,
            "change_recall": tot["chg_hit"] / max(tot["chg"], 1.0), "false_change": tot["keep_miss"] / max(tot["keep"], 1.0),
            "hold_go": tot["hold_go"] / max(tot["hold"], 1.0), "brake_weak": tot["brake_weak"] / max(tot["brake"], 1.0),
            "brake_bias": tot["brake_bias"] / max(tot["brake"], 1.0)}


# ══════════════════════════════ 1) BC 사전학습 ══════════════════════════════
def pretrain_bc(cfg, run_dir):
    """PPO 신경망을 시범으로 사전학습해 results/<run>/bc_init.npz 로 저장한다. Returns: 그 경로."""
    out = os.path.join(run_dir, "bc_init.npz")
    if os.path.exists(out):
        say(f"사전학습한 정책이 이미 있어 그대로 씁니다: {out}")
        return out
    if cfg.from_bc:
        return convert_bc(cfg, run_dir, out)
    if cfg.init:
        src = cfg.init if os.path.isabs(cfg.init) else os.path.join(BASE, cfg.init)
        shutil.copy(src, out)
        say(f"사전학습을 건너뛰고 {src} 에서 시작합니다")
        return out
    if not cfg.demo:
        raise SystemExit("--demo 가 필요합니다 (예: --demo data/v41_d6400.npz)")
    say(f"1) BC 사전학습: {', '.join(cfg.demo)}")
    obs, accel, lane, eps = load_demos(cfg.demo)
    rng = np.random.default_rng(cfg.seed)
    ids = rng.permutation(np.unique(eps))
    n_val = min(max(1, round(len(ids) * cfg.bc_val)), len(ids) - 1)
    val_mask = np.isin(eps, ids[:n_val])
    tr, va = np.flatnonzero(~val_mask), np.flatnonzero(val_mask)
    actor = Actor(obs.shape[1], rng, cfg.sigma)
    actor.mean, actor.std, const = fit_normalizer(obs[tr[::max(1, len(tr) // 500_000)]])   # 통계는 학습 쪽 50만 스텝 정도면 충분하다
    keys = [k for k in actor.p if k != "log_std"]
    opt = Adam(actor.p, keys)
    per_epoch = math.ceil(len(tr) / cfg.bc_batch)
    total = min(cfg.bc_epochs * per_epoch, cfg.bc_max_steps)
    check = max(1, min(per_epoch, total // 30))        # 검증 간격 (갱신 횟수)
    say(f"   학습 {len(tr):,} 스텝 / 검증 {len(va):,} 스텝 ({n_val}판), 묶음 {cfg.bc_batch}, 총 {total:,} 번 갱신 "
        f"(가감속 가중치 {cfg.bc_accel_weight}, 꺾는 점 {cfg.bc_delta}, 조심 {cfg.bc_caution}, 가중치 감쇠 {cfg.bc_wd})")
    v_obs, v_acc, v_lane = obs[va], accel[va], lane[va]
    fields = ["step", "epoch", "lr", "train_loss", "val_loss", "val_rmse", "val_mae", "val_lane_ce", "val_lane_acc",
              "val_change_recall", "val_false_change", "val_hold_go", "val_brake_weak", "val_brake_bias"]
    best, best_p, run, t0 = None, None, None, time.time()
    with open(os.path.join(run_dir, "bc_log.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields)
        wr.writeheader()
        perm, pos = rng.permutation(tr), 0
        for step in range(1, total + 1):
            if pos + cfg.bc_batch > len(perm):
                perm, pos = rng.permutation(tr), 0
            mb = np.sort(perm[pos:pos + cfg.bc_batch])
            pos += cfg.bc_batch
            warm = min(1.0, step / 200.0)
            lr = warm * (cfg.bc_lr_end + 0.5 * (cfg.bc_lr - cfg.bc_lr_end) * (1.0 + math.cos(math.pi * step / total)))
            x = obs[mb]
            if cfg.bc_noise > 0:                       # 입력을 조금 흔들어 준다 (정규화한 눈금으로 bc_noise 만큼)
                x = x + (cfg.bc_noise * actor.std) * rng.standard_normal(x.shape).astype(F32)
            loss, grads, _ = bc_grads(actor, x, accel[mb], lane[mb], cfg.bc_accel_weight, 1.0, cfg.bc_delta, cfg.bc_caution)
            opt.step(grads, lr, max_norm=cfg.bc_grad_norm, weight_decay=cfg.bc_wd)
            run = loss if run is None else 0.98 * run + 0.02 * loss
            if step % check == 0 or step == total:
                m = demo_metrics(actor, v_obs, v_acc, v_lane, cfg)
                wr.writerow({"step": step, "epoch": round(step / per_epoch, 2), "lr": f"{lr:.2e}", "train_loss": round(run, 5),
                             "val_loss": round(m["loss"], 5), "val_rmse": round(m["rmse"], 4), "val_mae": round(m["mae"], 4),
                             "val_lane_ce": round(m["lane_ce"], 5), "val_lane_acc": round(m["lane_acc"], 5),
                             "val_change_recall": round(m["change_recall"], 4), "val_false_change": round(m["false_change"], 5),
                             "val_hold_go": round(m["hold_go"], 4), "val_brake_weak": round(m["brake_weak"], 4),
                             "val_brake_bias": round(m["brake_bias"], 4)})
                fh.flush()
                mark = ""
                if best is None or m["loss"] < best["loss"]:
                    best, best_p, mark = dict(m, step=step), {k: v.copy() for k, v in actor.p.items()}, " ★"
                print(f"   {step:>7,}/{total:,} ({step / per_epoch:4.1f} 에폭) | 학습 {run:.4f} | 검증 {m['loss']:.4f} "
                      f"(가감속 오차 {m['mae']:.3f}, 서 있다 가속 {m['hold_go']:.1%}, 브레이크 부족 {m['brake_weak']:.0%} · 평균 {m['brake_bias']:+.2f}, "
                      f"차선 정답률 {m['lane_acc']:.2%}, 차로변경 맞힘 {m['change_recall']:.0%}){mark}", flush=True)
    last = demo_metrics(actor, v_obs, v_acc, v_lane, cfg)
    if cfg.bc_pick == "best":
        actor.p.update(best_p)
    picked = best if cfg.bc_pick == "best" else dict(last, step=total)
    actor.p["W0"][:, const] = 0.0                      # 시범에서 늘 0 이던 입력: 처음 보는 값에 엉뚱하게 반응하지 않게 연결을 끊고 시작한다
    save_actor(out, actor, {"demo": list(cfg.demo), "samples": int(len(obs)), "episodes": int(len(ids)),
                            "val": {k: float(v) for k, v in picked.items()}, "bc_steps": int(total),
                            "constant_inputs": [int(i) for i in np.flatnonzero(const)]})
    say(f"   사전학습 끝 ({(time.time() - t0) / 60:.1f}분). 고른 시점 {picked['step']:,} 번째 (검증 {len(va):,} 스텝 기준): "
        f"가감속 오차 평균 {picked['mae']:.3f}, 서 있어야 할 때 가속 {picked['hold_go']:.1%}, 브레이크를 0.2 넘게 덜 밟음 {picked['brake_weak']:.0%} "
        f"(평균 {picked['brake_bias']:+.2f}), 차선 정답률 {picked['lane_acc']:.2%}, 차로변경 맞힘 {picked['change_recall']:.0%} → {out}")
    return out


def save_actor(path, actor, meta=None, extra=None):
    tmp = path + ".tmp.npz"
    np.savez(tmp, mean=actor.mean, std=actor.std, meta=np.array(json.dumps(meta or {}, ensure_ascii=False)),
             **{"p/" + k: v for k, v in actor.p.items()}, **(extra or {}))
    os.replace(tmp, path)


def load_actor(path, rng):
    with np.load(path, allow_pickle=False) as d:
        actor = Actor(len(d["mean"]), rng)
        actor.mean, actor.std = d["mean"].astype(F32), d["std"].astype(F32)
        for k in actor.p:
            actor.p[k] = d["p/" + k].astype(F32)
        meta = json.loads(str(d["meta"])) if "meta" in d.files else {}
        teacher = {k[len("teacher/"):]: d[k].astype(F32) for k in d.files if k.startswith("teacher/")}
    if teacher:
        meta["teacher"] = teacher                          # --from-bc 로 옮겨 온 BC 모델 (시범 닻의 정답으로 쓴다)
    return actor, meta


# ══════════════════════════════ 1') 팀의 BC 모델을 PPO 신경망으로 옮기기 (--from-bc) ══════════════════════════════
def read_bc(path):
    """train_bc.py 가 저장한 BCPolicy(.pt) 의 가중치를 numpy 로 읽는다 (fc1·fc2·fc3 와 입력 정규화 통계)."""
    path = path if os.path.isabs(path) else os.path.join(BASE, path)
    if not os.path.exists(path):
        raise SystemExit(f"--from-bc: 파일이 없습니다: {path}")
    sd = None
    try:                                               # (시험용) 같은 이름으로 numpy 에 옮겨 둔 파일
        with np.load(path, allow_pickle=False) as d:
            if "fc1.weight" in d.files:
                sd = {k: d[k] for k in d.files}
    except Exception:
        sd = None
    if sd is None:
        import torch
        try:
            from env.observation_schema import require_schema
        except ImportError:                            # v3 환경
            require_schema = lambda ck: None
        ck = torch.load(path, map_location="cpu", weights_only=True)
        if not isinstance(ck, dict) or ck.get("algorithm") != "bc" or "state_dict" not in ck:
            raise SystemExit(f"--from-bc: train_bc.py 가 만든 BC 모델이 아닙니다: {path}")
        require_schema(ck)                             # 관측 형식이 지금 환경과 같은지
        sd = {k: v.detach().cpu().numpy() for k, v in ck["state_dict"].items()}
    need = {"fc1.weight": (HIDDEN[0], None), "fc2.weight": (HIDDEN[1], HIDDEN[0]), "fc3.weight": (2, HIDDEN[1])}
    for k, shape in need.items():
        if k not in sd or sd[k].shape[0] != shape[0] or (shape[1] is not None and sd[k].shape[1] != shape[1]):
            raise SystemExit(f"--from-bc: 신경망 모양이 다릅니다 ({k}: {sd.get(k, np.zeros(0)).shape}). 은닉 256-256, 출력 2개인 BCPolicy 만 옮길 수 있습니다")
    return {k: np.ascontiguousarray(sd[k], dtype=F32) for k in
            ("obs_mean", "obs_std", "fc1.weight", "fc1.bias", "fc2.weight", "fc2.bias", "fc3.weight", "fc3.bias")}


def bc_teacher(sd, x):
    """BCPolicy 가 환경에서 하는 행동 그대로. Returns: 가감속(−1~1 로 자른 값) [N], 차선 번호(0 왼쪽 / 1 유지 / 2 오른쪽) [N]."""
    h = np.maximum(((np.asarray(x, dtype=F32) - sd["obs_mean"]) / sd["obs_std"]) @ sd["fc1.weight"].T + sd["fc1.bias"], 0)
    h = np.maximum(h @ sd["fc2.weight"].T + sd["fc2.bias"], 0)
    y = h @ sd["fc3.weight"].T + sd["fc3.bias"]
    lane = np.where(y[:, 1] >= LANE_THRESHOLD, 0, np.where(y[:, 1] <= -LANE_THRESHOLD, 2, 1))
    return np.clip(y[:, 0], -1.0, 1.0).astype(F32), lane.astype(np.int64)


def actor_from_bc(sd, rng, sigma, lane_scale, dtype=F32):
    """BCPolicy 의 가중치를 PPO 신경망 모양으로 복사한다 (다시 맞추기 전). 차선은 이 상태에서 BCPolicy 와 정확히 같다."""
    actor = Actor(sd["fc1.weight"].shape[1], rng, sigma, dtype)
    actor.mean, actor.std = sd["obs_mean"].astype(dtype), sd["obs_std"].astype(dtype)
    actor.p["W0"], actor.p["b0"] = sd["fc1.weight"].astype(dtype), sd["fc1.bias"].astype(dtype)
    actor.p["W1"], actor.p["b1"] = sd["fc2.weight"].astype(dtype), sd["fc2.bias"].astype(dtype)
    w, b = sd["fc3.weight"].astype(np.float64), sd["fc3.bias"].astype(np.float64)
    actor.p["mu.W"], actor.p["mu.b"] = (1.2 * w[0:1]).astype(dtype), (1.2 * b[0:1]).astype(dtype)   # tanh(1.2·y) ≈ y 인 쪽에서 시작
    actor.p["lane.W"] = (lane_scale * np.stack([w[1], np.zeros_like(w[1]), -w[1]])).astype(dtype)
    actor.p["lane.b"] = (lane_scale * np.array([b[1] - LANE_THRESHOLD, 0.0, -b[1] - LANE_THRESHOLD])).astype(dtype)
    return actor


def convert_bc(cfg, run_dir, out):
    """팀의 BCPolicy 를 PPO 신경망(HybridActorCritic 모양)으로 옮겨 out(bc_init.npz) 에 저장한다 (위 설명 ⑥).

    은닉층 2개는 그대로 복사한다 (두 신경망의 은닉층 모양과 입력 정규화 방식이 같다).
    차선: BCPolicy 는 숫자 하나 y 를 내고 환경이 ±0.5 에서 자른다. 3갈래 점수를 [s(y−0.5), 0, s(−y−0.5)] 로 두면
          가장 큰 쪽이 그 규칙과 정확히 같다 (y ≥ 0.5 → 왼쪽, y ≤ −0.5 → 오른쪽, 그 사이 → 유지).
    가감속: BCPolicy 는 y 를 그대로 내고 환경이 ±1 에서 자르는데, PPO 신경망은 tanh 를 거친다. 식으로는 똑같이 만들 수 없어서
          BCPolicy 의 출력을 정답으로 잠깐 다시 학습한다 (증류). 정답을 BCPolicy 에 물어서 얻으므로 시범에 없는 상태
          (시범 관측을 흔든 것)에서도 맞춘다."""
    sd = read_bc(cfg.from_bc)
    from env.mdp_config import ACTION
    if abs(float(ACTION.get("lane_change_threshold", LANE_THRESHOLD)) - LANE_THRESHOLD) > 1e-9:
        raise SystemExit(f"환경의 차로변경 기준({ACTION.get('lane_change_threshold')})이 이 파일의 LANE_THRESHOLD({LANE_THRESHOLD})와 다릅니다")
    if not cfg.demo:
        raise SystemExit("--from-bc 에는 --demo 도 필요합니다 (옮긴 뒤 맞춰 볼 관측과 시범 닻에 쓴다)")
    say(f"1) 팀의 BC 모델을 PPO 신경망으로 옮깁니다: {cfg.from_bc}")
    obs = load_demos(cfg.demo)[0]
    if obs.shape[1] != sd["fc1.weight"].shape[1]:
        raise SystemExit(f"--from-bc: BC 모델의 입력 {sd['fc1.weight'].shape[1]} 이 시범 관측 {obs.shape[1]} 과 다릅니다")
    rng = np.random.default_rng(cfg.seed)
    actor = actor_from_bc(sd, rng, cfg.sigma, 16.0 / max(cfg.lane_sharpen, 1e-6))   # 학습기가 --lane-sharpen 을 곱한 뒤의 눈금이 16 이 되게

    hold = rng.choice(len(obs), min(len(obs), 50_000), replace=False)
    tests = (("시범 관측", obs[hold]),
             ("흔든 관측", obs[hold] + cfg.conv_noise * actor.std * rng.standard_normal((len(hold), obs.shape[1])).astype(F32)))

    def agreement():
        res = []
        for _, x in tests:
            ta, tl = bc_teacher(sd, x)
            c = actor.dist(x)
            e = np.abs(c["mean"] - np.clip(ta, -ACCEL_CAP, ACCEL_CAP))
            res.append((float(e.mean()), float(np.percentile(e, 99)), float((np.argmax(c["lane"], axis=1) == tl).mean())))
        return res

    before = agreement()
    opt = Adam(actor.p, [k for k in actor.p if k != "log_std"])
    half, t0 = cfg.bc_batch // 2, time.time()
    for step in range(1, cfg.conv_steps + 1):
        lr = min(1.0, step / 100.0) * (1e-5 + 0.5 * (3e-4 - 1e-5) * (1.0 + math.cos(math.pi * step / cfg.conv_steps)))
        x = obs[np.sort(rng.integers(0, len(obs), cfg.bc_batch))]
        x[half:] += cfg.conv_noise * actor.std * rng.standard_normal((len(x) - half, x.shape[1])).astype(F32)
        ta, tl = bc_teacher(sd, x)
        _, grads, _ = bc_grads(actor, x, np.clip(ta, -ACCEL_CAP, ACCEL_CAP), tl, 1.0, 1.0, None, 0.5)
        opt.step(grads, lr, max_norm=5.0)
    after = agreement()
    for (name, _), b0, a0 in zip(tests, before, after):
        say(f"   {name}에서 BC 모델과의 차이: 가감속 평균 {b0[0]:.4f} → {a0[0]:.4f} (99% 가 {a0[1]:.3f} 이내), 차선 일치 {a0[2]:.3%}")
    if after[0][0] > 0.03 or after[0][2] < 0.995:
        raise SystemExit("옮긴 정책이 BC 모델과 충분히 같아지지 않았습니다 (--conv-steps 를 늘려 보세요)")
    save_actor(out, actor, {"from_bc": cfg.from_bc, "demo": list(cfg.demo), "conv_steps": int(cfg.conv_steps),
                            "accel_diff_mean": after[0][0], "accel_diff_p99": after[0][1], "lane_same": after[0][2]},
               extra={"teacher/" + k: v for k, v in sd.items()})
    say(f"   옮기기 끝 ({(time.time() - t0) / 60:.1f}분) → {out}")
    return out


# ══════════════════════════════ 모델 파일 (팀 공통 PPO 형식) ══════════════════════════════
def export_state(actor):
    """입력 정규화를 첫 층에 합쳐, utils/networks.py 의 HybridActorCritic 가중치 이름으로 돌려준다.
        (x − μ)/σ · Wᵀ + b  =  x · (W/σ)ᵀ + (b − W·μ/σ)
    가치 출력(v_head)은 0 으로 둔다 — 가치망은 이 파일에서 따로 학습하고, 평가·주행에는 쓰이지 않는다."""
    p = {k: v.astype(np.float64) for k, v in actor.p.items()}
    mean, std = actor.mean.astype(np.float64), actor.std.astype(np.float64)
    sd = {"trunk.0.weight": p["W0"] / std[None, :], "trunk.0.bias": p["b0"] - p["W0"] @ (mean / std),
          "trunk.2.weight": p["W1"], "trunk.2.bias": p["b1"],
          "mu_head.weight": p["mu.W"], "mu_head.bias": p["mu.b"],
          "lane_head.weight": p["lane.W"], "lane_head.bias": p["lane.b"],
          "v_head.weight": np.zeros((1, HIDDEN[-1])), "v_head.bias": np.zeros(1), "log_std": p["log_std"]}
    return {k: np.ascontiguousarray(v, dtype=F32) for k, v in sd.items()}


class ExportedPolicy:
    """내보낸 가중치로 HybridActorCritic.det_action 과 같은 계산을 한다 (torch 없이 평가할 때)."""

    def __init__(self, sd):
        self.s = {k: np.asarray(v, dtype=F32) for k, v in sd.items()}

    def predict(self, obs, deterministic=True):
        s = self.s
        h = np.maximum(s["trunk.0.weight"] @ np.asarray(obs, dtype=F32) + s["trunk.0.bias"], 0)
        h = np.maximum(s["trunk.2.weight"] @ h + s["trunk.2.bias"], 0)
        mu = np.tanh(s["mu_head.weight"] @ h + s["mu_head.bias"])[0]
        lane = LANE_CMDS[int(np.argmax(s["lane_head.weight"] @ h + s["lane_head.bias"]))]
        return np.array([mu, lane], dtype=F32)


def save_model(path, actor, check_obs=None):
    """정책을 팀 공통 PPO 형식(.pt)으로 저장한다. --no-torch 면 같은 이름의 numpy 파일로 저장한다 (시험용).
    check_obs 를 주면 저장한 파일을 팀 공통 불러오기(test.py 의 load_agent)로 다시 읽어 같은 행동이 나오는지 확인한다."""
    sd = export_state(actor)
    tmp = path + ".tmp"                                # 다 쓴 뒤에 이름을 바꾼다 (쓰는 도중에 끊겨도 반쪽짜리 파일이 남지 않게)
    if CTX["cfg"].no_torch:
        with open(tmp, "wb") as f:
            np.savez(f, **sd)
        os.replace(tmp, path)
        return
    import torch
    state = {k: torch.from_numpy(v.copy()) for k, v in sd.items()}
    try:
        from env.observation_schema import metadata
        torch.save({"algorithm": "ppo", "state_dict": state, **metadata()}, tmp)
    except ImportError:                                # v3 환경: test.py 가 state_dict 를 그대로 저장한 파일을 읽는다
        torch.save(state, tmp)
    os.replace(tmp, path)
    if check_obs is not None:
        try:
            from test import load_agent
        except ImportError as exc:                     # 평가 쪽 패키지가 없을 때: 학습은 계속하고 알리기만 한다
            say(f"   저장 형식 확인을 건너뜁니다 (test.py 를 불러올 수 없음: {exc})")
            return
        agent = load_agent(path, actor.mean.shape[0], 2)
        got = np.stack([np.asarray(agent.predict(o, deterministic=True), dtype=np.float64) for o in check_obs])
        want = actor.best(check_obs).astype(np.float64)
        d_acc = float(np.abs(got[:, 0] - want[:, 0]).max())
        same = float((got[:, 1] == want[:, 1]).mean())
        if d_acc > 2e-3 or same < 0.995:
            raise SystemExit(f"저장한 모델이 학습 중인 정책과 다르게 행동합니다 (가감속 차이 최대 {d_acc:.4f}, 차선 일치 {same:.1%}). "
                             "train.py 의 HPARAMS (hidden_sizes, activation, policy_type) 가 256-256 / relu / hybrid 인지 확인하세요.")
        say(f"   저장 형식 확인: test.py 의 load_agent 로 다시 읽은 모델과 가감속 차이 최대 {d_acc:.1e}, 차선 일치 {same:.1%} ({len(check_obs)} 장면)")


def load_exported(path):
    with np.load(path, allow_pickle=False) as d:
        if "trunk.0.weight" not in d.files:
            raise SystemExit(f"{path}: numpy 로 저장한 모델이 아닙니다 (torch 형식은 run_all_BC.py --job 으로 평가합니다)")
        return ExportedPolicy({k: d[k] for k in d.files})


# ══════════════════════════════ 평가 ══════════════════════════════
def eval_job(model, seed, episodes, out_json):
    """run_all_BC.py --job 과 같은 평가를 torch 없이 한다 (--no-torch 시험용)."""
    from env.mdp_config import SIMULATION, OBSERVATION, ACTION, REWARD
    from env import daehakro_env
    from env.daehakro_env import DaehakroEnv
    import eval_daehakro
    print(f"모델: {model}\nseed {seed}, {episodes} 에피소드", flush=True)
    policy = load_exported(model)
    env = DaehakroEnv(daehakro_env.build(), None, None, SIMULATION, OBSERVATION, ACTION, REWARD)
    try:
        r = eval_daehakro.evaluate(policy, env, int(episodes), seed=int(seed))
    finally:
        env.close()
    eval_daehakro.report(r)
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in r.items()}
    out.update(model=model, seed=int(seed))
    with open(out_json + ".tmp", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(out_json + ".tmp", out_json)


def merge_results(parts):
    """seed 별 평가 결과(json)를 하나로 합친다."""
    out = {"episodes": 0, "ends": {}, "events": {}, "where": {}, "clean": 0, "lane_changes": 0, "speed_episodes": 0,
           "speed_steps": 0, "steps": 0, "return": 0.0, "length": 0.0, "speed": 0.0, "seeds": []}
    for r in parts:
        n = r["episodes"]
        out["episodes"] += n
        out["seeds"].append(r.get("seed"))
        for k in ("clean", "lane_changes", "speed_episodes", "speed_steps", "steps"):
            out[k] += r.get(k, 0)
        for k in ("return", "length", "speed"):
            out[k] += r.get(k, 0.0) * n
        for name in ("ends", "events", "where"):
            for k, v in (r.get(name) or {}).items():
                out[name][k] = out[name].get(k, 0) + v
    for k in ("return", "length", "speed"):
        out[k] /= max(out["episodes"], 1)
    return out


def result_row(r, steps, phase, ckpt):
    """train_ppo_curriculum.Evaluator.poll 과 같은 칸."""
    ends, ev, n = r.get("ends", {}), r.get("events", {}), max(r.get("episodes", 1), 1)
    return {"steps": steps, "phase": phase, "episodes": n,
            "arrive": ends.get("도착", 0) / n, "clean": r.get("clean", 0) / n,
            "crash": ends.get("차와 충돌", 0) / n, "ped_crash": ends.get("보행자와 충돌", 0) / n,
            "stuck": ends.get("오래 멈춤", 0) / n, "off_route": ends.get("경로 이탈", 0) / n,
            "timeout": ends.get("시간초과", 0) / n,
            "red": ev.get("red_light", 0) / n, "crosswalk": ev.get("crosswalk_violation", 0) / n,
            "yield": ev.get("yield_violation", 0) / n,
            "bus_lane": ev.get("bus_lane_violation", 0) / n, "solid_line": ev.get("solid_line_violation", 0) / n,
            "speeding_eps": r.get("speed_episodes", 0) / n, "speed": r.get("speed", 0.0),
            "return": r.get("return", 0.0), "length": r.get("length", 0.0), "ckpt": os.path.basename(ckpt)}


class ParallelEvaluator:
    """체크포인트를 seed 여러 개로 나눠 동시에 평가한다 (train_ppo_curriculum.Evaluator 와 같은 쓰임새).
    seed 는 --eval-seed, +1, +2 … 로 고정이라 체크포인트끼리 같은 교통 상황에서 비교된다.
    달라진 점: PPO 를 시작하기 전 모델(ckpt_0.pt)을 먼저 평가하고, 정책이 바뀌지 않은 동안(가치망 준비)은 건너뛴다."""

    def __init__(self, run_dir, seed, episodes):
        cfg = CTX["cfg"]
        self.run_dir, self.seed, self.episodes = run_dir, seed, episodes
        self.n = max(1, min(cfg.eval_procs, episodes))
        self.path = os.path.join(run_dir, "eval_log.csv")
        self.jobs, self.cur, self.last_version = [], None, None
        lrn = CTX.get("learner")
        if lrn is not None and lrn.steps == 0:
            ckpt = os.path.join(run_dir, "ckpt_0.pt")
            lrn.save(ckpt)
            say("PPO 를 시작하기 전 모델(BC 만 한 정책)을 평가합니다 → 기준선")
            self.start(ckpt, 0, 4)

    def busy(self):
        return any(p.poll() is None for p, _, _ in self.jobs)

    def start(self, ckpt, steps, phase):
        lrn = CTX.get("learner")
        version = lrn.actor_updates if lrn is not None else None
        if steps > 0 and version is not None and version == self.last_version:
            say(f"{steps:,} 스텝: 지난 평가 뒤로 정책이 바뀌지 않아(가치망 준비 중) 평가를 건너뜁니다")
            return
        self.last_version = version
        cfg = CTX["cfg"]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        counts = [self.episodes // self.n + (1 if i < self.episodes % self.n else 0) for i in range(self.n)]
        self.jobs = []
        for i, k in enumerate(counts):
            out_json = os.path.join(self.run_dir, f"eval_{steps}_s{self.seed + i}.json")
            if os.path.exists(out_json):
                os.remove(out_json)                    # 예전 결과를 이번 결과로 읽지 않게
            log = open(os.path.join(self.run_dir, f"eval_{steps}_s{self.seed + i}.txt"), "w", encoding="utf-8")
            if cfg.no_torch:
                cmd = [sys.executable, os.path.abspath(__file__), "--eval-job", ckpt, str(self.seed + i), str(k), out_json]
            else:
                cmd = [sys.executable, os.path.join(BASE, "run_all_BC.py"), "--job", ckpt, str(self.seed + i), str(k), out_json]
            self.jobs.append((subprocess.Popen(cmd, cwd=BASE, stdout=log, stderr=subprocess.STDOUT, env=env), out_json, log))
        self.cur = (ckpt, steps, phase)

    def poll(self):
        """끝난 평가가 있으면 결과 dict 를 돌려준다."""
        if not self.jobs or self.busy():
            return None
        ckpt, steps, phase = self.cur
        parts = []
        for _, out_json, log in self.jobs:
            log.close()
            if os.path.exists(out_json):
                with open(out_json, encoding="utf-8") as f:
                    parts.append(json.load(f))
        failed = len(parts) < len(self.jobs)
        self.jobs, self.cur = [], None
        if failed:
            return {"steps": steps, "phase": phase, "ckpt": ckpt, "failed": True}
        r = merge_results(parts)
        with open(os.path.join(self.run_dir, f"eval_{steps}.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        row = result_row(r, steps, phase, ckpt)
        new = not os.path.exists(self.path)
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row))
            if new:
                w.writeheader()
            w.writerow(row)
        where = sorted(r["where"].items(), key=lambda kv: -kv[1])[:6]
        if where:
            label = getattr(self, "tag", None) or f"{steps:,} 스텝"
            say(f"   {label} 평가에서 실패한 구간: " + ", ".join(f"{k} {v}" for k, v in where))
        return row

    def wait(self, timeout):
        end = time.time() + timeout
        for p, _, _ in self.jobs:
            try:
                p.wait(timeout=max(1.0, end - time.time()))
            except subprocess.TimeoutExpired:
                p.kill()
        return self.poll()


# ══════════════════════════════ 2)·3) 가치망 준비 → PPO ══════════════════════════════
class BCPPOLearner:
    """train_ppo_curriculum.main() 이 TorchLearner 대신 쓰는 학습기 (act / value / update / save / load 가 같은 모양)."""

    def __init__(self, args, obs_dim, act_dim):
        cfg = CTX["cfg"]
        self.args, self.cfg, self.run_dir = args, cfg, CTX["run_dir"]
        self.rng = np.random.default_rng(args.seed + 1)
        self.actor, self.meta = load_actor(os.path.join(self.run_dir, "bc_init.npz"), self.rng)
        self.teacher = self.meta.pop("teacher", None)      # --from-bc 로 시작했으면 그 BC 모델
        if self.actor.mean.shape[0] != obs_dim or act_dim != 2:
            raise SystemExit(f"사전학습한 정책의 입력 {self.actor.mean.shape[0]} 이 환경 관측 {obs_dim} 과 다릅니다")
        self.actor.p["lane.W"] *= cfg.lane_sharpen         # ③ 차선 점수를 키운다: 가장 높은 쪽은 그대로, 뽑기만 덜 흔들린다
        self.actor.p["lane.b"] *= cfg.lane_sharpen
        self.actor.p["log_std"][...] = math.log(cfg.sigma)
        self.critic = Net(obs_dim, HIDDEN, [("v", 1, 0.0)], self.rng)   # ① 가치망은 따로. 마지막 층은 0 에서 시작
        self.critic.mean, self.critic.std = self.actor.mean, self.actor.std
        self.vnorm = ValueNorm()
        self.opt_a, self.opt_c = Adam(self.actor.p), Adam(self.critic.p)
        self.steps, self.updates, self.actor_updates = 0, 0, 0
        self.demo = None
        if cfg.demo and cfg.bc_coef > 0:
            self.demo = load_demos(cfg.demo)[:3]
        elif cfg.bc_coef > 0:
            say("시범 파일(--demo)이 없어 시범 닻 없이 학습합니다")
        self.checked = False
        self.log_path = os.path.join(self.run_dir, "bcppo_log.csv")
        self.fields = ["time", "steps", "update", "stage", "lr_actor", "lr_critic", "bc_coef", "policy_loss", "value_loss",
                       "ev", "approx_kl", "clip_frac", "epochs", "std", "p_lane", "anchor_accel", "anchor_lane",
                       "anchor_lane_acc", "grad_ppo", "grad_anchor", "grad_critic", "ret_mean", "ret_std"]
        CTX["learner"] = self

    # ---- 행동 ----
    def act(self, obs):
        a, logp = self.actor.sample(obs, self.rng)
        return a, logp, self.value(obs)

    def value(self, obs):
        v = self.critic.forward(obs)["v"][:, 0]
        return (v * self.vnorm.sd + self.vnorm.mu).astype(F32)

    def set_lr(self, lr):
        pass                                               # 학습률은 아래 schedule() 이 정한다

    def schedule(self):
        """지금 스텝의 (단계 이름, 정책 학습률, 시범 닻 가중치)."""
        cfg, s = self.cfg, self.steps
        if s <= cfg.critic_warmup:
            return "가치망 준비", 0.0, cfg.bc_coef
        t = s - cfg.critic_warmup
        ramp = min(1.0, t / max(cfg.actor_warmup, 1))
        coef = cfg.bc_coef_min + (cfg.bc_coef - cfg.bc_coef_min) * 0.5 ** (t / max(cfg.bc_halflife, 1))
        return ("학습률 올리는 중" if ramp < 1.0 else "PPO"), cfg.lr_actor * ramp, coef

    # ---- 업데이트 ----
    def update(self, obs, act, logp, adv, ret, target_kl):
        cfg, args = self.cfg, self.args
        T = len(obs)
        self.steps += T
        self.updates += 1
        stage, lr_a, coef = self.schedule()
        warm = lr_a <= 0.0
        obs = np.ascontiguousarray(obs, dtype=F32)
        act, logp = act.astype(F32), logp.astype(np.float64)
        adv = adv.astype(np.float64)
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        ret = ret.astype(np.float64)
        v_old = self.critic.forward(obs)["v"][:, 0] * self.vnorm.sd + self.vnorm.mu
        ev = 1.0 - float(np.var(ret - v_old)) / (float(np.var(ret)) + 1e-8)     # 이번 경험을 모을 때의 가치망이 맞힌 정도 (1 이 완벽)
        self.vnorm.update(self.critic, ret)
        target = ((ret - self.vnorm.mu) / self.vnorm.sd).astype(F32)
        idx = np.arange(T)
        st = {"policy_loss": 0.0, "approx_kl": 0.0, "clip_frac": 0.0, "entropy": 0.0, "anchor_accel": 0.0, "anchor_lane": 0.0,
              "anchor_lane_acc": 0.0, "grad_ppo": 0.0, "grad_anchor": 0.0}
        v_loss = g_c = 0.0
        nb_c = nb_a = epochs = 0
        # 가치망: 준비 단계에서는 두 배로 돈다 (정책이 고정이라 이 경험이 곧 정답이다)
        for _ in range(args.epochs * (2 if warm else 1)):
            self.rng.shuffle(idx)
            for s in range(0, T, args.minibatch):
                mb = idx[s:s + args.minibatch]
                loss, grads = value_grads(self.critic, obs[mb], target[mb])
                g_c += self.opt_c.step(grads, cfg.lr_critic, max_norm=cfg.grad_norm)
                v_loss += loss
                nb_c += 1
        # 정책: PPO + 시범 닻. 에폭 평균 KL 이 한도를 넘으면 멈춘다
        if not warm:
            for _ in range(args.epochs):
                self.rng.shuffle(idx)
                kls = []
                for s in range(0, T, args.minibatch):
                    mb = idx[s:s + args.minibatch]
                    _, grads, ps = ppo_grads(self.actor, obs[mb], act[mb], logp[mb], adv[mb], cfg.clip)
                    st["grad_ppo"] += grad_norm(grads)
                    if self.demo is not None and coef > 0:
                        d_obs, d_acc, d_lane = self.demo
                        j = np.sort(self.rng.integers(0, len(d_obs), len(mb)))
                        if self.teacher is not None:           # 옮겨 온 BC 모델의 행동이 닻의 정답 (시범 정답으로 당기면 그 모델에서 멀어진다)
                            t_acc, t_lane = bc_teacher(self.teacher, d_obs[j])
                            _, g_bc, bs = bc_grads(self.actor, d_obs[j], np.clip(t_acc, -ACCEL_CAP, ACCEL_CAP), t_lane,
                                                   coef * cfg.bc_accel_weight, coef * cfg.anchor_lane, None, 0.5)
                        else:
                            _, g_bc, bs = bc_grads(self.actor, d_obs[j], d_acc[j], d_lane[j],
                                                   coef * cfg.bc_accel_weight, coef * cfg.anchor_lane, cfg.bc_delta, cfg.bc_caution)
                        st["grad_anchor"] += grad_norm(g_bc)
                        for k in grads:
                            grads[k] = grads[k] + g_bc[k]
                        st["anchor_accel"] += bs["accel"]
                        st["anchor_lane"] += bs["lane"]
                        st["anchor_lane_acc"] += bs["lane_acc"]
                    self.opt_a.step(grads, lr_a, max_norm=cfg.grad_norm)
                    for k in ("policy_loss", "approx_kl", "clip_frac", "entropy"):
                        st[k] += ps[k]
                    kls.append(ps["approx_kl"])
                    nb_a += 1
                epochs += 1
                if target_kl and np.mean(kls) > 1.5 * target_kl:
                    break
            self.actor_updates += 1
            lo, hi = math.log(args.min_std), math.log(cfg.max_sigma)
            np.clip(self.actor.p["log_std"], lo, hi, out=self.actor.p["log_std"])
        out = {k: v / max(nb_a, 1) for k, v in st.items()}
        c = self.actor.dist(obs[:8192])
        out.update(value_loss=v_loss / max(nb_c, 1) * self.vnorm.sd ** 2, epochs=epochs,
                   p_lane=float(1.0 - np.exp(c["lsm"][:, 1]).mean()), std=float(np.exp(self.actor.p["log_std"][0])))
        row = {"time": stamp(), "steps": self.steps, "update": self.updates, "stage": stage, "lr_actor": f"{lr_a:.2e}",
               "lr_critic": f"{cfg.lr_critic:.2e}", "bc_coef": round(coef, 4), "ev": round(ev, 4),
               "grad_critic": round(g_c / max(nb_c, 1), 4), "ret_mean": round(self.vnorm.mu, 3), "ret_std": round(self.vnorm.sd, 3)}
        for k in self.fields:
            if k not in row:
                row[k] = round(out[k], 5) if isinstance(out.get(k), float) else out.get(k, "")
        new = not os.path.exists(self.log_path)
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.fields)
            if new:
                w.writeheader()
            w.writerow(row)
        print(f"           [{stage}] 정책 학습률 {lr_a:.1e} | 시범 닻 {coef:.2f} | 가치망 맞힘(ev) {ev:.2f} | "
              + (f"시범과의 차이: 가감속 {out['anchor_accel']:.4f}, 차선 정답률 {out['anchor_lane_acc']:.2%}"
                 if (not warm and self.demo is not None) else "정책 고정"), flush=True)
        return out

    # ---- 저장 / 불러오기 ----
    def save(self, path, opt_path=None):
        check = None
        if not self.checked and not self.cfg.no_torch:
            check = (self.demo[0] if self.demo is not None else self.rng.random((512, self.actor.mean.shape[0]), dtype=F32))[:512]
            self.checked = True
        save_model(path, self.actor, check)
        if opt_path:                                       # last.pt 를 저장할 때: 이어서 학습할 내부 상태도 함께
            state = {"mean": self.actor.mean, "std": self.actor.std,
                     "counters": np.array([self.steps, self.updates, self.actor_updates], dtype=np.int64),
                     "vnorm": np.array([self.vnorm.mu, self.vnorm.sd, float(self.vnorm.ready)]),
                     "rng": np.array(json.dumps(self.rng.bit_generator.state))}
            state.update({"a/" + k: v for k, v in self.actor.p.items()})
            state.update({"c/" + k: v for k, v in self.critic.p.items()})
            state.update(self.opt_a.state("oa"))
            state.update(self.opt_c.state("oc"))
            tmp = os.path.join(os.path.dirname(path), "learner_state.tmp.npz")
            np.savez(tmp, **state)
            os.replace(tmp, os.path.join(os.path.dirname(path), "learner_state.npz"))

    def load(self, path, opt_path=None):
        src = os.path.join(os.path.dirname(path), "learner_state.npz")
        if not os.path.exists(src):
            raise SystemExit(f"{src} 가 없어 이어서 학습할 수 없습니다 (이 파일로 시작한 학습만 --resume 할 수 있습니다)")
        with np.load(src, allow_pickle=False) as d:
            for k in self.actor.p:
                self.actor.p[k][...] = d["a/" + k]
            for k in self.critic.p:
                self.critic.p[k][...] = d["c/" + k]
            self.opt_a.load(d, "oa")
            self.opt_c.load(d, "oc")
            self.steps, self.updates, self.actor_updates = (int(x) for x in d["counters"])
            self.vnorm.mu, self.vnorm.sd, ready = (float(x) for x in d["vnorm"])
            self.vnorm.ready = bool(ready)
            self.actor.mean[...], self.actor.std[...] = d["mean"], d["std"]
            self.rng.bit_generator.state = json.loads(str(d["rng"]))
        self.checked = True


def final_eval(cfg, run_dir):
    """학습이 끝까지 간 뒤, 처음(ckpt_0)·최고 기록(best)·마지막(last) 모델을 '같은 판'으로 더 많이 평가해 견준다.
    학습 중 평가는 판 수가 적어서(--eval-episodes) ±15%p 안팎으로 흔들리고, best.pt 는 그중 가장 높게 나온 것이라
    실제보다 좋아 보인다. 여기서는 학습 중 평가와 다른 seed 를 쓴다. 결과는 results/<run>/final/ 에 남는다."""
    if cfg.final_eval <= 0:
        return
    try:
        with open(os.path.join(run_dir, "state.json"), encoding="utf-8") as f:
            steps = int(json.load(f)["steps"])
    except (OSError, ValueError, KeyError):
        return
    if steps < cfg.total:                              # Ctrl+C 로 멈춘 경우: 이어서 학습이 끝났을 때 한다
        return
    seen, models = set(), []
    for label, name in (("처음 (PPO 전)", "ckpt_0.pt"), ("최고 기록", "best.pt"), ("마지막", "last.pt")):
        path = os.path.join(run_dir, name)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            digest = hashlib.md5(f.read()).hexdigest()
        if digest in seen:                             # 같은 파일 (예: 최고 기록이 처음 모델 그대로)
            continue
        seen.add(digest)
        models.append((label, name, path))
    if len(models) < 2:
        return
    d = os.path.join(run_dir, "final")
    os.makedirs(d, exist_ok=True)
    CTX.pop("learner", None)                           # 학습은 끝났다 (평가기가 '정책이 안 바뀌었다'며 건너뛰지 않게)
    ev = ParallelEvaluator(d, cfg.eval_seed + 1000, cfg.final_eval)
    ev.n = max(1, min(max(cfg.eval_procs, min(cfg.workers, 6)), cfg.final_eval))
    say(f"최종 평가: 모델 {len(models)}개를 같은 {cfg.final_eval}판으로 견줍니다 (seed {ev.seed}~{ev.seed + ev.n - 1}, 학습 중 평가와 다른 판)")
    lines = []
    for i, (label, name, path) in enumerate(models):
        ev.tag = f"최종 평가 — {label}"
        ev.start(path, i, 0)
        row = ev.wait(6 * 3600)
        if row is None or row.get("failed"):
            say(f"   {label} ({name}): 평가 실패 — {d} 의 eval_{i}_s*.txt 확인")
            continue
        lines.append(f"   {label:<11s} {name:<10s}: 도착 {row['arrive']:.0%}, 위반 없이 도착 {row['clean']:.0%}, 충돌 {row['crash'] + row['ped_crash']:.0%} "
                     f"(차 {row['crash']:.0%} + 보행자 {row['ped_crash']:.0%}), 멈춤 {row['stuck']:.0%}, 이탈 {row['off_route']:.0%} ({row['episodes']}판)")
        say(lines[-1])
    with open(os.path.join(d, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(f"최종 평가 ({stamp()}, {steps:,} 스텝, 같은 {cfg.final_eval}판)\n" + "\n".join(lines) + "\n")


def final_curriculum(base, overrides):
    """보상 일정: 처음부터 4단계(모든 벌점 최종값). --reward 로 준 값은 그 위에 덮어쓴다."""

    class FinalCurriculum(base.Curriculum):
        def __init__(self, gate_scale=1.0):
            super().__init__(gate_scale)
            self.phase, self.s_crash, self.s_rules = 4, 1.0, 1.0

        def rewards(self):
            r = super().rewards()
            r.update(overrides)
            return r

    return FinalCurriculum


# ══════════════════════════════ 계산 점검 ══════════════════════════════
def selfcheck():
    """기울기를 수치 미분과 비교하고, 정규화를 첫 층에 합친 모델이 같은 행동을 내는지 본다 (SUMO·torch 없이)."""
    rng = np.random.default_rng(0)
    D, N, ok = 12, 64, True
    global HIDDEN
    keep, HIDDEN = HIDDEN, (16, 16)
    try:
        actor = Actor(D, rng, 0.3, np.float64)
        critic = Net(D, HIDDEN, [("v", 1, 1.0)], rng, np.float64)
        for net in (actor, critic):
            net.mean, net.std = rng.normal(0, 0.3, D), rng.uniform(0.2, 1.5, D)
            for k in net.p:
                if k != "log_std":
                    net.p[k] = net.p[k] + rng.normal(0, 0.3, net.p[k].shape)
        obs = rng.normal(0, 1, (N, D))
        act = np.stack([rng.uniform(-1, 1, N), rng.choice([-1.0, 0.0, 1.0], N)], 1)
        old = actor.log_prob(actor.dist(obs), act)[0] + rng.normal(0, 0.15, N)
        adv, tgt = rng.normal(0, 1, N), rng.normal(0, 1, N)
        lane = rng.integers(0, 3, N)
        acc = rng.uniform(-0.98, 0.98, N)
        cases = [("BC 손실 (제곱)", actor, lambda: bc_grads(actor, obs, acc, lane, 3.0, 0.7, None)[:2]),
                 ("BC 손실 (꺾고 기울인 것)", actor, lambda: bc_grads(actor, obs, acc, lane, 3.0, 0.7, 0.25, 0.7)[:2]),
                 ("BC 손실 (꺾은 것)", actor, lambda: bc_grads(actor, obs, acc, lane, 3.0, 0.7, 0.25)[:2]),
                 ("PPO 손실", actor, lambda: ppo_grads(actor, obs, act, old, adv, 0.1)[:2]),
                 ("가치 손실", critic, lambda: value_grads(critic, obs, tgt))]
        for name, net, fn in cases:
            _, grads = fn()
            worst = 0.0
            for k, g in grads.items():
                flat = net.p[k].reshape(-1)
                for i in rng.choice(flat.size, min(flat.size, 12), replace=False):
                    w0 = flat[i]
                    flat[i] = w0 + 1e-6
                    up = fn()[0]
                    flat[i] = w0 - 1e-6
                    dn = fn()[0]
                    flat[i] = w0
                    num = (up - dn) / 2e-6
                    worst = max(worst, abs(num - g.reshape(-1)[i]) / max(1e-4, abs(num) + abs(g.reshape(-1)[i])))
            good = worst < 1e-5
            ok &= good
            print(f"  {'OK ' if good else '틀림'} {name}: 수치 미분과의 상대 차이 최대 {worst:.1e}")
        # 가치 정규화: 통계를 바꿔도 가치망이 내는 실제 값은 그대로여야 한다
        vn = ValueNorm()
        vn.update(critic, rng.normal(3, 5, 500))
        before = critic.forward(obs)["v"][:, 0] * vn.sd + vn.mu
        vn.update(critic, rng.normal(-8, 11, 500))
        after = critic.forward(obs)["v"][:, 0] * vn.sd + vn.mu
        good = float(np.abs(before - after).max()) < 1e-9
        ok &= good
        print(f"  {'OK ' if good else '틀림'} 가치 정규화: 통계를 바꾼 뒤 가치 차이 최대 {np.abs(before - after).max():.1e}")
    finally:
        HIDDEN = keep
    # 내보내기: 정규화를 첫 층에 합친 가중치(float32)로 계산한 행동 = 학습 중인 정책의 행동
    a32 = Actor(116, rng, 0.2)
    a32.mean, a32.std = rng.normal(0.2, 0.3, 116).astype(F32), rng.uniform(0.05, 1.0, 116).astype(F32)
    for k in a32.p:
        if k != "log_std":
            a32.p[k] = (a32.p[k] + rng.normal(0, 0.05, a32.p[k].shape)).astype(F32)
    x = rng.uniform(-1, 1, (2000, 116)).astype(F32)
    pol = ExportedPolicy(export_state(a32))
    got, want = np.stack([pol.predict(o) for o in x]), a32.best(x)
    d_acc, same = float(np.abs(got[:, 0] - want[:, 0]).max()), float((got[:, 1] == want[:, 1]).mean())
    good = d_acc < 2e-3 and same > 0.995
    ok &= good
    print(f"  {'OK ' if good else '틀림'} 내보내기: 가감속 차이 최대 {d_acc:.1e}, 차선 일치 {same:.2%}")
    # --from-bc: BCPolicy 를 복사한 직후, 차선 명령이 BCPolicy 의 규칙(±0.5 에서 자름)과 같고 가감속 출력이 tanh(1.2·y) 인가
    sd = {"obs_mean": rng.normal(0, 0.2, 116).astype(F32), "obs_std": rng.uniform(0.05, 1.0, 116).astype(F32),
          "fc1.weight": rng.normal(0, 0.15, (HIDDEN[0], 116)).astype(F32), "fc1.bias": rng.normal(0, 0.1, HIDDEN[0]).astype(F32),
          "fc2.weight": rng.normal(0, 0.1, (HIDDEN[1], HIDDEN[0])).astype(F32), "fc2.bias": rng.normal(0, 0.1, HIDDEN[1]).astype(F32),
          "fc3.weight": rng.normal(0, 0.12, (2, HIDDEN[1])).astype(F32), "fc3.bias": rng.normal(0, 0.1, 2).astype(F32)}
    x = rng.uniform(-1, 1, (20000, 116)).astype(F32)
    _, t_lane = bc_teacher(sd, x)
    h = np.maximum(((x - sd["obs_mean"]) / sd["obs_std"]) @ sd["fc1.weight"].T + sd["fc1.bias"], 0)
    y0 = (np.maximum(h @ sd["fc2.weight"].T + sd["fc2.bias"], 0) @ sd["fc3.weight"].T + sd["fc3.bias"])[:, 0]
    c = actor_from_bc(sd, rng, 0.2, 8.0).dist(x)
    same = float((np.argmax(c["lane"], axis=1) == t_lane).mean())
    share = np.bincount(t_lane, minlength=3) / len(t_lane)
    d_acc = float(np.abs(c["mean"] - np.tanh(1.2 * y0)).max())
    good = same > 0.999 and share.min() > 0.02 and d_acc < 1e-3
    ok &= good
    print(f"  {'OK ' if good else '틀림'} BC 모델 옮기기: 차선 일치 {same:.3%} (왼쪽 {share[0]:.0%} / 유지 {share[1]:.0%} / 오른쪽 {share[2]:.0%} 인 시험 입력), "
          f"가감속 출력 차이 최대 {d_acc:.1e}")
    print("결과: " + ("모두 OK" if ok else "틀린 항목이 있습니다"))
    return ok


# ══════════════════════════════ 메인 ══════════════════════════════
def parse_args(argv):
    cpu = os.cpu_count() or 4
    ap = argparse.ArgumentParser(description="BC 사전학습 → 가치망 준비 → PPO 미세조정 (v4.1)",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    g = ap.add_argument_group("실행")
    g.add_argument("--run", default=time.strftime("bcppo_%m%d_%H%M"), help="results/ 아래 폴더 이름")
    g.add_argument("--resume", action="store_true", help="같은 --run 폴더에서 이어서 학습")
    g.add_argument("--demo", nargs="+", default=None, help="시범 npz (여러 개면 이어 붙인다). 사전학습과 시범 닻에 쓴다")
    g.add_argument("--init", default=None, help="사전학습을 건너뛰고 이 bc_init.npz 에서 시작")
    g.add_argument("--from-bc", default=None, metavar="model.pt",
                   help="사전학습 대신 train_bc.py / run_all_BC.py 가 만든 BC 모델을 PPO 신경망으로 옮겨 거기서 시작")
    g.add_argument("--conv-steps", type=int, default=6000, help="--from-bc: 옮긴 뒤 BC 모델의 출력에 맞춰 다시 학습하는 횟수")
    g.add_argument("--conv-noise", type=float, default=0.3, help="--from-bc: 맞출 때 관측을 흔드는 크기 (정규화한 눈금)")
    g.add_argument("--bc-only", action="store_true", help="사전학습과 그 평가까지만 하고 끝낸다")
    g.add_argument("--selfcheck", action="store_true", help="기울기·내보내기 계산을 점검하고 끝낸다 (SUMO 없이)")
    g.add_argument("--no-torch", action="store_true", help=argparse.SUPPRESS)      # torch 없는 곳에서의 시험용
    g.add_argument("--seed", type=int, default=0)
    b = ap.add_argument_group("1) BC 사전학습")
    b.add_argument("--bc-epochs", type=int, default=40)
    b.add_argument("--bc-max-steps", type=int, default=60_000, help="갱신 횟수 상한 (시범이 아주 많을 때)")
    b.add_argument("--bc-batch", type=int, default=1024)
    b.add_argument("--bc-lr", type=float, default=1e-3, help="시작 학습률 (코사인으로 --bc-lr-end 까지 줄인다)")
    b.add_argument("--bc-lr-end", type=float, default=1e-5)
    b.add_argument("--bc-wd", type=float, default=1e-4, help="가중치 감쇠")
    b.add_argument("--bc-noise", type=float, default=0.0, help="입력 흔들기 크기 (정규화한 눈금)")
    b.add_argument("--bc-val", type=float, default=0.1, help="검증에 떼어 두는 판의 비율")
    b.add_argument("--bc-accel-weight", type=float, default=4.0, help="가감속 오차의 가중치 (차선 교차엔트로피가 1)")
    b.add_argument("--bc-delta", type=float, default=0.2, help="가감속 오차가 이보다 크면 직선으로 (0 이면 제곱 오차만)")
    b.add_argument("--bc-caution", type=float, default=0.5,
                   help="0.5 보다 크면 시범보다 '덜 밟은' 오차를 더 크게 벌준다 (0.5 = 양쪽 같게). 시범 닻에도 같은 값을 쓴다")
    b.add_argument("--bc-grad-norm", type=float, default=5.0)
    b.add_argument("--bc-pick", choices=["best", "last"], default="last", help="마지막 시점 / 검증 손실이 가장 낮았던 시점")
    p = ap.add_argument_group("2)·3) 가치망 준비와 PPO")
    p.add_argument("--workers", type=int, default=max(2, min(8, cpu - 4)), help="동시에 돌릴 SUMO 수")
    p.add_argument("--total", type=int, default=1_000_000, help="총 학습 스텝 (가치망 준비 포함)")
    p.add_argument("--n-steps", type=int, default=512, help="업데이트 1번에 SUMO 하나가 모으는 스텝")
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--minibatch", type=int, default=512)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--lam", type=float, default=0.95)
    p.add_argument("--critic-warmup", type=int, default=40_000, help="처음 이 스텝 동안은 정책을 고정하고 가치망만 학습")
    p.add_argument("--actor-warmup", type=int, default=40_000, help="그 뒤 이 스텝에 걸쳐 정책 학습률을 0 에서 올린다")
    p.add_argument("--lr-actor", type=float, default=3e-5)
    p.add_argument("--lr-critic", type=float, default=3e-4)
    p.add_argument("--clip", type=float, default=0.1, help="PPO 의 ε")
    p.add_argument("--target-kl", type=float, default=0.02, help="업데이트 1번에 정책이 바뀌는 폭 한도")
    p.add_argument("--grad-norm", type=float, default=0.5)
    p.add_argument("--sigma", type=float, default=0.2, help="가감속 탐험 폭의 시작값")
    p.add_argument("--min-sigma", type=float, default=0.05)
    p.add_argument("--max-sigma", type=float, default=0.35)
    p.add_argument("--lane-sharpen", type=float, default=2.0, help="사전학습 뒤 차선 점수에 곱하는 값")
    p.add_argument("--bc-coef", type=float, default=1.0, help="시범 닻 가중치의 시작값 (0 이면 닻 없음)")
    p.add_argument("--bc-coef-min", type=float, default=0.3, help="시범 닻 가중치의 바닥")
    p.add_argument("--bc-halflife", type=int, default=200_000, help="시범 닻 가중치가 바닥까지의 절반으로 줄어드는 스텝")
    p.add_argument("--anchor-lane", type=float, default=1.0, help="시범 닻 안에서 차선 교차엔트로피의 가중치")
    p.add_argument("--reward", nargs="*", default=[], metavar="이름=값",
                   help="학습용 보상을 바꾼다 (예: crash_penalty=50 crash_pedestrian_penalty=80 tailgate_penalty=0.3)")
    e = ap.add_argument_group("평가")
    e.add_argument("--eval-every", type=int, default=50_000)
    e.add_argument("--eval-episodes", type=int, default=30)
    e.add_argument("--eval-seed", type=int, default=99)
    e.add_argument("--eval-procs", type=int, default=2, help="평가를 나눠 돌릴 SUMO 수 (seed 는 --eval-seed 부터 하나씩)")
    e.add_argument("--final-eval", type=int, default=100,
                   help="학습이 끝난 뒤 처음·최고·마지막 모델을 같은 판으로 견줄 때의 판 수 (0 이면 하지 않는다)")
    cfg = ap.parse_args(argv)
    if cfg.bc_delta is not None and cfg.bc_delta <= 0:
        cfg.bc_delta = None
    return cfg


def reward_overrides(items):
    from env.daehakro_env import REWARD
    out = {}
    for item in items:
        k, _, v = item.partition("=")
        if k not in REWARD:
            raise SystemExit(f"--reward {item}: 없는 보상 이름입니다. 쓸 수 있는 이름: {', '.join(REWARD)}")
        out[k] = float(v)
    return out


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--eval-job":
        eval_job(*sys.argv[2:6])
        return
    cfg = parse_args(sys.argv[1:])
    if cfg.selfcheck:
        sys.exit(0 if selfcheck() else 1)
    import train_ppo_curriculum as base               # 환경 작업자·GAE·기록·보상 일정을 그대로 쓴다

    run_dir = os.path.join(BASE, "results", cfg.run)
    started = os.path.exists(os.path.join(run_dir, "state.json"))
    if started and not cfg.resume:
        sys.exit(f"{run_dir} 에 이미 학습 기록이 있습니다. 이어서 하려면 --resume, 새로 하려면 다른 --run 이름을 쓰세요.")
    if cfg.resume and not started:
        sys.exit(f"{run_dir} 에 이어서 할 학습 기록(state.json)이 없습니다.")
    os.makedirs(run_dir, exist_ok=True)
    CTX.update(cfg=cfg, run_dir=run_dir)
    if not cfg.no_torch:
        try:
            import torch
            torch.set_num_threads(1)
        except ImportError:
            sys.exit("torch 를 불러올 수 없습니다. 학습 환경(conda)이 켜져 있는지 확인하세요.")
    overrides = reward_overrides(cfg.reward)
    shutil.copy(os.path.abspath(__file__), os.path.join(run_dir, os.path.basename(__file__)))
    with open(os.path.join(run_dir, "bcppo_config.json"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": stamp(), **vars(cfg)}, ensure_ascii=False) + "\n")

    if cfg.resume and cfg.demo is None:                # 이어서 할 때 --demo 를 생략하면 처음에 쓴 시범을 그대로 쓴다
        with np.load(os.path.join(run_dir, "bc_init.npz"), allow_pickle=False) as d:
            cfg.demo = json.loads(str(d["meta"])).get("demo") or None
    pretrain_bc(cfg, run_dir)

    if cfg.bc_only:
        actor, _ = load_actor(os.path.join(run_dir, "bc_init.npz"), np.random.default_rng(0))
        ckpt = os.path.join(run_dir, "ckpt_0.pt")
        demo_obs = load_demos(cfg.demo)[0][:512] if cfg.demo else None
        save_model(ckpt, actor, demo_obs)
        from env import daehakro_env
        daehakro_env.build()                           # 도로 파일 확인은 평가를 나눠 띄우기 전에 한 번만 (동시에 다시 만들지 않게)
        ev = ParallelEvaluator(run_dir, cfg.eval_seed, cfg.eval_episodes)
        say(f"BC 만 한 정책을 평가합니다: seed {cfg.eval_seed}~{cfg.eval_seed + ev.n - 1}, 모두 {cfg.eval_episodes} 에피소드")
        ev.start(ckpt, 0, 0)
        row = ev.wait(6 * 3600)
        if row is None or row.get("failed"):
            sys.exit(f"평가 실패 — {run_dir} 의 eval_0_s*.txt 확인")
        say(f"BC 결과: 도착 {row['arrive']:.0%}, 위반 없이 도착 {row['clean']:.0%}, 충돌 {row['crash'] + row['ped_crash']:.0%} "
            f"(차 {row['crash']:.0%} + 보행자 {row['ped_crash']:.0%}), 멈춤 {row['stuck']:.0%}, 이탈 {row['off_route']:.0%}, "
            f"시간초과 {row['timeout']:.0%} ({row['episodes']} 에피소드)")
        return

    # train_ppo_curriculum.main() 을 그대로 돌리되, 학습기·보상 일정·평가기만 이 파일의 것으로 바꾼다
    base.TorchLearner = BCPPOLearner
    base.Curriculum = final_curriculum(base, overrides)
    base.Evaluator = ParallelEvaluator
    base.LR_PHASE4 = (cfg.lr_actor, cfg.lr_actor, 0)   # train_log.csv 의 lr 칸에 적히는 값 (실제 값은 bcppo_log.csv)
    sys.argv = [sys.argv[0], "--run", cfg.run, "--workers", str(cfg.workers), "--total", str(cfg.total),
                "--n-steps", str(cfg.n_steps), "--epochs", str(cfg.epochs), "--minibatch", str(cfg.minibatch),
                "--lr", str(cfg.lr_actor), "--gamma", str(cfg.gamma), "--lam", str(cfg.lam),
                "--target-kl", str(cfg.target_kl), "--min-std", str(cfg.min_sigma),
                "--eval-every", str(cfg.eval_every), "--eval-episodes", str(cfg.eval_episodes),
                "--eval-seed", str(cfg.eval_seed), "--seed", str(cfg.seed)] + (["--resume"] if cfg.resume else [])
    say(f"2) 가치망 준비 {cfg.critic_warmup:,} 스텝 (정책 고정) → 3) PPO: 정책 학습률 {cfg.lr_actor:.0e} "
        f"({cfg.actor_warmup:,} 스텝에 걸쳐 올림), ε {cfg.clip}, 시범 닻 {cfg.bc_coef} → {cfg.bc_coef_min} "
        f"(반감 {cfg.bc_halflife:,} 스텝)" + (f", 보상 변경 {overrides}" if overrides else ""))
    base.main()
    try:
        final_eval(cfg, run_dir)
    except Exception as exc:                           # 덧붙인 평가다. 실패해도 학습 결과는 그대로다
        say(f"최종 평가를 건너뜁니다 ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    main()
