#!/bin/bash
# 가림 요소별 평가 (밤새 돌리는 묶음). 결과는 occ_night/ 와 siren_diag_1500.txt 에 쌓인다.
#   bash run_occ_night.sh test     # 각 조건 8판씩만 (오류가 없는지 5분쯤 확인)
#   caffeinate -i bash run_occ_night.sh 2>&1 | tee occ_night.log
# 이미 끝난 조건(결과 .json 이 있는 것)은 건너뛴다. 중간에 끊겨도 같은 명령으로 이어서 돌린다.
cd "$(dirname "$0")"
EP=300; OUT=occ_night
if [ "$1" = "test" ]; then EP=8; OUT=occ_night_test; fi
PPO=models/ppo_track.pt
BC=models/bc_track.pt
run() {   # run <결과 이름 앞부분> <모델> <가릴 것 또는 none>
  if [ -f "$OUT/$1_$3.json" ]; then echo "건너뜀 (이미 있음): $1 $3"; return; fi
  echo "=== $(date '+%m-%d %H:%M') $2 | 가림: $3"
  if [ "$3" = "none" ]; then python occ_report.py "$2" --episodes $EP --out-dir $OUT
  else python occ_report.py "$2" --episodes $EP --hide "$3" --out-dir $OUT; fi
}
for h in none signal ped cross lane siren all; do run models_ppo_track $PPO $h; done
run expert expert none
run expert expert siren
for h in none signal ped cross lane siren all; do run models_bc_track $BC $h; done
if [ "$1" != "test" ] && [ ! -f siren_diag_1500.txt ]; then
  echo "=== $(date '+%m-%d %H:%M') 사이렌 양보 진단 1,500판"
  python siren_diag.py oracle expert $PPO --seeds 110 120 130 140 150 --episodes 300 --out siren_diag_1500.txt
fi
echo "=== $(date '+%m-%d %H:%M') 모두 끝"
