#!/usr/bin/env python3
"""Deterministic walkthrough: render the short Astra README tour (optional Pillow/numpy production tools)."""
from __future__ import annotations
import argparse
from pathlib import Path
from render_astra_launch import frame, TOUR
from PIL import ImageDraw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', default='docs/assets/laneorchestrator-demo.gif')
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Compact one-fps preview; the MP4 exports retain thirty-fps motion.
    frames = []
    for index in range(20):
        preview = frame(index + .65, TOUR).resize((1200,675))
        # Playback progress keeps held UI states legible and frames distinct.
        preview = preview.quantize(colors=16)
        palette = preview.getpalette()
        palette += [0] * (768-len(palette))
        palette[48:54] = [188,164,255,52,59,69]
        preview.putpalette(palette)
        draw = ImageDraw.Draw(preview)
        draw.rectangle((60,663,1140,666),fill=17)
        draw.rectangle((60,663,60+int(1080*(index+1)/20),666),fill=16)
        frames.append(preview)
    frames[0].save(output,save_all=True,append_images=frames[1:],duration=1000,loop=0,optimize=True,disposal=2)
    print(output)

if __name__ == '__main__':
    main()
