// Turns a photo name from a post (rows, commentary, feature) into the URLs and sizes the site needs.
// Shared by the gallery and the home page hero.
import { createHash } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { getImage } from "astro:assets";
import exifr from "exifr";
import type { ImageMetadata } from "astro";
import { publicUrl } from "./images";

/** Long edges made for every photo (r2sync uses the same sizes). */
export const WIDTHS = [720, 1200, 1800, 2400];

export interface Photo {
  key: string;
  ratio: number;
  width: number;
  height: number;
  src: string;
  srcset: string;
  /** Same sizes as srcset, as AVIF (uploaded photos only). */
  avifSrcset?: string;
  /** Tiny blurred preview shown while the photo loads. */
  lqip?: string;
  /** Dev only: photo is coming from your PC, not R2. */
  badge?: "not uploaded" | "edited";
  /** Wallpaper JPEG for the lightbox's download button (uploaded photos; local ones in dev). */
  download?: string;
  /** Camera settings, for auto captions (uploaded and local photos; not Azure). */
  exposure?: Exposure;
  /** Number of the aside about this photo, shown as a badge (gallery only). */
  aside?: string;
  href: string;
  lightboxSrcset: string;
  lightboxWidth: number;
  lightboxHeight: number;
}

/** Formatted like r2sync stores them: "f/4", "1/300s", 125. */
export interface Exposure {
  aperture?: string;
  shutter?: string;
  iso?: number;
}

/** "f/4 · 1/300s · ISO 125" (missing parts left out), or undefined if there's nothing to show. */
export function exposureText(e?: Exposure): string | undefined {
  if (!e) return undefined;
  const parts = [e.aperture, e.shutter, e.iso && `ISO ${e.iso}`].filter(Boolean);
  return parts.length ? parts.join(" · ") : undefined;
}

/** Which collection a photo name belongs to. */
export interface PhotoSource {
  /** Folder holding the post, e.g. "src/collections/2025-peak-fog". */
  dir: string;
  slug: string;
}

// --- Uploaded: in the collection's photos.json, written by `py r2sync`. ---
interface ManifestEntry {
  sha256: string;
  width: number;
  height: number;
  lqip?: string;
  variants: { edge: number; w: number; h: number; avif: string; webp: string }[];
  download?: { key: string; w: number; h: number };
  exif?: Exposure & Record<string, unknown>;
}
const manifests = import.meta.glob<Record<string, ManifestEntry>>("/src/collections/*/photos.json", {
  eager: true,
  import: "default",
});

function r2Photo(file: string, entry: ManifestEntry): Photo {
  const v = entry.variants;
  const fallback = v[Math.min(1, v.length - 1)];
  const largest = v[v.length - 1];
  const webpSrcset = v.map((x) => `${publicUrl(x.webp)} ${x.w}w`).join(", ");
  return {
    key: file,
    ratio: entry.width / entry.height,
    width: fallback.w,
    height: fallback.h,
    src: publicUrl(fallback.webp),
    srcset: webpSrcset,
    avifSrcset: v.map((x) => `${publicUrl(x.avif)} ${x.w}w`).join(", "),
    lqip: entry.lqip,
    download: entry.download && publicUrl(entry.download.key),
    exposure: entry.exif && { aperture: entry.exif.aperture, shutter: entry.exif.shutter, iso: entry.exif.iso },
    href: publicUrl(largest.webp),
    // The lightbox shows one format, so WebP (works everywhere).
    lightboxSrcset: webpSrcset,
    lightboxWidth: largest.w,
    lightboxHeight: largest.h,
  };
}

// --- Azure: "1-01", or "1-01v" for portrait. ---
// Each photo exists as <id>-720.webp and <id>-1200/1800/2400.jpg (number = long edge).
function azurePhoto(raw: string, slug: string): Photo {
  const base = `https://stjjp.blob.core.windows.net/images/${slug}/`;
  const portrait = raw.endsWith("v");
  const id = portrait ? raw.slice(0, -1) : raw;
  const widthOf = (edge: number) => (portrait ? Math.round((edge * 2) / 3) : edge);
  const url = (edge: number) => `${base}${id}-${edge}.${edge === 720 ? "webp" : "jpg"}`;
  return {
    key: id,
    ratio: portrait ? 2 / 3 : 3 / 2,
    width: widthOf(1200),
    height: portrait ? 1200 : 800,
    src: url(1200),
    srcset: WIDTHS.map((e) => `${url(e)} ${widthOf(e)}w`).join(", "),
    href: url(2400),
    lightboxSrcset: WIDTHS.slice(1).map((e) => `${url(e)} ${widthOf(e)}w`).join(", "),
    lightboxWidth: widthOf(2400),
    lightboxHeight: portrait ? 2400 : 1600,
  };
}

// --- Local preview: "DSCF0669.JPG", a file next to post.mdx. Resized at build time. ---
const LOCAL = /\.(jpe?g|png|webp|avif|tiff?)$/i;
const localFiles = import.meta.glob<{ default: ImageMetadata }>(
  "/src/collections/**/*.{jpg,jpeg,JPG,JPEG,png,PNG,webp,WEBP,avif,AVIF,tif,tiff,TIF,TIFF}",
  { eager: true },
);

// Same format as r2sync/convert.py exif_summary(), so local and uploaded captions match.
const trimNum = (n: number) => String(Number(n.toPrecision(12)));
async function readExposure(path: string): Promise<Exposure | undefined> {
  const tags = await exifr.parse(path, ["FNumber", "ExposureTime", "ISO"]).catch(() => undefined);
  if (!tags) return undefined;
  const { FNumber: f, ExposureTime: t, ISO: iso } = tags as { FNumber?: number; ExposureTime?: number; ISO?: number };
  return {
    aperture: f ? `f/${trimNum(Math.round(f * 10) / 10)}` : undefined,
    shutter: t ? (t >= 1 ? `${trimNum(t)}s` : `1/${Math.round(1 / t)}s`) : undefined,
    iso: iso ? Math.trunc(Array.isArray(iso) ? iso[0] : iso) : undefined,
  };
}

// Camera settings of a local file, remembered until the file changes.
const exposureCache = new Map<string, { stamp: string; exposure?: Exposure }>();
async function exposureOf(path: string): Promise<Exposure | undefined> {
  const { mtimeMs, size } = statSync(path);
  const stamp = `${mtimeMs}:${size}`;
  const hit = exposureCache.get(path);
  if (hit?.stamp === stamp) return hit.exposure;
  const exposure = await readExposure(path);
  exposureCache.set(path, { stamp, exposure });
  return exposure;
}

async function localPhoto(file: string, path: string, meta: ImageMetadata, badge: Photo["badge"]): Promise<Photo> {
  const longEdge = Math.max(meta.width, meta.height);
  const widths = WIDTHS.filter((e) => e <= longEdge).map((e) => Math.round((e / longEdge) * meta.width));
  if (widths.length === 0) widths.push(meta.width);

  const heightOf = (w: number) => Math.round((w / meta.width) * meta.height);
  const fallbackWidth = widths[Math.min(1, widths.length - 1)];
  const fullWidth = widths[widths.length - 1];
  // Without `src` override, getImage's default src is a full-resolution copy we don't want.
  const display = await getImage({ src: meta, widths, format: "webp" });
  const fallback = await getImage({ src: meta, width: fallbackWidth, format: "webp" });
  const full = await getImage({ src: meta, width: fullWidth, format: "webp" });
  return {
    key: file,
    ratio: meta.width / meta.height,
    width: fallbackWidth,
    height: heightOf(fallbackWidth),
    src: fallback.src,
    srcset: display.srcSet.attribute,
    href: full.src,
    lightboxSrcset: display.srcSet.attribute,
    lightboxWidth: fullWidth,
    lightboxHeight: heightOf(fullWidth),
    badge: import.meta.env.DEV ? badge : undefined,
    // Dev only, to try the button: in a build this would copy the full original into dist.
    download: import.meta.env.DEV ? meta.src : undefined,
    exposure: await exposureOf(path),
  };
}

// sha256 of a local file, remembered until the file changes (dev re-renders on every reload).
const hashCache = new Map<string, { stamp: string; sha: string }>();
function sha256Of(path: string): string {
  const { mtimeMs, size } = statSync(path);
  const stamp = `${mtimeMs}:${size}`;
  const hit = hashCache.get(path);
  if (hit?.stamp === stamp) return hit.sha;
  const sha = createHash("sha256").update(readFileSync(path)).digest("hex");
  hashCache.set(path, { stamp, sha });
  return sha;
}

/*
 * A name with an image extension is a file: your local copy wins (so you can tinker),
 * unless it's identical to the upload; otherwise the uploaded version from photos.json.
 * Local photos are gitignored, so the deployed site only ever uses uploaded ones.
 * A name without an extension is a legacy Azure ID.
 */
export async function loadPhoto(raw: string, { dir, slug }: PhotoSource): Promise<Photo> {
  if (!LOCAL.test(raw)) return azurePhoto(raw, slug);
  const local = localFiles[`/${dir}/${raw}`]?.default;
  const entry = (manifests[`/${dir}/photos.json`] ?? {})[raw];
  if (local && !(entry && sha256Of(resolve(dir, raw)) === entry.sha256)) {
    return localPhoto(raw, resolve(dir, raw), local, entry ? "edited" : "not uploaded");
  }
  if (entry) return r2Photo(raw, entry);
  const folder = dir.split("/").pop();
  throw new Error(
    `"${raw}" is used in ${folder}/post.mdx but isn't in ${dir}/ or uploaded. ` +
      `If it's on your PC, run: py r2sync push ${folder}`,
  );
}
