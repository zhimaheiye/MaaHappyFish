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

sea_otter_gem_state = {
    "current_side": "left",
    "total_harvests": 0,
    "max_harvests": 200,
    "consecutive_exhausted": 0,
    "max_consecutive_exhausted": 30,
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