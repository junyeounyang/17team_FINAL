"""53칸 시범 파일에서 환경이 계산해 주던 세 칸 [45] [46] [47] 을 잘라 50칸 시범 파일을 만든다.
    python cut_demo.py ../17team_v3occ/data/van_on.npz data/please_on.npz
이 폴더의 환경은 예전 환경에서 그 세 칸만 뺀 것이라, 잘라 낸 관측은 새로 수집한 관측과 같다 (정답 행동은 그대로).
"""
import sys
import numpy as np

CUT = (45, 46, 47)          # 앞차 정차 중, 서려면 필요한 감속, 앞차 때문에 필요한 감속
if len(sys.argv) != 3:
    sys.exit(__doc__)
src, out = sys.argv[1], sys.argv[2]
data = {}
with np.load(src, allow_pickle=False) as d:
    for k in d.files:
        a = d[k]
        if a.ndim == 2 and a.shape[1] == 53:
            a = np.delete(a, CUT, axis=1)
            print(f"  {k}: 53칸 → {a.shape[1]}칸 ({len(a):,} 스텝)")
        elif a.ndim == 2 and a.shape[1] not in (1, 2):
            sys.exit(f"{k} 의 칸 수가 {a.shape[1]} 입니다. 53칸 시범 파일이 아닙니다.")
        data[k] = a
np.savez_compressed(out, **data)
print("저장:", out)
