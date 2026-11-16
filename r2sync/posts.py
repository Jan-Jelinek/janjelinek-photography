"""Reads the site's collections: which photos each post's rows use, and which are on disk."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
COLLECTIONS = REPO / "src" / "collections"

# Same rule as Gallery.astro: a name with an image (or video) extension is a file; without one it's a
# legacy Azure ID. Videos only go in text sections and asides.
PHOTO = re.compile(r"\.(jpe?g|png|webp|avif|tiff?|mp4|mov|m4v)$", re.IGNORECASE)
VIDEO = re.compile(r"\.(mp4|mov|m4v)$", re.IGNORECASE)
FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.DOTALL)
# Same rule as Gallery.astro for aside / text section items: no spaces + photo/video extension = file, else text.
SNAPSHOT = re.compile(r"^\S+\.(jpe?g|png|webp|avif|tiff?|mp4|mov|m4v)$", re.IGNORECASE)


@dataclass
class Collection:
    name: str  # folder name, e.g. "2025-peak-fog"; also the prefix in both buckets
    dir: Path
    referenced: list[str] = field(default_factory=list)  # photo file names in rows, then aside images
    local: dict[str, Path] = field(default_factory=dict)  # photo files on disk
    legacy: int = 0  # Azure IDs in rows ("1-01"), ignored by r2sync

    @property
    def unreferenced_local(self) -> list[str]:
        return sorted(n for n in self.local if n not in self.referenced)


def _rows_photos(rows) -> tuple[list[str], int]:
    """(photo file names in order, number of legacy Azure IDs)."""
    names: list[str] = []
    legacy = 0
    for row in rows or []:
        if not isinstance(row, list):
            continue  # text row
        for item in row:
            for name in item if isinstance(item, list) else [item]:
                name = str(name)
                if not PHOTO.search(name):
                    legacy += 1
                elif name not in names:
                    names.append(name)
    return names, legacy


TEXT_KEYS = ("text", "text-r", "text-f", "aside")


def _snapshot_images(rows) -> list[str]:
    """Image file names used in text sections and asides (rows like `- aside: [...]`), in order."""
    lists = [row[k] for row in rows or [] if isinstance(row, dict) for k in TEXT_KEYS if k in row]
    names: list[str] = []
    for items in lists:
        for item in items if isinstance(items, list) else [items]:
            item = str(item).strip()
            if SNAPSHOT.match(item) and item not in names:
                names.append(item)
    return names


def load_collection(folder: Path) -> Collection:
    post = folder / "post.mdx"
    match = FRONT_MATTER.match(post.read_text(encoding="utf-8"))
    data = yaml.safe_load(match.group(1)) if match else {}
    data = data or {}
    local = {
        p.name: p
        for p in sorted(folder.iterdir())
        if p.is_file() and PHOTO.search(p.name)
    }
    referenced, legacy = _rows_photos(data.get("rows"))
    # Snapshots (in asides and text sections) count as used too: push uploads them, unused doesn't list them.
    snapshots = _snapshot_images(data.get("rows"))
    referenced += [n for n in snapshots if n not in referenced]
    return Collection(name=folder.name, dir=folder, referenced=referenced, local=local, legacy=legacy)


def all_collections() -> dict[str, Collection]:
    return {
        f.name: load_collection(f)
        for f in sorted(COLLECTIONS.iterdir())
        if f.is_dir() and (f / "post.mdx").exists()
    }
