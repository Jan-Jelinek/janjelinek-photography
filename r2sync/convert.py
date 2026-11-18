"""Turns one original into the files the site serves: AVIF + WebP at a few sizes, a wallpaper JPEG,
a tiny blurred preview, and camera info. Videos: a 1080p MP4 plus a poster made the same way."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import ExifTags, Image, ImageCms, ImageOps

# Long edge of each size made, in px (no upscaling: sizes above the original are skipped).
EDGES = [720, 1200, 1800, 2400]
AVIF_QUALITY = 60  # 0–100; AVIF holds up well at lower numbers than JPEG
AVIF_SPEED = 6  # 0 (slowest, smallest) – 10 (fastest)
WEBP_QUALITY = 82
WEBP_METHOD = 6  # 0 (fast) – 6 (smallest)
LQIP_EDGE = 24  # blurred placeholder, px

# Wallpaper JPEG behind the lightbox's download button. Fills 1440p/1600p screens; kept below 4K on purpose.
DOWNLOAD_EDGE = 2592
DOWNLOAD_QUALITY = 90
ARTIST = "Jan Jelinek"  # the only metadata written into the JPEG

Image.MAX_IMAGE_PIXELS = 200_000_000  # allow big originals (default warns past ~90 MP)


@dataclass
class Variant:
    edge: int
    w: int
    h: int
    avif: bytes
    webp: bytes


@dataclass
class Download:
    w: int
    h: int
    jpg: bytes


@dataclass
class Converted:
    width: int
    height: int
    variants: list[Variant]
    download: Download
    lqip: str
    exif: dict


def _clean(value) -> str:
    return str(value).replace("\x00", "").strip()


def exif_summary(im: Image.Image) -> dict:
    exif = im.getexif()
    ifd = exif.get_ifd(ExifTags.IFD.Exif)
    out: dict = {}
    if exif.get(272):
        out["camera"] = _clean(exif[272])
    if ifd.get(42036):
        out["lens"] = _clean(ifd[42036])
    if ifd.get(37386):
        out["focal"] = f"{round(float(ifd[37386]))}mm"
    if ifd.get(33437):
        out["aperture"] = f"f/{round(float(ifd[33437]), 1):g}"
    if ifd.get(33434):
        t = float(ifd[33434])
        out["shutter"] = f"{t:g}s" if t >= 1 else f"1/{round(1 / t)}s"
    iso = ifd.get(34855)
    if iso:
        out["iso"] = int(iso[0] if isinstance(iso, tuple) else iso)
    if ifd.get(36867):
        date, _, time = _clean(ifd[36867]).partition(" ")
        out["taken"] = f"{date.replace(':', '-')}T{time}"
    return out


def _to_srgb(im: Image.Image) -> Image.Image:
    icc = im.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(BytesIO(icc))
            if "srgb" not in ImageCms.getProfileDescription(src).lower():
                return ImageCms.profileToProfile(im, src, ImageCms.createProfile("sRGB"), outputMode="RGB")
        except (ImageCms.PyCMSError, OSError):
            pass  # unreadable profile: treat as sRGB
    return im.convert("RGB")


def edges_for(long_edge: int) -> list[int]:
    """[720, 1200, 1800, 2400], capped at the original's size (which becomes the largest)."""
    return [e for e in EDGES[:-1] if e < long_edge] + [min(long_edge, EDGES[-1])]


SRGB_ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _resize(im: Image.Image, edge: int) -> Image.Image:
    """Scale so the long edge is `edge` px (never up)."""
    width, height = im.size
    scale = edge / max(width, height)
    if scale >= 1:
        return im
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return im.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0)


def _download_jpg(im: Image.Image) -> Download:
    resized = _resize(im, DOWNLOAD_EDGE)
    meta = Image.Exif()
    meta[315] = ARTIST  # Artist
    meta[33432] = f"Copyright {ARTIST}"  # EXIF text is ASCII only, so no ©
    buf = BytesIO()
    resized.save(
        buf, "JPEG", quality=DOWNLOAD_QUALITY, subsampling=0, progressive=True, optimize=True,
        icc_profile=SRGB_ICC, exif=meta.tobytes(),  # no camera data / GPS
    )
    return Download(resized.width, resized.height, buf.getvalue())


def convert(data: bytes) -> Converted:
    im = Image.open(BytesIO(data))
    exif = exif_summary(im)
    im = _to_srgb(ImageOps.exif_transpose(im))
    width, height = im.size
    long_edge = max(width, height)

    variants = []
    for edge in edges_for(long_edge):
        resized = _resize(im, edge)
        size = resized.size
        avif, webp = BytesIO(), BytesIO()
        # No exif= / icc_profile= passed, so camera data (incl. GPS) is left out of the files.
        resized.save(avif, "AVIF", quality=AVIF_QUALITY, speed=AVIF_SPEED)
        resized.save(webp, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
        variants.append(Variant(edge, size[0], size[1], avif.getvalue(), webp.getvalue()))

    tiny = im.copy()
    tiny.thumbnail((LQIP_EDGE, LQIP_EDGE), Image.Resampling.LANCZOS)
    buf = BytesIO()
    tiny.save(buf, "WEBP", quality=40)
    lqip = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()

    return Converted(width, height, variants, _download_jpg(im), lqip, exif)


# --- Videos (text sections and asides): a 1080p H.264 MP4 plus a poster image. Needs ffmpeg. ---

VIDEO_SHORT_EDGE = 1080  # "1080p": the short edge, so portrait phone clips come out 1080×1920
VIDEO_CRF = 22  # x264 quality, lower = better/bigger (18 ≈ visually lossless, 23 = default)
VIDEO_PRESET = "slow"
# Cap for busy footage (water, foliage), where CRF alone can go past the phone's own bitrate.
VIDEO_MAXRATE, VIDEO_BUFSIZE = "6M", "12M"
AUDIO_BITRATE = "160k"
HDR_TRANSFERS = {"arib-std-b67", "smpte2084"}  # HLG / PQ (phone HDR video)


@dataclass
class ConvertedVideo:
    mp4: bytes
    w: int
    h: int
    duration: float
    poster: Converted  # first frame, made like a photo: variants + lqip (its download isn't used)


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} not found: install ffmpeg (winget install ffmpeg) and open a new terminal")
    return path


def _probe(path: Path) -> dict:
    out = subprocess.run(
        [_tool("ffprobe"), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,color_transfer:format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    data = json.loads(out)
    stream = (data.get("streams") or [{}])[0]
    return {**stream, "duration": float(data.get("format", {}).get("duration") or 0)}


def convert_video(data: bytes, suffix: str = ".mp4") -> ConvertedVideo:
    with tempfile.TemporaryDirectory() as tmp:
        src, out, poster = Path(tmp) / f"in{suffix}", Path(tmp) / "out.mp4", Path(tmp) / "poster.png"
        src.write_bytes(data)
        info = _probe(src)

        # ffmpeg turns phone clips upright on its own (rotation metadata), before these filters.
        filters = []
        if info.get("color_transfer") in HDR_TRANSFERS:
            filters.append(
                "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv"
            )
        e = VIDEO_SHORT_EDGE
        # Short edge to at most 1080 (never up); -2 keeps the other side even, which H.264 needs.
        filters.append(f"scale='if(lte(iw,ih),min({e},iw),-2)':'if(lte(iw,ih),-2,min({e},ih))'")
        filters.append("format=yuv420p")

        subprocess.run(
            [_tool("ffmpeg"), "-v", "error", "-y", "-i", str(src),
             "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(filters),
             "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF), "-profile:v", "high",
             "-maxrate", VIDEO_MAXRATE, "-bufsize", VIDEO_BUFSIZE,
             "-c:a", "aac", "-b:a", AUDIO_BITRATE,
             "-map_metadata", "-1",  # no GPS / phone info in the file
             "-movflags", "+faststart",  # can start playing before it's fully downloaded
             str(out)],
            check=True, capture_output=True, text=True,
        )
        # Poster from the finished file, so it's upright and has the same colors.
        subprocess.run(
            [_tool("ffmpeg"), "-v", "error", "-y", "-i", str(out), "-frames:v", "1", str(poster)],
            check=True, capture_output=True, text=True,
        )
        done = _probe(out)
        return ConvertedVideo(out.read_bytes(), int(done["width"]), int(done["height"]),
                              round(done["duration"], 2), convert(poster.read_bytes()))
