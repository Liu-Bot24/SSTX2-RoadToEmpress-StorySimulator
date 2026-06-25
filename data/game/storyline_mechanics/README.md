# Storyline Mechanics Audit

这个目录从运行时恢复的 Storyline JSON 中抽取路径判断机制，不依赖 HTML 页面。

## 覆盖范围

- 条件节点：52
- 全局变量 getter/setter 节点：13
- 视频片段内数值/属性变化：900
- 表达式仍含未知变量 hash 的条件：0

## 关键结论

- `Function_Storyline_If` 的判断参数可以从 `parameterLink` 反向还原。
- 数值/效果的唯一源文件是 `video_effects.jsonl`；选项效果由页面根据其中的 `upstream_choices.distance == 1` 动态推导，不再生成第二份选择效果文件。
- 部分剧情数值变化不在 `Global_GlobalVariableSetter`，而在 `PlayVideo_VideoKey_Variable_Int` 子节点里。
- `PlayVideo_Toast_DimensionIncrease` 和 `PlayVideo_Toast_FlavorIncrese` 是展示层提示，但也可作为效果交叉验证。

## 样例：王皇后信任度判断

- Storyline: `storyline_009_a11568e081`
- 节点：`31984147` / IF王皇后信任度＜2
- 表达式：`王皇后信任度 累计值 < 2`
- 结果：`{"endPointTrue": "B02_010_024", "endPointElse": "010_025"}`

