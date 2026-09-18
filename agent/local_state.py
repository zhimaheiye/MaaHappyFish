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
# MFA 任务说明（task.description）指向的运行时状态 markdown；
# 属于运行时生成物，禁止提交进 Git（已加入 .gitignore）。
SEA_OTTER_STATUS_FILENAME = "sea_otter_status.md"
SEA_OTTER_DAILY_LIMIT = 3
# 海獭摸宝游戏每日上限（仅用于日志展示，不用于拦截任务）
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


def _sea_otter_status_path():
    """状态 markdown 必须位于 resource/runtime/（MFA task.description 按程序目录解析，
    开发环境经 junction、发布包经 install/resource 均可达）。"""
    agent_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(agent_dir, "..", "assets", "resource", "runtime"),
        os.path.join(agent_dir, "..", "resource", "runtime"),
        os.path.abspath(os.path.join("assets", "resource", "runtime")),
    ]
    for d in candidates:
        if os.path.isdir(d):
            return Path(d) / SEA_OTTER_STATUS_FILENAME
    return Path(candidates[0]) / SEA_OTTER_STATUS_FILENAME


def build_sea_otter_status_markdown(now=None):
    """从 state.json（唯一真源）构造 MFA 任务说明 markdown。"""
    game_day = get_current_game_day(now)
    state = load_local_state()
    sea_otter = state.get("sea_otter") if isinstance(state, dict) else None
    if isinstance(sea_otter, dict) and sea_otter.get("game_day") == game_day:
        try:
            count = max(0, int(sea_otter.get("completed_runs", 0)))
        except (TypeError, ValueError):
            count = 0
        last_at = sea_otter.get("last_completed_at") or "尚未有完整运行记录"
    else:
        count = 0
        last_at = "尚未有完整运行记录"

    if count >= SEA_OTTER_DAILY_LIMIT:
        headline = f"今日完整运行：**{count} / {SEA_OTTER_DAILY_LIMIT} 次**（已达到游戏每日上限记录）"
    else:
        headline = f"今日完整运行：**{count} / {SEA_OTTER_DAILY_LIMIT} 次**"

    return (
        "## 海獭摸宝\n\n"
        f"{headline}\n\n"
        f"游戏日：{game_day}  \n"
        "每日 04:00 刷新。\n\n"
        "仅“完整正常结束”的一次任务会 +1；\n"
        "Safety Limit、手动停止、异常中断不计数。\n\n"
        f"上次完整运行：{last_at}\n\n"
        "---\n\n"
        "从海獭寻宝好友列表或好友水族箱启动，在相邻好友间往复切换并自动摸取目标宝石；"
        "到达末位好友后推荐玩家只作跳板。详见日志与功能文档。"
    )


def write_sea_otter_status_markdown(now=None):
    """刷新 MFA 任务说明 markdown；失败仅 warning，不影响自动化。"""
    try:
        path = _sea_otter_status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        content = build_sea_otter_status_markdown(now)
        tmp = path.with_suffix(".md.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
        return path
    except Exception as e:
        print(f"[本地状态] 海獭状态说明写入失败（不影响自动化）: {e}", flush=True)
        return None
