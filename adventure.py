"""Default launcher for the STC-B Pokemon-style adventure."""
from __future__ import annotations

import sys

from essentials_adventure import Game


Adventure = Game


if __name__ == "__main__":
    Adventure(sys.argv[1] if len(sys.argv) > 1 else None).run()
