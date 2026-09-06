# 精选游戏素材

本目录从 `resource/Pokemon Essentials v20.1` 中筛选出当前矿山 RPG 可能使用的素材，并补充收纳了项目中已有的 Granite Cave 图集和两张 GBA UI 参考图。原始 Essentials 目录及原文件均未修改。

## 推荐使用顺序

1. 地图优先使用 `map/tilesets/granite_tiles_32.png`，它适配当前项目的 32 x 32 网格；需要补充地形时再查 `map/tilesets/caves.png`。
2. 主角候选位于 `map/characters/`。三张图都是 128 x 128、4 x 4 帧；实现前应固定一张为正式行走图，另外两张可用作特殊动作或参考。
3. 战斗中的坚果哑铃使用 `battle/pokemon/back/ferrothorn.png`，敌人使用 `battle/pokemon/front/`。
4. 中文对话字体使用 `fonts/zpix.ttf`，拉丁字母和数字可使用 `fonts/power_red_blue_intl.ttf`。
5. 对话框优先测试 `ui/windows/speech_rs.png`。这是本包中最接近红宝石/蓝宝石风格的窗口皮肤。
6. `battle/effects/` 中的图片是动画素材表，不是可直接播放的 GIF；需要按实际排布切帧，并在代码中定义位置、缩放、持续时间和音效触发点。

## 目录说明

- `map/tilesets/`：完整洞穴 tileset、精选 Granite Cave 图集和 tile 索引。
- `map/autotiles/`：棕色洞穴地面、沙地和高光动画素材。
- `map/characters/`：坚果哑铃地图角色候选图。
- `map/objects/`：普通岩石、巨石和破碎序列。
- `map/effects/`：地图灰尘、草屑和感叹号效果。
- `battle/pokemon/`：12 种候选宝可梦的正面、背面和菜单图标。
- `battle/backgrounds/`：三种明暗洞穴背景及双方站台。
- `battle/ui/`：血条、指令框、技能框、游标和状态图标拆件。
- `battle/effects/`：普通攻击、日光束、光合作用、重磅冲撞、岩石和气象球候选素材。
- `battle/transitions/`：进入战斗时可使用的遮罩和转场图片。
- `ui/system/`：标题提示、暂停、存档读档、属性图标和通用选择箭头。
- `audio/`：洞穴/战斗音乐、UI 音效、技能音效和候选宝可梦叫声。
- `reference_data/`：Essentials 的技能、属性和宝可梦数据，仅供查数值，不建议直接作为 Pygame 运行时数据。
- `reference/gen3_ui/`：GBA 火红/叶绿界面参考图，适合用于重制更接近原作的战斗 HUD。

## 候选宝可梦

已收纳坚果种子、坚果哑铃、超音蝠、小拳石、隆隆石、幕下力士、可可多拉、勾魂眼、大嘴娃、朝北鼻、波士可多拉和凯西。没有复制闪光、蛋、脚印、训练家和捕捉系统素材。

## 风格与兼容性

Essentials 自带的战斗 HUD 和洞穴战斗背景并非严格的第三世代风格，建议先作为功能占位，最终根据 `reference/gen3_ui/` 重绘或重新拼装。三张洞穴战斗背景整体偏蓝，也应在美术打磨阶段调整为 Granite Cave 的暖棕色调。

`audio/bgm/cave.mid` 是 MIDI 文件，Pygame 在不同电脑上的支持不完全一致。提交前应测试目标电脑，必要时从合法来源转换或替换为 OGG。

## 来源追踪

`manifest.csv` 记录每个文件的目标路径、原始路径、用途、大小和 SHA-256。重新执行 `tools/collect_essentials_assets.ps1` 可以从原包重建本目录。

Pokemon Essentials 和其中的宝可梦相关素材涉及各自作者及任天堂、Game Freak、Creatures 的权利。课程原型应保留来源记录；若公开发布或上传素材包，需要另行确认授权并补充完整署名。
