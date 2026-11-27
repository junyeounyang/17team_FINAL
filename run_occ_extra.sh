#!/bin/bash
# 추가 측정: 가림을 완전히 끈 도로(DAEHAKRO_OCCLUSION=0)에서 같은 300판. 결과는 occ_night_off/ 에 쌓인다.
#   caffeinate -i bash run_occ_extra.sh 2>&1 | tee occ_extra.log
# run_occ_night.sh 가 돌고 있으면 끝날 때까지 기다렸다가 시작한다.
cd "$(dirname "$0")"
while pgrep -f run_occ_night.sh >/dev/null; do sleep 60; done
OUT=occ_night_off
for m in models/ppo_track.pt expert models/bc_track.pt; do
  echo "=== $(date '+%m-%d %H:%M') $m | 가림 끔"
  DAEHAKRO_OCCLUSION=0 python occ_report.py "$m" --episodes 300 --out-dir $OUT
done
echo "=== $(date '+%m-%d %H:%M') 추가 측정 끝"
