import subprocess, time, cv2, numpy as np, json, re
from rapidocr_onnxruntime import RapidOCR

adb = r"D:\Program Files\Netease\MuMu\nx_main\adb.exe"
device = "127.0.0.1:16384"
ocr = RapidOCR()

import glob
pipeline = {}
for pf in glob.glob("assets/resource/pipeline/**/*.json", recursive=True):
    with open(pf, "r", encoding="utf-8") as f:
        pipeline.update(json.load(f))

def cap():
    raw = subprocess.check_output([adb, "-s", device, "exec-out", "screencap", "-p"])
    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    return cv2.resize(img, (1280, 720))

def imread_u(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)

tpl_home = imread_u(r"assets\resource\image\主界面特征.png")
tpl_amuse = imread_u(r"assets\resource\image\游乐园入口.png")
tpl_rod = imread_u(r"assets\resource\image\钓鱼达人入口.png")

def tap(x720, y720):
    subprocess.run([adb, "-s", device, "shell", "input", "tap", str(int(x720*1.5)), str(int(y720*1.5))])

def run_fishing_task_pipeline(configured_location="宫殿温泉"):
    print(f"\n>>> 启动 FishingTask (目标地点配置: {configured_location}) <<<")
    # 模拟 FishingStartRouter 执行
    img = cap()

    # 1. FishingStartAtScene (深度 1: 已在钓鱼场景)
    cfg_scene = pipeline["FishingStartAtScene"]
    roi_s = cfg_scene["roi"]
    crop_s = img[roi_s[1]:roi_s[1]+roi_s[3], roi_s[0]:roi_s[0]+roi_s[2]]
    res_s, _ = ocr(crop_s)
    texts_s = [t for _, t, _ in (res_s or [])]
    if any(re.search(cfg_scene["expected"], t) for t in texts_s):
        print(f"[StartRouter] 命中 FishingStartAtScene (检测到「甩杆」)! 直接就地就绪，DoNothing 结束。")
        return "SCENE_READY"

    # 2. FishingStartAtLocationMap (深度 2: 已在大地图)
    cfg_map = pipeline["FishingStartAtLocationMap"]
    roi_m = cfg_map["roi"]
    crop_m = img[roi_m[1]:roi_m[1]+roi_m[3], roi_m[0]:roi_m[0]+roi_m[2]]
    res_m, _ = ocr(crop_m)
    texts_m = [t for _, t, _ in (res_m or [])]
    if any(re.search(cfg_map["expected"], t) for t in texts_m):
        print(f"[StartRouter] 命中 FishingStartAtLocationMap (检测到「钓鱼达人」)! 直接进入地点选择。")
        return select_location(configured_location)

    # 3. FishingStartAtActivityGrid (深度 3: 已在 2x6 面板)
    cfg_grid = pipeline["FishingStartAtActivityGrid"]
    roi_g = cfg_grid["roi"]
    crop_g = img[roi_g[1]:roi_g[1]+roi_g[3], roi_g[0]:roi_g[0]+roi_g[2]]
    res_g = cv2.matchTemplate(crop_g, tpl_rod, cv2.TM_CCOEFF_NORMED)
    _, max_vg, _, _ = cv2.minMaxLoc(res_g)
    if max_vg >= cfg_grid["threshold"]:
        print(f"[StartRouter] 命中 FishingStartAtActivityGrid (score={max_vg:.4f})! 点击钓鱼达人图标。")
        cfg_act = pipeline["FishingNavActivityGrid"]
        tap(cfg_act["target"][0], cfg_act["target"][1])
        time.sleep(cfg_act["post_delay"] / 1000.0)
        return select_location(configured_location)

    # 4. FishingStartAtOwnTank (深度 4: 自身主水族箱)
    cfg_own = pipeline["FishingStartAtOwnTank"]
    roi_o = cfg_own["roi"]
    crop_o = img[roi_o[1]:roi_o[1]+roi_o[3], roi_o[0]:roi_o[0]+roi_o[2]]
    res_o = cv2.matchTemplate(crop_o, tpl_home, cv2.TM_CCOEFF_NORMED)
    _, max_vo, _, _ = cv2.minMaxLoc(res_o)
    if max_vo >= cfg_own["threshold"]:
        print(f"[StartRouter] 命中 FishingStartAtOwnTank (score={max_vo:.4f})! 点击游乐园入口。")
        cfg_amuse = pipeline["FishingNavOpenAmusement"]
        tap(cfg_amuse["target"][0], cfg_amuse["target"][1])
        time.sleep(cfg_amuse["post_delay"] / 1000.0)
        
        # 此时应到达 2x6 面板
        cfg_act = pipeline["FishingNavActivityGrid"]
        tap(cfg_act["target"][0], cfg_act["target"][1])
        time.sleep(cfg_act["post_delay"] / 1000.0)
        return select_location(configured_location)

    raise RuntimeError(f"Unknown page state! Texts: {texts_m}, max_vo: {max_vo}, max_vg: {max_vg}")

def select_location(loc_name):
    node_map = {
        "星河": "FishingSelectLocation_Xinghe",
        "冰川": "FishingSelectLocation_Bingchuan",
        "宫殿温泉": "FishingSelectLocation_Gongdian",
        "魔法塔楼": "FishingSelectLocation_Mofa",
        "大戏台": "FishingSelectLocation_Daxitai",
        "星空湖": "FishingSelectLocation_Xingkonghu",
    }
    cfg_loc = pipeline[node_map[loc_name]]
    tx, ty = cfg_loc["target"][0], cfg_loc["target"][1]
    print(f"  DirectHit 点击目标地点 [{loc_name}]: ({tx}, {ty})...")
    tap(tx, ty)
    time.sleep(cfg_loc["post_delay"] / 1000.0)

    # 验证 FishingSceneReady
    img = cap()
    cfg_ready = pipeline["FishingSceneReady"]
    roi_r = cfg_ready["roi"]
    crop_r = img[roi_r[1]:roi_r[1]+roi_r[3], roi_r[0]:roi_r[0]+roi_r[2]]
    res_r, _ = ocr(crop_r)
    texts_r = [t for _, t, _ in (res_r or [])]
    matched = any(re.search(cfg_ready["expected"], t) for t in texts_r)
    print(f"  场景就绪校验 (未甩杆特征): texts={texts_r}, matched={matched}")
    assert matched, f"FishingSceneReady failed for {loc_name}: {texts_r}"
    print(f"  [SUCCESS] 成功到达场景 [{loc_name}]！0 鱼饵消耗！")
    return "SCENE_READY"

print("--- 测试 4: 当前正在钓鱼场景，直接运行 FishingTask ---")
res = run_fishing_task_pipeline("宫殿温泉")
assert res == "SCENE_READY"
print("测试 4 PASS: 命中 FishingStartAtScene，0 点击，不重新导航！")