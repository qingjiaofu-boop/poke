# 战斗数据

这里的 JSON 是战斗系统的可编辑数据，不需要数据库或专用编辑器。

## 文件职责

- `pokemon.json`：完整宝可梦图鉴。每条记录包含 `id`、显示名、属性、六项种族值、特性和图鉴说明。
- `moves.json`：普通招式。每条记录包含 `id`、显示名、属性、`category`（`Physical`、`Special` 或 `Status`）、威力、命中率、PP 和说明。
- `protagonist_moves.py`：坚果哑铃主角的四个专属招式。它们不用 JSON 保存，因为每次使用都要读取并计算实时 STC-B 数据；模块会把传感器状态转换成普通战斗引擎可以执行的 `Move`。

## 简化战斗规则

`battle_engine.py` 使用默认 6V：所有个体的六项 IV 都是 `31`，EV 默认 `0`，不使用性格、特性效果、道具和状态异常。等级和种族值仍然参与标准的 HP/能力值计算。

伤害公式的核心形状为：

```text
基础伤害 = floor(floor(floor((2×等级/5+2)×威力×攻击/防御)/50)+2)
最终伤害 = floor(基础伤害 × 暴击倍率 × STAB × 属性倍率 × 随机数/255)
```

招式先按 `1..100` 掷骰检验命中率；未命中不会造成伤害。普通招式默认暴击率为 `1/24`，提高暴击等级后依次为 `1/8`、`1/2` 和必定暴击，暴击倍率为 `1.5`。随机数范围为 `217..255`。测试或展示固定数值时传入 `random_factor=255`、`accuracy_roll` 和 `critical_roll`。没有性格修正；物理招式使用攻击/防御，特殊招式使用特攻/特防，变化招式（威力为 0）不造成直接伤害。

## 修改数据

直接用记事本编辑 JSON 即可。`pokemon.json` 的 `base_stats` 顺序和字段固定为：`hp`、`attack`、`defense`、`speed`、`special_attack`、`special_defense`。新增宝可梦时保持相同结构；新增普通招式时保持 `id` 唯一。

如果重新导入资源包中的 Essentials 文本数据：

```powershell
python tools\build_battle_data.py
```

这会根据 `assets/resource/reference_data/pokemon.txt` 和 `moves.txt` 重建 `pokemon.json`、`moves.json`。手动对这两个 JSON 的改动会被重建覆盖，请先备份。

## 主角招式调用

```python
from protagonist_moves import SensorSnapshot, protagonist_move

sensors = SensorSnapshot(light=800, temperature=32, vibration_count=2, heavy_ready=True)
solar = protagonist_move("STC_SOLARBEAM", sensors)
weather = protagonist_move("STC_WEATHERBALL", sensors)  # FIRE，威力翻倍
```

## Python 使用示例

```python
from battle_engine import Battle, Pokemon, load_move, load_species

player = Pokemon(load_species("FERROTHORN"), level=50)  # 默认 6V、无性格
foe = Pokemon(load_species("FERROSEED"), level=20)
solar_beam = load_move("SOLARBEAM")
battle = Battle(player, foe, {solar_beam.id: solar_beam})
result = battle.use_player_move("SOLARBEAM", random_factor=255)
print(result.damage.damage, result.defender_hp)
```
