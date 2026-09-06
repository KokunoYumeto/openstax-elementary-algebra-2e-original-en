#!/usr/bin/env python3
"""Fail closed unless every A10 reader page exposes the universal navigation."""

from __future__ import annotations

import argparse
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_READER_ROOT = REPOSITORY_ROOT / "output" / "html-en"
DEFAULT_RECEIPT = REPOSITORY_ROOT / "PROGRAM_NAVIGATION_VALIDATION_V1.json"
EXPECTED_LINKS = {
    "https://kokunoyumeto.github.io/program-matematika-indonesia/en/#course-A10": {
        "hreflang": "en",
        "rel": "home",
    },
    "https://kokunoyumeto.github.io/program-matematika-indonesia/id/#course-A10": {
        "hreflang": "id",
        "rel": "home",
    },
    "https://openstax.org/details/books/elementary-algebra-2e": {
        "hreflang": "en",
        "class": "original-source-link",
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_json(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


class NavigationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nav_depth = 0
        self.navigation_count = 0
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "nav" and "paired-access" in attributes.get("class", "").split():
            self.navigation_count += 1
            self.nav_depth = 1
            return
        if self.nav_depth:
            self.nav_depth += 1
            if tag == "a":
                self.links.append(attributes)

    def handle_endtag(self, tag: str) -> None:
        if not self.nav_depth:
            return
        self.nav_depth -= 1


def normalized_rel(value: str) -> set[str]:
    return {part.casefold() for part in value.split() if part}


def validate_page(path: Path) -> None:
    parser = NavigationParser()
    parser.feed(path.read_text(encoding="utf-8"))
    if parser.navigation_count != 1:
        raise RuntimeError(
            f"{path}: expected one paired-access navigation, got {parser.navigation_count}"
        )
    for href, attributes in EXPECTED_LINKS.items():
        matches = [link for link in parser.links if link.get("href") == href]
        if len(matches) != 1:
            raise RuntimeError(f"{path}: expected exactly one link to {href}")
        match = matches[0]
        for key, expected in attributes.items():
            if key == "rel":
                if expected not in normalized_rel(match.get(key, "")):
                    raise RuntimeError(f"{path}: {href} lacks rel={expected}")
            elif key == "class":
                if expected not in match.get(key, "").split():
                    raise RuntimeError(f"{path}: {href} lacks class={expected}")
            elif match.get(key) != expected:
                raise RuntimeError(f"{path}: {href} lacks {key}={expected}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_READER_ROOT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--no-write", action="store_true")
    arguments = parser.parse_args()

    reader_root = arguments.root.resolve()
    html_files = sorted(reader_root.rglob("*.html"))
    if len(html_files) != 84:
        raise RuntimeError(f"Expected 84 published HTML files, got {len(html_files)}")
    inventory_lines: list[str] = []
    total_bytes = 0
    for path in html_files:
        validate_page(path)
        data = path.read_bytes()
        relative = path.relative_to(reader_root).as_posix()
        total_bytes += len(data)
        inventory_lines.append(f"{relative}\t{len(data)}\t{sha256(data)}\n")

    receipt = {
        "schema": "program-reader-navigation-validation/1",
        "status": "pass",
        "course_id": "A10",
        "content_language": "en",
        "reader_root": str(reader_root),
        "html_files": len(html_files),
        "html_bytes": total_bytes,
        "html_inventory_sha256": sha256("".join(inventory_lines).encode("utf-8")),
        "required_links": sorted(EXPECTED_LINKS),
        "navigation_instances_per_page": 1,
        "credentials_recorded": False,
    }
    data = stable_json(receipt)
    if not arguments.no_write:
        target = arguments.receipt.resolve()
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError(f"Refusing to replace different receipt bytes: {target}")
        if not target.exists():
            target.write_bytes(data)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    print(f"Receipt {len(data):,} bytes SHA-256 {sha256(data)}")


if __name__ == "__main__":
    main()
