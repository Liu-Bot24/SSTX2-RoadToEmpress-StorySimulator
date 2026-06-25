# 视频摘要

本目录保存按 video key 组织的剧情摘要层，用于补充上下文、回顾长距离前因后果和辅助路线理解。

## 文件

- `docs/<videoKey>.summary.md`：每个 video key 的 Markdown 摘要文档；前端卡片展示以这里的 `display_summary` 段为准。需要核验事实时，仍要读取证据字段并回到字幕、路线图和档案正文。
- `video_summaries.jsonl`：由 Markdown 摘要同步出的结构化摘要记录，保留批量生成结果和来源信息。
- `INDEX.md`：按 video key 进入摘要文档的检索索引。

## 来源标记

- `source.kind = ai_generated_summary` 且 `source.model = DeepSeek V4 Flash`：由 DeepSeek V4 Flash 生成的有字幕剧情摘要。
- `source.kind = metadata_context_summary`：无字幕节点摘要，依据官方摘要、剧情标题、节点元数据和相邻节点整理。

## 使用边界

- 目标视频自己的既有摘要不能作为生成或重写该目标摘要的输入。
- 可读取同路线、图顺序早于目标节点的摘要来补充前文；后文和兄弟分支只用于判断路线位置与差异。
- 具体事实仍以目标字幕片段、路线图、官方字段和档案正文为准。
