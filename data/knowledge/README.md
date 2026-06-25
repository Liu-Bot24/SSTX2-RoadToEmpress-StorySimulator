# 知识库入口

本目录保存可长期引用的剧情知识库。调用方通过结构化定位信息或检索词进入这里，读取字幕片段、人物/物品档案、关系链、别名导航、解锁线索和证据锚点。

知识库只提供可核验资料和取证路径；具体输出形态由调用方处理。

## 目录

- [AGENT_GUIDE.md](AGENT_GUIDE.md)：查询契约、检索顺序、输入边界和禁用事项。
- [storyline_guide.md](storyline_guide.md)：路线图数据使用指南，说明节点、边、选择和合流关系如何查询。
- [task_guides/README.md](task_guides/README.md)：具体任务的调用导引；只说明取证方法，不作为剧情事实来源。
- [video_subtitles/INDEX.md](video_subtitles/INDEX.md)：每个 video key 对应的剧情字幕片段文档。
- [video_subtitles/INDEX_BY_CHAPTER.md](video_subtitles/INDEX_BY_CHAPTER.md)：按章节进入字幕片段。
- [video_subtitles/INDEX_BY_ROUTE.md](video_subtitles/INDEX_BY_ROUTE.md)：按线路进入字幕片段。
- [dossiers/README.md](dossiers/README.md)：人物、物品/词条、关系链、别名导航和解锁线索资料。
- [video_summaries/INDEX.md](video_summaries/INDEX.md)：AI 生成的派生摘要层，可作为上下文和长距离剧情回顾；生成目标视频摘要时不得读取目标自己的既有摘要，事实核验仍回到字幕片段、路线图和档案正文。

## 使用原则

- 当前视频、当前选择、当前人物或目标资料的位置来自后台日志、运行状态、存档、HTML 模拟器 state、批处理目标或外层运行器传入的结构化状态，不来自用户口头提供。
- `choice key`、`video key`、`profile key`、`tag key`、`item id` 是机器检索锚点；用户不会也不应该负责提供这些 key。
- 具体视频内容以 `video_subtitles/docs/<videoKey>.subtitles.md` 为目标片段事实来源。
- 需要查路线顺序、前置选择、兄弟分支和合流关系时，先读 [storyline_guide.md](storyline_guide.md)，再进入路线图数据。
- 当前状态类查询以后台读取到的当前节点、路线、已选项、可选项、数值和条件结果为入口，再按 [AGENT_GUIDE.md](AGENT_GUIDE.md) 检索背景资料。
- `dossiers/unresolved/` 只用于补采和排查，不作为剧情事实或人物设定引用。
- 命中人物或词条档案后读取完整 Markdown。脚本只负责构建、召回、导航和校验路径，不负责摘句、裁剪正文或判断人物关系。
