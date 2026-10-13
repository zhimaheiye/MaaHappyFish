# -*- coding: utf-8 -*-
"""把一次 Maa 知识边界 / 识别失败写成 session/takeover/<id>/。

截图由调用方传入。正式 CustomAction 使用 my_action._capture_720p，
不在这里再连一个控制器。trace 或 Maa 日志缺失时仍然写包。
"""
import json
import os
from datetime import datetime
from pathlib import Path

from maa.custom_action import CustomAction

TRACE_TAIL_LIMIT = 10
LOG_TAIL_LINES = 200


def find_maa_log(environ=None, extra_candidates=None):
    """只认调用方明确给的目录，或当前进程按 MaaToolkit 约定写出的 debug/maa.log。

    找不到就返回 None。不猜测历史安装路径。
    """
    environ = os.environ if environ is None else environ
    for key in ("MAA_LOG_DIR", "MAAFW_LOG_DIR"):
        raw = (environ.get(key) or "").strip()
        if not raw:
            continue
        found = _resolve_log_path(Path(raw))
        if found is not None:
            return found
    if extra_candidates is None:
        # Toolkit.init_option(user_path) 把日志写到 user_path/debug。
        # 当前 Maa 文件名是 maafw.log，旧一些的构建才叫 maa.log。目录不存在就当没有。
        candidates = []
        for directory in (
            Path.cwd() / "debug",
            Path(__file__).resolve().parents[1] / "debug",
        ):
            candidates.append(directory / "maa.log")
            candidates.append(directory / "maafw.log")
    else:
        candidates = [Path(item) for item in extra_candidates]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _resolve_log_path(path):
    if path.is_file():
        return path
    if not path.is_dir():
        return None
    logs = [item for item in path.glob("maa.log") if item.is_file()]
    if not logs:
        logs = [item for item in path.glob("*.log") if item.is_file()]
    if not logs:
        return None
    logs.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return logs[0]


def _tail_lines(path, limit):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-limit:]


def _save_png(image, path):
    if image is None:
        return False
    path = Path(path)
    if isinstance(image, (bytes, bytearray)):
        path.write_bytes(image)
        return path.is_file() and path.stat().st_size > 0
    save = getattr(image, "save", None)
    if callable(save):
        save(path, format="PNG")
        return path.is_file() and path.stat().st_size > 0
    try:
        import cv2
    except Exception:
        return False
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        return False
    path.write_bytes(encoded.tobytes())
    return path.is_file() and path.stat().st_size > 0


def write_takeover_package(param, image, log_text=None, log_path=None, now=None):
    """写 meta.json、current.png、trace_tail.jsonl。返回 (目录, meta)。"""
    if not isinstance(param, dict):
        raise ValueError("takeover param 必须是 dict")
    session_raw = param.get("session_dir")
    if not session_raw:
        raise ValueError("takeover param 缺少 session_dir")
    session_dir = Path(session_raw)
    moment = now or datetime.now()
    stamp = moment.strftime("%Y%m%d-%H%M%S-%f")
    reason = str(param.get("reason") or "unknown")
    source = str(param.get("source_state") or "unknown")
    takeover_id = "%s_%s_%s" % (stamp, _safe_id(reason), _safe_id(source))
    root = session_dir / "takeover"
    dest = root / takeover_id
    suffix = 2
    while dest.exists():
        dest = root / ("%s-%d" % (takeover_id, suffix))
        suffix += 1
    dest.mkdir(parents=True)

    screenshot_ok = _save_png(image, dest / "current.png")
    trace_path = session_dir / "trace.jsonl"
    if trace_path.is_file():
        tail = _tail_lines(trace_path, TRACE_TAIL_LIMIT)
        trace_status = "ok"
    else:
        tail = []
        trace_status = "unavailable"
    tail_path = dest / "trace_tail.jsonl"
    tail_path.write_text(("\n".join(tail) + ("\n" if tail else "")), encoding="utf-8")

    log_status = "unavailable"
    if log_text is not None:
        (dest / "maa_log_tail.txt").write_text(str(log_text), encoding="utf-8")
        log_status = "ok"
    else:
        found = Path(log_path) if log_path else find_maa_log()
        if found is not None and Path(found).is_file():
            log_lines = _tail_lines(found, LOG_TAIL_LINES)
            (dest / "maa_log_tail.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
            log_status = "ok"

    meta = {
        "event": param.get("event"),
        "session": param.get("session"),
        "timestamp": moment.isoformat(timespec="seconds"),
        "source_state": param.get("source_state"),
        "reason": param.get("reason"),
        "pipeline_node": param.get("pipeline_node"),
        "expected": param.get("expected"),
        "roi": param.get("roi"),
        "result_candidates": param.get("result_candidates") or [],
        "flow_path": param.get("flow_path"),
        "pipeline_path": param.get("pipeline_path"),
        "trace_status": trace_status,
        "log_status": log_status,
        "screenshot_status": "ok" if screenshot_ok else "unavailable",
    }
    if "known_candidates" in param:
        meta["known_candidates"] = param.get("known_candidates") or []
    if param.get("template"):
        meta["template"] = param.get("template")
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dest, meta


def _safe_id(text):
    cleaned = []
    for char in str(text):
        if char.isalnum() or char in ("-", "_"):
            cleaned.append(char)
        else:
            cleaned.append("_")
    value = "".join(cleaned).strip("_")
    return value or "x"


class DumpActivityTakeover(CustomAction):
    """正式注册在 my_action.py，避免这个模块导入时去连 AgentServer。"""

    capture = None

    def run(self, context, argv):
        try:
            from param_utils import parse_dict_param
        except ImportError:
            from agent.param_utils import parse_dict_param

        try:
            param = parse_dict_param(getattr(argv, "custom_action_param", None))
        except Exception:
            param = {}
        param = dict(param)
        node_name = getattr(argv, "node_name", None)
        if node_name:
            param["pipeline_node"] = node_name
        image = None
        capture = self.capture
        if capture is None:
            capture = _load_capture_720p()
        if capture is not None and context is not None:
            controller = getattr(getattr(context, "tasker", None), "controller", None)
            if controller is not None:
                try:
                    image = capture(controller)
                except Exception as exc:
                    print("[DumpActivityTakeover] 截图失败: %s" % exc, flush=True)
        try:
            _dest, meta = write_takeover_package(param, image)
        except Exception as exc:
            print("[DumpActivityTakeover] 写接管包失败: %s" % exc, flush=True)
            return False
        print(
            "[DumpActivityTakeover] %s %s screenshot=%s trace=%s log=%s"
            % (
                meta.get("source_state"),
                meta.get("reason"),
                meta.get("screenshot_status"),
                meta.get("trace_status"),
                meta.get("log_status"),
            ),
            flush=True,
        )
        return meta.get("screenshot_status") == "ok"


def _load_capture_720p():
    try:
        from my_action import _capture_720p
    except Exception:
        try:
            from agent.my_action import _capture_720p
        except Exception:
            return None
    return _capture_720p
