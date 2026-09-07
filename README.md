# STC-B 坚果哑铃实验世界

这是从 Pokémon Essentials/GBA 资源包中提取素材后制作的独立 Python/Pygame 原型。由于前期 STC 串口方案存在问题，项目已不再使用原有的 RPG Maker 工程。`assets/resource` 目录保存了地图、战斗、角色、UI 和音效资源。

## 运行

推荐在 Windows 上使用 Python 3.12（Python 3.10-3.13 均可）。首次运行时，在 PowerShell 中依次执行：

```powershell
git clone https://github.com/yee810/poke.git
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

## 当前原型

- Essentials/绿宝石风格的序章地图与对话
- Hades 风格事件对白：角色立绘卡片 + 旁侧文本框，文本可外部编辑
- 坚果哑铃主角显示
- 流星坠入矿洞，好奇的坚果哑铃前去冒险寻找的完整剧情流程
- 矿洞岩石阻挡；靠近后用 STC-B 震动传感器触发重磅冲撞并击碎岩石
- 矿洞深处苏醒的基拉祈，以及成为朋友的结尾
- 右上角地图坐标和传感器状态提示
- 训练战斗页：日光束、光合作用、重磅冲撞的数值随传感器变化
- STC-B 协议兼容：方向/确认指令 `0x01-0x05`，重开 `0x06`，导航键 3 切页 `0x08`，震动 `0x09`，光照/温度数据帧 `0x40/0x41`

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

快捷键：`1/2/3` 切换三层，`4` 切换游戏最终画面预览，`C` 切换当前层碰撞标记模式，`P` 设置出生点，左键绘制、右键擦除，`←/→` 翻图块页，`G` 输入页码后直接跳转图块页，`T` 切换图块集，`O` 打开已有地图，`E` 扩充/调整地图尺寸，`W/A/S/D`（或滚轮）平移画布，`Ctrl+S` 保存。也可以点击左侧的“跳转图块页 [G]”或“保存地图 [Ctrl+S]”按钮。保存后会更新 `assets/maps/*_lower.png`、`*_current.png`、`*_upper.png` 和 `outdoor_maps.json`，游戏下次启动自动读取。

按 `O` 或点击“打开已有地图 [O]”会弹出 `outdoor_maps.json` 里已有的地图列表（也会扫描 `assets/maps/*_lower.png`），用 `↑/↓`（或 `PgUp/PgDn`、滚轮）选择、`Enter` 打开；打开前会自动保存当前地图的未保存修改。

切换图层后，当前层会以彩色描边高亮，另外两层变暗：蓝色为地面层、橙色为当前层、紫色为上层。按 `4` 后三层会按游戏实际顺序正常合成，并隐藏编辑辅助框，便于检查最终效果；按 `1/2/3` 返回编辑。

编辑器还支持三层区域复制：点击左侧的“框选工具 [M]”（或按 `M`，也可按住 `Shift` 后用左键拖动）进入框选模式；按住左键在地图上拖出黄色矩形，松开后按 `Ctrl+C` 复制。编辑器会显示复制范围、三层内容和碰撞格数量的确认提示。随后点击左侧“开始粘贴 [Ctrl+V]”（或按 `Ctrl+V`），移动鼠标查看黄色目标框，在目标位置左键放置。粘贴模式会保持开启，可连续点击以重复放置同一棵树或建筑；按 `1/2/3` 返回普通编辑。地面、当前层、上层和当前层碰撞标记会一起复制。

按 `N` 或点击“新建地图 [N]”可以创建新地图。输入 `地图名 宽 高`，例如 `forest2 20 14`，按 Enter 后会生成对应尺寸的地面层、当前层、上层 PNG 和配置项。当前编辑器支持宽 1-40 格、高 1-40 格。地图大于编辑器视口（768×576）时，用 `W/A/S/D` 或鼠标滚轮平移画布，图块仍保持 32×32 清晰显示。

按 `E` 或点击“扩充地图 [E]”可以调整当前地图的宽高（支持扩大和缩小）。输入 `新宽 新高`（例如 `40 30`），按 Enter 后原内容保留在左上角、新增区域留空，超出新尺寸的碰撞格和出生点会被自动清理；改完按 `Ctrl+S` 保存。

## 回归测试

```powershell
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

## 剧情事件编辑器

对白存放在 `assets/story_events.json`，程序启动时自动读取；每条记录包含
`speaker` 和 `text`，例如 `{"speaker":"父亲","text":"去左边的森林空地。"}`。
不想手动编辑 JSON 时，可运行：

```powershell
python tools/event_editor.py
```

在窗口中选择 `father`（父亲事件）或 `friend`（青梅事件），新增、更新、删除对白后点击“保存 JSON”。重新启动游戏即可看到新的立绘对白。当前立绘使用 `introOak.png`、`introMarill.png` 和坚果哑铃素材；没有对应立绘时仍会正常显示文本框。

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
| 对战背景、平台、消息框 | `assets/resource/battle/backgrounds/` | 已用于训练战斗背景 |
| 坚果哑铃及野生宝可梦正背面 | `assets/resource/battle/pokemon/front/`、`back/` | 坚果哑铃已用于训练战斗；可替换敌方立绘 |
| 技能特效 | `assets/resource/battle/effects/` | 可接入日光束、光合作用、重磅冲撞、气象球动画 |
| 宝可梦对战 UI | `assets/resource/battle/ui/` | 可替换当前简化 HP 与技能菜单 |
| 音效、招式音效与 BGM | `assets/resource/audio/` | 可在攻击、胜利、菜单操作时播放 |

目前训练战斗已经具备回合制选招、HP、胜负和传感器数值联动。下一阶段建议优先把 `battle/ui` 的状态框和 `battle/effects` 的四个专属招式特效接入现有 `draw_battle` / `use_move`，而不是重写战斗逻辑。
