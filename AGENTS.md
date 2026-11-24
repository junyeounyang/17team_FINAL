# 작업 규칙 (AI 코딩 도구용) — 17조 대학로 자율주행 공통 학습 환경 v3

이 저장소는 팀 세 명이 같은 조건으로 학습·평가하기 위한 공통 환경이다. 아래 규칙은 사용자가 따로 말하지 않아도 항상 지킨다.

## 절대 수정하지 않는 파일·폴더
- `env/` 의 모든 파일 (`*.py`, `data/`, `sumo/daehakro/` 의 도로 파일 포함)
- `eval_daehakro.py`, `collect_pomdp_data_daehakro.py`, `test.py`, `train.py`
- `algorithms/`, `utils/`
- `check_setup.py`, `PROTECTED.sha256`

이 파일들에는 도로·교통, 관측 51개·행동 2개, 충돌 기준(2.5 m), 위반 판정, 에피소드 규칙, 평가 규칙, 데이터 수집 형식, 모델 불러오기, PPO 신경망 구조가 들어 있다.
버그처럼 보여도, 더 좋게 만들 수 있어 보여도 고치지 않는다. 고쳐야 할 것 같으면 코드를 바꾸지 말고 사용자에게 알린다.

## 수정해도 되는 파일
- `train_ppo_curriculum.py` — 보상 일정·학습용 감점·하이퍼파라미터
- `train_bc.py`, `run_all_BC.py`, `collect_demo.py` — 명령줄 옵션으로 조절. 방법을 바꾸려면 복사해서 새 이름으로
- `example_loader.py` — 복사본을 만들어 고친다

## 새 기능은 새 파일로
- 새 학습 방법(BC+PPO 변환, 새 신경망 등)은 새 파일로 추가한다 (예: `train_bc_ppo.py`, `algorithms/bc_ppo.py`).
- 다른 형식의 모델 평가는 `python eval_daehakro.py <모델> --loader <내 로더.py>` 를 쓴다. `test.py` 를 고치지 않는다.
- 학습 보상은 환경을 만들 때 `reward` 인자(`{이름: 값}`)나 `env.drw[이름] = 값` 으로 바꾼다. `env/daehakro_env.py` 의 `REWARD` 표는 건드리지 않는다.

## 작업 뒤 확인
- `python check_setup.py` 를 실행해 모두 OK 인지 확인한다. CHANGED 가 있으면 그 파일을 원래대로 되돌린다.
- SUMO 는 1.27.1, 순간이동은 꺼져 있어야 한다 (`time-to-teleport -1`).
