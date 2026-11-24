"""학습·평가 전에 실행한다: 팀 공통 환경이 그대로인지 확인한다.

    python check_setup.py

확인하는 것
    1. 수정 금지 파일이 배포한 그대로인가 (PROTECTED.sha256 와 비교. 줄바꿈 형식·XML 주석 차이는 무시)
    2. SUMO 순간이동이 꺼져 있는가 (daehakro.sumocfg 의 time-to-teleport = -1)
    3. SUMO 버전이 1.27.1 인가, 필요한 파이썬 패키지가 있는가

모두 OK 일 때 낸 학습·평가 결과만 팀 비교표에 넣는다.
CHANGED 가 나오면: 그 파일을 배포본으로 되돌린다 (git checkout -- <파일>, 또는 배포 ZIP 에서 다시 복사).
이 파일과 PROTECTED.sha256 도 고치지 않는다.
"""
import hashlib
import importlib
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE, "PROTECTED.sha256")
SUMO_VERSION = "1.27.1"
PACKAGES = ("numpy", "torch", "gymnasium", "matplotlib", "tensorboard")


def digest(path):
    """줄바꿈(CRLF/LF)과 XML 주석을 빼고 계산한 SHA-256.
    도로 파일은 처음 실행 때 다시 만들어지며 생성 시각·경로 주석만 바뀌므로 주석은 비교하지 않는다."""
    with open(path, "rb") as f:
        data = f.read().replace(b"\r\n", b"\n")
    if path.endswith((".xml", ".sumocfg")):
        data = re.sub(rb"<!--.*?-->", b"", data, flags=re.S)
    return hashlib.sha256(data).hexdigest()


def main():
    ok = True
    print("1) 수정 금지 파일")
    if not os.path.exists(MANIFEST):
        print("   PROTECTED.sha256 이 없습니다. 배포 ZIP 에서 다시 복사하세요.")
        return 1
    changed, missing, n = [], [], 0
    for line in open(MANIFEST, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        want, rel = line.split(None, 1)
        n += 1
        path = os.path.join(BASE, *rel.split("/"))
        if not os.path.exists(path):
            missing.append(rel)
        elif digest(path) != want:
            changed.append(rel)
    for rel in changed:
        print(f"   CHANGED  {rel}")
    for rel in missing:
        print(f"   MISSING  {rel}")
    if changed or missing:
        ok = False
    else:
        print(f"   OK ({n}개 파일 모두 배포본과 같음)")

    print("2) SUMO 순간이동")
    cfg = os.path.join(BASE, "env", "sumo", "daehakro", "daehakro.sumocfg")
    try:
        text = re.sub(r"<!--.*?-->", "", open(cfg, encoding="utf-8").read(), flags=re.S)
        m = re.search(r'<time-to-teleport\s+value="([^"]+)"', text)
        value = m.group(1) if m else "(없음 → SUMO 기본 300)"
    except OSError:
        value = "(sumocfg 없음 — 처음 실행 때 만들어진다)"
    if value == "-1":
        print("   OK (time-to-teleport = -1, 꺼짐)")
    elif value.startswith("(sumocfg 없음"):
        print("   " + value)
    else:
        print(f"   다름: time-to-teleport = {value}. 팀 공통 조건은 -1 이다.")
        ok = False

    print("3) SUMO 버전·패키지")
    home = os.environ.get("SUMO_HOME")
    if not home:
        print("   SUMO_HOME 환경변수가 없습니다.")
        ok = False
    else:
        exe = os.path.join(home, "bin", "sumo.exe" if os.name == "nt" else "sumo")
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30).stdout
            first = out.splitlines()[0] if out else "?"
            if SUMO_VERSION in first:
                print(f"   OK ({first.strip()})")
            else:
                print(f"   다름: {first.strip()} — 팀 공통 조건은 SUMO {SUMO_VERSION} 이다 (교통 흐름이 달라진다).")
                ok = False
        except (OSError, subprocess.SubprocessError) as e:
            print(f"   SUMO 를 실행하지 못했습니다: {e}")
            ok = False
    lack = []
    for name in PACKAGES:
        try:
            importlib.import_module(name)
        except Exception:
            lack.append(name)
    print("   패키지: " + ("OK" if not lack else "없음 → " + ", ".join(lack) + " (pip install 로 설치)"))
    if lack:
        ok = False

    print("\n결과: " + ("모두 OK — 학습·평가를 시작해도 된다." if ok else "문제가 있다. 위 항목을 고친 뒤 다시 실행한다."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
