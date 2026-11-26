"""시범 파일 여러 개를 하나로 합친다 (에피소드 번호가 겹치지 않게 다시 매긴다).
    python merge_demo.py data/합친파일.npz data/a.npz data/b.npz ...
"""
import sys
import numpy as np

out, parts = sys.argv[1], sys.argv[2:]
if len(parts) < 1:
    sys.exit(__doc__)
merged, base = {}, 0
for path in parts:
    with np.load(path, allow_pickle=False) as d:
        ep = d["episode"].astype(np.int64)
        ep = ep - ep.min() + base
        base = int(ep.max()) + 1
        for k in d.files:
            if d[k].ndim == 0:                      # 설명용 값 (있으면 첫 파일 것을 쓴다)
                merged.setdefault(k, d[k])
                continue
            merged.setdefault(k, []).append(ep.astype(np.int32) if k == "episode" else d[k])
    print(f"  {path}: {len(ep):,} 스텝")
data = {k: (np.concatenate(v) if isinstance(v, list) else v) for k, v in merged.items()}
np.savez_compressed(out, **data)
print(f"합침: {out}  ({len(data['episode']):,} 스텝, {base} 판)")
