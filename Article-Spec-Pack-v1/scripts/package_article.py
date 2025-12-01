"""Utility to normalize completed article folders.

Usage:
    python scripts/package_article.py \
        --article-folder "6-Completed-Articles/Article-20251114-From-Logic-to-Prediction" \
        --source-file "0-Article-Content/03-from-logic-to-prediction.md"

The script is intentionally flexible:
- Default mappings move briefs, references, reports, and drafts into subfolders.
- Additional pattern→folder mappings can be provided via repeated --mapping flags.
- Skip or dry-run modes let you preview changes before applying them.
- When a source file is provided it is moved (not copied) from `0-Article-Content/` into the article’s `sources/` folder so the intake directory stays clean.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

DEFAULT_MAPPINGS: Sequence[Tuple[str, str]] = (
    ("brief*.md", "briefs"),
    ("*brief*.md", "briefs"),
    ("references*.md", "references"),
    ("reference*.md", "references"),
    ("Article-*v*.md", "reports"),
    ("*-v*.md", "reports"),
    ("*report*.md", "reports"),
    ("*.draft.md", "drafts"),
    ("draft*.md", "drafts"),
    ("metadata.json", "reports"),
)

DEFAULT_SKIP_PATTERNS = {"article.md"}


def parse_mapping(value: str) -> Tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            f"Mapping '{value}' must look like 'pattern=folder'"
        )
    pattern, folder = value.split("=", 1)
    pattern = pattern.strip()
    folder = folder.strip()
    if not pattern or not folder:
        raise argparse.ArgumentTypeError(
            f"Mapping '{value}' is missing a pattern or folder name"
        )
    return pattern, folder


def ensure_folder(path: Path, dry_run: bool) -> None:
    if path.exists():
        return
    if dry_run:
        print(f"[dry-run] mkdir {path}")
        return
    path.mkdir(parents=True, exist_ok=True)


def resolve_collision(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    counter = 1
    while True:
        candidate = dest.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def move_file(src: Path, dest_dir: Path, dry_run: bool) -> None:
    ensure_folder(dest_dir, dry_run)
    dest = dest_dir / src.name
    dest = resolve_collision(dest)
    if dry_run:
        print(f"[dry-run] move {src} -> {dest}")
        return
    src.replace(dest)
    print(f"Moved {src.name} -> {dest.relative_to(dest_dir.parent)}")


def move_source_file(source_file: Path, dest_dir: Path, dry_run: bool) -> None:
    ensure_folder(dest_dir, dry_run)
    dest = dest_dir / source_file.name
    dest = resolve_collision(dest)
    if dry_run:
        print(f"[dry-run] move {source_file} -> {dest}")
        return
    source_file.replace(dest)
    print(f"Moved source file -> {dest.relative_to(dest_dir.parent)}")


def gather_targets(article_dir: Path) -> Iterable[Path]:
    yield from article_dir.glob("*")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize article folder layout")
    parser.add_argument(
        "--article-folder",
        required=True,
        type=Path,
        help="Path to the completed article folder",
    )
    parser.add_argument(
        "--source-file",
        type=Path,
        help="Path to the originating chapter file to move into sources/",
    )
    parser.add_argument(
        "--mapping",
        type=parse_mapping,
        action="append",
        default=[],
        help="Custom pattern=folder mapping (repeatable)",
    )
    parser.add_argument(
        "--ensure",
        action="append",
        default=[],
        help="Additional subfolder names to create",
    )
    parser.add_argument(
        "--skip-pattern",
        action="append",
        default=[],
        help="Filename glob patterns to leave untouched",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without modifying files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print matched files even if they stay put",
    )

    args = parser.parse_args(argv)
    article_dir = args.article_folder.expanduser().resolve()
    if not article_dir.exists():
        parser.error(f"Article folder '{article_dir}' does not exist")

    mappings: List[Tuple[str, str]] = list(DEFAULT_MAPPINGS)
    mappings.extend(args.mapping)

    skip_patterns = set(DEFAULT_SKIP_PATTERNS)
    skip_patterns.update(pattern.strip() for pattern in args.skip_pattern)

    folders_to_ensure = {folder for _, folder in mappings}
    folders_to_ensure.update(args.ensure)
    if args.source_file is not None:
        folders_to_ensure.add("sources")

    for folder in sorted(folders_to_ensure):
        ensure_folder(article_dir / folder, args.dry_run)

    targets = list(gather_targets(article_dir))
    for path in targets:
        if not path.is_file():
            continue
        relative_name = path.name
        if any(fnmatch.fnmatch(relative_name, pattern) for pattern in skip_patterns):
            if args.verbose:
                print(f"Skipping {relative_name} (matched skip pattern)")
            continue
        for pattern, folder in mappings:
            if fnmatch.fnmatch(relative_name, pattern):
                move_file(path, article_dir / folder, args.dry_run)
                break
        else:
            if args.verbose:
                print(f"Leaving {relative_name} in place (no mapping)")

    if args.source_file:
        source_path = args.source_file.expanduser().resolve()
        if not source_path.exists():
            parser.error(f"Source file '{source_path}' does not exist")
        move_source_file(source_path, article_dir / "sources", args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
