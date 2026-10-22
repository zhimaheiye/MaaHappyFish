"""Top-level Tasker events bound transient daily state to the actual queue task."""
from maa.event_sink import NotificationType
from maa.tasker import TaskerEventSink

try:
    from runtime_state import daily_routine_state, hangup_schedule_state, green_wild_daily_state
except ImportError:
    from agent.runtime_state import daily_routine_state, hangup_schedule_state, green_wild_daily_state


def clear_daily_context(reason):
    if daily_routine_state.get("active"):
        print(f"[日常收尾] {reason}；清理未完成上下文，不记录完成。", flush=True)
        daily_routine_state["outcome"] = "INTERRUPTED"
    daily_routine_state.update(active=False, queue=[])
    green_wild_daily_state["pending_buy_fish"] = False
    hangup_schedule_state["resume_stack"] = []


class DailyTaskLifecycleSink(TaskerEventSink):
    def on_tasker_task(self, tasker, noti_type, detail):
        # Context.run_task uses context events, not a new top-level queue task.
        if noti_type == NotificationType.Starting:
            clear_daily_context("新的队列任务开始")
        elif noti_type in (NotificationType.Succeeded, NotificationType.Failed):
            clear_daily_context("队列任务已结束或停止")
