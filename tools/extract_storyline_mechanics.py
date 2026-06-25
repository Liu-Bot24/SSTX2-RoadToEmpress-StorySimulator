from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


DIMENSION_NAMES = {
    0: "韧性",
    1: "谋略",
    2: "野心",
    3: "果决",
    4: "声望",
}

KNOWN_PARAMETER_NAMES = {
    "trust_wanghuanghou": "王皇后信任度",
    "dimensionKey_heart": "心计/心动变量",
}

PARAMETER_DISPLAY_NAMES = {
    "052A": "引蛇出洞布置值",
    "count": "立后推进计数",
    "dimensionKey_heart": "心计/心动变量",
    "dimensionValue_010": "政治黑洞规避值 / 季怀衷政治判断值",
    "doubt": "疑虑值",
    "doubt_lizhi": "礼治疑虑值",
    "favor_litai": "礼泰好感度",
    "jihuaizhong": "季怀衷臣服度",
    "litai": "礼泰羁绊值",
    "lixian": "礼贤说服值",
    "liyifu": "李义府招揽值",
    "nvdi": "女帝进度值",
    "refuse": "反对老李家计数",
    "trust_wanghuanghou": "王皇后信任度",
    "value_jiakong": "削权架空值",
    "yueer": "月儿真相关联值",
}


def load_text_map(path: Path) -> dict[str, str]:
    text_map: dict[str, str] = {}
    if not path.exists():
        return text_map
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        key = obj.get("raw_key") or (f"Key:{obj.get('key')}" if obj.get("key") else None) or obj.get("tid") or obj.get("id")
        value = obj.get("zh_CN") or obj.get("zh_GL") or obj.get("zh") or obj.get("zh_TW") or obj.get("text") or obj.get("value")
        if key and isinstance(value, str):
            text_map[str(key)] = value
    return text_map


def tr(value: Any, text_map: dict[str, str]) -> Any:
    if isinstance(value, str) and value.startswith("Key:"):
        return text_map.get(value, value)
    return value


def display_name_for_parameter(key: Any, fallback: Any = None) -> str:
    value = "" if key is None else str(key)
    if value in PARAMETER_DISPLAY_NAMES:
        return PARAMETER_DISPLAY_NAMES[value]
    if value.startswith("dimension:"):
        try:
            dim = int(value.split(":", 1)[1])
        except ValueError:
            dim = None
        if dim in DIMENSION_NAMES:
            return DIMENSION_NAMES[dim]
    fallback_text = "" if fallback is None else str(fallback)
    return fallback_text or value


def flavor_display_name(target: Any, metric: Any) -> str:
    target_text = "" if target is None else str(target).strip()
    metric_text = "" if metric is None else str(metric).strip()
    if target_text and metric_text:
        return f"{target_text}{metric_text}"
    return metric_text or target_text


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def node_key(node: dict[str, Any]) -> str:
    return node.get("baseInfo", {}).get("key") or ""


def node_pv(node: dict[str, Any]) -> dict[str, Any]:
    return node.get("dataInfo", {}).get("parameterValue") or {}


def node_annotation(node: dict[str, Any]) -> str:
    return node.get("dataInfo", {}).get("annotation") or ""


def choice_text(choice: dict[str, Any], text_map: dict[str, str]) -> str:
    return str(tr(choice.get("choiceText") or "", text_map) or "")


def choice_letter(index: int | None) -> str:
    if index is None or index < 0:
        return ""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return alphabet[index] if index < len(alphabet) else str(index)


def label_node(storyline_id: str, node_hash: str, node: dict[str, Any], text_map: dict[str, str]) -> str:
    pv = node_pv(node)
    return (
        pv.get("videoKey")
        or node_annotation(node)
        or tr(pv.get("title"), text_map)
        or tr(pv.get("storylineTitle"), text_map)
        or node_key(node)
        or f"{storyline_id}:{node_hash}"
    )


def port_ref(ref: dict[str, Any]) -> tuple[str, str, int, str]:
    return (
        ref.get("hashNode") or "",
        ref.get("searchKeyGroup") or "",
        int(ref.get("indexGroup", -1)),
        ref.get("searchKey") or "",
    )


class StorylineMechanics:
    def __init__(self, storyline_id: str, raw: dict[str, Any], text_map: dict[str, str]):
        self.storyline_id = storyline_id
        self.raw = raw
        self.text_map = text_map
        self.nodes = {node.get("hash"): node for node in raw.get("node", []) if node.get("hash")}
        self.variables = self._load_variables(raw)
        self.param_in: dict[tuple[str, str, int, str], list[dict[str, Any]]] = defaultdict(list)
        self.lead_in: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.lead_out: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._index_links()

    def _load_variables(self, raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
        variables: dict[str, dict[str, Any]] = {}
        for var in raw.get("globalVariable", []) or []:
            h = var.get("hash")
            if not h:
                continue
            variables[h] = {
                "hash": h,
                "key": var.get("baseInfo", {}).get("key") or h,
                "type": var.get("typeInfo", {}).get("type"),
                "default": var.get("dataInfo", {}).get("defaultValue"),
            }
        return variables

    def _index_links(self) -> None:
        for link in self.raw.get("parameterLink", []) or []:
            base = link.get("baseInfo", {})
            dst = base.get("to") or {}
            self.param_in[port_ref(dst)].append(link)
        for link in self.raw.get("leadLink", []) or []:
            base = link.get("baseInfo", {})
            src = base.get("from") or {}
            dst = base.get("to") or {}
            src_hash = src.get("hashNode")
            dst_hash = dst.get("hashNode")
            if src_hash:
                self.lead_out[src_hash].append(link)
            if dst_hash:
                self.lead_in[dst_hash].append(link)

    def variable_name(self, variable_hash: str | None) -> str:
        if not variable_hash:
            return ""
        if variable_hash in self.variables:
            key = self.variables[variable_hash]["key"]
            return KNOWN_PARAMETER_NAMES.get(key, key)
        return KNOWN_PARAMETER_NAMES.get(variable_hash, f"var:{variable_hash}")

    def value_for(self, node_hash: str, search_key: str, default: Any = None, group: str = "", index: int = -1) -> Any:
        links = self.param_in.get((node_hash, group, index, search_key), [])
        if len(links) == 1:
            src = (links[0].get("baseInfo", {}).get("from") or {}).get("hashNode")
            if src:
                return self.expr(src)
        node = self.nodes.get(node_hash) or {}
        return node_pv(node).get(search_key, default)

    def expr(self, node_hash: str, seen: set[str] | None = None) -> str:
        seen = seen or set()
        if node_hash in seen:
            return f"<cycle:{node_hash}>"
        seen.add(node_hash)
        node = self.nodes.get(node_hash)
        if not node:
            return f"<missing:{node_hash}>"
        kind = node_key(node)
        pv = node_pv(node)
        if kind == "Global_GlobalVariableGetter":
            return self.variable_name(pv.get("variableHash"))
        if kind == "Global_GlobalVariableSetter":
            name = self.variable_name(pv.get("variableHash"))
            value = self.value_for(node_hash, "inputValue", pv.get("inputValue"))
            return f"set {name} = {value}"
        if kind == "Getter_GetVideoKeyVariable_Boloean":
            key = pv.get("parameterKey")
            return f"已播放/选择过 {KNOWN_PARAMETER_NAMES.get(key, key)}"
        if kind == "Getter_GetVideoKeyVariable_Sum":
            key = pv.get("parameterKey")
            return f"{KNOWN_PARAMETER_NAMES.get(key, key)} 累计值"
        if kind == "Getter_GetVideoKeyIndex":
            return f"视频索引({pv.get('parameterKey') or pv.get('customParams1') or node_annotation(node)})"
        if kind == "Getter_GetArray":
            return f"数组取值({pv.get('customParams1') or node_annotation(node)})"
        if kind in {"Logic_Math_LessThan", "Logic_Math_LessThanOrEqual", "Logic_Math_GreaterThanOrEqual", "Logic_Math_Equal"}:
            op = {
                "Logic_Math_LessThan": "<",
                "Logic_Math_LessThanOrEqual": "<=",
                "Logic_Math_GreaterThanOrEqual": ">=",
                "Logic_Math_Equal": "==",
            }[kind]
            a = self.value_for(node_hash, "inputValueA", pv.get("inputValueA"))
            b = self.value_for(node_hash, "inputValueB", pv.get("inputValueB"))
            return f"{a} {op} {b}"
        if kind == "Logic_AND":
            a = self.value_for(node_hash, "inputValueA", pv.get("inputValueA"))
            b = self.value_for(node_hash, "inputValueB", pv.get("inputValueB"))
            return f"({a}) AND ({b})"
        if kind == "Logic_OR":
            a = self.value_for(node_hash, "inputValueA", pv.get("inputValueA"))
            b = self.value_for(node_hash, "inputValueB", pv.get("inputValueB"))
            return f"({a}) OR ({b})"
        if kind == "Logic_NOT":
            value = self.value_for(node_hash, "inputValue", pv.get("inputValue"))
            return f"NOT ({value})"
        return node_annotation(node) or kind or node_hash

    def condition_exprs(self, if_hash: str) -> list[str]:
        node = self.nodes[if_hash]
        pv = node_pv(node)
        groups = pv.get("conditionGroup") or []
        exprs: list[str] = []
        if groups:
            for idx, item in enumerate(groups):
                links = self.param_in.get((if_hash, "conditionGroup", idx, "condition"), [])
                if len(links) == 1:
                    src = (links[0].get("baseInfo", {}).get("from") or {}).get("hashNode")
                    exprs.append(self.expr(src) if src else str(item.get("condition")))
                else:
                    exprs.append(str(item.get("condition")))
            return exprs
        links = self.param_in.get((if_hash, "", -1, "condition"), [])
        if len(links) == 1:
            src = (links[0].get("baseInfo", {}).get("from") or {}).get("hashNode")
            return [self.expr(src)] if src else [str(pv.get("condition"))]
        return [str(pv.get("condition"))]

    def show_choice_by_video_key(self, video_key: str) -> tuple[str, dict[str, Any]] | None:
        matches: list[tuple[str, dict[str, Any]]] = []
        for node_hash, node in self.nodes.items():
            if node_key(node) != "ShowChoice":
                continue
            if node_pv(node).get("videoKey") == video_key:
                matches.append((node_hash, node))
        return matches[0] if len(matches) == 1 else None

    def lead_target_info_for_condition_group(self, if_hash: str, group_index: int) -> dict[str, str]:
        for link in self.lead_out.get(if_hash, []):
            src = link.get("baseInfo", {}).get("from") or {}
            if src.get("searchKeyGroup") != "conditionGroup":
                continue
            if int(src.get("indexGroup", -1)) != group_index:
                continue
            if src.get("searchKey") != "endPointTrue":
                continue
            target_hash = (link.get("baseInfo", {}).get("to") or {}).get("hashNode") or ""
            target = self.nodes.get(target_hash) or {}
            return {
                "target": label_node(self.storyline_id, target_hash, target, self.text_map),
                "target_hash": target_hash,
                "target_node_id": f"{self.storyline_id}:{target_hash}" if target_hash else "",
            }
        return {}

    def lead_target_info_for_else(self, if_hash: str) -> dict[str, str]:
        for link in self.lead_out.get(if_hash, []):
            src = link.get("baseInfo", {}).get("from") or {}
            if src.get("searchKeyGroup"):
                continue
            if src.get("searchKey") not in {"endPointElse", "endPointFalse"}:
                continue
            target_hash = (link.get("baseInfo", {}).get("to") or {}).get("hashNode") or ""
            target = self.nodes.get(target_hash) or {}
            return {
                "target": label_node(self.storyline_id, target_hash, target, self.text_map),
                "target_hash": target_hash,
                "target_node_id": f"{self.storyline_id}:{target_hash}" if target_hash else "",
            }
        return {}

    def lead_target_for_condition_group(self, if_hash: str, group_index: int) -> str:
        return self.lead_target_info_for_condition_group(if_hash, group_index).get("target", "")

    def lead_target_for_else(self, if_hash: str) -> str:
        return self.lead_target_info_for_else(if_hash).get("target", "")

    def choice_index_cases(self, if_hash: str) -> list[dict[str, Any]]:
        node = self.nodes[if_hash]
        groups = node_pv(node).get("conditionGroup") or []
        explicit_cases: list[dict[str, Any]] = []
        for idx, _item in enumerate(groups):
            links = self.param_in.get((if_hash, "conditionGroup", idx, "condition"), [])
            if len(links) != 1:
                continue
            src_hash = (links[0].get("baseInfo", {}).get("from") or {}).get("hashNode")
            src = self.nodes.get(src_hash or "") or {}
            if node_key(src) != "Getter_GetVideoKeyIndex":
                continue
            pv = node_pv(src)
            video_key = pv.get("connectVideoKey")
            select_index = pv.get("selectIndex")
            if not video_key or select_index is None:
                continue
            target_info = self.lead_target_info_for_condition_group(if_hash, idx)
            target = target_info.get("target", "")
            if not target:
                continue
            choice_match = self.show_choice_by_video_key(str(video_key))
            choice_hash, choice_node = choice_match if choice_match else ("", {})
            choices = node_pv(choice_node).get("choice") or []
            choice_idx = int(select_index)
            text = choice_text(choices[choice_idx], self.text_map) if 0 <= choice_idx < len(choices) else ""
            explicit_cases.append(
                {
                    "choice_hash": choice_hash,
                    "storyline_id": self.storyline_id,
                    "choice_video_key": str(video_key),
                    "choice_title": tr(node_pv(choice_node).get("title"), self.text_map) or node_annotation(choice_node),
                    "choice_index": choice_idx,
                    "choice_text": text,
                    "case_source": "explicit",
                    "condition_group_index": idx,
                    "target": target,
                    "target_hash": target_info.get("target_hash", ""),
                    "target_node_id": target_info.get("target_node_id", ""),
                }
            )
        if not explicit_cases:
            return []
        video_keys = {item["choice_video_key"] for item in explicit_cases}
        if len(video_keys) != 1:
            return explicit_cases
        video_key = next(iter(video_keys))
        choice_match = self.show_choice_by_video_key(video_key)
        if not choice_match:
            return explicit_cases
        choice_hash, choice_node = choice_match
        choices = node_pv(choice_node).get("choice") or []
        used = {item["choice_index"] for item in explicit_cases}
        else_target_info = self.lead_target_info_for_else(if_hash)
        else_target = else_target_info.get("target", "")
        if else_target:
            for idx, choice in enumerate(choices):
                if idx in used:
                    continue
                explicit_cases.append(
                    {
                        "choice_hash": choice_hash,
                        "storyline_id": self.storyline_id,
                        "choice_video_key": video_key,
                        "choice_title": tr(node_pv(choice_node).get("title"), self.text_map) or node_annotation(choice_node),
                        "choice_index": idx,
                        "choice_text": choice_text(choice, self.text_map),
                        "case_source": "else_complement",
                        "condition_group_index": -1,
                        "target": else_target,
                        "target_hash": else_target_info.get("target_hash", ""),
                        "target_node_id": else_target_info.get("target_node_id", ""),
                    }
                )
        return sorted(explicit_cases, key=lambda item: item["choice_index"])

    def lead_target_summary(self, node_hash: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for link in self.lead_out.get(node_hash, []):
            src = link.get("baseInfo", {}).get("from") or {}
            dst = link.get("baseInfo", {}).get("to") or {}
            port = src.get("searchKey") or ""
            target_hash = dst.get("hashNode") or ""
            target = self.nodes.get(target_hash) or {}
            result[port] = label_node(self.storyline_id, target_hash, target, self.text_map)
        return result

    def lead_target_id_summary(self, node_hash: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for link in self.lead_out.get(node_hash, []):
            src = link.get("baseInfo", {}).get("from") or {}
            dst = link.get("baseInfo", {}).get("to") or {}
            port = src.get("searchKey") or ""
            target_hash = dst.get("hashNode") or ""
            result[port] = f"{self.storyline_id}:{target_hash}" if target_hash else ""
        return result

    def upstream_choices(self, start_hash: str, max_depth: int = 10) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        queue: deque[tuple[str, int]] = deque([(start_hash, 0)])
        seen = {start_hash}
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for link in self.lead_in.get(current, []):
                base = link.get("baseInfo", {})
                src = base.get("from") or {}
                src_hash = src.get("hashNode")
                if not src_hash:
                    continue
                src_node = self.nodes.get(src_hash) or {}
                if node_key(src_node) == "ShowChoice" and src.get("searchKey") == "choiceEndPoint":
                    idx = int(src.get("indexGroup", -1))
                    choices = node_pv(src_node).get("choice") or []
                    text = choice_text(choices[idx], self.text_map) if 0 <= idx < len(choices) else ""
                    found.append(
                        {
                            "choice_hash": src_hash,
                            "storyline_id": self.storyline_id,
                            "choice_video_key": node_pv(src_node).get("videoKey") or "",
                            "choice_title": tr(node_pv(src_node).get("title"), self.text_map) or node_annotation(src_node),
                            "choice_index": idx,
                            "choice_text": text,
                            "distance": depth + 1,
                        }
                    )
                if src_hash not in seen:
                    seen.add(src_hash)
                    queue.append((src_hash, depth + 1))
        return found

    def extract_conditions(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for h, node in self.nodes.items():
            kind = node_key(node)
            if kind not in {"Function_Storyline_If", "Function_If"}:
                continue
            expressions = self.condition_exprs(h)
            choice_cases = self.choice_index_cases(h)
            if choice_cases:
                expressions = [
                    "此前选择「"
                    + (case.get("choice_title") or case.get("choice_video_key") or "")
                    + " / "
                    + (choice_letter(case.get("choice_index")) + "：" if choice_letter(case.get("choice_index")) else "")
                    + (case.get("choice_text") or "")
                    + f"」则进入 {case.get('target')}"
                    for case in choice_cases
                ]
            variable_display_names = {}
            for expr in expressions:
                if "累计值" not in expr:
                    continue
                variable = expr.split("累计值", 1)[0].strip()
                if variable:
                    variable_display_names[variable] = display_name_for_parameter(variable)
            outcomes = self.lead_target_summary(h)
            outcome_target_ids = self.lead_target_id_summary(h)
            rows.append(
                {
                    "storyline_id": self.storyline_id,
                    "node_hash": h,
                    "node_kind": kind,
                    "annotation": node_annotation(node),
                    "expressions": expressions,
                    "variable_display_names": variable_display_names,
                    "outcomes": outcomes,
                    "outcome_target_ids": outcome_target_ids,
                    "upstream_choices": self.upstream_choices(h),
                    **({"choice_index_cases": choice_cases} if choice_cases else {}),
                }
            )
        return rows

    def extract_global_variable_nodes(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for h, node in self.nodes.items():
            kind = node_key(node)
            if kind not in {"Global_GlobalVariableGetter", "Global_GlobalVariableSetter"}:
                continue
            pv = node_pv(node)
            row = {
                "storyline_id": self.storyline_id,
                "node_hash": h,
                "kind": kind,
                "variable_hash": pv.get("variableHash"),
                "variable_name": self.variable_name(pv.get("variableHash")),
                "value": pv.get("inputValue") if kind.endswith("Setter") else None,
                "upstream_choices": self.upstream_choices(h),
                "outcomes": self.lead_target_summary(h),
            }
            rows.append(row)
        return rows

    def extract_video_effects(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for h, node in self.nodes.items():
            kind = node_key(node)
            pv = node_pv(node)
            video_key = pv.get("videoKey")
            if not video_key:
                continue
            if kind == "ShowChoice":
                choices = pv.get("choice") or []
                for sub in node.get("dataInfo", {}).get("subNode", []) or []:
                    sub_kind = node_key(sub)
                    sub_pv = node_pv(sub)
                    if sub_kind == "ShowChoice_SixDimension_Increase":
                        for item in sub_pv.get("choice") or []:
                            try:
                                choice_idx = int(item.get("targetChoice"))
                            except (TypeError, ValueError):
                                choice_idx = None
                            dim = item.get("dimensionKey")
                            key = f"dimension:{dim}"
                            name = DIMENSION_NAMES.get(dim, f"属性{dim}")
                            choice = choices[choice_idx] if choice_idx is not None and 0 <= choice_idx < len(choices) else {}
                            rows.append(
                                {
                                    "storyline_id": self.storyline_id,
                                    "video_hash": h,
                                    "video_key": video_key,
                                    "effect_kind": sub_kind,
                                    "effect_key": key,
                                    "effect_name": name,
                                    "effect_display_name": display_name_for_parameter(key, name),
                                    "effect_value": item.get("dimensionValue"),
                                    "upstream_choices": [
                                        {
                                            "choice_hash": h,
                                            "storyline_id": self.storyline_id,
                                            "choice_video_key": video_key,
                                            "choice_title": tr(pv.get("title"), self.text_map)
                                            or tr(pv.get("storylineTitle"), self.text_map)
                                            or node_annotation(node),
                                            "choice_index": choice_idx,
                                            "choice_text": choice_text(choice, self.text_map) if choice else "",
                                            "distance": 1,
                                        }
                                    ],
                                }
                            )
            for sub in node.get("dataInfo", {}).get("subNode", []) or []:
                sub_kind = node_key(sub)
                sub_pv = node_pv(sub)
                if sub_kind == "PlayVideo_VideoKey_Variable_Int":
                    for item in sub_pv.get("addParams") or []:
                        key = item.get("parameterKey")
                        name = KNOWN_PARAMETER_NAMES.get(key, key)
                        rows.append(
                            {
                                "storyline_id": self.storyline_id,
                                "video_hash": h,
                                "video_key": video_key,
                                "effect_kind": sub_kind,
                                "effect_key": key,
                                "effect_name": name,
                                "effect_display_name": display_name_for_parameter(key, name),
                                "effect_value": item.get("parameVariable"),
                                "upstream_choices": self.upstream_choices(h),
                            }
                        )
                elif sub_kind == "QTE_SixDimension_Increase":
                    for item in sub_pv.get("qte") or []:
                        dim = item.get("dimensionKey")
                        key = f"dimension:{dim}"
                        name = DIMENSION_NAMES.get(dim, f"属性{dim}")
                        rows.append(
                            {
                                "storyline_id": self.storyline_id,
                                "video_hash": h,
                                "video_key": video_key,
                                "effect_kind": sub_kind,
                                "effect_key": key,
                                "effect_name": name,
                                "effect_display_name": display_name_for_parameter(key, name),
                                "effect_value": item.get("dimensionValue"),
                                "upstream_choices": self.upstream_choices(h),
                            }
                        )
                elif sub_kind == "PlayVideo_Toast_DimensionIncrease":
                    for item in sub_pv.get("flavor") or []:
                        dim = item.get("dimensionType")
                        key = f"dimension:{dim}"
                        name = DIMENSION_NAMES.get(dim, f"属性{dim}")
                        rows.append(
                            {
                                "storyline_id": self.storyline_id,
                                "video_hash": h,
                                "video_key": video_key,
                                "effect_kind": sub_kind,
                                "effect_key": key,
                                "effect_name": name,
                                "effect_display_name": display_name_for_parameter(key, name),
                                "effect_value": item.get("customParams2"),
                                "upstream_choices": self.upstream_choices(h),
                            }
                        )
                elif sub_kind in {"PlayVideo_Toast_FlavorIncrese", "PlayVideo_Toast_FlavorDecrease"}:
                    for item in sub_pv.get("flavor") or []:
                        key = tr(item.get("customParams1"), self.text_map)
                        name = tr(item.get("customParams2"), self.text_map)
                        value = item.get("customParams3")
                        if sub_kind == "PlayVideo_Toast_FlavorDecrease":
                            try:
                                value = -abs(int(value))
                            except (TypeError, ValueError):
                                value = f"-{value}" if value not in (None, "") else value
                        rows.append(
                            {
                                "storyline_id": self.storyline_id,
                                "video_hash": h,
                                "video_key": video_key,
                                "effect_kind": sub_kind,
                                "effect_key": key,
                                "effect_name": name,
                                "effect_display_name": flavor_display_name(key, name),
                                "effect_value": value,
                                "upstream_choices": self.upstream_choices(h),
                            }
                        )
        return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def write_report(
    path: Path,
    conditions: list[dict[str, Any]],
    variable_nodes: list[dict[str, Any]],
    video_effects: list[dict[str, Any]],
) -> None:
    unknown_conditions = [c for c in conditions if any("var:" in expr or "<missing:" in expr for expr in c["expressions"])]
    lines = [
        "# Storyline Mechanics Audit",
        "",
        "这个目录从运行时恢复的 Storyline JSON 中抽取路径判断机制，不依赖 HTML 页面。",
        "",
        "## 覆盖范围",
        "",
        f"- 条件节点：{len(conditions)}",
        f"- 全局变量 getter/setter 节点：{len(variable_nodes)}",
        f"- 视频片段内数值/属性变化：{len(video_effects)}",
        f"- 表达式仍含未知变量 hash 的条件：{len(unknown_conditions)}",
        "",
        "## 关键结论",
        "",
        "- `Function_Storyline_If` 的判断参数可以从 `parameterLink` 反向还原。",
        "- 数值/效果的唯一源文件是 `video_effects.jsonl`；选项效果由页面根据其中的 `upstream_choices.distance == 1` 动态推导，不再生成第二份选择效果文件。",
        "- 部分剧情数值变化不在 `Global_GlobalVariableSetter`，而在 `PlayVideo_VideoKey_Variable_Int` 子节点里。",
        "- `PlayVideo_Toast_DimensionIncrease` 和 `PlayVideo_Toast_FlavorIncrese` 是展示层提示，但也可作为效果交叉验证。",
        "",
        "## 样例：王皇后信任度判断",
        "",
    ]
    for row in conditions:
        if "王皇后信任度" in row.get("annotation", "") or any("王皇后" in expr for expr in row.get("expressions", [])):
            lines.extend(
                [
                    f"- Storyline: `{row['storyline_id']}`",
                    f"- 节点：`{row['node_hash']}` / {row.get('annotation')}",
                    f"- 表达式：`{' AND '.join(row.get('expressions') or [])}`",
                    f"- 结果：`{json.dumps(row.get('outcomes'), ensure_ascii=False)}`",
                    "",
                ]
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", default="tools/recovered_storyline_json_live_26692")
    parser.add_argument("--out-dir", default="data/game/storyline_mechanics")
    parser.add_argument("--text-index", default="data/index/roadtoempress2/textclient_zh.jsonl")
    args = parser.parse_args()

    json_dir = Path(args.json_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    text_map = load_text_map(Path(args.text_index))

    all_conditions: list[dict[str, Any]] = []
    all_variable_nodes: list[dict[str, Any]] = []
    all_video_effects: list[dict[str, Any]] = []
    for path in sorted(json_dir.glob("*.json")):
        raw = read_json(path)
        mechanics = StorylineMechanics(path.stem, raw, text_map)
        all_conditions.extend(mechanics.extract_conditions())
        all_variable_nodes.extend(mechanics.extract_global_variable_nodes())
        all_video_effects.extend(mechanics.extract_video_effects())

    write_jsonl(out_dir / "conditions.jsonl", all_conditions)
    write_jsonl(out_dir / "global_variable_nodes.jsonl", all_variable_nodes)
    write_jsonl(out_dir / "video_effects.jsonl", all_video_effects)
    write_report(out_dir / "README.md", all_conditions, all_variable_nodes, all_video_effects)
    print(
        f"conditions={len(all_conditions)} variable_nodes={len(all_variable_nodes)} "
        f"video_effects={len(all_video_effects)} out={out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
