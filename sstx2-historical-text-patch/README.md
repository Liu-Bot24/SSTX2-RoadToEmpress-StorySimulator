# 《盛世天下：女帝篇》历史称谓补丁

这个补丁用于把《盛世天下：女帝篇》游戏显示文本中的架空称谓、谐写人名，还原为对应的历史称谓。

## 文件版本

补丁发布包通常包含三种下载：

- `sstx2-historical-text-patch-20260625.zip`：一键包，也就是本 README 所在的版本。通过脚本执行全部替换、谐音替换或还原原文，会自动处理备份和在线字幕域名屏蔽。
- `sstx2-historical-text-direct-all-20260625.zip`：全部替换直接解压版。解压后直接覆盖游戏目录中的对应 `Data` 文件。
- `sstx2-historical-text-direct-phonetic-20260625.zip`：谐音替换直接解压版。只覆盖谐音/近音规避项对应的游戏文件。

如果不确定选哪个，优先使用一键包；它可以备份、还原，并自动处理视频字幕所需的在线字幕屏蔽。

## 使用方式

关闭游戏后，把整个 `sstx2-historical-text-patch` 文件夹放到游戏根目录下，和 `Data` 文件夹同级。

如果拿到的是压缩包，请解压出完整的 `sstx2-historical-text-patch` 文件夹，再把这个文件夹放到游戏根目录。不要把文件夹里的文件散放到游戏根目录。

正确结构应类似这样：

```text
roadtoempress2
├─ Data
└─ sstx2-historical-text-patch
   ├─ sstx2-history-patch.bat
   ├─ patch_sstx2_history.py
   ├─ patch_manifest.json
   ├─ patch_manifest_zh_TW.json
   └─ README.md
```

然后双击：

```text
sstx2-history-patch.bat
```

补丁会申请管理员权限，用于屏蔽游戏的线上字幕域名。这样视频播放时会使用本地已替换的字幕文件。选择还原原文时，会移除补丁写入的域名屏蔽。

在菜单中选择：

- `1`：全部替换
- `2`：谐音替换
- `3`：还原原文

也可以在补丁文件夹中从命令行指定操作：

```powershell
.\sstx2-history-patch.bat all
.\sstx2-history-patch.bat phonetic
.\sstx2-history-patch.bat restore
```

## 直接解压版说明

直接解压版不需要运行本脚本。关闭游戏后，把对应压缩包直接解压到游戏根目录，让压缩包里的 `Data` 文件夹覆盖游戏目录中的 `Data` 文件夹即可。

直接解压版不会创建备份，也不会自动修改 `hosts`。如果需要恢复原文，请通过 Steam 验证游戏文件完整性。

视频字幕会优先使用在线字幕资源。使用直接解压版时，如果希望视频字幕也显示替换后的本地字幕，需要自己屏蔽在线字幕域名。可以用管理员权限编辑系统 `hosts` 文件，加入：

```text
127.0.0.1 eo.roadtoempress.com
```

Windows 的 `hosts` 文件通常在：

```text
C:\Windows\System32\drivers\etc\hosts
```

如果不想手动修改 `hosts`，请使用一键包。

## 处理范围

- 中文字幕：`Data\StreamingAssets\res\main\SSTX2\Global\srt\zh_GL\*.srt`、`Data\StreamingAssets\res\main\SSTX2\Global\srt\zh_TW\*.srt`
- 游戏显示文本：`Data\StreamingAssets\res\main\cfg\data\TextClient*.pbin`
- 由 `TextClient*.pbin` 提供的游戏选择、标题、界面文案、人物档案、人物卡、风物/物品词条等资料页文本
- 线上字幕域名屏蔽：`eo.roadtoempress.com`

补丁会按资源语种分别应用清单：简体字幕和简体 UI 字段使用 `patch_manifest.json`，繁体字幕和繁体 UI 字段使用 `patch_manifest_zh_TW.json`。不会把简体替换结果写入繁体文本，也不会把繁体替换结果写入简体文本。

补丁不直接修改加密结构配置、存档、日志、音频或视频资源。

## 补丁清单

`patch_manifest.json` 是简体覆盖清单，`patch_manifest_zh_TW.json` 是对应的繁体覆盖清单。

每条记录表示一项已经确认的文本覆盖：

- `from`：游戏原文
- `to`：历史称谓文本
- `modes`：该条覆盖适用于完整替换、谐音替换，或两者
- `skipWhenNear`：少量歧义词的保护短语，用于避免把普通词义误替换成人名

`extra_replacements.md` 记录补丁包额外覆盖的游戏本体界面文本，例如人物档案、风物/物品词条、人物卡等。补丁执行时会合并这些额外项；如果同一原文同时存在于通用清单和额外项，额外项优先。

更新补丁包时，已确认的通用覆盖关系写入 `patch_manifest.json`；只存在于游戏本体额外界面的条目记录到 `extra_replacements.md`，并在 `patch_manifest.json` 中标记为 `sourceGroup: game_ui_extra`。补丁包本身只负责执行清单，不重新判断语义。
