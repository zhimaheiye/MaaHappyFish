"""好友摸宝留言箱的纯决策。

只根据已经识别出的文字决定点哪一个框。不认识的付费词、绿色勾选和「添加」都不在可选按钮里。
"""

MESSAGE_CATEGORIES = (
    "system",
    "friend_request",
    "baby_visit",
    "coupon",
    "other",
)
POLICIES = ("skip", "accept", "reject")
BUTTON_WORDS = ("同意", "拒绝", "查看", "删除")
PAY_WORDS = ("开心宝", "购买", "VIP", "广告")
STRICT_CATEGORIES = ("friend_request", "baby_visit", "coupon")
# 2026-10-02 留言箱桥接的第 3 页签。target [489, 41, 8, 8] 的中心。
STAR_TAB_CENTER = (493, 45)


def default_message_policy():
    return {key: "skip" for key in MESSAGE_CATEGORIES}


def normalize_policy(category, policy):
    if category not in MESSAGE_CATEGORIES or policy not in POLICIES:
        return None
    return policy


def _center(box):
    return int(box[0]) + int(box[2]) // 2, int(box[1]) + int(box[3]) // 2


def _cx(item):
    return _center(item["box"])[0]


def _cy(item):
    return _center(item["box"])[1]


def classify_message_text(text):
    compact = "".join(str(text).split())
    if any(key in compact for key in ("好友申请", "加你为好友", "加好友申请")):
        return "friend_request"
    if "鱼宝宝" in compact or "拜访邀请" in compact:
        return "baby_visit"
    if "折扣券" in compact or "优惠券" in compact:
        return "coupon"
    if any(key in compact for key in ("系统通知", "系统消息", "悬赏")):
        return "system"
    return "other"


def _wanted_words(category, policy):
    if policy == "accept":
        if category in STRICT_CATEGORIES:
            return ("同意",)
        return ("同意", "查看")
    if policy == "reject":
        if category in STRICT_CATEGORIES:
            return ("拒绝",)
        return ("拒绝", "删除")
    return ()


def message_rows(items):
    buttons = []
    for item in items:
        text = str(item.get("text", "")).strip()
        box = item.get("box")
        if text not in BUTTON_WORDS or not box or len(box) != 4:
            continue
        cx, cy = _center(box)
        if cx < 800 or cy < 170:
            continue
        buttons.append({"text": text, "box": [int(value) for value in box]})
    buttons.sort(key=_cy)
    rows = []
    for button in buttons:
        cy = _cy(button)
        row = next((candidate for candidate in rows if abs(candidate["cy"] - cy) <= 36), None)
        if row is None:
            row = {"cy": cy, "buttons": [], "texts": []}
            rows.append(row)
        row["buttons"].append(button)
    for row in rows:
        y0, y1 = row["cy"] - 45, row["cy"] + 55
        for item in items:
            text = str(item.get("text", "")).strip()
            box = item.get("box")
            if not text or not box or len(box) != 4:
                continue
            cx, cy = _center(box)
            if text in BUTTON_WORDS and cx >= 800:
                continue
            if y0 <= cy <= y1 and cx < 900:
                row["texts"].append(text)
        row["blob"] = "".join(row["texts"])
        row["category"] = classify_message_text(row["blob"])
    return rows


def left_category_tabs(items):
    tabs = []
    for item in items:
        text = str(item.get("text", "")).strip()
        box = item.get("box")
        if not text or not box or len(box) != 4:
            continue
        cx, cy = _center(box)
        if not (170 <= cy <= 640 and cx < 230):
            continue
        if not any(key in text for key in ("系统", "好友", "鱼宝", "拜访", "折扣", "优惠", "申请")):
            continue
        tabs.append({
            "text": text,
            "box": [int(value) for value in box],
            "category": classify_message_text(text),
        })
    return tabs


def choose_message_click(items, policy, opened_tabs, acted_rows):
    """返回一个点击，或 None。付费行、绿色勾选和「添加」不会被选中。"""
    safe_policy = default_message_policy()
    for key, value in (policy or {}).items():
        if key in safe_policy and value in POLICIES:
            safe_policy[key] = value
    rows = message_rows(items)
    visible = {row["category"] for row in rows if row["blob"]}
    for tab in left_category_tabs(items):
        category = tab["category"]
        if safe_policy.get(category, "skip") == "skip" or category in visible:
            continue
        key = ("tab", tab["text"])
        if key in opened_tabs:
            continue
        return {
            "kind": "tab",
            "box": tab["box"],
            "category": category,
            "label": tab["text"],
            "key": key,
        }
    for row in rows:
        if any(word in row["blob"] for word in PAY_WORDS):
            continue
        if row["category"] == "other" and not row["blob"].strip():
            continue
        words = _wanted_words(row["category"], safe_policy.get(row["category"], "skip"))
        button = next(
            (item for word in words for item in row["buttons"] if item["text"] == word),
            None,
        )
        if button is None:
            continue
        key = ("row", row["category"], button["text"], row["blob"][:12], row["cy"] // 40)
        if key in acted_rows:
            continue
        return {
            "kind": "button",
            "box": button["box"],
            "category": row["category"],
            "label": button["text"],
            "key": key,
        }
    return None
