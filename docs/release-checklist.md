# Corpus release checklist

For a release that changes parser or builder output and republishes the corpus from cached DOCX (an offline rebuild). Learned the hard way across v0.15.0 to v0.16.1, where a gate that silently skipped its checks and a text-dropping builder bug both shipped or nearly shipped.

## 1. Baseline

- Restore the HF head into an empty directory with `scripts/restore_corpus_from_hf.py` (hash-verified). Do not use a local `corpus/` snapshot.
- HF holds no DOCX. Copy `docx/` in from a local source, and for any Act whose compilation changed, re-fetch it with `lexau build --list-file ... --force`.
- Record the head sha. Check it again just before publishing; the weekly workflows can move it.

## 2. Rebuild and prove determinism

- `scripts/rebuild_offline.py --baseline-corpus <baseline> --out <rebuild> --local-definitions --workers 12` (about 40 minutes).
- Run it twice and `diff -rq` the two `xml/` directories. The output must be byte-identical apart from the Generation date. A difference means order or `id()` dependence somewhere.
- `scripts/merge_offline.py --baseline-corpus <baseline> --chunk <rebuild> --out <final>`.

## 3. Gates (on the merged corpus)

- `python scripts/spot_check.py --corpus-dir <final>`. It must end `All checks passed`, with the XSD gate PASS. A missing `<Act>-v*.json` report now fails the run; do not pass `--allow-missing-reports` for a release.
- `python scripts/diff_corpora.py <baseline>/xml <final>/xml --allow-section-increase`. It exits non-zero on lost paragraph text, duplicate or empty eIds, a section or figure drop. Read the counts, not just the exit code: every changed Act should be explainable.
- `python scripts/canary_shape.py --corpus-dir <final> --baseline canary-baseline.json`.
- Full `pytest`, and `scripts/build_contract_fixtures.py` to see whether any fixture really changed (restore date-only differences).

## 4. Publish and verify

- `lexau export-jsonl`, then `lexau export-hf --repo cchew/lex-au --corpus-dir <final> --allow-large-change --skip-sync-check`.
- Verify by hash: every `xml/` and `reports/` file against the corpus (LFS sha256, or git blob sha1 for small files).
- `python scripts/hf_orphans.py --corpus-dir <final>` (dry run) lists files the corpus no longer uses; `--delete` removes them.
- Tag the repo (and `contract-fixtures-vX.Y.Z` if the fixtures changed), push.
- Re-run the `Growth check` workflow (`gh workflow run "Growth check"`) and confirm it is green. This runs the same gate on the live HF corpus.

## 5. Consumers

- Bump the `contract-fixtures` pin (and privacy's `lexau` pin) in lex-au-search, lex-au-graph, lex-au-explorer and lex-au-privacy; run their suites; push.
- A change in `STRUCTURE_VERSION` needs each consumer's supported-versions list updated first.
- Trigger the lex-au-graph rebuild (`rebuild-on-corpus-publish.yml`); it restores from HF.
- Explorer: see its README Deploy section (`LEXAU_CORPUS_DIR=... LEXAU_GRAPH_JSON=... npm run deploy`).
- Search: re-ingest against the pinned corpus revision (`docs/colab-reingest-runbook.md` in lex-au-search, or `ingest` on a machine with enough RAM).
