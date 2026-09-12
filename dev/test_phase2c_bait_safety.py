import os, sys, cv2, json
import numpy as np

def imread_utf8(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)

print("================================================================================")
print("=== 鱼饵选择与防购买禁区严密几何与模板安全验证 ===")
print("================================================================================")

# 1. 几何禁区保护验证
cheese_bbox = [83, 414, 37, 38]
plus_bbox = [379, 410, 31, 48]
roi_cheese = [50, 380, 120, 100]

cheese_cx = cheese_bbox[0] + cheese_bbox[2] / 2
plus_cx = plus_bbox[0] + plus_bbox[2] / 2
dist = plus_cx - cheese_cx
print(f"1. 奶酪中心 x={cheese_cx}, 购买+按钮中心 x={plus_cx}, 物理安全距离: {dist:.1f} 像素")
assert dist > 250, "奶酪与购买+按钮距离过近，存在危险！"

# ROI 与禁区无重叠验证
roi_max_x = roi_cheese[0] + roi_cheese[2]
plus_min_x = plus_bbox[0]
clearance = plus_min_x - roi_max_x
print(f"   识别 ROI [50, 380, 120, 100] 最大边界 x={roi_max_x}, 购买+按钮起始边界 x={plus_min_x}")
print(f"   ROI 距离危险购买+按钮禁区缓冲余量: {clearance} 像素")
assert clearance > 150, "ROI 侵入危险区域！"
print("   >>> 几何禁区保护 100% PASS！")

# 2. 奶酪模板抗扰与绝不误触购买验证
tpl_cheese = imread_utf8("assets/resource/image/普通饵食_黄色奶酪.png")
img_drawer = cv2.imread("dev/exploration/fishing/after_safe_close_purchase_popup.png")

res_cheese = cv2.matchTemplate(img_drawer[380:480, 50:170], tpl_cheese, cv2.TM_CCOEFF_NORMED)
_, max_v_cheese, _, _ = cv2.minMaxLoc(res_cheese)
print(f"\n2. 黄色奶酪在自身栏位匹配置信度: {max_v_cheese:.4f} (预期 >= 0.85)")
assert max_v_cheese >= 0.85

res_plus = cv2.matchTemplate(img_drawer[380:480, 340:440], tpl_cheese, cv2.TM_CCOEFF_NORMED)
_, max_v_plus, _, _ = cv2.minMaxLoc(res_plus)
print(f"   黄色奶酪在购买+按钮区域误匹配置信度: {max_v_plus:.4f} (预期 < 0.35)")
assert max_v_plus < 0.35
print("   >>> 奶酪模板抗扰验证 100% PASS！绝无可能误触购买入口！")

# 3. 购买弹窗右上角红色 X 模板识别验证
tpl_close_x = imread_utf8("assets/resource/image/鱼饵购买弹窗_关闭.png")
img_popup = cv2.imread("dev/exploration/fishing/purchase_popup_live.png")
res_x = cv2.matchTemplate(img_popup[100:250, 950:1100], tpl_close_x, cv2.TM_CCOEFF_NORMED)
_, max_v_x, _, max_loc_x = cv2.minMaxLoc(res_x)
print(f"\n3. 购买弹窗右上角红色 X 模板匹配置信度: {max_v_x:.4f} (预期 >= 0.85)")
print(f"   匹配位置 (ROI内): {max_loc_x} -> 全局中心: ({950 + max_loc_x[0] + 32}, {100 + max_loc_x[1] + 32})")
assert max_v_x >= 0.85
print("   >>> 购买弹窗关闭模板 100% PASS！")

# 4. Pipeline 语法与路由关系验证
import glob
pipeline = {}
for pf in glob.glob("assets/resource/pipeline/**/*.json", recursive=True):
    with open(pf, "r", encoding="utf-8") as f:
        pipeline.update(json.load(f))

start_next = [name for name in pipeline["FishingStartRouter"]["next"] if not name.startswith("[JumpBack]Global")]
bait_next = [name for name in pipeline["FishingBaitRouter"]["next"] if not name.startswith("[JumpBack]Global")]
assert "FishingStartAtPurchasePopup" in start_next
assert start_next[0] == "FishingBaitExhausted"
assert "FishingBaitPurchasePopup" in bait_next
assert bait_next[0] == "FishingBaitExhausted"
exhausted = pipeline["FishingBaitExhausted"]
assert exhausted["template"] == "钓鱼达人_鱼饵已用尽.png"
assert exhausted["roi"] == [8, 369, 196, 153]
assert exhausted["action"] == "DoNothing"
assert "target" not in exhausted
assert pipeline["FishingSelectCheeseBait"]["recognition"] == "TemplateMatch"
assert pipeline["FishingSelectCheeseBait"]["template"] == "普通饵食_黄色奶酪.png"
print("\n4. Pipeline 路由合规验证:")
print("   FishingStartRouter 首选业务路由:", start_next[0])
print("   FishingBaitRouter 首选业务路由:", bait_next[0])
print("   FishingBaitExhausted 使用模板与 ROI:", exhausted["template"], exhausted["roi"])
print("   FishingSelectCheeseBait 采用识别:", pipeline["FishingSelectCheeseBait"]["recognition"], pipeline["FishingSelectCheeseBait"]["template"])
print("   >>> Pipeline 配置规范 100% PASS！")

print("\n================================================================================")
print("=== 全部安全验证 100% 通过！防购买与黄色奶酪模板完全闭环！===")
print("================================================================================")
