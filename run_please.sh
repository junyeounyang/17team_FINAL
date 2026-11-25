#!/bin/bash
# 관측 50칸 (환경이 계산해 주던 [45] [46] [47] 을 뺀 것) 한 벌: 시범 자르기 → BC (seed 3개) → 가장 좋은 BC 에서 PPO → 집계.
#   bash run_please.sh          처음부터 끝까지
#   bash run_please.sh bc       BC 평가까지만 하고 멈춘다 (성능이 얼마나 떨어지는지 먼저 볼 때)
# 시범은 다시 모으지 않는다. ../17team_v3occ/data/van_on.npz (53칸) 에서 세 칸만 잘라 쓴다.
# 끊겨도 같은 명령을 다시 실행하면 끝난 단계는 건너뛴다.
UNTIL=${1:-all}
export DAEHAKRO_OCCLUSION=1
TAG=please_on
SRC=${SRC:-../17team_v3occ/data/van_on.npz}
cd "$(dirname "$0")" || exit 1
say() { echo; echo "===== $(date +%H:%M:%S) $* ====="; }

say "0. 도로·교통 파일 만들기 (택배 탑차 4%)"
python -m env.daehakro_builder > /dev/null || exit 1
grep -q car_van env/sumo/daehakro/daehakro.rou.xml || { echo "교통 파일에 탑차가 없습니다"; exit 1; }

say "1. 시범 파일에서 세 칸 자르기"
mkdir -p data
[ -f data/$TAG.npz ] || python cut_demo.py "$SRC" data/$TAG.npz || exit 1

say "2. BC 학습 3개 + 평가"
python run_all_BC.py --data data/$TAG.npz --tag $TAG --seeds 0 10 20 --epochs 60 --until mid --workers 8 || exit 1
BEST=$(python - "$TAG" <<'PY'
import glob, json, sys
tag = sys.argv[1]
rows = []
for p in glob.glob(f"logs_{tag}/mid_s*.json"):
    r = json.load(open(p, encoding="utf-8"))
    rows.append((r["ends"].get("도착", 0), r.get("clean", 0), p.split("mid_")[1].split(".")[0]))
print(f"results/bc_{tag}_{max(rows)[2]}/model.pt" if rows else "")
PY
)
[ -n "$BEST" ] || { echo "BC 평가 결과가 없습니다"; exit 1; }
echo "PPO 출발점: $BEST"
[ "$UNTIL" = "bc" ] && { say "BC 까지 끝. 이어서 하려면: bash run_please.sh"; exit 0; }

say "3. PPO 60만 스텝 (끝나면 처음·최고·마지막을 같은 100판으로 견준다)"
if [ -f results/ppo_$TAG/state.json ]; then R="--resume"; else R="--from-bc $BEST --demo data/$TAG.npz"; fi
python train_bc_ppo.py --run ppo_$TAG $R --workers 8 --total 600000 || exit 1
cat results/ppo_$TAG/final/summary.txt

say "4. 가림 장면 집계 (BC 와 PPO 를 같은 300판으로. 모델마다 15분쯤 조용히 돈다)"
python occ_report.py $BEST results/ppo_$TAG/last.pt --episodes 300 --procs 8 || exit 1
say "끝. 결과: results/ppo_$TAG/final/summary.txt, results/ppo_$TAG/occ_report.txt"
