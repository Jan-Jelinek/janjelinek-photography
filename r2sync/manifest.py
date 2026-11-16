"""photos.json: what's been uploaded for a collection. The site reads this; it's committed to git.

{
  "DSCF0669.JPG": {
    "sha256": "...",           # of the original, to spot edited local copies
    "etag": "...",             # of the original in master, to spot changes made in the dashboard
    "version": "a3f9c2e1",     # first 8 of sha256; part of every public file name
    "width": 7728, "height": 5152,
    "variants": [{"edge": 720, "w": 720, "h": 480, "avif": "<key>", "webp": "<key>"}, ...],
    "download": {"key": "<key>.jpg", "w": 2592, "h": 1728},  # wallpaper JPEG for the download button
    "lqip": "data:image/webp;base64,...",
    "exif": {"camera": "X-T5", "shutter": "1/250s", ...}
  },
  "PXL_0001.mp4": {              # a video: same fields, but variants/lqip are its poster (first frame),
    ...,                         # width/height are the video's, and there's no download
    "video": {"key": "<key>.mp4", "w": 1080, "h": 1920, "duration": 12.6}
  }
}
"""

from __future__ import annotations

import json
import os
from pathlib import Path

FILE = "photos.json"


def load(folder: Path) -> dict[str, dict]:
    path = folder / FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(folder: Path, data: dict[str, dict]) -> None:
    path = folder / FILE
    if not data:
        path.unlink(missing_ok=True)
        return
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # all or nothing: never a half-written file


def public_keys(entry: dict) -> list[str]:
    keys = [v[fmt] for v in entry["variants"] for fmt in ("avif", "webp")]
    if "download" in entry:
        keys.append(entry["download"]["key"])
    if "video" in entry:
        keys.append(entry["video"]["key"])
    return keys
