#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib import error, request


DEFAULT_SPLITS = (
    "train2014",
    "val2014",
    "test2014",
    "train2017",
    "val2017",
    "test2017",
    "unlabeled2017",
)
DEFAULT_BASE_URL = "https://images.cocodataset.org"


@dataclass(frozen=True)
class DatasetEntry:
    entry_name: str
    image_id: str
    source_group: str
    source_path: str


@dataclass(frozen=True)
class DownloadResult:
    image_id: str
    status: str
    split: str
    url: str
    local_path: str
    message: str


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    output_dir = repo_root / "mscoco_images"

    parser = argparse.ArgumentParser(
        description=(
            "Download the MS COCO images referenced by AOI_Data CSV files, "
            "deduplicate repeated image IDs, and write a manifest mapping AOI entries to local files."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root,
        help="Path to the dataset repository root.",
    )
    parser.add_argument(
        "--entry-dir",
        type=Path,
        default=repo_root / "AOI_Data",
        help="Directory used to enumerate canonical AOI CSV files.",
    )
    parser.add_argument(
        "--entry-glob",
        default="*.csv",
        help="Glob used inside --entry-dir to find AOI CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=output_dir,
        help="Directory where COCO images will be stored.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=output_dir / "manifest.csv",
        help="CSV file to write the AOI-entry-to-image mapping.",
    )
    parser.add_argument(
        "--mapping-csv",
        type=Path,
        help=(
            "Optional CSV containing explicit image-to-split mapping. Expected columns: "
            "image_id or stimuli, and split."
        ),
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        default=list(DEFAULT_SPLITS),
        help="COCO split names to try when no explicit mapping exists.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL for COCO image downloads.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of concurrent download workers.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retries per split for transient network failures.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional cap on the number of unique image IDs to process.",
    )
    return parser.parse_args()


def normalize_image_id(value: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("Empty image ID")
    if text.endswith(".0"):
        text = text[:-2]
    return f"{int(text):012d}"


def parse_entry_name(file_path: Path, root_dir: Path) -> DatasetEntry:
    parent_name = file_path.parent.name
    if parent_name not in {"A", "B"}:
        raise ValueError(f"Expected AOI files under A/ or B/, got: {file_path}")

    image_id = normalize_image_id(file_path.stem)
    relative_path = file_path.relative_to(root_dir)
    return DatasetEntry(
        entry_name=str(relative_path.with_suffix("")),
        image_id=image_id,
        source_group=parent_name,
        source_path=str(relative_path),
    )


def load_entries(entry_dir: Path, entry_glob: str) -> list[DatasetEntry]:
    if not entry_dir.exists():
        raise FileNotFoundError(f"Entry directory does not exist: {entry_dir}")

    entries: list[DatasetEntry] = []
    invalid_names: list[str] = []
    for file_path in sorted(entry_dir.rglob(entry_glob)):
        if not file_path.is_file():
            continue
        try:
            entries.append(parse_entry_name(file_path, entry_dir))
        except ValueError:
            invalid_names.append(str(file_path.relative_to(entry_dir)))

    if not entries:
        raise RuntimeError(f"No AOI CSV files found in {entry_dir} matching {entry_glob!r}")

    if invalid_names:
        preview = ", ".join(invalid_names[:5])
        raise RuntimeError(
            "Encountered files that do not match the expected AOI CSV layout: "
            f"{preview}"
        )

    return entries


def load_split_mapping(mapping_csv: Path | None) -> dict[str, str]:
    if mapping_csv is None:
        return {}
    if not mapping_csv.exists():
        raise FileNotFoundError(f"Mapping CSV does not exist: {mapping_csv}")

    with mapping_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"Mapping CSV has no header row: {mapping_csv}")

        lowered = {name.lower(): name for name in reader.fieldnames}
        image_key = lowered.get("image_id") or lowered.get("stimuli")
        split_key = lowered.get("split")
        if image_key is None or split_key is None:
            raise RuntimeError(
                "Mapping CSV must contain columns named image_id or stimuli, and split."
            )

        mapping: dict[str, str] = {}
        for row in reader:
            image_id = normalize_image_id(row[image_key])
            split = row[split_key].strip()
            if split:
                mapping[image_id] = split
        return mapping


def build_url(base_url: str, split: str, image_id: str) -> str:
    return f"{base_url.rstrip('/')}/{split}/{image_id}.jpg"


def relative_to_root(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def existing_download(output_dir: Path, image_id: str, splits: Iterable[str]) -> tuple[str, Path] | None:
    for split in splits:
        candidate = output_dir / split / f"{image_id}.jpg"
        if candidate.exists() and candidate.stat().st_size > 0:
            return split, candidate
    return None


def fetch_url(url: str, destination: Path, timeout: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(destination.suffix + ".part")
    insecure_context = ssl._create_unverified_context()
    response = request.urlopen(url, timeout=timeout, context=insecure_context)

    with response:
        if getattr(response, "status", 200) != 200:
            raise error.HTTPError(url, response.status, "Unexpected status", response.headers, None)
        temporary_path.write_bytes(response.read())
    temporary_path.replace(destination)


def resolve_and_download(
    image_id: str,
    output_dir: Path,
    repo_root: Path,
    base_url: str,
    mapping: dict[str, str],
    split_order: list[str],
    timeout: float,
    retries: int,
) -> DownloadResult:
    mapped_split = mapping.get(image_id)
    candidate_splits = [mapped_split] if mapped_split else list(split_order)

    existing = existing_download(output_dir, image_id, candidate_splits)
    if existing is not None:
        split, local_path = existing
        url = build_url(base_url, split, image_id)
        return DownloadResult(
            image_id=image_id,
            status="existing",
            split=split,
            url=url,
            local_path=relative_to_root(local_path, repo_root),
            message="already present",
        )

    last_error = "not_found"
    for split in candidate_splits:
        url = build_url(base_url, split, image_id)
        destination = output_dir / split / f"{image_id}.jpg"
        for attempt in range(retries + 1):
            try:
                fetch_url(url, destination, timeout)
                return DownloadResult(
                    image_id=image_id,
                    status="downloaded",
                    split=split,
                    url=url,
                    local_path=relative_to_root(destination, repo_root),
                    message="downloaded",
                )
            except error.HTTPError as exc:
                if exc.code == 404:
                    last_error = f"404:{split}"
                    break
                last_error = f"http_{exc.code}:{split}"
            except error.URLError as exc:
                last_error = f"url_error:{split}:{exc.reason}"
            except TimeoutError:
                last_error = f"timeout:{split}"

            if attempt < retries:
                time.sleep(min(1.5 * (attempt + 1), 5.0))

    return DownloadResult(
        image_id=image_id,
        status="missing",
        split="",
        url="",
        local_path="",
        message=last_error,
    )


def write_manifest(
    manifest_path: Path,
    entries: list[DatasetEntry],
    results: dict[str, DownloadResult],
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "entry_name",
                "source_group",
                "image_id",
                "source_path",
                "image_status",
                "split",
                "coco_url",
                "local_path",
                "message",
            ],
        )
        writer.writeheader()
        for entry in entries:
            result = results[entry.image_id]
            writer.writerow(
                {
                    "entry_name": entry.entry_name,
                    "source_group": entry.source_group,
                    "image_id": entry.image_id,
                    "source_path": entry.source_path,
                    "image_status": result.status,
                    "split": result.split,
                    "coco_url": result.url,
                    "local_path": result.local_path,
                    "message": result.message,
                }
            )


def main() -> int:
    args = parse_args()

    entries = load_entries(args.entry_dir, args.entry_glob)
    mapping = load_split_mapping(args.mapping_csv)

    image_ids = sorted({entry.image_id for entry in entries})
    if args.limit is not None:
        image_ids = image_ids[: args.limit]

    selected_ids = set(image_ids)
    selected_entries = [entry for entry in entries if entry.image_id in selected_ids]

    results: dict[str, DownloadResult] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                resolve_and_download,
                image_id,
                args.output_dir,
                args.repo_root,
                args.base_url,
                mapping,
                list(args.splits),
                args.timeout,
                max(0, args.retries),
            ): image_id
            for image_id in image_ids
        }
        for future in as_completed(futures):
            image_id = futures[future]
            results[image_id] = future.result()

    write_manifest(args.manifest_path, selected_entries, results)

    downloaded = sum(1 for result in results.values() if result.status == "downloaded")
    existing = sum(1 for result in results.values() if result.status == "existing")
    missing = sum(1 for result in results.values() if result.status == "missing")

    print(f"AOI entries processed: {len(selected_entries)}")
    print(f"Unique image IDs: {len(image_ids)}")
    print(f"Downloaded: {downloaded}")
    print(f"Already present: {existing}")
    print(f"Missing: {missing}")
    print(f"Manifest: {args.manifest_path}")

    if missing:
        missing_ids = ", ".join(
            sorted(result.image_id for result in results.values() if result.status == "missing")[:10]
        )
        print(f"First missing IDs: {missing_ids}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())