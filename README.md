# STC-B 坚果哑铃实验世界

这是从 Pokémon Essentials/GBA 资源包中提取素材后制作的独立 Python/Pygame 原型，不依赖 RPG Maker 运行时。`assets/resource` 目录保存了你提供的地图、战斗、角色、UI 和音效资源。

## 运行

```powershell
cd E:\openProject\stc_pokemon_game
python adventure.py
```

连接 STC-B 时（可选）：

```powershell
python -m pip install --proxy http://127.0.0.1:7897 pyserial pygame pillow
python adventure.py COM3
```

如果 Clash 没有运行，去掉 `--proxy http://127.0.0.1:7897`；如果更换了 Clash 端口，把 `7897` 改成设置页中显示的端口。

方向键和 Enter 可演示操作，R 重开，V 模拟一次震动。也可以双击 `run.bat` 启动键盘演示。

查看当前串口：

```powershell
python -c "from serial.tools import list_ports; print([(p.device, p.description) for p in list_ports.comports()])"
```

把启动命令中的端口换成实际端口，例如 `python adventure.py COM9`；若端口被 Keil、串口助手或其他程序占用，先关闭占用它的程序。当前电脑检测到 `COM8` 和 `COM9`，其中 `COM8` 曾被占用，建议先试 `COM9`。

## 当前原型

- Essentials/绿宝石风格的序章地图与对话
- 月影山洞使用 resource 包中的 Granite Cave 原始地图素材
- 坚果哑铃主角显示
- 父亲引导至森林空地、青梅教学、流星坠入矿洞的完整剧情流程
- 矿洞岩石阻挡；靠近后用 STC-B 震动传感器触发重磅冲撞并击碎岩石
- 矿洞深处苏醒的基拉祈，以及成为朋友的结尾
- 右侧状态面板：光照、温度、震动次数和当前场景
- 训练战斗页：日光束、光合作用、重磅冲撞的数值随传感器变化
- STC-B 协议兼容：方向/确认指令 `0x01-0x05`，重开 `0x06`，导航键 3 切页 `0x08`，震动 `0x09`，光照/温度数据帧 `0x40/0x41`

原 RPG Maker 工程保持不变，提取的资源副本位于 `assets` 目录。

## STC-B 开发板固件

开发板端 Keil/C51 工程已放在 `firmware/stc_bsp_gomoku`，包括 `main.c`、完整 BSP 头文件、`STCBSP_V3.6.LIB`、Keil 工程配置和可直接烧录的 HEX。开发板负责按键、震动、光照和温度采集，电脑端 `adventure.py` 负责游戏逻辑与画面，二者通过 9600 baud 串口协议连接。协议和烧录流程见 [firmware/README.md](firmware/README.md)。

## 三层地图编辑器（像 RPG Maker 一样搭图）

编辑器左侧是 `Outside.png` 图块资源区，右侧是 24×18 地图画布。鼠标选中图块后点击画布即可绘制，支持地面层、当前层、上层，以及当前层碰撞标记和出生点设置：

```powershell
cd E:\openProject\stc_pokemon_game
python tools/map_editor.py home       # 编辑父亲的家
python tools/map_editor.py friend     # 编辑青梅空地
python tools/map_editor.py route      # 编辑 1 号道路
```

快捷键：`1/2/3` 切换三层，`C` 切换当前层碰撞标记模式，`P` 设置出生点，左键绘制、右键擦除，`←/→` 翻图块页，`S` 保存。保存后会更新 `assets/maps/*_lower.png`、`*_current.png`、`*_upper.png` 和 `outdoor_maps.json`，游戏下次启动自动读取。

切换图层后，当前层会以彩色描边高亮，另外两层变暗：蓝色为地面层、橙色为当前层、紫色为上层。

编辑器还支持三层区域复制：按 `M` 后在地图上拖出矩形范围，按 `Ctrl+C` 复制，再按 `Ctrl+V`，移动鼠标到目标格并点击即可粘贴。地面、当前层、上层和当前层碰撞标记会一起复制，适合重复放置完整树木或建筑。

## 回归测试

```powershell
python test_adventure.py
```

## 剧情演示路线

1. 在家中走到左上角父亲旁，按 Enter（或开发板中心键）推进对白。
2. 按左键离开家，到森林空地靠近青梅，按 Enter 开始教学战斗。
3. 战斗中用方向键选择四个专属招式，Enter 确认；光照、温度和震动会改变招式效果。
4. 战斗胜利后按 Enter 进入 1 号道路，继续向上经过三段矿洞。
5. 在深处岩石旁晃动开发板；没有开发板时按 `V`。通道打开后继续向上，与基拉祈完成结局。
