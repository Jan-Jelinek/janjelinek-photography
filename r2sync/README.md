# r2sync

Moves photos from your PC → the **master** bucket (originals, private) → the **public** bucket
(resized AVIF + WebP that the site serves from `i.jelinekphotos.com`, plus one wallpaper JPEG per photo
for the lightbox's download button).

## Setup (once)

```
py -m pip install -r r2sync/requirements.txt
```

`.env` in the repo root (gitignored):

```bash
R2_ACCOUNT_ID=...          # Cloudflare → R2 → Account details
R2_ACCESS_KEY_ID=...       # R2 → Manage API tokens → Object Read & Write,
R2_SECRET_ACCESS_KEY=...   #   limited to both buckets
R2_MASTER_BUCKET=jelinekphotos-master
R2_PUBLIC_BUCKET=jelinekphotos-public
```

The public bucket needs the custom domain connected in its R2 settings. Until then you can point the
site at the bucket's `r2.dev` URL with `PUBLIC_IMAGE_BASE=https://pub-xxxx.r2.dev` (see `src/lib/images.ts`).

## Daily workflow

1. Drop exports into the collection folder, e.g. `src/collections/2025-peak-fog/`.
2. Put the file names in the post's `rows` and tinker with `npm run dev`.
   Photos coming from your PC have a badge (only in dev):
   - **not uploaded**: only on your PC
   - **edited**: uploaded, but your local copy is different
3. `py r2sync push 2025-peak-fog`: uploads the photos used in rows, converts them, and moves the
   local copies to the Recycle Bin. The badges disappear.
   Only photos in rows are uploaded; leftovers in the folder are skipped.
4. `py r2sync unused 2025-peak-fog` lists those leftovers; delete the ones you don't need.
5. Commit `post.mdx` and `photos.json`, push.

To re-edit a photo, drop the new version in the folder under the same name and push again.

## Commands

| Command | What it does |
|---|---|
| `py r2sync push <collection>` | Local → master → public, then removes the local copies. `--keep` keeps them; `--dry-run` only shows the plan. Photos in the folder but not in rows are left alone. |
| `py r2sync run` | Makes public match master. Use after changing the master bucket by hand in the dashboard. `--dry-run` shows the plan; `--yes` skips the "delete more than 10 files?" question. |
| `py r2sync unused [collection]` | Local only, no `.env` needed. Lists photos in collection folders that aren't in rows (leftovers from tinkering) so you can delete them. Deletes nothing. |
| `py r2sync check` | Changes nothing. Reports photos not pushed, local edits, photos in rows that are missing, masters not converted, unused files. Exits with an error if the deploy would break. |

## How it fits together

- `src/collections/<collection>/photos.json` lists what's uploaded (sizes, camera info, file names).
  The site only reads this; it's committed. Don't edit it by hand.
- The gallery picks each photo in this order: your local file (unless identical to the upload) →
  `photos.json` → build error. Local photos are gitignored, so the deployed site only ever uses
  uploaded photos, and a photo you forgot to push fails the deploy instead of showing broken.
- Public file names include a short fingerprint of the photo (`DSCF0669.a3f9c2e1-1200.avif`), so
  browsers can cache them forever and a re-edited photo gets a new name. Old versions are deleted
  by `push` and `run`.
- Safety: `run` refuses to start if master is empty, never drops a photo that's still in rows, and
  asks before deleting more than 10 public files. A photo's `photos.json` entry is only written after
  all its files uploaded, so if anything fails, just run the command again.

## Testing without R2

`R2SYNC_FAKE=.r2sync-fake py r2sync ...` uses two local folders instead of the buckets
(`.r2sync-fake/` is gitignored). Delete any `photos.json` it writes before committing; they point at
files that aren't really uploaded.

## Settings

Sizes and quality are at the top of `convert.py` (long edges 720/1200/1800/2400, AVIF q60, WebP q82;
download JPEG `DOWNLOAD_EDGE` 2592 at q90, kept below 4K so it's no substitute for a print). The JPEG is
saved as `jan-jelinek-<collection>-<file>.jpg` and contains no camera data, only Artist/Copyright.
After changing them, delete the `photos.json` files and run `py r2sync run` to rebuild public from master.
