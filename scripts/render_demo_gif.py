#!/usr/bin/env python3
"""Deterministic walkthrough: render the short Astra README tour (optional Pillow/numpy production tools)."""
from __future__ import annotations
import argparse
from pathlib import Path
from render_astra_launch import frame, TOUR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', default='docs/assets/laneorchestrator-demo.gif')
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Compact one-fps preview; the MP4 exports retain thirty-fps motion.
    frames = [frame(index + .65, TOUR).resize((1200,675)).quantize(colors=16) for index in range(20)]
    frames[0].save(output,save_all=True,append_images=frames[1:],duration=1000,loop=0,optimize=True,disposal=2)
    print(output)

if __name__ == '__main__':
    main()
