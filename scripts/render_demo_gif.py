#!/usr/bin/env python3
"""Render the deterministic LaneOrchestrator README product walkthrough."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1200, 675
FPS = 4
SECONDS = 20

BG = "#0B0D12"
PANEL = "#11151E"
PANEL_2 = "#171C27"
BORDER = "#293043"
TEXT = "#F6F7FB"
MUTED = "#9AA4B7"
PURPLE = "#A78BFA"
PURPLE_DARK = "#6D4AFF"
CYAN = "#67E8F9"
GREEN = "#5EE6A8"
AMBER = "#F9C74F"


def font_path() -> str:
    candidates = (
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("No supported monospaced font found")


FONT_FILE = font_path()


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_FILE, size=size)


F12 = font(12)
F14 = font(14)
F16 = font(16)
F18 = font(18)
F20 = font(20)
F24 = font(24)
F30 = font(30)


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def phase(now: float, start: float, duration: float) -> float:
    return ease((now - start) / duration)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, fill: str = MUTED, face: ImageFont.FreeTypeFont = F14) -> None:
    draw.text(xy, value, font=face, fill=fill)


def pill(draw: ImageDraw.ImageDraw, x: int, y: int, value: str, color: str, width: int | None = None) -> None:
    measured = int(draw.textlength(value, font=F12))
    actual = width or measured + 24
    rounded(draw, (x, y, x + actual, y + 28), 14, PANEL_2, color)
    draw.text((x + 12, y + 7), value, font=F12, fill=color)


def header(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(((42, 34), (57, 19), (72, 34), (57, 49)), fill=PURPLE_DARK)
    draw.polygon(((50, 34), (57, 27), (64, 34), (57, 41)), fill=TEXT)
    label(draw, (88, 20), "LaneOrchestrator", TEXT, F24)
    label(draw, (88, 50), "Risk-aware routing for Codex", MUTED, F12)
    pill(draw, 959, 24, "ILLUSTRATIVE PRODUCT TOUR", PURPLE, 199)


STEPS = ("Task", "Route card", "Specialists", "Verification")


def sidebar(draw: ImageDraw.ImageDraw, active: int) -> None:
    label(draw, (48, 112), "WORKFLOW", MUTED, F12)
    for index, name in enumerate(STEPS):
        y = 154 + index * 76
        complete = index < active
        current = index == active
        color = GREEN if complete else PURPLE if current else "#4C556A"
        if index < len(STEPS) - 1:
            draw.line((62, y + 28, 62, y + 72), fill=GREEN if complete else BORDER, width=2)
        draw.ellipse((50, y, 74, y + 24), fill=color if (complete or current) else PANEL, outline=color, width=2)
        if complete:
            draw.line((56, y + 12, 61, y + 17), fill=BG, width=2)
            draw.line((61, y + 17, 69, y + 8), fill=BG, width=2)
        else:
            draw.text((58, y + 5), str(index + 1), font=F12, fill=BG if current else MUTED)
        label(draw, (88, y + 2), name, TEXT if current else MUTED, F16)


def shell_window(draw: ImageDraw.ImageDraw, title: str) -> None:
    rounded(draw, (252, 96, 1158, 590), 18, PANEL, BORDER)
    rounded(draw, (252, 96, 1158, 146), 18, PANEL_2)
    draw.rectangle((252, 128, 1158, 146), fill=PANEL_2)
    for x, color in ((278, "#FF6B6B"), (300, AMBER), (322, GREEN)):
        draw.ellipse((x, 116, x + 10, 126), fill=color)
    label(draw, (357, 113), title, MUTED, F14)


def task_scene(draw: ImageDraw.ImageDraw, now: float) -> None:
    sidebar(draw, 0)
    shell_window(draw, "codex — task intake")
    label(draw, (296, 185), "YOU", CYAN, F12)
    prompt = "$laneorchestrator secure OAuth token storage and update the public API"
    chars = int(len(prompt) * phase(now, 1.0, 3.0))
    label(draw, (296, 220), prompt[:chars], TEXT, F18)
    if chars < len(prompt) and int(now * 2) % 2 == 0:
        cursor_x = 296 + int(draw.textlength(prompt[:chars], font=F18))
        draw.rectangle((cursor_x, 220, cursor_x + 9, 240), fill=PURPLE)
    if now >= 3.4:
        rounded(draw, (296, 286, 1114, 390), 12, PANEL_2, BORDER)
        label(draw, (322, 309), "Evidence detected", MUTED, F12)
        pill(draw, 322, 340, "credentials", AMBER)
        pill(draw, 438, 340, "public contract", AMBER)
        pill(draw, 590, 340, "multi-file", CYAN)
        label(draw, (296, 430), "Unknown or elevated risk cannot select Luna.", MUTED, F16)


def route_scene(draw: ImageDraw.ImageDraw, now: float) -> None:
    sidebar(draw, 1)
    shell_window(draw, "laneorchestrator — route card")
    label(draw, (296, 180), "ROUTE CARD", PURPLE, F12)
    label(draw, (296, 214), "Sol → Terra → Sol", TEXT, F30)
    pill(draw, 296, 260, "HIGH-RISK PATH", AMBER, 132)
    rows = (
        ("WHY", "Credentials and a public API contract raise the blast radius."),
        ("BOUNDARY", "Sol plans read-only; Terra writes only inside the workspace."),
        ("DONE WHEN", "Tests pass and a fresh Sol reviewer approves the result."),
    )
    visible = 1 + int(phase(now, 5.0, 2.2) * 2.99)
    for index, (key, value) in enumerate(rows[:visible]):
        y = 322 + index * 70
        label(draw, (296, y), key, MUTED, F12)
        label(draw, (420, y - 3), value, TEXT, F16)


def specialists_scene(draw: ImageDraw.ImageDraw, now: float) -> None:
    sidebar(draw, 2)
    shell_window(draw, "laneorchestrator — capability shortlist")
    label(draw, (296, 178), "172 BUNDLED SPECIALISTS", PURPLE, F12)
    label(draw, (296, 211), "Three relevant profiles, inside the selected lane", TEXT, F24)
    cards = (
        ("security-auditor", "Review token storage and trust boundaries", PURPLE),
        ("api-designer", "Check the public contract and compatibility", CYAN),
        ("penetration-tester", "Probe practical abuse paths before approval", AMBER),
    )
    visible = 1 + int(phase(now, 9.2, 2.0) * 2.99)
    for index, (name, purpose, color) in enumerate(cards[:visible]):
        y = 275 + index * 84
        rounded(draw, (296, y, 1114, y + 64), 12, PANEL_2, BORDER)
        draw.rectangle((296, y, 301, y + 64), fill=color)
        label(draw, (324, y + 12), name, TEXT, F16)
        label(draw, (555, y + 12), purpose, MUTED, F14)
        pill(draw, 1012, y + 18, "TERRA", color, 78)
    label(draw, (296, 536), "Metadata can suggest expertise; it cannot rewrite the route.", MUTED, F14)


def verification_scene(draw: ImageDraw.ImageDraw, now: float) -> None:
    sidebar(draw, 3)
    shell_window(draw, "laneorchestrator — high-risk gates")
    label(draw, (296, 178), "SAFE HIGH-RISK WORKFLOW", PURPLE, F12)
    label(draw, (296, 211), "Authority stays separated from execution", TEXT, F24)
    stages = (
        ("01", "SOL PLANS", "Read-only threat and change plan", PURPLE),
        ("02", "TERRA IMPLEMENTS", "Scoped workspace changes + tests", CYAN),
        ("03", "SOL REVIEWS", "Fresh independent evidence review", GREEN),
    )
    reveal = 1 + int(phase(now, 13.0, 3.0) * 2.99)
    for index, (number, title, detail, color) in enumerate(stages):
        x = 296 + index * 274
        muted = index >= reveal
        card_color = BORDER if muted else color
        rounded(draw, (x, 282, x + 244, 422), 14, PANEL_2, card_color, 2)
        pill(draw, x + 18, 300, number, card_color, 48)
        label(draw, (x + 18, 348), title, MUTED if muted else TEXT, F14)
        label(draw, (x + 18, 380), detail, MUTED, F12)
        if index < 2:
            draw.line((x + 244, 352, x + 270, 352), fill=BORDER, width=2)
            draw.polygon(((x + 270, 352), (x + 262, 347), (x + 262, 357)), fill=BORDER)
    if now >= 17.0:
        rounded(draw, (296, 464, 1114, 531), 12, "#11241F", GREEN)
        draw.ellipse((322, 483, 342, 503), fill=GREEN)
        draw.line((327, 493, 332, 498), fill=BG, width=2)
        draw.line((332, 498, 338, 488), fill=BG, width=2)
        label(draw, (360, 479), "No silent downgrade. No self-approval. No hidden global mutation.", TEXT, F16)


def render_frame(now: float) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw)
    if now < 5.0:
        task_scene(draw, now)
    elif now < 9.0:
        route_scene(draw, now)
    elif now < 13.0:
        specialists_scene(draw, now)
    else:
        verification_scene(draw, now)
    label(draw, (42, 638), "Deterministic walkthrough • no live credentials • no hidden installation result", MUTED, F12)
    label(draw, (1018, 638), "laneorchestrator", "#667085", F12)
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="docs/assets/laneorchestrator-demo.gif")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = [render_frame(index / FPS) for index in range(FPS * SECONDS)]
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / FPS),
        loop=0,
        optimize=True,
        disposal=2,
    )
    print("rendered {0} frames to {1}".format(len(frames), output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
