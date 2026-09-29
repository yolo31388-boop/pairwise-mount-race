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
    1: {"gold": 1000, "title": "冠军骑士", "mount_skin": "golden"},
    2: {"gold": 600, "title": "亚军骑士", "mount_skin": "silver"},
    3: {"gold": 400, "title": "季军骑士", "mount_skin": "bronze"},
}
BASE_GOLD = 200  # 第4名起, 每降一名减20, 保底参与奖
GOLD_STEP = 20
MIN_GOLD = 50

RACER_RADIUS = 2.0  # 多人竞速碰撞体积半径
DISCONNECT_PENALTY = 30.0  # 掉线重连时间补偿(秒)


@dataclass
class RaceTrack:
    tid: str
    name: str
    checkpoints: list = field(default_factory=list)
    obstacles: list = field(default_factory=list)
    boundaries: list = field(default_factory=list)  # [(x1, y1, x2, y2), ...] 碰撞体


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
        # bug2: 分段计时记录 {tid: {rid: {segment: 通过时间}}}
        self.segment_records: dict = {}
        # bug3: 技能状态 {rid: {skill: {"uses": n, "last_used": ts, "active_until": ts}}}
        self.skill_state: dict = {}
        # bug4: 掉线重连保护 {rid: 掉线时刻}
        self.disconnected: dict = {}

    # bug1: 赛道碰撞体与边界检测, 抄近道越界则成绩无效
    def check_boundary(self, tid: str, x: float, y: float) -> bool:
        track = self.tracks.get(tid)
        if track is None or not track.boundaries:
            return True
        for (x1, y1, x2, y2) in track.boundaries:
            if min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
                return True
        return False

    def validate_lap(self, tid: str, path: list) -> bool:
        """路径全部在边界内成绩才有效, 穿墙抄近道判无效。"""
        return all(self.check_boundary(tid, x, y) for x, y in path)

    # bug2: 分段计时, 记录每个检查点的通过时间
    def record_checkpoint(self, tid: str, rid: str, segment: int, ts: float = None) -> float:
        ts = time.monotonic() if ts is None else ts
        self.segment_records.setdefault(tid, {}).setdefault(rid, {})[segment] = ts
        return ts

    def get_segment_time(self, tid: str, segment: int, rid: str = None) -> float:
        records = self.segment_records.get(tid, {})
        if rid is not None:
            return records.get(rid, {}).get(segment, 0.0)
        # 未指定玩家时返回该分段最早记录, 无记录返回0
        times = [r[segment] for r in records.values() if segment in r]
        return min(times) if times else 0.0

    def get_segment_splits(self, tid: str, rid: str) -> list:
        """相邻检查点分段耗时, 可对比每段快慢。"""
        rec = self.segment_records.get(tid, {}).get(rid, {})
        segs = sorted(rec)
        return [rec[b] - rec[a] for a, b in zip(segs, segs[1:])]

    # bug3: 技能冷却 + 次数限制 + 持续时间
    def _skill_cfg(self, skill: str) -> dict:
        return SKILL_CONFIG.get(skill, DEFAULT_SKILL_CONFIG)

    def can_use_skill(self, rid: str, skill: str, now: float = None) -> bool:
        racer = self.racers.get(rid)
        if racer is None or skill not in racer.skills:
            return False
        cfg = self._skill_cfg(skill)
        state = self.skill_state.get(rid, {}).get(skill)
        if state is None:
            return True
        if state["uses"] >= cfg["max_uses"]:
            return False
        now = time.monotonic() if now is None else now
        return now - state["last_used"] >= cfg["cooldown"]

    def use_skill(self, rid: str, skill: str, now: float = None) -> bool:
        if not self.can_use_skill(rid, skill, now):
            return False
        now = time.monotonic() if now is None else now
        cfg = self._skill_cfg(skill)
        state = self.skill_state.setdefault(rid, {}).setdefault(
            skill, {"uses": 0, "last_used": 0.0, "active_until": 0.0})
        state["uses"] += 1
        state["last_used"] = now
        state["active_until"] = now + cfg["duration"]  # 加速持续时间限制
        racer = self.racers.get(rid)
        if racer is not None and skill in racer.skills:
            racer.skills[skill]["uses"] = state["uses"]
            racer.skills[skill]["cd"] = cfg["cooldown"]
        return True

    def skill_active(self, rid: str, skill: str, now: float = None) -> bool:
        state = self.skill_state.get(rid, {}).get(skill)
        if state is None:
            return False
        now = time.monotonic() if now is None else now
        return now < state["active_until"]

    # bug4: 按完成时间排序, 掉线者加重连时间补偿排最后, 不掉出排名
    def disconnect(self, rid: str, now: float = None):
        self.disconnected[rid] = time.monotonic() if now is None else now

    def reconnect(self, rid: str, now: float = None) -> float:
        """重连保护: 返回掉线时长作为时间补偿依据。"""
        now = time.monotonic() if now is None else now
        left = self.disconnected.pop(rid, None)
        return 0.0 if left is None else now - left

    def get_rank(self, finish_times: dict) -> list:
        finished = [(t, rid) for rid, t in finish_times.items() if t is not None]
        dropped = [rid for rid, t in finish_times.items() if t is None]
        finished.sort()
        # 掉线玩家按补偿后排在完成者之后, 保持确定顺序
        return [rid for _, rid in finished] + sorted(dropped)

    # bug5: 按种子随机生成障碍, 每次比赛不同但同种子可复现
    def generate_obstacles(self, tid: str, count: int = 5,
                           area: tuple = (0, 0, 500, 100)) -> list:
        rng = random.Random(f"{self.seed}:{tid}")  # 每场比赛独立可复现
        x1, y1, x2, y2 = area
        obstacles = [(rng.randint(x1, x2), rng.randint(y1, y2)) for _ in range(count)]
        track = self.tracks.get(tid)
        if track is not None:
            track.obstacles = obstacles
        return obstacles

    # bug6: 奖励按排名阶梯, 前三名专属奖励
    def get_reward(self, rank: int) -> dict:
        if rank in REWARD_TABLE:
            return dict(REWARD_TABLE[rank])
        gold = max(MIN_GOLD, BASE_GOLD - GOLD_STEP * (rank - 4))
        return {"gold": gold}

    # bug7: 多人竞速碰撞体积, 距离小于直径则卡位阻挡
    def has_collision(self, r1: str, r2: str) -> bool:
        a, b = self.racers.get(r1), self.racers.get(r2)
        if a is None or b is None:
            return False
        return abs(a.position - b.position) < RACER_RADIUS * 2

    def resolve_blocking(self, r1: str, r2: str):
        """碰撞时卡位: 后者被挡在前者身后。"""
        if self.has_collision(r1, r2):
            a, b = self.racers[r1], self.racers[r2]
            if a.position <= b.position:
                b.position = a.position - RACER_RADIUS * 2
            else:
                a.position = b.position - RACER_RADIUS * 2
