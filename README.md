# STC-B 坚果哑铃实验世界

这是从 Pokémon Essentials/GBA 资源包中提取素材后制作的独立 Python/Pygame 原型。由于前期 STC 串口方案存在问题，项目已不再使用原有的 RPG Maker 工程。`assets/resource` 目录保存了地图、战斗、角色、UI 和音效资源。

## 运行

推荐在 Windows 上使用 Python 3.12（Python 3.10-3.13 均可）。首次运行时，在 PowerShell 中依次执行：

```powershell
git clone https://github.com/qingjiaofu-boop/poke.git
cd poke
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python adventure.py
```

以后再次运行，只需进入项目目录、激活虚拟环境并启动游戏：

```powershell
cd poke
.\.venv\Scripts\Activate.ps1
python adventure.py
```

也可以在项目目录双击 `run.bat`，或在 PowerShell 中运行 `.\run.bat`。游戏默认进入 120×120 的室外森林世界；未连接开发板时可以完全使用键盘操作。

### 键盘操作

| 按键 | 功能 |
| --- | --- |
| 方向键 | 每次移动一格、菜单选择 |
| `Enter` | 交互、确认 |
| `Z` | 地图中临时触发“重磅冲撞”，击碎面前符合条件的岩石 |
| `1`-`5` | 调试切换室外世界及四张洞穴地图 |
| `F1` | 返回原有剧情演示界面 |
| `V` | 在原有剧情演示中模拟一次震动 |
| `R` | 重置当前流程 |
| `Esc` | 退出游戏 |

## 连接 STC-B 开发板

使用 USB 线将 STC-B 学习板连接到电脑，并确认板上已经烧录本项目的固件。先查询 Windows 分配的串口号：

```powershell
python -c "from serial.tools import list_ports; print([(p.device, p.description) for p in list_ports.comports()])"
```

将输出中的端口号代入启动命令，例如：

```powershell
python adventure.py COM3
```

也可以把端口号传给批处理脚本：

```powershell
.\run.bat COM3
```

如果串口无法打开，请关闭 Keil、串口助手等可能占用该端口的程序，然后重新启动游戏。

## 单独采集开发板原始数据

如果当前只负责开发板串口采集，不需要启动游戏，可以运行 Pygame 原始数据窗口：

```powershell
python sensor_monitor.py COM3
```

也可以双击 `run_sensor_monitor.bat`，或把实际串口号作为参数传给它。窗口只显示固件发送的原始协议，不进行温度换算、震动强度计算、伤害计算或属性判断：

| 协议 | 窗口显示 |
| --- | --- |
| `0x40 hi lo` | 光照原始 ADC：`(hi << 8) | lo` |
| `0x41 hi lo` | 温度原始 ADC：`(hi << 8) | lo` |
| `0x09` | 震动事件和累计次数 |
| 其他单字节 | 原始按键字节 |

没有连接开发板时，可按 `L`、`T`、`V` 注入一条模拟的原始光照、温度或震动事件；这只用于检查窗口，不会修改固件数据。协议解析和跨串口分包测试在 `test_sensor_monitor.py` 中，可运行 `python test_sensor_monitor.py`。

## 当前原型

- Essentials/绿宝石风格的序章地图与对话
- 地图剧情事件：宝可梦立绘预载图、逐字对白、事件图标、顺序步骤与战斗占位
- 坚果哑铃主角显示
- 流星坠入矿洞，好奇的坚果哑铃前去冒险寻找的完整剧情流程
- 矿洞岩石阻挡；靠近后用 STC-B 震动传感器触发重磅冲撞并击碎岩石
- 矿洞深处苏醒的基拉祈，以及成为朋友的结尾
- 右上角地图坐标和传感器状态提示
- 训练战斗页：日光束、光合作用、重磅冲撞的数值随传感器变化
- STC-B 协议兼容：方向/确认指令 `0x01-0x05`，重开 `0x06`，导航键 3 切页 `0x08`，震动 `0x09`，光照/温度数据帧 `0x40/0x41`

### 坚果哑铃独立战斗测试

运行目前独立于主线的 480×320 战斗原型：

```powershell
python battle_demo.py --port COM3
```

也可以双击 `run_battles.bat`，连接开发板时使用 `run_battles.bat COM3`。数字键 `1`、`2`、`3` 随时切换超音蝠、可可多拉和勾魂眼；方向键选择技能，`Enter` 或空格确认普通技能，勾魂眼战的“重磅冲撞”必须选中后按 `Z` 触发，`R` 重开，`Esc` 退出。`Z` 与 STC-B 震动命令 `0x09` 共用同一处理入口。光照 `0` 到 `105` 映射日光束威力 `70` 到 `120`，光合作用回复 `30%` 到 `50%`，中间线性插值。完整应用流程和可复用提示词见 [docs/STC_BATTLE_FLOW.md](docs/STC_BATTLE_FLOW.md)。

## 数据驱动战斗框架

基础战斗规则位于 [battle_engine.py](battle_engine.py)。资源包中的 898 条宝可梦图鉴记录和 741 条普通招式记录已转换到 `assets/data/pokemon.json`、`assets/data/moves.json`，可以直接用记事本编辑。图鉴记录包含六项种族值、属性和图鉴文本；招式记录包含属性、物理/特殊/变化分类、威力、命中率、PP 和说明。

战斗默认使用 6V（六项 IV 均为 31）、0 EV、无性格。伤害保留等级、攻击/防御、威力、随机数（217-255）、STAB、属性倍率、命中判定和暴击判定；不加入特性、道具和异常状态。主角的传感器招式单独位于 [protagonist_moves.py](protagonist_moves.py)，实时读取光照、温度和震动后才生成可执行的 `Move`，不放进 JSON。

重新从课程资源生成静态数据：

```powershell
python tools\build_battle_data.py
```

公式和调用示例见 [assets/data/README.md](assets/data/README.md)。

原 RPG Maker 工程保持不变，提取的资源副本位于 `assets` 目录。

## STC-B 开发板固件

开发板端 Keil/C51 工程已放在 `firmware/stc_bsp_gomoku`，包括 `main.c`、完整 BSP 头文件、`STCBSP_V3.6.LIB`、Keil 工程配置和可直接烧录的 HEX。开发板负责按键、震动、光照和温度采集，电脑端 `adventure.py` 负责游戏逻辑与画面，二者通过 9600 baud 串口协议连接。协议和烧录流程见 [firmware/README.md](firmware/README.md)。

## 三层地图编辑器（像 RPG Maker 一样搭图）

编辑器左侧是 `Outside.png` 图块资源区，右侧是 24×18 地图画布。鼠标选中图块后点击画布即可绘制，支持地面层、当前层、上层，以及当前层碰撞标记和出生点设置：

```powershell
cd poke
python tools/map_editor.py home       # 编辑父亲的家
python tools/map_editor.py friend     # 编辑青梅空地
python tools/map_editor.py route      # 编辑 1 号道路
```

快捷键：`1/2/3` 切换三层，`4` 切换游戏最终画面预览，`C` 切换当前层碰撞标记模式，`P` 设置出生点，左键绘制、右键擦除，`←/→` 翻图块页，`G` 输入页码后直接跳转图块页，`T` 切换图块集，`O` 打开已有地图，`E` 扩充/调整地图尺寸，`F5` 重新加载事件标记，`W/A/S/D`（或滚轮）平移画布，`Ctrl+S` 保存。也可以点击左侧的“跳转图块页 [G]”或“保存地图 [Ctrl+S]”按钮。保存后会更新 `assets/maps/*_lower.png`、`*_current.png`、`*_upper.png` 和 `outdoor_maps.json`，游戏下次启动自动读取。

地图画布会额外显示 `assets/map_events.json` 中的事件：青色框表示事件触发格，红色 `B` 表示该事件序列中包含战斗步骤。事件图标只是编辑器与游戏运行时叠加层，不会被烘焙进 lower/current/upper 三层 PNG。

按 `O` 或点击“打开已有地图 [O]”会弹出 `outdoor_maps.json` 里已有的地图列表（也会扫描 `assets/maps/*_lower.png`），用 `↑/↓`（或 `PgUp/PgDn`、滚轮）选择、`Enter` 打开；打开前会自动保存当前地图的未保存修改。

切换图层后，当前层会以彩色描边高亮，另外两层变暗：蓝色为地面层、橙色为当前层、紫色为上层。按 `4` 后三层会按游戏实际顺序正常合成，并隐藏编辑辅助框，便于检查最终效果；按 `1/2/3` 返回编辑。

编辑器还支持三层区域复制：点击左侧的“框选工具 [M]”（或按 `M`，也可按住 `Shift` 后用左键拖动）进入框选模式；按住左键在地图上拖出黄色矩形，松开后按 `Ctrl+C` 复制。编辑器会显示复制范围、三层内容和碰撞格数量的确认提示。随后点击左侧“开始粘贴 [Ctrl+V]”（或按 `Ctrl+V`），移动鼠标查看黄色目标框，在目标位置左键放置。粘贴模式会保持开启，可连续点击以重复放置同一棵树或建筑；按 `1/2/3` 返回普通编辑。地面、当前层、上层和当前层碰撞标记会一起复制。

按 `N` 或点击“新建地图 [N]”可以创建新地图。输入 `地图名 宽 高`，例如 `forest2 20 14`，按 Enter 后会生成对应尺寸的地面层、当前层、上层 PNG 和配置项。当前编辑器支持宽 1-40 格、高 1-40 格。地图大于编辑器视口（768×576）时，用 `W/A/S/D` 或鼠标滚轮平移画布，图块仍保持 32×32 清晰显示。

按 `E` 或点击“扩充地图 [E]”可以调整当前地图的宽高（支持扩大和缩小）。输入 `新宽 新高`（例如 `40 30`），按 Enter 后原内容保留在左上角、新增区域留空，超出新尺寸的碰撞格和出生点会被自动清理；改完按 `Ctrl+S` 保存。

## 回归测试

```powershell
python test_event_system.py
python test_adventure.py
```

游戏启动后默认显示 120×120 室外世界。运行中可按数字键 `1-5` 依次查看室外世界、`grancave`、`caveB1F`、`caveB2f` 和 `finalcave`；方向键可按各地图的局部坐标与碰撞数据移动，右上角显示主角当前格坐标，`F1` 返回剧情场景。室外子图更新后，运行 `python tools/build_world_map.py` 可按 `world_connections.json` 重新烘焙三张世界图层。

地图以 480×320（15×10 格）逻辑分辨率运行，并按 2 倍最近邻放大到 960×640 窗口。每次方向输入会触发一个不可中断的四帧原子步；目标格被碰撞数据阻挡时不会移动。

在洞穴地图中，`blocked` 且 upper 层有图块的格子会被视为可击碎岩石。面向相邻岩石按 `Z` 可临时触发场外“重磅冲撞”：命中时清除该格 upper 图块及碰撞并播放碎裂动画，普通墙体不会响应。后续可将同一入口替换为 STC-B 的 `0x09` 震动事件。

世界地图及三层洞穴的楼梯使用统一双向传送表。主角走上楼梯格后会立即切换地图和落点，并播放短暂黑屏淡入；传送不会重新载入地图，因此本次运行中已经粉碎的岩石仍保持粉碎状态。

## 剧情演示路线

1. 在家中走到左上角父亲旁，按 Enter（或开发板中心键）推进对白。
2. 按左键离开家，到森林空地靠近青梅，按 Enter 开始教学战斗。
3. 战斗中用方向键选择四个专属招式，Enter 确认；光照、温度和震动会改变招式效果。
4. 战斗胜利后按 Enter 进入 1 号道路，继续向上经过三段矿洞。
5. 在深处岩石旁晃动开发板；没有开发板时按 `V`。通道打开后继续向上，与基拉祈完成结局。

### 训练战斗操作

青梅事件结束后会进入一场与种子铁球的训练战。`↑/↓/←/→`（或开发板导航键）选择四个技能，`Enter`（或开发板中心键）确认。攻击动画结束后可继续选择；胜利时按 `Enter` 前往 1 号道路，失败时按 `Enter` 重新挑战。

| 技能 | 开发板联动 | 效果 |
| --- | --- | --- |
| 光合作用 | 光敏传感器 | 光照越强，回复越多体力。 |
| 日光束 | 光敏传感器 | 光照越强，伤害越高。 |
| 重磅冲撞 | 震动传感器 | 先晃动学习板使技能进入可用状态；震动次数会提升伤害。 |
| 气象球 | 温度传感器 | 温度大于 30C 为火属性，小于 10C 为冰属性，否则为一般属性。 |

## 剧情事件编辑器

地图剧情统一存放在 `assets/map_events.json`。运行以下命令打开可视化编辑器：

```powershell
python tools/event_editor.py
```

编辑流程：新建事件，选择地图，在地图画布上点击触发格，再选择一个事件图标。随后按播放顺序添加任意数量的“对白”或“战斗”步骤。对白步骤可选择 `assets/resource/dialogue/preloads` 中的宝可梦预载图、输入说话者与多行文本，右下角会以 480×320 实际逻辑分辨率循环预览文字渐入。事件图标来自 `assets/resource/event/icon`；宽图会取第一帧、裁去透明边缘，再以最近邻方式放入 32×32 格。

保存后重新启动游戏读取新事件。主角走入事件格时会自动开始事件；对白期间背景保持为当时的地图或战斗画面，并由预载图淡化。按一次 `Enter`（未来对应 STC-B 中心键）时，如果文字仍在渐入，会立即显示完整文字；文字已经完整时，再按一次进入下一步骤。`once` 开启的事件在一次运行中只触发一次，按 `R` 重置流程后可再次触发。

战斗步骤目前按 `battle_id` 保存，但统一调用现有训练战作为占位。战斗胜利后继续执行下一事件步骤；紧随战斗步骤的对白会保留战斗结束画面作为淡化背景，对白结束后才返回地图。战斗失败后按 `Enter` 会回到原触发地图和坐标，并从事件第一个步骤重新开始。以后接入正式战斗配置时，可用 `battle_id` 创建对应敌人与战场，而无需修改已有事件文件。

事件文件示例：

```json
{
  "version": 1,
  "events": [
    {
      "id": "jirachi_meeting",
      "name": "遇见基拉祈",
      "map": "finalcave",
      "position": [7, 4],
      "icon": "jirachi_sleep_1.png",
      "once": true,
      "steps": [
        {"type": "dialogue", "preload": "jirachi_right.png", "speaker": "基拉祈", "text": "你终于来了。"},
        {"type": "battle", "battle_id": "placeholder"},
        {"type": "dialogue", "preload": "no_portrait_center.png", "speaker": "", "text": "洞穴恢复了平静。"}
      ]
    }
  ]
}
```

原有 `assets/story_events.json` 的父亲/青梅确认键事件和 `assets/step_events.json` 的旧踩格对白仍然兼容，便于逐步迁移。

普通 NPC 事件与 RPG Maker 的行为一致：NPC 自己所在的一格不可通行，主角必须走到相邻格、**面向 NPC** 后按 `Enter`（开发板中心键）才会触发对话。父亲使用独立的 `FERROTHORN_STC.png` 四方向角色图，和主控的 `FERROTHORN_USER.png` 区分开。

踩格事件在 `assets/step_events.json` 中配置，键名格式为 `"格子X,格子Y"`。主角完成走入该格的一步后自动触发一次；按 `R` 重开后可再次触发。示例中的 `route` 的 `"11,14"` 就是从 1 号道路起点向上走一格后触发。

## 事件配置速查

所有事件都使用地图局部坐标，左上角为 `(0,0)`，向右为 X 增加，向下为 Y 增加。游戏右上角会显示当前 X/Y；地图编辑器也能用于核对格子位置。

### 确认键 NPC 事件

`essentials_adventure.py` 中的 `NPC_POS` 管理 NPC 格坐标。NPC 的那一格由程序自动视为碰撞格，不能走入。主角站在上下左右相邻的一格并且面朝 NPC 时，按 `Enter` 或 STC-B 中心键触发对应事件。

父亲使用 `assets/FERROTHORN_STC.png` 四方向角色图；主控使用不同的 `FERROTHORN_USER.png`。父亲和青梅的文本在 `assets/story_events.json` 中编辑，格式如下：

```json
{
  "father": [
    {"speaker": "父亲", "text": "第一句对白"}
  ]
}
```

### 踩格自动事件

在 `assets/step_events.json` 的地图名下添加 `"X,Y"` 记录。每个格子默认每次流程只触发一次，按 `R` 重置流程后可以再次触发。

```json
{
  "route": {
    "11,14": [
      {"speaker": "青梅", "text": "走到这里时自动触发。"}
    ]
  }
}
```

## 对战素材与后续扩展

资源包已包含可直接使用的绿宝石风格对战素材，不需要额外下载：

| 资源 | 位置 | 当前用途 |
| --- | --- | --- |
| 对战背景、平台、消息框 | `assets/resource/battle/backgrounds/` | 已用于训练战斗背景和双方平台 |
| 坚果哑铃及野生宝可梦正背面 | `assets/resource/battle/pokemon/front/`、`back/` | 坚果哑铃背面和种子铁球正面已用于训练战斗 |
| 技能特效 | `assets/resource/battle/effects/` | 光合作用、日光束、重磅冲撞、气象球均已接入短动画 |
| 宝可梦对战 UI | `assets/resource/battle/ui/` | 已接入双方状态框、消息框和四格技能菜单 |
| 音效、招式音效与 BGM | `assets/resource/audio/` | 四种招式已接入可用时自动播放的音效 |

目前训练战斗已经具备回合制选招、HP、胜负、原始 Essentials 风格战斗 UI、四种技能特效/音效和传感器数值联动。下一阶段可以添加敌方招式、属性克制与更多野生宝可梦遭遇，而不必重写现有战斗逻辑。
