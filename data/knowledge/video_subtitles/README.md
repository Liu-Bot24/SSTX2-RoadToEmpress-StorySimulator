# Video Key 字幕文档

本目录按 video key 保存可阅读的字幕片段。修正说话人时，以 `docs/<videoKey>.subtitles.md` 为入口。

## 查询使用

- 理解具体视频内容时，读取 `docs/<videoKey>.subtitles.md`。
- 按章节或线路查找字幕片段时，先读 `INDEX_BY_CHAPTER.md` 或 `INDEX_BY_ROUTE.md`。
- SRT 是页面显示的派生字幕层，不是知识库查询入口。

## 维护链路

- 修正入口：修改 `docs/<videoKey>.subtitles.md` 中 `## 字幕` 下的说话人或正文。
- 同步到页面 SRT：运行 `python tools/sync_srt_from_subtitle_md.py`。
- 构建 HTML：运行 `python tools/build_interactive_branch_preview.py`，构建过程中会自动执行 MD -> SRT 同步。

HTML 页面实际读取 `data/game/storyline_graph/srt/...`，该目录下的 SRT 是派生文件。不要把页面 SRT 当作修正入口。

`tools/export_video_key_subtitle_docs.py` 是反向导出工具，会从页面 SRT 重建本目录的 MD；只有在重新生成整套字幕文档时使用，日常修正说话人不要运行它。
