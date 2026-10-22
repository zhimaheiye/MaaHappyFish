"""Read a named daily task from this MFA instance; never modify client configuration.

Only the select/checkbox/input option types used by DailyRoutineTask are supported.
Their overrides are applied in declaration order, like MFA v2.16.2 ProcessOptions.
Unknown or ambiguous saved choices fail closed instead of enabling extra work.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re


def read_daily_plan(task_name="", data_root=None):
    root = Path(data_root or Path.cwd())
    instance_id = os.environ.get("MFA_INSTANCE_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", instance_id):
        raise ValueError("无法确定当前 MFA 实例，未读取其它实例或默认配置")
    interface = json.loads((root / "interface.json").read_text(encoding="utf-8-sig"))
    config = json.loads((root / "config" / "instances" / f"{instance_id}.json").read_text(encoding="utf-8-sig"))
    tasks = [task for task in config.get("TaskItems", []) if task.get("entry") == "DailyRoutineTask"]
    if task_name:
        tasks = [task for task in tasks if daily_task_name(task) == task_name]
    if len(tasks) != 1:
        raise ValueError("引用日常任务不存在或不唯一；请在挂机设置填写唯一的独立日常显示名")
    task = tasks[0]
    if task.get("advanced"):
        raise ValueError("引用日常包含尚不支持的高级参数，未启动")
    definition = next(item for item in interface["task"] if item["entry"] == "DailyRoutineTask")
    if task.get("pipeline_override") and task["pipeline_override"] != definition.get("pipeline_override"):
        raise ValueError("引用日常包含自定义任务级覆盖，未忽略参数继续运行")
    return interface, task


def daily_task_name(task):
    return task.get("display_name_override") or task.get("label") or task.get("name", "日常收尾")


def daily_option_nodes(interface):
    """All declared daily option targets, including unselected cases, for isolation."""
    definition = next(task for task in interface["task"] if task["entry"] == "DailyRoutineTask")
    visited, nodes = set(), set()

    def visit(name):
        if name in visited:
            return
        visited.add(name)
        option = interface["option"][name]
        nodes.update(option.get("pipeline_override", {}))
        for case in option.get("cases", []):
            nodes.update(case.get("pipeline_override", {}))
            for child in case.get("option", []):
                visit(child)

    for name in definition.get("option", []):
        visit(name)
    return nodes


def compile_daily_options(interface, task):
    """Return ordered override objects, not a deep merge of custom_action_param."""
    definition = next(item for item in interface["task"] if item["entry"] == "DailyRoutineTask")
    result = [copy.deepcopy(definition.get("pipeline_override", {}))]
    processed = set()

    def process(names, saved_options, path=()):
        saved = {item["name"]: item for item in saved_options}
        if len(saved) != len(saved_options):
            raise ValueError("日常配置包含重复选项，未猜测使用哪组参数")
        for name in names:
            if name in path:
                raise ValueError(f"日常选项循环引用：{name}")
            if name in processed:
                continue
            processed.add(name)
            option = interface["option"][name]
            choice = saved.get(name, {})
            kind = option.get("type", "select")
            if kind == "input":
                values = {}
                for field in option.get("inputs", []):
                    value = choice.get("data", {}).get(field["name"], field.get("default", ""))
                    value = str(value)
                    if field.get("verify") and not re.fullmatch(field["verify"], value):
                        raise ValueError(f"日常输入值无效：{name} - {field['name']}")
                    field_type = field.get("pipeline_type", "string")
                    if field_type == "int":
                        value = int(value)
                    elif field_type == "bool":
                        if value.lower() not in ("true", "false"):
                            raise ValueError(f"日常布尔输入无效：{name}")
                        value = value.lower() == "true"
                    values[field["name"]] = value

                def substitute(value):
                    if isinstance(value, dict):
                        return {key: substitute(item) for key, item in value.items()}
                    if isinstance(value, list):
                        return [substitute(item) for item in value]
                    if isinstance(value, str):
                        match = re.fullmatch(r"\{([^{}]+)\}", value)
                        if match:
                            return values[match[1]]
                        return re.sub(r"\{([^{}]+)\}", lambda m: str(values[m[1]]), value)
                    return value

                result.append(substitute(option.get("pipeline_override", {})))
                continue
            cases = option.get("cases", [])
            if kind == "checkbox":
                selected = choice.get("selected_cases")
                if selected is None:
                    selected = option.get("default_case", [])
                if name == "日常收尾任务" and isinstance(selected, list) and "领取活动体力（酿月食香）" in selected:
                    print("[日常收尾] 酿月食香已结束，已忽略引用方案中旧的活动体力勾选。", flush=True)
                    selected = [case for case in selected if case != "领取活动体力（酿月食香）"]
                if not isinstance(selected, list) or set(selected) - {case["name"] for case in cases}:
                    raise ValueError(f"日常多选项已失效：{name}")
                active = [case for case in cases if case["name"] in selected]
            elif kind in ("select", "switch"):
                default = next((i for i, case in enumerate(cases) if case["name"] == option.get("default_case")), 0)
                index = choice.get("index")
                if index is None:
                    index = default
                if type(index) is not int or not 0 <= index < len(cases):
                    raise ValueError(f"日常选项索引无效：{name}")
                active = [cases[index]]
            else:
                raise ValueError(f"日常选项类型尚不支持：{name}")
            for case in active:
                result.append(copy.deepcopy(case.get("pipeline_override", {})))
                process(case.get("option", []), choice.get("sub_options", []), (*path, name))

    process(definition.get("option", []), task.get("option", []))
    return [override for override in result if override]


def daily_config_signature(context, interface, selection):
    """Fingerprint effective configuration, not UI names, timestamps or progress."""
    config = {}
    for name in sorted(daily_option_nodes(interface)):
        node = context.get_node_data(name)
        if not node:
            raise ValueError(f"日常配置节点缺失：{name}")
        config[name] = {key: value for key, value in node.items() if key != "focus"}
    data = json.dumps([os.environ.get("MFA_INSTANCE_ID", ""), selection, config], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
