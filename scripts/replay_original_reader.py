#!/usr/bin/env python3
"""Rebuild A10 in an isolated root and prove byte-identical output."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "output" / ".isolated-a10-replay"
LIVE = ROOT / "output" / "html-en"
RECEIPT = ROOT / "ISOLATED_READER_REPLAY.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def confined(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(ROOT.resolve())
    return resolved


def link(relative: str) -> None:
    source = confined(ROOT / relative)
    target = REPLAY / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    os.link(source, target)


def copy(relative: str) -> None:
    source = confined(ROOT / relative)
    target = REPLAY / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def inventory_from_manifest(root: Path) -> dict[str, tuple[int, str]]:
    manifest_bytes = (root / "volume.manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    rows = {
        row["path"]: (int(row["bytes"]), row["sha256"])
        for row in manifest["outputs"]["files_excluding_manifest"]
    }
    rows["volume.manifest.json"] = (len(manifest_bytes), sha(manifest_bytes))
    return rows


def main() -> None:
    if RECEIPT.exists():
        previous = json.loads(RECEIPT.read_bytes())
        current_manifest = (LIVE / "volume.manifest.json").read_bytes()
        if (
            previous.get("status") == "pass"
            and previous["live_reader"]["manifest_sha256"] == sha(current_manifest)
            and not REPLAY.exists()
        ):
            print(RECEIPT.read_text(encoding="utf-8"), end="")
            return
        raise RuntimeError("Existing replay receipt does not bind the current reader")
    if REPLAY.exists():
        raise RuntimeError(f"Stale isolated replay root requires review: {REPLAY}")
    if not LIVE.is_dir():
        raise RuntimeError("Live A10 reader is missing")
    REPLAY.mkdir(parents=True)
    try:
        for relative in (
            "collections/elementary-algebra-2e.collection.xml",
            "authority/source-manifest.tsv",
            "authority/source-package-manifest.json",
            "authority/original-assets.tsv",
            "authority/original-rights-summary.json",
            "authority/provenance/RIGHTS_FREEZE_RECEIPT_20260829.json",
            "LICENSE",
        ):
            link(relative)
        source_rows = list(
            csv.DictReader(
                (ROOT / "authority/source-manifest.tsv").read_text(encoding="utf-8").splitlines(),
                delimiter="\t",
            )
        )
        for row in source_rows:
            link(f"modules/{row['module']}/index.cnxml")
        asset_rows = list(
            csv.DictReader(
                (ROOT / "authority/original-assets.tsv").read_text(encoding="utf-8").splitlines(),
                delimiter="\t",
            )
        )
        for row in asset_rows:
            link(row["workspace_path"])
        # Build scripts are copied, not linked, so the subprocess has an
        # independently rooted executable surface with identical bytes.
        for relative in (
            "scripts/build_reader_en.py",
            "scripts/reader-id.css",
            "scripts/validate_original_reader.py",
        ):
            copy(relative)
        completed = subprocess.run(
            [sys.executable, "-B", str(REPLAY / "scripts/build_reader_en.py")],
            cwd=REPLAY,
            check=True,
            capture_output=True,
            text=True,
        )
        validation = subprocess.run(
            [sys.executable, "-B", str(REPLAY / "scripts/validate_original_reader.py")],
            cwd=REPLAY,
            check=True,
            capture_output=True,
            text=True,
        )
        replay_reader = REPLAY / "output" / "html-en"
        live_inventory = inventory_from_manifest(LIVE)
        replay_inventory = inventory_from_manifest(replay_reader)
        if live_inventory != replay_inventory:
            raise RuntimeError("Isolated replay manifest inventory differs")
        for relative, expected in live_inventory.items():
            live_bytes = (LIVE / relative).read_bytes()
            replay_bytes = (replay_reader / relative).read_bytes()
            if live_bytes != replay_bytes or (len(live_bytes), sha(live_bytes)) != expected:
                raise RuntimeError(f"Isolated replay byte mismatch: {relative}")
        live_manifest = (LIVE / "volume.manifest.json").read_bytes()
        replay_validation = REPLAY / "INDEPENDENT_READER_VALIDATION_V2.json"
        receipt = {
            "schema": "openstax-elementary-original-reader-isolated-replay/1",
            "status": "pass",
            "method": (
                "isolated directory; manifest-enumerated same-volume hardlinks for immutable "
                "source bytes; independently copied scripts; full build and independent validator"
            ),
            "source_revision": "38cae454e644abf9f0a623e876994553881597c9",
            "inputs": {
                "modules": len(source_rows),
                "media_files": len(asset_rows),
                "input_files_total": 7 + len(source_rows) + len(asset_rows) + 3,
            },
            "live_reader": {
                "files": len(live_inventory),
                "bytes": sum(size for size, _ in live_inventory.values()),
                "manifest_sha256": sha(live_manifest),
            },
            "replay_reader": {
                "files": len(replay_inventory),
                "bytes": sum(size for size, _ in replay_inventory.values()),
                "manifest_sha256": sha((replay_reader / "volume.manifest.json").read_bytes()),
            },
            "independent_validation": {
                "bytes": replay_validation.stat().st_size,
                "sha256": sha(replay_validation.read_bytes()),
                "stdout_sha256": sha(validation.stdout.encode("utf-8")),
            },
            "builder_stdout_sha256": sha(completed.stdout.encode("utf-8")),
            "byte_identical": True,
            "replay_root_removed_after_verification": True,
        }
        shutil.rmtree(REPLAY)
        data = stable(receipt)
        with RECEIPT.open("xb") as stream:
            stream.write(data)
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        print(f"Receipt {len(data):,} bytes SHA-256 {sha(data)}")
    except BaseException:
        # Keep a failed isolated root for exact diagnosis; never touch live output.
        raise


if __name__ == "__main__":
    main()
