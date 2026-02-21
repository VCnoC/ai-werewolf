"""
T7.10 边界情况测试 — 验证各种特殊场景。

测试项：
  - 平安夜（守卫守住狼刀）
  - 空刀（狼人不杀人）
  - 同守同救（守卫+女巫同时保护）
  - 女巫毒杀
  - 猎人开枪（被刀死触发）
  - 猎人被毒死不能开枪
  - 屠边判定（屠神/屠民）
  - 20回合平局
  - 狼刀在先原则
  - 首夜自救
"""

import asyncio
import os
import sys
import shutil
import tempfile
from unittest.mock import patch
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_temp_dir = tempfile.mkdtemp(prefix="werewolf_edge_")


def _mock_settings():
    from config import Settings
    return Settings(
        game_data_dir=_temp_dir,
        db_host="localhost",
        db_port=3306,
        db_user="test",
        db_password="test",
        db_name="test",
    )


with patch("config.get_settings", _mock_settings):
    from game.state import GameState, NightActions
    from game.engine import GameEngine
    from game.resolver import resolve_night, check_hunter_trigger
    from models.game_models import (
        RoleType, Faction, DeathCause, GamePhase,
        Player, ROLE_FACTION_MAP,
    )


def make_state(game_id: str = "edge_test") -> GameState:
    """创建标准12人局状态"""
    with patch("config.get_settings", _mock_settings):
        state = GameState.create(game_id, [1] * 12)
    state.current_round = 1
    return state


def find_player_by_role(state: GameState, role: RoleType) -> Player:
    """找到指定角色的玩家"""
    for p in state.players.values():
        if p.role == role:
            return p
    raise ValueError(f"找不到角色 {role}")


def find_players_by_role(state: GameState, role: RoleType) -> list[Player]:
    """找到指定角色的所有玩家"""
    return [p for p in state.players.values() if p.role == role]


# ========== 夜晚结算边界测试 ==========

def test_peaceful_night_guard_block():
    """测试平安夜：守卫守住狼刀"""
    state = make_state("guard_block")
    wolves = find_players_by_role(state, RoleType.WEREWOLF)
    guard = find_player_by_role(state, RoleType.GUARD)
    target = wolves[0].player_id  # 随便选个目标（不是狼人自己）
    # 选一个非狼人目标
    non_wolves = [p for p in state.players.values() if p.role != RoleType.WEREWOLF]
    target = non_wolves[0].player_id

    state.night_actions = NightActions(
        guard_target=target,
        wolf_target=target,  # 守卫和狼人选同一个
    )

    events = resolve_night(state)
    details = [e.get("detail") for e in events if e.get("type") == "night_resolve"]

    assert "guard_blocked" in details, f"应有 guard_blocked 事件，实际: {details}"
    # 目标应存活
    assert state.players[target].is_alive, "被守住的玩家应存活"
    print("  ✅ 平安夜（守卫守住狼刀）")


def test_empty_knife():
    """测试空刀"""
    state = make_state("empty_knife")
    state.night_actions = NightActions(wolf_target=None)

    events = resolve_night(state)
    details = [e.get("detail") for e in events if e.get("type") == "night_resolve"]

    assert "wolf_empty_knife" in details, f"应有 wolf_empty_knife 事件"
    assert "peaceful_night" in details, "空刀应为平安夜"
    # 无人死亡
    death_events = [e for e in events if e.get("type") == "death"]
    assert len(death_events) == 0, "空刀不应有人死亡"
    print("  ✅ 空刀（狼人不杀人）")


def test_witch_save():
    """测试女巫救人"""
    state = make_state("witch_save")
    non_wolves = [p for p in state.players.values()
                  if p.role != RoleType.WEREWOLF and p.role != RoleType.WITCH]
    victim = non_wolves[0].player_id

    state.night_actions = NightActions(
        wolf_target=victim,
        witch_save=True,
    )

    events = resolve_night(state)
    details = [e.get("detail") for e in events if e.get("type") == "night_resolve"]

    assert "witch_saved" in details, "应有 witch_saved 事件"
    assert state.players[victim].is_alive, "被救的玩家应存活"
    print("  ✅ 女巫救人")


def test_witch_poison():
    """测试女巫毒杀"""
    state = make_state("witch_poison")
    wolves = find_players_by_role(state, RoleType.WEREWOLF)
    poison_target = wolves[0].player_id  # 毒一个狼人

    state.night_actions = NightActions(
        wolf_target=None,  # 空刀
        witch_poison_target=poison_target,
    )

    events = resolve_night(state)
    details = [e.get("detail") for e in events if e.get("type") == "night_resolve"]

    assert "witch_poisoned" in details, "应有 witch_poisoned 事件"
    assert not state.players[poison_target].is_alive, "被毒的玩家应死亡"
    print("  ✅ 女巫毒杀")


def test_guard_cannot_block_poison():
    """测试守卫无法挡毒"""
    state = make_state("guard_no_block_poison")
    non_wolves = [p for p in state.players.values()
                  if p.role != RoleType.WEREWOLF and p.role != RoleType.WITCH]
    target = non_wolves[0].player_id

    state.night_actions = NightActions(
        guard_target=target,
        wolf_target=None,
        witch_poison_target=target,  # 毒被守卫守的人
    )

    events = resolve_night(state)
    assert not state.players[target].is_alive, "守卫无法挡毒，被毒者应死亡"
    print("  ✅ 守卫无法挡毒")


def test_hunter_trigger_on_wolf_kill():
    """测试猎人被狼杀触发开枪"""
    state = make_state("hunter_shoot")
    hunter = find_player_by_role(state, RoleType.HUNTER)

    state.night_actions = NightActions(wolf_target=hunter.player_id)
    events = resolve_night(state)

    # 猎人应死亡
    assert not hunter.is_alive, "猎人应被狼杀"
    # 检查猎人触发
    trigger = check_hunter_trigger(state, hunter.player_id)
    assert trigger is not None, "猎人被狼杀应触发开枪"
    assert trigger["trigger"] == "hunter_shoot"
    print("  ✅ 猎人被狼杀触发开枪")


def test_hunter_poisoned_cannot_shoot():
    """测试猎人被毒死不能开枪"""
    state = make_state("hunter_poisoned")
    hunter = find_player_by_role(state, RoleType.HUNTER)

    state.night_actions = NightActions(
        wolf_target=None,
        witch_poison_target=hunter.player_id,
    )
    events = resolve_night(state)

    assert not hunter.is_alive, "猎人应被毒死"
    assert hunter.death_cause == DeathCause.POISON, "死因应为毒杀"
    trigger = check_hunter_trigger(state, hunter.player_id)
    assert trigger is None, "被毒死的猎人不能开枪"
    print("  ✅ 猎人被毒死不能开枪")


def test_wolf_kill_and_poison_same_target():
    """测试狼刀+毒药同一目标"""
    state = make_state("double_kill")
    non_wolves = [p for p in state.players.values()
                  if p.role not in (RoleType.WEREWOLF, RoleType.WITCH)]
    target = non_wolves[0].player_id

    state.night_actions = NightActions(
        wolf_target=target,
        witch_poison_target=target,
    )
    events = resolve_night(state)

    assert not state.players[target].is_alive, "目标应死亡"
    # 毒杀优先
    assert state.players[target].death_cause == DeathCause.POISON, "毒杀优先级高于狼刀"
    # 只死一次
    death_events = [e for e in events if e.get("type") == "death"]
    target_deaths = [e for e in death_events if e.get("player_id") == target]
    assert len(target_deaths) == 1, "同一目标只应死一次"
    print("  ✅ 狼刀+毒药同一目标（毒杀优先）")


# ========== 胜利条件边界测试 ==========

def test_victory_all_wolves_dead():
    """测试好人获胜：狼人全灭"""
    state = make_state("good_win")
    wolves = find_players_by_role(state, RoleType.WEREWOLF)
    for w in wolves:
        state.kill_player(w.player_id, DeathCause.VOTE_EXILE)

    winner = state.check_victory()
    assert winner == "好人阵营", f"狼人全灭应好人获胜，实际: {winner}"
    print("  ✅ 好人获胜（狼人全灭）")


def test_victory_gods_eliminated():
    """测试狼人获胜：屠神"""
    state = make_state("wolf_win_gods")
    gods = [p for p in state.players.values()
            if p.faction == Faction.GOOD and p.role != RoleType.VILLAGER]
    for g in gods:
        state.kill_player(g.player_id, DeathCause.WOLF_KILL)

    winner = state.check_victory()
    assert winner == "狼人阵营", f"屠神应狼人获胜，实际: {winner}"
    print("  ✅ 狼人获胜（屠神）")


def test_victory_villagers_eliminated():
    """测试狼人获胜：屠民"""
    state = make_state("wolf_win_villagers")
    villagers = find_players_by_role(state, RoleType.VILLAGER)
    for v in villagers:
        state.kill_player(v.player_id, DeathCause.WOLF_KILL)

    winner = state.check_victory()
    assert winner == "狼人阵营", f"屠民应狼人获胜，实际: {winner}"
    print("  ✅ 狼人获胜（屠民）")


def test_wolf_first_principle():
    """测试狼刀在先原则：同时满足双方胜利条件时狼人优先"""
    state = make_state("wolf_first")
    # 杀掉所有狼人
    wolves = find_players_by_role(state, RoleType.WEREWOLF)
    for w in wolves:
        state.kill_player(w.player_id, DeathCause.VOTE_EXILE)
    # 同时杀掉所有村民
    villagers = find_players_by_role(state, RoleType.VILLAGER)
    for v in villagers:
        state.kill_player(v.player_id, DeathCause.WOLF_KILL)

    winner = state.check_victory()
    assert winner == "狼人阵营", f"狼刀在先原则：应狼人获胜，实际: {winner}"
    print("  ✅ 狼刀在先原则")


# ========== 20回合平局测试 ==========

async def test_max_rounds_draw():
    """测试20回合平局（通过引擎运行验证）"""
    import random
    random.seed(99999)

    with patch("config.get_settings", _mock_settings):
        state = GameState.create("draw_test", [1] * 12)
        state.max_rounds = 2  # 缩短到2回合以加速测试

    collector = []

    async def collect(event):
        collector.append(event)

    # 用一个特殊引擎：所有决策都选空/不行动，制造平局
    with patch("config.get_settings", _mock_settings):
        engine = GameEngine(state, collect, ai_agent=None)

    # Monkey-patch 让狼人空刀、女巫不用药、投票平票
    original_wolf = engine._get_ai_wolf_decision
    original_witch = engine._get_ai_witch_decision
    original_vote = engine._get_ai_vote

    async def empty_wolf(wolf_ids):
        return None  # 空刀

    async def empty_witch(pid, victim):
        return False, None  # 不救不毒

    async def scatter_vote(voter_id):
        # 每人投不同的人，制造平票
        alive = state.get_alive_ids()
        targets = [p for p in alive if p != voter_id]
        if targets:
            return targets[voter_id % len(targets)]
        return None

    engine._get_ai_wolf_decision = empty_wolf
    engine._get_ai_witch_decision = empty_witch
    engine._get_ai_vote = scatter_vote

    with patch("config.get_settings", _mock_settings):
        await engine.run()

    assert state.winner == "平局", f"应为平局，实际: {state.winner}"
    print("  ✅ 最大回合平局（2回合测试）")


# ========== 主函数 ==========

async def main():
    print("=" * 60)
    print("🐺 AI狼人杀 边界情况测试 (T7.10)")
    print("=" * 60)

    passed = 0
    failed = 0

    tests = [
        ("夜晚结算", [
            test_peaceful_night_guard_block,
            test_empty_knife,
            test_witch_save,
            test_witch_poison,
            test_guard_cannot_block_poison,
            test_hunter_trigger_on_wolf_kill,
            test_hunter_poisoned_cannot_shoot,
            test_wolf_kill_and_poison_same_target,
        ]),
        ("胜利条件", [
            test_victory_all_wolves_dead,
            test_victory_gods_eliminated,
            test_victory_villagers_eliminated,
            test_wolf_first_principle,
        ]),
    ]

    for group_name, test_funcs in tests:
        print(f"\n🔍 {group_name}测试：")
        for test_func in test_funcs:
            try:
                test_func()
                passed += 1
            except Exception as e:
                print(f"  ❌ {test_func.__doc__}: {e}")
                failed += 1

    # 异步测试
    print(f"\n🔍 特殊场景测试：")
    try:
        await test_max_rounds_draw()
        passed += 1
    except Exception as e:
        print(f"  ❌ 最大回合平局: {e}")
        failed += 1

    # 总结
    print(f"\n{'=' * 60}")
    total = passed + failed
    if failed == 0:
        print(f"🎉 T7.10 边界情况测试全部通过！({passed}/{total})")
    else:
        print(f"⚠️ 通过 {passed}/{total}，失败 {failed} 个")
    print("=" * 60)

    # 清理
    shutil.rmtree(_temp_dir, ignore_errors=True)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
