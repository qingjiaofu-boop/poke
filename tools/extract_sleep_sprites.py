"""Extract the first three sleeping Jirachi poses as transparent 32x32 sprites."""

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


SOURCE = Path(r"E:\Jirachi Sleeping Sprite Sheet V2 (2).png")
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "sprites" / "jirachi_sleep"

# The source is 2560x1440. These regions exclude the top-right generator mark
# and isolate the first three sleeping poses.
FRAME_BOXES = (
    (35, 570, 620, 965),
    (620, 570, 1205, 965),
    (1200, 570, 1790, 975),
)


def transparent_background(crop: Image.Image) -> Image.Image:
    """Remove edge-connected near-black pixels while keeping black outlines."""
    rgb = np.asarray(crop.convert("RGB"))
    dark = np.all(rgb <= 45, axis=2)
    labels, _ = ndimage.label(dark, structure=np.ones((3, 3), dtype=np.int8))
    edge_labels = np.unique(np.r_[labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    background = np.isin(labels, edge_labels)
    mask = ~background
    points = np.argwhere(mask)
    if not len(points):
        raise RuntimeError("No sprite pixels found in crop")
    y0, x0 = points.min(axis=0)
    y1, x1 = points.max(axis=0) + 1
    rgba = np.dstack((rgb, (mask * 255).astype(np.uint8)))
    return Image.fromarray(rgba, "RGBA").crop((x0, y0, x1, y1))


def main():
    source = Image.open(SOURCE).convert("RGBA")
    if source.size != (2560, 1440):
        raise RuntimeError(f"Unexpected source size: {source.size}")

    extracted = [transparent_background(source.crop(box)) for box in FRAME_BOXES]
    max_dimension = max(max(frame.width, frame.height) for frame in extracted)
    scale = 30 / max_dimension

    OUTPUT.mkdir(parents=True, exist_ok=True)
    final_frames = []
    for index, frame in enumerate(extracted, 1):
        size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
        sprite = frame.resize(size, Image.Resampling.NEAREST)
        canvas = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        canvas.alpha_composite(sprite, ((32 - size[0]) // 2, 31 - size[1]))
        path = OUTPUT / f"jirachi_sleep_{index}.png"
        canvas.save(path)
        final_frames.append(canvas)
        print(path)

    sheet = Image.new("RGBA", (32 * len(final_frames), 32), (0, 0, 0, 0))
    for index, frame in enumerate(final_frames):
        sheet.alpha_composite(frame, (index * 32, 0))
    sheet_path = OUTPUT / "jirachi_sleep_sheet.png"
    sheet.save(sheet_path)
    print(sheet_path)
    preview = sheet.resize((sheet.width * 8, sheet.height * 8), Image.Resampling.NEAREST)
    preview.save(OUTPUT / "jirachi_sleep_preview.png")


if __name__ == "__main__":
    main()
