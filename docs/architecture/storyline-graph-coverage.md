# Storyline 路径图覆盖报告

本文说明剧情模拟器当前纳入的剧情图范围、HTML 展示边界和数据产物。

## 当前覆盖范围

当前剧情图产物位于：

```text
data/game/storyline_graph/
```

核心统计：

- Storyline 根对象：17 个。
- 节点：1614 个。
- 跳转边：1659 条。
- 选择边：534 条。

这些边来自剧情图里的跳转关系，不来自 SRT 文件顺序、攻略顺序或某一次玩家游玩路线。

## 章节范围

当前主剧情覆盖：

```text
chapter999
chapter101
chapter102
chapter103
chapter104
chapter105
chapter106
chapter107
chapter108
chapter109
chapter110
chapter111
chapter112
chapter201
chapter202
chapter203
chapter204
```

章节分组：

- `chapter999`：前情提要和分线入口。
- `chapter101` 到 `chapter112`：女帝篇主剧情。
- `chapter201` 到 `chapter204`：新世界篇主剧情。

## HTML 展示边界

当前交互页面：

```text
data/game/storyline_graph/storyline_graph.html
```

展示规则：

- 首页按“前情提要”“女帝线”“新世界线”组织入口。
- 主线节点顺序由剧情图跳转关系产生。
- 页面不会一次性展开所有分支；遇到选择节点时停止，用户点击某个选项后进入对应目标分支。
- 已点击过的选择保留在浏览器本地状态中，便于回到相关选择和查看路径影响。
- 字幕显示来自同名 zh_GL SRT 和 `data/knowledge/video_subtitles/docs/` 的整理结果。
- 剧情摘要显示来自 `data/knowledge/video_summaries/` 的摘要库。
- “真实历史人物”显示层来自 `data/game/storyline_graph/historical_name_overlay.json`，只做可切换显示，不覆盖游戏原文。

## 附加内容

当前项目还整理了 4 个附加内容包：

```text
chapter_envoy_1
chapter_envoy_2
chapter_envoy_3
chapter_extra_nc
```

这些内容作为“额外内容”单独展示。当前页面只展示可确认的字幕和文本内容，不把它们混入女帝线或新世界线主图。

## 与攻略章节的关系

攻略只用于对照检查是否存在明显缺口。正式展示和知识库事实以项目内剧情图、节点文本、字幕片段和摘要库为准。

当前分组对应：

- 女帝篇：覆盖第十七集到第四十一集相关主剧情。
- 新世界篇：覆盖第十七集到第二十三集相关主剧情。

最终展示名优先采用游戏文本和剧情图节点标题，不按攻略标题强行改写。

## 当前可用产物

```text
data/game/storyline_graph/nodes.jsonl
data/game/storyline_graph/edges.jsonl
data/game/storyline_graph/edges.csv
data/game/storyline_graph/choice_edges.csv
data/game/storyline_graph/overview.json
data/game/storyline_graph/storyline_lines_manifest.json
data/game/storyline_graph/storyline_graph_data.json
data/game/storyline_graph/value_table.json
data/game/storyline_graph/storyline_graph.html
data/game/storyline_graph/historical_name_overlay.json
data/game/storyline_graph/historical_name_overlay.md
```

文件用途：

- `nodes.jsonl`：节点清单。
- `edges.jsonl`：节点跳转边。
- `choice_edges.csv`：选择节点到目标节点的表格版。
- `overview.json`：章节和覆盖统计。
- `storyline_lines_manifest.json`：按线路和章节组织的顺序清单。
- `storyline_graph_data.json`：HTML 使用的聚合数据。
- `value_table.json`：HTML 数值面板使用的数值表。
- `storyline_graph.html`：可直接浏览的剧情模拟器页面。
- `historical_name_overlay.json`：真实历史人物显示层映射。
- `historical_name_overlay.md`：映射表的人类可读说明。

## 维护要求

- 修改字幕说话人时，以 `data/knowledge/video_subtitles/docs/*.subtitles.md` 为维护入口，再同步回 SRT。
- 修改视频摘要时，以 `data/knowledge/video_summaries/docs/*.summary.md` 为维护入口，再同步聚合文件。
- 修改真实历史人物显示层时，更新 `historical_name_overlay.json` 和对应说明文档。游戏本体历史称谓补丁包的 `patch_manifest.json` 是该映射表的发布副本，不作为新的语义判断入口；补丁包只执行已经在显示层确认的替换关系。
- 修改 HTML 交互时，更新 `tools/storyline_graph_template.html` 并重新生成页面。
