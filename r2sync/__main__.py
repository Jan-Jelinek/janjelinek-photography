"""r2sync: local photos -> master bucket (originals) -> public bucket (what the site serves).

    py r2sync push <collection> [--keep] [--dry-run]
    py r2sync run [--yes] [--dry-run]
    py r2sync check
    py r2sync unused [collection]

See r2sync/README.md.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

import manifest
import posts
from convert import convert
from store import Store, open_stores

CACHE_FOREVER = "public, max-age=31536000, immutable"  # safe: public file names change when the photo does
WORKERS = 4  # photos converted at once
CONFIRM_OVER = 10  # ask before deleting more public files than this


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def publish(coll: str, name: str, data: bytes, etag: str, public: Store) -> dict:
    """Convert one original, upload its files to public, and return its photos.json entry."""
    digest = sha256(data)
    version = digest[:8]
    stem = Path(name).stem
    converted = convert(data)
    variants = []
    for v in converted.variants:
        base = f"{coll}/{stem}.{version}-{v.edge}"
        public.put(f"{base}.avif", v.avif, CACHE_FOREVER)
        public.put(f"{base}.webp", v.webp, CACHE_FOREVER)
        variants.append({"edge": v.edge, "w": v.w, "h": v.h, "avif": f"{base}.avif", "webp": f"{base}.webp"})
    d = converted.download
    download_key = f"{coll}/{stem}.{version}-{max(d.w, d.h)}.jpg"
    public.put(download_key, d.jpg, CACHE_FOREVER, download_name=f"jan-jelinek-{coll}-{stem}.jpg".lower())
    return {
        "sha256": digest,
        "etag": etag,
        "version": version,
        "width": converted.width,
        "height": converted.height,
        "variants": variants,
        "download": {"key": download_key, "w": d.w, "h": d.h},
        "lqip": converted.lqip,
        "exif": converted.exif,
    }


def parallel(jobs: dict):
    """Run {name: fn} a few at a time; yield (name, result, error) as each one finishes."""
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(fn): name for name, fn in jobs.items()}
        for future in as_completed(futures):
            try:
                yield futures[future], future.result(), None
            except Exception as error:  # noqa: BLE001 - report and carry on with the rest
                yield futures[future], None, error


def confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        print("  (no terminal to ask in; pass --yes)")
        return False
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:  # nothing to read an answer from
        print("\n  (no answer; pass --yes)")
        return False


def delete_public(public: Store, keys: set[str], *, yes: bool, dry: bool) -> None:
    if not keys:
        return
    print(f"\n{len(keys)} public file(s) no photo uses{' (would delete)' if dry else ''}:")
    for key in sorted(keys)[:20]:
        print(f"  - {key}")
    if len(keys) > 20:
        print(f"  ... and {len(keys) - 20} more")
    if dry:
        return
    if len(keys) > CONFIRM_OVER and not confirm(f"Delete these {len(keys)} files?", yes):
        print("  kept them")
        return
    public.delete(sorted(keys))
    print(f"  deleted {len(keys)}")


def all_public_keys(entries: dict[str, dict]) -> set[str]:
    return {k for e in entries.values() for k in manifest.public_keys(e)}


# --- push -----------------------------------------------------------------------------------------


def cmd_push(args) -> int:
    colls = posts.all_collections()
    coll = colls.get(args.collection)
    if not coll:
        sys.exit(f"No collection {args.collection!r}. Collections: {', '.join(colls)}")
    master, public = open_stores(posts.REPO)
    entries = manifest.load(coll.dir)
    in_master = master.list(f"{coll.name}/")

    upload: dict[str, Path] = {}
    already: list[str] = []
    print(coll.name)
    for name in coll.referenced:
        path = coll.local.get(name)
        if not path:
            continue
        entry = entries.get(name)
        if entry and entry["sha256"] == sha256(path.read_bytes()) and in_master.get(f"{coll.name}/{name}") == entry["etag"]:
            already.append(name)
            print(f"  ok       {name}  already uploaded")
        else:
            upload[name] = path
            print(f"  upload   {name}  {'edited' if entry else 'new'}")
    if not upload and not already:
        print("  no photos from rows on disk, nothing to push")
    if coll.unreferenced_local:
        print(f"  not in rows, left alone: {', '.join(coll.unreferenced_local)}")
    if args.dry_run:
        return 0

    def job(name: str, path: Path):
        def run():
            data = path.read_bytes()
            etag = master.put(f"{coll.name}/{name}", data)
            return publish(coll.name, name, data, etag, public)
        return run

    done = list(already)  # safe to remove locally
    uploaded = 0
    failed = []
    started = time.monotonic()
    for name, entry, error in parallel({n: job(n, p) for n, p in upload.items()}):
        if error:
            failed.append(name)
            print(f"  FAILED   {name}: {error}")
            continue
        entries[name] = entry
        manifest.save(coll.dir, entries)  # after every photo, so a crash loses nothing
        done.append(name)
        uploaded += 1
        print(f"  done     {name}  ({len(manifest.public_keys(entry))} files, {time.monotonic() - started:.0f}s)")

    # Old versions of re-edited photos.
    delete_public(public, set(public.list(f"{coll.name}/")) - all_public_keys(entries), yes=False, dry=False)

    if done and not args.keep:
        from send2trash import send2trash

        for name in done:
            send2trash(str(coll.local[name]))
        print(f"\nMoved {len(done)} local cop{'y' if len(done) == 1 else 'ies'} to the Recycle Bin; the site now uses the uploaded versions.")
    if uploaded:
        print(f"Next: commit {coll.name}/post.mdx and {coll.name}/{manifest.FILE}.")
    return 1 if failed else 0


# --- run ------------------------------------------------------------------------------------------


def cmd_run(args) -> int:
    colls = posts.all_collections()
    master, public = open_stores(posts.REPO)
    masters = master.list()
    if not masters:
        sys.exit("The master bucket is empty, so every public file would be deleted. Refusing to run.")
    pub = set(public.list())

    by_coll: dict[str, dict[str, str]] = {}
    for key, etag in masters.items():
        coll, _, name = key.partition("/")
        if not name or "/" in name:
            print(f"! skipping master/{key} (expected <collection>/<file>)")
            continue
        by_coll.setdefault(coll, {})[name] = etag
    for coll in sorted(set(by_coll) - set(colls)):
        print(f"! master/{coll}/ has no matching folder in src/collections, skipped")

    manifests = {name: manifest.load(c.dir) for name, c in colls.items()}
    todo: dict[str, tuple[str, str, str]] = {}  # job id -> (collection, file, etag)
    survivors: set[str] = set()  # public keys that stay no matter what
    changed = False
    for name, coll in colls.items():
        entries = manifests[name]
        files = by_coll.get(name, {})
        lines = []
        for file, etag in sorted(files.items()):
            if file not in entries or entries[file]["etag"] != etag:
                todo[f"{name}/{file}"] = (name, file, etag)
                lines.append(f"  convert  {file}  {'changed' if file in entries else 'new'}")
        drop = set()
        for file in sorted(set(entries) - set(files)):
            if file in coll.referenced:
                lines.append(f"  KEPT     {file}  deleted from master but still in rows; remove it from rows first")
            else:
                lines.append(f"  drop     {file}  deleted from master")
                drop.add(file)
        for file, entry in entries.items():
            if file not in drop and f"{name}/{file}" not in todo:
                survivors |= set(manifest.public_keys(entry))
        if drop and not args.dry_run:
            for file in drop:
                del entries[file]
            changed = True
        if lines:
            print(name, *lines, sep="\n")

    if args.dry_run:
        delete_public(public, pub - survivors, yes=False, dry=True)
        if not todo and not pub - survivors:
            print("Everything in sync.")
        return 0

    failed = 0
    started = time.monotonic()

    def job(coll: str, file: str, etag: str):
        return lambda: publish(coll, file, master.get(f"{coll}/{file}"), etag, public)

    for job_id, entry, error in parallel({j: job(*t) for j, t in todo.items()}):
        coll, file, _ = todo[job_id]
        if error:
            failed += 1
            print(f"  FAILED   {job_id}: {error}")
            continue
        manifests[coll][file] = entry
        manifest.save(colls[coll].dir, manifests[coll])
        print(f"  done     {job_id}  ({time.monotonic() - started:.0f}s)")
    if changed:
        for name, coll in colls.items():
            manifest.save(coll.dir, manifests[name])

    expected = set().union(*(all_public_keys(e) for e in manifests.values()))
    delete_public(public, pub - expected, yes=args.yes, dry=False)
    if not todo and not changed and not pub - expected:
        print("Everything in sync.")
    elif todo or changed:
        print("\nNext: commit the changed photos.json files.")
    return 1 if failed else 0


# --- check ----------------------------------------------------------------------------------------


def cmd_check(args) -> int:
    colls = posts.all_collections()
    master, public = open_stores(posts.REPO)
    masters, pub = master.list(), set(public.list())
    problems = 0
    expected: set[str] = set()

    for name, coll in colls.items():
        entries = manifest.load(coll.dir)
        expected |= all_public_keys(entries)
        files = {k.split("/", 1)[1]: e for k, e in masters.items() if k.startswith(f"{name}/")}
        lines: list[tuple[bool, str, str, str]] = []  # (problem, tag, file, note)

        for file in coll.referenced:
            local, entry = coll.local.get(file), entries.get(file)
            if entry and any(k not in pub for k in manifest.public_keys(entry)):
                lines.append((True, "PUBLIC GONE", file, "public files missing; run `py r2sync run`"))
            if local and not entry:
                lines.append((True, "NOT PUSHED", file, f"only on your PC; deploy fails until `py r2sync push {name}`"))
            elif local and entry:
                if sha256(local.read_bytes()) != entry["sha256"]:
                    lines.append((False, "edited", file, "local copy differs from the upload; push to replace it"))
                else:
                    lines.append((False, "local copy", file, "same as the upload; safe to delete"))
            elif not entry:
                if file in files:
                    lines.append((True, "NOT CONVERTED", file, "in master but not converted; run `py r2sync run`"))
                else:
                    lines.append((True, "MISSING", file, "not on your PC and not uploaded (typo?)"))

        for file, etag in sorted(files.items()):
            if file not in entries:
                if file not in coll.referenced:
                    lines.append((False, "not converted", file, "in master; `py r2sync run` converts it"))
            elif entries[file]["etag"] != etag:
                lines.append((False, "changed", file, "replaced in master; `py r2sync run` converts it"))
            if file not in coll.referenced:
                lines.append((False, "unused", file, "in master, not in rows"))
        for file in sorted(set(entries) - set(files)):
            lines.append((file in coll.referenced, "NO MASTER" if file in coll.referenced else "no master", file,
                          "deleted from master" + (" but still in rows" if file in coll.referenced else "")))
        for file in coll.unreferenced_local:
            lines.append((False, "candidate", file, "on your PC, not in rows"))

        uploaded = sum(1 for f in coll.referenced if f in entries)
        legacy = f", {coll.legacy} old Azure IDs" if coll.legacy else ""
        print(f"{name}  ({uploaded}/{len(coll.referenced)} photos in rows uploaded{legacy})")
        for problem, tag, file, note in lines:
            problems += problem
            print(f"  {'!!' if problem else '  '} {tag:<13} {file}  {note}")

    for coll in sorted({k.split("/", 1)[0] for k in masters} - set(colls)):
        print(f"\n! master/{coll}/ has no matching folder in src/collections")
    orphans = pub - expected
    if orphans:
        print(f"\n{len(orphans)} public file(s) no photo uses; `py r2sync run` deletes them")
    print(f"\n{problems} problem(s)" if problems else "\nAll good: everything the site uses is uploaded.")
    return 1 if problems else 0


# --- unused ---------------------------------------------------------------------------------------


def cmd_unused(args) -> int:
    """Local only (no .env needed): photos in collection folders that rows don't use. Deletes nothing."""
    colls = posts.all_collections()
    if args.collection:
        if args.collection not in colls:
            sys.exit(f"No collection {args.collection!r}. Collections: {', '.join(colls)}")
        colls = {args.collection: colls[args.collection]}

    found = 0
    for name, coll in colls.items():
        unused = coll.unreferenced_local
        if not unused:
            continue
        found += len(unused)
        print(f"{name}  ({len(unused)} not in rows)")
        for file in unused:
            print(f"  {coll.local[file].relative_to(posts.REPO).as_posix()}")
    if found:
        print(f"\n{found} photo(s) not used by any rows. Delete them if you're done with them (nothing was deleted).")
    else:
        print("No unused photos: every photo in the collection folders is in rows.")
    return 0


def main() -> int:
    load_dotenv(posts.REPO / ".env")
    parser = argparse.ArgumentParser(prog="py r2sync", description="Sync photos: local -> master -> public.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("push", help="upload a collection's local photos, convert them, remove the local copies")
    p.add_argument("collection", help="folder name in src/collections, e.g. 2025-peak-fog")
    p.add_argument("--keep", action="store_true", help="keep the local copies")
    p.add_argument("--dry-run", action="store_true", help="only show what would happen")
    p.set_defaults(fn=cmd_push)

    p = sub.add_parser("run", help="make public match master")
    p.add_argument("--yes", action="store_true", help="don't ask before deleting many files")
    p.add_argument("--dry-run", action="store_true", help="only show what would happen")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("check", help="report what's out of sync (changes nothing)")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("unused", help="list local photos that rows don't use (local only, deletes nothing)")
    p.add_argument("collection", nargs="?", help="only this collection (default: all)")
    p.set_defaults(fn=cmd_unused)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
