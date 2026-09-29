"""坐骑竞速与赛马系统"""
import random
import time
from dataclasses import dataclass, field

# 技能配置: 冷却秒数 / 最大使用次数 / 持续时间秒数
SKILL_CONFIG = {
    "boost": {"cooldown": 30.0, "max_uses": 3, "duration": 5.0},
}
DEFAULT_SKILL_CONFIG = {"cooldown": 10.0, "max_uses": 5, "duration": 3.0}

# 奖励阶梯: 前三名专属奖励, 其余按名次递减
REWARD_TABLE = {
    1: {"gold": 1000, "title": "冠军", "item": "黄金马鞍"},
    2: {"gold": 600, "title": "亚军", "item": "白银马鞍"},
    3: {"gold": 400, "title": "季军", "item": "青铜马鞍"},
}
PARTICIPATION_GOLD = 50

RACER_RADIUS = 2.0  # 碰撞半径
RECONNECT_GRACE = 30.0  # 掉线重连宽限秒数


@dataclass
class RaceTrack:
    tid: str
    name: str
    checkpoints: list = field(default_factory=list)
    obstacles: list = field(default_factory=list)
    boundaries: list = field(default_factory=list)  # [(x1, y1, x2, y2), ...]


@dataclass
class Racer:
    rid: str
    mount: str
    position: float = 0
    skills: dict = field(default_factory=dict)


class RaceSystem:
    def __init__(self, seed=42):
        self.seed = seed
        self.rng = random.Random(seed)
        self.tracks: dict[str, RaceTrack] = {}
        self.racers: dict[str, Racer] = {}
        # bug2: 分段计时记录 {tid: {rid: [各检查点通过时间]}}
        self.segment_records: dict[str, dict[str, list]] = {}
        # bug3: 技能状态 {rid: {skill: {"cd_until": float, "uses": int, "active_until": float}}}
        self.skill_state: dict[str, dict[str, dict]] = {}
        # bug4: 掉线重连保护 {rid: {"disconnected_at": float, "penalty": float}}
        self.disconnect_state: dict[str, dict] = {}

    # ---- bug1: 赛道碰撞体与边界检测 ----
    def check_boundary(self, tid: str, x: float, y: float) -> bool:
        """坐标在赛道边界内返回 True, 越界(抄近道)返回 False。"""
        track = self.tracks.get(tid)
        if track is None or not track.boundaries:
            return False
        for (x1, y1, x2, y2) in track.boundaries:
            if min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
                return True
        return False

    def validate_lap(self, tid: str, path: list) -> bool:
        """整段轨迹都在边界内成绩才有效, 抄近道穿墙判无效。"""
        return all(self.check_boundary(tid, x, y) for x, y in path)

    # ---- bug2: 分段计时 ----
    def record_checkpoint(self, tid: str, rid: str, segment: int, t: float) -> None:
        """记录玩家通过某检查点的时间, 用于分段对比。"""
        records = self.segment_records.setdefault(tid, {}).setdefault(rid, [])
        while len(records) <= segment:
            records.append(None)
        records[segment] = t

    def get_segment_time(self, tid: str, segment: int, rid: str = None) -> float:
        """取某段用时; 无记录时返回 0.0。"""
        if rid is None:
            return 0.0
        records = self.segment_records.get(tid, {}).get(rid, [])
        if segment < len(records) and records[segment] is not None:
            if segment == 0 or records[segment - 1] is None:
                return records[segment]
            return records[segment] - records[segment - 1]
        return 0.0

    # ---- bug3: 技能冷却 / 次数 / 持续时间 ----
    def can_use_skill(self, rid: str, skill: str) -> bool:
        racer = self.racers.get(rid)
        if racer is None or skill not in racer.skills:
            return False
        cfg = SKILL_CONFIG.get(skill, DEFAULT_SKILL_CONFIG)
        state = self.skill_state.get(rid, {}).get(skill)
        if state is None:
            return True
        now = time.monotonic()
        if state["uses"] >= cfg["max_uses"]:
            return False
        if now < state["cd_until"]:
            return False
        return True

    def use_skill(self, rid: str, skill: str) -> bool:
        """使用技能: 进入冷却并消耗次数, 加速有持续时间上限。"""
        if not self.can_use_skill(rid, skill):
            return False
        cfg = SKILL_CONFIG.get(skill, DEFAULT_SKILL_CONFIG)
        now = time.monotonic()
        state = self.skill_state.setdefault(rid, {}).setdefault(
            skill, {"cd_until": 0.0, "uses": 0, "active_until": 0.0})
        state["uses"] += 1
        state["cd_until"] = now + cfg["cooldown"]
        state["active_until"] = now + cfg["duration"]
        return True

    def skill_active(self, rid: str, skill: str) -> bool:
        state = self.skill_state.get(rid, {}).get(skill)
        return bool(state) and time.monotonic() < state["active_until"]

    # ---- bug4: 排名按完成时间, 掉线重连保护 ----
    def on_disconnect(self, rid: str) -> None:
        self.disconnect_state[rid] = {"disconnected_at": time.monotonic(), "penalty": 0.0}

    def on_reconnect(self, rid: str) -> bool:
        """宽限期内重连保留成绩并补偿掉线时间, 超时判未完赛。"""
        state = self.disconnect_state.get(rid)
        if state is None:
            return False
        offline = time.monotonic() - state["disconnected_at"]
        if offline <= RECONNECT_GRACE:
            state["penalty"] = -offline  # 时间补偿: 扣除掉线时长
            return True
        return False

    def get_rank(self, finish_times: dict) -> list:
        """按完成时间升序排名; 掉线(None)且未重连的排最后, 重连者带时间补偿。"""
        def key(rid):
            t = finish_times.get(rid)
            if t is None:
                return (1, 0.0)  # 未完赛排最后
            penalty = self.disconnect_state.get(rid, {}).get("penalty", 0.0)
            return (0, t + penalty)
        return sorted(finish_times, key=key)

    # ---- bug5: 种子随机障碍, 可复现 ----
    def generate_obstacles(self, tid: str, count: int = 5, area=(0, 0, 500, 100)) -> list:
        """按 (seed, tid) 生成障碍, 同一种子可复现, 不同种子/赛道不同。"""
        rng = random.Random(f"{self.seed}:{tid}")
        x1, y1, x2, y2 = area
        obstacles = [(rng.uniform(x1, x2), rng.uniform(y1, y2)) for _ in range(count)]
        track = self.tracks.get(tid)
        if track is not None:
            track.obstacles = obstacles
        return obstacles

    # ---- bug6: 排名阶梯奖励 ----
    def get_reward(self, rank: int) -> dict:
        if rank in REWARD_TABLE:
            return dict(REWARD_TABLE[rank])
        gold = max(PARTICIPATION_GOLD, 300 - (rank - 3) * 25)
        return {"gold": gold}

    # ---- bug7: 多人碰撞体积 ----
    def has_collision(self, r1: str, r2: str) -> bool:
        a = self.racers.get(r1)
        b = self.racers.get(r2)
        if a is None or b is None:
            return False
        return abs(a.position - b.position) <= RACER_RADIUS * 2

    def resolve_blocking(self, rid: str, target: float) -> float:
        """卡位/阻挡: 目标位置与其他玩家碰撞体积重叠时, 停在对方身后。"""
        me = self.racers.get(rid)
        if me is None:
            return target
        for other in self.racers.values():
            if other.rid == rid:
                continue
            if me.position <= other.position and target > other.position - RACER_RADIUS * 2:
                if me.position < other.position:
                    target = min(target, other.position - RACER_RADIUS * 2)
        return target
