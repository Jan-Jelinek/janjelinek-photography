"""Reads the site's collections: which photos each post's rows use, and which are on disk."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
COLLECTIONS = REPO / "src" / "collections"

# Same rule as Gallery.astro: a name with an image extension is a file; without one it's a legacy Azure ID.
PHOTO = re.compile(r"\.(jpe?g|png|webp|avif|tiff?)$", re.IGNORECASE)
FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.DOTALL)
# Same rule as Gallery.astro for `commentary` items: no spaces + photo extension = image, else text.
ASIDE_IMAGE = re.compile(r"^\S+\.(jpe?g|png|webp|avif|tiff?)$", re.IGNORECASE)


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


def _aside_images(commentary) -> list[str]:
    """Image file names used in `commentary` asides, in order."""
    names: list[str] = []
    for items in (commentary or {}).values():
        for item in items if isinstance(items, list) else [items]:
            item = str(item).strip()
            if ASIDE_IMAGE.match(item) and item not in names:
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
    # Aside images count as used too: push uploads them, unused doesn't list them.
    referenced += [n for n in _aside_images(data.get("commentary")) if n not in referenced]
    return Collection(name=folder.name, dir=folder, referenced=referenced, local=local, legacy=legacy)


def all_collections() -> dict[str, Collection]:
    return {
        f.name: load_collection(f)
        for f in sorted(COLLECTIONS.iterdir())
        if f.is_dir() and (f / "post.mdx").exists()
    }
