#!/usr/bin/env python3
"""Acquire the exact original-English Elementary Algebra 2e closure.

The current Indonesian preservation source ZIP is the manifest/provenance
anchor.  It already contains the 82 original CNXML modules and exact source
and media manifests.  The pinned upstream codeload archive is used only to
recover the hash-bound media bytes and to independently confirm the original
collection, modules, and license.

The operation is resumable at the archive download boundary, writes only below
this mirror root, refuses to overwrite differing bytes, and removes the large
temporary codeload archive only after every admitted byte has been verified.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

from lxml import etree
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ZIP = ROOT / "elementary-algebra-2e-id-ID-1.0.3-source.zip"
SOURCE_ZIP_BYTES = 7_264_274
SOURCE_ZIP_SHA256 = (
    "77a6ecfa22c4a5b58b0b7f72e5ec9db11ac4656bc7fc9c4944a4a7916a2472f3"
)
SOURCE_MANIFEST_SHA256 = (
    "b817c9bfbd1dcba59f1e6949a83727a662bf95407882634620cd46b625b6a5f2"
)
MEDIA_MANIFEST_SHA256 = (
    "3b8478b77c8860363b7000cbffa68782320e73458289bdcda957acf1b971210f"
)
REVISION = "38cae454e644abf9f0a623e876994553881597c9"
TREE = "7907e4c81d43de1c3b6da173f0eb273c01dc5b55"
ARCHIVE_URL = (
    "https://codeload.github.com/openstax/osbooks-prealgebra-bundle/zip/"
    + REVISION
)
ARCHIVE = ROOT / f"upstream-{REVISION}.zip"
ARCHIVE_PART = ROOT / f"upstream-{REVISION}.zip.part"
ARCHIVE_BYTES = 537_455_794
ARCHIVE_SHA256 = (
    "effdf2dbb6dfd9cab771b568c6575d8074be4a1f9565f1fedbd54f621e138917"
)
ARCHIVE_PREFIX = f"osbooks-prealgebra-bundle-{REVISION}/"
COLLECTION = "collections/elementary-algebra-2e.collection.xml"
EXPECTED_MODULES = 82
EXPECTED_SOURCE_ROWS = 88
EXPECTED_IMAGE_USES = 4_024
EXPECTED_MEDIA = 4_018
EXPECTED_MEDIA_BYTES = 194_271_847
CNXML = "http://cnx.rice.edu/cnxml"
COLLXML = "http://cnx.rice.edu/collxml"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(name)
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in name
        and not re.match(r"^[A-Za-z]:", name)
    )


def immutable(path: Path, data: bytes) -> None:
    resolved = path.resolve()
    resolved.relative_to(ROOT.resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"Refusing to replace different bytes: {path}")
        return
    with path.open("xb") as stream:
        stream.write(data)


def verify_source_zip() -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, object]]:
    if SOURCE_ZIP.stat().st_size != SOURCE_ZIP_BYTES or sha256_file(SOURCE_ZIP) != SOURCE_ZIP_SHA256:
        raise RuntimeError("A10 preservation source ZIP identity mismatch")
    with zipfile.ZipFile(SOURCE_ZIP) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not all(safe_member(name) for name in names):
            raise RuntimeError("Unsafe or duplicate preservation ZIP member")
        if archive.testzip() is not None:
            raise RuntimeError("Preservation source ZIP CRC failure")
        manifest_bytes = archive.read("MANIFEST.json")
        checksums_bytes = archive.read("SHA256SUMS.txt")
        manifest = json.loads(manifest_bytes)
        entries = {row["path"]: row for row in manifest["entries"]}
        if len(entries) != 428 or set(names) != set(entries) | {"MANIFEST.json", "SHA256SUMS.txt"}:
            raise RuntimeError("Preservation ZIP manifest coverage mismatch")
        checksum_rows = {}
        for line in checksums_bytes.decode("utf-8").splitlines():
            digest, name = line.split("  ", 1)
            checksum_rows[name] = digest
        if checksum_rows != {name: row["sha256"] for name, row in entries.items()}:
            raise RuntimeError("Preservation ZIP checksum file and manifest differ")
        payload_bytes = 0
        for name, row in entries.items():
            data = archive.read(name)
            if len(data) != int(row["bytes"]) or sha256_bytes(data) != row["sha256"]:
                raise RuntimeError(f"Preservation ZIP payload mismatch: {name}")
            payload_bytes += len(data)
        if (
            manifest["payload_entry_count"] != len(entries)
            or manifest["payload_uncompressed_bytes"] != payload_bytes
        ):
            raise RuntimeError("Preservation ZIP aggregate mismatch")
        source_manifest = archive.read("authority/SOURCE_AUTHORITY_MANIFEST.csv")
        media_manifest = archive.read("authority/MEDIA_AUTHORITY_MANIFEST.csv")
        if sha256_bytes(source_manifest) != SOURCE_MANIFEST_SHA256:
            raise RuntimeError("Frozen source manifest mismatch")
        if sha256_bytes(media_manifest) != MEDIA_MANIFEST_SHA256:
            raise RuntimeError("Frozen media manifest mismatch")
        sources = list(csv.DictReader(io.StringIO(source_manifest.decode("utf-8-sig"))))
        media = list(csv.DictReader(io.StringIO(media_manifest.decode("utf-8-sig"))))
        if len(sources) != EXPECTED_SOURCE_ROWS or len(media) != EXPECTED_MEDIA:
            raise RuntimeError("Frozen authority row count mismatch")
        package = {
            "schema": "openstax-elementary-original-source-package/1",
            "preservation_source_zip": {
                "path": SOURCE_ZIP.name,
                "bytes": SOURCE_ZIP_BYTES,
                "sha256": SOURCE_ZIP_SHA256,
                "entries": len(names),
                "payload_entries": len(entries),
                "payload_uncompressed_bytes": payload_bytes,
                "manifest": {
                    "bytes": len(manifest_bytes),
                    "sha256": sha256_bytes(manifest_bytes),
                },
                "checksums": {
                    "bytes": len(checksums_bytes),
                    "sha256": sha256_bytes(checksums_bytes),
                },
            },
            "authority": {
                "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
                "media_manifest_sha256": MEDIA_MANIFEST_SHA256,
                "source_revision": REVISION,
                "source_tree": TREE,
            },
        }
        return sources, media, package


def download_archive() -> None:
    if ARCHIVE.exists():
        return
    offset = ARCHIVE_PART.stat().st_size if ARCHIVE_PART.exists() else 0
    headers = {"User-Agent": "Interlanguage-original-reader-preservation/1"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = Request(ARCHIVE_URL, headers=headers)
    with urlopen(request, timeout=120) as response:
        status = getattr(response, "status", response.getcode())
        append = bool(offset and status == 206)
        if offset and not append and status != 200:
            raise RuntimeError(f"Unexpected archive resume status {status}")
        mode = "ab" if append else "wb"
        with ARCHIVE_PART.open(mode) as target:
            copied = offset if append else 0
            while True:
                chunk = response.read(4 * 1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)
                copied += len(chunk)
                if copied // (64 * 1024 * 1024) != (copied - len(chunk)) // (64 * 1024 * 1024):
                    print(f"Downloaded {copied:,}/{ARCHIVE_BYTES:,} bytes", flush=True)
    if ARCHIVE_PART.stat().st_size != ARCHIVE_BYTES or sha256_file(ARCHIVE_PART) != ARCHIVE_SHA256:
        raise RuntimeError(
            f"Incomplete or mismatched upstream archive: {ARCHIVE_PART.stat().st_size:,} bytes"
        )
    os.replace(ARCHIVE_PART, ARCHIVE)


def source_rows_by_path(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result = {row["relative_path"]: row for row in rows}
    if len(result) != len(rows):
        raise RuntimeError("Duplicate frozen source paths")
    return result


def extract_original_sources(rows: list[dict[str, str]]) -> tuple[list[str], int]:
    by_path = source_rows_by_path(rows)
    with zipfile.ZipFile(SOURCE_ZIP) as package:
        collection_bytes = package.read("authority/elementary-algebra-2e.collection.xml")
        binding = by_path[COLLECTION]
        if len(collection_bytes) != int(binding["bytes"]) or sha256_bytes(collection_bytes) != binding["sha256"]:
            raise RuntimeError("Original collection does not match frozen source manifest")
        immutable(ROOT / COLLECTION, collection_bytes)
        collection = etree.fromstring(
            collection_bytes,
            parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True),
        )
        refs = collection.xpath(".//c:module/@document", namespaces={"c": COLLXML})
        if len(refs) != len(set(refs)) or len(refs) != EXPECTED_MODULES:
            raise RuntimeError("Elementary collection module order mismatch")
        module_rows = sorted(
            (row for row in rows if row["role"] == "cnxml_module"),
            key=lambda row: int(row["order"]),
        )
        if refs != [PurePosixPath(row["relative_path"]).parts[1] for row in module_rows]:
            raise RuntimeError("Source manifest and collection order differ")
        total = 0
        lines = ["ordinal\tmodule\tbytes\tsha256\tpath\turl"]
        for position, (module_id, row) in enumerate(zip(refs, module_rows), 1):
            member = f"authority/source/modules/{module_id}/index.cnxml"
            data = package.read(member)
            if len(data) != int(row["bytes"]) or sha256_bytes(data) != row["sha256"]:
                raise RuntimeError(f"Original module mismatch: {module_id}")
            immutable(ROOT / "modules" / module_id / "index.cnxml", data)
            total += len(data)
            lines.append(
                "\t".join(
                    (
                        str(position),
                        module_id,
                        str(len(data)),
                        row["sha256"],
                        f"{module_id}.source.cnxml",
                        "https://raw.githubusercontent.com/openstax/"
                        f"osbooks-prealgebra-bundle/{REVISION}/modules/{module_id}/index.cnxml",
                    )
                )
            )
        immutable(ROOT / "authority/source-manifest.tsv", ("\n".join(lines) + "\n").encode("utf-8"))
        immutable(ROOT / "LICENSE", package.read("LICENSE.txt"))
        immutable(
            ROOT / "authority/provenance/SOURCE_AUTHORITY_AND_RIGHTS.md",
            package.read("documentation/SOURCE_AUTHORITY_AND_RIGHTS.md"),
        )
        immutable(
            ROOT / "authority/provenance/SOURCE_FREEZE.md",
            package.read("documentation/SOURCE_FREEZE.md"),
        )
        rights_bytes = package.read("documentation/rights/RIGHTS_FREEZE_RECEIPT_20260829.json")
        immutable(ROOT / "authority/provenance/RIGHTS_FREEZE_RECEIPT_20260829.json", rights_bytes)
        rights = json.loads(rights_bytes)
        summary = {
            "schema": "openstax-elementary-original-rights-summary/1",
            "source_revision": REVISION,
            "status": rights["status"],
            "work_default_rights_record": rights["work_default_rights_record"],
            "asset_rights_linkage": rights["asset_rights_linkage"],
            "preserved_component_status": rights["preserved_component_status"],
            "explicit_credit_witnesses": rights["explicit_credit_witnesses"],
            "notice": (
                "Original CNXML captions and credits remain controlling. Component uncertainty "
                "is preserved and this summary does not independently relicense any asset."
            ),
        }
        immutable(ROOT / "authority/original-rights-summary.json", stable_json(summary))
    return refs, total


def analyze_asset_uses(refs: list[str], media_rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    bindings = {row["relative_path"]: row for row in media_rows}
    if len(bindings) != EXPECTED_MEDIA:
        raise RuntimeError("Duplicate media authority path")
    uses: dict[str, dict[str, object]] = {}
    for module_id in refs:
        raw = (ROOT / "modules" / module_id / "index.cnxml").read_bytes()
        root = etree.fromstring(
            raw,
            parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True),
        )
        for image in root.iter(f"{{{CNXML}}}image"):
            source = image.get("src")
            if not source:
                raise RuntimeError(f"Image without src in {module_id}")
            normalized = posixpath.normpath(posixpath.join("modules", module_id, source))
            if normalized not in bindings:
                raise RuntimeError(f"Image outside frozen media closure: {module_id} {source}")
            declared = image.get("mime-type") or ""
            canonical_declared = "image/jpeg" if declared == "image/jpg" else declared
            # Upstream's declared MIME is known to be unreliable (including one
            # repeated JPEG path declared once as JPEG and once as PNG).  The
            # path/signature identity is canonical; every declaration remains
            # inventoried instead of being rewritten in the source CNXML.
            suffix = PurePosixPath(normalized).suffix.casefold()
            canonical_mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
            }.get(suffix)
            if canonical_mime is None:
                raise RuntimeError(f"Unsupported media suffix: {normalized}")
            row = uses.setdefault(
                normalized,
                {
                    "raw_source_path": source,
                    "workspace_path": normalized,
                    "mime_type": canonical_mime,
                    "declared_mime_types": [],
                    "occurrences": 0,
                    "modules": [],
                },
            )
            if row["raw_source_path"] != source or row["mime_type"] != canonical_mime:
                raise RuntimeError(f"Conflicting repeated media identity: {normalized}")
            if canonical_declared not in row["declared_mime_types"]:
                row["declared_mime_types"].append(canonical_declared)
            row["occurrences"] = int(row["occurrences"]) + 1
            if module_id not in row["modules"]:
                row["modules"].append(module_id)
    if len(uses) != EXPECTED_MEDIA or sum(int(row["occurrences"]) for row in uses.values()) != EXPECTED_IMAGE_USES:
        raise RuntimeError("CNXML image-use closure mismatch")
    if set(uses) != set(bindings):
        raise RuntimeError("Frozen media manifest is not the exact referenced closure")
    return uses


def verify_upstream_and_extract(
    refs: list[str],
    source_rows: list[dict[str, str]],
    media_rows: list[dict[str, str]],
    uses: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    by_source = source_rows_by_path(source_rows)
    formats: Counter[str] = Counter()
    detected_mime_differences = 0
    results: list[dict[str, object]] = []
    with zipfile.ZipFile(ARCHIVE) as upstream:
        names = upstream.namelist()
        if len(names) != len(set(names)) or not all(safe_member(name) for name in names):
            raise RuntimeError("Unsafe or duplicate upstream archive member")
        bad = upstream.testzip()
        if bad is not None:
            raise RuntimeError(f"Upstream archive CRC failure: {bad}")
        required_source_paths = ["LICENSE", COLLECTION] + [f"modules/{module_id}/index.cnxml" for module_id in refs]
        for relative in required_source_paths:
            data = upstream.read(ARCHIVE_PREFIX + relative)
            binding = by_source[relative]
            if (
                len(data) != int(binding["bytes"])
                or sha256_bytes(data) != binding["sha256"]
                or git_blob_sha1(data) != binding["git_blob_sha1"]
            ):
                raise RuntimeError(f"Official archive source mismatch: {relative}")
        for index, binding in enumerate(media_rows, 1):
            relative = binding["relative_path"]
            data = upstream.read(ARCHIVE_PREFIX + relative)
            if (
                len(data) != int(binding["bytes"])
                or sha256_bytes(data) != binding["sha256"]
                or git_blob_sha1(data) != binding["git_blob_sha1"]
            ):
                raise RuntimeError(f"Official archive media mismatch: {relative}")
            with Image.open(io.BytesIO(data)) as image:
                detected_format = image.format
                dimensions = list(image.size)
                image.verify()
            if detected_format not in {"JPEG", "PNG"}:
                raise RuntimeError(f"Unsupported image format {detected_format}: {relative}")
            formats[detected_format] += 1
            detected_mime = {"JPEG": "image/jpeg", "PNG": "image/png"}[detected_format]
            if detected_mime not in uses[relative]["declared_mime_types"]:
                detected_mime_differences += 1
            if detected_mime != uses[relative]["mime_type"]:
                raise RuntimeError(f"Path/signature MIME mismatch: {relative}")
            immutable(ROOT / relative, data)
            results.append(
                {
                    **uses[relative],
                    "bytes": len(data),
                    "sha256": binding["sha256"],
                    "git_blob_sha1": binding["git_blob_sha1"],
                    "detected_format": detected_format,
                    "detected_mime_type": detected_mime,
                    "dimensions": dimensions,
                }
            )
            if index % 250 == 0:
                print(f"Verified original assets {index:,}/{EXPECTED_MEDIA:,}", flush=True)
    if sum(int(row["bytes"]) for row in results) != EXPECTED_MEDIA_BYTES:
        raise RuntimeError("Admitted media byte total mismatch")
    lines = ["source_path\tworkspace_path\tmime_type\tbytes\tsha256\toccurrences"]
    for row in sorted(results, key=lambda item: str(item["raw_source_path"])):
        lines.append(
            "\t".join(
                str(row[key])
                for key in ("raw_source_path", "workspace_path", "mime_type", "bytes", "sha256", "occurrences")
            )
        )
    asset_tsv = ("\n".join(lines) + "\n").encode("utf-8")
    immutable(ROOT / "authority/original-assets.tsv", asset_tsv)
    return results, {
        "formats": dict(formats),
        "declared_mime_signature_differences": detected_mime_differences,
        "canonical_asset_manifest": {
            "path": "authority/original-assets.tsv",
            "bytes": len(asset_tsv),
            "sha256": sha256_bytes(asset_tsv),
        },
    }


def verify_existing_outputs(
    refs: list[str], media_rows: list[dict[str, str]]
) -> None:
    for module_id in refs:
        path = ROOT / "modules" / module_id / "index.cnxml"
        if not path.is_file():
            raise RuntimeError(f"Missing extracted module: {module_id}")
    for row in media_rows:
        path = ROOT / row["relative_path"]
        if (
            not path.is_file()
            or path.stat().st_size != int(row["bytes"])
            or sha256_file(path) != row["sha256"]
        ):
            raise RuntimeError(f"Extracted media identity mismatch: {row['relative_path']}")


def main() -> None:
    source_rows, media_rows, package = verify_source_zip()
    refs, module_bytes = extract_original_sources(source_rows)
    uses = analyze_asset_uses(refs, media_rows)
    receipt_path = ROOT / "SOURCE_ACQUISITION_RECEIPT.json"
    if receipt_path.exists() and not ARCHIVE.exists() and not ARCHIVE_PART.exists():
        verify_existing_outputs(refs, media_rows)
        print(receipt_path.read_text(encoding="utf-8"), end="")
        return
    download_archive()
    if ARCHIVE.stat().st_size != ARCHIVE_BYTES or sha256_file(ARCHIVE) != ARCHIVE_SHA256:
        raise RuntimeError("Upstream archive identity mismatch")
    results, image_summary = verify_upstream_and_extract(refs, source_rows, media_rows, uses)
    verify_existing_outputs(refs, media_rows)
    package["authority"]["source_manifest_rows"] = len(source_rows)
    package["authority"]["ordered_modules"] = len(refs)
    package["authority"]["module_bytes"] = module_bytes
    package["authority"]["media_files"] = len(results)
    package["authority"]["media_bytes"] = sum(int(row["bytes"]) for row in results)
    package["authority"]["image_uses"] = sum(int(row["occurrences"]) for row in results)
    immutable(ROOT / "authority/source-package-manifest.json", stable_json(package))
    archive_identity = {
        "url": ARCHIVE_URL,
        "bytes": ARCHIVE_BYTES,
        "sha256": ARCHIVE_SHA256,
        "entry_prefix": ARCHIVE_PREFIX,
        "zip_crc_pass": True,
        "duplicate_member_names": 0,
        "removed_after_exact_closure_extraction": True,
    }
    receipt = {
        "schema": "openstax-elementary-original-source-acquisition/1",
        "source_revision": REVISION,
        "source_tree": TREE,
        "preservation_package": package["preservation_source_zip"],
        "official_upstream_archive": archive_identity,
        "closure": {
            "collection": COLLECTION,
            "ordered_modules": len(refs),
            "module_bytes": module_bytes,
            "image_uses": EXPECTED_IMAGE_USES,
            "media_files": len(results),
            "media_bytes": sum(int(row["bytes"]) for row in results),
        },
        "images": image_summary,
        "checks": [
            "preservation ZIP safe unique names and CRC",
            "preservation manifest/checksum exact payload closure",
            "source and media authority manifest hashes",
            "collection and source-manifest module order",
            "official archive safe unique names and CRC",
            "official collection/module/license bytes, SHA-256 and Git blob identities",
            "all media bytes, SHA-256 and Git blob identities",
            "all media image signatures decode",
            "exact CNXML image-use closure",
            "bounded rehash of every admitted output path",
        ],
    }
    # The codeload archive is a transient carrier.  All exact source/module/media
    # outputs and the much smaller provenance ZIP remain locally.
    ARCHIVE.unlink()
    data = stable_json(receipt)
    immutable(receipt_path, data)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True), flush=True)
    print(f"Receipt {len(data):,} bytes SHA-256 {sha256_bytes(data)}", flush=True)


if __name__ == "__main__":
    main()
