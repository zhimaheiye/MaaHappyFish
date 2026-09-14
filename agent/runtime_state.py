"""
MaaHappyFish 共享运行时状态容器
用于解耦 CustomRecognition 与 CustomAction 之间的状态依赖，避免循环引用。
"""

friend_gem_state = {
    "attempts": 0,
    "max_attempts": 30,
    "current_friend_index": 1,
    "bubble_miss_count": 0,
    "max_bubble_misses": 12,
}

manatee_state = {
    "return_mode": "standalone",
    "last_feed_count": 0,
}

sea_otter_gem_state = {
    "current_side": "left",
    "total_harvests": 0,
    "max_harvests": 200,
    "consecutive_exhausted": 0,
    "max_consecutive_exhausted": 30,
    "completion_reason": None,
    "current_task_id": None,
}

BAND_FISH_TARGETS = {
    1: "不想上课",
    2: "一只胖梨",
    4: "扶摇",
    5: "游来游去",
}

band_fish_state = {
    "status": None,  # "DONE" | "READY_TO_PERFORM" | "NEED_INVITE" | "UNKNOWN"
    "slots": {
        1: {"target": "不想上课", "state": "EMPTY"},
        2: {"target": "一只胖梨", "state": "EMPTY"},
        4: {"target": "扶摇", "state": "EMPTY"},
        5: {"target": "游来游去", "state": "EMPTY"},
    },
    "current_invite_slot": None,
    "performance_finished": False,
}

romantic_house_state = {
    "likes": 0,
    "max_likes": 10,
    "status": "IDLE",
}

daily_routine_state = {
    "active": False,
    "step": "INIT",  # "FREE_GIFT" | "REINDEER_FISH" | "GOLD_SHELL_COUPON" | "BAND_FISH" | "GOLDEN_DOLPHIN" | "FISHING" | "GEM_GIFT_BOX" | "ROMANTIC_HOUSE" | "ALL_DONE"
    "queue": [],     # 待执行的后续子任务序列
    "tasks": {
        "FreeGift": {"status": "IDLE"},
        "ReindeerFish": {"status": "IDLE"},
        "GoldShellCoupon": {"status": "IDLE"},
        "BandFish": {"status": "IDLE", "stage": "PASS1"},
        "GoldenDolphin": {"status": "IDLE"},
        "Fishing": {"status": "IDLE"},
        "GemGiftBox": {"status": "IDLE"},
        "RomanticHouse": {"status": "IDLE"},
    },
}

fishing_state = {
    "current_task_id": None,
    "cast_count": 0,
    "max_casts": 0,  # 0 = 不限次数，直到鱼饵耗尽/无法继续
    "bite_mode": "ordinary",  # ordinary = 早期形态加速；special = 旧版严格形态
    "force_ordinary_bait": False,
    "fish_caught": 0,
    "status": "IDLE",  # "DONE" | "NO_STAMINA"
}

golden_dolphin_state = {
    "status": "IDLE",  # "READY_TO_PLAY" | "NEXT_ROUND" | "DONE" | "NO_STAMINA" | "FAILED"
    "completed_rounds": 0,
    "max_rounds": 3,
    "reward_priority": "xp",  # "xp" | "heart" | "gem" | "coin"
}

shake_game_state = {
    "status": "IDLE",  # "IDLE" | "READY_TO_PLAY" | "PLAYING" | "SETTLEMENT" | "NEXT_ROUND" | "DONE" | "NO_STAMINA" | "FAILED"
    "completed_rounds": 0,
    "max_rounds": 3,
}

gem_collect_state = {
    "mode": "IMAGE",  # "IMAGE" | "SHAKE"
}

mobile_ad_state = {
    "completed_cycles": 0,
    "max_cycles": 3,
    "reward_recorded": False,
    "log_tag": "手机看广告",
    "stop_count": 0,
    "max_stops_per_ad": 5,
}

collect_fish_state = {
    "tank_mode": "single",            # "single" | "dual"
    "switch_interval_sec": 120.0,     # 双缸切换间隔（秒）
    "current_tank": 1,                # 当前所在或预期的鱼缸编号 (1 或 2)
    "dual_start_time": 0.0,           # 双缸轮换正式 t0（monotonic 秒）
    "last_switch_slot": -1,           # 上次执行切缸的 slot
    "is_inited": False,               # 是否已完成启动归一与首喂
    "task_id": None,                  # 当前任务 ID
    "switch_retry_count": 0,          # 切缸重试次数
    "starfish_entry_retry_count": 0,  # 海星入口连续失败次数
    "pending_target_tank": None,      # 切缸过程中目标鱼缸
    "initial_feed_done": False,       # 启动首轮喂食是否已完成
}

starfish_timer_state = {
    "task_id": None,
    "last_feed_time": 0.0,
    "interval_seconds": 600.0,
    "attempt_in_progress": False,
    "retry_not_before": 0.0,
}
