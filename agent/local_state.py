# -*- coding: utf-8 -*-
"""本机持久化状态 helper（同一台电脑自己的状态，不进入 Git）。

存储位置：`%LOCALAPPDATA%\\MaaHappyFish\\state.json`
（LOCALAPPDATA 缺失时回退到用户目录下的 AppData/Local，再退回家目录）。

游戏日定义：游戏每日刷新时间为凌晨 04:00，因此
    game_day = (当前时间 - 4 小时).date()
电脑在 04:00 时刻无需开机或运行，读取时按当前时间惰性计算即可。

JSON 损坏时记录 warning 并安全视为空状态，绝不因计数文件问题中断自动化任务。
写入使用「临时文件 + os.replace」原子替换，避免程序中断产生半个 JSON。
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

_STATE_VERSION = 1
# 海獭摸宝游戏每日上限（仅用于日志展示，不用于拦截任务）
SEA_OTTER_DAILY_LIMIT = 3
# 游戏日刷新偏移：每天 04:00 为新一天
_GAME_DAY_SHIFT = timedelta(hours=4)


def get_current_game_day(now=None):
    """返回当前游戏日（ISO 日期字符串），04:00 为刷新边界。"""
    moment = now or datetime.now()
    return (moment - _GAME_DAY_SHIFT).date().isoformat()


def _state_dir():
    override = os.environ.get("MAAHAPPYFISH_STATE_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        home = Path.home()
        candidate = home / "AppData" / "Local"
        base = str(candidate) if candidate.is_dir() else str(home)
    return Path(base) / "MaaHappyFish"


def _state_file_path():
    return _state_dir() / "state.json"


def load_local_state():
    """读取本机状态；文件缺失返回空结构，损坏时 warning 并返回空结构。"""
    path = _state_file_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict):
            raise ValueError("state root is not a dict")
        return state
    except FileNotFoundError:
        return {"version": _STATE_VERSION}
    except Exception as e:
        print(f"[本地状态] 状态文件损坏或不可读，已按空状态继续: {e}", flush=True)
        return {"version": _STATE_VERSION}


def save_local_state(state):
    """原子写入本机状态；失败仅 warning，不抛出。"""
    path = _state_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f"[本地状态] 状态文件写入失败（不影响自动化任务）: {e}", flush=True)
        return False


def get_sea_otter_daily_count(now=None):
    """读取海獭摸宝今日完整运行次数；跨游戏日时惰性清零并落盘新游戏日。"""
    game_day = get_current_game_day(now)
    state = load_local_state()
    sea_otter = state.get("sea_otter")
    if not isinstance(sea_otter, dict):
        return 0
    if sea_otter.get("game_day") != game_day:
        sea_otter["game_day"] = game_day
        sea_otter["completed_runs"] = 0
        state["version"] = state.get("version", _STATE_VERSION)
        state["sea_otter"] = sea_otter
        save_local_state(state)
        return 0
    try:
        return max(0, int(sea_otter.get("completed_runs", 0)))
    except (TypeError, ValueError):
        return 0


def record_sea_otter_completed_run(now=None):
    """记录一次完整正常结束，返回 (最新次数, 每日上限)。"""
    game_day = get_current_game_day(now)
    state = load_local_state()
    sea_otter = state.get("sea_otter")
    if not isinstance(sea_otter, dict) or sea_otter.get("game_day") != game_day:
        sea_otter = {
            "game_day": game_day,
            "completed_runs": 0,
            "last_completed_at": None,
        }
    sea_otter["completed_runs"] = max(0, int(sea_otter.get("completed_runs", 0) or 0)) + 1
    sea_otter["last_completed_at"] = (now or datetime.now()).isoformat(timespec="seconds")
    state["version"] = state.get("version", _STATE_VERSION)
    state["sea_otter"] = sea_otter
    save_local_state(state)
    return sea_otter["completed_runs"], SEA_OTTER_DAILY_LIMIT
