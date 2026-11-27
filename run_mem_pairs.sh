#!/bin/bash
# 기억 켬·끔 비교 (같은 PPO 모델, 같은 교통 상황). 300판짜리 비교를 5번 → 켬 1,500판, 끔 1,500판.
#   bash run_mem_pairs.sh test        # 16판씩 한 쌍만 (오류 확인, 3분쯤)
#   caffeinate -i bash run_mem_pairs.sh 2>&1 | tee mem_pairs.log
# 결과는 mem_pairs/ 에 쌓인다. 이미 끝난 것은 건너뛴다.
cd "$(dirname "$0")"
M=models/ppo_track.pt; EP=300; OUT=mem_pairs; SEEDS="9000 9100 9200 9300 9400"
if [ "$1" = "test" ]; then EP=16; OUT=mem_pairs_test; SEEDS="9900"; fi
mkdir -p $OUT
for s in $SEEDS; do
  for mode in on off; do
    f=$OUT/mem_${mode}_$s.txt
    if [ -f "$f" ]; then echo "건너뜀: $f"; continue; fi
    echo "=== $(date '+%m-%d %H:%M') seed $s | 기억 $mode"
    if [ $mode = on ]; then python siren_diag.py $M --episodes $EP --seed $s --out $f
    else python siren_diag.py $M --episodes $EP --seed $s --no-memory --out $f; fi
  done
done
echo "=== $(date '+%m-%d %H:%M') 모두 끝"
