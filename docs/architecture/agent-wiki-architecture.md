# Agent Wiki 架构

本项目当前的 Agent Wiki 是 `data/knowledge/`。权威使用规则见 [data/knowledge/AGENT_GUIDE.md](../../data/knowledge/AGENT_GUIDE.md)。

## 当前形态

```text
data/knowledge/
  README.md
  AGENT_GUIDE.md
  video_subtitles/
    INDEX.md
    docs/*.subtitles.md
  dossiers/
    README.md
    characters/*.md
    items/*.md
    aliases/*.md
    unlocks/*.md
    reference/
    unresolved/
  video_summaries/
```

## 设计原则

- Agent Wiki 的边界是查询和证据组织。调用方提供定位输入或检索词，Wiki 返回可引用资料、上下文、关系链和证据路径。
- 长期给 Agent 使用的知识材料使用 Markdown。
- 原始 SRT、运行日志、JSON、JSONL 和 CSV 是构建输入、运行输入或校验材料；可长期引用的知识正文应通过 `data/knowledge/` 中的 Markdown 进入上下文。
- 用户不会提供 key。当前节点、当前选择、当前视频、路线状态或目标资料必须来自后台日志、运行状态、存档、HTML state、批处理目标或外层运行器传入的结构化状态。
- 人物/物品档案负责补充背景、关系链和消歧，不替代目标视频字幕、路线图和当前运行状态。
- 命中人物/物品档案后读取完整 Markdown；脚本不得把正文拆成关键词摘录，也不得先替模型判断人物关系。

## 读取顺序

1. 从外层输入或后台运行状态取得查询目标，例如当前 video key、choice key、节点、路线、已选项、可选项、人物 key、物品 id 或固定资料名。
2. 读取最直接的事实文档：具体视频读 `data/knowledge/video_subtitles/docs/<videoKey>.subtitles.md`；具体人物/物品读 `data/knowledge/dossiers/characters/` 或 `data/knowledge/dossiers/items/`。
3. 读取 Storyline 路径图，确认前置选择、兄弟选项、前后节点、合流关系和全量图顺序。
4. 按需要读取同路线、图顺序早于当前节点的已生成前文摘要。摘要层只能补背景，不覆盖目标片段事实。
5. 按人物名、物品名、profile key、tag key、item id、固定别名或上下文称谓检索 `data/knowledge/dossiers/`。
6. 只在需要旧作背景、旧名溯源或未实装候选排查时读取 `data/knowledge/dossiers/reference/`。
7. 只在需要补采、映射排查或索引占位核查时读取 `data/knowledge/dossiers/unresolved/`；这里不能作为事实依据。

## 接入约定

- 调用方决定输出形态；Agent Wiki 只提供可追溯资料和上下文。
- 需要理解某个剧情片段时，从目标字幕片段、路线图、前后节点和涉及实体档案取证。
- 需要解释人物、物品、称谓或关系时，从正式档案、别名导航、关系链和消歧指南取证。
- 需要处理当前游戏状态时，由外层运行器提供日志或 state；Agent 不向用户索要 key。
- 需要旧作或未实装背景时，明确进入 `reference/`，并标注它不能覆盖当前游戏文本。
- 需要补全资料时，读取 `unresolved/` 作为补采线索，而不是把它写成事实。

若外层运行器没有提供必要定位输入，Agent 应报告缺少定位输入，不应要求用户补 key。
