# Granite Cave tile extraction

The warm brown cave section at Caves.png y=5856 was selected because it is the closest visual match to the Ruby/Sapphire Granite Cave references. The source sheet is from a different tileset generation, so its pixels do not exactly match the reference maps.

- granite_tiles_16.png: compact native-style atlas, 8 columns, 16 x 16 pixels per tile.
- granite_tiles_32.png: primary compact atlas at the current project's 32 x 32 grid size.
- granite_tiles_preview.png: enlarged checkerboard preview with tile IDs; do not load it in-game.
- individual_16/: one 16 x 16 PNG per tile.
- individual_32/: one 32 x 32 PNG per tile.
- 	iles.csv: atlas index, category, and original Caves.png coordinates.

Red-X placeholders, fully transparent cells, the unrelated green row, and exact duplicates are excluded automatically. Both atlases use transparent backgrounds. Caves.png contains some native one-pixel details, so the 16 x 16 atlas is a convenience downsample; use the 32 x 32 atlas for the best fidelity.
