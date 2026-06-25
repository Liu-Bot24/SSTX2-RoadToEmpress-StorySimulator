# 游戏内人物/词条资料

本目录保存已经恢复为 Markdown 的游戏内人物、物品/词条和解锁线索资料。完整使用规则见 [知识库 Agent 导览](../AGENT_GUIDE.md)。

## 目录

- [characters](characters/README.md)：人物档案。
- [items](items/README.md)：物品/词条档案。
- [unlocks](unlocks/README.md)：档案解锁线索。
- [aliases](aliases/README.md)：固定别名、称号、旧 key、阶段导航和上下文称谓消歧指南。
- [reference](reference/README.md)：前作/旧作、旧名溯源和未实装候选参考资料。
- [unresolved](unresolved/README.md)：只恢复到定位锚点、没有可引用正文的条目。

## 文件名规则

- 人物档案：`显示名__profileKey__tagKey.md`。
- 物品/词条档案：`显示名__item-ID.md`。
- 可引用正文保存在 `characters/` 和 `items/`；没有正文的条目隔离在 `unresolved/`。
- profile key、tag key、item id 是给 Agent 和日志/路线图/字幕块匹配用的检索锚点，不是要求用户提供的信息。

## 当前数量

- 人物可用档案：57
- 人物别名/称号导航：41
- 人物旧作参考档案：29
- 人物未恢复正文：40
- 物品/词条可用档案：18
- 物品/词条未恢复正文：1
- 解锁线索：273

## 使用规则

- 查询 Agent 读取 Markdown，不直接读取运行时 JSON 作为长期知识正文。
- 当前所处节点、目标片段或目标资料必须来自后台日志、运行状态、存档、模拟器 state、批处理目标或外层结构化输入；不要要求用户提供 choice key、video key、profile key。
- 人物/物品档案只用于背景检索和消歧，不替代目标视频字幕、路线图和当前运行日志。
- 人物路线小节是档案正文来源和剧情语境，不是人物存在范围；支线没有专属文本时，可用主线基础身份消歧，但不能继承主线后续事件。
- 命中人物或词条档案后读取完整 Markdown。不要用脚本按关键词摘句、裁剪正文或把共现关系预先写成事实。
- `reference/` 中的旧作参考资料只有在查询目标需要旧作背景、旧名溯源或未实装候选排查时才按需读取。
- 前作/旧作参考文本只辅助理解过往设定，不能覆盖当前游戏档案文本。
- `unresolved/` 中的条目没有可引用正文，默认不作为事实依据。
