# STC-B 固件

`stc_bsp_gomoku` 是本项目使用的 STC-B 学习板固件。它使用 Keil C51 和课程提供的 STC-B BSP 库编译，开发板通过 USB 转串口与电脑上的 Pygame 游戏通信。

## 数据关系

```text
导航键 / K1 / K2 / 震动传感器
                │
                ▼
       STC-B main.c + BSP
                │  9600 8N1
                ▼
       USB 串口（COM3 等）
                │
                ▼
   adventure.py / essentials_adventure.py
                │
                ▼
       游戏移动、剧情、战斗和传感器效果
```

开发板只负责采集输入并发送协议帧；游戏逻辑、地图渲染和战斗计算在电脑端完成。开发板收到电脑发送的结果码后，会在数码管显示 `SUCCESS`、`YOU LOSE` 或难度提示。

## 串口协议

| 字节 | 含义 |
|---|---|
| `0x01` | 导航上 |
| `0x02` | 导航下 |
| `0x03` | 导航左 |
| `0x04` | 导航右 |
| `0x05` | 导航中心/确认 |
| `0x06` | K1，重新开始 |
| `0x07` | K2，取消 |
| `0x08` | 导航键 3，切换场景/难度 |
| `0x09` | 震动传感器触发 |
| `0x40 hi lo` | 光照 ADC 值 |
| `0x41 hi lo` | 温度 ADC 值 |

电脑端发送给开发板：

| 字节 | 数码管显示 |
|---|---|
| `0x20` | SUCCESS |
| `0x21` | YOU LOSE |
| `0x22` | 难度提示 |

## Keil 编译与烧录

1. 使用 Keil uVision4/Keil C51 打开 `STC_BSP_Gomoku.uvproj`。
2. 确认目标芯片为 `STC15F2K60S2`、晶振为 `11.0592 MHz`。
3. 工程的 Include Path 已指向 `inc`，BSP 库为 `STCBSP_V3.6.LIB`。
4. Build Target 生成 `output/STC_BSP_Gomoku.hex`。
5. 使用 STC-ISP 或课程指定烧录工具，将 HEX 写入 STC-B 学习板。

仓库同时保留当前可直接烧录的 HEX 文件，位置是 `output/STC_BSP_Gomoku.hex`。如果只运行电脑端游戏，不需要重新编译固件。
