#!/bin/bash
# 사이렌 관측을 현실에 가깝게 고친 판 한 벌 (소리만 들림 + 차 너머로는 50 m 안에서 차로가 보임 + 본 차로를 10초 기억).
#   bash run_train.sh
# 시범 2,000판 수집 (90분) → BC 3개 + 평가 (40분) → 가장 좋은 BC 에서 PPO (80분) → 300판 집계 (30분) → 사이렌 진단 (25분)
# 시범 운전자의 양보 기준이 바뀌어서 시범을 다시 모은다. 끊겨도 같은 명령을 다시 실행하면 끝난 단계는 건너뛴다.
export DAEHAKRO_OCCLUSION=1
TAG=track_on
cd "$(dirname "$0")" || exit 1
say() { echo; echo "===== $(date '+%m-%d %H:%M:%S') $* ====="; }

say "0. 도로·교통 파일 만들기 (택배 탑차 4%)"
python -m env.daehakro_builder > /dev/null || exit 1
grep -q car_van env/sumo/daehakro/daehakro.rou.xml || { echo "교통 파일에 탑차가 없습니다"; exit 1; }

say "1. 시범 2,000판 수집"
mkdir -p data
for s in 41 42; do
  [ -f data/${TAG}_s$s.npz ] || python collect_demo.py --episodes 1000 --workers 10 --seed $s --name ${TAG}_s$s || exit 1
done
[ -f data/$TAG.npz ] || python merge_demo.py data/$TAG.npz data/${TAG}_s41.npz data/${TAG}_s42.npz || exit 1

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

say "3. PPO 60만 스텝 (끝나면 처음·최고·마지막을 같은 100판으로 견준다)"
OUT=results/ppo_$TAG
if [ ! -f $OUT/final/summary.txt ]; then
  if [ -f $OUT/state.json ]; then R="--resume"; else R="--from-bc $BEST --demo data/$TAG.npz"; fi
  python train_bc_ppo.py --run ppo_$TAG $R --workers 8 --total 600000 || exit 1
fi
cat $OUT/final/summary.txt

say "4. 300판 집계: BC 와 PPO"
if [ ! -f $OUT/report.txt ]; then
  python occ_report.py $BEST $OUT/last.pt --episodes 300 --procs 8 2>&1 | grep --line-buffered -v Retrying | tee $OUT/report.tmp
  grep -q "^모델:" $OUT/report.tmp && mv $OUT/report.tmp $OUT/report.txt
fi

say "5. 사이렌 진단: 다 아는 운전자 / 시범 운전자 / BC / PPO (150판씩)"
[ -f $OUT/siren_diag.txt ] || { python siren_diag.py oracle expert $BEST $OUT/last.pt --episodes 150 --procs 8 2>&1 | grep --line-buffered -v Retrying; cp siren_diag.txt $OUT/siren_diag.txt; }
say "끝. 결과: $OUT/final/summary.txt, $OUT/report.txt, $OUT/siren_diag.txt"
