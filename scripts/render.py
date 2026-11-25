#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from math import ceil, cos, pi, sin, sqrt
from pathlib import Path
import random
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError


PALETTES = {
    "thermal": ("#150e3b", "#692062", "#f04449", "#f9c945", "#27e5b0", "#7cd8ff", "#ffffff"),
    "cobalt": ("#090c32", "#2034a7", "#663bec", "#f197eb", "#fff4e6"),
    "violet": ("#170c2c", "#592a89", "#bf66c9", "#ffe6fb"),
    "acid": ("#0b1b18", "#2f7157", "#a6df67", "#fbffd7"),
    "mono": ("#151519", "#f7f4ec"),
}
INK = (22, 23, 28)
PAPER = (245, 243, 235)


@dataclass(frozen=True)
class Settings:
    density: int | None
    color: tuple | None
    background: tuple | None
    palette: tuple
    seed: int
    fps: int


def rgb_image(values):
    return Image.fromarray(np.uint8(np.clip(values, 0, 255)))


def rgba_color(color, alpha):
    return (*color, round(min(255, max(0, alpha))))


def solid(size, color):
    return Image.new("RGB", size, color)


def array(image):
    return np.asarray(image, dtype=np.float32)


@lru_cache(maxsize=48)
def font(size):
    return ImageFont.load_default(size=max(6, round(size)))


def dashed(draw, start, end, color, unit):
    x1, y1 = start
    x2, y2 = end
    length = max(1, round(sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)))
    for pos in range(0, length, unit * 2):
        a, b = pos / length, min(1, (pos + unit) / length)
        draw.line((x1 + (x2 - x1) * a, y1 + (y2 - y1) * a,
                   x1 + (x2 - x1) * b, y1 + (y2 - y1) * b), fill=color)


def schematic(image, settings, _frame):
    width, height = image.size
    scale = min(width, height)
    color = settings.color or (182, 231, 249)
    grid = rgba_color(color, 77)
    fine = rgba_color(color, 102)
    marks = rgba_color(color, 220)
    rng = random.Random(settings.seed)
    layer = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(layer)
    margin = round(scale * 0.085)
    step = max(5, round(scale / 37))
    for x in range(margin, width - margin + 1, step):
        draw.point([(x, y) for y in range(margin, height - margin + 1, step)], fill=grid)
    draw.rectangle((margin, margin, width - margin, height - margin), outline=fine)
    dashed(draw, (margin, height / 2), (width - margin, height / 2), fine, max(2, step // 3))
    dashed(draw, (width / 2, margin), (width / 2, height - margin), fine, max(2, step // 3))
    for i in range(3):
        y = height * (0.29 + i * 0.21)
        radius = scale * (0.17 - 0.012 * (i % 2))
        x = width * 0.50 + rng.uniform(-0.025, 0.025) * scale
        for ratio in (0.30, 0.67, 1.0):
            r = radius * ratio
            draw.ellipse((x - r, y - r, x + r, y + r), outline=fine)
        points = [(x + radius * cos(a * pi / 12), y + radius * sin(a * pi / 12))
                  for a in range(24)]
        offset = rng.randrange(2, 5)
        for j, point in enumerate(points):
            draw.line((point, points[(j + offset * 2) % len(points)]), fill=grid)
            draw.line((point, points[(j + 3) % len(points)]), fill=fine)
        draw.rectangle((x - radius, y - radius, x + radius, y + radius), outline=grid)
        draw.line((x - step, y, x + step, y), fill=marks)
        draw.line((x, y - step, x, y + step), fill=marks)
    count = max(3, min(20, settings.density or 11))
    points = []
    for i in range(count):
        t = i / (count - 1)
        x = width * (0.22 + 0.56 * t) + scale * 0.06 * sin(t * 5 * pi + 0.5)
        y = height * (0.15 + 0.70 * t)
        radius = scale * (0.06 + 0.043 * sin(pi * t) + rng.uniform(-0.010, 0.010))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=fine)
        px = x + radius * cos(t * 4 * pi + 0.5)
        py = y + radius * sin(t * 4 * pi + 0.5)
        points.append((px, py))
        dot = max(1, round(scale / 480))
        draw.ellipse((px - dot, py - dot, px + dot, py + dot), fill=marks)
        label = f"{round(px):04d}.{round(py):04d}"
        draw.text((min(width - margin - scale * 0.13, px + dot * 3), py - 2),
                  label, font=font(scale / 105), fill=marks)
    draw.line(points, fill=grid)
    lower = Image.blend(image, solid(image.size, (8, 15, 24)), 0.16)
    return Image.alpha_composite(lower.convert("RGBA"), layer).convert("RGB")


def tracker(image, settings, _frame):
    width, height = image.size
    scale = min(width, height)
    color = settings.color or (255, 132, 52)
    layer = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(layer)
    sample = np.asarray(ImageOps.grayscale(image).resize((22, 22), Image.Resampling.BOX), dtype=np.float32)
    dx = np.abs(np.diff(sample, axis=1, prepend=sample[:, :1]))
    dy = np.abs(np.diff(sample, axis=0, prepend=sample[:1, :]))
    scores = np.hypot(dx, dy)
    scores[[0, 1, 20, 21], :] = 0
    scores[:, [0, 1, 20, 21]] = 0
    rng = random.Random(settings.seed)
    points = []
    for index in range(min(settings.density or 9, 30)):
        row, col = np.unravel_index(np.argmax(scores), scores.shape)
        if scores[row, col] < 4:
            break
        scores[max(0, row - 2):row + 3, max(0, col - 2):col + 3] = 0
        x = (col + 0.5) / 22 * width
        y = (row + 0.5) / 22 * height
        box_w, box_h = (scale * rng.uniform(0.074, 0.152), scale * rng.uniform(0.057, 0.143))
        right, bottom = min(width - 1, x + box_w), min(height - 1, y + box_h)
        label_h = max(8, round(scale / 48))
        draw.rectangle((x, y, right, bottom), outline=rgba_color(color, 215), width=max(1, round(scale / 680)))
        draw.rectangle((x, y, min(right, x + scale * 0.079), y + label_h),
                       fill=rgba_color(color, 192))
        draw.text((x + 2, y + label_h / 2), f"ROI {index + 1:02d}", anchor="lm",
                  font=font(label_h * 0.69), fill=(20, 19, 21, 255))
        points.append((x + box_w / 2, y + box_h / 2))
    points.sort()
    for start, end in zip(points, points[1:]):
        dashed(draw, start, end, rgba_color(color, 107), max(2, round(scale / 182)))
    return Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")


def signal(image, settings, frame, effect):
    width, height = image.size
    rng = np.random.default_rng(settings.seed + frame)
    pixels = array(image)
    y, x = np.ogrid[:height, :width]
    step = max(2, round(height / 260))
    shift = max(1, round(width * (0.006 if effect == "vhs" else 0.004)))
    wave = np.zeros((height, 1), dtype=int)
    if effect == "vhs":
        wave = np.int32(np.sin(y * 0.035 + frame * 0.32) * shift * 1.1)
        for row in rng.integers(0, height, size=4):
            wave[row:row + max(2, height // 110)] += rng.integers(-shift * 5, shift * 5 + 1)
    red = pixels[y, (x + wave - shift).clip(0, width - 1), 0]
    green = pixels[y, (x + wave).clip(0, width - 1), 1]
    blue = pixels[y, (x + wave + shift).clip(0, width - 1), 2]
    result = np.stack((red, green, blue), axis=2)
    if effect == "crt":
        triad = np.float32(((1.00, 0.81, 0.81), (0.81, 1.00, 0.81), (0.81, 0.81, 1.00)))
        result *= triad[x[0] % 3]
        vignette = 1 - 0.15 * ((2 * x / max(1, width - 1) - 1) ** 2 + (2 * y / max(1, height - 1) - 1) ** 2)
        result *= vignette[:, :, None]
    result *= np.where((y + frame // 2) % step == 0, 0.76, 1.0)[:, :, None]
    result += rng.normal(0, 5 if effect == "crt" else 9, (height, width, 1)).astype(np.float32)
    return rgb_image(result)


def crt(image, settings, frame):
    return signal(image, settings, frame, "crt")


def vhs(image, settings, frame):
    return signal(image, settings, frame, "vhs")


def glitch(image, settings, frame):
    width, height = image.size
    rng = np.random.default_rng(settings.seed + frame // 3)
    source = np.asarray(image)
    rows = np.zeros(height, dtype=int)
    block = max(1, round(height / 52))
    for top in rng.integers(0, height, max(4, min(settings.density or 14, 160))):
        rows[top:top + int(rng.integers(block, 6 * block + 1))] = int(rng.uniform(-0.13, 0.13) * width)
    y, x = np.ogrid[:height, :width]
    luminance = np.asarray(ImageOps.grayscale(image.resize((max(1, width // 24), max(1, height // 24)),
                                                              Image.Resampling.BOX)
                                             .resize(image.size, Image.Resampling.NEAREST)), dtype=float)
    local = ((luminance - 128) / 256 * (rows[:, None] != 0) * width * 0.048).astype(int)
    return Image.fromarray(source[y, np.clip(x + rows[:, None] + local, 0, width - 1)])


def screen(image, settings, effect):
    width, height = image.size
    density = settings.density or {"halftone": 62, "stripes": 96, "ascii": 90}[effect]
    cell = max(3, round(min(width, height) / density))
    cols, rows = ceil(width / cell), ceil(height / cell)
    samples = np.asarray(ImageOps.grayscale(image.resize((cols, rows), Image.Resampling.BOX)))
    ink = settings.color or ((190, 240, 214) if effect == "ascii" else INK)
    background = settings.background or ((13, 23, 27) if effect == "ascii" else PAPER)
    texture = solid(image.size, background)
    draw = ImageDraw.Draw(texture)
    glyphs = " .:-=+*#%@"
    face = font(cell * 0.95) if effect == "ascii" else None
    for row in range(rows):
        for col in range(cols):
            value = int(samples[row, col])
            x, y = col * cell + cell / 2, row * cell + cell / 2
            if effect == "ascii":
                glyph = glyphs[round(value / 255 * (len(glyphs) - 1))]
                if glyph != " ":
                    draw.text((x, y), glyph, font=face, fill=ink, anchor="mm")
                continue
            amount = (1 - value / 255) ** 0.90
            if amount < 0.04:
                continue
            if effect == "stripes":
                line = min(cell - 1, max(1, round(amount * cell * 0.95)))
                left = round(x - line / 2)
                draw.rectangle((left, row * cell, left + line - 1, (row + 1) * cell - 1), fill=ink)
            else:
                radius = min(cell * 0.54, sqrt(amount) * cell * 0.55)
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=ink)
    return texture


def halftone(image, settings, _frame):
    return screen(image, settings, "halftone")


def stripes(image, settings, _frame):
    return screen(image, settings, "stripes")


def ascii_screen(image, settings, _frame):
    return screen(image, settings, "ascii")


def dither(image, settings, _frame):
    width, height = image.size
    density = settings.density or 112
    cell = max(1, round(min(image.size) / density))
    dims = (ceil(width / cell), ceil(height / cell))
    restored = ImageOps.grayscale(image.resize(dims, Image.Resampling.BOX))
    pixels = array(restored) / 255
    bayer = np.float32(((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5)))
    y, x = np.ogrid[:dims[1], :dims[0]]
    threshold = (bayer[y % 4, x % 4] + 0.5) / 16
    palette = np.array((settings.color or INK, settings.background or PAPER), dtype=np.uint8)
    return Image.fromarray(palette[(pixels >= threshold).astype(int)]).resize(image.size, Image.Resampling.NEAREST)


def recolor(image, settings, _frame):
    tones = array(ImageOps.grayscale(image))
    ramp = np.asarray(settings.palette, dtype=float)
    stops = np.linspace(0, 255, len(ramp))
    values = np.clip((tones - 128) * 1.13 + 128, 0, 255)
    mapped = np.stack([np.interp(values, stops, ramp[:, channel]) for channel in range(3)], axis=2)
    return rgb_image(mapped)


def logo_glow(image, settings, frame, alpha):
    if alpha is None:
        original = array(image)
        corners = np.array((original[0, 0], original[0, -1], original[-1, 0], original[-1, -1]))
        difference = np.max(np.abs(original - np.median(corners, axis=0)), axis=2)
        alpha = Image.fromarray(np.uint8(np.clip((difference - 10) * 2.5, 0, 255)))
    scale = min(image.size)
    pulse = 0.84 + 0.16 * cos(frame / settings.fps * 2 * pi / 2.4)
    color = np.array(settings.color or (56, 111, 255), dtype=np.float32)
    background = np.array(settings.background or (6, 9, 19), dtype=np.float32)
    mask = array(alpha) / 255
    broad = array(alpha.filter(ImageFilter.GaussianBlur(max(1, scale * 0.045 * pulse)))) / 255
    narrow = array(alpha.filter(ImageFilter.GaussianBlur(max(1, scale * 0.009)))) / 255
    glow = np.clip((broad - mask) * 1.25 + (narrow - mask) * 1.30, 0, 1)
    core = np.clip(narrow * (1 - mask), 0, 1)
    rgb = background + glow[:, :, None] * color * (0.8 + pulse * 0.42) + core[:, :, None] * 83
    rim = np.clip(mask - narrow, 0, 1)[:, :, None]
    rgb = rgb * (1 - mask[:, :, None] * 0.83) + rim * color * 2.1
    return rgb_image(rgb)


EFFECTS = {
    "schematic": (schematic, 0.92),
    "tracker": (tracker, 0.91),
    "crt": (crt, 0.84),
    "vhs": (vhs, 0.86),
    "glitch": (glitch, 0.94),
    "halftone": (halftone, 1.0),
    "stripes": (stripes, 1.0),
    "dither": (dither, 1.0),
    "ascii": (ascii_screen, 1.0),
    "recolor": (recolor, 1.0),
    "logo-glow": (logo_glow, 1.0),
}


def render(source, settings, effects, frame=0):
    alpha = None
    if "A" in source.getbands():
        candidate = source.getchannel("A")
        if candidate.getextrema()[0] < 255:
            alpha = candidate
    if alpha is not None:
        image = solid(source.size, settings.background or (13, 16, 22))
        image.paste(source.convert("RGB"), mask=alpha)
    else:
        image = source.convert("RGB")
    for index, (name, strength) in enumerate(effects):
        if strength == 0:
            continue
        effect = EFFECTS[name][0]
        if name == "logo-glow":
            result = effect(image, settings, frame, alpha if index == 0 else None)
        else:
            result = effect(image, settings, frame)
        image = result if strength == 1 else Image.blend(image, result, strength)
    return image


def fit(size, limit, even=False):
    if even and limit:
        limit -= limit % 2
    factor = min(1, limit / max(size)) if limit else 1
    if even:
        return tuple(max(2, round(side * factor / 2) * 2) for side in size)
    return tuple(max(1, round(side * factor)) for side in size)


def open_still(path):
    try:
        with Image.open(path) as source:
            if getattr(source, "is_animated", False):
                return None
            return ImageOps.exif_transpose(source).convert("RGBA")
    except UnidentifiedImageError:
        return None


def video_size(path):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
           "stream=width,height,sample_aspect_ratio:stream_side_data=rotation", "-of", "json", str(path)]
    meta = json.loads(subprocess.check_output(cmd))
    if not meta.get("streams"):
        raise ValueError("Input has no image or video stream.")
    stream = meta["streams"][0]
    width, height = stream["width"], stream["height"]
    sar = stream.get("sample_aspect_ratio", "1:1")
    if sar not in ("N/A", "0:1", "1:1"):
        num, den = map(int, sar.split(":"))
        if num > 0 and den > 0:
            width = round(width * num / den)
    rotation = next((side["rotation"] for side in stream.get("side_data_list", []) if "rotation" in side), 0)
    return (height, width) if rotation % 180 else (width, height)


def render_video(source, still, output, args, settings):
    if not shutil.which("ffmpeg") or (still is None and not shutil.which("ffprobe")):
        raise ValueError("Video export requires FFmpeg and FFprobe on PATH.")
    dimensions = still.size if still is not None else video_size(source)
    width, height = fit(dimensions, args.size or 1080, even=True)
    fps = settings.fps
    decode = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source),
              "-map", "0:v:0", "-vf", f"fps={fps},scale={width}:{height}:flags=lanczos,setsar=1",
              "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    encode = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
              "-s", f"{width}x{height}", "-r", str(fps), "-i", "-"]
    if still is None:
        encode += ["-i", str(source), "-map", "0:v:0", "-map", "1:a:0?",
                   "-c:a", "aac", "-af", "apad", "-shortest"]
    encode += ["-c:v", "libx264", "-preset", "fast", "-crf", "18",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    reader = None
    if still is not None:
        still = still.resize((width, height), Image.Resampling.LANCZOS)
    else:
        reader = subprocess.Popen(decode, stdout=subprocess.PIPE)
    writer = None
    try:
        writer = subprocess.Popen(encode, stdin=subprocess.PIPE)
        frame = 0
        stop = round(args.animate * fps) if still is not None else None
        byte_count = width * height * 3
        # Static effects on static input only need one render.
        moves = any(name in ("crt", "vhs", "glitch", "logo-glow") and strength for name, strength in args.effect)
        still_frame = render(still, settings, args.effect).tobytes() if still is not None and not moves else None
        while stop is None or frame < stop:
            if reader:
                raw = reader.stdout.read(byte_count)
                if not raw:
                    break
                if len(raw) != byte_count:
                    raise ValueError("The decoder returned an incomplete frame.")
                image = Image.frombytes("RGB", (width, height), raw)
            else:
                image = still
            writer.stdin.write(still_frame if still_frame is not None else
                               render(image, settings, args.effect, frame).tobytes())
            frame += 1
        if reader and reader.wait() != 0:
            raise ValueError("FFmpeg could not decode the video.")
        writer.stdin.close()
        if writer.wait() != 0 or not frame:
            raise ValueError("FFmpeg could not encode a playable video.")
    finally:
        for process in (reader, writer):
            if process is None:
                continue
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout:
                process.stdout.close()
            if process.stdin and not process.stdin.closed:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass


def color_value(value):
    try:
        return ImageColor.getcolor(value, "RGB")
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"Invalid color {value!r}.") from error


def palette_value(value):
    named = PALETTES[value] if value in PALETTES else [part.strip() for part in value.split(",")]
    if len(named) < 2:
        raise argparse.ArgumentTypeError("Use a named palette or at least two comma-separated colors.")
    return tuple(color_value(color) for color in named)


def effect_value(value):
    effect, separator, amount = value.partition(":")
    if effect not in EFFECTS:
        raise argparse.ArgumentTypeError(f"Unknown effect {effect!r}. Try {', '.join(EFFECTS)}.")
    if separator:
        try:
            strength = float(amount)
        except ValueError as error:
            raise argparse.ArgumentTypeError("Effect strength must be a number from 0 to 1.") from error
        if not 0 <= strength <= 1:
            raise argparse.ArgumentTypeError("Effect strength must be from 0 to 1.")
    else:
        strength = EFFECTS[effect][1]
    return effect, strength


def parse_args():
    parser = argparse.ArgumentParser(description="Render local graphic effects onto an image or video.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, help="PNG, JPEG, WebP or MP4")
    parser.add_argument("--effect", type=effect_value, action="append", required=True,
                        help="name or name:strength. Repeat for stacking. " + ", ".join(EFFECTS))
    parser.add_argument("--density", type=int, help="change grid spacing or number of marks")
    parser.add_argument("--color", type=color_value, help="foreground or glow color")
    parser.add_argument("--background", type=color_value, help="background or paper color")
    parser.add_argument("--palette", type=palette_value, default="thermal",
                        help="thermal, cobalt, violet, acid, mono, or comma-separated colors")
    parser.add_argument("--seed", type=int, default=19)
    parser.add_argument("--size", type=int, help="maximum long edge in pixels")
    parser.add_argument("--fps", type=int, default=24, help="MP4 output frame rate")
    parser.add_argument("--animate", type=float, help="duration in seconds for a still-to-MP4 render")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.seed < 2**63:
        parser.error("--seed must be a nonnegative integer smaller than 2^63.")
    if args.density is not None and not 1 <= args.density <= 400:
        parser.error("--density must be from 1 to 400.")
    if args.size is not None and args.size < 2:
        parser.error("--size must be at least 2.")
    if not 1 <= args.fps <= 120:
        parser.error("--fps must be from 1 to 120.")
    if args.animate is not None and not (args.animate * args.fps >= 1 and args.animate < float("inf")):
        parser.error("--animate must be finite and long enough for at least one frame.")
    return parser, args


def main():
    parser, args = parse_args()
    source, target = args.input.resolve(), args.output.resolve()
    extension = target.suffix.lower()
    if not source.is_file():
        parser.error(f"Input file does not exist: {source}")
    if source == target:
        parser.error("Choose a different path for the output.")
    if target.exists() and not args.overwrite:
        parser.error(f"Output exists: {target}")
    if extension not in (".png", ".jpg", ".jpeg", ".webp", ".mp4"):
        parser.error("Choose a PNG, JPEG, WebP or MP4 output.")
    try:
        still = open_still(source)
        if still is None and args.animate is not None:
            parser.error("--animate expects a still image.")
        if still is not None and (extension == ".mp4") != (args.animate is not None):
            parser.error("Use --animate SECONDS with a still-to-MP4 export.")
        if still is None and extension != ".mp4":
            parser.error("Video or animated input needs an MP4 output.")
        settings = Settings(args.density, args.color, args.background, args.palette, args.seed, args.fps)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".visual-effects-", dir=target.parent) as folder:
            temp = Path(folder) / target.name
            if extension == ".mp4":
                render_video(source, still, temp, args, settings)
            else:
                dims = fit(still.size, args.size)
                if dims != still.size:
                    still = still.resize(dims, Image.Resampling.LANCZOS)
                output = render(still, settings, args.effect)
                options = {"quality": 95} if extension != ".png" else {}
                output.save(temp, **options)
            if args.overwrite:
                temp.replace(target)
            else:
                os.link(temp, target)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Render failed: {error}\n")
    print(target)


if __name__ == "__main__":
    main()
