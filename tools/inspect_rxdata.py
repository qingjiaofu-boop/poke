"""Small Ruby Marshal reader for RPG Maker XP map metadata.

It intentionally extracts only the fields needed by the Pygame prototype:
map names, dimensions, tileset IDs and event coordinates/names.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


class MarshalReader:
    def __init__(self, data: bytes):
        if data[:2] != b"\x04\x08":
            raise ValueError("not Ruby Marshal 4.8 data")
        self.data, self.i, self.objects, self.symbols = data, 2, [], []

    def byte(self):
        value = self.data[self.i]
        self.i += 1
        return value

    def signed(self):
        encoded = self.byte()
        if encoded == 0:
            return 0
        if 1 <= encoded <= 4:
            return encoded - 5
        if 252 <= encoded <= 255:
            count = 256 - encoded
            value = 0
            for shift in range(count):
                value |= self.byte() << (8 * shift)
            return -value
        return encoded - 5

    def symbol(self):
        tag = self.byte()
        if tag == ord(":"):
            size = self.signed()
            value = self.data[self.i:self.i + size].decode("utf-8", "replace")
            self.i += size
            self.symbols.append(value)
            return value
        if tag == ord(";"):
            return self.symbols[self.signed()]
        raise ValueError(f"expected symbol at {self.i - 1}, got {tag!r}")

    def symbol_key(self):
        tag = self.data[self.i]
        if tag == ord("@"):
            self.i += 1
            return f"@ref{self.signed()}"
        return self.symbol()

    def read(self):
        tag = chr(self.byte())
        if tag == "0": return None
        if tag == "T": return True
        if tag == "F": return False
        if tag == "i": return self.signed()
        if tag == ":":
            self.i -= 1
            return self.symbol()
        if tag == ";": return self.symbol()
        if tag == "@": return self.objects[self.signed()]
        if tag == '"':
            size = self.signed()
            value = self.data[self.i:self.i + size]
            self.i += size
            try: result = value.decode("utf-8")
            except UnicodeDecodeError: result = value.decode("latin1")
            self.objects.append(result)
            return result
        if tag == "[":
            result = [self.read() for _ in range(self.signed())]
            self.objects.append(result)
            return result
        if tag == "{":
            result = {}
            self.objects.append(result)
            for _ in range(self.signed()): result[self.read()] = self.read()
            return result
        if tag == "o":
            klass = self.symbol()
            result = {"__class__": klass}
            self.objects.append(result)
            count = self.signed()
            for _ in range(count):
                key = self.symbol_key()
                result[key] = self.read()
            return result
        if tag == "I":
            result = self.read()
            for _ in range(self.signed()): self.symbol(); self.read()
            return result
        if tag == "u":
            klass = self.symbol(); size = self.signed()
            raw = self.data[self.i:self.i + size]; self.i += size
            result = {"__class__": klass, "__raw__": raw.hex()}
            self.objects.append(result)
            return result
        if tag == "f":
            size = self.signed(); raw = self.data[self.i:self.i + size]; self.i += size
            return float(raw.decode("ascii"))
        raise ValueError(f"unsupported Marshal tag {tag!r} at {self.i - 1}")


def parse(path: Path):
    return MarshalReader(path.read_bytes()).read()


def field(obj, *names, default=None):
    if not isinstance(obj, dict): return default
    for name in names:
        if name in obj: return obj[name]
        key = f"@{name}"
        if key in obj: return obj[key]
    return default


def map_summary(path: Path):
    obj = parse(path)
    events = field(obj, "events", default={}) or {}
    event_rows = []
    for event_id, event in events.items() if isinstance(events, dict) else []:
        event_rows.append({"id": event_id, "x": field(event, "x"), "y": field(event, "y"), "name": field(event, "name")})
    return {"file": path.name, "name": path.stem, "width": field(obj, "width"), "height": field(obj, "height"), "tileset_id": field(obj, "tileset_id", "tileset"), "events": event_rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--maps", action="store_true")
    args = ap.parse_args()
    if args.maps:
        infos = parse(args.data / "MapInfos.rxdata")
        rows = []
        for key, value in sorted(infos.items(), key=lambda item: int(item[0])):
            rows.append({"id": key, "name": field(value, "name"), "order": field(value, "order")})
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(map_summary(args.data), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
