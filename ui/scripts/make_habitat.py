"""Build the habitat's artwork: specimens cut out of Merian's plates, and block-printed foliage.

Run from the repository root after changing anything here (the results are committed):

    python ui/scripts/make_habitat.py

Needs numpy, scipy and Pillow, which are only used here and never at runtime.

Specimens: the paper of each plate is estimated locally, then whatever differs from it is kept and
split into connected pieces, so a butterfly or a branch can sit directly on the page in both themes.

Foliage: leaves are cut like a woodblock (Morris & Co. printed wallpaper this way). Each blade is a
set of slices with the midrib and side veins left as gaps, so one flat colour still reads as an
engraved leaf. Every SVG is used as a CSS mask, so the themes choose the ink.
"""

# ruff: noqa: E501  (the long lines are SVG markup)

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1] / "public"
PLATES = ROOT / "plates"
OUT = ROOT / "habitat"


# ---- Specimens --------------------------------------------------------------------------------


def paper_of(rgb: np.ndarray) -> np.ndarray:
    """Estimate the bare paper under each pixel: ink is darker, so take a broad local maximum."""
    small = rgb[::6, ::6]
    out = np.empty_like(rgb)
    for channel in range(3):
        estimate = ndi.percentile_filter(small[..., channel], 85, size=41)
        estimate = ndi.gaussian_filter(estimate, 12)
        zoom = (rgb.shape[0] / small.shape[0], rgb.shape[1] / small.shape[1])
        out[..., channel] = ndi.zoom(estimate, zoom, order=1)[: rgb.shape[0], : rgb.shape[1]]
    return out


def matte(
    rgb: np.ndarray,
    threshold: float,
    min_area: int,
    keep_pale: tuple[int, int, int, int] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (solid mask, labelled pieces) for everything printed on the plate."""
    paper = paper_of(rgb)
    darker = np.clip(paper - rgb, 0, None).mean(axis=2)  # ink
    chroma = np.abs(
        (rgb - rgb.mean(axis=2, keepdims=True)) - (paper - paper.mean(axis=2, keepdims=True))
    ).max(axis=2)
    score = darker + 1.2 * chroma
    mask = score > threshold
    mask = ndi.binary_closing(mask, iterations=2)
    # Fill holes that are pale ink (wing scales), but leave the paper a branch encloses or a
    # caterpillar has chewed through: on a dark page those would show as white patches.
    holes, count = ndi.label(ndi.binary_fill_holes(mask) & ~mask)
    if count:
        index = np.arange(1, count + 1)
        sizes = ndi.sum_labels(np.ones_like(holes), holes, index=index)
        tint = ndi.mean(score, holes, index=index)
        mask |= np.isin(holes, index[(sizes < 90) | ((sizes < 1800) & (tint > threshold * 0.62))])
    if keep_pale:  # a white flower looks exactly like paper, so it is named by hand
        left, top, right, bottom = keep_pale
        mask[top:bottom, left:right] = ndi.binary_fill_holes(mask[top:bottom, left:right])
    mask = ndi.binary_opening(mask, iterations=1)
    labels, count = ndi.label(mask)
    areas = ndi.sum_labels(mask, labels, index=np.arange(1, count + 1))
    keep = np.isin(labels, np.flatnonzero(areas >= min_area) + 1)
    labels, _ = ndi.label(keep)
    return keep, labels


def cutout(rgb: np.ndarray, mask: np.ndarray) -> Image.Image:
    """Feather the matte inward, so no halo of paper survives on a dark page."""
    inner = ndi.binary_erosion(mask, iterations=1)
    alpha = np.clip(ndi.gaussian_filter(inner.astype(np.float32), 0.8) * 255, 0, 255).astype(
        np.uint8
    )
    return Image.fromarray(np.dstack([rgb.astype(np.uint8), alpha]), "RGBA")


def save(image: Image.Image, name: str, crop: bool = True, max_side: int = 1400) -> None:
    if crop:
        image = image.crop(image.getchannel("A").getbbox())
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    image.save(OUT / f"{name}.webp", quality=82, method=6)
    print(f"{name}.webp {image.size} {(OUT / f'{name}.webp').stat().st_size // 1024} KB")


def pieces_of(labels: np.ndarray) -> list[int]:
    """Labels of the printed pieces, largest first."""
    counts = np.bincount(labels.ravel())
    counts[0] = 0
    return [int(label) for label in np.argsort(-counts) if counts[label] > 0]


def specimens() -> None:
    vii = np.asarray(Image.open(PLATES / "plate-vii.webp").convert("RGB"), dtype=np.float32)
    mask, labels = matte(vii, threshold=26, min_area=1500, keep_pale=(225, 165, 320, 255))
    save(cutout(vii, mask), "plate-vii-cut", crop=False)
    branch, morpho = pieces_of(labels)[:2]
    save(cutout(vii, labels == branch), "branch")
    save(cutout(vii, labels == morpho), "morpho")

    viii = np.asarray(Image.open(PLATES / "plate-viii.webp").convert("RGB"), dtype=np.float32)
    _, labels = matte(viii, threshold=34, min_area=1500)
    found = pieces_of(labels)
    print("plate viii pieces", [(int((labels == f).sum())) for f in found[:6]])
    save(cutout(viii, labels == found[0]), "frangipani")
    save(cutout(viii, labels == found[1]), "moth")


# ---- Foliage ----------------------------------------------------------------------------------


def blade(x: float, y: float, angle: float, length: float, width: float, slices: int = 5) -> str:
    """One leaf as woodblock slices: both halves of the blade, with the veins left uncut."""
    cos, sin = math.cos(angle), math.sin(angle)

    def at(along: float, across: float) -> str:
        px = x + along * length * cos - across * width * sin
        py = y + along * length * sin + across * width * cos
        return f"{px:.1f} {py:.1f}"

    def half_width(t: float) -> float:
        return max(math.sin(math.pi * min(t, 1.0) ** 0.75), 0.04)

    parts = []
    gap = 0.018
    slant = 0.13  # side veins sweep towards the tip
    for side in (-1, 1):
        for i in range(slices):
            t0, t1 = i / slices + gap, (i + 1) / slices - gap
            mid = (t0 + t1) / 2 + slant
            a, b = at(t0, side * 0.05), at(t1, side * 0.05)
            c = at(min(t1 + slant, 1.0), side * half_width(t1 + slant))
            m = at(min(mid, 1.0), side * half_width(mid) * 1.03)
            d = at(min(t0 + slant, 1.0), side * half_width(t0 + slant))
            parts.append(f"M{a}L{b}L{c}L{m}L{d}Z")
    return "".join(parts)


def blossom(x: float, y: float, radius: float, rng: random.Random) -> str:
    start = rng.uniform(0, math.tau)
    return "".join(
        blade(x, y, start + i * math.tau / 5, radius, radius * 0.42, slices=2) for i in range(5)
    )


def wrapped(tile: int, x: float, y: float, reach: float) -> list[tuple[float, float]]:
    """Every position an element must be drawn at for the tile to repeat seamlessly."""
    return [
        (x + dx, y + dy)
        for dx in (-tile, 0, tile)
        for dy in (-tile, 0, tile)
        if -reach < x + dx < tile + reach and -reach < y + dy < tile + reach
    ]


def foliage(name: str, tile: int, vines: int, leaf: float, seed: int, stem_width: float) -> None:
    """A diagonal, interlacing repeat: each vine climbs one tile while waving, so the seam hides."""
    rng = random.Random(seed)
    stems, shapes = [], []
    for vine in range(vines):
        offset = tile * vine / vines + rng.uniform(-30, 30)
        waves, amplitude, phase = (
            rng.choice((2, 3)),
            tile * rng.uniform(0.05, 0.1),
            rng.uniform(0, math.tau),
        )
        points = [
            (
                offset + t / 90 * tile + amplitude * math.sin(math.tau * waves * t / 90 + phase),
                tile * t / 90 + amplitude * math.cos(math.tau * waves * t / 90 + phase),
            )
            for t in range(91)
        ]
        for dx in (-tile, 0, tile):
            for dy in (-tile, 0, tile):
                stems.append("M" + "L".join(f"{px + dx:.1f} {py + dy:.1f}" for px, py in points))

        count = max(5, int(tile / (leaf * 0.72)))
        for i in range(count):
            where = (i + rng.uniform(-0.2, 0.2)) / count
            index = int(where % 1 * 90)
            (px, py), (qx, qy) = points[index], points[index + 1]
            heading = math.atan2(qy - py, qx - px)
            side = 1 if i % 2 else -1
            angle = heading + side * rng.uniform(0.55, 1.15)
            size = leaf * rng.uniform(0.72, 1.2)
            for wx, wy in wrapped(tile, px % tile, py % tile, size * 1.3):
                if i % 9 == 4:
                    shapes.append(blossom(wx, wy, size * 0.42, random.Random(vine * 100 + i)))
                else:
                    shapes.append(blade(wx, wy, angle, size, size * 0.27))
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tile}" height="{tile}" viewBox="0 0 {tile} {tile}">'
        f'<path fill="none" stroke="#000" stroke-width="{stem_width}" stroke-linecap="round" d="{"".join(stems)}"/>'
        f'<path d="{"".join(shapes)}"/></svg>'
    )
    (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
    print(f"{name}.svg {len(svg) // 1024} KB")


def forest_floor(width: int = 1600, height: int = 240, seed: int = 11) -> None:
    """The floor the footer stands in: grasses and ferns, repeating across the page."""
    rng = random.Random(seed)
    grass, ferns = [], []
    for _ in range(170):
        x, tall = rng.uniform(0, width), rng.uniform(0.25, 0.8) * height
        lean, base = rng.uniform(-0.3, 0.3) * tall, rng.uniform(2.5, 6)
        for wx in (x - width, x, x + width):
            if -120 < wx < width + 120:
                grass.append(
                    f"M{wx - base:.1f} {height}"
                    f"Q{wx - base + lean * 0.3:.1f} {height - tall * 0.55:.1f} {wx + lean:.1f} {height - tall:.1f}"
                    f"Q{wx + base + lean * 0.3:.1f} {height - tall * 0.5:.1f} {wx + base:.1f} {height}Z"
                )
    for _ in range(16):
        x, reach = rng.uniform(0, width), rng.uniform(0.55, 0.95) * height
        start, bend = -math.pi / 2 + rng.uniform(-0.55, 0.55), rng.uniform(-0.05, 0.05)
        for wx in (x - width, x, x + width):
            if not -240 < wx < width + 240:
                continue
            px, py, heading = wx, float(height), start
            steps = 14
            for i in range(steps):
                nx, ny = (
                    px + math.cos(heading) * reach / steps,
                    py + math.sin(heading) * reach / steps,
                )
                grass.append(f"M{px - 1.2:.1f} {py:.1f}L{nx:.1f} {ny:.1f}L{px + 1.2:.1f} {py:.1f}Z")
                size = (1 - i / steps) * reach * 0.3 + 5
                if i >= 2:
                    ferns.append(blade(nx, ny, heading - 1.15, size, size * 0.2, slices=2))
                    ferns.append(blade(nx, ny, heading + 1.15, size, size * 0.2, slices=2))
                px, py, heading = nx, ny, heading + bend
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<path d="{"".join(grass)}{"".join(ferns)}"/></svg>'
    )
    (OUT / "floor.svg").write_text(svg, encoding="utf-8")
    print(f"floor.svg {len(svg) // 1024} KB")


def grain(size: int = 256, seed: int = 5) -> None:
    """Rag-paper fibre: a small transparent noise tile, cheaper than a live SVG filter."""
    noise = np.random.default_rng(seed).normal(size=(size, size))
    fibre = ndi.gaussian_filter(noise, (0.6, 1.4), mode="wrap")
    fibre = (fibre - fibre.min()) / (fibre.max() - fibre.min())
    alpha = np.clip((fibre - 0.5) * 2, 0, 1) ** 1.4 * 46
    rgba = np.dstack([np.full((size, size, 3), 70, np.uint8), alpha.astype(np.uint8)])
    Image.fromarray(rgba, "RGBA").save(OUT / "grain.webp", quality=60, method=6)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    specimens()
    foliage("foliage-back", tile=900, vines=3, leaf=150, seed=3, stem_width=3.5)
    foliage("foliage-front", tile=620, vines=2, leaf=74, seed=8, stem_width=2)
    forest_floor()
    grain()
