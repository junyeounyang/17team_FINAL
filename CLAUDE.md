# Claude Code 작업 규칙

이 저장소의 작업 규칙은 `AGENTS.md` 에 있다. 반드시 먼저 읽고 따른다. 요약:

- **절대 수정 금지**: `env/` 전체, `eval_daehakro.py`, `collect_pomdp_data_daehakro.py`, `test.py`, `train.py`, `algorithms/`, `utils/`, `check_setup.py`, `PROTECTED.sha256`
- **수정 가능**: `train_ppo_curriculum.py`, `train_bc.py`·`run_all_BC.py`·`collect_demo.py`(옵션 위주), `example_loader.py` 의 복사본
- 새 학습 방법은 새 파일로, 다른 형식 모델 평가는 `eval_daehakro.py --loader`
- 작업 뒤 `python check_setup.py` 가 모두 OK 인지 확인
