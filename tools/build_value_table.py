#!/usr/bin/env python3
"""场外预计算:把固定剧情图谱 + 机制数据算成一张 value_table.json。

页面运行时只查这张表 + 沿固定路线确定相加,不在运行时做模糊归因/去重。

输出结构:
  options: { choiceNodeId: { choiceIndex(str): [ {name, value, statKey} ] } }
           选项卡显示的主数值(每个选项区分)。
  video:   { nodeId: [ {name, value, statKey} ] }
           剧情影响显示值:关系/路线值恒保留;主数值若为上游(选项/QTE)镜像则剔除。
  counted: { choices: {choiceNodeId: {idx: [...]}}, nodes: {nodeId: [...]} }
           节点对数值面板的贡献。镜像主数值只在"拥有者"(选项/QTE)处计一次。

镜像判定(离线、按图相邻,与运行时选择无关):
  视频 V 的主数值向量,若与其直接上游来源 P(展开该视频的选项,或其 QTE 节点)
  的主数值向量逐项相等,则 V 的主数值是镜像 -> 从 video 显示与 counted 中剔除。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "data" / "game" / "storyline_graph" / "storyline_graph_data.json"
MECH = ROOT / "data" / "game" / "storyline_mechanics"

MAIN_DIM_KINDS = {
    "ShowChoice_SixDimension_Increase",
    "PlayVideo_Toast_DimensionIncrease",
    "QTE_SixDimension_Increase",
}
DIM_NAMES = {
    "dimension:0": "韧性", "dimension:1": "谋略", "dimension:2": "野心",
    "dimension:3": "果决", "dimension:4": "声望",
}
FLAVOR_KINDS = {"PlayVideo_Toast_FlavorIncrese", "PlayVideo_Toast_FlavorDecrease"}
# 这些 ShowChoice 数值是后续连续剧情节点的汇总预览,不是真正的独立选项加值。
# 页面不在选项上重复显示,数值累计只保留后续视频卡的 counted.nodes。
PREVIEW_ONLY_CHOICES = {
    ("CL270_010_105", 0),
    ("CL270_010_105", 1),
    ("CL030_011_024", 1),
    ("CL070_009_020", 0),
    ("CL070_009_020", 2),
    ("CL070_013_033", 2),
    ("CL170_013_069", 0),
    ("CL170_013_069", 1),
    ("CL100_009_047", 0),
    ("CL090_015_057", 0),
    ("CL090_015_057", 1),
    ("CL080_015_037", 2),
    ("CL070_017_041", 2),
    ("CL090_018_041", 1),
    ("CL040_015_019", 1),
    ("C130_018_058", 1),
    ("CL020_013_010", 2),
    ("CL210_013_114", 0),
    ("CL190_010_060", 1),
    ("CL150_013_054", 1),
    ("CL170_010_146", 0),
    ("CL140_013_050", 0),
    ("CL181_020_077", 0),
    ("CL181_020_077", 1),
}
# 上官琬儿问答循环:两个分支都必须看过才能继续。
# 选项原始值是后续汇总预览,这里只保留跨分支补偿的小映射。
MANUAL_CHOICE_MAIN_TOTALS = {
    # 皇后的试探:选项果决22包含后续视频果决2,这里只保留选项侧果决20。
    ("CL020_012_004", 0): {"dimension:3": 20, "dimension:4": 20},
    # 趁陛下养疾除去礼泰:选项原始值含后续视频谋3/果3,这里只保留选项侧谋略10。
    ("CL080_018_035", 1): {"dimension:1": 10},
    ("CL140_020_050", 0): {"dimension:1": 5},
    ("CL140_020_050", 1): {"dimension:0": 5},
}
# 人工拆分后不再单独显示/计数主数值的视频节点。
SUPPRESS_MAIN_VIDEO_KEYS = {
    "013_C070C_036",
    "020_C181A_078",
}
# 内部变量名 -> 中文显示名(build_indexes 从 conditions 填充)
VAR_DISPLAY_DEFAULTS = {
    "liyifu": "李义府招揽值",
}
VAR_DISPLAY = {}


def canonical_concept(e):
    """关系/路线值的规范概念名:Flavor=人物+关系类型;Var=内部名映射中文;其它=原名。
    用作 statKey 与显示名,使"内部变量"与"中文 Toast"两种表达归一、可去重。"""
    kind = e.get("effect_kind")
    if kind in FLAVOR_KINDS:
        return f"{e.get('effect_key', '')}{e.get('effect_name', '')}"
    if kind == "PlayVideo_VideoKey_Variable_Int":
        key, name = e.get("effect_key", ""), e.get("effect_name", "")
        return VAR_DISPLAY.get(key) or VAR_DISPLAY.get(name) or name or key
    return e.get("effect_name") or e.get("effect_key") or ""


def load_jsonl(path: Path) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def to_number(v):
    try:
        n = float(v)
        return int(n) if n == int(n) else n
    except (TypeError, ValueError):
        return 0


def build_indexes():
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    nodes_by_id = {}
    node_id_by_mk = {}  # (storyline_id, hash) -> node_id
    for ch in graph["chapters"]:
        for n in ch["nodes"]:
            nodes_by_id[n["id"]] = n
            node_id_by_mk[(n["storylineId"], n["hash"])] = n["id"]

    video_effects = load_jsonl(MECH / "video_effects.jsonl")
    effects_by_node = defaultdict(list)
    for e in video_effects:
        nid = node_id_by_mk.get((e["storyline_id"], e["video_hash"]))
        if nid:
            effects_by_node[nid].append(e)

    # 内部变量名 -> 中文显示名(来自 conditions 的权威映射),供关系值去重与命名归一
    VAR_DISPLAY.clear()
    VAR_DISPLAY.update(VAR_DISPLAY_DEFAULTS)
    for c in load_jsonl(MECH / "conditions.jsonl"):
        for k, v in (c.get("variable_display_names") or {}).items():
            if k and v:
                VAR_DISPLAY[str(k)] = str(v)

    in_edges = defaultdict(list)  # target_node_id -> [(source_node_id, edge)]
    for n in nodes_by_id.values():
        for edge in n.get("edges", []):
            tid = edge.get("targetId")
            if tid:
                in_edges[tid].append((n["id"], edge))

    return graph, nodes_by_id, effects_by_node, in_edges


# ---------- effect 格式化与向量 ----------
def is_main_dim(e):
    return e.get("effect_kind") in MAIN_DIM_KINDS


def is_noop(e):
    return "Increase" in str(e.get("effect_kind", "")) and to_number(e.get("effect_value")) == 0


def is_preview_only_choice(e, src):
    try:
        choice_index = int(src.get("choice_index"))
    except (TypeError, ValueError):
        return False
    return (e.get("video_key"), choice_index) in PREVIEW_ONLY_CHOICES


def stat_key(e):
    if is_main_dim(e):
        return e.get("effect_key", "")
    # 关系/路线值用规范概念名作 statKey,使变量写入与 Toast 两种表达归一
    return canonical_concept(e)


def display_name(e):
    if is_main_dim(e):
        return DIM_NAMES.get(e.get("effect_key", ""), e.get("effect_name") or "")
    return canonical_concept(e)


MAIN_VALUE_STATS = {"韧性", "谋略", "野心", "果决", "声望"}

# 人工核定的主数值合计(对照游戏剧情确认,代码无法自行判定的节点)。
# 按 videoKey 覆盖该节点的主数值(五维);关系/路线值不受影响。
# 依据见 docs/same-dimension-multivalue-review.md。
MANUAL_MAIN_TOTALS = {
    # 两段不同场景(出征+内政)分别加值,合计保留:韧性30+30,谋略30+30,野心30,果决20,声望30+20
    "017_047": {"dimension:0": 60, "dimension:1": 60, "dimension:2": 30, "dimension:3": 20, "dimension:4": 50},
    # 以视频为准:野心20+2、谋略2、声望20、果决50
    "018_C090B_044": {"dimension:2": 22, "dimension:1": 2, "dimension:4": 20, "dimension:3": 50},
    # 结局结算:声望40+60=100,其余各50
    "020_C181B_081": {"dimension:0": 50, "dimension:1": 50, "dimension:2": 50, "dimension:3": 50, "dimension:4": 100},
}


def value_group(name, e):
    import re as _re
    if is_main_dim(e) or name in MAIN_VALUE_STATS:
        return "main"
    if _re.search(r"好感|信任|亲密|疑虑|满意|臣服|认可|怒气|羁绊|说服", name or ""):
        return "relation"
    return "plot"


def fmt(e):
    name = display_name(e)
    return {
        "name": name,
        "value": to_number(e.get("effect_value")),
        "statKey": stat_key(e),
        "group": value_group(name, e),
    }


def manual_main_rows(totals):
    return [
        {"name": DIM_NAMES[k], "value": v, "statKey": k, "group": "main"}
        for k, v in totals.items()
    ]


def main_vector(effects):
    v = defaultdict(int)
    for e in effects:
        value = to_number(e.get("effect_value"))
        if is_main_dim(e) and value:
            v[e.get("effect_key")] += value
    return dict(v)


def option_main_vector(effects_by_node, node_id, choice_index):
    v = defaultdict(int)
    for e in effects_by_node.get(node_id, []):
        if e.get("effect_kind") != "ShowChoice_SixDimension_Increase":
            continue
        value = to_number(e.get("effect_value"))
        if not value:
            continue
        for src in e.get("upstream_choices", []):
            if src.get("distance") == 1 and src.get("choice_index") == choice_index:
                v[e.get("effect_key")] += value
    return dict(v)


def qte_main_vector(effects_by_node, node_id):
    v = defaultdict(int)
    for e in effects_by_node.get(node_id, []):
        value = to_number(e.get("effect_value"))
        if e.get("effect_kind") == "QTE_SixDimension_Increase" and value:
            v[e.get("effect_key")] += value
    return dict(v)


def toast_main_vector(effects_by_node, node_id):
    v = defaultdict(int)
    for e in effects_by_node.get(node_id, []):
        value = to_number(e.get("effect_value"))
        if e.get("effect_kind") == "PlayVideo_Toast_DimensionIncrease" and value:
            v[e.get("effect_key")] += value
    return dict(v)


def is_mirror_video(node_id, nodes_by_id, effects_by_node, in_edges):
    """V 的视频主数值若与直接上游(展开它的选项 / 其 QTE 节点)主数值逐项相等 -> 镜像。"""
    tv = toast_main_vector(effects_by_node, node_id)
    if not tv:
        return False
    for pid, edge in in_edges.get(node_id, []):
        p = nodes_by_id.get(pid)
        if not p:
            continue
        if p.get("kind") == "ShowChoice" and edge.get("choiceIndex") is not None:
            if (p.get("videoKey"), int(edge["choiceIndex"])) in PREVIEW_ONLY_CHOICES:
                continue
            if option_main_vector(effects_by_node, pid, edge["choiceIndex"]) == tv:
                return True
        if qte_main_vector(effects_by_node, pid) == tv:
            return True
    return False


def dedupe(rows):
    seen = set()
    out = []
    for r in rows:
        k = (r["name"], r["value"], r["statKey"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def build_tables(nodes_by_id, effects_by_node, in_edges):
    node_id_by_video_key = {
        node.get("videoKey"): nid
        for nid, node in nodes_by_id.items()
        if node.get("videoKey")
    }

    # 选项主数值:按 (choiceNodeId, choiceIndex) 归属
    options = {}
    for nid, effs in effects_by_node.items():
        for e in effs:
            if e.get("effect_kind") != "ShowChoice_SixDimension_Increase" or is_noop(e):
                continue
            for src in e.get("upstream_choices", []):
                if src.get("distance") != 1:
                    continue
                if is_preview_only_choice(e, src):
                    continue
                cnid = f"{e['storyline_id']}:{src.get('choice_hash', '')}"
                idx = str(src.get("choice_index"))
                options.setdefault(cnid, {}).setdefault(idx, []).append(fmt(e))
    for (video_key, choice_index), totals in MANUAL_CHOICE_MAIN_TOTALS.items():
        cnid = node_id_by_video_key.get(video_key)
        if cnid:
            options.setdefault(cnid, {})[str(choice_index)] = manual_main_rows(totals)
    for cnid, by_idx in options.items():
        for idx in by_idx:
            by_idx[idx] = dedupe(by_idx[idx])
    counted_choices = {cnid: {i: list(v) for i, v in by_idx.items()} for cnid, by_idx in options.items()}

    # 视频显示 + 节点计数(主数值镜像剔除,关系恒保留)
    video = {}
    counted_nodes = {}
    for nid, node in nodes_by_id.items():
        effs = effects_by_node.get(nid, [])
        if not effs:
            continue
        override = MANUAL_MAIN_TOTALS.get(node.get("videoKey"))
        suppress_main = node.get("videoKey") in SUPPRESS_MAIN_VIDEO_KEYS
        mirror = is_mirror_video(nid, nodes_by_id, effects_by_node, in_edges) and not override
        vid_list, cnt_list = [], []
        for e in effs:
            if is_noop(e):
                continue
            if e.get("effect_kind") == "ShowChoice_SixDimension_Increase":
                continue  # 归选项,不在视频/节点重复
            if is_main_dim(e) and override:
                continue  # 人工核定节点:主数值改用 override,跳过原始主数值
            if is_main_dim(e) and suppress_main:
                continue  # 人工拆分的小分支主数值不再单独显示/计数
            if e.get("effect_kind") == "PlayVideo_Toast_DimensionIncrease" and mirror:
                continue  # 镜像主数值剔除
            row = fmt(e)
            vid_list.append(row)
            cnt_list.append(row)
        if override:
            # 注入人工核定的主数值合计(置于关系值之前)
            manual = manual_main_rows(override)
            vid_list = manual + vid_list
            cnt_list = manual + cnt_list
        if vid_list:
            video[nid] = dedupe(vid_list)
        if cnt_list:
            counted_nodes[nid] = dedupe(cnt_list)

    return {
        "options": options,
        "video": video,
        "counted": {"choices": counted_choices, "nodes": counted_nodes},
    }


def main():
    graph, nodes_by_id, effects_by_node, in_edges = build_indexes()
    table = build_tables(nodes_by_id, effects_by_node, in_edges)
    out = GRAPH.parent / "value_table.json"
    out.write_text(json.dumps(table, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n_opt = sum(len(v) for v in table["options"].values())
    print(f"value_table.json: 选项节点 {len(table['options'])}(共 {n_opt} 选项)"
          f", 视频显示 {len(table['video'])} 节点, 计数节点 {len(table['counted']['nodes'])}")
    print(f"  -> {out}")


if __name__ == "__main__":
    main()
