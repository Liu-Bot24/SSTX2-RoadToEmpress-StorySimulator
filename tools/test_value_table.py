#!/usr/bin/env python3
"""value_table 预计算的回归测试。用真实数据锁住核心规则。

跑法: python tools/test_value_table.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_value_table as B

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "data" / "game" / "storyline_graph" / "storyline_graph_data.json"


def build():
    graph, nodes, effects, in_edges = B.build_indexes()
    return B.build_tables(nodes, effects, in_edges), nodes


def nid_by_videokey(vk):
    d = json.loads(GRAPH.read_text(encoding="utf-8"))
    for ch in d["chapters"]:
        for n in ch["nodes"]:
            if n.get("videoKey") == vk:
                return n["id"]
    return None


def incoming_choice_for_videokey(vk):
    d = json.loads(GRAPH.read_text(encoding="utf-8"))
    target = nid_by_videokey(vk)
    if not target:
        return None, None
    for ch in d["chapters"]:
        for n in ch["nodes"]:
            for edge in n.get("edges", []):
                if edge.get("targetId") == target and edge.get("choiceIndex") is not None:
                    return n["id"], str(edge["choiceIndex"])
    return None, None


def main():
    table, nodes = build()
    fails = []

    def check(cond, msg):
        if cond:
            print(f"  ok  {msg}")
        else:
            fails.append(msg)
            print(f"FAIL  {msg}")

    # 1. 选项区分:多选项节点各 index 值不全相同
    multi = [(k, v) for k, v in table["options"].items() if len(v) > 1]
    check(len(multi) > 0, f"存在多选项节点({len(multi)} 个)")
    differing = 0
    for _, by_idx in multi:
        sigs = {json.dumps(sorted((r["statKey"], r["value"]) for r in rows)) for rows in by_idx.values()}
        if len(sigs) > 1:
            differing += 1
    check(differing > 0, f"多选项节点中存在各选项数值不同的情形({differing} 个)")

    # 2. QTE 镜像剔除:已知 QTE 后续视频 009_052 主数值应被剔除
    vid = nid_by_videokey("009_052")
    check(vid is not None, "找到镜像视频 009_052")
    if vid:
        toast_in_video = [r for r in table["video"].get(vid, []) if r["statKey"].startswith("dimension:")]
        check(not toast_in_video, "镜像视频 009_052 的主数值已从 video 显示剔除")
        toast_in_counted = [r for r in table["counted"]["nodes"].get(vid, []) if r["statKey"].startswith("dimension:")]
        check(not toast_in_counted, "镜像视频 009_052 的主数值已从 counted 剔除")

    def check_choice_mirror(vk, stat_name, value):
        vid = nid_by_videokey(vk)
        choice_id, choice_index = incoming_choice_for_videokey(vk)
        video_dims = [r for r in table["video"].get(vid, []) if r["group"] == "main"] if vid else []
        counted_dims = [r for r in table["counted"]["nodes"].get(vid, []) if r["group"] == "main"] if vid else []
        option_rows = table["counted"]["choices"].get(choice_id, {}).get(choice_index, [])
        check(vid is not None and choice_id is not None, f"找到选项镜像链路 {vk}")
        check(not video_dims and not counted_dims, f"{vk} 镜像视频主数值不重复显示/计数")
        check(any(r["name"] == stat_name and r["value"] == value for r in option_rows),
              f"{vk} 主数值归属上游选项 {stat_name}+{value}")

    # 非零主数值相同、但上游含 0 值的镜像也必须剔除视频重复项。
    check_choice_mirror("012_C011B_063", "谋略", 3)
    check_choice_mirror("020_C020D_012", "果决", 3)
    check_choice_mirror("020_C050B_023", "谋略", 3)

    def check_preview_only_choice(vk, choice_index):
        choice_id = nid_by_videokey(vk)
        idx = str(choice_index)
        option_rows = table["options"].get(choice_id, {}).get(idx, []) if choice_id else []
        counted_rows = table["counted"]["choices"].get(choice_id, {}).get(idx, []) if choice_id else []
        check(choice_id is not None, f"找到汇总预览选项 {vk}#{idx}")
        check(not option_rows, f"{vk}#{idx} 汇总预览不在选项上重复显示")
        check(not counted_rows, f"{vk}#{idx} 汇总预览不进入 counted.choices")

    def check_video_keeps_main(vk, stat_name, value):
        vid = nid_by_videokey(vk)
        video_dims = [r for r in table["video"].get(vid, []) if r["group"] == "main"] if vid else []
        counted_dims = [r for r in table["counted"]["nodes"].get(vid, []) if r["group"] == "main"] if vid else []
        check(
            any(r["name"] == stat_name and r["value"] == value for r in video_dims)
            and any(r["name"] == stat_name and r["value"] == value for r in counted_dims),
            f"{vk} 视频卡主数值保留 {stat_name}+{value}",
        )

    # 这些选项值是后续连续剧情节点的汇总预览,只保留视频卡显示与计数。
    check_preview_only_choice("CL270_010_105", 0)
    check_preview_only_choice("CL270_010_105", 1)
    check_video_keeps_main("010_C270A_106", "声望", 3)
    check_video_keeps_main("010_110", "谋略", 10)
    check_preview_only_choice("CL030_011_024", 1)
    check_video_keeps_main("011_C030B_026", "谋略", 2)
    check_video_keeps_main("011_031", "韧性", 1)
    check_preview_only_choice("CL070_009_020", 0)
    check_preview_only_choice("CL070_009_020", 2)
    check_video_keeps_main("010_025", "韧性", 15)
    check_video_keeps_main("QL090_010_030", "谋略", 5)
    check_preview_only_choice("CL070_013_033", 2)
    check_video_keeps_main("013_119", "谋略", 15)
    check_preview_only_choice("CL170_013_069", 0)
    check_preview_only_choice("CL170_013_069", 1)
    check_video_keeps_main("013_C170A_070", "野心", 10)
    check_video_keeps_main("013_C170B_071", "果决", 4)
    check_video_keeps_main("013_126", "谋略", 20)
    check_preview_only_choice("CL090_015_057", 0)
    check_preview_only_choice("CL090_015_057", 1)
    check_video_keeps_main("015_CL090A_058", "野心", 5)
    check_video_keeps_main("015_CL090A_058", "果决", 5)
    check_video_keeps_main("015_CL090B_059", "韧性", 7)
    check_video_keeps_main("015_060", "谋略", 50)
    check_preview_only_choice("CL040_015_019", 1)
    check_video_keeps_main("015_C040B_022", "韧性", 30)
    check_preview_only_choice("C130_018_058", 1)
    check_video_keeps_main("018_C130B_060", "野心", 20)
    check_preview_only_choice("CL100_009_047", 0)
    check_video_keeps_main("009_C100B_050", "韧性", 3)
    check_preview_only_choice("CL020_013_010", 2)
    check_video_keeps_main("013_019", "谋略", 2)
    check_preview_only_choice("CL210_013_114", 0)
    check_video_keeps_main("013_117", "谋略", 20)
    check_preview_only_choice("CL190_010_060", 1)
    check_video_keeps_main("010_C190B_062", "谋略", 10)
    check_preview_only_choice("CL150_013_054", 1)
    check_video_keeps_main("QL220_013_058", "果决", 2)
    check_preview_only_choice("CL170_010_146", 0)
    check_video_keeps_main("010_C170A_053", "韧性", 2)
    check_preview_only_choice("CL140_013_050", 0)
    check_video_keeps_main("N09_013_C140A_051", "谋略", 1)
    check_preview_only_choice("CL080_015_037", 2)
    check_video_keeps_main("015_CL080C_042", "果决", 3)
    check_video_keeps_main("015_CL080B_045", "野心", 15)
    check_preview_only_choice("CL070_017_041", 2)
    check_video_keeps_main("017_C070C_046", "韧性", 3)
    check_video_keeps_main("017_047", "声望", 50)
    check_preview_only_choice("CL090_018_041", 1)
    check_video_keeps_main("018_C090B_044", "果决", 50)
    check_preview_only_choice("CL181_020_077", 0)
    check_preview_only_choice("CL181_020_077", 1)

    # 3. 选项主数值进入 counted.choices
    sample_choice = multi[0][0]
    check(sample_choice in table["counted"]["choices"], "选项主数值进入 counted.choices")

    # 4. 关系数值保留(存在至少一个非主数值的 video 显示项)
    has_relation = any(
        any(not r["statKey"].startswith("dimension:") for r in rows)
        for rows in table["video"].values()
    )
    check(has_relation, "视频关系/路线数值被保留")

    def relations_of(vk):
        i = nid_by_videokey(vk)
        return [(r["name"], r["value"]) for r in table["video"].get(i, [])] if i else []

    # 5. 关系 Var↔Toast 同概念同值合并(CodeX 核实的 17 处之一);中文名,不暴露内部字段
    rel_038 = relations_of("010_C110B_038")
    trust_038 = [r for r in rel_038 if r[0] == "王皇后信任度"]
    check(len(trust_038) == 1 and trust_038[0][1] == 5, "010_C110B_038 王皇后信任度+5 只计一次")
    rel_330 = relations_of("S03_C330A_003")
    check(any(n == "礼泰好感度" for n, _ in rel_330) and not any("favor_litai" in n for n, _ in rel_330),
          "S03_C330A_003 favor_litai 合并为礼泰好感度,不暴露内部字段")

    # 6. 关系不同概念/不同值保留(CodeX 核实的 5 处之一)
    rel_200 = relations_of("010_C200C_067")
    names_200 = {n for n, _ in rel_200}
    check("王皇后信任度" in names_200 and "萧舒妃怒气值" in names_200,
          "010_C200C_067 两个不同关系都保留")

    # 7. 人工核定的主数值合计(对照游戏剧情,写入映射表覆盖)
    def main_totals(vk):
        rows = table["counted"]["nodes"].get(nid_by_videokey(vk), [])
        out = {}
        for r in rows:
            if r.get("group") == "main":
                out[r["name"]] = out.get(r["name"], 0) + r["value"]
        return out

    def video_main_totals(vk):
        rows = table["video"].get(nid_by_videokey(vk), [])
        out = {}
        for r in rows:
            if r.get("group") == "main":
                out[r["name"]] = out.get(r["name"], 0) + r["value"]
        return out

    def choice_main_totals(vk, choice_index, table_key):
        source = table["counted"]["choices"] if table_key == "counted" else table[table_key]
        rows = source.get(nid_by_videokey(vk), {}).get(str(choice_index), [])
        out = {}
        for r in rows:
            if r.get("group") == "main":
                out[r["name"]] = out.get(r["name"], 0) + r["value"]
        return out

    check(main_totals("017_047") == {"韧性": 60, "谋略": 60, "野心": 30, "果决": 20, "声望": 50},
          "017_047 两段场景分别累加(韧性60/谋略60/野心30/果决20/声望50)")
    check(main_totals("018_C090B_044") == {"野心": 22, "谋略": 2, "声望": 20, "果决": 50},
          "018_C090B_044 以视频为准(果决50,野心22)")
    shitan_choice = {"果决": 20, "声望": 20}
    shitan_video = {"果决": 2}
    for table_key in ("options", "counted"):
        check(choice_main_totals("CL020_012_004", 0, table_key) == shitan_choice,
              f"CL020_012_004#0 {table_key} 拆分后只保留果决20/声望20")
    check(video_main_totals("012_C020A_005") == shitan_video and main_totals("012_C020A_005") == shitan_video,
          "012_C020A_005 保留视频果决2")
    check(shitan_choice["果决"] + shitan_video["果决"] == 22,
          "皇后的试探果决合计仍为22,其中选项20/视频2")
    c080_choice = {"谋略": 10}
    c080_video = {"谋略": 3, "果决": 3}
    for table_key in ("options", "counted"):
        check(choice_main_totals("CL080_018_035", 1, table_key) == c080_choice,
              f"CL080_018_035#1 {table_key} 只保留选项谋略10")
    check(video_main_totals("018_C080C_040") == c080_video and main_totals("018_C080C_040") == c080_video,
          "018_C080C_040 保留视频谋略3/果决3")
    for table_key in ("options", "counted"):
        check(choice_main_totals("CL070_013_033", 2, table_key) == {},
              f"CL070_013_033#2 {table_key} 不保留重复预览值")
    check(video_main_totals("013_C070C_036") == {} and main_totals("013_C070C_036") == {},
          "013_C070C_036 只保留实测臣服度提示,不显示/计数韧10/野10")
    c070c_rel = relations_of("013_C070C_036")
    check(c070c_rel == [("季怀衷臣服度", 1)], "013_C070C_036 保留季怀衷臣服度+1")
    check(video_main_totals("013_119") == {"谋略": 15, "野心": 5, "果决": 10, "声望": 5}
          and main_totals("013_119") == {"谋略": 15, "野心": 5, "果决": 10, "声望": 5},
          "013_119 保留视频总值(谋15/野5/果10/声5)")
    for idx in (0, 1):
        for table_key in ("options", "counted"):
            check(choice_main_totals("CL170_013_069", idx, table_key) == {},
                  f"CL170_013_069#{idx} {table_key} 不保留重复预览值")
    check(video_main_totals("013_C170A_070") == {"野心": 10}
          and main_totals("013_C170A_070") == {"野心": 10},
          "013_C170A_070 保留视频野心10")
    check(video_main_totals("013_C170B_071") == {"果决": 4}
          and main_totals("013_C170B_071") == {"果决": 4},
          "013_C170B_071 保留视频果决4")
    check(video_main_totals("013_126") == {"谋略": 20, "野心": 20, "声望": 20}
          and main_totals("013_126") == {"谋略": 20, "野心": 20, "声望": 20},
          "013_126 保留视频总值(谋20/野20/声20)")
    for table_key in ("options", "counted"):
        check(choice_main_totals("CL080_015_037", 2, table_key) == {},
              f"CL080_015_037#2 {table_key} 不保留重复预览值")
    check(video_main_totals("015_CL080C_042") == {"果决": 3}
          and main_totals("015_CL080C_042") == {"果决": 3},
          "015_CL080C_042 保留视频果决3")
    check(video_main_totals("015_CL080B_045") == {"野心": 15, "声望": 15}
          and main_totals("015_CL080B_045") == {"野心": 15, "声望": 15},
          "015_CL080B_045 保留视频野心15/声望15")
    chusui_video = {"韧性": 30, "谋略": 30, "野心": 30, "果决": 30, "声望": 30}
    for table_key in ("options", "counted"):
        check(choice_main_totals("CL040_015_019", 1, table_key) == {},
              f"CL040_015_019#1 {table_key} 不保留选项预览值")
    check(video_main_totals("015_C040B_022") == chusui_video and main_totals("015_C040B_022") == chusui_video,
          "015_C040B_022 保留舌战楚遂良视频主体(五维各30)")
    yimu_a_branch = {"野心": 5, "果决": 5}
    yimu_b_branch = {"韧性": 7}
    yimu_tail = {"韧性": 40, "谋略": 50, "野心": 50, "果决": 40, "声望": 50}
    for idx in (0, 1):
        check(choice_main_totals("CL090_015_057", idx, "options") == {},
              f"CL090_015_057#{idx} 选项不显示实测不存在的主数值")
        check(choice_main_totals("CL090_015_057", idx, "counted") == {},
              f"CL090_015_057#{idx} 选项不计入实测不存在的主数值")
    check(video_main_totals("015_CL090A_058") == yimu_a_branch and main_totals("015_CL090A_058") == yimu_a_branch,
          "015_CL090A_058 保留 A 分支小值(野5/果5)")
    check(video_main_totals("015_CL090B_059") == yimu_b_branch and main_totals("015_CL090B_059") == yimu_b_branch,
          "015_CL090B_059 保留 B 分支小值(韧7)")
    check(video_main_totals("015_060") == yimu_tail and main_totals("015_060") == yimu_tail,
          "015_060 保留姨母遗愿后续视频总值(韧40/谋50/野50/果40/声50)")
    waner_choice_a = {"谋略": 5}
    waner_choice_b = {"韧性": 5}
    waner_video_a = {"韧性": 5}
    waner_video_b = {"谋略": 5}
    waner_tail = {"韧性": 35, "谋略": 40, "声望": 30}
    for table_key in ("options", "counted"):
        check(choice_main_totals("CL140_020_050", 0, table_key) == waner_choice_a,
              f"CL140_020_050#0 {table_key} 只保留跨分支补偿谋略5")
        check(choice_main_totals("CL140_020_050", 1, table_key) == waner_choice_b,
              f"CL140_020_050#1 {table_key} 只保留跨分支补偿韧性5")
    check(video_main_totals("020_C140A_051") == waner_video_a and main_totals("020_C140A_051") == waner_video_a,
          "020_C140A_051 保留 A 分支视频韧性5")
    check(video_main_totals("020_C140B_052") == waner_video_b and main_totals("020_C140B_052") == waner_video_b,
          "020_C140B_052 保留 B 分支视频谋略5")
    check(video_main_totals("020_053") == waner_tail and main_totals("020_053") == waner_tail,
          "020_053 保留上官琬儿后续视频原值(韧35/谋40/声30)")
    check(
        {k: waner_choice_a.get(k, 0) + waner_video_a.get(k, 0) for k in ("韧性", "谋略")}
        == {"韧性": 5, "谋略": 5},
        "上官琬儿最终选 A 时跨分支补偿 + 当前视频合计为韧5/谋5",
    )
    check(
        {k: waner_choice_b.get(k, 0) + waner_video_b.get(k, 0) for k in ("韧性", "谋略")}
        == {"韧性": 5, "谋略": 5},
        "上官琬儿最终选 B 时跨分支补偿 + 当前视频合计为韧5/谋5",
    )
    ending_total = {"韧性": 50, "谋略": 50, "野心": 50, "果决": 50, "声望": 100}
    check(video_main_totals("020_C181A_078") == {} and main_totals("020_C181A_078") == {},
          "020_C181A_078 结局前置声望预览不单独显示/计数")
    check(video_main_totals("020_C181B_081") == ending_total and main_totals("020_C181B_081") == ending_total,
          "020_C181B_081 以结局最终视频为总值(韧/谋/野/果50,声100)")
    lizhi_video = {"野心": 20}
    for table_key in ("options", "counted"):
        check(choice_main_totals("C130_018_058", 1, table_key) == {},
              f"C130_018_058#1 {table_key} 不保留选项预览值")
    check(video_main_totals("018_C130B_060") == lizhi_video and main_totals("018_C130B_060") == lizhi_video,
          "018_C130B_060 保留礼治线视频野心20")

    # 8. QTE 例外:后续无镜像视频的 QTE 自身主数值必须保留
    i_qte = nid_by_videokey("QL090_010_030")
    qte_dims = [r for r in table["counted"]["nodes"].get(i_qte, []) if r["statKey"].startswith("dimension:")]
    check(len(qte_dims) > 0, "QTE 例外 QL090_010_030 自身主数值保留(后续无镜像)")

    print()
    if fails:
        print(f"{len(fails)} 项失败")
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
