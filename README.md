# Elementary Algebra 2e — original English reader

Read the program-hosted edition: **[Open the complete HTML reader](https://kokunoyumeto.github.io/openstax-elementary-algebra-2e-original-en/)**

Original publisher: **[OpenStax — Elementary Algebra 2e](https://openstax.org/details/books/elementary-algebra-2e)**

Indonesian edition: **[Read or download the complete Bahasa Indonesia edition](https://doi.org/10.5281/zenodo.22236314)**

Course in the complete program: **[English interface](https://kokunoyumeto.github.io/program-matematika-indonesia/en/#course-A10)** · **[Bahasa Indonesia interface](https://kokunoyumeto.github.io/program-matematika-indonesia/id/#course-A10)**

This repository preserves the original English text of *Elementary Algebra 2e* by Lynn Marecek, MaryAnne Anthony-Smith, and Andrea Honeycutt Mathis, published by OpenStax at Rice University. The source is pinned to the official OpenStax bundle revision `38cae454e644abf9f0a623e876994553881597c9`. The program-generated HTML presentation is not a new translation, and OpenStax, Rice University, and the authors do not sponsor or endorse this mirror.

The reader contains all 82 source modules in official order, 4,018 original image files, 20,491 native MathML expressions, 9,406 exercises, and all 6,106 source-provided solutions. It requires no JavaScript or remote mathematics renderer. Download the release ZIP, extract it without changing its folder layout, and open `index.html` for offline reading. External citations and publisher services still require internet access.

## Reproducibility and provenance

- `collections/` and `modules/` contain the frozen original source documents.
- `media/` contains exactly the images referenced by those 82 documents.
- `authority/` binds source order, media closure, source-package provenance, rights distinctions, and exact hashes.
- `scripts/build_reader_en.py` produces and validates `output/html-en/` without changing original source bytes.
- `scripts/validate_original_reader.py` independently checks the output inventory, prose, MathML, native IDs, semantic counts, cross-references, list styles, local resources, credits, license, and paired access.
- `scripts/replay_original_reader.py` performs a clean, isolated rebuild and verifies every output byte against the admitted reader.
- `scripts/check_program_navigation.py` independently requires the English course link, Indonesian course link, and authoritative OpenStax link on every published HTML page.
- `output/html-en/metadata/source-provenance.json` describes the presentation and its offline limitations in machine-readable form.

The source and presentation are distributed under CC BY-NC-SA 4.0, subject to the original book’s component-specific credits and limitations. All original captions remain part of the reader. The component inventory preserves 4,022 unreviewed asset uses and two explicit but still unverified Flickr credits; inherited work licensing is not presented as independent component clearance. See [LICENSE](LICENSE) and `output/html-en/metadata/original-component-credits.json`.

Presentation prepared with OpenAI Codex gpt-5.6-sol, Ultra, on instructions of the user. Original authorship and contributor credits are unchanged.
