# Local real-document research

`real_manifest.csv` records hashes, sizes, retrieval notes and original official URLs.
`real_coverage_example_labels.csv` contains 18 published numeric SBC examples across
six insurers: rounded illustrations, **not actual claims or hospital bills**.

**No redistribution license; PDF/text not in this repo.** Originals and full text
extracts stay in gitignored `data/real_private/`, including the CMS workbook and
its third-party code descriptions. Follow official links in the manifest rather
than rehosting. A source URL identifies provenance, not an open license.

To import an existing local download (no network requests):

```sh
python3 scripts/import_real_corpus.py /path/to/real-insurer-research
git check-ignore data/real_private/docs/kaiser_2026_ca_gold80_sbc.pdf
```

The local `SYNTHETIC_kaiser_demo_replay.json` is a constructed overcharge demo,
with historical Northwest sample prices, not verified California negotiated rates.
It is not an actual error, claim or bill and is excluded from real-label evaluation.
No public matched policy → adjudicated claim → hospital bill chain is available.
