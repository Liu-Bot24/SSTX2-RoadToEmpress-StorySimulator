from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "data" / "runtime"
DOSSIERS = ROOT / "data" / "knowledge" / "dossiers"
GRAPH_DATA = ROOT / "data" / "game" / "storyline_graph" / "storyline_graph_data.json"


OVERRIDE_CHARACTER_FILENAMES = {
    ("Character_zhangsuntaiwei", "tag_zhangsuntaiwei"): "长孙太尉__Character_zhangsuntaiwei__tag_zhangsuntaiwei.md",
    ("Character_waner", "tag_waner"): "琬儿__Character_waner__tag_waner.md",
    ("Character_lizhi", "tag_lizhi"): "礼治__Character_lizhi__tag_lizhi.md",
    ("Character_litai", "tag_litai"): "礼泰__Character_litai__tag_litai.md",
}

OVERRIDE_CHARACTER_KEYS = set(OVERRIDE_CHARACTER_FILENAMES)


CHARACTER_IDENTITY_LINKS = {
    ("Character_moying", "tag_moying"): [
        {
            "name": "蜃楼楼主",
            "profile_key": "Character_shenloulouzhu",
            "tag_key": "tag_shenloulouzhu",
            "relation": "蜃楼楼主是莫影在支线中的身份/称号；需要蜃楼楼主背景时读取莫影档案。",
        },
    ],
    ("Character_lishimin", "tag_lishimin"): [
        {
            "name": "盛帝",
            "profile_key": "Character_shengdi",
            "tag_key": "tag_shengdi",
            "relation": "盛帝是本档案人物的帝号/称号；`Character_shengdi` 是没有独立正文的导航 key。",
        },
    ],
}


CHARACTER_ALIAS_REDIRECTS = {
    ("Character_shenloulouzhu", "tag_shenloulouzhu"): {
        "display": "蜃楼楼主",
        "target_display": "莫影",
        "target_profile_key": "Character_moying",
        "target_tag_key": "tag_moying",
        "target_filename": "莫影__Character_moying__tag_moying.md",
        "target_dir": "../../characters",
        "relation": "蜃楼楼主是莫影在支线中的身份/称号。",
    },
    ("Character_shengdi", "tag_shengdi"): {
        "display": "盛帝",
        "target_display": "盛帝",
        "target_profile_key": "Character_lishimin",
        "target_tag_key": "tag_lishimin",
        "target_filename": "盛帝__Character_lishimin__tag_lishimin.md",
        "target_dir": "../../reference/characters",
        "relation": "盛帝是 `Character_lishimin` 对应人物的帝号/称号；此 key 没有独立档案正文。",
    },
}


CHARACTER_DESC_SECTION_OVERRIDES = {
    ("Character_chusuiliang", "tag_chusuiliang", "TID_CharacterConfig_605042"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_lingxiao", "tag_lingxiao", "TID_CharacterConfig_610436"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_lingxiao", "tag_lingxiao", "TID_CharacterConfig_965918"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_lisujie", "tag_lisujie", "TID_CharacterConfig_125854"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_liuguifei", "tag_liuguifei", "TID_CharacterConfig_813022"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_liuxi", "tag_liuxi", "TID_CharacterConfig_833839"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_liuxi", "tag_liuxi", "TID_CharacterConfig_37914"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_lizhong", "tag_lizhong", "TID_CharacterConfig_501761"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_lizhong", "tag_lizhong", "TID_CharacterConfig_409645"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_lizhong", "tag_lizhong", "TID_CharacterConfig_961967"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_moying", "tag_moying", "TID_CharacterConfig_266239"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_moying", "tag_moying", "TID_CharacterConfig_224501"): "当前游戏档案文本 - 女帝线/主线",
    ("Character_moying", "tag_moying", "TID_CharacterConfig_439424"): "当前游戏档案文本 - 新世界线/支线",
    ("Character_xiaoshufei", "tag_xiaoshufei", "TID_CharacterConfig_961146"): "当前游戏档案文本 - 女帝线/主线",
}


CHARACTER_SECTION_ORDER = [
    "当前游戏档案文本 - 前情提要",
    "当前游戏档案文本 - 女帝线/主线",
    "当前游戏档案文本 - 新世界线/支线",
    "当前游戏档案文本 - 跨路线共用",
    "当前游戏配置文本",
    "前作/旧作参考文本",
    "其他配置文本",
]


CHARACTER_DESC_SECTION_LOOKUP: dict[tuple[str, str, str], str] | None = None
CHARACTER_ROUTE_REVIEW_ROWS: list[dict[str, str]] = []


OVERRIDE_CHARACTER_DOCS = [
    {
        "display": "琬儿",
        "name_key": "Character_waner",
        "tag_key": "tag_waner",
        "filename": OVERRIDE_CHARACTER_FILENAMES[("Character_waner", "tag_waner")],
        "sections": [
            (
                "当前游戏档案文本",
                [
                    (
                        "TID_CharacterConfig_322388",
                        "上官宜的孙女，因受祖父当年的罪行牵连，被罚入掖庭宫为奴婢。但她自幼熟读诗书，通晓古今，有为政之才，哪怕深陷困境，也不改其志。",
                    ),
                ],
            ),
        ],
        "notes": [
            "本档案目前只包含主线条目。",
            "`Character_shangguanwaner` / `tag_shangguanwaner` 暂作后期身份、旧名或未实装候选，不合并进本档案。",
        ],
    },
    {
        "display": "礼治",
        "name_key": "Character_lizhi",
        "tag_key": "tag_lizhi",
        "filename": OVERRIDE_CHARACTER_FILENAMES[("Character_lizhi", "tag_lizhi")],
        "sections": [
            (
                "当前游戏档案文本 - 女帝线/主线",
                [
                    (
                        "TID_CharacterConfig_114825",
                        "盛朝第三代君主。先帝朝时候，刚入宫为才人的你就和当时身为晋王的他相识，在凶险万分的宫廷中，你们互相拯救和扶持，这份羁绊难以被撼动。",
                    ),
                    (
                        "TID_CharacterConfig_447663",
                        "作为新君，登基后的礼治本想大展鸿图，却不料皇位之下，是权臣和豪族们编织的重重枷锁。但礼治不但继承了父皇的江山，更继承了他的魄力和野心，他，绝不愿当一个傀儡皇帝，唯一缺少的，或许是一个能站在他身边，和他共进退的人……",
                    ),
                    (
                        "TID_CharacterConfig_811315",
                        "尽管有诸多遗憾，但在以无情著称的帝王家，能和礼治携手走完这三十多年的风雨，已是难得。",
                    ),
                ],
            ),
            (
                "当前游戏档案文本 - 新世界线/支线",
                [
                    (
                        "TID_CharacterConfig_113788",
                        "礼治不但继承了父皇的江山，更继承了他的魄力和野心，他心中所愿便是和他心中最在意的那个人一起开创盛世。可那个人心在四方，不在他身侧。",
                    ),
                ],
            ),
            (
                "前作/旧作背景参考",
                [
                    (
                        "TID_CharacterConfig_875203",
                        "大盛皇帝盛帝的第九子，被封为晋王。自礼治九岁丧母后，盛帝将其带在身边，亲自教养。他是所有皇子中最受盛帝怜爱的。",
                    ),
                    (
                        "TID_CharacterConfig_166396",
                        "夜宴上临危不惧化解死局的你，山洞中咫尺之间的你，南山狩猎场上义无反顾救他的你，都一次次地让他动心。江山和美人，他都要。",
                    ),
                    (
                        "TID_CharacterConfig_355102",
                        "亲手为你绘制那把山河伞的时候，他心中想着的，是你在宫中踽踽独行的那些日夜。太极宫的风雪太冷，这把伞若能时时伴你身侧，为你挡去那漫天的刺骨冷意该有多好。",
                    ),
                    (
                        "TID_CharacterConfig_772331",
                        "命运交织，权势翻涌。有些事，结局或许早已注定。可他常常在想，往后的路，你会选择和他携手并进吗？",
                    ),
                ],
            ),
        ],
        "notes": [
            "主线和支线需要分开引用。",
            "乌檀国使者、金象国使者等未实装/DLC 候选与礼治无关，不进入本档案。",
        ],
    },
    {
        "display": "礼泰",
        "name_key": "Character_litai",
        "tag_key": "tag_litai",
        "filename": OVERRIDE_CHARACTER_FILENAMES[("Character_litai", "tag_litai")],
        "sections": [
            (
                "当前游戏档案文本 - 女帝线/主线",
                [
                    (
                        "TID_CharacterConfig_143514",
                        "盛帝的第四子，魏王，先帝时和当时身为才人的你有过交情。他曾有夺嫡的野心，却在最后一刻输给了礼治，不得不离开盛安，去往封地钧州。时光荏苒，不知这些年，他的心态有多少改变？",
                    ),
                ],
            ),
            (
                "当前游戏档案文本 - 新世界线/支线",
                [
                    (
                        "TID_CharacterConfig_210072",
                        "盛帝的第四子，先帝时和曾身为才人的你有过交集。他曾有夺嫡的野心，但最终输给了他的九弟礼治。新帝登基，魏王不得不离开皇城盛安，去往封地钧州。时光荏苒，不知未见面的这些年，他的心态有多少改变？",
                    ),
                    (
                        "TID_CharacterConfig_923106",
                        "在临终之时，魏王长久地握着手中的那枚青雀玉佩出神，鸢飞戾天，这一生，有你来过，魏王没有遗憾。",
                    ),
                ],
            ),
            (
                "前作/旧作背景参考",
                [
                    (
                        "TID_CharacterConfig_278904",
                        "大盛皇帝盛帝最爱重的四皇子，被封为魏王。野心勃勃，极度渴望成为大盛的储君，为达目的，不择手段。不屑痴男怨女的情爱，认为万物皆可利用，万物皆不该成为自己软肋。",
                    ),
                    (
                        "TID_CharacterConfig_662668",
                        "通过暗中布局，礼泰如愿将礼承乾拉下了太子之位。按照立嫡立长的古例，储君之位终将是他的囊中之物。可你的决然离开，让他第一次感受到对手中棋子的失控感，他的心中似乎有什么在变化着。",
                    ),
                    (
                        "TID_CharacterConfig_420744",
                        "“路过”你的家乡利州，“顺便”找工匠为你打造那枚“鸢飞戾天”的时候，他竟觉得忐忑不安，也不知道，你会不会喜欢这个样式？",
                    ),
                    (
                        "TID_CharacterConfig_440284",
                        "下意识挥刀砍向百夫长的那一刻，礼泰便知道，这是他夺嫡之路上走得最错的一步棋。但也是那一刻，他似乎察觉到，比起那九五之尊的皇位，还有更值得他保住的东西。",
                    ),
                ],
            ),
        ],
        "notes": [
            "主线和支线需要分开引用。",
            "茯苓国使者、金象国使者贴身随从等未实装/DLC 候选与礼泰无关，不进入本档案。",
        ],
    },
    {
        "display": "长孙太尉",
        "name_key": "Character_zhangsuntaiwei",
        "tag_key": "tag_zhangsuntaiwei",
        "filename": OVERRIDE_CHARACTER_FILENAMES[("Character_zhangsuntaiwei", "tag_zhangsuntaiwei")],
        "sections": [
            (
                "当前游戏档案文本 - 女帝线/主线",
                [
                    (
                        "TID_CharacterConfig_452062",
                        "盛朝第一重臣，陛下的舅舅，先帝临终前指名他为顾命老臣，让他全力辅佐礼治，他也的确尽职尽责，总览三省，为陛下“分担”了不少政务。然而，作为门阀贵族在朝中的代表，他的野心似乎并不止于此……",
                    ),
                    (
                        "TID_CharacterConfig_940976",
                        "通过手染皇族鲜血的残酷手腕，长孙太尉的真正达到了权倾朝野，却也让礼治彻底寒心。平心而论，太尉这些年也做了不少实事，比如完善律法，编撰《律疏》，就功不可没，但功高震主可就是另一回事了。",
                    ),
                    (
                        "TID_CharacterConfig_992117",
                        "被贬前州后不久，长孙太尉就在流放地投缳自尽，显然是因为无法接受从万人之上到一介庶民的巨大落差，因而选择了短见。尽管生前有罪，陛下还是念在其前曾经的功绩，下诏恢复了他的爵位。",
                    ),
                ],
            ),
            (
                "当前游戏档案文本 - 新世界线/支线",
                [
                    (
                        "TID_CharacterConfig_246646",
                        "盛朝第一重臣，陛下的舅舅，先帝临终前指名他为顾命老臣，让他全力辅佐礼治.然而，他却似乎将“辅佐”和“扶植”画上了等号，俨然成了一个权臣，任何被他视为权力威胁之人，都难逃被清除的厄运，首当其中的便是魏王礼泰。",
                    ),
                ],
            ),
        ],
        "notes": [
            "`Character_zhangsunwuji` / `tag_zhangsunwuji` 是旧历史人物/旧称呼组，不作为当前游戏长孙太尉档案。",
        ],
    },
]


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("&nbsp;", " ")
    return "\n".join(line.strip() for line in value.splitlines()).strip()


def one_line(value: str | None, fallback: str) -> str:
    text = clean_text(value)
    if not text:
        return fallback
    return re.sub(r"\s+", " ", text)


def safe_filename(name: str, fallback: str) -> str:
    name = one_line(name, fallback)
    name = INVALID_FILENAME_CHARS.sub("_", name).strip(" .")
    return name or fallback


def source_scope_label(kind) -> str:
    if kind == 3:
        return "当前游戏配置文本"
    if kind == 1:
        return "前作/旧作参考文本"
    return "其他配置文本"


def route_section_label(routes: set[str]) -> str | None:
    routes = {route for route in routes if route}
    if not routes:
        return None
    if routes == {"女帝线"}:
        return "当前游戏档案文本 - 女帝线/主线"
    if routes == {"新世界线"}:
        return "当前游戏档案文本 - 新世界线/支线"
    if routes == {"前情提要"}:
        return "当前游戏档案文本 - 前情提要"
    return "当前游戏档案文本 - 跨路线共用"


def build_video_route_lookup() -> dict[str, set[str]]:
    if not GRAPH_DATA.exists():
        return {}
    graph = read_json(GRAPH_DATA)
    lookup: dict[str, set[str]] = {}
    for chapter in graph.get("chapters") or []:
        chapter_route = chapter.get("lineTitle") or chapter.get("title") or ""
        for node in chapter.get("nodes") or []:
            route = node.get("lineTitle") or chapter_route
            for key in (node.get("videoKey"), node.get("targetVideoKey")):
                if key and route:
                    lookup.setdefault(str(key), set()).add(str(route))
    return lookup


def character_desc_section_lookup() -> dict[tuple[str, str, str], str]:
    global CHARACTER_DESC_SECTION_LOOKUP
    if CHARACTER_DESC_SECTION_LOOKUP is not None:
        return CHARACTER_DESC_SECTION_LOOKUP

    video_routes = build_video_route_lookup()
    section_lookup: dict[tuple[str, str, str], str] = {}
    unlock_path = RUNTIME / "dossier_unlock_stage_map_20260622.json"
    if not unlock_path.exists():
        CHARACTER_DESC_SECTION_LOOKUP = section_lookup
        return section_lookup

    unlock_data = read_json(unlock_path)
    routes_by_desc: dict[tuple[str, str, str], set[str]] = {}
    for record in unlock_data.get("records") or []:
        if record.get("unlock_type") != "character" or not record.get("desc_tid"):
            continue
        key = (
            str(record.get("target_key") or ""),
            str(record.get("target_tag_key") or ""),
            str(record.get("desc_tid") or ""),
        )
        for loc in record.get("location_entries") or []:
            for field in ("resource_text_0x20", "resource_text_0x28"):
                resource = loc.get(field)
                if resource:
                    routes_by_desc.setdefault(key, set()).update(video_routes.get(str(resource), set()))

    for key, routes in routes_by_desc.items():
        section = route_section_label(routes)
        if section:
            section_lookup[key] = section

    CHARACTER_DESC_SECTION_LOOKUP = section_lookup
    return section_lookup


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def override_character_doc(entry: dict) -> tuple[str, str]:
    lines: list[str] = [f"# {entry['display']}", "", "## 人物档案"]
    tid_refs: list[tuple[str, str]] = []
    for title, items in entry["sections"]:
        lines.extend(["", f"### {title}", ""])
        for index, (tid, text) in enumerate(items, 1):
            lines.append(f"{index}. {text}")
            tid_refs.append((title, tid))

    if entry.get("notes"):
        lines.extend(["", "## 备注", ""])
        for note in entry["notes"]:
            lines.append(f"- {note}")

    lines.extend(
        [
            "",
            "## 检索锚点",
            "",
            f"- profile key：`{entry['name_key']}`",
            f"- tag key：`{entry['tag_key']}`",
            "- 档案状态：可用正文。",
            "- 使用方式：作为当前游戏人物背景资料；摘要或决策分析引用时，仍以当前剧情路线和目标片段为第一事实来源。",
            "- 路线边界：路线小节表示该段档案文本的解锁来源和剧情语境，不表示人物只存在于该路线。",
            "- 跨线引用：没有支线专属文本时，可以用主线基础身份辅助消歧；但不能把主线后续事件、心态变化或结局当成支线已发生事实。",
            "- 路线优先级：同一人物同时有女帝线/主线和新世界线/支线小节时，先按当前路线读取对应小节，再用不冲突的基础身份作补充。",
        ]
    )
    if tid_refs:
        lines.append("- 档案文本锚点：")
        for title, tid in tid_refs:
            lines.append(f"  - {title}：`{tid}`")
    return entry["filename"], "\n".join(lines).rstrip() + "\n"


def write_override_character_docs(character_dir: Path) -> None:
    for entry in OVERRIDE_CHARACTER_DOCS:
        filename, body = override_character_doc(entry)
        (character_dir / filename).write_text(body, encoding="utf-8")


def character_doc(group: dict) -> tuple[str, str, bool]:
    names = group.get("display_name_texts") or []
    display = one_line(names[0] if names else None, group.get("name_key") or "未命名人物")
    name_key = group.get("name_key") or ""
    tag_key = group.get("tag_key") or ""
    filename = safe_filename(f"{display}__{name_key}__{tag_key}.md", safe_filename(name_key or tag_key, "character.md"))

    by_section: dict[str, list[tuple[object, str, str]]] = {}
    seen_texts: set[tuple[object, str, str]] = set()
    variants = group.get("variants") or []
    for variant in variants:
        descriptions = variant.get("descriptions") or []
        for desc in descriptions:
            desc_tid = desc.get("desc_tid") or "unknown desc"
            text = clean_text(desc.get("desc_text"))
            if not text:
                continue
            dedupe_key = (desc.get("kind"), desc_tid, text)
            if dedupe_key in seen_texts:
                continue
            seen_texts.add(dedupe_key)
            section = CHARACTER_DESC_SECTION_OVERRIDES.get((name_key, tag_key, desc_tid))
            if not section and desc.get("kind") == 3:
                section = character_desc_section_lookup().get((name_key, tag_key, desc_tid))
                if not section:
                    CHARACTER_ROUTE_REVIEW_ROWS.append(
                        {
                            "display": display,
                            "name_key": name_key,
                            "tag_key": tag_key,
                            "desc_tid": desc_tid,
                            "stage": "" if desc.get("stage") is None else str(desc.get("stage")),
                            "text": one_line(text, "")[:120],
                        }
                    )
            if not section:
                section = source_scope_label(desc.get("kind"))
            by_section.setdefault(section, []).append((desc.get("stage"), desc_tid, text))

    if not by_section:
        lines = [
            f"# {display}",
            "",
            "## 未恢复正文",
            "",
            "此条目只恢复到人物定位锚点，尚未恢复到可引用的人物档案正文。视频摘要、剧情问答和决策分析默认不要引用本文件。",
            "",
            "## 检索锚点",
            "",
            f"- profile key：`{name_key}`",
            f"- tag key：`{tag_key}`",
            "- 处理方式：仅供后续补采、映射排查和人工确认，不进入常规知识检索。",
        ]
        return filename, "\n".join(lines).rstrip() + "\n", False

    lines: list[str] = [f"# {display}", "", "## 人物档案"]
    tid_refs: list[tuple[str, object, str]] = []
    ordered_sections = [section for section in CHARACTER_SECTION_ORDER if section in by_section]
    ordered_sections.extend(section for section in sorted(by_section) if section not in ordered_sections)
    for section in ordered_sections:
        entries = by_section.get(section) or []
        if not entries:
            continue
        lines.append("")
        lines.append(f"### {section}")
        lines.append("")
        for index, (stage, desc_tid, text) in enumerate(entries, 1):
            lines.append(f"{index}. {text}")
            tid_refs.append((section, stage, desc_tid))

    lines.append("")
    lines.append("## 检索锚点")
    lines.append("")
    lines.append(f"- profile key：`{name_key}`")
    lines.append(f"- tag key：`{tag_key}`")
    lines.append("- 档案状态：可用正文。")
    lines.append("- 使用方式：用于背景检索、人物消歧和路线语境补充。目标视频字幕、路线图和当前运行日志优先级高于本档案。")
    lines.append("- 路线边界：路线小节表示该段档案文本的解锁来源和剧情语境，不表示人物只存在于该路线。")
    lines.append("- 跨线引用：没有支线专属文本时，可以用主线基础身份辅助消歧；但不能把主线后续事件、心态变化或结局当成支线已发生事实。")
    lines.append("- 路线优先级：同一人物同时有女帝线/主线和新世界线/支线小节时，先按当前路线读取对应小节，再用不冲突的基础身份作补充。")
    lines.append("- 旧作边界：前作/旧作参考文本只用于理解过往设定，不覆盖当前游戏配置文本。")
    identity_links = CHARACTER_IDENTITY_LINKS.get((name_key, tag_key)) or []
    if identity_links:
        lines.append("- 关联身份/别名：")
        for link in identity_links:
            lines.append(
                f"  - {link['name']}：`{link['profile_key']}` / `{link['tag_key']}`；{link['relation']}"
            )
    if tid_refs:
        lines.append("- 档案文本锚点：")
        for label, stage, tid in tid_refs:
            stage_text = f"解锁阶段 {stage}" if stage is not None else "解锁阶段未知"
            lines.append(f"  - {label} / {stage_text}：`{tid}`")
    return filename, "\n".join(lines).rstrip() + "\n", True


def character_alias_doc(alias: dict) -> tuple[str, str]:
    filename = safe_filename(
        f"{alias['display']}__{alias['target_profile_key']}__alias.md",
        f"{alias['display']}__alias.md",
    )
    target_path = f"{alias['target_dir']}/{alias['target_filename']}"
    lines = [
        f"# {alias['display']}",
        "",
        "## 人物导航",
        "",
        f"- 关系：{alias['relation']}",
        f"- 指向人物：[{alias['target_display']}]({target_path})",
        f"- target profile key：`{alias['target_profile_key']}`",
        f"- target tag key：`{alias['target_tag_key']}`",
        "- 使用方式：本文件只负责名称、称号或旧 key 导航；需要正文时读取指向人物档案。",
    ]
    return filename, "\n".join(lines).rstrip() + "\n"


def write_character_route_review_doc() -> None:
    review_path = ROOT / "docs" / "development" / "character-route-confirmation-list.md"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        CHARACTER_ROUTE_REVIEW_ROWS,
        key=lambda row: (row["display"], row["name_key"], row["stage"], row["desc_tid"]),
    )
    lines = [
        "# 人物路线需确认清单",
        "",
        "本清单列出当前游戏人物正文中，暂时没有从解锁位置映射到明确路线的条目。它们没有写入任何路线小节；确认后再补入生成规则。",
        "",
        f"- 条目数：{len(rows)}",
        "",
        "| 人物 | profile key | tag key | 阶段 | desc TID | 文本预览 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        text = row["text"].replace("|", "\\|")
        lines.append(
            f"| {row['display']} | `{row['name_key']}` | `{row['tag_key']}` | "
            f"{row['stage']} | `{row['desc_tid']}` | {text} |"
        )
    review_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def group_has_current_game_text(group: dict) -> bool:
    for variant in group.get("variants") or []:
        for desc in variant.get("descriptions") or []:
            if desc.get("kind") == 3 and clean_text(desc.get("desc_text")):
                return True
    return False


def item_doc(entry: dict) -> tuple[str, str, bool]:
    display = one_line(entry.get("resolved_chinese_name") or entry.get("requested_name") or entry.get("name_text"), "未命名词条")
    item_id = entry.get("itemId")
    filename = safe_filename(f"{display}__item-{item_id}.md", f"item-{item_id or 'unknown'}.md")

    descs = entry.get("desc_tid_order_and_text") or []
    usable_descs = []
    for desc in descs:
        text = clean_text(desc.get("text"))
        if not text:
            continue
        usable_descs.append((desc, text))

    if not usable_descs:
        lines = [
            f"# {display}",
            "",
            "## 未恢复正文",
            "",
            "此条目只恢复到物品/词条定位锚点，尚未恢复到可引用的正文。视频摘要、剧情问答和决策分析默认不要引用本文件。",
            "",
            "## 检索锚点",
            "",
            f"- item id：`{item_id}`",
        ]
        if entry.get("name_tid"):
            lines.append(f"- name TID：`{entry.get('name_tid')}`")
        lines.append("- 处理方式：仅供后续补采、映射排查和人工确认，不进入常规知识检索。")
        return filename, "\n".join(lines).rstrip() + "\n", False

    lines: list[str] = [f"# {display}", "", "## 词条文本"]
    tid_refs: list[tuple[object, str]] = []
    for index, (desc, text) in enumerate(usable_descs, 1):
        lines.append("")
        lines.append(f"{index}. {text}")
        tid_refs.append((desc.get("stage_raw"), str(desc.get("desc_tid") or "")))

    lines.append("")
    lines.append("## 检索锚点")
    lines.append("")
    lines.append(f"- item id：`{item_id}`")
    if entry.get("name_tid"):
        lines.append(f"- name TID：`{entry.get('name_tid')}`")
    lines.append("- 词条状态：可用正文。")
    lines.append("- 使用方式：用于背景检索和物品/概念消歧；目标视频字幕、路线图和当前运行日志优先级高于本档案。")
    if tid_refs:
        lines.append("- 词条文本锚点：")
        for stage, tid in tid_refs:
            stage_text = f"解锁阶段 {stage}" if stage is not None else "解锁阶段未知"
            lines.append(f"  - {stage_text}：`{tid}`")
    return filename, "\n".join(lines).rstrip() + "\n", True


def unlock_line(record: dict) -> str:
    location_entries = record.get("location_entries") or []
    locations = []
    for loc in location_entries[:3]:
        resource = loc.get("resource_text_0x20") or loc.get("resource_text_0x28")
        if resource:
            locations.append(str(resource))
    location_text = "、".join(locations) if locations else ""
    desc_text = one_line(record.get("desc_text"), "")
    if len(desc_text) > 90:
        desc_text = desc_text[:87] + "..."
    return (
        f"| `{record.get('toast_id')}` | {record.get('unlock_type') or ''} | "
        f"{record.get('target_name_zh') or ''} | `{record.get('target_key') or ''}` | "
        f"`{record.get('desc_tid') or ''}` | {location_text} | {desc_text} |"
    )


def write_unlock_docs() -> dict:
    data = read_json(RUNTIME / "dossier_unlock_stage_map_20260622.json")
    records = data.get("records") or []
    unlock_dir = DOSSIERS / "unlocks"
    reset_dir(unlock_dir)

    by_type: dict[str, list[dict]] = {}
    for record in records:
        by_type.setdefault(record.get("unlock_type") or "unknown", []).append(record)

    index_lines = [
        "# 解锁线索",
        "",
        "本目录保存 ToastConfig 恢复出的档案解锁线索，用于理解人物/词条文本在游戏流程中的解锁位置。",
        "",
        "## 文件",
        "",
    ]
    for unlock_type in sorted(by_type):
        file_name = f"{safe_filename(unlock_type, 'unknown')}.md"
        rows = by_type[unlock_type]
        index_lines.append(f"- [{unlock_type}]({file_name})：{len(rows)} 条")
        lines = [
            f"# {unlock_type} 解锁线索",
            "",
            "| toast id | 类型 | 目标 | target key | desc TID | 位置 key | 描述预览 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for record in rows:
            lines.append(unlock_line(record))
        (unlock_dir / file_name).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    (unlock_dir / "README.md").write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")
    return {k: len(v) for k, v in by_type.items()}


def main() -> None:
    reset_dir(DOSSIERS)

    character_data = read_json(RUNTIME / "character_dossier_rebuild_candidates_20260622.json")
    character_dir = DOSSIERS / "characters"
    alias_character_dir = DOSSIERS / "aliases" / "characters"
    reference_character_dir = DOSSIERS / "reference" / "characters"
    unresolved_character_dir = DOSSIERS / "unresolved" / "characters"
    character_dir.mkdir(parents=True, exist_ok=True)
    alias_character_dir.mkdir(parents=True, exist_ok=True)
    reference_character_dir.mkdir(parents=True, exist_ok=True)
    unresolved_character_dir.mkdir(parents=True, exist_ok=True)
    write_override_character_docs(character_dir)
    character_count = 0
    reference_character_count = 0
    unresolved_character_count = 0
    skipped_source_rows = 0
    needs_review = 0
    alias_character_count = 0
    character_index: list[tuple[str, str, str, str]] = []
    for entry in OVERRIDE_CHARACTER_DOCS:
        character_index.append(
            (
                entry["filename"],
                entry["display"],
                entry["name_key"],
                entry["tag_key"],
            )
        )
    unresolved_character_index: list[tuple[str, str, str, str]] = []
    reference_character_index: list[tuple[str, str, str, str]] = []
    alias_character_index: list[tuple[str, str, str, str, str]] = []
    for group in character_data.get("groups") or []:
        key = (group.get("name_key"), group.get("tag_key"))
        if key in OVERRIDE_CHARACTER_KEYS:
            skipped_source_rows += 1
            continue
        filename, body, has_text = character_doc(group)
        display = one_line((group.get("display_name_texts") or [None])[0], group.get("name_key") or "未命名人物")
        if has_text:
            row = (
                filename,
                display,
                group.get("name_key") or "",
                group.get("tag_key") or "",
            )
            if group_has_current_game_text(group):
                (character_dir / filename).write_text(body, encoding="utf-8")
                character_index.append(row)
                character_count += 1
            else:
                (reference_character_dir / filename).write_text(body, encoding="utf-8")
                reference_character_index.append(row)
                reference_character_count += 1
            if group.get("needs_manual_confirmation"):
                needs_review += 1
        else:
            alias = CHARACTER_ALIAS_REDIRECTS.get(key)
            if alias:
                alias_filename, alias_body = character_alias_doc(alias)
                (alias_character_dir / alias_filename).write_text(alias_body, encoding="utf-8")
                alias_character_index.append(
                    (
                        alias_filename,
                        alias["display"],
                        group.get("name_key") or "",
                        group.get("tag_key") or "",
                        alias["target_display"],
                    )
                )
                alias_character_count += 1
            else:
                (unresolved_character_dir / filename).write_text(body, encoding="utf-8")
                unresolved_character_index.append(
                    (
                        filename,
                        display,
                        group.get("name_key") or "",
                        group.get("tag_key") or "",
                    )
                )
                unresolved_character_count += 1

    write_character_route_review_doc()

    character_index_lines = [
        "# 人物档案",
        "",
        "本目录只保存已经恢复到正文、可以被摘要或决策分析引用的人物档案。只恢复到 key、没有正文的条目放在 `../unresolved/characters/`。",
        "",
        "## 文件名规则",
        "",
        "- 人物：`显示名__profileKey__tagKey.md`。",
        "- 中文显示名用于语义检索，profile key/tag key 用于和游戏日志、路线图、字幕块里的结构字段做精确匹配。",
        "",
        "## 可用人物档案",
        "",
        "| 人物 | profile key | tag key | 文件 |",
        "| --- | --- | --- | --- |",
    ]
    for filename, display, name_key, tag_key in sorted(character_index, key=lambda x: (x[1], x[2], x[3])):
        character_index_lines.append(f"| {display} | `{name_key}` | `{tag_key}` | [{filename}]({filename}) |")
    character_index_lines.extend(
        [
            "",
            "## 使用规则",
            "",
            "- 人物档案用于背景检索、人物消歧和路线语境补充，不替代目标视频字幕、路线图和当前运行日志。",
            "- 检索锚点只用于匹配日志、路线图、字幕块或配置字段，不作为剧情正文引用。",
            "- 路线小节表示该段档案文本的解锁来源和剧情语境，不表示人物只存在于该路线。",
            "- 没有支线专属文本时，可以用主线基础身份辅助消歧；但不能把主线后续事件、心态变化或结局当成支线已发生事实。",
            "- 同一人物在主线、支线存在不同身份、关系或结局语境时，必须优先读取当前路线对应小节。",
            "- 前作/旧作参考文本只用于理解过往设定，不覆盖当前游戏档案文本。",
            "- `../unresolved/characters/` 里的条目没有可引用正文，默认不参与视频摘要或游戏决策分析。",
        ]
    )
    (character_dir / "README.md").write_text("\n".join(character_index_lines).rstrip() + "\n", encoding="utf-8")

    alias_dir = DOSSIERS / "aliases"
    alias_index_lines = [
        "# 别名和称号导航",
        "",
        "本目录保存没有独立正文、但需要指向已知人物档案的名称、称号或旧 key。默认检索可以读取本目录来做名称跳转，但剧情事实仍以目标档案为准。",
        "",
        "## 目录",
        "",
        f"- [characters](characters/README.md)：人物别名/称号 {alias_character_count} 条。",
    ]
    (alias_dir / "README.md").write_text("\n".join(alias_index_lines).rstrip() + "\n", encoding="utf-8")

    alias_character_lines = [
        "# 人物别名和称号导航",
        "",
        "本目录保存人物别名、称号或旧 key 到已知人物档案的跳转关系。",
        "",
        "| 名称 | source profile key | source tag key | 指向人物 | 文件 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for filename, display, name_key, tag_key, target_display in sorted(alias_character_index, key=lambda x: (x[1], x[2], x[3])):
        alias_character_lines.append(
            f"| {display} | `{name_key}` | `{tag_key}` | {target_display} | [{filename}]({filename}) |"
        )
    (alias_character_dir / "README.md").write_text("\n".join(alias_character_lines).rstrip() + "\n", encoding="utf-8")

    reference_dir = DOSSIERS / "reference"
    reference_index_lines = [
        "# 参考资料",
        "",
        "本目录保存不进入默认摘要检索的补充资料。当前用途是保留只有前作/旧作文本、没有当前游戏档案正文的人物条目。",
        "",
        "## 目录",
        "",
        f"- [characters](characters/README.md)：前作/旧作参考人物 {reference_character_count} 条。",
        "",
        "## 使用规则",
        "",
        "- 默认视频摘要和游戏决策分析不读取本目录。",
        "- 只有在任务明确需要前作背景、旧名溯源或未实装/DLC 候选排查时，才按需读取。",
        "- 本目录资料不能覆盖 `../characters/` 里的当前游戏人物档案。",
    ]
    (reference_dir / "README.md").write_text("\n".join(reference_index_lines).rstrip() + "\n", encoding="utf-8")

    reference_character_lines = [
        "# 前作/旧作参考人物",
        "",
        "本目录保存只有前作/旧作参考文本、没有当前游戏档案正文的人物条目。默认不参与视频摘要和游戏决策分析。",
        "",
        "| 人物 | profile key | tag key | 文件 |",
        "| --- | --- | --- | --- |",
    ]
    for filename, display, name_key, tag_key in sorted(reference_character_index, key=lambda x: (x[1], x[2], x[3])):
        reference_character_lines.append(f"| {display} | `{name_key}` | `{tag_key}` | [{filename}]({filename}) |")
    (reference_character_dir / "README.md").write_text("\n".join(reference_character_lines).rstrip() + "\n", encoding="utf-8")

    item_data = read_json(RUNTIME / "item_collect_dossier_rebuild_candidates_20260622.json")
    item_dir = DOSSIERS / "items"
    unresolved_item_dir = DOSSIERS / "unresolved" / "items"
    item_dir.mkdir(parents=True, exist_ok=True)
    unresolved_item_dir.mkdir(parents=True, exist_ok=True)
    item_count = 0
    unresolved_item_count = 0
    item_needs_review = 0
    item_index: list[tuple[str, str, object]] = []
    unresolved_item_index: list[tuple[str, str, object]] = []
    for entry in item_data.get("entries") or []:
        filename, body, has_text = item_doc(entry)
        display = one_line(entry.get("resolved_chinese_name") or entry.get("requested_name") or entry.get("name_text"), "未命名词条")
        if has_text:
            (item_dir / filename).write_text(body, encoding="utf-8")
            item_index.append((filename, display, entry.get("itemId")))
            item_count += 1
            if entry.get("requires_human_confirmation"):
                item_needs_review += 1
        else:
            (unresolved_item_dir / filename).write_text(body, encoding="utf-8")
            unresolved_item_index.append((filename, display, entry.get("itemId")))
            unresolved_item_count += 1

    item_index_lines = [
        "# 物品/词条档案",
        "",
        "本目录只保存已经恢复到正文、可以被摘要或决策分析引用的物品/词条档案。只恢复到 id、没有正文的条目放在 `../unresolved/items/`。",
        "",
        "## 文件名规则",
        "",
        "- 物品/词条：`显示名__item-ID.md`。",
        "- 中文显示名用于语义检索，item id 用于和游戏日志、路线图或配置字段做精确匹配。",
        "",
        "| 名称 | item id | 文件 |",
        "| --- | --- | --- |",
    ]
    for filename, display, item_id in sorted(item_index, key=lambda x: (x[1], str(x[2]))):
        item_index_lines.append(f"| {display} | `{item_id}` | [{filename}]({filename}) |")
    item_index_lines.extend(
        [
            "",
            "## 使用规则",
            "",
            "- 物品/词条档案用于背景检索和概念消歧，不替代目标视频字幕、路线图和当前运行日志。",
            "- 检索锚点只用于匹配日志、路线图、字幕块或配置字段，不作为剧情正文引用。",
            "- 不把运行时地址、内存指针、截图路径写入上下文。",
            "- `../unresolved/items/` 里的条目没有可引用正文，默认不参与视频摘要或游戏决策分析。",
        ]
    )
    (item_dir / "README.md").write_text("\n".join(item_index_lines).rstrip() + "\n", encoding="utf-8")

    unresolved_dir = DOSSIERS / "unresolved"
    unresolved_index_lines = [
        "# 未恢复正文条目",
        "",
        "本目录只保存已经恢复到定位锚点、但没有恢复到可引用正文的条目。视频摘要、剧情问答和游戏决策分析默认不要读取这里作为事实依据。",
        "",
        "## 目录",
        "",
        f"- [characters](characters/README.md)：人物 {unresolved_character_count} 条。",
        f"- [items](items/README.md)：物品/词条 {unresolved_item_count} 条。",
        "",
        "## 使用规则",
        "",
        "- 这里的文件只用于补采、映射排查和人工确认。",
        "- 后续如果补到正文，再重新生成到 `../characters/` 或 `../items/`。",
        "- 不要把本目录条目当成角色设定、物品设定或剧情事实。",
    ]
    (unresolved_dir / "README.md").write_text("\n".join(unresolved_index_lines).rstrip() + "\n", encoding="utf-8")

    unresolved_character_lines = [
        "# 未恢复正文的人物条目",
        "",
        "| 人物 | profile key | tag key | 文件 |",
        "| --- | --- | --- | --- |",
    ]
    for filename, display, name_key, tag_key in sorted(unresolved_character_index, key=lambda x: (x[1], x[2], x[3])):
        unresolved_character_lines.append(f"| {display} | `{name_key}` | `{tag_key}` | [{filename}]({filename}) |")
    (unresolved_character_dir / "README.md").write_text("\n".join(unresolved_character_lines).rstrip() + "\n", encoding="utf-8")

    unresolved_item_lines = [
        "# 未恢复正文的物品/词条条目",
        "",
        "| 名称 | item id | 文件 |",
        "| --- | --- | --- |",
    ]
    for filename, display, item_id in sorted(unresolved_item_index, key=lambda x: (x[1], str(x[2]))):
        unresolved_item_lines.append(f"| {display} | `{item_id}` | [{filename}]({filename}) |")
    (unresolved_item_dir / "README.md").write_text("\n".join(unresolved_item_lines).rstrip() + "\n", encoding="utf-8")

    unlock_counts = write_unlock_docs()
    total_character_count = len(character_index)

    root_readme = DOSSIERS / "README.md"
    root_readme.write_text(
        "\n".join(
            [
                "# 游戏内人物/词条资料",
                "",
                "本目录保存已经恢复为 Markdown 的游戏内人物、物品/词条和解锁线索资料。完整使用规则见 [知识库 Agent 导览](../AGENT_GUIDE.md)。",
                "",
                "## 目录",
                "",
                "- [characters](characters/README.md)：人物档案。",
                "- [items](items/README.md)：物品/词条档案。",
                "- [unlocks](unlocks/README.md)：档案解锁线索。",
                "- [aliases](aliases/README.md)：别名、称号和旧 key 导航。",
                "- [reference](reference/README.md)：默认不参与检索的前作/旧作参考资料。",
                "- [unresolved](unresolved/README.md)：只恢复到定位锚点、没有可引用正文的条目。",
                "",
                "## 文件名规则",
                "",
                "- 人物档案：`显示名__profileKey__tagKey.md`。",
                "- 物品/词条档案：`显示名__item-ID.md`。",
                "- 可引用正文保存在 `characters/` 和 `items/`；没有正文的条目隔离在 `unresolved/`。",
                "- profile key、tag key、item id 是给 Agent 和日志/路线图/字幕块匹配用的检索锚点，不是要求用户提供的信息。",
                "",
                "## 当前数量",
                "",
                f"- 人物可用档案：{total_character_count}",
                f"- 人物别名/称号导航：{alias_character_count}",
                f"- 人物旧作参考档案：{reference_character_count}",
                f"- 人物未恢复正文：{unresolved_character_count}",
                f"- 物品/词条可用档案：{item_count}",
                f"- 物品/词条未恢复正文：{unresolved_item_count}",
                f"- 解锁线索：{sum(unlock_counts.values())}",
                "",
                "## 使用规则",
                "",
                "- 摘要和决策 Agent 读取 Markdown，不直接读取运行时 JSON。",
                "- Agent 当前所处节点必须来自后台日志、运行状态、存档或模拟器 state；不要要求用户提供 choice key、video key、profile key。",
                "- 人物/物品档案只用于背景检索和消歧，不替代目标视频字幕、路线图和当前运行日志。",
                "- 人物路线小节是档案正文来源和剧情语境，不是人物存在范围；支线没有专属文本时，可用主线基础身份消歧，但不能继承主线后续事件。",
                "- 命中人物或词条档案后读取完整 Markdown。不要用脚本按关键词摘句、裁剪正文或把共现关系预先写成事实。",
                "- `reference/` 中的旧作参考资料默认不参与检索，只有明确需要旧作背景时才按需读取。",
                "- 前作/旧作参考文本只辅助理解过往设定，不能覆盖当前游戏档案文本。",
                "- `unresolved/` 中的条目没有可引用正文，默认不参与视频摘要、剧情问答或游戏决策分析。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"characters usable: {total_character_count}, reference: {reference_character_count}, unresolved: {unresolved_character_count}, source rows skipped: {skipped_source_rows}, source rows needing review: {needs_review}")
    print(f"items usable: {item_count}, unresolved: {unresolved_item_count}, source rows needing review: {item_needs_review}")
    print(f"unlock records: {sum(unlock_counts.values())} ({unlock_counts})")


if __name__ == "__main__":
    main()
