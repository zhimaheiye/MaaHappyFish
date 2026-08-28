import json
import math
import time
from datetime import datetime, timedelta
from typing import Optional
from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.define import RectType

timer_state = {
    "last_feed_time": time.time(),
    "interval_seconds": 600.0,
    "is_inited": False
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
            print("[鱼食预算] 萌海星挂机鱼食规划结果:", flush=True)
            print(f"[鱼食预算] 当前时间: {now.strftime('%H:%M')} | 计划挂机至: {target_time.strftime('%H:%M')} (共 {total_hours:.1f} 小时)", flush=True)
            print(f"[鱼食预算] 当前存粮可用: {int(current_duration)} 分钟 | 缺口时长: {max(0, int(diff_minutes - current_duration))} 分钟", flush=True)
            print(f"[鱼食预算] 至少需额外准备/购买: {extra_food} 粒 ~= {bags} 袋 (30粒/袋)", flush=True)
            print("=" * 55, flush=True)

            focus_dict = {
                "Node.Action.Starting": ui_msg,
                "Node.Action.Succeeded": ui_msg,
                "Node.PipelineNode.Succeeded": ui_msg,
                "Node.Recognition.Succeeded": ui_msg,
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

        if not timer_state["is_inited"]:
            timer_state["last_feed_time"] = time.time()
            timer_state["is_inited"] = True

        param = argv.custom_recognition_param
        if isinstance(param, str) and param:
            try:
                p = json.loads(param)
                if "interval" in p:
                    timer_state["interval_seconds"] = float(p["interval"])
            except Exception:
                pass

        interval = timer_state["interval_seconds"]
        if interval <= 0:
            return None

        now = time.time()
        elapsed = now - timer_state["last_feed_time"]

        if elapsed >= interval:
            print("=" * 55, flush=True)
            print(f"[海星喂食] 定时已达! 距上次喂食 {int(elapsed)} 秒 (设定间隔: {int(interval)} 秒)", flush=True)
            print("[海星喂食] 正在触发萌海星自动补充鱼食...", flush=True)
            print("=" * 55, flush=True)
            timer_state["last_feed_time"] = time.time()
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
                print("-" * 55, flush=True)
                print(f"[巡检收宝] 任务启动, 默认进入【待机休眠】模式 (间隔 {mins} {unit})", flush=True)
                print(f"[巡检收宝] 预计在 {target_dt.strftime('%H:%M:%S')} 开启第一轮收宝巡检", flush=True)
                print("-" * 55, flush=True)
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Recognition.Succeeded": f"[巡检收宝] 待机休眠中（间隔 {mins} {unit}），预计 {target_dt.strftime('%H:%M:%S')} 开始收宝"
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
                print("-" * 55, flush=True)
                print("[巡检收宝] 【持续实时】收宝模式, 全天候不间断监控鱼缸!", flush=True)
                print("-" * 55, flush=True)
                return None

        # 如果是持续实时模式
        if idle_interval <= 0:
            return None

        if duty_state["mode"] == "ACTIVE":
            elapsed_active = now_time - duty_state["active_start_time"]
            if elapsed_active >= active_duration:
                duty_state["mode"] = "IDLE"
                duty_state["idle_start_time"] = now_time
                target_dt = now_dt + timedelta(seconds=idle_interval)
                mins = int(idle_interval / 60) if idle_interval >= 60 else int(idle_interval)
                unit = "分钟" if idle_interval >= 60 else "秒"
                print("-" * 55, flush=True)
                print(f"[巡检收宝] 本轮 {int(active_duration)} 秒密集收宝完成!", flush=True)
                print(f"[巡检收宝] 进入休眠等待, 预计在 {target_dt.strftime('%H:%M:%S')} 开启下一轮...", flush=True)
                print("-" * 55, flush=True)
                # 注入 focus 让 MFA 日志面板也显示
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Recognition.Succeeded": f"[巡检收宝] 本轮收宝完成！待机休眠中，预计 {target_dt.strftime('%H:%M:%S')} 开始下一轮"
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
                print("=" * 55, flush=True)
                print(f"[巡检收宝] 休眠结束! 现在开始收宝!", flush=True)
                print(f"[巡检收宝] 本轮密集收宝持续至 {target_dt.strftime('%H:%M:%S')}", flush=True)
                print("=" * 55, flush=True)
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Recognition.Failed": f"[巡检收宝] 休眠结束！开始收宝，本轮持续至 {target_dt.strftime('%H:%M:%S')}"
                            }
                        }
                    })
                except Exception:
                    pass
                return None
            else:
                # 节流：每 ui_log_interval 秒才更新一次 UI 播报，其余时间静默
                since_last_log = now_time - duty_state["last_ui_log_time"]
                if since_last_log >= duty_state["ui_log_interval"]:
                    duty_state["last_ui_log_time"] = now_time
                    remaining = idle_interval - elapsed_idle
                    wake_dt = now_dt + timedelta(seconds=remaining)
                    mins = int(idle_interval / 60) if idle_interval >= 60 else int(idle_interval)
                    unit = "分钟" if idle_interval >= 60 else "秒"
                    print(f"[巡检收宝] 休眠中 | 剩余 {int(remaining)} 秒 | 预计 {wake_dt.strftime('%H:%M:%S')} 开始收宝", flush=True)
                    try:
                        context.override_pipeline({
                            "CheckDutyCycle": {
                                "focus": {
                                    "Node.Recognition.Succeeded": f"[巡检收宝] 待机休眠中（间隔 {mins} {unit}），预计 {wake_dt.strftime('%H:%M:%S')} 开始收宝"
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