# -*- coding: utf-8 -*-
"""
대학로 긴급차량(사이렌 켬) 보조 — TraCI 로 시뮬레이션 1스텝마다 step() 을 부른다.

  import traci
  from env.daehakro_emergency import EmergencyAssist
  traci.start([...])
  assist = EmergencyAssist()
  while ...:
      traci.simulationStep()
      assist.step()

SUMO 파일만으로(이 보조 없이도) 되는 것 — daehakro.rou.xml 의 fire_siren / ambulance_siren 차종
  - 버스전용차로 통행 (차로 허용 목록에 emergency), 제한속도 초과 (speedFactor 1.4)
  - 신호 무시 (jmDriveAfterRedTime): 적색이어도 지나가되 다가오는 교차 차량·횡단보도 보행자에는 양보,
    적색 교차로는 약 22 km/h 이하로 (jmDriveRedSpeed)
  ※ SUMO 의 bluelight 장치는 쓰지 않는다. 서브레인 모델 없이 쓰면 주변 차와 긴급차 자신의 '경로 때문에
    하는 차로변경'을 꺼 버려(구조 차로용 설정) 차가 갈 차로로 못 옮기고 차로 끝에 서서 정체·충돌이 생긴다.

이 보조가 하는 것 (TraCI)
  1) 길 비켜 주기: SUMO 기본 차로변경 모델(서브레인 모델을 안 씀)은 차가 차로 안에서 옆으로
     비킬 수 없다. → 긴급차 앞 80 m 안, 같은 차로의 차를 옆 차로로 차로변경시킨다.
     오른쪽 옆이 버스전용차로면 그 차를 잠시 '긴급 통행 허용'(vClass emergency)으로 바꿔
     버스차로에 들어가게 하고(sumo-gui 에서 연두색), 긴급차가 지나가면 일반 차로로 돌아온 뒤
     원래 종류·색으로 되돌린다. 비킬 틈이 없어 서 있는 차는 옆 차로 뒤차를 세워 틈을 만들어 주고,
     정류장에 선 버스 뒤에 긴급차가 서면 옆 차로 뒤차를 세워 긴급차가 끼어들 틈을 만든다.
     긴급차 옆 차로 앞쪽에 서 있던 차(정류장 버스 등)는 긴급차가 지나갈 때까지 출발하지 않는다.
  2) 긴급차 안전 운전 (긴급차가 사고를 내지 않게. 우선신호 없이 적색을 지나갈 때 특히 중요)
     - 보행자: 횡단보도에 사람이 있거나 막 건너려는 사람이 있으면 횡단보도 앞에 완전히 선다 (사람 사이를
       서행으로 지나가지 않음). 보행 신호가 켜져 있는 횡단보도는 사람이 안 보여도 지나가지 않는다.
       신호 시간표를 보고, 횡단보도를 다 빠져나가기 전에 보행 신호가 켜질 것 같으면 교차로 정지선 앞에서
       미리 선다 (교차로 안에서 달리는 중에 보행 신호가 켜져 사람이 건너기 시작하는 일을 막음).
     - 교차로 진입: 초록불이 아닌데 들어가는 곳에서는 정지선 앞에서 먼저 확인하고, 안 되면 거기서 기다린다.
       · 적색·황색 신호: 내 길을 가로지르는 교차로 안 차로가 비어 있고, 그쪽에서 들어올 차(SUMO 가 '곧 들어올
         차'로 잡은 차, 내가 다 지나가기 전에 초록불을 받을 차)가 없고, 나갈 차로에 자리가 있을 때만 들어간다.
       · 신호 없는 진출로(소방서)·양보 진입: 다가오는 차에 대한 양보는 SUMO 기본 판단대로 하되, 가로지르는
         차로에 서행·정지 차가 걸쳐 있거나 나갈 자리가 없으면 들어가지 않는다 (SUMO 는 교차로 안에서 서행하는
         차의 꽁무니를 놓쳐 부딪치는 일이 있었다).
  3) 긴급차량 우선신호(선택, 기본 끔): 실제 인천·경기 등 여러 도시에서 쓰는 방식처럼 긴급차가
     다가오는 신호등을 미리 긴급차 방향 초록불로 바꾼다 (황색 3초 + 전적색 2초를 거쳐 안전하게).
     소방서에서 나올 때는 O 교차로 본선을 빨간불로 세운다 (소방서 앞 출동 신호, 옆길 O 신호 단계).
     앞에 신호 대기 줄이 있으면 SUMO 차는 옆으로 비킬 공간이 없어 긴급차가 줄 뒤에 갇히는데,
     우선신호로 줄이 먼저 빠져나가게 한다. 긴급차가 지나가면 원래 신호 시간표의 같은
     시각 위치로 되돌려 연동(녹색 물결)이 깨지지 않게 한다.
  5) 버스 끼워 주기 (긴급차와 상관없이 늘): 경로대로 가려면 옆 차로로 옮겨야 하는 버스가 차로 끝에 서서
     기다리고 있으면, 옆 차로에서 뒤따라오던 차가 잠깐 서서 버스를 들여보낸다 (실제 도로에서 버스에 양보하듯).
     SUMO 운전자는 서서 양보하지 않아, 혜화동로터리 서쪽 우회전 갈림 앞에서 버스가 5분씩 갇혀 로터리가
     통째로 막히는 일이 있었다. AV 와 긴급차는 세우지 않는다.
  4) 꼬리물기 방지 (긴급차와 상관없이 늘): 한 차로가 직진·우회전처럼 갈라지는 신호 교차로에서, 옆 갈래로
     들어가 교차로 안에 멈춘 차(횡단보도 보행자를 기다리는 우회전 차 등)가 두 길이 갈라지기 전 구간을
     막고 있으면, 뒤차는 정지선을 넘지 않고 기다린다. SUMO 는 같은 갈래의 앞차만 보고 진입을 막으므로
     (keepClear), 뒤차가 정지선을 1 m 쯤 넘어 섰다가 신호가 바뀐 뒤 늦게 교차로를 빠져나가며
     다음 신호에 막 건너기 시작한 보행자와 부딪치는 일이 있었다 (이화사거리 남쪽 버스차로).
"""
import math
import zlib
import os
import xml.etree.ElementTree as ET

import traci

from env import daehakro_config as cfg

YIELD_COLOR = (170, 255, 0, 255)   # 비켜 주느라 버스전용차로에 들어간 차 (sumo-gui 에서 연두색으로 보임)
LC_MODE_DEFAULT = 1621      # SUMO 기본 차로변경 방식
LC_MODE_BUSY = 1617         # 기본에서 '협력 차로변경'만 끔: 자기 경로 때문에 비킬 수 없는 차가 긴급차 앞에 있는 동안
LC_MODE_YIELD = 1873        # 기본 + 'TraCI 차로변경 요청은 안전할 때만, 틈을 만들려고 속도를 줄이지는 않음'
#   + '협력 차로변경 끔' (옆 차로 차를 먼저 보내려고 서 버리는 SUMO 의 협력 감속 때문에, 비키던 차가
#   교차로 출구·횡단보도 위에 선 채 옆 차와 서로 기다리는 일이 있었음)
#   (기본 1621 은 요청받은 차로변경을 하려고 그 자리에 서서 틈을 기다려 오히려 긴급차를 막음)
INF = float("inf")


def _default_net():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "sumo", "daehakro", "daehakro.net.xml")


def _seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    qx, qy = ax + u * dx, ay + u * dy
    return math.hypot(p[0] - qx, p[1] - qy), (qx, qy)


class EmergencyAssist:
    def __init__(self, net_file=None, siren_types=None, priority_signal=None, skip=(), box_guard=None):
        """skip: 보조가 건드리지 않을 차 id 앞부분들 (예: ("ego",) → 학습하는 자율주행차는 스스로 판단).
        box_guard: 꼬리물기 방지 (None 이면 설정값, 기본 켬)."""
        a = cfg.EMERGENCY_ASSIST
        self.skip = tuple(skip)
        self.box_guard = a.get("box_guard", True) if box_guard is None else box_guard
        self.box = None           # 갈라지는 차로 → 갈래별 '옆 갈래 차가 막는 구간' (처음 step 때 만듦)
        self.box_held = set()     # 꼬리물기 방지로 정지선 앞에 세운 차
        self.bus_wait = a.get("bus_merge_wait", 5.0)   # 차로 끝에 선 버스를 이만큼(초) 기다린 뒤 끼워 줌. 0 이하면 끔
        self.buses = set()        # 지금 달리는 버스
        self.bus_asked = {}       # 버스 → 마지막으로 끼워 달라고 한 시각
        self.bus_since = {}       # 버스 → 끼워 달라고 하기 시작한 시각 (40초 넘으면 20초 쉼)
        self.bus_hold = {}        # 버스를 들여보내려고 정지선에 선 차 → (차로, 풀어 줄 시각)
        self.bus_slowed = set()   # 기록용 : 이번 스텝에 버스 끼워 주기로 세운 옆 차로 뒤차. 보조 동작에는 쓰지 않는다
        self.siren_types = set(siren_types or [f"{k}_siren" for k in cfg.EMERGENCY_TYPES])
        self.make_way_dist = a["make_way_dist"]
        self.return_after = a["return_after"]
        self.priority = a["priority_signal"] if priority_signal is None else priority_signal
        self.pre_dist = a["priority_dist"]
        self.max_hold = a["priority_max_hold"]
        self.ped_brake = a["ped_brake"]
        self.ped_margin = a.get("ped_green_margin", 3.0)
        self.native_foes = hasattr(traci.vehicle, "getJunctionFoes")   # SUMO 1.17 이상 (없으면 정지선 맨 앞 차만 봄)
        self.exit_signal = {"FS_in": cfg.FIRE_STATION.get("exit_signal")}   # 소방서 진출로 → 출동 신호등
        self.exiting = set()      # 소방서에서 막 나오는 긴급차
        self.helped = {}          # 정차 차량 뒤에 갇힌 긴급차 → 마지막으로 옆 차로를 비워 달라고 한 시각
        self.held = {}            # 긴급차가 지나갈 때까지 출발하지 않게 붙잡아 둔 차 → 마지막 확인 시각
        self.held_since = {}      # 붙잡기 시작한 시각 (한 번에 최대 hold_max 초, 1분에 한 번)
        self.held_lane = {}       # 붙잡은 버스 → (붙잡을 때 차로, 원래 차로변경 방식). 붙잡는 동안 차로변경 금지
        self.hold_max = 20.0
        self.evs = set()          # 지금 달리는 사이렌 차
        self.yielding = {}        # 비켜 준 차 → 상태
        self.kind_share = float(a.get("kind_share", 0.5))   # 자기 길이 꼬여도 비켜 주는 운전자 비율
        self.busy = {}            # 자기 경로 때문에 비킬 수 없는 차 (곧 좌회전·유턴, 곧 차로를 옮겨야 함) → 상태
        self.after_yield = {}     # 비키기를 마친 차 → 마친 시각 (120 초 동안 '길 잃음'을 살핌)
        self.strand = {}          # 경로대로 못 가는 차로 끝에 선 차 → 처음 선 시각
        self.trap = {}            # 버스차로(점선) 끝에 갇힌 차 → 처음 선 시각 (비킨 적 없는 차 포함)
        self.trap_scan = 0.0      # 다음에 버스차로 끝을 살필 시각 (5초마다)
        self.rescue_try = {}      # 차 → 마지막으로 버스차로 통행 허용을 살핀 시각
        self.capped = set()       # 횡단보도·교차로 앞에서 속도를 줄이거나 세운 긴급차
        self.hold = {}            # 정지선 앞에 세운 긴급차 → 그 교차로 (조건이 풀릴 때까지 계속 세움)
        self.why = {}             # 긴급차 → 지금 세운 이유 (확인용)
        self.junc = {}            # 교차로 안 차로 → 그 길을 가로지르는 차로들 (처음 쓸 때 만듦)
        self.lane_len = {}        # 차로 길이 (처음 쓸 때 읽음)
        self.bus_lane_entries = set()
        self.pre = {}             # 우선신호 중인 신호등 → 상태
        self.cool = {}            # 오래 붙잡았던 신호등 → 다시 우선신호를 줄 수 있는 시각 (교차 방향도 한 번은 초록)
        self.tl = None            # 신호등 시간표 (처음 step 때 읽음)
        self.stats = {"make_way": 0, "into_bus_lane": 0, "priority_signal": 0, "ped_stop": 0, "entry_hold": 0,
                      "box_hold": 0, "bus_merge": 0}
        self._load_crossings(net_file or _default_net())

    # ── 네트워크에서 횡단보도 읽기 ──
    def _load_crossings(self, net_file):
        root = ET.parse(net_file).getroot()
        self.turn_dir = {}                    # (도로, 다음 도로) → 회전 방향들 (s 직진, r 우회전, l 좌회전, t 유턴 …)
        self.dash_bus = []                    # 일반 차도 들어갈 수 있는 버스차로 구간 (교차로 앞 점선 구간)
        self.edge_len = {}                    # 도로 → 길이
        for c in root.iter("connection"):
            f, to = c.get("from"), c.get("to")
            if f and to and not f.startswith(":") and not to.startswith(":"):
                self.turn_dir.setdefault((f, to), set()).add(c.get("dir"))
        for e in root.iter("edge"):
            if e.get("function") is None:
                ln = e.find("lane")
                if ln is not None:
                    self.edge_len[e.get("id")] = float(ln.get("length"))
                for l in e.iter("lane"):
                    al = (l.get("allow") or "").split()
                    if "bus" in al and "passenger" in al:
                        self.dash_bus.append(l.get("id"))
        self.cross = {}                       # 횡단보도 → 정보
        self.cross_at = {}                    # 노드 → [횡단보도]
        self.feeds = {}                       # 차로 → 교차로를 지나 그 차로로 들어오는 앞 도로의 차로들
        self.via_src = {}                     # 교차로 안 차로 → (들어오는 차로, 신호등, 신호 번호)
        to_node = {}
        for e in root.iter("edge"):
            if e.get("function") == "crossing":
                ln = e.find("lane")
                pts = [tuple(map(float, p.split(","))) for p in ln.get("shape").split()]
                cid = e.get("id")
                node = cid[1:cid.rindex("_c")]
                self.cross[cid] = {"node": node, "edges": set(e.get("crossingEdges", "").split()),
                                   "shape": pts, "half": float(ln.get("width", "4.0")) / 2,
                                   "tl": None, "idx": None, "wa": set()}
                self.cross_at.setdefault(node, []).append(cid)
            elif not e.get("function"):
                to_node[e.get("id")] = e.get("to")
        for c in root.iter("connection"):
            f, t = c.get("from", ""), c.get("to", "")
            if f and t and not f.startswith(":") and not t.startswith(":"):
                self.feeds.setdefault(f"{t}_{c.get('toLane')}", set()).add(f"{f}_{c.get('fromLane')}")
            if c.get("via"):
                tl = c.get("tl")
                self.via_src[c.get("via")] = (f"{f}_{c.get('fromLane')}", tl, int(c.get("linkIndex")) if tl is not None else None)
            if t in self.cross:
                self.cross[t]["wa"].add(f)
                if c.get("tl") is not None:
                    self.cross[t]["tl"], self.cross[t]["idx"] = c.get("tl"), int(c.get("linkIndex"))
            elif f in self.cross:
                self.cross[f]["wa"].add(t)
        self.to_node = to_node

    # ── 한 스텝 ──
    def step(self):
        t = traci.simulation.getTime()
        self.bus_slowed.clear()                        # 기록용 (이번 스텝에 세운 차만 담는다)
        if self.tl is None:
            self._snapshot_signals(t)
        if self.box is None:
            self._build_box()
        if self.box_guard:
            self._box_guard()
        for v in traci.simulation.getDepartedIDList():
            kind = traci.vehicle.getTypeID(v)
            if kind in self.siren_types:
                self.evs.add(v)
            elif kind == "bus":
                self.buses.add(v)
        for v in traci.simulation.getEndingTeleportIDList():
            # SUMO 가 오래 서 있던 차를 앞으로 옮긴 경우(순간이동): 옮기는 동안 목록에서 빠졌던 긴급차를 다시 넣는다
            try:
                if v not in self.evs and traci.vehicle.getTypeID(v) in self.siren_types:
                    self.evs.add(v)
            except traci.TraCIException:
                pass
        for v in traci.simulation.getArrivedIDList():
            self.buses.discard(v)
            self.held_since.pop(v, None)
            self.bus_asked.pop(v, None)
            self.bus_since.pop(v, None)
            self.evs.discard(v)
            self.capped.discard(v)
            self.hold.pop(v, None)
            self.why.pop(v, None)
            self.yielding.pop(v, None)
        if self.bus_wait > 0:
            self._bus_merge(t)
        if (not self.evs and not self.yielding and not self.pre and not self.held and not self.after_yield
                and not self.busy and t < self.trap_scan):
            return
        live = set(traci.vehicle.getIDList())
        self.evs &= live
        for ev in sorted(self.evs):                    # 정렬: 실행할 때마다 같은 순서 (같은 시드 → 같은 결과)
            chain = self._make_way(ev, t)
            self._help_change(ev, t)
            self._hold_stoppers(ev, t, chain)
            self._guard(ev, t)
        if self.priority:
            self._signals(t)
        self._restore(t, live)
        self._reroute_stranded(t, live)
        if t >= self.trap_scan:
            self.trap_scan = t + 5.0
            self._scan_traps(t, live)
        self._release_busy(t, live)
        self._release_held(t, live)

    # ── 1) 길 비켜 주기 ──
    def _leaders(self, ev):
        """긴급차가 갈 차로(경로 따라)에서 앞에 있는 차들 (가까운 순)."""
        out, cur, dist = [], ev, 0.0
        while dist < self.make_way_dist and len(out) < 8:
            lead = traci.vehicle.getLeader(cur, self.make_way_dist - dist)
            if not lead or not lead[0]:
                break
            lid, gap = lead
            if gap > self.make_way_dist - dist:              # getLeader 는 더 멀리 있는 차도 돌려줌
                break
            dist += max(0.0, gap) + (traci.vehicle.getLength(lid) if cur != ev else 0.0)
            out.append(lid)
            cur = lid
        return out

    def _make_way(self, ev, t):
        chain = self._leaders(ev)
        for vid in chain:
            if vid in self.evs or vid.startswith(self.skip) or traci.vehicle.getVehicleClass(vid) == "bus":
                continue                                  # 버스는 정류장 때문에 그대로 (긴급차가 비켜 감)
            if traci.vehicle.isStopped(vid):
                continue
            if not self._kind(vid) and self._busy(vid):
                # 곧 좌회전·유턴하거나 경로 때문에 곧 차로를 옮겨야 하는 차: 자기 길을 지키는 운전자는 비키지 않는다
                # (차로변경 요청 없음, SUMO 의 '뒤차 먼저 보내기' 협력 차로변경도 긴급차가 뒤에 있는 동안 끔)
                if vid in self.yielding:
                    self.yielding[vid]["seen"] = t        # 이미 비키던 차: 새 요청만 하지 않음
                else:
                    b = self.busy.get(vid)
                    if b is None:
                        self.busy[vid] = {"seen": t, "lcm": traci.vehicle.getLaneChangeMode(vid)}
                        traci.vehicle.setLaneChangeMode(vid, LC_MODE_BUSY)
                        self.stats["busy_no_yield"] = self.stats.get("busy_no_yield", 0) + 1
                    else:
                        b["seen"] = t
                continue
            if vid in self.busy:                          # 더는 바쁘지 않음 → 원래 차로변경 방식으로 돌리고 보통처럼 비킴
                traci.vehicle.setLaneChangeMode(vid, self.busy.pop(vid)["lcm"])
            st = self.yielding.get(vid)
            if st is None:
                st = {"cls": traci.vehicle.getVehicleClass(vid), "seen": t, "asked": -1e9}
                self.yielding[vid] = st
                self.stats["make_way"] += 1
                # 비키는 방향은 이 보조가 경로를 보고 정한다: SUMO 의 '뒤차 먼저 보내기' 협력 차로변경은 경로를 보지 않고
                # 옆 차로로 보내 (교차로 직전 13 m 구간 등) 다시 못 돌아오게 만들 수 있어 바로 끈다
                traci.vehicle.setLaneChangeMode(vid, LC_MODE_YIELD)
                st["lcm"] = True
            st["seen"] = t
            ln = traci.vehicle.getLaneID(vid)
            if not ln or ln.startswith(":") or t - st["asked"] < 1.0:
                continue                                  # 교차로 안에서는 차로변경 불가
            if traci.vehicle.getLanePosition(vid) < traci.vehicle.getLength(vid) + 1.0:
                continue                                  # 차 뒤끝이 아직 교차로·횡단보도 위 → 먼저 빠져나가게
            if traci.vehicle.getSpeed(vid) < 0.1:
                lead = traci.vehicle.getLeader(vid, 10.0)
                if not lead or not lead[0] or lead[1] > 5.0:
                    continue                                  # 앞이 비었는데 서 있음 → 다시 재촉하지 않음
            edge, idx = traci.vehicle.getRoadID(vid), traci.vehicle.getLaneIndex(vid)
            nl = traci.edge.getLaneNumber(edge)
            cand = []                                     # (방향, 목표 차로, 버스차로인지)
            for d in (-1, 1):                             # 오른쪽(버스차로·가장자리 쪽) 먼저
                j = idx + d
                if j < 0 or j >= nl:
                    continue
                allowed = traci.lane.getAllowed(f"{edge}_{j}")
                if allowed and "emergency" not in allowed:
                    continue                              # 보도 등
                into_bus = bool(allowed) and st["cls"] not in allowed
                if into_bus:
                    if not self._continues(vid, f"{edge}_{j}"):
                        continue                          # 버스차로가 그 차 다음 도로로 안 이어짐 (로터리 정류장 칸 등)
                elif not self._on_route(vid, f"{edge}_{j}"):
                    continue                              # 그 차 경로로 못 이어지는 차로(유턴 베이·회전 전용 등)
                cand.append((d, j, into_bus))
            pick = next((c for c in cand if self._room(vid, left=(c[0] > 0))), None)
            if pick is None and cand and traci.vehicle.getSpeed(vid) < 1.0:
                # 서 있는 차(갈 차로로 못 옮겨 서 있는 차 포함): 옆 차로 뒤차를 세워 틈을 만들어 비키게 함
                want = self._wanted_dir(vid, f"{edge}_{idx}")
                cand.sort(key=lambda c: c[0] != want)
                for c in cand:
                    if self._room_ahead(vid, left=(c[0] > 0)):
                        self._open_gap(vid, left=(c[0] > 0))
                        pick = c
                        break
            if pick is None:
                continue
            d, j, into_bus = pick
            if into_bus:                                  # 버스전용차로 → 잠시 진입 허용
                # 지금 차로에서는 차종을 다시 확인하지 않는다 (같은 스텝의 _restore 가 버스차로로 옮기기도 전에
                # 원래 차종을 돌려줘 버스전용차로에 못 들어가던 문제). 다음 차로(버스차로·다음 도로)에서 확인한다
                st["chk"] = ln
                if traci.vehicle.getVehicleClass(vid) != "emergency":
                    if "color" not in st:
                        st["color"] = traci.vehicletype.getColor(traci.vehicle.getTypeID(vid))
                        traci.vehicle.setColor(vid, YIELD_COLOR)
                    traci.vehicle.setVehicleClass(vid, "emergency")
                    traci.vehicle.updateBestLanes(vid)   # 차종이 바뀌면 갈 수 있는 차로 다시 계산
                if vid not in self.bus_lane_entries:
                    self.bus_lane_entries.add(vid)
                    self.stats["into_bus_lane"] += 1
            if not st.get("lcm"):
                traci.vehicle.setLaneChangeMode(vid, LC_MODE_YIELD)
                st["lcm"] = True
            # 1초짜리 요청 (긴급차가 뒤에 있는 동안 1초마다 다시 함): 길게 걸어 두면 다음 도로에서도 같은 번호 차로로
            # 옮겨져, 그 번호가 교차로 앞 짧은 점선 버스차로(차는 우회전만)인 곳에서 차가 급정거했다
            traci.vehicle.changeLane(vid, j, 1.0)
            st["asked"] = t
        return set(chain)

    @staticmethod
    def _continues(vid, lane_id):
        """그 차로에서 그 차의 다음 경로 도로로 바로 이어지는 연결이 있는지 (버스차로용: 긴급 통행 허용 기준)."""
        route, ri = traci.vehicle.getRoute(vid), traci.vehicle.getRouteIndex(vid)
        if ri + 1 >= len(route):
            return True
        nxt = route[ri + 1]
        return any(lk[0].rsplit("_", 1)[0] == nxt for lk in traci.lane.getLinks(lane_id))

    @staticmethod
    def _wanted_dir(vid, lane_id):
        """그 차가 경로 때문에 옮겨 가야 하는 방향 (+1 왼쪽, -1 오른쪽, 0 없음)."""
        for b in traci.vehicle.getBestLanes(vid):
            if b[0] == lane_id:
                return (b[3] > 0) - (b[3] < 0)
        return 0

    @staticmethod
    def _room_ahead(vid, left):
        side = 0 if left else 1      # getNeighbors: 0 = 왼쪽, 1 = 오른쪽
        return min((g for _, g in traci.vehicle.getNeighbors(vid, side | 2)), default=1e9) > 1.0

    def _open_gap(self, vid, left):
        """옆 차로에서 vid 바로 뒤(25 m 안)에 오는 차들을 세워 vid 가 들어갈 틈을 만든다."""
        side = 0 if left else 1      # getNeighbors: 0 = 왼쪽, 1 = 오른쪽
        for f, g in traci.vehicle.getNeighbors(vid, side):
            # 뒤끝보다 뒤에 있는 차만 (옆에 나란히 있는 차를 세우면 틈이 생기지 않고 서로 기다리게 됨)
            if 0.5 <= g < 25.0 and f not in self.evs and not f.startswith(self.skip):
                traci.vehicle.slowDown(f, 0.0, 2.0)

    def _bus_merge(self, t):
        """버스 끼워 주기: 차로가 20 m 안에서 끝나는데 옆 차로로 못 옮기고 bus_wait 초 넘게 서 있는 버스가 있으면,
        옮겨 갈 차로에서 버스 뒤로 따라오는 차(25 m 안)와, 앞 교차로를 지나 그 차로로 들어올 맨 앞 차를 세우고
        버스에 차로변경을 시킨다 (버스 옆에 이미 와 있는 차는 지나가게 둔다). 차로변경 자체는 SUMO 가 안전할 때만
        실행한다. 한 버스에 40초 넘게 해 줬으면 20초 쉰다. 정류장에 선 버스, 교차로 안의 버스는 해당 없음."""
        if int(t) % 10 == 0 and t == int(t):
            self.buses &= set(traci.vehicle.getIDList())
        for b in sorted(self.buses):
            if t - self.bus_asked.get(b, -1e9) < 1.0 or b in self.held:
                continue
            try:
                if (traci.vehicle.getSpeed(b) > 0.1 or traci.vehicle.getWaitingTime(b) < self.bus_wait
                        or traci.vehicle.isStopped(b)):
                    self.bus_since.pop(b, None)
                    continue
                ln = traci.vehicle.getLaneID(b)
                if not ln or ln.startswith(":"):
                    continue
                want, reach = 0, INF
                for bl in traci.vehicle.getBestLanes(b):
                    if bl[0] == ln:
                        want, reach = (bl[3] > 0) - (bl[3] < 0), bl[1]
                if not want or reach - traci.vehicle.getLanePosition(b) > 20.0:
                    continue                              # 옮길 필요가 없거나 아직 차로가 한참 남음
                edge, idx = traci.vehicle.getRoadID(b), traci.vehicle.getLaneIndex(b)
                if not 0 <= idx + want < traci.edge.getLaneNumber(edge):
                    continue
                since = self.bus_since.setdefault(b, t)
                if t - since > 40.0:
                    if t - since > 60.0:
                        self.bus_since[b] = t
                    continue                              # 너무 오래 세워 둠 → 잠시 쉼
                for f, g in traci.vehicle.getNeighbors(b, 0 if want > 0 else 1):
                    # 버스 꽁무니보다 뒤에 있는 차만 세운다 (옆에 나란히 있는 차는 먼저 지나가야 틈이 생김)
                    if 0.5 <= g < 25.0 and f not in self.evs and not f.startswith(self.skip):
                        traci.vehicle.slowDown(f, 0.0, 2.0)
                        self.bus_slowed.add(f)            # 기록용
                for src in self.feeds.get(f"{edge}_{idx + want}", ()):
                    ids = traci.lane.getLastStepVehicleIDs(src)
                    if not ids:
                        continue
                    f = ids[-1]                           # 앞 도로에서 그 차로로 들어올 맨 앞 차
                    if f == b or f in self.evs or f in self.buses or f.startswith(self.skip):
                        continue
                    vf = traci.vehicle.getSpeed(f)
                    room = self._length(src) - traci.vehicle.getLanePosition(f) - 1.0
                    if f in self.bus_hold or room >= vf * self.dt + vf * vf / (2 * 3.0):
                        self.bus_hold[f] = (src, t + 1.6)  # 정지선 앞에 편하게 설 수 있는 차만
                traci.vehicle.changeLane(b, idx + want, 3.0)
            except traci.TraCIException:
                self.buses.discard(b)
                continue
            if b not in self.bus_asked:
                self.stats["bus_merge"] += 1
            self.bus_asked[b] = t
        for f in list(self.bus_hold):                     # 세운 차: 정지선 1 m 앞에 서 있게 하고, 요청이 끊기면 풀어 준다
            src, until = self.bus_hold[f]
            try:
                if t > until or traci.vehicle.getLaneID(f) != src:
                    traci.vehicle.setSpeed(f, -1)
                    del self.bus_hold[f]
                else:
                    traci.vehicle.setSpeed(f, self._stop_speed(self._length(src) - traci.vehicle.getLanePosition(f) - 1.0))
            except traci.TraCIException:
                del self.bus_hold[f]

    def _hold_stoppers(self, ev, t, chain):
        """긴급차 경로 앞 60 m 안, 옆 차로 정류장에 서 있는 버스(등)는 긴급차가 지나갈 때까지 출발하지 않음
        (막 출발한 버스가 긴급차와 같은 차로로 합류하다 부딪치는 것 방지). 긴급차 바로 앞 차는 붙잡지 않음.
        긴급차가 실제로 달려오고 있을 때만(2 m/s 이상, 10초 안에 도착) 붙잡고, 한 번에 최대 hold_max 초,
        같은 버스는 1분에 한 번만. 긴급차가 서 버리면 붙잡지 않는다 (그 긴급차가 그 버스가 비켜야 풀리는
        줄 속에 서 있으면 서로 기다리게 됨)."""
        ev_v = traci.vehicle.getSpeed(ev)
        ex, ey = traci.vehicle.getPosition(ev)
        a = math.radians(traci.vehicle.getAngle(ev))
        hx, hy = math.sin(a), math.cos(a)
        route, ri = traci.vehicle.getRoute(ev), traci.vehicle.getRouteIndex(ev)
        own = traci.vehicle.getLaneID(ev)
        for e in route[max(0, ri):ri + 3]:
            for v in traci.edge.getLastStepVehicleIDs(e):
                if v in self.evs or v in chain or v.startswith(self.skip):
                    continue
                x, y = traci.vehicle.getPosition(v)
                ahead = (x - ex) * hx + (y - ey) * hy
                if ahead < -3.0 or math.hypot(x - ex, y - ey) > 60.0:
                    continue                                # 이미 지나갔거나 멂
                coming = ev_v >= 2.0 and math.hypot(x - ex, y - ey) / ev_v <= 10.0
                if v in self.held:
                    if coming and t - self.held_since.get(v, t) < self.hold_max:
                        self.held[v] = t                      # 계속 붙잡음 (안 갱신하면 1.5초 뒤 풀림)
                elif (coming and traci.vehicle.isStopped(v) and traci.vehicle.getLaneID(v) != own
                        and t - self.held_since.get(v, -1e9) > 60.0):
                    traci.vehicle.setSpeed(v, 0.0)
                    # 정류장 차로에 그대로 둔다: 붙잡는 동안 차로변경 금지 (정차가 끝나는 순간 옆 차로로 반쯤
                    # 나간 채 서 있으면 뒤차가 교차로 안에서 부딪힘)
                    self.held_lane[v] = (traci.vehicle.getLaneID(v), traci.vehicle.getLaneChangeMode(v))
                    traci.vehicle.setLaneChangeMode(v, 0)
                    self.held[v] = t
                    self.held_since[v] = t

    def _release_busy(self, t, live):
        """긴급차가 지나간 뒤(return_after 초) 비킬 수 없던 차의 차로변경 방식을 원래대로."""
        for v in list(self.busy):
            if v not in live:
                del self.busy[v]
            elif t - self.busy[v]["seen"] > self.return_after:
                traci.vehicle.setLaneChangeMode(v, self.busy[v]["lcm"])
                del self.busy[v]

    def _release_held(self, t, live):
        for v in list(self.held):
            if v not in live:
                del self.held[v]
                self.held_lane.pop(v, None)
                continue
            lane0, lcm = self.held_lane.get(v, (None, None))
            moved = lane0 is not None and traci.vehicle.getLaneID(v) != lane0
            if t - self.held[v] > 1.5 or moved:          # 긴급차가 옆을 지나감 / 이미 정류장 차로를 벗어남
                traci.vehicle.setSpeed(v, -1)
                if lcm is not None:
                    traci.vehicle.setLaneChangeMode(v, lcm)
                del self.held[v]
                self.held_lane.pop(v, None)

    def _help_change(self, ev, t):
        """정류장에 선 버스 등 움직이지 않는 차 뒤에 긴급차가 서 버렸으면, 옆 차로 뒤쪽 차를 세워
        끼어들 틈을 만들어 준다 (옆 차로 차들도 긴급차에 양보). 끼어드는 것은 뒤차가 설 수 있게 된 다음에:
        빠르게 오는 차 바로 앞으로 끼어들면 그 차가 급제동해도 긴급차를 들이받는다."""
        if traci.vehicle.getSpeed(ev) > 2.0 or t - self.helped.get(ev, -1e9) < 3.0:
            return
        ln = traci.vehicle.getLaneID(ev)
        if not ln or ln.startswith(":"):
            return
        lead = traci.vehicle.getLeader(ev, 25.0)
        if not lead or not lead[0] or traci.vehicle.getSpeed(lead[0]) > 0.5:
            return
        edge, idx = traci.vehicle.getRoadID(ev), traci.vehicle.getLaneIndex(ev)
        nl = traci.edge.getLaneNumber(edge)
        for d in (1, -1):                                   # 왼쪽(추월 방향) 먼저
            j = idx + d
            if j < 0 or j >= nl:
                continue
            allowed = traci.lane.getAllowed(f"{edge}_{j}")
            if allowed and "emergency" not in allowed:
                continue
            if not self._on_route(ev, f"{edge}_{j}"):
                continue                                    # 유턴 베이처럼 경로로 못 이어지는 차로에는 안 들어감
            side = 0 if d > 0 else 1      # getNeighbors: 0 = 왼쪽, 1 = 오른쪽
            ahead = traci.vehicle.getNeighbors(ev, side | 2)
            if min((g for _, g in ahead), default=1e9) < 1.0:
                continue                                    # 옆 차로 바로 앞도 막힘
            ready = True                                    # 옆 차로 뒤차가 모두 편하게 설 수 있을 때만 끼어든다
            for f, g in traci.vehicle.getNeighbors(ev, side):
                vf = traci.vehicle.getSpeed(f)
                if g < vf * vf / (2 * 3.0) + 2.0:
                    ready = False                           # 그 차가 설 거리가 모자람 → 이번에는 끼어들지 않는다
                if 0.5 <= g < 25.0 and f not in self.evs and not f.startswith(self.skip):
                    traci.vehicle.slowDown(f, 0.0, 2.0)
            if ready:
                traci.vehicle.changeLane(ev, j, 4.0)
            self.helped[ev] = t if ready else t - 2.0       # 못 끼어들었으면 1초 뒤 다시 확인
            return

    @staticmethod
    def _can_return(vid, lane_id):
        """원래 차종으로 돌려준 상태에서, 지금 차로에 그대로 있어도 되거나(옮길 필요 없음) 옮겨 갈 거리가 충분한지
        (남은 거리 50 m + 옮길 차로 하나당 40 m)."""
        for b in traci.vehicle.getBestLanes(vid):
            if b[0] == lane_id:
                return b[3] == 0 or b[1] - traci.vehicle.getLanePosition(vid) >= 50.0 + 40.0 * abs(b[3])
        return False

    def _kind(self, vid):
        """운전자 성향 (차 id 로 고정): kind_share 만큼은 자기 길이 꼬여도 비켜 주고 나중에 길을 다시 찾는다."""
        return zlib.crc32(vid.encode("utf-8")) % 1000 < self.kind_share * 1000

    def _busy(self, vid):
        """자기 경로 때문에 비킬 수 없는 차인지: ahead 300 m 안에 좌회전·유턴이 있거나, 지금 차로가 그 차 경로로는
        곧 끝나 차로를 옮겨야 함 (남은 거리 < 50 m + 옮길 차로 하나당 40 m)."""
        ln = traci.vehicle.getLaneID(vid)
        if not ln or ln.startswith(":"):
            return False
        if self._turns_left_soon(vid):
            return True
        for b in traci.vehicle.getBestLanes(vid):
            if b[0] == ln:
                return b[3] != 0 and b[1] - traci.vehicle.getLanePosition(vid) < 50.0 + 40.0 * abs(b[3])
        return False

    def _turns_left_soon(self, vid, ahead=300.0):
        """경로를 따라 ahead m 안에 좌회전·유턴이 있는지 (그런 차는 오른쪽 버스차로로 비키지 않음)."""
        route, i = traci.vehicle.getRoute(vid), traci.vehicle.getRouteIndex(vid)
        if i < 0:
            return False
        dist = self.edge_len.get(route[i], 0.0) - traci.vehicle.getLanePosition(vid)
        for k in range(i, len(route) - 1):
            if self.turn_dir.get((route[k], route[k + 1]), set()) & {"l", "L", "t"}:
                return True
            dist += self.edge_len.get(route[k + 1], 0.0)
            if dist > ahead:
                break
        return False

    @staticmethod
    def _on_route(vid, lane_id):
        """그 차로에서 차로를 더 바꾸지 않고 경로대로 계속 갈 수 있는지 (SUMO best lanes)."""
        for b in traci.vehicle.getBestLanes(vid):
            if b[0] == lane_id:
                return bool(b[4]) and b[3] == 0
        return False

    @staticmethod
    def _room(vid, left):
        """옆 차로에 들어갈 빈틈이 있는지: 앞차와 겹치지 않고, 뒤차가 편하게 설 수 있는 거리."""
        side = 0 if left else 1      # getNeighbors: 0 = 왼쪽, 1 = 오른쪽
        if min((d for _, d in traci.vehicle.getNeighbors(vid, side | 2)), default=1e9) <= 0.5:
            return False
        for f, d in traci.vehicle.getNeighbors(vid, side):
            vf = traci.vehicle.getSpeed(f)
            if d <= max(0.5, vf * vf / (2 * 3.0) + 1.0):
                return False
        return True

    # ── 2) 긴급차 안전 운전: 보행자 보호 · 교차로 진입 ──
    def _green_in(self, tls, idx, t):
        """신호등 tls 의 idx 번 신호가 초록이 될 때까지 남은 시간(초). 지금 초록이거나 시간표를 모르면 0."""
        st = traci.trafficlight.getRedYellowGreenState(tls)
        if idx >= len(st) or st[idx] in "Gg":
            return 0.0
        P = self.pre.get(tls)
        if P is not None:                                 # 우선신호 중: 예정된 신호 순서에서 찾는다
            start = t
            for state, until in P["plan"]:
                if state[idx] in "Gg":
                    return max(0.0, start - t)
                start = until
            if P["mode"] != "out":
                return INF                                # 긴급차가 지나갈 때까지 지금 신호 그대로
        T = self.tl.get(tls)
        if T is None:
            return 0.0
        n = len(T["phases"])
        e = (t - T["anchor"]) % T["C"]
        k = next((i for i in range(n) if e < T["cum"][i + 1]), n - 1)
        wait = T["cum"][k + 1] - e
        for j in range(1, n + 1):
            state, dur = T["phases"][(k + j) % n]
            if idx < len(state) and state[idx] in "Gg":
                return wait
            wait += dur
        return INF

    @staticmethod
    def _travel(dist, v, acc=1.5, cruise=6.0):
        """지금 속도 v 에서 dist(m) 를 가는 데 걸리는 시간 (넉넉하게: 가속 1.5 m/s², 적색 통과 속도 6 m/s 기준)."""
        top = max(v, cruise)
        t_acc = (top - v) / acc
        d_acc = (v + top) / 2 * t_acc
        if dist <= d_acc:
            return (math.sqrt(v * v + 2 * acc * max(dist, 0.0)) - v) / acc
        return t_acc + (dist - d_acc) / top

    def _stop_speed(self, room):
        """room(m) 안에 설 수 있는 속도: 감속도 ped_brake 로, 한 스텝 늦게 줄이기 시작해도 넘지 않게 (SUMO 는 0.5 초 단위)."""
        if room <= 0.0:
            return 0.0
        b = self.ped_brake * self.dt
        return min(math.sqrt(b * b + 2 * self.ped_brake * room) - b, room / self.dt)

    def _length(self, lane_id):
        if lane_id not in self.lane_len:
            self.lane_len[lane_id] = traci.lane.getLength(lane_id)
        return self.lane_len[lane_id]

    def _ped_state(self, cid, t, need):
        """그 횡단보도를 지금부터 need 초 동안 지나가도 되는가 → (단계, 보행 신호가 켜질 때까지 남은 시간).
        2 = 사람이 건너는 중·막 건너려 함, 또는 보행 신호가 켜져 있음 / 1 = 다 지나가기 전에 보행 신호가 켜짐 / 0 = 됨."""
        c = self.cross[cid]
        g = 0.0 if c["tl"] is None else self._green_in(c["tl"], c["idx"], t)
        if traci.edge.getLastStepPersonIDs(cid):
            return 2, g
        if g > need:
            return 0, g                                   # 다 지나갈 때까지 보행 신호 빨강 → 새로 건너오지 않음
        if c.get("timed"):
            return (2 if g <= 0.0 else 1), g
        for wa in c["wa"]:                                # 늘 초록이거나 신호 없는 횡단보도 (소방서 진출입로 보도 등)
            for p in traci.edge.getLastStepPersonIDs(wa):
                if traci.person.getNextEdge(p) == cid:
                    return 2, g                           # 끝에서 막 건너려는 사람
        return 0, g

    @staticmethod
    def _ped_in_path(cid, pos, hx, hy):
        """차 앞머리 바로 앞 (앞 8 m, 좌우 3 m) 에 그 횡단보도를 건너는 사람이 있는지."""
        for p in traci.edge.getLastStepPersonIDs(cid):
            px, py = traci.person.getPosition(p)
            ahead = (px - pos[0]) * hx + (py - pos[1]) * hy
            side = (px - pos[0]) * hy - (py - pos[1]) * hx
            if -1.0 <= ahead <= 8.0 and abs(side) <= 3.0:
                return True
        return False

    def _source(self, lane):
        """교차로 안 차로 lane 으로 들어오는 (바깥 차로, 신호등, 신호 번호, 중간에 거치는 교차로 안 차로들)."""
        src, tls, idx, mid = lane, None, None, []
        for _ in range(3):
            if src not in self.via_src:
                return None, None, None, mid
            src, tls, idx = self.via_src[src]
            if not src.startswith(":"):
                break
            mid.append(src)                               # 교차로 안에서 기다렸다 들어오는 차로
        return src, tls, idx, mid

    def _conflicts(self, via):
        """교차로 안 차로 via 로 지나갈 때 가로지르거나 합쳐지는 차로들. len: via 길이,
        inside: [(교차로 안 차로, 그 차로가 나가는 차로)], from: [(그리로 들어오는 차로, 신호등, 신호 번호)],
        lanes: 그 교차로 안 차로들"""
        inside, srcs, seen, length, lane = [], {}, set(), 0.0, via
        own = self._source(via)[0]                        # 내가 들어오는 차로: 같은 차로에서 갈라지는 길은 앞차 문제 (SUMO 가 봄)
        for _ in range(3):
            length += traci.lane.getLength(lane)
            for f in traci.lane.getInternalFoes(lane):
                edge = f.rsplit("_", 1)[0]
                if f in seen or "_c" in edge or "_w" in edge:
                    continue                              # 횡단보도·보행자 대기 공간은 _ped_state 가 본다
                seen.add(f)
                out = [lk[0] for lk in traci.lane.getLinks(f) if not lk[0].startswith(":")]
                src, tls, idx, mid = self._source(f)
                if src is not None and src == own:
                    continue
                inside.append((f, out[0] if out else None))
                for m in mid:
                    if m not in seen:
                        seen.add(m)
                        inside.append((m, None))
                if src is not None:
                    srcs.setdefault(src, (tls, idx))
            nxt = [lk[0] for lk in traci.lane.getLinks(lane) if lk[0].startswith(":")]
            if not nxt:
                break
            lane = nxt[0]
        return {"len": length, "inside": inside, "from": [(src, tls, idx) for src, (tls, idx) in srcs.items()],
                "lanes": {f for f, _ in inside}}

    def _entry(self, ev, t, nl, line, length, v):
        """초록불이 아닌데 들어가는 교차로에 지금 들어가면 안 되는 이유 (없으면 None). 초록불이면 None: SUMO 기본 판단대로.
        nl: traci.vehicle.getNextLinks(ev), line: 정지선까지 거리"""
        if not nl or not nl[0][4] or nl[0][5] in "GM":
            return None
        out, via = nl[0][0], nl[0][4]
        red = nl[0][5] in "ryu"                           # 적색·황색을 지나감 (아니면 신호 없는 진출로·양보 진입)
        J = self.junc.get(via)
        if J is None:
            J = self.junc[via] = self._conflicts(via)
        ids = traci.lane.getLastStepVehicleIDs(out)
        if ids:
            x = ids[0]                                    # 나갈 차로 맨 뒤 차
            if (traci.vehicle.getLanePosition(x) - traci.vehicle.getLength(x) < length + 2.0
                    and traci.vehicle.getSpeed(x) < 2.0):
                return "나갈 자리 없음"
        # 내 길을 가로지르는 교차로 안 차로: 적색·황색이면 비어 있어야 하고, 양보 진입이면 서행·정지 차가 없어야 한다
        slow = INF if red else 3.0
        for f, tail in J["inside"]:
            for x in traci.lane.getLastStepVehicleIDs(f):
                if traci.vehicle.getSpeed(x) < slow:
                    return "교차로 안에 차"
            if tail is not None:
                ids = traci.lane.getLastStepVehicleIDs(tail)
                if (ids and traci.vehicle.getLanePosition(ids[0]) < traci.vehicle.getLength(ids[0]) + 0.5
                        and traci.vehicle.getSpeed(ids[0]) < slow):
                    return "교차로를 빠져나가는 차"         # 꽁무니가 아직 교차로 안
        cross = self._travel(J["len"] + length, min(v, 6.0))   # 교차로를 다 빠져나가는 데 걸리는 시간
        for src, tls, idx in J["from"]:
            g = 0.0 if tls is None else self._green_in(tls, idx, t)
            if g > cross + 2.0 or (g <= 0.0 and (self.native_foes or not red)):
                continue          # 내가 지나가는 동안 그쪽은 빨강 / 지금 초록인 쪽은 아래에서 (양보 진입은 SUMO 가) 본다
            ids = traci.lane.getLastStepVehicleIDs(src)
            if ids and ids[-1] != ev:                     # 정지선에 가장 가까운 차: 내가 다 지나가기 전에 초록불을 받고 들어옴
                d = self._length(src) - traci.vehicle.getLanePosition(ids[-1])
                if g + d / max(traci.vehicle.getSpeed(ids[-1]), 4.0) <= cross + 3.0:
                    return "곧 들어올 차"
        if red and self.native_foes:
            # SUMO 가 '그 차로로 곧 들어올 차'로 잡은 차 (짧은 도로 너머 윗길에서 오는 차도 포함). 적색·황색에서는
            # SUMO 가 가로지르는 차에 양보를 시키지 않는 경우가 있어 직접 확인한다.
            for f in traci.vehicle.getJunctionFoes(ev, line + J["len"] + 1.0):
                x, lane = f[0], f[6]
                if x == ev or lane not in J["lanes"]:
                    continue
                if x in self.evs and x in self.hold and x > ev:
                    continue                              # 서로 기다리는 긴급차 둘: 이름순으로 먼저 감
                return "들어올 차"
        return None

    def _blocked_ahead(self, ev, pos, hx, hy, v):
        """교차로 안을 지나는 긴급차 앞길(멈추는 데 필요한 거리 + 6 m, 좌우는 긴급차 폭의 절반 + 0.8 m)에 가로지르는
        차로의 차 몸통(직사각형)이 걸쳐 있으면 거기까지의 거리, 없으면 None. SUMO 는 교차로 안에서 기어가다 멈춘 차를
        '지나간 차'로 보고 긴급차를 출발시켜 들이받는 일이 있어서 차 위치를 직접 본다.
        몸통은 길이 방향 1 m 간격 × 폭 방향 양끝·가운데 점으로 본다. (전에는 가운데 줄만 보고 옆 여유에 상대 차 폭의
        절반을 더해, 직각으로 가로지르는 차를 실제보다 최대 1.25 m 가깝게 봤다 → 긴급차를 기다려 주는 버스 앞에서
        긴급차도 서서 서로 기다림)"""
        via = traci.vehicle.getLaneID(ev)
        J = self.junc.get(via)
        if J is None:
            J = self.junc[via] = self._conflicts(via)
        look = v * v / (2 * self.ped_brake) + 6.0
        side_max = traci.vehicle.getWidth(ev) / 2 + 0.8
        best = None
        for f, tail in J["inside"]:
            ids = list(traci.lane.getLastStepVehicleIDs(f))
            if tail is not None:
                ids += list(traci.lane.getLastStepVehicleIDs(tail))[:1]
            for x in ids:
                if x == ev or traci.vehicle.getSpeed(x) > 3.0:
                    continue                              # 움직이는 차는 SUMO 가 본다
                px, py = traci.vehicle.getPosition(x)
                a = math.radians(traci.vehicle.getAngle(x))
                ux, uy = math.sin(a), math.cos(a)          # 그 차의 앞쪽
                w2, length = traci.vehicle.getWidth(x) / 2, traci.vehicle.getLength(x)
                k = 0.0
                while True:                               # 차 몸통을 앞머리부터 1 m 간격으로, 폭 방향 양끝·가운데
                    for w in (-w2, 0.0, w2):
                        qx, qy = px - ux * k + uy * w, py - uy * k - ux * w
                        ahead = (qx - pos[0]) * hx + (qy - pos[1]) * hy
                        side = (qx - pos[0]) * hy - (qy - pos[1]) * hx
                        if 0.0 <= ahead <= look and abs(side) <= side_max and (best is None or ahead < best):
                            best = ahead
                    if k >= length:
                        break
                    k = min(k + 1.0, length)              # 꽁무니 끝까지
        return best

    def _guard(self, ev, t):
        """긴급차 속도 상한: 정지선·횡단보도 앞에서 설 수 있게 줄이고, 조건이 풀리면 원래대로."""
        pos = traci.vehicle.getPosition(ev)
        ang = math.radians(traci.vehicle.getAngle(ev))
        hx, hy = math.sin(ang), math.cos(ang)            # SUMO 각도: 북=0, 시계방향
        v = traci.vehicle.getSpeed(ev)
        length = traci.vehicle.getLength(ev)
        inside = traci.vehicle.getRoadID(ev).startswith(":")
        nl = () if inside else traci.vehicle.getNextLinks(ev)
        slow = bool(nl) and nl[0][5] not in "GM"         # 다음 교차로에 초록불 없이 들어감 (적색이면 SUMO 가 6 m/s 이하로 줄임)
        route, ri = traci.vehicle.getRoute(ev), max(0, traci.vehicle.getRouteIndex(ev))
        brake = v * v / (2 * self.ped_brake)             # 편하게 서는 데 필요한 거리
        hard = v * v / (2 * traci.vehicle.getDecel(ev))  # 급제동으로 서는 데 필요한 거리
        held = self.hold.get(ev)
        cap, hold, why = INF, None, None
        for i in range(3):
            if ri + i >= len(route):
                break
            e = route[ri + i]
            node = self.to_node.get(e)
            nxt = route[ri + i + 1] if ri + i + 1 < len(route) else None
            if i == 0:                                    # 정지선까지 거리 (이미 교차로 안이면 None)
                line = None if inside else self._length(traci.vehicle.getLaneID(ev)) - traci.vehicle.getLanePosition(ev)
            else:
                try:
                    line = traci.vehicle.getDrivingDistance(ev, e, self._length(f"{e}_0"))
                except traci.TraCIException:
                    break
                if line < 0:
                    break
            if line is not None and line > brake + 30.0:
                break                                     # 아직 멀다
            stops, worst = [], 0
            for cid in self.cross_at.get(node, ()):
                c = self.cross[cid]
                if e not in c["edges"] and (nxt is None or nxt not in c["edges"]):
                    continue
                pts = c["shape"]
                d, q = min((_seg_dist(pos, pts[k], pts[k + 1]) for k in range(len(pts) - 1)), key=lambda x: x[0])
                if (q[0] - pos[0]) * hx + (q[1] - pos[1]) * hy < -c["half"]:
                    continue                              # 앞머리가 이미 지나감
                # 꽁무니까지 다 지나가는 시간 (굽은 길 여유 1.25)
                clear = self._travel(1.25 * (d + c["half"]) + length, min(v, 6.0) if slow and i == 0 else v)
                level, g = self._ped_state(cid, t, clear + self.ped_margin)
                if level == 1 and line is None and g > clear:
                    level = 0                             # 이미 교차로 안: 보행 신호 전에 빠져나갈 수 있으면 그대로 간다
                if level:
                    stops.append((cid, d - c["half"], level))        # 횡단보도 가장자리까지 거리
                    worst = max(worst, level)
            jam = None
            if i == 0 and line is not None and not worst and line <= brake + 15.0:
                jam = self._entry(ev, t, nl, line, length, v)
            if line is not None and (worst or jam) and (held == node or v < 0.5 or line >= v * self.dt + hard + 0.5):
                cap = min(cap, self._stop_speed(line - 1.0))       # 정지선 1 m 앞에 선다 (서 있던 차는 그대로 서 있음)
                hold, why = node, (jam or ("보행자" if worst == 2 else "곧 보행 신호"))
                break
            for cid, edge, level in stops:
                if line is not None and level == 1:
                    continue                              # 정지선 앞에 설 수 없고 아직 보행 신호 전 → 그대로 지나감
                if edge > 0.5:                            # 횡단보도 2 m 앞에 선다 (거기를 조금 넘었어도 횡단보도 밖이면 선다)
                    cap, why = min(cap, self._stop_speed(edge - 2.0)), "보행자"
                elif self._ped_in_path(cid, pos, hx, hy):
                    cap, why = 0.0, "보행자"               # 이미 횡단보도에 걸쳐 있음: 바로 앞에 사람이 있을 때만 선다
        if inside:                                        # 교차로 안: 내 길에 걸쳐 서 있는 차 앞에서 선다
            room = self._blocked_ahead(ev, pos, hx, hy, v)
            if room is not None:
                cap, why = min(cap, self._stop_speed(room - 2.0)), "교차로 안에 차"
        if hold is None:
            self.hold.pop(ev, None)
        else:
            if held != hold:
                self.stats["ped_stop" if why in ("보행자", "곧 보행 신호") else "entry_hold"] += 1
            self.hold[ev] = hold
        if cap < INF:
            if hold is None and ev not in self.capped:
                self.stats["ped_stop"] += 1
            traci.vehicle.setSpeed(ev, cap)
            self.capped.add(ev)
            self.why[ev] = why
        elif ev in self.capped:
            traci.vehicle.setSpeed(ev, -1)
            self.capped.discard(ev)
            self.why.pop(ev, None)

    # ── 3) 긴급차량 우선신호 ──
    def _snapshot_signals(self, t):
        self.tl = {}
        for tls in traci.trafficlight.getIDList():
            prog = traci.trafficlight.getProgram(tls)
            logic = next((lg for lg in traci.trafficlight.getAllProgramLogics(tls) if lg.programID == prog), None)
            if logic is None or logic.type != 0:          # 고정식(static)만
                continue
            phases = [(p.state, p.duration) for p in logic.phases]
            cum = [0.0]
            for _, dur in phases:
                cum.append(cum[-1] + dur)
            k = traci.trafficlight.getPhase(tls)
            rem = traci.trafficlight.getNextSwitch(tls) - t
            elapsed = cum[k] + (phases[k][1] - rem)
            links = traci.trafficlight.getControlledLinks(tls)
            ped = {i for i, lk in enumerate(links) if lk and lk[0][0].startswith(":")}
            veh_cross = {}                    # 차 신호 → 그 차가 가로지르는 횡단보도들
            for i, lk in enumerate(links):
                if lk and i not in ped and lk[0][2]:
                    veh_cross[i] = self._link_crossings(lk[0][2])
            self.tl[tls] = {"prog": prog, "phases": phases, "cum": cum, "C": cum[-1],
                            "anchor": t - elapsed, "ped": ped, "veh_cross": veh_cross}
        for c in self.cross.values():                 # 켜졌다 꺼졌다 하는 보행 신호인가 (늘 초록·신호 없음은 False)
            T = self.tl.get(c["tl"])
            on = [st[c["idx"]] in "Gg" for st, _ in T["phases"] if c["idx"] < len(st)] if T else []
            c["timed"] = any(on) and not all(on)

    @staticmethod
    def _link_crossings(via):
        """교차로 안 차로(via)부터 교차로를 빠져나갈 때까지 가로지르는 횡단보도 id."""
        out, lane = set(), via
        for _ in range(3):
            out |= {f.rsplit("_", 1)[0] for f in traci.lane.getInternalFoes(lane) if "_c" in f.rsplit("_", 1)[0]}
            nxt = [lk[0] for lk in traci.lane.getLinks(lane) if lk[0].startswith(":")]
            if not nxt:
                break
            lane = nxt[0]
        return out

    def _ped_hold(self, tls, frm, to):
        """새로 초록이 되는 차 신호 중, 가로지르는 횡단보도에 아직 사람이 남아 있는 것 (보행자 다 건널 때까지 빨강)."""
        T = self.tl[tls]
        hold = set()
        for i, cr in T["veh_cross"].items():
            if i < len(to) and to[i] in "Gg" and frm[i] not in "Gg":
                if any(traci.edge.getLastStepPersonIDs(c) for c in cr):
                    hold.add(i)
        return hold

    def _phase_end(self, tls, k, t):
        """시간표에서 단계 k 가 (t 이후) 끝나는 시각. t 가 그 단계 전이면 다음 그 단계 끝 (늦게 맞춤)."""
        T = self.tl[tls]
        n = math.floor((t - T["anchor"]) / T["C"])
        for m in (n, n + 1):
            end = T["anchor"] + m * T["C"] + T["cum"][k + 1]
            if end > t + 0.25:
                return end
        return t + T["phases"][k][1]

    def _scheduled(self, tls, t):
        T = self.tl[tls]
        e = (t - T["anchor"]) % T["C"]
        k = next(i for i in range(len(T["phases"])) if e < T["cum"][i + 1])
        return k, T["cum"][k + 1] - e

    def _target_phase(self, tls, idx):
        best = None
        for k, (s, dur) in enumerate(self.tl[tls]["phases"]):
            if idx < len(s) and s[idx] in "Gg":
                key = (s[idx] == "G", dur)
                if best is None or key > best[0]:
                    best = (key, k)
        return None if best is None else best[1]

    def _transition(self, tls, cur, tgt, t):
        """cur → tgt: 초록에서 빨강이 되는 차 신호는 황색 3초, 그다음 전적색 2초, 그리고 tgt."""
        ped = self.tl[tls]["ped"]
        y, ar = [], []
        need_y = need_ar = False
        for i, (c, g) in enumerate(zip(cur, tgt)):
            cg, gg = c in "Gg", g in "Gg"
            if cg and gg:
                y.append(c)
                ar.append(c)
            elif cg or c in "yY":
                y.append("r" if i in ped else "y")
                need_y |= i not in ped
                ar.append("r")
                need_ar = True
            else:
                y.append(c if c == "s" else "r")
                ar.append("r")
                need_ar |= gg
        plan = []
        if need_y:
            plan.append(("".join(y), t + 3.0))
        if need_y or need_ar:
            plan.append(("".join(ar), (plan[-1][1] if plan else t) + 2.0))
        plan.append((tgt, INF))
        return plan

    def _exit_phase(self, tls):
        """본선(nb_/sb_) 차 신호가 모두 빨간 단계 중 가장 긴 것 (소방서 출동용)."""
        if tls not in self.tl:
            return None
        links = traci.trafficlight.getControlledLinks(tls)
        main = [i for i, lk in enumerate(links) if lk and lk[0][0].startswith(("nb_", "sb_"))]
        best = None
        for k, (s, dur) in enumerate(self.tl[tls]["phases"]):
            key = (sum(s[i] in "rs" for i in main), dur)
            if best is None or key > best[0]:
                best = (key, k)
        return None if best is None else best[1]

    def _signals(self, t):
        want = {}
        for ev in sorted(self.evs):
            road = traci.vehicle.getRoadID(ev)
            if road in self.exit_signal and self.exit_signal[road]:
                self.exiting.add(ev)
            elif ev in self.exiting and not road.startswith(":"):
                self.exiting.discard(ev)
            if ev in self.exiting:
                tls = self.exit_signal["FS_in"]
                want.setdefault(tls, {})[ev] = "exit"
                continue
            for tls, idx, dist, _ in traci.vehicle.getNextTLS(ev):
                if dist > self.pre_dist:
                    break
                if tls in self.tl:
                    want.setdefault(tls, {}).setdefault(ev, idx)
        for tls, owners in want.items():
            P = self.pre.get(tls)
            if P is None:
                if t < self.cool.get(tls, -1.0):
                    continue
                idx = next(iter(owners.values()))
                k = self._exit_phase(tls) if idx == "exit" else self._target_phase(tls, idx)
                if k is None:
                    continue
                tgt = self.tl[tls]["phases"][k][0]
                cur = traci.trafficlight.getRedYellowGreenState(tls)
                self.pre[tls] = {"tgt": tgt, "owners": dict(owners), "since": t, "mode": "in", "exit": idx == "exit",
                                 "plan": self._transition(tls, cur, tgt, t), "set": None, "from": cur}
                self.stats["priority_signal"] += 1
            elif P["mode"] != "out":
                for ev, idx in owners.items():
                    same = P["exit"] if idx == "exit" else (not P["exit"] and P["tgt"][idx] in "Gg")
                    if same:                                  # 같은 신호로 함께 지나갈 수 있는 긴급차
                        P["owners"].setdefault(ev, idx)
        for tls, P in list(self.pre.items()):
            if P["mode"] != "out":
                P["owners"] = {ev: i for ev, i in P["owners"].items() if ev in want.get(tls, {})}
                if not P["owners"] or t - P["since"] > self.max_hold:
                    if P["owners"]:                        # 오래 붙잡음 → 25초는 원래 신호대로
                        self.cool[tls] = t + 25.0
                    cur = P["plan"][0][0]
                    k_s, rem = self._scheduled(tls, t + 5.0)
                    if rem < 3.0:                          # 곧 끝날 단계 대신 그다음 단계로 맞춤
                        k_s = (k_s + 1) % len(self.tl[tls]["phases"])
                    P["plan"] = self._transition(tls, cur, self.tl[tls]["phases"][k_s][0], t)
                    P["mode"], P["k_s"], P["from"] = "out", k_s, cur
                    P.pop("hold0", None)
            while len(P["plan"]) > 1 and t >= P["plan"][0][1]:
                P["plan"].pop(0)
            state = P["plan"][0][0]
            if len(P["plan"]) == 1:
                # 보행 신호가 끝났어도 횡단보도에 남은 사람이 다 건널 때까지 그 횡단보도를 지나는 차 신호는 빨강
                hold = self._ped_hold(tls, P["from"], state)
                if hold and t - P.setdefault("hold0", t) < 40.0:   # 가장 긴 횡단보도(E, 30 m)도 다 건너게
                    state = "".join("r" if i in hold else c for i, c in enumerate(state))
                    if P["set"] != state:
                        traci.trafficlight.setRedYellowGreenState(tls, state)
                        P["set"] = state
                    continue
            if P["mode"] == "out" and len(P["plan"]) == 1:
                T = self.tl[tls]
                traci.trafficlight.setProgram(tls, T["prog"])
                traci.trafficlight.setPhase(tls, P["k_s"])
                traci.trafficlight.setPhaseDuration(tls, max(0.5, self._phase_end(tls, P["k_s"], t) - t))
                del self.pre[tls]
                continue
            if P["set"] != state:
                traci.trafficlight.setRedYellowGreenState(tls, state)
                P["set"] = state

    # ── 4) 꼬리물기 방지 ──
    def _build_box(self):
        """신호 교차로에서 한 차로가 둘 이상의 갈래(교차로 안 차로)로 나뉘는 곳을 찾고, 갈래 V 마다
        옆 갈래 S 의 차가 V 앞을 막는 구간 (S 를 따라 두 길이 2.5 m 벌어지는 곳까지, SUMO 와 같은 기준)."""
        vias = {}
        for tls in traci.trafficlight.getIDList():
            for lk in traci.trafficlight.getControlledLinks(tls):
                for inl, _out, via in lk:
                    if via and not inl.startswith(":"):
                        vias.setdefault(inl, set()).add(via)
        self.box = {}
        for inl, vs in vias.items():
            if len(vs) < 2:
                continue
            shape = {v: traci.lane.getShape(v) for v in vs}
            sib = {}
            for V in vs:
                for S in vs:
                    pv, ps = shape[V], shape[S]
                    if S == V or math.hypot(pv[0][0] - ps[0][0], pv[0][1] - ps[0][1]) >= 2.5:
                        continue
                    d = self._divergence(pv, ps)
                    if d > 0.5:
                        sib.setdefault(V, {})[S] = d
            if sib:
                self.box[inl] = {"len": traci.lane.getLength(inl), "sib": sib}
        self.dt = traci.simulation.getDeltaT()

    @staticmethod
    def _divergence(pv, ps, gap=2.5):
        """ps 를 따라가다 pv 와 gap 만큼 벌어지는 곳까지의 거리."""
        acc = 0.0
        for a, b in zip(ps[:-1], ps[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            n = max(1, int(L / 0.25))
            for i in range(n + 1):
                p = (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)
                if min(_seg_dist(p, pv[k], pv[k + 1])[0] for k in range(len(pv) - 1)) >= gap:
                    return acc + L * i / n
            acc += L
        return acc

    @staticmethod
    def _sibling_stopped(sibs):
        """옆 갈래에서 갈라지기 전 구간에 멈춰 있거나 멈추려는 차가 있는지."""
        for S, div in sibs.items():
            for x in traci.lane.getLastStepVehicleIDs(S):
                if traci.vehicle.getLanePosition(x) - traci.vehicle.getLength(x) >= div:
                    continue                              # 뒤끝이 이미 갈라진 곳을 지남
                sp = traci.vehicle.getSpeed(x)
                if sp < 0.5 or (sp < 3.0 and traci.vehicle.getAcceleration(x) < -0.5):
                    return True
        return False

    def _box_guard(self):
        keep = set()
        for inl, B in self.box.items():
            if not traci.lane.getLastStepVehicleNumber(inl):
                continue
            f = traci.lane.getLastStepVehicleIDs(inl)[-1]          # 정지선에 가장 가까운 차
            if f in self.evs or f in self.held or f in self.yielding or f.startswith(self.skip):
                continue
            dist = B["len"] - traci.vehicle.getLanePosition(f)
            if dist > 12.0:
                continue
            nl = traci.vehicle.getNextLinks(f)
            if not nl or nl[0][4] not in B["sib"] or not self._sibling_stopped(B["sib"][nl[0][4]]):
                continue
            room = max(0.0, dist - 0.5)                              # 정지선 0.5 m 앞에 선다
            v = min(math.sqrt(2 * 3.0 * room), room / self.dt, max(traci.vehicle.getSpeed(f), 2.0))
            traci.vehicle.setSpeed(f, v)
            if f not in self.box_held:
                self.stats["box_hold"] += 1
            keep.add(f)
        for f in self.box_held - keep:
            if f not in self.held:
                try:
                    traci.vehicle.setSpeed(f, -1)
                except traci.TraCIException:
                    pass                                         # 이미 도착
        self.box_held = keep

    # ── 비켜 준 차 되돌리기 ──
    def _restore(self, t, live):
        for vid in list(self.yielding):
            st = self.yielding[vid]
            if vid not in live:
                del self.yielding[vid]
                continue
            ln = traci.vehicle.getLaneID(vid)
            if not ln or ln.startswith(":"):
                continue
            # 버스전용 차로에 들어가려고 잠시 바꾼 차종('긴급차')은 원래 차종으로 다닐 수 있는 차로에 왔고, 그 차종으로
            # 필요한 차로까지 옮겨 갈 거리(50 m + 차로 하나당 40 m)가 있으면 바로 돌려준다 (긴급차가 아직 뒤에 있어도).
            # '긴급차'로 남아 있으면 A 유턴 차로처럼 긴급차를 막아 둔 차로를 못 써서 갇힐 수 있음.
            # 어느 차로로 갈지는 SUMO 운전자가 자기 경로를 보고 스스로 정한다 (코드는 차로를 지시하지 않음).
            if traci.vehicle.getVehicleClass(vid) != st["cls"] and st.get("chk") != ln:
                st["chk"] = ln                             # 같은 차로에서는 한 번만 확인
                allowed = traci.lane.getAllowed(ln)
                if not allowed or st["cls"] in allowed:
                    traci.vehicle.setVehicleClass(vid, st["cls"])
                    traci.vehicle.updateBestLanes(vid)     # 차종이 바뀌면 갈 수 있는 차로 다시 계산
                    if self._can_return(vid, ln):
                        if "color" in st:
                            traci.vehicle.setColor(vid, st["color"])
                    else:                                  # 교차로 직전 짧은 구간 등: 다음 도로에서 다시 봄
                        traci.vehicle.setVehicleClass(vid, "emergency")
                        traci.vehicle.updateBestLanes(vid)
            if t - st["seen"] < self.return_after:
                continue                                   # 긴급차가 아직 뒤에 있음
            if traci.vehicle.getVehicleClass(vid) != st["cls"]:
                continue                                   # 아직 차종을 돌려줄 수 없는 곳 (버스전용 구간 등)
            if st.get("lcm"):
                traci.vehicle.setLaneChangeMode(vid, LC_MODE_DEFAULT)
            del self.yielding[vid]
            self.after_yield[vid] = t

    def _reroute_stranded(self, t, live):
        """비켜 준 뒤 계획한 길로 못 가게 된 차(가야 할 차로로 못 옮기고 차로 끝에 3초 넘게 선 차)는 내비게이션처럼
        지금 차로에서 갈 수 있는 다음 도로로 시작하는 새 경로(같은 목적지, SUMO 최단 시간)를 받는다."""
        cands = [v for v in self.yielding if v in live]
        for v in list(self.after_yield):
            if v not in live or t - self.after_yield[v] > 120.0:
                del self.after_yield[v]
                self.strand.pop(v, None)
            else:
                cands.append(v)
        for v in cands:
            ln = traci.vehicle.getLaneID(v)
            if not ln or ln.startswith(":"):
                continue
            need = None
            for b in traci.vehicle.getBestLanes(v):
                if b[0] == ln:
                    need = (b[1] - traci.vehicle.getLanePosition(v), b[3], b[4])
            # 원래 차종: 차로를 옮겨야 하는데 못 옮김 / 어느 차종이든: 이 차로로는 경로를 더 이어 갈 수 없음
            # (예: 임시 차종 '긴급차'로 A 유턴 차로 앞까지 왔는데 유턴 차로는 '긴급차'를 막아 둠)
            own = v not in self.yielding or traci.vehicle.getVehicleClass(v) == self.yielding[v]["cls"]
            if (need is None or need[0] > 15.0 or traci.vehicle.getSpeed(v) > 0.5
                    or not ((own and need[1] != 0) or not need[2])):
                self.strand.pop(v, None)
                continue
            t0 = self.strand.setdefault(v, t)
            if t - t0 >= 3.0 and self._reroute(v, ln):
                self.strand.pop(v, None)
            elif t - t0 >= 10.0 and self._rescue(v, ln, t):
                self.strand.pop(v, None)                   # 새 경로도 없음 → 버스차로로 계속 가도록 허용

    def _scan_traps(self, t, live):
        """비킨 적이 없거나 비킨 지 오래된 차라도, 버스차로(점선) 구간 끝에서 경로대로 못 가고(차로를 옮겨야 함)
        신호 한 주기(90초) 넘게 서 있으면 갇힌 것으로 본다 → 새 경로가 있으면 새 경로, 없으면 _rescue."""
        cur = set()
        for ln in self.dash_bus:
            ids = traci.lane.getLastStepVehicleIDs(ln)
            if not ids:
                continue
            v = ids[-1]                                    # 차로 끝에 가장 가까운 차
            if (v in self.evs or v in self.yielding or v in self.buses or v in self.held or v in self.box_held
                    or v.startswith(self.skip) or traci.vehicle.getSpeed(v) > 0.5
                    or self._length(ln) - traci.vehicle.getLanePosition(v) > 15.0
                    or self._wanted_dir(v, ln) == 0):
                continue
            cur.add(v)
            t0 = self.trap.setdefault(v, t)
            if t - t0 >= 90.0 and (self._reroute(v, ln) or self._rescue(v, ln, t)):
                cur.discard(v)
        for v in list(self.trap):
            if v not in cur:
                del self.trap[v]
        for v in list(self.rescue_try):
            if v not in live:
                del self.rescue_try[v]

    def _rescue(self, v, ln, t):
        """차로 끝에 갇힌 차(새 경로도 없음)에게 비켜 주는 차와 같은 임시 통행 허용(차종 '긴급차')을 준다. 그러면
        SUMO 운전자가 버스차로를 따라 스스로 직진해 원래 경로로 간다. 원래 차종으로 돌아갈 거리가 있는 차로에 오면
        _restore 가 원래 차종을 돌려준다 (차로·속도 명령은 하지 않음)."""
        cls = traci.vehicle.getVehicleClass(v)
        if ln not in self.dash_bus or cls in ("bus", "emergency") or not self._continues(v, ln):
            return False
        if t - self.rescue_try.get(v, -1e9) < 5.0:
            return False                                   # 같은 차는 5초에 한 번만 살핌
        self.rescue_try[v] = t
        traci.vehicle.setVehicleClass(v, "emergency")
        traci.vehicle.updateBestLanes(v)
        pos = traci.vehicle.getLanePosition(v)
        if not any(b[0] == ln and b[4] and b[1] - pos > 30.0 for b in traci.vehicle.getBestLanes(v)):
            # 허용해도 이 차로로는 경로를 이어 갈 수 없음 (차로 규칙 때문에 갇힌 게 아니라 차가 많아 못 옮기는 것)
            traci.vehicle.setVehicleClass(v, cls)
            traci.vehicle.updateBestLanes(v)
            return False
        st = self.yielding.get(v)
        if st is None:                                     # 긴급차는 이미 지나감 (seen 을 지난 시각으로)
            st = self.yielding[v] = {"cls": cls, "seen": t - self.return_after - 1.0, "asked": -1e9}
        st["chk"] = ln                                     # 이 차로에서는 바로 되돌리지 않음
        self.after_yield.pop(v, None)
        self.stats["rescue"] = self.stats.get("rescue", 0) + 1
        return True

    def _reroute(self, v, ln):
        route, i = traci.vehicle.getRoute(v), traci.vehicle.getRouteIndex(v)
        if i < 0 or i + 1 >= len(route):
            return False
        dest, planned = route[-1], route[i + 1]
        # 차종을 바꾼 적이 있는 차는 'car_idm@차이름' 같은 그 차 전용 차종을 쓴다. 그 이름으로 경로를 찾으면 SUMO 가
        # 임시 차를 만들었다 지우면서 그 전용 차종까지 지워 버려 SUMO 가 멈춘다 → 원래 차종 이름으로 찾는다
        vtype = traci.vehicle.getTypeID(v).split("@")[0]
        best = None
        for lk in traci.lane.getLinks(ln):
            nxt = lk[0].rsplit("_", 1)[0]
            if nxt == planned or nxt.startswith(":"):
                continue                                   # 계획한 길로는 못 감 → 다른 길만 찾음
            allowed = traci.lane.getAllowed(lk[0])
            if allowed and traci.vehicle.getVehicleClass(v) not in allowed:
                continue
            try:
                r = traci.simulation.findRoute(nxt, dest, vType=vtype)
            except traci.TraCIException:
                continue
            if not r.edges or route[i] in r.edges:
                continue                                   # 지금 도로를 다시 지나는 빙 도는 길은 쓰지 않음
            if best is None or r.travelTime < best[1]:
                best = (list(r.edges), r.travelTime)
        if best is None:
            return False
        try:
            traci.vehicle.setRoute(v, [route[i]] + best[0])
        except traci.TraCIException:
            return False
        self.stats["reroute"] = self.stats.get("reroute", 0) + 1
        return True

    # ── 보고용 ──
    def summary(self):
        return dict(self.stats, bus_lane_cars=len(self.bus_lane_entries))
