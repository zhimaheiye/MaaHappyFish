import json
import math
from datetime import datetime, timedelta

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context


@AgentServer.custom_action("CalcFishingFoodAction")
class CalcFishingFoodAction(CustomAction):

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = argv.custom_action_param
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
                ui_msg = f"[鱼食预算] 计划挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 存粮为0，请及时为海星喂食！"
            elif extra_mins <= 0:
                extra_food = 0
                bags = 0
                ui_msg = f"[鱼食预算] 计划挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 存粮充足(剩余 {int(current_duration)} 分钟)，无需补充"
            else:
                rate_per_min = capacity / current_duration
                extra_mins = max(0.0, diff_minutes - current_duration)
                extra_food = int(round(extra_mins * rate_per_min + 0.4999))
                bags = math.ceil(extra_food / 30.0)
                ui_msg = f"[鱼食预算] 挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 缺口 {int(extra_mins)}分钟 | 需备鱼食: {extra_food}粒 (约 {bags}袋)"

            print("=" * 55, flush=True)
            print("[鱼食预算] 萌海星挂机鱼食规划结果:", flush=True)
            print(f"[鱼食预算] 当前时间: {now.strftime('%H:%M')} | 计划挂机至: {target_time.strftime('%H:%M')} (共 {total_hours:.1f} 小时)", flush=True)
            print(f"[鱼食预算] 当前存粮可用: {int(current_duration)} 分钟 | 缺口时长: {max(0, int(extra_mins))} 分钟", flush=True)
            print(f"[鱼食预算] 至少需额外准备/购买: {extra_food} 粒 ~= {bags} 袋 (30粒/袋)", flush=True)
            print(f"[鱼食预算] 请确保背包备足鱼食, 海星将按设定间隔自动补充", flush=True)
            print("=" * 55, flush=True)

            try:
                context.override_pipeline({
                    "LogFoodBudget": {
                        "focus": {
                            "Node.Action.Succeeded": ui_msg
                        }
                    }
                })
            except Exception:
                pass

        except Exception as e:
            print(f"[鱼食预算] 计算异常: {e}", flush=True)

        return True