#!/usr/bin/env python3
"""Build and validate the original-English Elementary Algebra 2e HTML mirror.

The original collection is the sole module-order authority. Assets are copied
only when referenced by one of those modules. The build is deliberately local,
offline, timestamp-free, and fail-closed.
"""

from __future__ import annotations

import hashlib
import csv
import io
import json
import os
import platform
import re
import shutil
import sys
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import unquote, urlsplit

import lxml
from lxml import etree, html


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT
COLLECTION_PATH = ROOT / "collections" / "elementary-algebra-2e.collection.xml"
MODULES_ROOT = ROOT / "modules"
MEDIA_ROOT = ROOT / "media"
CSS_SOURCE = ROOT / "scripts" / "reader-id.css"
FINAL_OUTPUT_ROOT = ROOT / "output" / "html-en"
# Build and validate away from the published reader. The fixed sibling staging
# name makes the publication boundary auditable and keeps every mutation inside
# this lane's exact output directory. Published readers are immutable: this
# builder never moves, replaces, or deletes an existing final tree.
OUTPUT_ROOT = ROOT / "output" / ".html-en.staging"
OUTPUT_MODULES = OUTPUT_ROOT / "modules"
OUTPUT_MEDIA = OUTPUT_ROOT / "media"
OUTPUT_CSS = OUTPUT_ROOT / "reader-id.css"
MANIFEST_PATH = OUTPUT_ROOT / "volume.manifest.json"
STAGING_OWNED_BY_PROCESS = False
PENDING_PUBLICATION_FINGERPRINT: tuple[tuple[str, int, str], ...] | None = None
PENDING_PUBLICATION_RESULT: dict[str, object] | None = None

EXPECTED_MODULES = 82
EXPECTED_CHAPTERS = 10
EXPECTED_IMAGE_OCCURRENCES = 4_024
EXPECTED_UNIQUE_ASSETS = 4_018
EXPECTED_UNIQUE_ASSET_BYTES = 194_271_847
EXPECTED_ASSET_MANIFEST_BYTES = 744_894
EXPECTED_ASSET_MANIFEST_SHA256 = (
    "19e26c86ccbffa9b7ca2cc63211eef7e7ed307cc601b654c3feb06384a35bcc8"
)
EDITION_NOTICE_TEXT = (
    "Original English text by OpenStax and its contributors, presented in an "
    "unofficial program-generated HTML reader. This is not a new translation. "
    "OpenStax, Rice University and the authors do not sponsor or endorse this "
    "mirror. The original website remains available for updates and services."
)
ORIGINAL_WEBSITE = "https://openstax.org/details/books/elementary-algebra-2e"
PROGRAM_WEBSITE = "https://kokunoyumeto.github.io/program-matematika-indonesia/en/"
SOURCE_REVISION = "38cae454e644abf9f0a623e876994553881597c9"
AUTHORITY_HASHES = {
    "collections/elementary-algebra-2e.collection.xml": "5fdc03ab9e6ee7327be72f7e0a17c4d884e65f4a8081a0b2a06dbdb1392bda72",
    "authority/source-manifest.tsv": "59816c6eba9ea0a3efb2128c8924119f31175aa9bffe5d29dc57d4be84e410de",
    "authority/source-package-manifest.json": "74025f1cad1a97d6b81ee3120592380245c5c415b568440743aff87cebec6545",
    "authority/original-assets.tsv": "19e26c86ccbffa9b7ca2cc63211eef7e7ed307cc601b654c3feb06384a35bcc8",
    "authority/original-rights-summary.json": "b1bea405ab92be9ccec599616a15dee3e6a102c22d6226f693d0f50a93334083",
    "authority/provenance/RIGHTS_FREEZE_RECEIPT_20260829.json": "090b42fbe2b262471ac15adbc27e958155f0804c45b8447bef78ce7188dbb8e4",
    "LICENSE": "ab1a44bbba58252630134574d7b2534813339240eb645825ffcc2487dbe8114a",
}

CNXML_NS = "http://cnx.rice.edu/cnxml"
COLLXML_NS = "http://cnx.rice.edu/collxml"
MDML_NS = "http://cnx.rice.edu/mdml"
MATHML_NS = "http://www.w3.org/1998/Math/MathML"
XML_NS = "http://www.w3.org/XML/1998/namespace"

XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    remove_blank_text=False,
    remove_comments=True,
    remove_pis=True,
    huge_tree=True,
)

BLOCK_CHILDREN = {
    "definition",
    "equation",
    "example",
    "exercise",
    "figure",
    "glossary",
    "list",
    "note",
    "section",
    "table",
}

SEMANTIC_CONTAINERS = {
    "definition",
    "example",
    "exercise",
    "glossary",
    "note",
}

COUNT_CLASSES = {
    "exercise": "cnxml-exercise",
    "figure": "cnxml-figure",
    "media": "cnxml-media",
    "problem": "cnxml-problem",
    "solution": "cnxml-solution",
    "table": "cnxml-table",
    "list": "cnxml-list",
}


def fail(message: str) -> "NoReturn":
    raise RuntimeError(message)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def namespace(tag: str) -> str | None:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_is_link_or_junction(path: Path) -> bool:
    junction_check = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(junction_check and junction_check())


def stable_json_bytes(payload: object, *, pretty: bool = True) -> bytes:
    if pretty:
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    else:
        text = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return (text + "\n").encode("utf-8")


def write_bytes(path: Path, data: bytes) -> dict[str, object]:
    resolved_root = OUTPUT_ROOT.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError(f"Generated path escapes staging root: {path}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
    return {
        "path": path.relative_to(OUTPUT_ROOT).as_posix(),
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def parse_xml(path: Path) -> etree._Element:
    return etree.parse(str(path), XML_PARSER).getroot()


def source_title(root: etree._Element) -> str:
    for child in root:
        if child.tag == f"{{{CNXML_NS}}}title":
            return "".join(child.itertext()).strip()
    return "Untitled module"


def validate_module_namespace_topology(
    root: etree._Element,
    module_id: str,
    metadata: etree._Element,
) -> None:
    """Reject namespace confusion while allowing foreign islands inside MathML."""
    metadata_nodes = set(metadata.iter())
    for element in root.iter():
        tag = local_name(element.tag)
        uri = namespace(element.tag)
        ancestors = list(element.iterancestors())
        inside_mathml = any(namespace(ancestor.tag) == MATHML_NS for ancestor in ancestors)
        inside_abstract = any(
            ancestor.tag == f"{{{MDML_NS}}}abstract" for ancestor in ancestors
        )

        if uri not in {CNXML_NS, MDML_NS, MATHML_NS} and not inside_mathml:
            fail(
                f"Module {module_id} contains unsupported element namespace "
                f"{uri!r} on <{tag}>"
            )
        if element in metadata_nodes and element is not metadata:
            if uri == CNXML_NS and not inside_abstract:
                fail(f"Module {module_id} has CNXML content in metadata outside abstract")
            if uri not in {CNXML_NS, MDML_NS, MATHML_NS} and not inside_mathml:
                fail(f"Module {module_id} has unsupported metadata namespace on <{tag}>")
        elif uri == MDML_NS:
            fail(f"Module {module_id} has MDML element outside direct metadata")

        if tag == "metadata" and element is not metadata:
            fail(f"Module {module_id} has an extra metadata element")
        if tag == "abstract" and element.tag != f"{{{MDML_NS}}}abstract":
            fail(f"Module {module_id} has abstract outside the MDML namespace")
        if (
            element.tag == f"{{{MDML_NS}}}abstract"
            and element.getparent() is not metadata
        ):
            fail(f"Module {module_id} has abstract outside direct metadata")
        if tag == "uuid" and element.tag != f"{{{MDML_NS}}}uuid":
            fail(f"Module {module_id} has uuid outside the MDML namespace")
        if element.tag in {
            f"{{{MDML_NS}}}content-id",
            f"{{{MDML_NS}}}uuid",
        } and element.getparent() is not metadata:
            fail(f"Module {module_id} has {tag} outside direct metadata")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_-]+", "-", value.strip()).strip("-").lower()
    return slug or "value"


def resolve_media_reference(
    module_id: str,
    module_directory: Path,
    raw_src: str,
) -> tuple[Path, Path, Path]:
    """Admit one local media URI before any path-dependent filesystem probe."""

    parts = urlsplit(raw_src)
    if parts.scheme or parts.netloc or raw_src.startswith("//"):
        fail(f"Remote media source is forbidden: {module_id}: {raw_src}")
    try:
        decoded = unquote(parts.path, errors="strict")
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            f"Media source is not valid UTF-8 percent encoding: {module_id}: {raw_src}"
        ) from exc
    if not decoded or "\x00" in decoded:
        fail(f"Invalid empty or NUL-containing media path: {module_id}: {raw_src}")

    # Perform all URI-controlled lexical checks before resolve(), is_file(), or
    # read_bytes(). PureWindowsPath catches drive-relative, rooted, UNC, and
    # device paths even when a forward-slash spelling is supplied on Windows.
    windows_path = PureWindowsPath(decoded)
    posix_path = PurePosixPath(decoded.replace("\\", "/"))
    if (
        windows_path.drive
        or windows_path.root
        or windows_path.is_absolute()
        or posix_path.is_absolute()
    ):
        fail(f"Absolute, rooted, drive, or UNC media path is forbidden: {module_id}: {raw_src}")

    logical_media_root = Path(os.path.abspath(MEDIA_ROOT))
    logical_module_directory = Path(os.path.abspath(module_directory))
    logical_path = Path(os.path.abspath(logical_module_directory / decoded))
    try:
        logical_path.relative_to(logical_media_root)
    except ValueError as exc:
        raise RuntimeError(
            f"Media path lexically escapes media root: {module_id}: {raw_src} -> {logical_path}"
        ) from exc

    # Lexical admission is complete. Resolve only now, then retain the physical
    # containment gate so links and junctions cannot redirect an admitted path
    # outside this mirror or its media tree.
    resolved_root = ROOT.resolve(strict=True)
    resolved_media_root = logical_media_root.resolve(strict=True)
    try:
        resolved_media_root.relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError(
            f"Media root resolves outside the mirror: {logical_media_root}"
        ) from exc
    try:
        resolved_path = logical_path.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(
            f"Missing referenced asset: {module_id}: {raw_src}"
        ) from exc
    try:
        media_relative = resolved_path.relative_to(resolved_media_root)
    except ValueError as exc:
        raise RuntimeError(
            f"Asset resolves outside media root: {module_id}: {raw_src} -> {resolved_path}"
        ) from exc
    if not resolved_path.is_file():
        fail(f"Missing referenced asset: {module_id}: {raw_src}")
    return logical_path, resolved_path, media_relative


def append_text(parent: etree._Element, text: str | None) -> None:
    if not text:
        return
    if len(parent):
        parent[-1].tail = (parent[-1].tail or "") + text
    else:
        parent.text = (parent.text or "") + text


def add_classes(out: etree._Element, base: str, source: etree._Element) -> None:
    values = [base]
    raw = source.get("class")
    if raw:
        values.extend(f"source-{safe_slug(token)}" for token in raw.split())
    out.set("class", " ".join(dict.fromkeys(values)))


def abstract_has_reader_content(node: etree._Element) -> bool:
    # Any child can be visibly meaningful even without direct text (newline,
    # image, MathML, and a child's nonblank tail are all examples).
    return bool((node.text or "").strip() or len(node))


def visible_source_coverage(root: etree._Element) -> dict[str, object]:
    """Describe every reader-visible source node and nonblank text slot.

    Metadata is non-reader content except for its abstract. Identifiers are
    represented by the surrounding module/manifest rather than visible HTML.
    The resulting signature is independent of the HTML representation and is
    used by Renderer to prove that no visible source node or prose slot was
    silently skipped.
    """

    ordinals = {node: index for index, node in enumerate(root.iter())}
    node_rows: list[tuple[int, str, str, str]] = []
    text_rows: list[tuple[int, str, int, str]] = []

    def add_text(node: etree._Element, slot: str, value: str | None) -> None:
        if value is None or not value.strip():
            return
        data = value.encode("utf-8")
        text_rows.append((ordinals[node], slot, len(data), sha256_bytes(data)))

    def visit(node: etree._Element) -> None:
        tag = local_name(node.tag)
        if node.tag in {
            f"{{{CNXML_NS}}}metadata",
            f"{{{MDML_NS}}}content-id",
            f"{{{MDML_NS}}}uuid",
        }:
            return
        if node.tag == f"{{{MDML_NS}}}abstract" and not abstract_has_reader_content(node):
            return
        node_rows.append(
            (
                ordinals[node],
                namespace(node.tag) or "",
                tag,
                node.get("id", ""),
            )
        )
        add_text(node, "text", node.text)
        for child in node:
            visit(child)
            add_text(child, "tail", child.tail)

    node_rows.append((ordinals[root], namespace(root.tag) or "", local_name(root.tag), root.get("id", "")))
    add_text(root, "text", root.text)
    for child in root:
        if child.tag == f"{{{CNXML_NS}}}metadata":
            for metadata_child in child:
                if metadata_child.tag == f"{{{MDML_NS}}}abstract":
                    visit(metadata_child)
        else:
            visit(child)
        add_text(child, "tail", child.tail)

    node_stream = "".join(
        f"{ordinal}\t{uri}\t{tag}\t{native_id}\n"
        for ordinal, uri, tag, native_id in node_rows
    ).encode("utf-8")
    text_stream = "".join(
        f"{ordinal}\t{slot}\t{size}\t{digest}\n"
        for ordinal, slot, size, digest in text_rows
    ).encode("utf-8")
    return {
        "ordinals": ordinals,
        "node_rows": tuple(node_rows),
        "text_rows": tuple(text_rows),
        "node_count": len(node_rows),
        "text_slot_count": len(text_rows),
        "node_signature_sha256": sha256_bytes(node_stream),
        "text_signature_sha256": sha256_bytes(text_stream),
    }


def _declared_namespace(node: etree._Element, prefix: str | None) -> str | None:
    if prefix == "xml":
        return XML_NS
    current: etree._Element | None = node
    attribute = "xmlns" if prefix is None else f"xmlns:{prefix}"
    while current is not None:
        value = current.get(attribute)
        if value is not None:
            return value
        if prefix in current.nsmap:
            return current.nsmap[prefix] or ""
        current = current.getparent()
    return None


def _expanded_attribute_name(node: etree._Element, key: str) -> tuple[str, str] | None:
    if key == "xmlns" or key.startswith("xmlns:"):
        return None
    if key.startswith("{"):
        uri, name = key[1:].split("}", 1)
        return (uri, name)
    if ":" in key:
        prefix, name = key.split(":", 1)
        uri = _declared_namespace(node, prefix)
        return (uri or f"unresolved-prefix:{prefix}", name)
    return ("", key)


def _effective_element_namespace(node: etree._Element) -> str:
    explicit = namespace(node.tag)
    if explicit:
        return explicit
    return _declared_namespace(node, None) or ""


def _expanded_element_name(node: etree._Element) -> tuple[str, str]:
    tag = node.tag
    if tag.startswith("{"):
        uri, name = tag[1:].split("}", 1)
        return (uri, name)
    if ":" in tag:
        prefix, name = tag.split(":", 1)
        uri = _declared_namespace(node, prefix)
        return (uri if uri is not None else f"unresolved-prefix:{prefix}", name)
    return (_declared_namespace(node, None) or "", tag)


class Renderer:
    def __init__(self, module_id: str, reference_labels: dict[tuple[str, str], str],
                 titles: dict[str, str], *, print_mode: bool) -> None:
        self.module_id = module_id
        self.reference_labels = reference_labels
        self.titles = titles
        self.print_mode = print_mode
        self._coverage: dict[str, object] | None = None
        self._copied_nodes: Counter[int] = Counter()
        self._copied_text: Counter[tuple[int, str, int, str]] = Counter()
        self.coverage_result: dict[str, object] | None = None

    def begin_coverage(self, root: etree._Element) -> None:
        self._coverage = visible_source_coverage(root)
        self._copied_nodes.clear()
        self._copied_text.clear()
        self.coverage_result = None

    def mark_node(self, source: etree._Element) -> None:
        if self._coverage is None:
            fail(f"Coverage was not initialized for {self.module_id}")
        ordinal = self._coverage["ordinals"].get(source)
        if ordinal is None:
            fail(f"Rendered node is outside source coverage for {self.module_id}")
        self._copied_nodes[ordinal] += 1

    def append_source_text(
        self,
        parent: etree._Element,
        source: etree._Element,
        slot: str,
    ) -> None:
        value = source.text if slot == "text" else source.tail
        append_text(parent, value)
        self.mark_source_text(source, slot, value)

    def mark_source_text(
        self, source: etree._Element, slot: str, value: str | None
    ) -> None:
        if value is None or not value.strip():
            return
        if self._coverage is None:
            fail(f"Coverage was not initialized for {self.module_id}")
        ordinal = self._coverage["ordinals"].get(source)
        if ordinal is None:
            fail(f"Copied text is outside source coverage for {self.module_id}")
        data = value.encode("utf-8")
        self._copied_text[(ordinal, slot, len(data), sha256_bytes(data))] += 1

    def finish_coverage(self) -> None:
        if self._coverage is None:
            fail(f"Coverage was not initialized for {self.module_id}")
        expected_nodes = Counter(row[0] for row in self._coverage["node_rows"])
        expected_text = Counter(self._coverage["text_rows"])
        if self._copied_nodes != expected_nodes:
            fail(
                f"Visible source-node coverage mismatch in {self.module_id}: "
                f"expected={expected_nodes} actual={self._copied_nodes}"
            )
        if self._copied_text != expected_text:
            fail(
                f"Visible source-text coverage mismatch in {self.module_id}: "
                f"expected={expected_text} actual={self._copied_text}"
            )
        self.coverage_result = {
            key: self._coverage[key]
            for key in (
                "node_count",
                "text_slot_count",
                "node_signature_sha256",
                "text_signature_sha256",
            )
        }


    def output_id(self, native_id: str) -> str:
        if self.print_mode:
            return f"{self.module_id}--{native_id}"
        return native_id

    def copy_common(self, source: etree._Element, out: etree._Element) -> None:
        if source.get("id"):
            out.set("id", self.output_id(source.get("id")))
        for key, value in source.attrib.items():
            lname = local_name(key)
            if lname.startswith("aria-"):
                out.set(lname, value)

    def child_level(self, parent_tag: str, child_tag: str, level: int) -> int:
        if child_tag == "section" and parent_tag == "section":
            return min(level + 1, 6)
        if child_tag in SEMANTIC_CONTAINERS:
            return min(level + 1, 6)
        return level

    def copy_children(
        self,
        source: etree._Element,
        out: etree._Element,
        *,
        title_level: int,
    ) -> None:
        self.append_source_text(out, source, "text")
        parent_tag = local_name(source.tag)
        for child in source:
            child_tag = local_name(child.tag)
            rendered = self.render_node(
                child,
                title_level=self.child_level(parent_tag, child_tag, title_level),
            )
            nodes = [] if rendered is None else rendered if isinstance(rendered, list) else [rendered]
            for node in nodes:
                out.append(node)
            self.append_source_text(out, child, "tail")

    def clone_math(self, source: etree._Element, *, root: bool = True) -> etree._Element:
        # HTML5 recognizes unprefixed MathML integration points. Element names,
        # expanded attribute names, text, and child order remain exact; only the
        # source element prefix is normalized to the default MathML namespace.
        if not root:
            self.mark_node(source)
        source_namespace = namespace(source.tag)
        if root:
            if source_namespace != MATHML_NS:
                fail(f"MathML root has unexpected namespace in {self.module_id}")
            out = etree.Element(local_name(source.tag), nsmap={None: MATHML_NS})
        elif source_namespace == MATHML_NS:
            out = etree.Element(local_name(source.tag))
        elif source_namespace is None:
            # Preserve an explicit xmlns="" boundary beneath default MathML.
            out = etree.Element(local_name(source.tag), nsmap={None: ""})
        else:
            out = etree.Element(f"{{{source_namespace}}}{local_name(source.tag)}")
        for key, value in source.attrib.items():
            if key == "id":
                out.set(key, self.output_id(value))
            else:
                out.set(key, value)
        out.text = source.text
        self.mark_source_text(source, "text", source.text)
        for child in source:
            cloned = self.clone_math(child, root=False)
            cloned.tail = child.tail
            self.mark_source_text(child, "tail", child.tail)
            out.append(cloned)
        return out

    def render_image(self, source: etree._Element, *, alt: str) -> etree._Element:
        image = etree.Element("img")
        raw_src = source.get("src")
        if raw_src is None:
            fail(f"Image without src in {self.module_id}")
        if self.print_mode:
            _, _, rel = resolve_media_reference(
                self.module_id,
                MODULES_ROOT / self.module_id,
                raw_src,
            )
            image.set("src", f"media/{rel.as_posix()}")
        else:
            image.set("src", raw_src.replace("\\", "/"))
            image.set("loading", "lazy")
            image.set("decoding", "async")
        image.set("alt", alt)
        if source.get("mime-type"):
            image.set("data-mime-type", source.get("mime-type"))
        return image

    def rewrite_link(self, source: etree._Element) -> str:
        url = source.get("url")
        if url:
            return url
        document = source.get("document")
        target_id = source.get("target-id")
        if self.print_mode:
            target_module = document or self.module_id
            if target_id:
                return f"#{target_module}--{target_id}"
            if document:
                return f"#module-{document}"
            return "#"
        if document:
            if document == self.module_id and target_id:
                return f"#{target_id}"
            href = f"../{document}/index.html"
            return f"{href}#{target_id}" if target_id else href
        if target_id:
            return f"#{target_id}"
        return "#"

    def render_media(self, source: etree._Element, *, title_level: int) -> etree._Element:
        wrapper = etree.Element("span")
        add_classes(wrapper, "cnxml-media", source)
        self.copy_common(source, wrapper)
        alt = source.get("alt", "")
        self.append_source_text(wrapper, source, "text")
        for child in source:
            if child.tag == f"{{{CNXML_NS}}}image":
                self.mark_node(child)
                wrapper.append(self.render_image(child, alt=alt))
            else:
                rendered = self.render_node(child, title_level=title_level)
                if rendered is not None:
                    for node in rendered if isinstance(rendered, list) else [rendered]:
                        wrapper.append(node)
            self.append_source_text(wrapper, child, "tail")
        return wrapper

    def render_table(self, source: etree._Element, *, title_level: int) -> etree._Element:
        scroll = etree.Element("div", {"class": "table-scroll", "tabindex": "0"})
        table = etree.SubElement(scroll, "table")
        add_classes(table, "cnxml-table", source)
        self.copy_common(source, table)
        summary_text = source.get("summary")
        if summary_text:
            table.set("data-cnxml-summary", summary_text)
            if not table.get("aria-label"):
                table.set("aria-label", summary_text)

        # CNXML tables use direct label/title children rather than HTML's
        # caption shape. Consume every such node exactly once. Empty labels mean
        # "no generated label" and therefore need no empty visible caption;
        # nonempty label/title/caption content is represented inside one semantic
        # HTML caption in source order.
        heading_sources = [
            child
            for child in source
            if local_name(child.tag) in {"label", "title", "caption"}
        ]
        source_caption_visible = bool((source.text or "").strip()) or any(
            abstract_has_reader_content(child)
            or child.get("id")
            or any(local_name(key).startswith("aria-") for key in child.attrib)
            or bool((child.tail or "").strip())
            for child in heading_sources
        )
        caption = None
        if source_caption_visible:
            caption = etree.SubElement(table, "caption")
            self.append_source_text(caption, source, "text")
        for heading_source in heading_sources:
            self.mark_node(heading_source)
            heading_visible = (
                abstract_has_reader_content(heading_source)
                or bool(heading_source.get("id"))
                or any(
                    local_name(key).startswith("aria-")
                    for key in heading_source.attrib
                )
            )
            if heading_visible:
                if caption is None:
                    caption = etree.SubElement(table, "caption")
                part_name = local_name(heading_source.tag)
                part = etree.SubElement(
                    caption,
                    "span",
                    {"class": f"cnxml-table-{safe_slug(part_name)}"},
                )
                self.copy_common(heading_source, part)
                self.copy_children(
                    heading_source,
                    part,
                    title_level=title_level,
                )
            if caption is not None:
                self.append_source_text(caption, heading_source, "tail")
            else:
                self.mark_source_text(
                    heading_source,
                    "tail",
                    heading_source.tail,
                )
        if caption is None and summary_text:
            caption = etree.SubElement(table, "caption", {"class": "sr-only"})
            caption.text = summary_text

        tgroups = [child for child in source if local_name(child.tag) == "tgroup"]
        if len(tgroups) > 1:
            fail(f"Table has multiple tgroup children in {self.module_id}")
        tgroup = tgroups[0] if tgroups else None
        if tgroup is None:
            for child in source:
                if child in heading_sources:
                    continue
                rendered = self.render_node(child, title_level=title_level)
                if rendered is not None:
                    for node in rendered if isinstance(rendered, list) else [rendered]:
                        table.append(node)
                self.append_source_text(table, child, "tail")
            return scroll

        unexpected_direct_children = [
            child
            for child in source
            if child not in heading_sources and child is not tgroup
        ]
        if unexpected_direct_children:
            fail(
                f"Unsupported direct table child in {self.module_id}: "
                f"{unexpected_direct_children[0].tag!r}"
            )

        self.mark_node(tgroup)
        colspecs = [c for c in tgroup if local_name(c.tag) == "colspec"]
        col_positions: dict[str, int] = {}
        if colspecs:
            colgroup = etree.SubElement(table, "colgroup")
            for ordinal, colspec in enumerate(colspecs, 1):
                self.mark_node(colspec)
                etree.SubElement(colgroup, "col")
                name = colspec.get("colname")
                if name:
                    col_positions[name] = int(colspec.get("colnum") or ordinal)

        for group_source in tgroup:
            group_name = local_name(group_source.tag)
            if group_name == "colspec":
                continue
            if group_name not in {"thead", "tbody"}:
                continue
            self.mark_node(group_source)
            group_out = etree.SubElement(table, group_name)
            for row_source in group_source:
                if local_name(row_source.tag) != "row":
                    continue
                self.mark_node(row_source)
                row_out = etree.SubElement(group_out, "tr")
                for entry_source in row_source:
                    if local_name(entry_source.tag) != "entry":
                        continue
                    self.mark_node(entry_source)
                    cell = etree.SubElement(row_out, "th" if group_name == "thead" else "td")
                    if group_name == "thead":
                        cell.set("scope", "col")
                    morerows = entry_source.get("morerows")
                    if morerows is not None:
                        cell.set("rowspan", str(int(morerows) + 1))
                    namest = entry_source.get("namest")
                    nameend = entry_source.get("nameend")
                    if namest and nameend and namest in col_positions and nameend in col_positions:
                        colspan = col_positions[nameend] - col_positions[namest] + 1
                        if colspan > 1:
                            cell.set("colspan", str(colspan))
                    styles = []
                    if entry_source.get("align"):
                        styles.append(f"text-align:{entry_source.get('align')}")
                    if entry_source.get("valign"):
                        styles.append(f"vertical-align:{entry_source.get('valign')}")
                    if styles:
                        cell.set("style", ";".join(styles))
                    self.copy_children(entry_source, cell, title_level=title_level)
        self.append_source_text(scroll, tgroup, "tail")
        return scroll

    def render_figure(self, source: etree._Element, *, title_level: int) -> etree._Element:
        out = etree.Element("figure")
        add_classes(out, "cnxml-figure", source)
        self.copy_common(source, out)
        self.append_source_text(out, source, "text")
        for child in source:
            if local_name(child.tag) == "caption":
                self.mark_node(child)
                rendered = etree.Element("figcaption")
                self.copy_children(child, rendered, title_level=title_level)
            else:
                rendered = self.render_node(child, title_level=title_level)
            if rendered is not None:
                for node in rendered if isinstance(rendered, list) else [rendered]:
                    out.append(node)
            self.append_source_text(out, child, "tail")
        return out

    def render_node(
        self,
        source: etree._Element,
        *,
        title_level: int,
    ) -> etree._Element | list[etree._Element] | None:
        tag = local_name(source.tag)
        if namespace(source.tag) == MATHML_NS:
            self.mark_node(source)
            return self.clone_math(source)
        if source.tag in {
            f"{{{CNXML_NS}}}metadata",
            f"{{{MDML_NS}}}content-id",
            f"{{{MDML_NS}}}uuid",
        }:
            return None
        if source.tag == f"{{{MDML_NS}}}abstract" and not abstract_has_reader_content(source):
            return None
        if source.tag != f"{{{MDML_NS}}}abstract" and namespace(source.tag) != CNXML_NS:
            fail(
                f"Unsupported reader element namespace {namespace(source.tag)!r} "
                f"on <{tag}> in {self.module_id}"
            )
        self.mark_node(source)
        if source.tag == f"{{{MDML_NS}}}abstract":
            out = etree.Element(
                "aside",
                {"class": "module-abstract", "aria-label": "Learning objectives"},
            )
            heading = etree.SubElement(out, f"h{max(2, min(title_level, 6))}")
            heading.text = "Learning Objectives"
            self.copy_children(source, out, title_level=min(title_level + 1, 6))
            return out
        if tag == "content":
            out = etree.Element("div")
            add_classes(out, "module-content", source)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "title":
            out = etree.Element(f"h{max(1, min(title_level, 6))}")
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "section":
            out = etree.Element("section")
            add_classes(out, "cnxml-section", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "para":
            has_block = any(local_name(child.tag) in BLOCK_CHILDREN for child in source)
            out = etree.Element("div" if has_block else "p")
            add_classes(out, "cnxml-para", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "emphasis":
            effect = source.get("effect")
            out = etree.Element("strong" if effect in {"bold", "strong"} else "span" if effect == "underline" else "em")
            if effect == "underline":
                out.set("class", "source-underline")
            elif effect and effect not in {"bold", "strong", "italics"}:
                out.set("data-cnxml-effect", effect)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "newline":
            return etree.Element("br")
        if tag == "space":
            raw_count = source.get("count", "1")
            if not raw_count.isdigit() or not (1 <= int(raw_count) <= 64):
                fail(f"Invalid CNXML space count {raw_count!r} in {self.module_id}")
            out = etree.Element(
                "span",
                {
                    "class": "cnxml-space",
                    "aria-hidden": "true",
                    "data-count": raw_count,
                },
            )
            out.text = "\u00a0" * int(raw_count)
            return out
        if tag == "list":
            ordered = bool(source.get("number-style")) or source.get("list-type") in {
                "enumerated",
                "numbered",
            }
            out = etree.Element("ol" if ordered else "ul")
            add_classes(out, "cnxml-list", source)
            self.copy_common(source, out)
            if source.get("number-style"):
                out.set("data-number-style", source.get("number-style"))
            if source.get("list-type"):
                out.set("data-list-type", source.get("list-type"))
            if source.get("bullet-style"):
                out.set("data-bullet-style", source.get("bullet-style"))
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "item":
            out = etree.Element("li")
            add_classes(out, "cnxml-item", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "table":
            return self.render_table(source, title_level=title_level)
        if tag == "figure":
            return self.render_figure(source, title_level=title_level)
        if tag == "media":
            return self.render_media(source, title_level=title_level)
        if tag == "image":
            # Images normally occur under media; retain a safe fallback.
            if source.tag != f"{{{CNXML_NS}}}image":
                fail(f"Unsupported non-CNXML image element in {self.module_id}")
            return self.render_image(source, alt=source.get("alt", ""))
        if tag == "link":
            out = etree.Element("a", href=self.rewrite_link(source))
            if source.get("url"):
                out.set("rel", "noopener noreferrer")
                out.set("referrerpolicy", "no-referrer")
            self.copy_children(source, out, title_level=title_level)
            if not "".join(source.itertext()).strip():
                target_module = source.get("document") or self.module_id
                target_id = source.get("target-id")
                label = self.reference_labels.get((target_module, target_id))
                if not label:
                    fail(f"Empty cross-reference has no visible target label in {self.module_id}")
                out.text = label + (f" in {self.titles[target_module]}" if target_module != self.module_id else "")
                out.set("data-generated-cross-reference-label", "true")
            return out
        if tag == "note":
            out = etree.Element("aside")
            add_classes(out, "cnxml-note", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "example":
            out = etree.Element("section")
            add_classes(out, "cnxml-example", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "exercise":
            out = etree.Element("section")
            add_classes(out, "cnxml-exercise", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "problem":
            out = etree.Element("div")
            add_classes(out, "cnxml-problem", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "solution":
            out = etree.Element("details")
            add_classes(out, "cnxml-solution", source)
            self.copy_common(source, out)
            if self.print_mode:
                out.set("open", "open")
            summary = etree.SubElement(out, "summary")
            summary.text = "Solution"
            body = etree.SubElement(out, "div", {"class": "solution-body"})
            self.copy_children(source, body, title_level=title_level)
            return out
        if tag == "equation":
            out = etree.Element("div")
            add_classes(out, "cnxml-equation", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "definition":
            out = etree.Element("section")
            add_classes(out, "cnxml-definition", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "meaning":
            out = etree.Element("div")
            add_classes(out, "cnxml-meaning", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "glossary":
            out = etree.Element("section", {"class": "cnxml-glossary"})
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "term":
            out = etree.Element("dfn")
            add_classes(out, "cnxml-term", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "span":
            out = etree.Element("span")
            add_classes(out, "cnxml-span", source)
            self.copy_common(source, out)
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "sup":
            out = etree.Element("sup")
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "sub":
            out = etree.Element("sub")
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "label":
            out = etree.Element("span", {"class": "cnxml-label"})
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag == "caption":
            out = etree.Element("div", {"class": "cnxml-caption"})
            self.copy_children(source, out, title_level=title_level)
            return out
        if tag in {"tgroup", "thead", "tbody", "row", "entry", "colspec"}:
            # These are handled by render_table. Keep a transparent fallback.
            holder = etree.Element("div", {"data-cnxml-tag": tag})
            self.copy_children(source, holder, title_level=title_level)
            return list(holder)

        fail(f"Unsupported CNXML element <{tag}> in {self.module_id}")

    def render_module_article(self, source_root: etree._Element) -> etree._Element:
        self.begin_coverage(source_root)
        article = etree.Element("article", {"class": "module"})
        article.set("data-module-id", self.module_id)
        if self.print_mode:
            article.set("id", f"module-{self.module_id}")
            article.set("class", "module print-module")
        self.mark_node(source_root)
        self.append_source_text(article, source_root, "text")
        for child in source_root:
            if child.tag == f"{{{CNXML_NS}}}metadata":
                rendered = [
                    self.render_node(node, title_level=2)
                    for node in child
                    if node.tag == f"{{{MDML_NS}}}abstract"
                ]
                rendered = [node for node in rendered if node is not None]
            elif child.tag == f"{{{CNXML_NS}}}title":
                rendered = self.render_node(child, title_level=1)
            elif child.tag == f"{{{CNXML_NS}}}content":
                rendered = self.render_node(child, title_level=2)
            else:
                rendered = self.render_node(child, title_level=2)
            if rendered is not None:
                for node in rendered if isinstance(rendered, list) else [rendered]:
                    article.append(node)
            self.append_source_text(article, child, "tail")
        self.finish_coverage()
        return article


def html_document(title: str, css_href: str, body: etree._Element) -> bytes:
    root = etree.Element("html", lang="en")
    head = etree.SubElement(root, "head")
    etree.SubElement(head, "meta", charset="utf-8")
    etree.SubElement(
        head,
        "meta",
        name="viewport",
        content="width=device-width, initial-scale=1",
    )
    etree.SubElement(head, "meta", name="referrer", content="no-referrer")
    etree.SubElement(head, "meta", name="description", content=f"{title}. Original English OpenStax content in a portable program-hosted reader, with a direct link to the publisher.")
    title_node = etree.SubElement(head, "title")
    title_node.text = title
    etree.SubElement(head, "link", rel="stylesheet", href=css_href)
    etree.SubElement(head, "link", rel="alternate", hreflang="en", href=ORIGINAL_WEBSITE)
    access = etree.Element("nav", {"class": "paired-access", "aria-label": "Book access and original publisher"})
    original = etree.SubElement(access, "a", href=ORIGINAL_WEBSITE, hreflang="en", **{"class": "original-source-link"})
    original.text = "Original OpenStax website ↗"
    program = etree.SubElement(access, "a", href=PROGRAM_WEBSITE)
    program.text = "Mathematics program"
    print_link = etree.SubElement(access, "a", href=css_href.replace("reader-id.css", "print.html"))
    print_link.text = "Whole-book reading / print view"
    if "print-view" in body.get("class", "").split():
        front = body[0]
        if front.get("class") != "print-front":
            fail("Print view has no front matter for paired access")
        front.insert(2, access)
    else:
        body.insert(1, access)
    root.append(body)
    serialized = etree.tostring(
        root,
        encoding="utf-8",
        method="html",
        pretty_print=True,
    )
    return b"<!doctype html>\n" + serialized


def module_navigation(
    refs: list[str],
    titles: dict[str, str],
    position: int,
) -> etree._Element:
    nav = etree.Element("nav", {"class": "module-nav", "aria-label": "Module navigation"})
    index_link = etree.SubElement(nav, "a", href="../../index.html", **{"class": "toc-link"})
    index_link.text = "Contents"
    if position > 0:
        previous = refs[position - 1]
        link = etree.SubElement(nav, "a", href=f"../{previous}/index.html", rel="prev")
        link.text = f"← {titles[previous]}"
    else:
        etree.SubElement(nav, "span", {"class": "nav-spacer", "aria-hidden": "true"})
    marker = etree.SubElement(nav, "span", **{"class": "module-position"})
    marker.text = f"Module {position + 1} of {len(refs)}"
    if position + 1 < len(refs):
        following = refs[position + 1]
        link = etree.SubElement(nav, "a", href=f"../{following}/index.html", rel="next")
        link.text = f"{titles[following]} →"
    else:
        etree.SubElement(nav, "span", {"class": "nav-spacer", "aria-hidden": "true"})
    return nav


def collection_title(collection: etree._Element) -> str:
    node = collection.find(f".//{{{MDML_NS}}}title")
    return (node.text or "Elementary Algebra 2e").strip() if node is not None else "Elementary Algebra 2e"


def collection_license(collection: etree._Element) -> tuple[str, str]:
    node = collection.find(f".//{{{MDML_NS}}}license")
    if node is None:
        return ("License not stated", "")
    return ((node.text or "").strip(), node.get("url", ""))


def collect_collection_modules(collection_content: etree._Element) -> list[etree._Element]:
    """Return modules from the exact rendered CollXML content topology."""
    if collection_content.tag != f"{{{COLLXML_NS}}}content":
        fail("Collection topology root is not CollXML content")
    modules: list[etree._Element] = []

    def visit_content(content: etree._Element) -> None:
        for child in content:
            if child.tag == f"{{{COLLXML_NS}}}module":
                modules.append(child)
                continue
            if child.tag != f"{{{COLLXML_NS}}}subcollection":
                fail(
                    "Unexpected element in CollXML content topology: "
                    f"{child.tag!r}"
                )
            nested_contents = [
                node
                for node in child
                if node.tag == f"{{{COLLXML_NS}}}content"
            ]
            titles = [
                node
                for node in child
                if local_name(node.tag) == "title"
                and namespace(node.tag) in {COLLXML_NS, MDML_NS}
            ]
            allowed = set(nested_contents + titles)
            if len(nested_contents) != 1 or len(titles) != 1 or any(
                node not in allowed for node in child
            ):
                fail("Malformed CollXML subcollection topology")
            visit_content(nested_contents[0])

    visit_content(collection_content)
    return modules


def build_toc_list(
    collection_node: etree._Element,
    module_titles: dict[str, str],
    *,
    print_mode: bool,
) -> etree._Element:
    listing = etree.Element("ol", {"class": "toc-list"})
    for child in collection_node:
        tag = local_name(child.tag)
        if tag == "module":
            module_id = child.get("document")
            item = etree.SubElement(listing, "li", {"class": "toc-module"})
            href = f"#module-{module_id}" if print_mode else f"modules/{module_id}/index.html"
            link = etree.SubElement(item, "a", href=href)
            link.text = module_titles[module_id]
        elif tag == "subcollection":
            item = etree.SubElement(listing, "li", {"class": "toc-chapter"})
            title_node = next((n for n in child if local_name(n.tag) == "title"), None)
            heading = etree.SubElement(item, "span", {"class": "toc-chapter-title"})
            heading.text = (
                "".join(title_node.itertext()).strip() if title_node is not None else "Chapter"
            )
            content_node = next((n for n in child if local_name(n.tag) == "content"), None)
            if content_node is not None:
                item.append(build_toc_list(content_node, module_titles, print_mode=print_mode))
    return listing


def edition_notice() -> etree._Element:
    notice = etree.Element(
        "aside",
        {
            "class": "edition-notice",
            "role": "note",
            "aria-label": "Edition status",
        },
    )
    notice.text = EDITION_NOTICE_TEXT
    return notice


def build_index(
    collection: etree._Element,
    collection_content: etree._Element,
    module_titles: dict[str, str],
) -> bytes:
    body = etree.Element("body")
    header = etree.SubElement(body, "header", {"class": "site-header"})
    header_inner = etree.SubElement(header, "div", {"class": "site-header-inner"})
    eyebrow = etree.SubElement(header_inner, "p", {"class": "eyebrow"})
    eyebrow.text = "OpenStax · Original English"
    heading = etree.SubElement(header_inner, "h1")
    heading.text = collection_title(collection)
    intro = etree.SubElement(header_inner, "p", {"class": "lede"})
    intro.text = (
        "Read the complete original English book in its source order. "
        "Chapters, exercises, answers and illustrations are included locally; "
        "external websites and publisher services require an internet connection."
    )
    body.append(edition_notice())
    main = etree.SubElement(body, "main", {"class": "page-shell toc-page"})
    toc_heading = etree.SubElement(main, "h2")
    toc_heading.text = "Contents"
    main.append(build_toc_list(collection_content, module_titles, print_mode=False))
    license_name, license_url = collection_license(collection)
    footer = etree.SubElement(body, "footer", {"class": "site-footer"})
    footer.text = "Original content: OpenStax, Rice University and the credited contributors. License: "
    if license_url:
        link = etree.SubElement(
            footer,
            "a",
            href=license_url,
            rel="license noopener noreferrer",
            referrerpolicy="no-referrer",
        )
        link.text = license_name
    else:
        append_text(footer, license_name)
    return html_document(collection_title(collection), "reader-id.css", body)


def build_module_page(
    module_id: str,
    source_root: etree._Element,
    refs: list[str],
    titles: dict[str, str],
    reference_labels: dict[tuple[str, str], str],
    position: int,
) -> bytes:
    body = etree.Element("body")
    header = etree.SubElement(body, "header", {"class": "compact-header"})
    home = etree.SubElement(header, "a", href="../../index.html")
    home.text = "Elementary Algebra 2e — Original English"
    body.append(edition_notice())
    shell = etree.SubElement(body, "div", {"class": "page-shell"})
    shell.append(module_navigation(refs, titles, position))
    main = etree.SubElement(shell, "main")
    main.append(Renderer(module_id, reference_labels, titles, print_mode=False).render_module_article(source_root))
    shell.append(module_navigation(refs, titles, position))
    return html_document(f"{titles[module_id]} — Elementary Algebra 2e", "../../reader-id.css", body)


def build_print_page(
    collection: etree._Element,
    collection_content: etree._Element,
    refs: list[str],
    roots: dict[str, etree._Element],
    titles: dict[str, str],
    reference_labels: dict[tuple[str, str], str],
) -> bytes:
    body = etree.Element("body", {"class": "print-view"})
    front = etree.SubElement(body, "section", {"class": "print-front"})
    heading = etree.SubElement(front, "h1")
    heading.text = collection_title(collection)
    subtitle = etree.SubElement(front, "p")
    subtitle.text = "Original English · Complete reading and print view"
    front.append(edition_notice())
    toc_heading = etree.SubElement(front, "h2")
    toc_heading.text = "Contents"
    front.append(build_toc_list(collection_content, titles, print_mode=True))
    for module_id in refs:
        body.append(Renderer(module_id, reference_labels, titles, print_mode=True).render_module_article(roots[module_id]))
    return html_document(
        f"{collection_title(collection)} — Print view",
        "reader-id.css",
        body,
    )


def canonical_asset_manifest_bytes(asset_manifest: list[dict[str, object]]) -> bytes:
    lines = ["source_path\tworkspace_path\tmime_type\tbytes\tsha256\toccurrences"]
    for record in sorted(asset_manifest, key=lambda item: str(item["raw_source_path"])):
        lines.append(
            "\t".join(
                (
                    str(record["raw_source_path"]),
                    str(record["workspace_path"]),
                    str(record["mime_type"]),
                    str(record["bytes"]),
                    str(record["sha256"]),
                    str(record["occurrences"]),
                )
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def add_payload(payloads: dict[str, bytes], relative: str, data: bytes) -> None:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or relative != posix.as_posix():
        fail(f"Unsafe generated reader path: {relative}")
    if relative in payloads:
        fail(f"Duplicate generated reader path: {relative}")
    payloads[relative] = data


def original_component_credits(roots: dict[str, etree._Element]) -> list[dict[str, object]]:
    """Verify and expose explicit original-side credit witnesses.

    The work-level license does not independently clear every component.  The
    complete 4,024-use uncertainty inventory is preserved in the accompanying
    rights summary; this function separately verifies the two captions with
    explicit third-party creator/platform credits against original English XML.
    """
    rights = json.loads((ROOT / "authority/original-rights-summary.json").read_bytes())
    result = []
    for component in rights["explicit_credit_witnesses"]:
        module_id = component["module_id"]
        root = roots[module_id]
        matching_figures = [
            figure for figure in root.iter(f"{{{CNXML_NS}}}figure")
            if figure.get("id") == component["figure_id"]
        ]
        expected_caption = " ".join(component["source_caption"].split())
        captions = [" ".join("".join(caption.itertext()).split())
                    for figure in matching_figures
                    for caption in figure.findall(f"{{{CNXML_NS}}}caption")]
        if captions != [expected_caption]:
            fail(f"Original component caption mismatch: {module_id} {component['asset_path']}")
        result.append({
            "module_id": module_id,
            "figure_id": component["figure_id"],
            "source_asset_path": component["asset_path"],
            "source_caption_text": component["source_caption"],
            "rights_id": component["rights_id"],
            "third_party_status": component["third_party_status"],
            "review_status": component["review_status"],
            "standalone_component_license_url_present": component[
                "source_credit_contains_standalone_component_license_url"
            ],
        })
    if len(result) != 2:
        fail("Original credited-component closure changed")
    return result


def cross_reference_labels(roots: dict[str, etree._Element]) -> dict[tuple[str, str], str]:
    labels = {}
    names = {
        "example": "Example",
        "exercise": "Exercise",
        "figure": "Figure",
        "note": "Note",
        "table": "Table",
    }
    for module_id, root in roots.items():
        counts = Counter()
        for element in root.iter():
            tag = local_name(element.tag)
            if tag not in names:
                continue
            counts[tag] += 1
            if element.get("id"):
                labels[(module_id, element.get("id"))] = f"{names[tag]} {counts[tag]}"
    return labels


def render_reader_payloads(
    collection: etree._Element,
    collection_content: etree._Element,
    refs: list[str],
    roots: dict[str, etree._Element],
    titles: dict[str, str],
    css_bytes: bytes,
    asset_payloads: dict[str, bytes],
    asset_manifest_tsv: bytes,
) -> dict[str, bytes]:
    """Render one complete deterministic reader into an in-memory file map."""

    payloads: dict[str, bytes] = {}
    reference_labels = cross_reference_labels(roots)
    add_payload(payloads, "reader-id.css", css_bytes)
    add_payload(
        payloads,
        "index.html",
        build_index(collection, collection_content, titles),
    )
    for index, module_id in enumerate(refs):
        add_payload(
            payloads,
            f"modules/{module_id}/index.html",
            build_module_page(module_id, roots[module_id], refs, titles, reference_labels, index),
        )
    add_payload(
        payloads,
        "print.html",
        build_print_page(collection, collection_content, refs, roots, titles, reference_labels),
    )
    for relative in sorted(asset_payloads):
        add_payload(payloads, relative, asset_payloads[relative])
    add_payload(payloads, "metadata/assets.tsv", asset_manifest_tsv)
    add_payload(payloads, "LICENSE.txt", (ROOT / "LICENSE").read_bytes())
    add_payload(payloads, "metadata/original-component-credits.json", stable_json_bytes({
        "components": original_component_credits(roots),
        "source_preface": "modules/m82630/index.html",
        "uncredited_art_attribution_from_preface": "Copyright Rice University, OpenStax, under CC BY-NC-SA 4.0 license.",
        "complete_component_status": json.loads(
            (ROOT / "authority/original-rights-summary.json").read_bytes()
        )["preserved_component_status"],
        "notice": "Specific captions, credits, limitations, and unresolved component-review states remain controlling. No component is relicensed by this inventory.",
    }))
    add_payload(payloads, "metadata/source-provenance.json", stable_json_bytes({
        "course_role": "A10", "content_language": "en", "original_language": "en",
        "title": "Elementary Algebra 2e", "original_website": ORIGINAL_WEBSITE,
        "authors": ["Lynn Marecek", "MaryAnne Anthony-Smith", "Andrea Honeycutt Mathis"],
        "publisher": "OpenStax, Rice University", "source_revision": SOURCE_REVISION,
        "source_repository": "https://github.com/openstax/osbooks-prealgebra-bundle",
        "source_authority_sha256": AUTHORITY_HASHES,
        "presentation_provenance": "OpenAI Codex gpt-5.6-sol, Ultra; original text retained, no translation performed",
        "indonesian_edition_repository": "https://github.com/KokunoYumeto/openstax-elementary-algebra-2e-id",
        "indonesian_edition_release": "https://github.com/KokunoYumeto/openstax-elementary-algebra-2e-id/releases/tag/v1.0.3",
        "indonesian_edition_doi": "https://doi.org/10.5281/zenodo.22236314",
        "native_module_ids": refs, "native_source_bytes_unchanged": True,
        "license": "CC-BY-NC-SA-4.0 with original component-specific credits retained",
        "offline": {"book_text_math_css_images": "included", "javascript_required": False,
                    "math_renderer": "native browser MathML", "external_websites_and_publisher_services": "require internet"},
        "limitations": ["Frozen source edition, not a live upstream mirror", "No instructor accounts or publisher service replication",
                        "No browser visual or assistive-technology certification claimed", "Per-unit cross-language alignment is not yet integrated",
                        "Component-level uncertainty remains explicit; inherited work licensing is not independent component clearance"],
    }))
    return payloads


def element_counts(root: etree._Element) -> dict[str, int]:
    names = [local_name(element.tag) for element in root.iter()]
    return {
        "math": names.count("math"),
        "exercise": names.count("exercise"),
        "problem": names.count("problem"),
        "solution": names.count("solution"),
        "table": names.count("table"),
        "figure": names.count("figure"),
        "media": names.count("media"),
        "list": names.count("list"),
    }


def math_signature(root: etree._Element, *, id_prefix: str | None = None) -> tuple:
    def signature(node: etree._Element) -> tuple:
        attributes = []
        for key, value in node.attrib.items():
            expanded = _expanded_attribute_name(node, key)
            if expanded is not None:
                if expanded == ("", "id") and id_prefix is not None:
                    value = f"{id_prefix}--{value}"
                attributes.append((expanded[0], expanded[1], value))
        element_namespace, element_name = _expanded_element_name(node)
        return (
            element_namespace,
            element_name,
            tuple(sorted(attributes)),
            node.text or "",
            tuple((signature(child), child.tail or "") for child in node),
        )

    return tuple(signature(node) for node in root.iter() if local_name(node.tag) == "math")


def serialized_html_math_signature(document: bytes) -> tuple:
    """Parse exact serialized MathML islands as XML, preserving case/QNames."""
    token_pattern = re.compile(rb"<(/?)math(?=[\s>])[^>]*>")
    stack: list[int] = []
    fragments: list[bytes] = []
    for match in token_pattern.finditer(document):
        closing = match.group(1) == b"/"
        if not closing:
            stack.append(match.start())
            continue
        if not stack:
            fail("Serialized HTML contains an unmatched </math> tag")
        start = stack.pop()
        if not stack:
            fragments.append(document[start : match.end()])
    if stack:
        fail("Serialized HTML contains an unclosed <math> tag")
    signatures: list[tuple] = []
    for fragment in fragments:
        try:
            root = etree.fromstring(fragment, parser=XML_PARSER)
        except etree.XMLSyntaxError as exc:
            raise RuntimeError("Serialized MathML island is not exact XML") from exc
        if root.tag != f"{{{MATHML_NS}}}math":
            fail(f"Serialized MathML island has unexpected root: {root.tag!r}")
        signatures.extend(math_signature(root))
    return tuple(signatures)


def html_count(document: etree._Element, key: str) -> int:
    if key == "math":
        return len(document.xpath("//*[local-name()='math']"))
    class_name = COUNT_CLASSES[key]
    return len(
        document.xpath(
            "//*[contains(concat(' ', normalize-space(@class), ' '), $needle)]",
            needle=f" {class_name} ",
        )
    )


def parse_html_file(path: Path) -> etree._Element:
    # libxml2's HTML parser predates HTML5 and labels valid elements such as
    # main/header/math as unknown when recover=False. Recovery here means
    # HTML5-compatible unknown-element acceptance, not silent source repair;
    # the independent ID/count/link/MathML gates below remain fail-closed.
    parser = html.HTMLParser(encoding="utf-8", recover=True)
    return html.fromstring(path.read_bytes(), parser=parser)


def validate_local_resources(html_paths: list[Path]) -> dict[str, object]:
    parsed = {path.resolve(): parse_html_file(path) for path in html_paths}
    output_root = OUTPUT_ROOT.resolve()
    ids = {
        path: {value for value in doc.xpath("//*[@id]/@id")}
        for path, doc in parsed.items()
    }
    unresolved_links: list[dict[str, str]] = []
    unresolved_resources: list[dict[str, str]] = []
    external_links = 0

    def confined_target(base: Path, raw_path: str) -> Path | None:
        # Reject lexical escapes (including drive/UNC paths) before resolve(),
        # is_dir(), or is_file() can touch an outside/network filesystem.
        candidate = Path(os.path.abspath(base / unquote(raw_path)))
        try:
            candidate.relative_to(output_root)
        except ValueError:
            return None
        try:
            resolved = candidate.resolve()
            resolved.relative_to(output_root)
        except (OSError, RuntimeError, ValueError):
            return None
        return resolved

    for path, document in parsed.items():
        for href in document.xpath("//a[@href]/@href"):
            parts = urlsplit(href)
            if parts.scheme in {"http", "https", "mailto", "tel"} or href.startswith("//"):
                external_links += 1
                continue
            if parts.scheme:
                unresolved_links.append(
                    {"from": path.relative_to(OUTPUT_ROOT).as_posix(), "href": href}
                )
                continue
            target_path = path if not parts.path else confined_target(path.parent, parts.path)
            if target_path is None:
                unresolved_links.append(
                    {"from": path.relative_to(OUTPUT_ROOT).as_posix(), "href": href}
                )
                continue
            if target_path.is_dir():
                target_path = (target_path / "index.html").resolve()
            try:
                target_path.relative_to(output_root)
            except ValueError:
                unresolved_links.append(
                    {"from": path.relative_to(OUTPUT_ROOT).as_posix(), "href": href}
                )
                continue
            if target_path not in parsed:
                unresolved_links.append(
                    {"from": path.relative_to(OUTPUT_ROOT).as_posix(), "href": href}
                )
                continue
            if parts.fragment and unquote(parts.fragment) not in ids[target_path]:
                unresolved_links.append(
                    {"from": path.relative_to(OUTPUT_ROOT).as_posix(), "href": href}
                )

        for value in document.xpath("//img[@src]/@src | //link[@rel='stylesheet']/@href"):
            parts = urlsplit(value)
            if parts.scheme or value.startswith("//"):
                unresolved_resources.append(
                    {"from": path.relative_to(OUTPUT_ROOT).as_posix(), "resource": value}
                )
                continue
            target = confined_target(path.parent, parts.path)
            if target is None:
                unresolved_resources.append(
                    {"from": path.relative_to(OUTPUT_ROOT).as_posix(), "resource": value}
                )
                continue
            if not target.is_file():
                unresolved_resources.append(
                    {"from": path.relative_to(OUTPUT_ROOT).as_posix(), "resource": value}
                )

    return {
        "html_files_parsed": len(parsed),
        "external_link_occurrences_not_network_checked": external_links,
        "unresolved_local_links_or_fragments": unresolved_links,
        "unresolved_local_resources": unresolved_resources,
    }


def select_render_sample(refs: list[str], metrics: dict[str, dict[str, int]]) -> list[str]:
    candidates = [
        refs[0],
        refs[2] if len(refs) > 2 else refs[1],
        max(refs, key=lambda ref: (metrics[ref]["media"], -refs.index(ref))),
        max(refs, key=lambda ref: (metrics[ref]["table"], -refs.index(ref))),
        max(refs, key=lambda ref: (metrics[ref]["math"], -refs.index(ref))),
        max(refs, key=lambda ref: (metrics[ref]["exercise"], -refs.index(ref))),
        refs[-1],
    ]
    selected: list[str] = []
    for candidate in candidates:
        if candidate not in selected:
            selected.append(candidate)
    for candidate in refs:
        if len(selected) == 7:
            break
        if candidate not in selected:
            selected.append(candidate)
    return selected[:7]


def assert_safe_output_roots() -> None:
    resolved_root = ROOT.resolve()
    output_parent = ROOT / "output"
    if output_parent.exists() and path_is_link_or_junction(output_parent):
        fail(f"Refusing to operate through a linked output parent: {output_parent}")
    if output_parent.exists() and output_parent.resolve() != resolved_root / "output":
        fail(f"Output parent resolves outside the mirror: {output_parent}")
    expected_paths = {
        FINAL_OUTPUT_ROOT: resolved_root / "output" / "html-en",
        OUTPUT_ROOT: resolved_root / "output" / ".html-en.staging",
    }
    for actual, expected in expected_paths.items():
        actual_lexical = Path(os.path.abspath(actual))
        if os.path.normcase(str(actual_lexical)) != os.path.normcase(str(expected)):
            fail(f"Unsafe output path: {actual}")
        if actual.exists() and path_is_link_or_junction(actual):
            fail(f"Refusing to operate on linked output path: {actual}")


def tree_fingerprint(root: Path) -> tuple[tuple[str, int, str], ...]:
    resolved_root = root.resolve()
    if not root.is_dir() or path_is_link_or_junction(root):
        fail(f"Output candidate is not an ordinary directory: {root}")
    rows: list[tuple[str, int, str]] = []

    def visit(directory: Path) -> None:
        with os.scandir(directory) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
        for entry in ordered:
            path = Path(entry.path)
            if entry.is_symlink() or path_is_link_or_junction(path):
                fail(f"Link or junction is forbidden in reader output: {path}")
            resolved = path.resolve()
            try:
                resolved.relative_to(resolved_root)
            except ValueError as exc:
                raise RuntimeError(f"Reader output escapes candidate root: {path}") from exc
            relative = path.relative_to(root).as_posix()
            if entry.is_dir(follow_symlinks=False):
                rows.append((relative, -1, "directory"))
                visit(path)
                continue
            if not entry.is_file(follow_symlinks=False):
                fail(f"Unsupported reader output entry: {path}")
            data = path.read_bytes()
            rows.append((relative, len(data), sha256_bytes(data)))

    visit(root)
    return tuple(sorted(rows))


def payload_fingerprint(payloads: dict[str, bytes]) -> tuple[tuple[str, int, str], ...]:
    directories: set[str] = set()
    for relative in payloads:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    rows = [(relative, -1, "directory") for relative in directories]
    rows.extend(
        (relative, len(payloads[relative]), sha256_bytes(payloads[relative]))
        for relative in payloads
    )
    return tuple(sorted(rows))


def fingerprint_sha(fingerprint: tuple[tuple[str, int, str], ...]) -> str:
    stream = "".join(
        f"{relative}\t{size}\t{digest}\n"
        for relative, size, digest in fingerprint
    ).encode("utf-8")
    return sha256_bytes(stream)


def remember_input(
    snapshot: dict[Path, dict[str, object]],
    path: Path,
    data: bytes,
    *,
    expected_resolved: Path | None = None,
) -> None:
    root_resolved = ROOT.resolve()
    logical = Path(os.path.abspath(path))
    resolved_before = logical.resolve(strict=True)
    observed_data = logical.read_bytes()
    resolved_after = logical.resolve(strict=True)
    if resolved_before != resolved_after:
        fail(f"Input target changed while being captured: {logical}")
    if expected_resolved is not None and resolved_before != expected_resolved:
        fail(f"Input target changed after discovery: {logical}")
    if observed_data != data:
        fail(f"Input bytes changed while being captured: {logical}")
    resolved = resolved_before
    record = {
        "path": logical.relative_to(root_resolved).as_posix(),
        "resolved_path": resolved.relative_to(root_resolved).as_posix(),
        "resolved_absolute": str(resolved),
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }
    previous = snapshot.get(logical)
    if previous is not None and previous != record:
        fail(f"Input changed during preflight: {record['path']}")
    snapshot[logical] = record


def verify_input_snapshot(snapshot: dict[Path, dict[str, object]]) -> None:
    drift: list[dict[str, object]] = []
    for path, expected in sorted(snapshot.items(), key=lambda item: item[1]["path"]):
        try:
            resolved_before = path.resolve(strict=True)
            data = path.read_bytes()
            resolved_after = path.resolve(strict=True)
        except OSError as exc:
            drift.append(
                {
                    "path": expected["path"],
                    "expected_bytes": expected["bytes"],
                    "expected_sha256": expected["sha256"],
                    "read_error": str(exc),
                }
            )
            continue
        expected_resolved = Path(str(expected["resolved_absolute"]))
        actual_bytes = len(data)
        actual_sha256 = sha256_bytes(data)
        if (
            resolved_before != expected_resolved
            or resolved_after != expected_resolved
            or actual_bytes != expected["bytes"]
            or actual_sha256 != expected["sha256"]
        ):
            drift.append(
                {
                    "path": expected["path"],
                    "expected_resolved_path": expected["resolved_path"],
                    "actual_resolved_path_before_read": str(resolved_before),
                    "actual_resolved_path_after_read": str(resolved_after),
                    "expected_bytes": expected["bytes"],
                    "actual_bytes": actual_bytes,
                    "expected_sha256": expected["sha256"],
                    "actual_sha256": actual_sha256,
                }
            )
    if drift:
        fail(
            "Build inputs changed after preflight; published reader preserved:\n"
            + json.dumps(drift, ensure_ascii=False, indent=2)
        )


def prepare_staging_root() -> None:
    global STAGING_OWNED_BY_PROCESS

    # This runs only after the complete source/module/asset preflight succeeds.
    # It never touches FINAL_OUTPUT_ROOT or a staging tree from another run.
    if FINAL_OUTPUT_ROOT.exists():
        fail(f"Published reader already exists; refusing overwrite: {FINAL_OUTPUT_ROOT}")
    if OUTPUT_ROOT.exists():
        fail(f"Stale staging tree requires manual review: {OUTPUT_ROOT}")
    OUTPUT_ROOT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir()
    STAGING_OWNED_BY_PROCESS = True


def cleanup_failed_staging() -> None:
    global STAGING_OWNED_BY_PROCESS

    # A failed parse/build/QA/input-rehash may discard only the exact staging
    # tree. An immutable published reader is never touched.
    assert_safe_output_roots()
    if STAGING_OWNED_BY_PROCESS and OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    STAGING_OWNED_BY_PROCESS = False


def publish_staged_output(
    candidate_fingerprint: tuple[tuple[str, int, str], ...]
) -> dict[str, object]:
    """Atomically install an immutable reader without overwriting any entry."""
    global PENDING_PUBLICATION_FINGERPRINT, STAGING_OWNED_BY_PROCESS

    assert_safe_output_roots()
    if not OUTPUT_ROOT.is_dir():
        fail(f"Validated staging reader is missing: {OUTPUT_ROOT}")
    if FINAL_OUTPUT_ROOT.exists():
        fail(f"Published reader appeared during build; refusing overwrite: {FINAL_OUTPUT_ROOT}")
    if OUTPUT_ROOT.parent.resolve() != FINAL_OUTPUT_ROOT.parent.resolve():
        fail("Staging and final reader paths are not same-directory siblings")
    if OUTPUT_ROOT.anchor.casefold() != FINAL_OUTPUT_ROOT.anchor.casefold():
        fail("Staging and final reader paths are not on the same volume")
    if os.name != "nt":
        fail("Atomic no-overwrite directory publication requires Windows rename semantics")

    PENDING_PUBLICATION_FINGERPRINT = candidate_fingerprint
    reconciled_ambiguous_success = False
    try:
        # On Windows os.rename refuses an existing destination. Because these
        # are sibling directories on one volume, success is one atomic namespace
        # transition and there is never a missing-old-reader interval.
        os.rename(OUTPUT_ROOT, FINAL_OUTPUT_ROOT)
        STAGING_OWNED_BY_PROCESS = False
        return {
            "publication_mode": "same_volume_atomic_no_overwrite_rename",
            "ambiguous_success_reconciled": reconciled_ambiguous_success,
        }
    except BaseException:
        # The rename may have completed immediately before an asynchronous
        # exception was delivered. Accept only the exact sealed candidate.
        try:
            reconciled_ambiguous_success = (
                not OUTPUT_ROOT.exists()
                and FINAL_OUTPUT_ROOT.is_dir()
                and tree_fingerprint(FINAL_OUTPUT_ROOT) == candidate_fingerprint
            )
        except BaseException:
            reconciled_ambiguous_success = False
        if not reconciled_ambiguous_success:
            # Keep the exact pending fingerprint available to main(); a
            # transient read error here must not prevent one outer reconciliation
            # attempt after a rename that actually completed.
            raise
        STAGING_OWNED_BY_PROCESS = False
        return {
            "publication_mode": "same_volume_atomic_no_overwrite_rename",
            "ambiguous_success_reconciled": reconciled_ambiguous_success,
        }


def recover_published_result_after_exception() -> dict[str, object] | None:
    """Reconcile an exception delivered after the atomic rename completed."""
    global STAGING_OWNED_BY_PROCESS

    if PENDING_PUBLICATION_FINGERPRINT is None or PENDING_PUBLICATION_RESULT is None:
        return None
    try:
        exact_final = (
            not OUTPUT_ROOT.exists()
            and FINAL_OUTPUT_ROOT.is_dir()
            and tree_fingerprint(FINAL_OUTPUT_ROOT) == PENDING_PUBLICATION_FINGERPRINT
        )
    except BaseException:
        return None
    if not exact_final:
        return None
    STAGING_OWNED_BY_PROCESS = False
    recovered = dict(PENDING_PUBLICATION_RESULT)
    recovered["publication"] = {
        "publication_mode": "same_volume_atomic_no_overwrite_rename",
        "ambiguous_success_reconciled": True,
    }
    return recovered


def build() -> dict[str, object]:
    global PENDING_PUBLICATION_FINGERPRINT, PENDING_PUBLICATION_RESULT

    PENDING_PUBLICATION_FINGERPRINT = None
    PENDING_PUBLICATION_RESULT = None
    assert_safe_output_roots()
    if not COLLECTION_PATH.is_file():
        fail(f"Missing original-English collection: {COLLECTION_PATH}")
    if not CSS_SOURCE.is_file():
        fail(f"Missing reader CSS: {CSS_SOURCE}")

    input_snapshot: dict[Path, dict[str, object]] = {}
    for relative, expected_sha in AUTHORITY_HASHES.items():
        authority_path = ROOT / relative
        authority_data = authority_path.read_bytes()
        if sha256_bytes(authority_data) != expected_sha:
            fail(f"Frozen authority mismatch: {relative}")
        remember_input(input_snapshot, authority_path, authority_data)
    source_bindings = list(csv.DictReader(io.StringIO((ROOT / "authority/source-manifest.tsv").read_text(encoding="utf-8")), delimiter="\t"))
    expected_sources = {row["module"]: row for row in source_bindings}
    script_path = Path(__file__).resolve()
    script_bytes = script_path.read_bytes()
    remember_input(input_snapshot, script_path, script_bytes)
    css_bytes = CSS_SOURCE.read_bytes()
    remember_input(input_snapshot, CSS_SOURCE, css_bytes)
    collection_bytes = COLLECTION_PATH.read_bytes()
    remember_input(input_snapshot, COLLECTION_PATH, collection_bytes)
    collection = etree.fromstring(collection_bytes, parser=XML_PARSER)
    if collection.tag != f"{{{COLLXML_NS}}}collection":
        fail(f"Original collection has unexpected root: {collection.tag!r}")
    if collection.get(f"{{{XML_NS}}}lang") != "en":
        fail("Original collection xml:lang is not en")
    collection_contents = [
        child for child in collection if child.tag == f"{{{COLLXML_NS}}}content"
    ]
    if len(collection_contents) != 1:
        fail(f"Collection must have exactly one CollXML content element, found {len(collection_contents)}")
    collection_content = collection_contents[0]
    foreign_module_elements = [
        element
        for element in collection.iter()
        if local_name(element.tag) == "module"
        and element.tag != f"{{{COLLXML_NS}}}module"
    ]
    if foreign_module_elements:
        fail("Collection contains a module element outside the CollXML namespace")
    topology_modules = collect_collection_modules(collection_content)
    all_collxml_modules = [
        element
        for element in collection.iter()
        if element.tag == f"{{{COLLXML_NS}}}module"
    ]
    if topology_modules != all_collxml_modules:
        fail("Collection contains a module outside the admitted content topology")
    refs = [
        element.get("document")
        for element in topology_modules
    ]
    if (
        len(refs) != EXPECTED_MODULES
        or len(set(refs)) != EXPECTED_MODULES
        or not all(isinstance(ref, str) and re.fullmatch(r"m\d+", ref) for ref in refs)
    ):
        fail(
            f"Expected {EXPECTED_MODULES} ordered unique safe module refs, "
            f"found {len(refs)}/{len(set(refs))}"
        )
    chapter_count = sum(
        1 for node in collection_content if node.tag == f"{{{COLLXML_NS}}}subcollection"
    )
    if chapter_count != EXPECTED_CHAPTERS:
        fail(f"Expected {EXPECTED_CHAPTERS} chapter subcollections, found {chapter_count}")
    if refs != [row["module"] for row in source_bindings] or len(expected_sources) != EXPECTED_MODULES:
        fail("Original manifest and collection module order differ")

    roots: dict[str, etree._Element] = {}
    titles: dict[str, str] = {}
    source_metrics: dict[str, dict[str, int]] = {}
    module_manifest: list[dict[str, object]] = []
    all_asset_paths: dict[Path, dict[str, object]] = {}
    asset_logical_paths: dict[Path, Path] = {}
    assets_by_raw_source: dict[str, dict[str, object]] = {}
    source_ids: dict[str, list[str]] = {}
    source_math_signatures: dict[str, tuple] = {}
    source_print_math_signatures: dict[str, tuple] = {}
    image_occurrences = 0

    for position, module_id in enumerate(refs, 1):
        module_path = MODULES_ROOT / module_id / "index.cnxml"
        if not module_path.is_file():
            fail(f"Missing module {position}: {module_path}")
        raw = module_path.read_bytes()
        binding = expected_sources[module_id]
        if len(raw) != int(binding["bytes"]) or sha256_bytes(raw) != binding["sha256"]:
            fail(f"Original source bytes differ from frozen authority: {module_id}")
        remember_input(input_snapshot, module_path, raw)
        source_root = etree.fromstring(raw, parser=XML_PARSER)
        if source_root.tag != f"{{{CNXML_NS}}}document":
            fail(f"Module {module_id} has unexpected root: {source_root.tag!r}")
        declared_module_locale = source_root.get(f"{{{XML_NS}}}lang")
        if declared_module_locale not in {None, "en"}:
            fail(
                f"Module {module_id} declares incompatible xml:lang "
                f"{declared_module_locale!r}"
            )
        metadata_nodes = [
            child for child in source_root if child.tag == f"{{{CNXML_NS}}}metadata"
        ]
        if len(metadata_nodes) != 1:
            fail(
                f"Module {module_id} must have exactly one direct CNXML metadata "
                f"element, found {len(metadata_nodes)}"
            )
        validate_module_namespace_topology(source_root, module_id, metadata_nodes[0])
        foreign_content_ids = [
            element
            for element in source_root.iter()
            if local_name(element.tag) == "content-id"
            and element.tag != f"{{{MDML_NS}}}content-id"
        ]
        if foreign_content_ids:
            fail(f"Module {module_id} has content-id outside the MDML namespace")
        all_mdml_content_ids = [
            element
            for element in source_root.iter()
            if element.tag == f"{{{MDML_NS}}}content-id"
        ]
        direct_content_ids = [
            element
            for element in metadata_nodes[0]
            if element.tag == f"{{{MDML_NS}}}content-id"
        ]
        if all_mdml_content_ids != direct_content_ids:
            fail(f"Module {module_id} has MDML content-id outside direct metadata")
        content_ids = [
            (element.text or "").strip()
            for element in direct_content_ids
        ]
        if content_ids != [module_id]:
            fail(f"Module {module_id} content-id mismatch: {content_ids!r}")
        roots[module_id] = source_root
        titles[module_id] = source_title(source_root)
        source_metrics[module_id] = element_counts(source_root)
        source_ids[module_id] = [
            element.get("id") for element in source_root.iter() if element.get("id")
        ]
        if len(source_ids[module_id]) != len(set(source_ids[module_id])):
            fail(f"Duplicate source IDs in {module_id}")
        source_math_signatures[module_id] = math_signature(source_root)
        source_print_math_signatures[module_id] = math_signature(
            source_root, id_prefix=module_id
        )
        coverage = visible_source_coverage(source_root)
        module_manifest.append(
            {
                "position": position,
                "module_id": module_id,
                "title": titles[module_id],
                "source_xml_lang": declared_module_locale,
                "effective_locale": "en",
                "source_path": module_path.relative_to(ROOT).as_posix(),
                "source_bytes": len(raw),
                "source_sha256": sha256_bytes(raw),
                "source_native_id_count": len(source_ids[module_id]),
                "source_counts": source_metrics[module_id],
                "reader_visible_node_count": coverage["node_count"],
                "reader_visible_text_slot_count": coverage["text_slot_count"],
                "reader_visible_node_signature_sha256": coverage[
                    "node_signature_sha256"
                ],
                "reader_visible_text_signature_sha256": coverage[
                    "text_signature_sha256"
                ],
            }
        )
        for element in source_root.iter():
            if element.tag != f"{{{CNXML_NS}}}image":
                if element.get("src") is not None:
                    fail(f"Unsupported non-image src attribute in {module_id}")
                continue
            raw_src = element.get("src")
            declared_mime_type = element.get("mime-type")
            # Preserve declarations as evidence but do not trust them as the
            # serving identity: this source has 2,545 JPG uses declared PNG and
            # one repeated JPG declared both ways.  Acquisition independently
            # verified every signature against the pinned media manifest.
            if declared_mime_type == "image/jpg":
                declared_mime_type = "image/jpeg"
            if not raw_src or not declared_mime_type:
                fail(f"Incomplete image identity in {module_id}")
            asset_logical_path, asset_path, media_relative = resolve_media_reference(
                module_id,
                module_path.parent,
                raw_src,
            )
            suffix = asset_path.suffix.casefold()
            mime_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
            }.get(suffix)
            if mime_type is None:
                fail(f"Unsupported original asset suffix for {raw_src}")
            existing_raw = assets_by_raw_source.get(raw_src)
            existing_path = all_asset_paths.get(asset_path)
            if existing_raw is None:
                if existing_path is not None:
                    fail(
                        f"Multiple CNXML source paths resolve to one asset: "
                        f"{existing_path['raw_source_path']!r}, {raw_src!r}"
                    )
                record = {
                    "raw_source_path": raw_src,
                    "source_path": asset_path.relative_to(ROOT).as_posix(),
                    "workspace_path": asset_path.relative_to(WORKSPACE_ROOT).as_posix(),
                    "output_path": (Path("media") / media_relative).as_posix(),
                    "mime_type": mime_type,
                    "declared_mime_types": [],
                    "modules": [],
                    "occurrences": 0,
                }
                assets_by_raw_source[raw_src] = record
                all_asset_paths[asset_path] = record
                asset_logical_paths[asset_path] = asset_logical_path
            else:
                record = existing_raw
                if (
                    existing_path is not record
                    or asset_logical_paths[asset_path] != asset_logical_path
                ):
                    fail(f"Conflicting repeated asset identity for {raw_src}")
            if declared_mime_type not in record["declared_mime_types"]:
                record["declared_mime_types"].append(declared_mime_type)
            record["occurrences"] += 1
            image_occurrences += 1
            if module_id not in record["modules"]:
                record["modules"].append(module_id)

    if image_occurrences != EXPECTED_IMAGE_OCCURRENCES:
        fail(
            f"Expected {EXPECTED_IMAGE_OCCURRENCES} image occurrences, "
            f"found {image_occurrences}"
        )
    if (
        len(all_asset_paths) != EXPECTED_UNIQUE_ASSETS
        or len(assets_by_raw_source) != EXPECTED_UNIQUE_ASSETS
    ):
        fail(
            f"Expected {EXPECTED_UNIQUE_ASSETS} unique referenced assets, "
            f"found {len(all_asset_paths)}/{len(assets_by_raw_source)}"
        )

    # Materialize every referenced input before staging begins.  Generated
    # assets use this admitted byte snapshot, then all live inputs are rehashed
    # immediately before publication.
    asset_bytes_by_path: dict[Path, bytes] = {}
    for source_path in sorted(all_asset_paths, key=lambda path: path.as_posix().casefold()):
        logical_path = asset_logical_paths[source_path]
        data = logical_path.read_bytes()
        remember_input(
            input_snapshot,
            logical_path,
            data,
            expected_resolved=source_path,
        )
        asset_bytes_by_path[source_path] = data

    asset_manifest: list[dict[str, object]] = []
    for source_path, record in sorted(
        all_asset_paths.items(), key=lambda pair: pair[1]["output_path"].casefold()
    ):
        data = asset_bytes_by_path[source_path]
        asset_manifest.append(
            {
                **record,
                "bytes": len(data),
                "sha256": sha256_bytes(data),
            }
        )

    asset_total_bytes = sum(record["bytes"] for record in asset_manifest)
    if asset_total_bytes != EXPECTED_UNIQUE_ASSET_BYTES:
        fail(
            f"Expected {EXPECTED_UNIQUE_ASSET_BYTES} referenced asset bytes, "
            f"found {asset_total_bytes}"
        )
    asset_manifest_tsv = canonical_asset_manifest_bytes(asset_manifest)
    asset_manifest_boundary = (
        len(asset_manifest_tsv),
        sha256_bytes(asset_manifest_tsv),
    )
    expected_asset_manifest_boundary = (
        EXPECTED_ASSET_MANIFEST_BYTES,
        EXPECTED_ASSET_MANIFEST_SHA256,
    )
    if asset_manifest_boundary != expected_asset_manifest_boundary:
        fail(
            f"Canonical asset manifest mismatch: expected "
            f"{expected_asset_manifest_boundary}, got {asset_manifest_boundary}"
        )

    # The complete source byte set is now resident in memory. Rehash it once
    # before the first render and again at the final publication boundary so a
    # mixed live-input snapshot can never be admitted silently.
    verify_input_snapshot(input_snapshot)

    asset_payloads = {
        str(record["output_path"]): asset_bytes_by_path[source_path]
        for source_path, record in all_asset_paths.items()
    }
    first_payloads = render_reader_payloads(
        collection,
        collection_content,
        refs,
        roots,
        titles,
        css_bytes,
        asset_payloads,
        asset_manifest_tsv,
    )

    prepare_staging_root()
    output_inventory: list[dict[str, object]] = []
    for relative in sorted(first_payloads):
        output_inventory.append(
            write_bytes(OUTPUT_ROOT / PurePosixPath(relative), first_payloads[relative])
        )

    for index, module_id in enumerate(refs):
        relative = f"modules/{module_id}/index.html"
        module_manifest[index]["output_path"] = relative
        module_manifest[index]["output_bytes"] = len(first_payloads[relative])
        module_manifest[index]["output_sha256"] = sha256_bytes(first_payloads[relative])

    module_pages = [OUTPUT_MODULES / module_id / "index.html" for module_id in refs]
    html_paths = [OUTPUT_ROOT / "index.html", *module_pages, OUTPUT_ROOT / "print.html"]
    parsed_index = parse_html_file(OUTPUT_ROOT / "index.html")
    parsed_module_pages = {module_id: parse_html_file(path) for module_id, path in zip(refs, module_pages)}
    parsed_print = parse_html_file(OUTPUT_ROOT / "print.html")
    notice_counts = {
        "index.html": len(parsed_index.xpath("//aside[@class='edition-notice']")),
        **{
            f"modules/{module_id}/index.html": len(
                page.xpath("//aside[@class='edition-notice']")
            )
            for module_id, page in parsed_module_pages.items()
        },
        "print.html": len(parsed_print.xpath("//aside[@class='edition-notice']")),
    }
    notice_text_failures = [
        relative
        for relative, page in {
            "index.html": parsed_index,
            **{
                f"modules/{module_id}/index.html": page
                for module_id, page in parsed_module_pages.items()
            },
            "print.html": parsed_print,
        }.items()
        if [" ".join(text.split()) for text in page.xpath("//aside[@class='edition-notice']/text()")]
        != [EDITION_NOTICE_TEXT]
    ]
    paired_access_failures = []
    offline_dependency_failures = []
    for relative, page in {"index.html": parsed_index, "print.html": parsed_print,
                           **{f"modules/{key}/index.html": val for key, val in parsed_module_pages.items()}}.items():
        source_actions = page.xpath("//nav[@class='paired-access']/a[@class='original-source-link']")
        if (page.get("lang") != "en" or len(source_actions) != 1
            or source_actions[0].get("href") != ORIGINAL_WEBSITE
            or source_actions[0].get("hreflang") != "en"
            or not page.xpath("//nav[@class='paired-access']/a[@href=$url]", url=PROGRAM_WEBSITE)):
            paired_access_failures.append(relative)
        if page.xpath("//script | //iframe | //object | //embed"):
            offline_dependency_failures.append(relative)
    if re.search(rb"@import|url\s*\(", css_bytes, re.IGNORECASE):
        offline_dependency_failures.append("reader-id.css: dependency requires explicit inventory")
    source_empty_cross_references = [
        (module_id, link.get("document") or module_id, link.get("target-id"))
        for module_id, root in roots.items()
        for link in root.iter(f"{{{CNXML_NS}}}link")
        if not "".join(link.itertext()).strip()
    ]
    generated_cross_reference_counts = {
        "module_pages": sum(len(page.xpath("//a[@data-generated-cross-reference-label='true' and normalize-space(.)]"))
                            for page in parsed_module_pages.values()),
        "print": len(parsed_print.xpath("//a[@data-generated-cross-reference-label='true' and normalize-space(.)]")),
    }
    empty_generated_cross_references = {
        "module_pages": sum(len(page.xpath("//a[@data-generated-cross-reference-label='true' and not(normalize-space(.))]"))
                            for page in parsed_module_pages.values()),
        "print": len(parsed_print.xpath("//a[@data-generated-cross-reference-label='true' and not(normalize-space(.))]")),
    }
    source_list_presentation = Counter(
        (node.get("number-style") or None, node.get("list-type") or None, node.get("bullet-style") or None,
         "circled" in (node.get("class") or ""))
        for root in roots.values() for node in root.iter(f"{{{CNXML_NS}}}list")
    )
    html_list_presentation = Counter(
        (node.get("data-number-style"), node.get("data-list-type"), node.get("data-bullet-style"),
         any(name in {"source-circled", "source--circled"} for name in node.get("class", "").split()))
        for page in parsed_module_pages.values() for node in page.xpath("//*[contains(concat(' ',normalize-space(@class),' '),' cnxml-list ')]")
    )
    list_css_contract_pass = all(fragment in css_bytes for fragment in (
        b'.cnxml-list[data-number-style="lower-alpha"]', b'list-style-type: lower-alpha',
        b'.cnxml-list.source-circled', b'list-style-type: none',
    ))
    print_paired_access_in_front_matter = len(parsed_print.xpath(
        "//section[@class='print-front']/nav[@class='paired-access'][preceding-sibling::p and following-sibling::h2]"
    )) == 1

    native_id_failures = []
    parity_failures = []
    math_failures = []
    aggregate_source = Counter()
    aggregate_pages = Counter()
    aggregate_print = Counter()
    for module_id in refs:
        page = parsed_module_pages[module_id]
        page_ids = page.xpath("//*[@id]/@id")
        if page_ids != source_ids[module_id]:
            native_id_failures.append(module_id)
        for key, expected in source_metrics[module_id].items():
            aggregate_source[key] += expected
            actual = html_count(page, key)
            aggregate_pages[key] += actual
            if actual != expected:
                parity_failures.append(
                    {"module_id": module_id, "kind": key, "source": expected, "html": actual}
                )
        page_math = serialized_html_math_signature(
            first_payloads[f"modules/{module_id}/index.html"]
        )
        if page_math != source_math_signatures[module_id]:
            math_failures.append(module_id)

    for key in aggregate_source:
        aggregate_print[key] = html_count(parsed_print, key)
    print_parity_failures = {
        key: {"source": aggregate_source[key], "print": aggregate_print[key]}
        for key in aggregate_source
        if aggregate_source[key] != aggregate_print[key]
    }
    print_prefixed_ids = [
        value
        for value in parsed_print.xpath("//*[@id]/@id")
        if not value.startswith("module-")
    ]
    expected_print_ids = [
        f"{module_id}--{native_id}"
        for module_id in refs
        for native_id in source_ids[module_id]
    ]
    print_id_order_exact = print_prefixed_ids == expected_print_ids
    print_math_exact = serialized_html_math_signature(first_payloads["print.html"]) == tuple(
        signature
        for module_id in refs
        for signature in source_print_math_signatures[module_id]
    )

    resource_qa = validate_local_resources(html_paths)
    img_nodes = [img for page in parsed_module_pages.values() for img in page.xpath("//img")]
    print_image_count = len(parsed_print.xpath("//img"))
    image_alt_complete = all("alt" in img.attrib for img in img_nodes)
    copied_asset_mismatches = [
        record["output_path"]
        for record in asset_manifest
        if sha256_file(OUTPUT_ROOT / record["output_path"]) != record["sha256"]
    ]
    second_payloads = render_reader_payloads(
        collection,
        collection_content,
        refs,
        roots,
        titles,
        css_bytes,
        asset_payloads,
        asset_manifest_tsv,
    )
    replay_mismatches = sorted(
        relative
        for relative in set(first_payloads) | set(second_payloads)
        if first_payloads.get(relative) != second_payloads.get(relative)
    )

    qa = {
        "collection_module_order_count": len(refs),
        "collection_module_order_unique": len(set(refs)),
        "chapter_subcollection_count": chapter_count,
        "module_pages_generated": len(module_pages),
        "html_files_expected_and_parsed": len(html_paths),
        "edition_notice_expected_pages": len(html_paths),
        "edition_notice_exact_counts": notice_counts,
        "edition_notice_text_failures": notice_text_failures,
        "paired_original_program_access_failures": paired_access_failures,
        "offline_uninventoried_dependency_failures": offline_dependency_failures,
        "original_component_credits_preserved": len(original_component_credits(roots)),
        "source_empty_cross_references": len(source_empty_cross_references),
        "generated_cross_reference_counts": generated_cross_reference_counts,
        "empty_generated_cross_references": empty_generated_cross_references,
        "source_to_html_list_presentation_exact": source_list_presentation == html_list_presentation,
        "source_list_presentation": [
            {
                "number_style": key[0],
                "list_type": key[1],
                "bullet_style": key[2],
                "circled": key[3],
                "count": count,
            }
            for key, count in sorted(source_list_presentation.items(), key=lambda item: repr(item[0]))
        ],
        "html_list_presentation": [
            {
                "number_style": key[0],
                "list_type": key[1],
                "bullet_style": key[2],
                "circled": key[3],
                "count": count,
            }
            for key, count in sorted(html_list_presentation.items(), key=lambda item: repr(item[0]))
        ],
        "list_css_contract_pass": list_css_contract_pass,
        "print_paired_access_in_front_matter": print_paired_access_in_front_matter,
        "native_id_order_failure_modules": native_id_failures,
        "aggregate_source_native_ids": sum(len(source_ids[module_id]) for module_id in refs),
        "aggregate_module_page_native_ids": sum(
            len(parsed_module_pages[module_id].xpath("//*[@id]/@id")) for module_id in refs
        ),
        "aggregate_print_prefixed_native_ids": len(print_prefixed_ids),
        "print_prefixed_native_id_order_exact": print_id_order_exact,
        "source_to_module_html_parity_failures": parity_failures,
        "source_to_print_html_parity_failures": print_parity_failures,
        "mathml_element_attribute_text_failure_modules": math_failures,
        "print_mathml_element_attribute_text_exact": print_math_exact,
        "aggregate_source_counts": dict(aggregate_source),
        "aggregate_module_page_counts": dict(aggregate_pages),
        "aggregate_print_counts": dict(aggregate_print),
        "referenced_asset_occurrences": sum(record["occurrences"] for record in asset_manifest),
        "referenced_unique_assets": len(asset_manifest),
        "referenced_unique_asset_bytes": sum(record["bytes"] for record in asset_manifest),
        "asset_manifest_bytes": len(asset_manifest_tsv),
        "asset_manifest_sha256": sha256_bytes(asset_manifest_tsv),
        "copied_asset_hash_mismatches": copied_asset_mismatches,
        "generated_images": len(img_nodes),
        "print_generated_images": print_image_count,
        "generated_images_all_have_alt": image_alt_complete,
        "second_complete_render_byte_mismatches": replay_mismatches,
        "reader_visible_node_coverage_exact": True,
        "reader_visible_text_coverage_exact": True,
        **resource_qa,
        "render_sample_modules": select_render_sample(refs, source_metrics),
    }
    qa["pass"] = all(
        [
            len(refs) == len(set(refs)) == EXPECTED_MODULES,
            chapter_count == EXPECTED_CHAPTERS,
            len(module_pages) == EXPECTED_MODULES,
            len(notice_counts) == len(html_paths),
            all(count == 1 for count in notice_counts.values()),
            not notice_text_failures,
            not paired_access_failures,
            not offline_dependency_failures,
            generated_cross_reference_counts["module_pages"] == len(source_empty_cross_references),
            generated_cross_reference_counts["print"] == len(source_empty_cross_references),
            empty_generated_cross_references == {"module_pages": 0, "print": 0},
            source_list_presentation == html_list_presentation,
            list_css_contract_pass,
            print_paired_access_in_front_matter,
            not native_id_failures,
            print_id_order_exact,
            not parity_failures,
            not print_parity_failures,
            not math_failures,
            print_math_exact,
            not copied_asset_mismatches,
            sum(record["occurrences"] for record in asset_manifest)
            == EXPECTED_IMAGE_OCCURRENCES,
            len(asset_manifest) == EXPECTED_UNIQUE_ASSETS,
            sum(record["bytes"] for record in asset_manifest)
            == EXPECTED_UNIQUE_ASSET_BYTES,
            asset_manifest_boundary == expected_asset_manifest_boundary,
            len(img_nodes) == EXPECTED_IMAGE_OCCURRENCES,
            print_image_count == EXPECTED_IMAGE_OCCURRENCES,
            image_alt_complete,
            not replay_mismatches,
            not resource_qa["unresolved_local_links_or_fragments"],
            not resource_qa["unresolved_local_resources"],
        ]
    )
    if not qa["pass"]:
        fail("Aggregate reader QA failed:\n" + json.dumps(qa, ensure_ascii=False, indent=2))

    output_inventory = sorted(output_inventory, key=lambda item: item["path"].casefold())
    output_inventory_stream = "".join(
        f"{item['path']}\t{item['bytes']}\t{item['sha256']}\n" for item in output_inventory
    ).encode("utf-8")
    input_snapshot_stream = "".join(
        f"{record['path']}\t{record['resolved_path']}\t"
        f"{record['bytes']}\t{record['sha256']}\n"
        for record in sorted(input_snapshot.values(), key=lambda item: item["path"])
    ).encode("utf-8")
    manifest: dict[str, object] = {
        "schema": "openstax-deterministic-semantic-html-reader",
        "schema_version": "1.1.0",
        "locale": "en",
        "original_source": {"language": "en", "revision": SOURCE_REVISION, "website": ORIGINAL_WEBSITE,
                            "repository": "https://github.com/openstax/osbooks-prealgebra-bundle"},
        "presentation_provenance": "OpenAI Codex gpt-5.6-sol, Ultra; program reader adaptation only, not authorship of the textbook",
        "attribution": "OpenStax, Rice University and credited authors/contributors; original preface and image credits preserved",
        "license": "CC-BY-NC-SA-4.0; component-specific credits and limitations retained",
        "collection": {
            "path": COLLECTION_PATH.relative_to(ROOT).as_posix(),
            "bytes": len(collection_bytes),
            "sha256": sha256_bytes(collection_bytes),
            "title": collection_title(collection),
            "chapter_subcollections": chapter_count,
            "ordered_module_count": len(refs),
            "ordered_module_ids": refs,
            "ordered_module_id_stream_sha256": sha256_bytes(
                ("\n".join(refs) + "\n").encode("utf-8")
            ),
        },
        "build_inputs": {
            "builder": {
                "path": Path(__file__).relative_to(ROOT).as_posix(),
                "bytes": len(script_bytes),
                "sha256": sha256_bytes(script_bytes),
            },
            "css": {
                "path": CSS_SOURCE.relative_to(ROOT).as_posix(),
                "bytes": len(css_bytes),
                "sha256": sha256_bytes(css_bytes),
            },
            "preflight_file_count": len(input_snapshot),
            "preflight_inventory_stream_sha256": sha256_bytes(input_snapshot_stream),
        },
        "tools": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "lxml": lxml.__version__,
            "libxml2": ".".join(map(str, etree.LIBXML_VERSION)),
            "libxslt": ".".join(map(str, etree.LIBXSLT_VERSION)),
        },
        "modules": module_manifest,
        "assets": asset_manifest,
        "asset_closure": {
            "image_occurrences": EXPECTED_IMAGE_OCCURRENCES,
            "unique_assets": EXPECTED_UNIQUE_ASSETS,
            "unique_asset_bytes": EXPECTED_UNIQUE_ASSET_BYTES,
            "canonical_manifest_path": "metadata/assets.tsv",
            "canonical_manifest_bytes": EXPECTED_ASSET_MANIFEST_BYTES,
            "canonical_manifest_sha256": EXPECTED_ASSET_MANIFEST_SHA256,
        },
        "outputs": {
            "files_excluding_manifest": output_inventory,
            "file_count_excluding_manifest": len(output_inventory),
            "bytes_excluding_manifest": sum(item["bytes"] for item in output_inventory),
            "inventory_stream_sha256": sha256_bytes(output_inventory_stream),
        },
        "qa": qa,
    }
    payload_hash = sha256_bytes(stable_json_bytes(manifest, pretty=False))
    manifest["manifest_payload_sha256_before_this_field"] = payload_hash
    manifest_bytes = stable_json_bytes(manifest)
    write_bytes(MANIFEST_PATH, manifest_bytes)

    first_complete_payloads = dict(first_payloads)
    add_payload(first_complete_payloads, "volume.manifest.json", manifest_bytes)
    second_complete_payloads = dict(second_payloads)
    add_payload(
        second_complete_payloads,
        "volume.manifest.json",
        stable_json_bytes(manifest),
    )
    complete_replay_mismatches = sorted(
        relative
        for relative in set(first_complete_payloads) | set(second_complete_payloads)
        if first_complete_payloads.get(relative) != second_complete_payloads.get(relative)
    )
    if complete_replay_mismatches:
        fail(
            "Complete deterministic reader replay differs: "
            + json.dumps(complete_replay_mismatches, ensure_ascii=False)
        )
    candidate_fingerprint = payload_fingerprint(first_complete_payloads)
    actual_candidate_fingerprint = tree_fingerprint(OUTPUT_ROOT)
    if actual_candidate_fingerprint != candidate_fingerprint:
        fail("Complete staged reader tree differs from deterministic replay payloads")
    candidate_tree_sha256 = fingerprint_sha(candidate_fingerprint)

    # Fail closed if any exact input changed while staging was being built.
    # This gate is deliberately after all parse/render/QA work and immediately
    # before the atomic publication boundary.
    verify_input_snapshot(input_snapshot)
    if tree_fingerprint(OUTPUT_ROOT) != candidate_fingerprint:
        fail("Sealed reader candidate changed immediately before publication")
    result = {
        "output_root": FINAL_OUTPUT_ROOT.relative_to(ROOT).as_posix(),
        "manifest_bytes": len(manifest_bytes),
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "manifest_payload_sha256": payload_hash,
        "files_including_manifest": len(output_inventory) + 1,
        "bytes_including_manifest": sum(item["bytes"] for item in output_inventory)
        + len(manifest_bytes),
        "output_inventory_sha256_excluding_manifest": sha256_bytes(output_inventory_stream),
        "candidate_tree_sha256": candidate_tree_sha256,
        "determinism_mode": "two_complete_payload_renders_from_one_frozen_admitted_input_snapshot",
        "second_complete_payload_replay_byte_identical": True,
        "second_complete_build_byte_identical": True,
        "second_complete_build_claim_scope": (
            "complete output-payload replay; discovery and input admission are shared"
        ),
        "input_snapshot_reverified_before_publish": True,
        "input_snapshot_reverified_before_first_render": True,
        "qa": qa,
    }
    PENDING_PUBLICATION_RESULT = result
    result["publication"] = publish_staged_output(candidate_fingerprint)
    return result


def main() -> int:
    try:
        result = build()
    except BaseException as exc:
        recovered = recover_published_result_after_exception()
        if recovered is not None:
            try:
                os.write(
                    1,
                    (
                        json.dumps(recovered, ensure_ascii=False, indent=2, sort_keys=True)
                        + "\n"
                    ).encode("utf-8"),
                )
            except BaseException:
                pass
            return 0
        try:
            cleanup_failed_staging()
        except BaseException as cleanup_error:
            try:
                os.write(2, f"STAGING CLEANUP FAILED: {cleanup_error}\n".encode("utf-8"))
            except BaseException:
                pass
        try:
            os.write(2, f"BUILD FAILED: {exc}\n".encode("utf-8"))
        except BaseException:
            pass
        return 1
    try:
        os.write(
            1,
            (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )
    except BaseException:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
