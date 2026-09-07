import json
import os
import re
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()

def cv_imread(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), -1)

import glob
pipeline = {}
for pf in glob.glob("assets/resource/pipeline/**/*.json", recursive=True):
    with open(pf, "r", encoding="utf-8") as f:
        pipeline.update(json.load(f))

def match_node(node_name, img):
    cfg = pipeline[node_name]
    reco_type = cfg.get("recognition", "DirectHit")
    
    if reco_type == "DirectHit":
        return True, "DirectHit"
    
    if reco_type == "OCR":
        roi = cfg["roi"]
        expected = cfg["expected"]
        crop = img[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
        res, _ = ocr(crop)
        texts = [t[1] for t in (res or [])]
        for t in texts:
            if re.search(expected, t):
                return True, f"OCR Hit: '{t}' matches '{expected}'"
        return False, f"OCR Miss: texts={texts} expected='{expected}'"
        
    if reco_type == "TemplateMatch":
        roi = cfg["roi"]
        tpl_name = cfg["template"]
        threshold = cfg.get("threshold", 0.7)
        tpl_path = os.path.join("assets/resource/image", tpl_name)
        tpl = cv_imread(tpl_path)
        
        crop = img[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
        if len(tpl.shape) == 3 and tpl.shape[2] == 4:
            mask = tpl[:, :, 3]
            tpl_bgr = tpl[:, :, :3]
            crop_bgr = crop[:, :, :3] if len(crop.shape) == 3 and crop.shape[2] == 4 else crop
            res = cv2.matchTemplate(crop_bgr, tpl_bgr, cv2.TM_CCORR_NORMED, mask=mask)
        else:
            tpl_bgr = tpl[:, :, :3] if len(tpl.shape) == 3 and tpl.shape[2] == 4 else tpl
            crop_bgr = crop[:, :, :3] if len(crop.shape) == 3 and crop.shape[2] == 4 else crop
            res = cv2.matchTemplate(crop_bgr, tpl_bgr, cv2.TM_CCOEFF_NORMED)
            
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        hit = max_val >= threshold
        center_global = (roi[0] + max_loc[0] + tpl.shape[1] // 2, roi[1] + max_loc[1] + tpl.shape[0] // 2)
        return hit, f"Tpl: '{tpl_name}' score={max_val:.4f} thr={threshold} center={center_global}"

    return False, f"Unknown reco_type: {reco_type}"

def evaluate_candidates(candidate_nodes, img):
    for node in candidate_nodes:
        matched, detail = match_node(node, img)
        if matched:
            return node, detail
    return None, "No candidate matched"

def run_tests():
    print("=" * 70)
    print("【浪漫满屋退出修复】状态确认链深度验证")
    print("=" * 70)

    img_stage = cv_imread("dev/exploration/romantic_house/bless_00_before.png")
    img_home = cv_imread("dev/exploration/romantic_house/05_romantic_house_home.png")
    img_tank = cv_imread("dev/exploration/romantic_house/01_tank_full.png")

    # 合成 10/10 舞台满额帧
    img_10 = img_stage.copy()
    roi = pipeline["RomanticHouseCheckDone"]["roi"]
    cv2.rectangle(img_10, (roi[0], roi[1]), (roi[0]+roi[2], roi[1]+roi[3]), (139, 45, 175), -1)
    cv2.putText(img_10, "10/10", (roi[0]+50, roi[1]+45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)

    # -----------------------------------------------------------------
    # 情况 A：10/10 -> 点击退出 -> 返回主页 -> 返回主鱼缸 -> 成功
    # -----------------------------------------------------------------
    print("\n--- [测试 1: 情况 A] 正常顺序双级退出链 ---")
    
    # 1. 10/10 满额判定
    hit_1, detail_1 = evaluate_candidates(["RomanticHouseCheckDone", "RomanticHouseTryBless", "RomanticHouseNextCouple"], img_10)
    print(f"1. 满额画面评估: 命中 -> 【{hit_1}】 ({detail_1})")
    assert hit_1 == "RomanticHouseCheckDone"

    # 2. 流转至 ExitStage
    candidates_exit1 = pipeline[hit_1]["next"]
    print(f"   下一级候选: {candidates_exit1}")
    hit_2, detail_2 = evaluate_candidates(candidates_exit1, img_10)
    print(f"2. 舞台关闭评估: 命中 -> 【{hit_2}】 ({detail_2})")
    assert hit_2 == "RomanticHouseExitStage"
    assert "center=(1197, 57)" in detail_2, "Click point must be exact center (1197, 57)"

    # 3. 第一次点击成功，页面切换至浪漫满屋主页
    candidates_home = pipeline[hit_2]["next"]
    print(f"   下一级候选: {candidates_home}")
    hit_3, detail_3 = evaluate_candidates(candidates_home, img_home)
    print(f"3. 进入主页确认: 命中 -> 【{hit_3}】 ({detail_3})")
    assert hit_3 == "RomanticHouseCheckInHome"

    # 4. 主页触发 ExitHome
    candidates_exit2 = pipeline[hit_3]["next"]
    print(f"   下一级候选: {candidates_exit2}")
    hit_4, detail_4 = evaluate_candidates(candidates_exit2, img_home)
    print(f"4. 主页关闭评估: 命中 -> 【{hit_4}】 ({detail_4})")
    assert hit_4 == "RomanticHouseExitHome"
    assert "center=(1197, 57)" in detail_4, "Click point must be exact center (1197, 57)"

    # 5. 第二次点击成功，页面切换至主鱼缸
    candidates_tank = pipeline[hit_4]["next"]
    print(f"   下一级候选: {candidates_tank}")
    hit_5, detail_5 = evaluate_candidates(candidates_tank, img_tank)
    print(f"5. 返回鱼缸确认: 命中 -> 【{hit_5}】 ({detail_5})")
    assert hit_5 == "RomanticHouseDone"
    print(">> [PASS] 情况 A 验证通过：全链路状态驱动闭环退出，真正识别主鱼缸！")

    # -----------------------------------------------------------------
    # 情况 B：第一次点击没有生效（仍然停留在舞台）
    # -----------------------------------------------------------------
    print("\n--- [测试 2: 情况 B] 第一次关闭点击未生效（重试机制） ---")
    candidates_after_click1 = pipeline["RomanticHouseExitStage"]["next"]
    print(f"点击舞台关闭后候选列表: {candidates_after_click1}")
    # 模拟未关闭：传入依然是 stage 画面
    hit_b, detail_b = evaluate_candidates(candidates_after_click1, img_stage)
    print(f"未关闭时评估画面: 命中 -> 【{hit_b}】 ({detail_b})")
    assert hit_b == "RomanticHouseExitStage", "Must retry ExitStage when still on stage!"
    assert hit_b != "RomanticHouseCheckInHome", "Must not proceed to home when stage is not closed!"
    print(">> [PASS] 情况 B 验证通过：第一次未生效绝不推进，自动原地重试关闭！")

    # -----------------------------------------------------------------
    # 情况 C：停留在舞台，任务绝不能显示完成
    # -----------------------------------------------------------------
    print("\n--- [测试 3: 情况 C] 停留在舞台时杜绝假完成 ---")
    # 1. 验证 RomanticHouseDone 不是 DirectHit
    reco_done = pipeline["RomanticHouseDone"].get("recognition")
    print(f"RomanticHouseDone 识别方式: {reco_done}")
    assert reco_done != "DirectHit", "RomanticHouseDone must NOT be DirectHit!"
    
    # 2. 验证在舞台画面上评估 RomanticHouseDone 是否能通过
    matched_done_on_stage, detail_dos = match_node("RomanticHouseDone", img_stage)
    print(f"在舞台画面直接评估 RomanticHouseDone: matched={matched_done_on_stage} ({detail_dos})")
    assert matched_done_on_stage is False, "RomanticHouseDone must FAIL on stage!"

    # 3. 验证在活动主页画面上评估 RomanticHouseDone 是否能通过
    matched_done_on_home, detail_doh = match_node("RomanticHouseDone", img_home)
    print(f"在活动主页直接评估 RomanticHouseDone: matched={matched_done_on_home} ({detail_doh})")
    assert matched_done_on_home is False, "RomanticHouseDone must FAIL on home page!"

    print(">> [PASS] 情况 C 验证通过：未回到主鱼缸时绝对不可能触发完成！")

    print("\n" + "=" * 70)
    print("[PASS] 全部情况 A、B、C 仿真测试 100% 通过！彻底消除假完成风险！")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
