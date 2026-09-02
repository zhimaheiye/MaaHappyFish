import json
import math
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.define import RectType

timer_state = {
    "task_id": None,
    "last_feed_time": 0.0,
    "interval_seconds": 600.0,
}

duty_state = {
    "mode": "IDLE",
    "active_start_time": 0.0,
    "idle_start_time": 0.0,
    "idle_interval": 0.0,
    "active_duration": 120.0,
    "is_inited": False,
    "last_ui_log_time": 0.0,      # 上次向 MFA UI 注入 focus 消息的时间戳
    "ui_log_interval": 60.0,      # UI 播报最小间隔（秒）
}

screen_stall_state = {
    "task_id": None,
    "last_sample": None,
    "last_change_time": 0.0,
}

open_shell_loop_state = {
    "task_id": None,
    "completed": 0,
    "target": 1,
}


def _make_screen_sample(image: np.ndarray, sample_step: int) -> np.ndarray:
    if image is None or image.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)

    sample_step = max(1, sample_step)
    sample = image[::sample_step, ::sample_step]
    if sample.ndim == 3:
        sample = sample[..., :3]
    return sample.astype(np.uint8, copy=True)


def _screen_changed(previous: np.ndarray, current: np.ndarray, threshold: float) -> bool:
    if previous.shape != current.shape:
        return True

    difference = np.abs(current.astype(np.int16) - previous.astype(np.int16))
    return float(difference.mean()) > threshold


@AgentServer.custom_recognition("CheckScreenStallReco")
class CheckScreenStallReco(CustomRecognition):

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global screen_stall_state

        param = argv.custom_recognition_param
        if isinstance(param, str) and param:
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        elif not isinstance(param, dict):
            param = {}

        static_seconds = max(5.0, float(param.get("static_seconds", 30)))
        difference_threshold = max(0.0, float(param.get("difference_threshold", 0.5)))
        sample_step = max(1, int(param.get("sample_step", 8)))
        task_id = argv.task_detail.task_id
        now = time.monotonic()
        sample = _make_screen_sample(argv.image, sample_step)

        if screen_stall_state["task_id"] != task_id:
            screen_stall_state = {
                "task_id": task_id,
                "last_sample": sample,
                "last_change_time": now,
            }
            return None

        previous = screen_stall_state["last_sample"]
        if previous is None or _screen_changed(previous, sample, difference_threshold):
            screen_stall_state["last_sample"] = sample
            screen_stall_state["last_change_time"] = now
            return None

        screen_stall_state["last_sample"] = sample
        stalled_for = now - screen_stall_state["last_change_time"]
        if stalled_for < static_seconds:
            return None

        print(
            f"[运行保护] 画面已连续 {int(stalled_for)} 秒无明显变化，正在停止任务。",
            flush=True,
        )
        return (0, 0, 10, 10)

@AgentServer.custom_recognition("CalcFishingFoodReco")
class CalcFishingFoodReco(CustomRecognition):

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        param = argv.custom_recognition_param
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        elif not isinstance(param, dict):
            param = {}

        try:
            capacity = float(param.get("capacity", 100))
            current_duration = float(param.get("current_duration", 120))
            target_hour = int(param.get("target_hour", 8))

            now = datetime.now()
            target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)

            diff_minutes = (target_time - now).total_seconds() / 60.0
            total_hours = diff_minutes / 60.0

            if current_duration <= 0:
                extra_food = 0
                extra_mins = diff_minutes
                ui_msg = f"[鱼食预算] 挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 存粮为0，请及时为海星喂食！"
            elif diff_minutes <= current_duration:
                extra_food = 0
                bags = 0
                ui_msg = f"[鱼食预算] 挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 存粮充足(可用 {int(current_duration)} 分钟)，无需补充"
            else:
                rate_per_min = capacity / current_duration
                extra_mins = max(0.0, diff_minutes - current_duration)
                extra_food = int(round(extra_mins * rate_per_min + 0.4999))
                bags = math.ceil(extra_food / 30.0)
                ui_msg = f"[鱼食预算] 挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 缺口 {int(extra_mins)}分钟 | 需备鱼食: {extra_food}粒 (约 {bags}袋)"

            print("=" * 55, flush=True)
            print("[鱼食预算] 海星挂机鱼食规划结果:", flush=True)
            print(f"[鱼食预算] 当前时间: {now.strftime('%H:%M')} | 计划挂机至: {target_time.strftime('%H:%M')} (共 {total_hours:.1f} 小时)", flush=True)
            print(f"[鱼食预算] 当前存粮可用: {int(current_duration)} 分钟 | 缺口时长: {max(0, int(diff_minutes - current_duration))} 分钟", flush=True)
            print(f"[鱼食预算] 至少需额外准备/购买: {extra_food} 粒 ~= {bags} 袋 (30粒/袋)", flush=True)
            print("=" * 55, flush=True)

            focus_dict = {
                "Node.Action.Succeeded": ui_msg
            }

            try:
                context.override_pipeline({
                    "CollectFishTask": {
                        "focus": focus_dict
                    }
                })
            except Exception:
                pass

        except Exception as e:
            print(f"[鱼食预算] 计算异常: {e}", flush=True)

        return (0, 0, 10, 10)

@AgentServer.custom_recognition("CheckStarfishTimerReco")
class CheckStarfishTimerReco(CustomRecognition):

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global timer_state

        param = argv.custom_recognition_param
        if isinstance(param, str) and param:
            try:
                p = json.loads(param)
                if "interval" in p:
                    timer_state["interval_seconds"] = float(p["interval"])
            except Exception:
                pass

        interval = timer_state["interval_seconds"]
        task_id = argv.task_detail.task_id
        is_new_task = timer_state["task_id"] != task_id
        now = time.time()

        if is_new_task:
            timer_state["task_id"] = task_id
            timer_state["last_feed_time"] = now

        if interval <= 0:
            return None

        elapsed = now - timer_state["last_feed_time"]

        if is_new_task or elapsed >= interval:
            mins = int(interval / 60) if interval >= 60 else int(interval)
            unit = "分钟" if interval >= 60 else "秒"
            print("=" * 55, flush=True)
            if is_new_task:
                print("[海星喂食] 任务已启动，先执行一次自动补充鱼食。", flush=True)
            else:
                print(f"[海星喂食] 定时已达! 距上次喂食 {int(elapsed)} 秒 (设定间隔: {int(interval)} 秒)", flush=True)
            print("[海星喂食] 正在触发海星自动补充鱼食...", flush=True)
            print("=" * 55, flush=True)
            timer_state["last_feed_time"] = now
            feed_msg = (
                "[海星喂食] 任务已启动，正在先补充一次鱼食..."
                if is_new_task
                else f"[海星喂食] 设定间隔({mins}{unit})已到达，正在自动补充鱼食..."
            )
            try:
                context.override_pipeline({
                    "TriggerStarfishFeed": {
                        "focus": {
                            "Node.Action.Succeeded": feed_msg
                        }
                    }
                })
            except Exception:
                pass
            return (0, 0, 10, 10)

        return None


@AgentServer.custom_recognition("CheckDutyCycleReco")
class CheckDutyCycleReco(CustomRecognition):

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global duty_state

        param = argv.custom_recognition_param
        if isinstance(param, str) and param:
            try:
                p = json.loads(param)
                if "idle_interval" in p:
                    duty_state["idle_interval"] = float(p["idle_interval"])
                if "active_duration" in p:
                    duty_state["active_duration"] = float(p["active_duration"])
            except Exception:
                pass

        idle_interval = duty_state["idle_interval"]
        active_duration = duty_state["active_duration"]

        now_time = time.time()
        now_dt = datetime.now()

        # 首次初始化
        if not duty_state["is_inited"]:
            duty_state["is_inited"] = True
            if idle_interval > 0:
                duty_state["mode"] = "IDLE"
                duty_state["idle_start_time"] = now_time
                duty_state["last_ui_log_time"] = now_time   # 初始播报时间，60 秒内静默
                target_dt = now_dt + timedelta(seconds=idle_interval)
                mins = int(idle_interval / 60) if idle_interval >= 60 else int(idle_interval)
                unit = "分钟" if idle_interval >= 60 else "秒"
                msg = f"[巡检收宝] 待机休眠中（间隔 {mins}{unit}），预计 {target_dt.strftime('%H:%M:%S')} 开启首轮收宝"
                print("-" * 55, flush=True)
                print(f"[巡检收宝] 任务启动, 默认进入【待机休眠】模式 (间隔 {mins} {unit})", flush=True)
                print(f"[巡检收宝] 预计在 {target_dt.strftime('%H:%M:%S')} 开启第一轮收宝巡检", flush=True)
                print("-" * 55, flush=True)
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Action.Succeeded": msg
                            }
                        }
                    })
                except Exception:
                    pass
                time.sleep(1)
                return (0, 0, 10, 10)
            else:
                duty_state["mode"] = "ACTIVE"
                duty_state["active_start_time"] = now_time
                msg = "[巡检收宝] 模式:【持续实时】，全天候不间断监控鱼缸收宝！"
                print("-" * 55, flush=True)
                print(msg, flush=True)
                print("-" * 55, flush=True)
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Action.Succeeded": msg
                            }
                        }
                    })
                except Exception:
                    pass
                return (0, 0, 10, 10)

        # 如果是持续实时模式
        if idle_interval <= 0:
            return None

        if duty_state["mode"] == "ACTIVE":
            elapsed_active = now_time - duty_state["active_start_time"]
            if elapsed_active >= active_duration:
                duty_state["mode"] = "IDLE"
                duty_state["idle_start_time"] = now_time
                duty_state["last_ui_log_time"] = now_time
                target_dt = now_dt + timedelta(seconds=idle_interval)
                mins = int(idle_interval / 60) if idle_interval >= 60 else int(idle_interval)
                unit = "分钟" if idle_interval >= 60 else "秒"
                msg = f"[巡检收宝] 本轮收宝完成！进入待机休眠，预计 {target_dt.strftime('%H:%M:%S')} 开始下一轮"
                print("-" * 55, flush=True)
                print(f"[巡检收宝] 本轮 {int(active_duration)} 秒密集收宝完成!", flush=True)
                print(f"[巡检收宝] 进入休眠等待, 预计在 {target_dt.strftime('%H:%M:%S')} 开启下一轮...", flush=True)
                print("-" * 55, flush=True)
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Action.Succeeded": msg
                            }
                        }
                    })
                except Exception:
                    pass
                return (0, 0, 10, 10)
            else:
                return None

        elif duty_state["mode"] == "IDLE":
            elapsed_idle = now_time - duty_state["idle_start_time"]
            if elapsed_idle >= idle_interval:
                duty_state["mode"] = "ACTIVE"
                duty_state["active_start_time"] = now_time
                duty_state["last_ui_log_time"] = now_time
                target_dt = now_dt + timedelta(seconds=active_duration)
                msg = f"[巡检收宝] 休眠结束！开始收宝，本轮持续至 {target_dt.strftime('%H:%M:%S')}"
                print("=" * 55, flush=True)
                print(f"[巡检收宝] 休眠结束! 现在开始收宝!", flush=True)
                print(f"[巡检收宝] 本轮密集收宝持续至 {target_dt.strftime('%H:%M:%S')}", flush=True)
                print("=" * 55, flush=True)
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Action.Succeeded": msg
                            }
                        }
                    })
                except Exception:
                    pass
                return (0, 0, 10, 10)
            else:
                # 节流：每 ui_log_interval 秒才更新一次 UI 播报，其余时间静默
                since_last_log = now_time - duty_state["last_ui_log_time"]
                if since_last_log >= duty_state["ui_log_interval"]:
                    duty_state["last_ui_log_time"] = now_time
                    remaining = idle_interval - elapsed_idle
                    wake_dt = now_dt + timedelta(seconds=remaining)
                    mins = int(idle_interval / 60) if idle_interval >= 60 else int(idle_interval)
                    unit = "分钟" if idle_interval >= 60 else "秒"
                    msg = f"[巡检收宝] 待机休眠中（间隔 {mins}{unit}），预计 {wake_dt.strftime('%H:%M:%S')} 开始收宝"
                    print(f"[巡检收宝] 休眠中 | 剩余 {int(remaining)} 秒 | 预计 {wake_dt.strftime('%H:%M:%S')} 开始收宝", flush=True)
                    try:
                        context.override_pipeline({
                            "CheckDutyCycle": {
                                "focus": {
                                    "Node.Action.Succeeded": msg
                                }
                            }
                        })
                    except Exception:
                        pass
                else:
                    # 静默期间清空 focus，避免重复播报
                    try:
                        context.override_pipeline({"CheckDutyCycle": {"focus": {}}})
                    except Exception:
                        pass
                time.sleep(2)
                return (0, 0, 10, 10)


@AgentServer.custom_recognition("CheckOpenShellLoopReco")
class CheckOpenShellLoopReco(CustomRecognition):

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global open_shell_loop_state

        param = argv.custom_recognition_param
        if isinstance(param, str) and param:
            try:
                param = json.loads(param)
            except Exception:
                param = {}
        elif not isinstance(param, dict):
            param = {}

        try:
            target_count = max(1, int(param.get("target_count", 1)))
        except (TypeError, ValueError):
            target_count = 1

        task_id = argv.task_detail.task_id
        if open_shell_loop_state["task_id"] != task_id:
            open_shell_loop_state = {
                "task_id": task_id,
                "completed": 0,
                "target": target_count,
            }

        open_shell_loop_state["target"] = target_count
        open_shell_loop_state["completed"] += 1
        completed = open_shell_loop_state["completed"]

        if completed < target_count:
            print(f"[开贝壳] 已完成 {completed}/{target_count} 轮，继续下一轮", flush=True)
            return (0, 0, 10, 10)
        else:
            print(f"[开贝壳] 已完成 {completed}/{target_count} 轮，任务完成", flush=True)
            return None
