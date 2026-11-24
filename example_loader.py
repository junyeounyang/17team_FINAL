"""eval_daehakro.py --loader 예시 — 수업 형식(BC / PPO)이 아닌 모델을 평가할 때 이 파일을 '복사해서' 고쳐 쓴다.

    python eval_daehakro.py results/my_run/model.pt --loader my_loader.py --episodes 300 --seed 110

규칙 (이것만 지키면 eval_daehakro.py·test.py 를 고치지 않고 같은 평가를 받는다):
    load_agent(model_path, obs_dim, act_dim) 함수를 둔다.
    돌려주는 객체에 predict(obs, deterministic=True) 가 있어야 하고,
    [가감속(-1 ~ 1), 차로변경(+1 왼쪽 / 0 유지 / -1 오른쪽)] 을 돌려준다.
    관측은 환경이 주는 53개 그대로 들어온다 (정규화가 필요하면 이 안에서 한다).

아래는 동작하는 예시다: train_bc.py 로 만든 BC 모델을 이 방식으로 불러온다 (test.py 의 BC 불러오기와 결과가 같다).
"""
import numpy as np

from algorithms.bc import BCPolicy


class Wrapped:
    """predict 만 있으면 된다. 내 신경망을 여기서 감싼다."""

    def __init__(self, policy):
        self.policy = policy

    def predict(self, obs, deterministic=True):
        action = self.policy.predict(np.asarray(obs, dtype=np.float32), deterministic=True)
        return np.asarray(action, dtype=np.float32)


def load_agent(model_path, obs_dim, act_dim):
    policy = BCPolicy.load(model_path, device="cpu")
    return Wrapped(policy)
