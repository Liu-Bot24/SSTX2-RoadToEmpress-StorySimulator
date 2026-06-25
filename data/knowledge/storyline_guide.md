# 路线图数据使用指南

本文说明 Agent 如何从知识库进入路线图数据，理解节点顺序、前置选择、兄弟分支、后续节点和合流关系。

## 文件位置

- `data/game/storyline_graph/storyline_graph_data.json`：章节级路线图。包含 `chapters[]`、每章 `nodes[]`、节点内 `edges[]`，适合读取完整章节顺序和相邻节点。
- `data/game/storyline_graph/nodes.jsonl`：节点扁平表。每行一个节点，适合按 `video_key`、`kind`、`annotation`、`title_zh` 检索。
- `data/game/storyline_graph/edges.csv`：边扁平表。适合按选择节点、选项文本、source/target 快速追踪分支。
- `data/knowledge/video_subtitles/docs/<videoKey>.subtitles.md`：按 video key 组装后的可引用字幕片段。理解具体视频内容时优先读这里。
- `data/knowledge/video_subtitles/INDEX_BY_CHAPTER.md`：按章节进入字幕片段。
- `data/knowledge/video_subtitles/INDEX_BY_ROUTE.md`：按线路进入字幕片段。

`data/game/storyline_graph/srt/` 是原始字幕来源目录。常规知识库查询不要直接读取原始 SRT；需要理解具体视频时读取 `data/knowledge/video_subtitles/docs/*.subtitles.md`。

## 节点字段

常用节点字段：

- `storyline_id` / `storylineId`：路线图内部线路 ID。
- `node_id` / `id`：节点唯一 ID。
- `kind`：节点类型，例如 `PlayVideo_Ordinary`、`PlayVideo_TraceBack`、`ShowChoice`、`EndPoint_BadEnd`、`Function_Storyline_If`。
- `video_key` / `videoKey`：视频或选择节点 key。具体视频字幕文档以这个字段查找。
- `annotation`：官方卡片摘要、节点说明或显示 key。
- `title_zh` / `title`：节点标题。
- `storyline_title_zh` / `storylineTitle`：路线图显示标题。
- `choices[]`：选择节点内的选项信息。
- `edges[]`：从当前节点发出的边。

常用边字段：

- `source_label` / `sourceKind`：边起点。
- `target_label` / `targetKind`：边终点。
- `choice_index` / `choiceIndex`：选项序号。
- `choice_text_zh` / `choiceText`：选项文本。
- `source_port` / `sourcePort`：选择、条件或普通流向端口。
- `targetVideoKey`：目标视频 key。

## 常见查询方式

### 已知 video key，找目标字幕

1. 打开 `data/knowledge/video_subtitles/docs/<videoKey>.subtitles.md`。
2. 读取文档头部的“位置”“卡片摘要”“前置选择”“前一视频”“后续节点”。
3. 目标视频事实只从该字幕文档和目标官方摘要取证。

### 已知 video key，找前置选择

1. 先看字幕文档头部的“前置选择”。
2. 需要校验时，在 `edges.csv` 中搜索该 `videoKey`，找到指向它的边。
3. 若来源是 `ShowChoice`，读取 `choice_index` 和 `choice_text_zh`，再读取同一 source 下的其他选项作为兄弟分支。

### 找兄弟选项

1. 在 `edges.csv` 中定位当前选项边的 `source_label`。
2. 同一个 `source_label` 且 `source_kind=ShowChoice` 的边是同一选择题的其他选项。
3. 兄弟分支只用于理解差异和路线位置，不能写成当前视频已发生事实。

### 找直接前后节点

1. 字幕文档头部通常已经给出“前一视频”和“后续节点”。
2. 需要更完整的图结构时，在 `storyline_graph_data.json` 对应 chapter 的 `nodes[]` 内按 `videoKey` 找节点，再看节点 `edges[]`。
3. 条件节点、坏结局节点和合流节点要保留 `kind`，不要把不同路线合并成同一事实。

### 按线路或章节进入

1. 先读 `video_subtitles/INDEX_BY_ROUTE.md` 或 `video_subtitles/INDEX_BY_CHAPTER.md`。
2. 根据线路、章节和 video key 打开目标字幕文档。
3. 需要长距离前后文时，结合摘要层和路线图继续扩展。

## 取证边界

- 具体视频事实：优先来自 `video_subtitles/docs/<videoKey>.subtitles.md`。
- 选择题、分支、合流和前后顺序：来自路线图文件和字幕文档头部。
- 官方摘要字段可辅助理解视觉动作、卡片说明和节点定位；如果与字幕冲突，需要标注冲突。
- 原始 SRT 只适合导出或排错，不作为 Agent 常规查询入口。
- 后文节点、兄弟分支、坏结局、条件未满足路径不能写成当前路线事实。
