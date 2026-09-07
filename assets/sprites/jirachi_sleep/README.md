# 基拉祈睡眠循环

本目录包含从 `Jirachi Sleeping Sprite Sheet V2 (2).png` 提取的前三个睡眠姿势，适合在地图中循环播放。第四个起身姿势没有加入循环。

| 文件 | 内容 | 尺寸 |
| --- | --- | --- |
| `jirachi_sleep_1.png` | 熟睡 | 32×32 |
| `jirachi_sleep_2.png` | 呼吸/轻微呼噜 | 32×32 |
| `jirachi_sleep_3.png` | 抱着蓝色呼噜泡 | 32×32 |
| `jirachi_sleep_sheet.png` | 三帧横向 Sprite Sheet | 96×32 |
| `jirachi_sleep_preview.png` | 8 倍最近邻放大预览 | 768×256 |

PNG 文件均为 RGBA，黑色背景已转换为透明，像素使用最近邻缩放以保持像素画边缘。

## 在 Pygame 中播放

逐帧加载时，将 `jirachi_sleep_1.png`、`jirachi_sleep_2.png`、`jirachi_sleep_3.png` 放入列表，按约 350 ms 的间隔循环索引即可。使用 Sprite Sheet 时，可按 `x = frame_index * 32`、`y = 0`、`w = h = 32` 的矩形切出对应帧。

重新从原图生成素材：

```powershell
python tools\extract_sleep_sprites.py
```

脚本会覆盖本目录下的三帧 PNG、96×32 Sprite Sheet 和预览图，不会修改原始图片。
