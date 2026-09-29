"""坐骑竞速与赛马系统 - 含7个bug"""
from dataclasses import dataclass, field

@dataclass
class RaceTrack:
    tid: str
    name: str
    checkpoints: list = field(default_factory=list)
    obstacles: list = field(default_factory=list)  # bug5: 固定障碍
    boundaries: list = field(default_factory=list)  # bug1: 无碰撞

@dataclass
class Racer:
    rid: str
    mount: str
    position: float = 0
    skills: dict = field(default_factory=dict)

class RaceSystem:
    def __init__(self, seed=42):
        import random
        self.rng = random.Random(seed)
        self.tracks: dict[str, RaceTrack] = {}
        self.racers: dict[str, Racer] = {}

    def check_boundary(self, tid: str, x: float, y: float) -> bool:
        # bug1: 无碰撞检测
        return True

    def get_segment_time(self, tid: str, segment: int) -> float:
        # bug2: 无分段计时
        return 0.0

    def can_use_skill(self, rid: str, skill: str) -> bool:
        # bug3: 无技能限制
        return True

    def get_rank(self, finish_times: dict) -> list:
        # bug4: 掉线排名错乱
        return sorted(finish_times, key=finish_times.get)

    def generate_obstacles(self, tid: str) -> list:
        # bug5: 固定障碍
        return [(100, 50), (200, 50)]

    def get_reward(self, rank: int) -> dict:
        # bug6: 固定奖励
        return {"gold": 50}

    def has_collision(self, r1: str, r2: str) -> bool:
        # bug7: 无碰撞
        return False
