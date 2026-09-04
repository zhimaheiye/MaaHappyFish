import sys
sys.path.insert(0, ".")
import agent.runtime_state as rs
from agent.my_action import (
    InitFriendGemStateAction,
    RecordFriendGemAttemptAction,
    ResetFriendGemAttemptsAction,
    RecordFriendGemBubbleMissAction,
    StepFriendGemIndexAction,
)
from agent.my_reco import (
    CheckFriendGemLimitReco,
    CheckFriendGemBubbleMissLimitReco,
)

init_act = InitFriendGemStateAction()
attempt_act = RecordFriendGemAttemptAction()
reset_act = ResetFriendGemAttemptsAction()
miss_act = RecordFriendGemBubbleMissAction()
step_act = StepFriendGemIndexAction()
limit_reco = CheckFriendGemLimitReco()
miss_reco = CheckFriendGemBubbleMissLimitReco()

# Test 1: Init
init_act.run(None, None)
assert rs.friend_gem_state["attempts"] == 0
assert rs.friend_gem_state["bubble_miss_count"] == 0
print("Test 1 Init: PASS")

# Test 2: Miss 3 times
for i in range(3):
    miss_act.run(None, None)
assert rs.friend_gem_state["bubble_miss_count"] == 3
assert rs.friend_gem_state["attempts"] == 0
assert miss_reco.analyze(None, None) is None
print("Test 2 Miss 3 times: PASS")

# Test 3: Hit 1 bubble -> resets miss count
attempt_act.run(None, None)
assert rs.friend_gem_state["attempts"] == 1
assert rs.friend_gem_state["bubble_miss_count"] == 0
print("Test 3 Hit bubble resets miss count: PASS")

# Test 4: Miss 8 times -> triggers miss limit
for i in range(8):
    miss_act.run(None, None)
assert rs.friend_gem_state["bubble_miss_count"] == 8
res = miss_reco.analyze(None, None)
assert res == (0, 0, 10, 10), f"Expected limit trigger, got {res}"
print("Test 4 Miss limit triggered: PASS")

# Test 5: Next friend resets all and steps index
step_act.run(None, None)
reset_act.run(None, None)
assert rs.friend_gem_state["attempts"] == 0
assert rs.friend_gem_state["bubble_miss_count"] == 0
assert rs.friend_gem_state["current_friend_index"] == 2
print("Test 5 Next friend step and reset: PASS")

print("\nALL 5 STATE MACHINE UNIT TESTS PASSED 100%!")