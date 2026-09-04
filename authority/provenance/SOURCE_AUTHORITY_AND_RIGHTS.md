# Source Authority and Rights

Status: exact source, rendered authority, and available build-configuration
witnesses are frozen. The upstream repository does not contain a reproducible
reader toolchain. The official OpenStax Enki pipeline and exact `dev-math`
recipe are the provisional derivative candidates, not yet admitted by a build.
Translation block 1 is independently admitted on separate working copies.

## Corrected curriculum record

- Resource/catalog identity: `OS-EA2`, OpenStax *Elementary Algebra 2e*;
  curriculum course A10. In `curriculum.json`, R001 is the shared three-book
  source bundle; R002 is Precalculus 2e and is not this work.
- Official measured PDF: 1,290 pages, independently verified below. The earlier
  lane shorthand “R002 / A30 / 1,411 pages” conflated this book with Precalculus
  and is superseded.
- Authoring surface: CollXML collection, 82 ordered CNXML modules, and exact
  referenced media.

## Frozen source authority

- Repository: `https://github.com/openstax/osbooks-prealgebra-bundle`.
- Commit: `38cae454e644abf9f0a623e876994553881597c9` (`errata 29593`,
  2026-06-29T23:52:34Z); parent `6edcbbe740343cf2df90e9190a55a899bf7fae28`.
- Tree: `7907e4c81d43de1c3b6da173f0eb273c01dc5b55`.
- Elementary collection: `collections/elementary-algebra-2e.collection.xml`,
  blob `31100884d63f0c421b15905728637d5d010fe961`, UUID
  `55931856-c627-418b-a56f-1dd0007683a8`, source language `en`.
- Closure: 82 unique modules; 4,024 image uses resolving to 4,018 unique media
  assets; zero missing paths and zero case-fold collisions. The two sibling
  collections/modules are not admitted.
- Canonical snapshot: 4,111 files / 261,345,507 bytes, including the exact
  Elementary cover and four upstream configuration witnesses; manifest 736,557
  bytes, SHA-256
  `4f3c5006a896793fd3856606c6683fe48ba31734befadd5221c290f2c80dc2ec`.

## Official rendered baseline

- URL: `https://assets.openstax.org/oscms-prodcms/media/documents/elementary-algebra-2e_-_WEB.pdf`.
- Local authority: `authority/rendered/elementary-algebra-2e_WEB_20260820.pdf`.
- 56,728,705 bytes; SHA-256
  `a250861ff5e945a63a0b90f8c8790a6ed73d9eb04675854824a3880073d0759e`;
  1,290 Letter pages; PDF 1.7; unencrypted; `/Lang en`; untagged; no
  attachments; no JavaScript; no logical form fields. Created 2026-04-28 and
  modified 2026-05-26 by Prince 16.2.

## Rights boundary

- Repository README, repository legal code, collection metadata, current
  official PDF, and official web preface agree on CC BY-NC-SA 4.0.
- Translation is adapted material: retain attribution and license notice,
  identify modifications, remain noncommercial, apply compatible ShareAlike
  terms, impose no extra restrictions, and never imply OpenStax/Rice endorsement.
- OpenStax names/logos/trademarks are outside the CC license.
- The source preface warns that some art has attribution or permission-specific
  limitations. Component review is mandatory; a book-level license must not
  silently override asset-specific status. Two explicit Flickr credits currently
  lack license URLs and are not cleanly cleared for generalized reuse.
- The current web reader also displays an AI-ingestion notice not present in the
  pinned repository README/license/collection/modules or current PDF. Record it
  as a separate web-policy notice; do not rewrite the pinned license. This is a
  provenance observation, not legal advice.

## Authority freeze checklist

- [x] Verify official repository and Elementary collection identity.
- [x] Pin immutable commit/tree and record archive acquisition without Git.
- [x] Bind collection/module/media closure and missing/collision results.
- [x] Bind current official PDF identity and metadata.
- [x] Capture repository/book license and general attribution/change/
      non-endorsement duties.
- [x] Preserve component-level rights status without manufacturing clearance:
      every one of the 4,024 asset-use records has its own resolvable rights
      record, and uncertain third-party status remains explicit. This is a
      rights-preservation completion criterion, not a claim that every
      third-party component has been independently relicensed.
- [x] Record available build configuration and the negative reproducibility
      finding: the repository does not pin a complete reader toolchain.
- [~] Select and pin derivative validation/rendering infrastructure: official
      candidates and exact observed revisions are recorded, but immutable
      dependency/container closure and a disposable sideloaded build remain.
      Never present the result as an upstream-reproducible source-repository
      build.

Detailed witnesses: `09_SOURCE_FREEZE_20260820.md`,
`10_DERIVATIVE_TOOLCHAIN_RESEARCH.md`, and `authority/` manifests.

## Final rights-preservation freeze (2026-08-29)

Status: **PASS — preserved uncertainty, not generalized clearance.** The final
audit is bound to the 82-module `col31130` authority at commit
`38cae454e644abf9f0a623e876994553881597c9`. Its machine-readable receipt is
`qa/final-completion/RIGHTS_FREEZE_RECEIPT_20260829.json`.

- The backend contains 4,024 unique asset-use records for 4,018 unique frozen
  media paths (six repeated uses), plus 4,024 one-to-one component-rights
  records and one work-default rights record. Every asset has a nonempty
  `rights_id`; every reference resolves; every rights `subject_id` points back
  to the same asset; every component inherits the one work-default rights ID;
  and there are no orphan, duplicate-ID, evidence-path, collection-boundary,
  byte, SHA-256, or Git-blob mismatches.
- All 4,018 authority media files were rehashed from their explicit manifest
  paths: zero missing files, byte mismatches, or SHA-256 mismatches. This was a
  bounded manifest replay, not a workspace scan.
- The work-default record remains `CC-BY-NC-SA-4.0`, status `active`, with
  attribution `Elementary Algebra 2e, OpenStax, Rice University.` Its
  `third_party_status` remains `component_exceptions_possible` and its
  `review_status` remains
  `collection_authority_confirmed_component_review_required`.
- Component uncertainty is deliberately retained: 4,022 asset-use records are
  `third_party_status=unreviewed`; two are
  `third_party_status=credit_present_unverified`; all 4,024 remain
  `review_status=needs_component_review`. Their inherited license ID and URL
  are therefore not evidence of an independently verified component grant.
- Forty-eight asset-use records preserve nonempty source attribution text.
  The two explicit Flickr credits are bound to
  `CNX_ElemAlg_Figure_04_00_001` (Steve Jurvetson, `m82479`) and
  `CNX_ElemAlg_Figure_10_00_001` (tlc, `m82554`). The original English captions
  are exact in the rights records; the Indonesian captions preserve the named
  creator, Flickr platform, modification relationship where stated, figure ID,
  and image source. Neither frozen source credit supplies a standalone
  component-license URL, so both remain unverified rather than being silently
  cleared.
- The source license is preserved byte-for-byte as CC BY-NC-SA 4.0 (21,442
  bytes; SHA-256
  `ab1a44bbba58252630134574d7b2534813339240eb645825ffcc2487dbe8114a`).
  The translated preface retains attribution, noncommercial, ShareAlike,
  permission-limited-art, and fallback-art-credit language. The exact license,
  authority manifests, source/translated credit-bearing modules, and backend
  asset/rights exports are present in the release packages.
- Release wording does not flatten component status into a book-wide clearance:
  the release manifest, release profile, GitHub README/release notes, and public
  Zenodo description all qualify CC BY-NC-SA 4.0 as subject to
  component-specific credits and restrictions, and state non-endorsement.

This freeze satisfies the goal's requirement to preserve source relationships,
component rights, attribution, license/status evidence, and uncertainty. It is
not legal advice and does not convert unreviewed or permission-limited material
into independently cleared material.
