# 第三世代战斗 UI（2×）

本目录以 GBA 原生 240×160 像素为 1×，按最近邻放大为项目使用的 480×320（2×）逻辑尺寸。所有图集坐标、切片尺寸和推荐屏幕位置均为偶数，运行时不要再做平滑采样。

## 主要文件

- `gen3_battle_ui_atlas_2x.png`：透明总精灵表。
- `manifest.json`：图集矩形、原图切割矩形和 480×320 推荐布局。
- `*_2x.png`：便于直接加载的独立透明切片。
- `preview_command_480x320.png`：普通指令界面组合预览。
- `preview_fight_480x320.png`：四技能界面组合预览。

`databox_player_2x.png` 已去掉等级和经验条；`databox_player_classic_2x.png` 保留原版经验条。`panel_command_2x.png` 和 `panel_move_info_2x.png` 是无文字版本，适合运行时绘制中文；带 `_classic` 的版本保留原始英文标签。

HP 框内默认是空槽。根据当前比例裁切 `hp_fill_green/yellow/red_2x.png` 的宽度后覆盖到空槽即可，不要横向缩放色条，否则像素宽度会不稳定。

重新生成：

```powershell
python tools/build_gen3_battle_ui.py
```

源图为 `assets/resource/Game Boy Advance - Pokemon FireRed _ LeafGreen - Battle Effects - HP Bars & In-battle Menu.png`。`battleUisolo.jpg` 仅用于核对 480×320 画面布局，不参与切割，避免 JPEG 压缩污染像素边缘。
