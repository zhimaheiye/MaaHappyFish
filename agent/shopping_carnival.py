"""Shopping Carnival: observe the board, merge one pair, verify a fresh board."""

import re
import time
from pathlib import Path

import cv2
import numpy as np

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

try:
    from param_utils import parse_dict_param, safe_int
except ImportError:
    from agent.param_utils import parse_dict_param, safe_int


# Measured on the original 1280 x 720 frames, not the old 6 x 6 notes.
CENTERS = [(305 + 99 * c, 143 + 99 * r) for r in range(6) for c in range(8)]
PEACH = np.array([222, 235, 255], dtype=np.int16)


class BoardChangedError(RuntimeError):
    """A fresh observation is needed before any gesture or generation."""


class BubbleDismissed(RuntimeError):
    """The board must be rebuilt after a bubble disappears."""


def board_cells(image):
    cells = []
    for x, y in CENTERS:
        tile = image[y - 44:y + 44, x - 44:x + 44]
        hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
        peach = np.max(np.abs(tile.astype(np.int16) - PEACH), axis=2) < 18
        ring = np.ones((88, 88), dtype=bool)
        ring[8:-8, 8:-8] = False
        white = (hsv[:, :, 1] < 30) & (hsv[:, :, 2] > 232)
        selection = cv2.cvtColor(image[y - 52:y + 52, x - 52:x + 52], cv2.COLOR_BGR2HSV)
        cyan = (selection[:, :, 0] > 80) & (selection[:, :, 0] < 105) & (selection[:, :, 1] > 100)
        # The white base is locked; cyan corners only mean selected.
        movable = float(peach[ring].mean()) > 0.45 and float(white[ring].mean()) < 0.20
        patch = tile[10:-10, 10:-10].copy()
        inner_hsv = hsv[10:-10, 10:-10]
        foreground = (inner_hsv[:, :, 1] > 85) | (inner_hsv[:, :, 2] < 175)
        patch[~foreground] = 255
        cells.append({
            "empty": float(peach[10:-10, 10:-10].mean()) > 0.985,
            "movable": movable,
            "selected": all(int(cyan[a:a + 18, b:b + 18].sum()) > 25
                            for a, b in ((0, 0), (0, 86), (86, 0), (86, 86))),
            "patch": patch,
        })
    return cells


def similarity(first, second):
    return float(cv2.matchTemplate(first, second, cv2.TM_CCOEFF_NORMED)[0, 0])


def is_box_generator(identity):
    return (identity[0] == "保险箱" and identity[1] == 5
            and "点击生成新棋子" in identity[2] and "最高" in identity[2])


def merge_candidates(cells, identities):
    pairs = []
    for source, cell in enumerate(cells):
        identity = identities.get(source)
        if (cell["empty"] or not cell["movable"] or not identity
                or identity[1] == 0 or "最高" in identity[2]):
            continue
        for target, other in enumerate(cells):
            if source == target or other["empty"]:
                continue
            if other["movable"] and source > target:
                continue
            other_identity = identities.get(target)
            if (other_identity and "最高" not in other_identity[2]
                    and identity[:2] == other_identity[:2]):
                pairs.append((other["movable"], -identity[1], source, target))
    return [(s, t) for _, _, s, t in sorted(pairs)]


class ShoppingCarnivalSession:
    def __init__(self, context):
        self.context = context
        self.controller = context.tasker.controller
        self.deadline = time.monotonic() + 1800
        self.known_cells = {}
        root = Path(__file__).resolve().parent.parent
        resource = root / "assets" / "resource"
        if not resource.is_dir():
            resource = root / "resource"
        self.title = cv2.imdecode(np.fromfile(
            resource / "image" / "shopping_carnival" / "title.png", dtype=np.uint8
        ), cv2.IMREAD_COLOR)

    def check_running(self):
        if self.context.tasker.stopping or not self.context.tasker.running:
            raise InterruptedError("已收到停止请求")
        if time.monotonic() > self.deadline:
            raise RuntimeError("达到本次三十分钟上限，尚未完成")

    def wait(self, seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            self.check_running()
            time.sleep(min(0.1, max(0, until - time.monotonic())))

    def capture(self):
        self.check_running()
        if not self.controller.post_screencap().wait().succeeded:
            raise RuntimeError("截屏失败")
        self.check_running()
        image = self.controller.cached_image
        if image is None or image.shape[:2] != (720, 1280):
            raise RuntimeError("只支持 1280×720 活动棋盘")
        return image.copy()

    def recognition(self, name, image):
        self.check_running()
        result = self.context.run_recognition(name, image)
        if result is None:
            raise RuntimeError("识别调用失败：" + name)
        return result

    def text(self, name, image):
        result = self.recognition(name, image)
        if not result.hit:
            return ""
        return "".join(str(item.get("text", "")) for item in result.raw_detail.get("all", [])
                       if item.get("score", 0) >= 0.85)

    def board(self):
        image = self.capture()
        if not self.recognition("ShoppingCarnivalBoardIdentity", image).hit:
            raise RuntimeError("未确认购物狂欢季棋盘；未知页面不操作")
        # Normalized template correlation alone also matches a dimmed modal backdrop.
        title = image[216:361, 32:217]
        if self.title is None or np.mean(cv2.absdiff(title, self.title)) > 18:
            raise RuntimeError("活动页被遮挡或布局变化")
        return image, board_cells(image)

    def click(self, x, y):
        self.check_running()
        if not self.controller.post_click(x, y).wait().succeeded:
            raise RuntimeError("点击未执行")
        self.check_running()

    def describe(self, index):
        image, cells = self.board()
        if cells[index]["empty"]:
            raise RuntimeError("待识别棋子已变化")
        # A second click on a selected resource extracts it. Never double-click.
        if not cells[index]["selected"]:
            self.click(*CENTERS[index])
            # Input acknowledgement can precede the game's selection update.
            # Observe without re-clicking: a second resource click extracts it.
            for _ in range(6):
                self.wait(0.5)
                image, cells = self.board()
                if cells[index]["selected"]:
                    break
        if not cells[index]["selected"]:
            raise RuntimeError("棋子选中态未确认")
        name = self.text("ShoppingCarnivalItemName", image)
        level_text = self.text("ShoppingCarnivalItemLevel", image)
        match = re.fullmatch(r"([0-9]{1,2})", level_text.strip())
        body = self.text("ShoppingCarnivalItemDescription", image)
        if "气泡" in body or "氣泡" in body:
            self.ignore_bubble(index)
        if not name:
            raise RuntimeError("棋子名称未识别")
        if "最高" in body:
            return name, int(match.group(1)) if match else 0, body
        if not match or "合" not in body:
            raise RuntimeError("棋子等级或合并说明未确认：" + name)
        return name, int(match.group(1)), body

    def ignore_bubble(self, index):
        # Reconfirm on a fresh frame: countdown expiry must not turn into a stale click.
        image, cells = self.board()
        if cells[index]["empty"]:
            raise BubbleDismissed("气泡已自然消失")
        if not cells[index]["selected"]:
            raise RuntimeError("气泡棋子选中态变化，不点击忽略")
        body = self.text("ShoppingCarnivalBubbleDescription", image)
        if not re.search(r"[气氣]泡", body) or "消失" not in body:
            raise RuntimeError("气泡说明未重新确认，不点击忽略")
        button = self.recognition("ShoppingCarnivalIgnoreBubble", image)
        matches = button.raw_detail.get("filtered", []) if button.hit else []
        matches = [item for item in matches
                   if item.get("text", "").strip() == "忽略" and item.get("score", 0) >= 0.85]
        if len(matches) != 1:
            raise RuntimeError("气泡忽略按钮未唯一确认；不点击戳破或固定坐标")
        x, y, w, h = matches[0]["box"]
        self.click(x + w // 2, y + h // 2)
        for _ in range(6):
            self.wait(0.5)
            _, after = self.board()
            if after[index]["empty"]:
                print("[购物狂欢季] 已忽略气泡棋子，重新识别棋盘后继续。", flush=True)
                raise BubbleDismissed("已确认气泡格清空")
        raise RuntimeError("点击忽略后未确认气泡消失，停止而不重复点击")

    def identify_board(self, cells):
        identities = {}
        for index, cell in enumerate(cells):
            if cell["empty"]:
                self.known_cells.pop(index, None)
                continue
            previous = self.known_cells.get(index)
            if previous and similarity(previous[0], cell["patch"]) >= 0.98:
                identities[index] = previous[1]
            else:
                identities[index] = self.describe(index)
                self.known_cells[index] = cell["patch"].copy(), identities[index]
        return identities

    def merge(self, source, target):
        first = self.describe(source)
        second = self.describe(target)
        if not first or not second or first[:2] != second[:2]:
            return False
        if any("合" not in item[2] or "最高" in item[2] for item in (first, second)):
            return False
        image, cells = self.board()
        if not cells[source]["movable"] or cells[source]["empty"]:
            raise RuntimeError("来源棋子不是可移动状态")
        if sum(cell["empty"] for cell in cells) < 3:
            raise RuntimeError("空格少于三格，无法保证合成奖励空间；保留棋盘停止")
        if cells[target]["empty"] or not cells[target]["selected"]:
            raise BoardChangedError("目标选中态变化，取消拖拽")
        # The original frame predates the entire board scan. Comparing its pixels
        # here rejected mirrors whose fresh OCR still confirmed the exact same pair.
        # Fresh name/level, merge descriptions, source mobility and target selection
        # are the pre-action contract; old patches are only a scan-cache hint.
        self.check_running()
        sx, sy = CENTERS[source]
        tx, ty = CENTERS[target]
        if not self.controller.post_swipe(sx, sy, tx, ty, 600).wait().succeeded:
            raise RuntimeError("拖拽执行失败")
        self.wait(1.2)
        _, after = self.board()
        if after[target]["empty"]:
            raise RuntimeError("拖拽后目标格为空，停止而不重复拖拽")
        upgraded = self.describe(target)
        if not upgraded or upgraded[1] != first[1] + 1:
            raise RuntimeError("目标等级未确认提升，停止")
        # Merge rewards may immediately refill the source (observed lipstick -> mirror).
        # The positively confirmed level increase proves the merge, not an empty source.
        self.known_cells.pop(source, None)
        self.known_cells.pop(target, None)
        if not after[source]["empty"]:
            print("[购物狂欢季] 目标已升级，来源格出现新棋子；重新识别后继续。", flush=True)
        print(f"[购物狂欢季] {first[0]} 等级 {first[1]}：格 {source + 1} → {target + 1}，"
              f"已确认升级为 {upgraded[0]} 等级 {upgraded[1]}。", flush=True)
        return True

    def energy_empty(self, image):
        # Only zero blocks generation; exact positive OCR is not a business gate.
        return self.recognition("ShoppingCarnivalEnergyEmpty", image).hit

    def generate(self, before, cells):
        self.check_running()
        # Keep room for merge bonuses. No deletion or resource extraction to make space.
        if sum(cell["empty"] for cell in cells) < 4:
            raise RuntimeError("可合成对不足且空格少于四格；保留棋盘等待人工整理")
        button = self.recognition("ShoppingCarnivalGenerator", before)
        if not button.hit:
            raise RuntimeError("生成按钮未识别")
        if self.energy_empty(before):
            return False
        x, y, w, h = tuple(button.box)
        self.click(x + w // 2, y + h // 2)
        self.wait(1.2)
        _, new_cells = self.board()
        if sum(
            cell["empty"] for cell in new_cells
        ) != sum(cell["empty"] for cell in cells) - 1:
            raise RuntimeError("生成后空格变化未确认，停止而不连点")
        print("[购物狂欢季] 已确认生成一枚棋子，继续识别合成。", flush=True)
        return True

    def generate_from_box(self, index):
        # This specific Max item generates locked pieces; other Max resources
        # still must not be clicked for extraction.
        if not is_box_generator(self.describe(index)):
            raise RuntimeError("保险箱名称、等级或生成说明变化，不点击")
        before, cells = self.board()
        if cells[index]["empty"] or not cells[index]["selected"]:
            raise RuntimeError("保险箱选中态未确认，不点击")
        if sum(cell["empty"] for cell in cells) < 4:
            raise RuntimeError("空格少于四格，保留保险箱等待整理")
        self.click(*CENTERS[index])
        for _ in range(6):
            self.wait(0.5)
            _, new_cells = self.board()
            added = [i for i, cell in enumerate(cells)
                     if cell["empty"] and not new_cells[i]["empty"]]
            if not added:
                continue
            # Allow the box to disappear when exhausted, but no other piece may vanish.
            if (len(added) != 1 or new_cells[added[0]]["movable"]
                    or any(not cell["empty"] and new_cells[i]["empty"]
                           for i, cell in enumerate(cells) if i != index)):
                continue
            self.known_cells.clear()
            print(f"[购物狂欢季] 保险箱已生成一枚锁定棋子（格 {added[0] + 1}），"
                  "重新识别并优先解锁。", flush=True)
            return
        raise RuntimeError("保险箱点击后未确认新增锁定棋子，停止而不重复点击")


@AgentServer.custom_action("ShoppingCarnivalMergeAction")
class ShoppingCarnivalMergeAction(CustomAction):
    def run(self, context, argv) -> bool:
        try:
            param = parse_dict_param(getattr(argv, "custom_action_param", None))
            generation_limit = safe_int(param.get("generation_limit", 200), 200, 0, 500)
            operation_limit = safe_int(param.get("operation_limit", 600), 600, 1, 1500)
            session = ShoppingCarnivalSession(context)
            generated = merged = 0
            observation_retries = 0
            for _ in range(operation_limit):
                image, cells = session.board()
                try:
                    identities = session.identify_board(cells)
                except BubbleDismissed:
                    session.known_cells.clear()
                    observation_retries = 0
                    continue
                pairs = merge_candidates(cells, identities)
                if pairs:
                    source, target = pairs[0]
                    try:
                        if not session.merge(source, target):
                            raise BoardChangedError("配对详情变化，取消拖拽")
                        merged += 1
                        observation_retries = 0
                    except BubbleDismissed:
                        session.known_cells.clear()
                        observation_retries = 0
                    except BoardChangedError:
                        # Rebuild the plan when fresh identity or selection changed.
                        # Never drag or generate with the stale plan.
                        observation_retries += 1
                        if observation_retries > 2:
                            raise
                        session.known_cells.clear()
                        session.wait(1.2)
                else:
                    # Re-read after selection; never reuse the pre-selection frame to click.
                    image, cells = session.board()
                    box = next((i for i, identity in identities.items()
                                if is_box_generator(identity)), None)
                    if generation_limit == 0 or (box is None and session.energy_empty(image)):
                        print(f"[购物狂欢季] 本轮合成结束：已合成 {merged} 对、生成 {generated} 枚；"
                              "当前无已确认可移动的同类同级对。", flush=True)
                        return True
                    if generated >= generation_limit:
                        raise RuntimeError("达到本次生成上限，保留剩余体力")
                    if box is not None:
                        session.generate_from_box(box)
                    else:
                        if not session.generate(image, cells):
                            continue
                    generated += 1
                    observation_retries = 0
            raise RuntimeError("达到操作上限，尚未完成")
        except InterruptedError:
            print("[购物狂欢季] 已停止。", flush=True)
            return False
        except Exception as exc:
            print(f"[购物狂欢季] ERROR: {exc}", flush=True)
            return False
