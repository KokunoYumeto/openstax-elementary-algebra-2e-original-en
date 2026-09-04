# Exact Source Freeze — 2026-08-20

## Authority identity

- Official repository: `openstax/osbooks-prealgebra-bundle`.
- Default branch observed: `main`; repository not archived.
- Pinned commit: `38cae454e644abf9f0a623e876994553881597c9`.
- Commit tree: `7907e4c81d43de1c3b6da173f0eb273c01dc5b55`.
- Commit parent: `6edcbbe740343cf2df90e9190a55a899bf7fae28`.
- Commit message/date: `errata 29593`, `2026-06-29T23:52:34Z`.
- Elementary collection blob: `31100884d63f0c421b15905728637d5d010fe961`.
- Collection UUID/slug/catalog ID/style: `55931856-c627-418b-a56f-1dd0007683a8`,
  `elementary-algebra-2e`, `col31130`, `dev-math`.

All retrieval used official GitHub API/raw/codeload HTTPS endpoints and no Git
command. The full repository archive was streamed to disk solely to avoid 4,018
individual media requests. It was 537,455,794 bytes, SHA-256
`effdf2dbb6dfd9cab771b568c6575d8074be4a1f9565f1fedbd54f621e138917`;
only the explicit Elementary closure was extracted and verified, and the archive
was deleted. Receipt: `authority/ARCHIVE_ACQUISITION_RECEIPT.json`, SHA-256
`60eabf3e87288ee62709ba94f5926a5a7c96a2392e657d48d7abce3a61998a76`.

## Exact closure

- Collection references: 82, all unique and present.
- Module topology: 82 one-file module directories, each `index.cnxml`; all XML
  parses; directory ID equals `md:content-id`; module UUIDs are unique.
- Fixed source files + modules + exact optional cover: 88 files / 10,344,037
  bytes; source manifest SHA-256
  `b817c9bfbd1dcba59f1e6949a83727a662bf95407882634620cd46b625b6a5f2`.
- Image uses: 4,024; unique media paths: 4,018; 4,015 JPG + 3 PNG;
  194,271,847 bytes; zero missing and zero case-fold collisions; media manifest
  SHA-256 `3b8478b77c8860363b7000cbffa68782320e73458289bdcda957acf1b971210f`.
- Upstream build/editor configuration: four files / 918 bytes; manifest SHA-256
  `13a14c2b9222f91a54acfd176bb18bf94312e4457b263133f61b15883bd5e9b2`.
- Combined source+media+config+official PDF: 4,111 files / 261,345,507 bytes.
- Canonical `authority/AUTHORITY_SNAPSHOT.csv`: 736,557 bytes, SHA-256
  `4f3c5006a896793fd3856606c6683fe48ba31734befadd5221c290f2c80dc2ec`.
- Snapshot JSON SHA-256:
  `fcb2aa90796dcba4e8c8f4fac1cb4ff8d9de94ba72e0fcd3575248c0d24dbf50`.

Source census at this commit: 55,180 scoped CNXML element IDs (bare values are
not globally unique); 9,406 exercises/problems; 6,106 provided solutions and
3,300 intentionally absent solutions; 607 links; all book-internal targets
resolve. All 4,024 images have nonempty `alt`. Declared media MIME is unreliable:
2,545 `.jpg` paths claim `image/png`, so detected and declared MIME must remain
separate backend fields.

## Official rendered witness

`authority/rendered/elementary-algebra-2e_WEB_20260820.pdf` is the current
official asset at the recorded URL: 56,728,705 bytes, 1,290 pages, SHA-256
`a250861ff5e945a63a0b90f8c8790a6ed73d9eb04675854824a3880073d0759e`.
It is PDF 1.7, Letter, unencrypted, `/Lang en`, untagged, not optimized, has no
attachments or JavaScript, and exposes no logical fields despite an AcroForm
catalog marker. Front pages 1–12 were rendered and visually inspected; durable
contact sheet SHA-256
`67110a8a7f5b56ff586f1a97de5402d38c3f8f11e76f2838342bf668379f74b7`.

## Rights and adverse observations

Pinned README, legal code, collection metadata, current PDF, and official web
preface agree on CC BY-NC-SA 4.0. Preserve NonCommercial, ShareAlike,
attribution, change notice, and non-endorsement conditions. Trademarks are not
licensed. Some art is permission-limited; two explicit Flickr credits lack
license URLs, so component review remains mandatory. A current web-only
AI-ingestion notice is not present in the pinned repository/PDF authority and is
retained as a separate policy observation rather than silently merged into the
CC license.

Network closure is not clean: one external shortlink is currently 404
(`m82499`, `https://www.openstax.org/l/25GSInequal3`) and 21 other shortlinks
redirect from HTTPS to HTTP. These are source observations; no target change has
yet been made.

## Build status

The source/content closure is frozen. The repo contains no package/lock file,
build script, Dockerfile, or workflow. Its devcontainer is unpinned Debian 12
with unversioned OpenStax Editor/XML extensions; `dev-math` is an external style
name without an implementation/version in the repo. Exact CNXML/CollXML
validator and reader-generation toolchain must therefore be selected and pinned
as derivative infrastructure. Do not claim an upstream-reproducible build.
