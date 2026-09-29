"""坐骑竞速与赛马系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mount.race import RaceSystem, RaceTrack, Racer

class TestBoundary:
    def test_out_of_bounds_detected(self):
        rs = RaceSystem()
        rs.tracks["t1"] = RaceTrack("t1", "track", boundaries=[(0, 0, 100, 100)])
        assert rs.check_boundary("t1", 50, 50) == True
        assert rs.check_boundary("t1", 200, 200) == False  # bug1: True

class TestSegmentTime:
    def test_race_has_segment_times(self):
        rs = RaceSystem()
        rs.tracks["t1"] = RaceTrack("t1", "track", checkpoints=["cp1", "cp2"])
        t = rs.get_segment_time("t1", 0)
        assert t >= 0  # bug2: 0但应该有记录机制
        assert hasattr(rs, "segment_records")

class TestSkillLimit:
    def test_skill_has_cooldown(self):
        rs = RaceSystem()
        rs.racers["r1"] = Racer("r1", "horse", skills={"boost": {"cd": 0, "uses": 0}})
        assert rs.can_use_skill("r1", "boost") == True
        # 使用后应该有冷却
        assert hasattr(rs, "use_skill")
        rs.use_skill("r1", "boost")
        assert rs.can_use_skill("r1", "boost") == False  # bug3: 无限制永远True

class TestRankStability:
    def test_disconnect_does_not_break_ranking(self):
        rs = RaceSystem()
        times = {"r1": 100, "r2": None, "r3": 120}  # r2掉线
        rank = rs.get_rank(times)
        assert rank[0] == "r1"  # bug4: 可能错乱
        assert "r2" in rank or len(rank) == 2

class TestRandomObstacles:
    def test_obstacles_vary_by_seed(self):
        rs1 = RaceSystem(seed=42)
        rs2 = RaceSystem(seed=99)
        o1 = rs1.generate_obstacles("t1")
        o2 = rs2.generate_obstacles("t1")
        assert o1 != o2  # bug5: 固定一样

class TestRewardByRank:
    def test_first_place_better_reward(self):
        rs = RaceSystem()
        r1 = rs.get_reward(1)
        r10 = rs.get_reward(10)
        assert r1["gold"] > r10["gold"]  # bug6: 都是50

class TestRacerCollision:
    def test_racers_can_collide(self):
        rs = RaceSystem()
        rs.racers["r1"] = Racer("r1", "horse", position=100)
        rs.racers["r2"] = Racer("r2", "horse", position=101)
        assert rs.has_collision("r1", "r2") == True  # bug7: False
