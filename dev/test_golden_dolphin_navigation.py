import os
import sys
import cv2
import numpy as np

def run_tests():
    print("=" * 65)
    print("  GoldenDolphin Entrance & Dialog Click Test Suite")
    print("=" * 65)

    # 1. 验证模板加载路径解析
    agent_dir = os.path.abspath("client_avalonia/agent")
    candidate_dirs = [
        os.path.join(agent_dir, "../resource/image"),
        os.path.join(agent_dir, "../assets/resource/image"),
        os.path.join(agent_dir, "../../assets/resource/image"),
        os.path.abspath("assets/resource/image"),
        os.path.abspath("client_avalonia/resource/image"),
        os.path.abspath("resource/image"),
    ]
    tpl_dir = None
    for d in candidate_dirs:
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "游乐园入口.png")):
            tpl_dir = os.path.abspath(d)
            break

    assert tpl_dir is not None, "Failed to resolve valid tpl_dir containing 游乐园入口.png"
    print(f"[PASS] Check 1: 模板资源路径正确解析 -> {tpl_dir}")

    # 2. 验证所有 6 张关键模板存在且解码非 None
    def _load_tpl(name):
        p = os.path.join(tpl_dir, name)
        if os.path.exists(p):
            return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
        return None

    tpl_dolphin = _load_tpl("金海豚_图标.png")
    tpl_confirm = _load_tpl("金海豚_确定按钮.png")
    tpl_star_1 = _load_tpl("金海豚_经验星1.png")
    tpl_star_2 = _load_tpl("金海豚_经验星2.png")
    tpl_cancel = _load_tpl("金海豚_结束取消.png")
    tpl_ent = _load_tpl("游乐园入口.png")

    required = {
        "游乐园入口": tpl_ent,
        "金海豚_图标": tpl_dolphin,
        "金海豚_确定按钮": tpl_confirm,
        "金海豚_经验星1": tpl_star_1,
        "金海豚_经验星2": tpl_star_2,
        "金海豚_结束取消": tpl_cancel,
    }
    for name, tpl in required.items():
        assert tpl is not None, f"Template {name} failed to load!"
        assert tpl.shape[0] > 10 and tpl.shape[1] > 10, f"Template {name} has invalid shape: {tpl.shape}"
    print(f"[PASS] Check 2: 全部 6 张关键视觉模板完整加载 (无一为 None)")

    # 3. 验证主鱼缸截屏
    live_screen = cv2.imdecode(np.fromfile("dev/current_live_mumu_screen.png", dtype=np.uint8), cv2.IMREAD_COLOR)
    assert live_screen is not None, "Failed to load live screen"

    res_d = cv2.matchTemplate(live_screen, tpl_dolphin, cv2.TM_CCOEFF_NORMED)
    _, max_vd, _, _ = cv2.minMaxLoc(res_d)
    assert max_vd < 0.65, f"Live screen unexpectedly matched dolphin: {max_vd:.3f}"
    print(f"[PASS] Check 3a: 主鱼缸状态下未误判为游乐园面板 (dolphin score={max_vd:.3f} < 0.65)")

    res_e = cv2.matchTemplate(live_screen, tpl_ent, cv2.TM_CCOEFF_NORMED)
    _, max_ve, _, loc_e = cv2.minMaxLoc(res_e)
    assert max_ve >= 0.70, f"Live screen failed to match amusement park entrance: {max_ve:.3f}"
    ent_cx = loc_e[0] + tpl_ent.shape[1] // 2
    ent_cy = loc_e[1] + tpl_ent.shape[0] // 2
    assert 20 <= ent_cx <= 90 and 450 <= ent_cy <= 530, f"Entrance target out of bounds: ({ent_cx}, {ent_cy})"
    print(f"[PASS] Check 3b: 准确识别主鱼缸游乐园入口 (score={max_ve:.3f} at ({ent_cx}, {ent_cy}))")

    # 4. 验证游乐园面板截图
    grid_screen = cv2.imdecode(np.fromfile("dev/exploration/golden_dolphin/01_activity_grid.png", dtype=np.uint8), cv2.IMREAD_COLOR)
    assert grid_screen is not None, "Failed to load grid screen"

    res_d_grid = cv2.matchTemplate(grid_screen, tpl_dolphin, cv2.TM_CCOEFF_NORMED)
    _, max_vd_grid, _, loc_d_grid = cv2.minMaxLoc(res_d_grid)
    assert max_vd_grid >= 0.70, f"Grid screen failed to match dolphin: {max_vd_grid:.3f}"
    dx = loc_d_grid[0] + tpl_dolphin.shape[1] // 2
    dy = loc_d_grid[1] + tpl_dolphin.shape[0] // 2
    assert 480 <= dx <= 520 and 540 <= dy <= 580, f"Dolphin target out of bounds: ({dx}, {dy})"
    print(f"[PASS] Check 4: 游乐园面板就绪状态识别 (score={max_vd_grid:.3f} at ({dx}, {dy}))")

    # 5. 验证用户现场实拍: 机会耗尽提示弹窗，精准命中绿色对号中心 (829, 494) 而非 (800, 435)
    user_screen = cv2.imdecode(np.fromfile("C:/Users/sxy10/.gemini/antigravity/brain/65c155de-1230-4b2a-9733-2a78a0f09e43/.user_uploaded/media_1788689852954.jpg", dtype=np.uint8), cv2.IMREAD_COLOR)
    user_720 = cv2.resize(user_screen, (1280, 720))

    # HSV 绿色对号检测
    hsv_u = cv2.cvtColor(user_720, cv2.COLOR_BGR2HSV)
    mask_u = cv2.inRange(hsv_u, np.array([35, 70, 70]), np.array([85, 255, 255]))
    submask_u = np.zeros_like(mask_u)
    submask_u[410:560, 750:910] = mask_u[410:560, 750:910]
    cnts_u, _ = cv2.findContours(submask_u, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found_gc = None
    for c in cnts_u:
        if cv2.contourArea(c) > 1000:
            M = cv2.moments(c)
            if M["m00"] > 0:
                found_gc = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                break
    assert found_gc is not None, "Failed to find green check on user exhausted popup!"
    assert 815 <= found_gc[0] <= 845 and 480 <= found_gc[1] <= 510, f"Green check out of bounds: {found_gc}"
    print(f"[PASS] Check 5: 用户实拍现场精准锁定绿色对号中心 -> ({found_gc[0]}, {found_gc[1]}) (彻底规避旧坐标 (800, 435))")

    # 6. 验证模板匹配在用户实拍上的高置信度 (>= 0.80)
    res_c_user = cv2.matchTemplate(user_720, tpl_confirm, cv2.TM_CCOEFF_NORMED)
    _, max_vc_u, _, loc_c_u = cv2.minMaxLoc(res_c_user)
    assert max_vc_u >= 0.80, f"Template match failed on user exhausted screen: {max_vc_u:.3f}"
    btn_x = loc_c_u[0] + tpl_confirm.shape[1] // 2
    btn_y = loc_c_u[1] + tpl_confirm.shape[0] // 2
    assert 815 <= btn_x <= 845 and 480 <= btn_y <= 510
    print(f"[PASS] Check 6: 优化后金海豚_确定按钮模板实测命中 -> score={max_vc_u:.3f}, 中心=({btn_x}, {btn_y})")

    # 7. 静态代码审计确认
    with open("agent/my_action.py", "r", encoding="utf-8") as f:
        code = f.read()
    assert "674, 468" not in code
    assert "_find_green_check" in code
    assert "dialog_closed" in code
    print(f"[PASS] Check 7: 静态代码审计确认闭环确认循环 (dialog_closed) 与 HSV 双通道检测已就绪")

    print("\nALL 7 CHECKS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
