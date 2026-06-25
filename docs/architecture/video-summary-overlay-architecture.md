# 视频摘要覆盖层架构

视频摘要覆盖层通过知识库取证：它在保留官方摘要字段的基础上，为每个剧情视频补充更细的展示摘要、结构化事件和证据引用。它的输入规则必须服从 [知识库 Agent 使用导览](../../data/knowledge/AGENT_GUIDE.md)。

## 目标

- 页面展示时优先显示覆盖摘要，官方摘要保留为参考来源。
- 摘要必须能回到目标视频字幕片段、前置选择、路线图位置或官方摘要。
- 摘要生成读取 `video_subtitles/docs/<videoKey>.subtitles.md`，不直接读取原始 SRT。
- 生成器负责接收目标定位和资料入口，并主动读取字幕、路线图、摘要索引和相关 Markdown 档案。

## 目标视频事实

目标视频事实来源：

```text
data/knowledge/video_subtitles/docs/<videoKey>.subtitles.md
```

每个文档对应一个 video key，包含：

- 当前视频 key。
- 章节、线路和路径位置。
- 前置选择 key、问题、选项文本和流向。
- 前一视频和后续节点。
- 时间码、说话人和字幕正文。

生成摘要时，目标视频字幕片段是第一事实来源。官方摘要、人物档案和前文摘要只能补充背景。

## 路线图

路径图来源：

```text
data/game/storyline_graph/storyline_graph_data.json
data/game/storyline_graph/storyline_lines_manifest.json
data/game/storyline_graph/edges.jsonl
data/game/storyline_graph/choice_edges.csv
```

路径图用于确定：

- 目标视频所在章节、线路、节点和 storyline id。
- 上游最近选择、当前选项和兄弟选项。
- 直接前文视频、直接后文节点、合流和分支关系。
- 全量 Storyline 图顺序。

摘要排序使用 Storyline 图和 HTML 组装使用的全量顺序。用户点击历史、运行日志、数值面板状态和实时操作记录不参与摘要输入排序。

## 背景资料

背景资料来源：

```text
data/knowledge/dossiers/characters/*.md
data/knowledge/dossiers/items/*.md
data/knowledge/dossiers/unlocks/*.md
```

使用规则：

- 人物和词条资料用于身份、关系、物品、制度和动机解释。
- 只恢复到 key、没有正文的 `dossiers/unresolved/` 不进入摘要输入。
- `dossiers/unlocks/` 只说明资料解锁或更新时机，不能替代档案正文，不能证明当前路线事实，也不能独立推出人物关系。
- 前作/旧作参考文本只解释过往设定，不覆盖当前游戏文本。
- 同名人物在主线、支线身份不同的，必须按路线分开引用。

## 官方摘要

官方摘要来自 Storyline 节点的 `annotation` 字段。

使用规则：

- 有效官方摘要作为强参考进入摘要输入。
- 覆盖摘要可以比官方摘要更详细，但不能与目标字幕事实冲突。
- 官方字段保持原样，覆盖摘要写入独立数据。

## 单视频摘要输入

生成某个 video key 的摘要时，输入应包含：

1. 目标 `*.subtitles.md`。
2. 路线图中该节点的章节、线路、前置选择、兄弟选项、前后节点。
3. 同路线、图顺序早于目标节点的已生成前文摘要索引；摘要层只能作为辅助背景。
4. 根据目标字幕、前置选择和路线图检索到的人物和物品档案。
5. 官方摘要。

不要读取目标视频自己的旧覆盖摘要作为事实来源。不要把兄弟分支写成当前路线事实。
不要把 AI 生成摘要当成一手事实来源；关系和动机必须由模型结合目标字幕、路线图和完整档案正文判断。

## 输出要求

每条覆盖摘要至少包含：

- `videoKey`。
- 展示摘要。
- 结构化事件事实。
- 涉及人物和物品。
- 证据引用。
- 置信度和风险提示。

证据引用应指向字幕片段、前置选择、路线节点或官方摘要，避免只写“根据上下文”。
