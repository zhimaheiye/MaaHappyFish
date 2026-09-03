"""
MaaHappyFish 共享运行时状态容器
用于解耦 CustomRecognition 与 CustomAction 之间的状态依赖，避免循环引用。
"""

friend_gem_state = {
    "attempts": 0,
    "max_attempts": 12,
    "current_friend_index": 1,
    "bubble_miss_count": 0,
    "max_bubble_misses": 8,
}