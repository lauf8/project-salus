# WHO ICD-10 English source

The original `icd102019enMeta.zip` is the WHO ICD-10 2019 English plain text tabular release, including COVID-19 updates, from [WHO's download catalog](https://icdcdn.who.int/icd10/index.html).

`catalog.json` records the direct official ZIP URL, revision, archive member date, SHA-256 and size. The ZIP contains unmodified chapter, group and code files. These are text sources with no page count. The application reads the code table directly, preserving English classification labels and terminal/category distinctions. Search covers the complete code table, including conditions, symptoms, injuries and external causes; category headings cannot be selected as terminal codes.

This source is WHO ICD-10, not the US ICD-10-CM modification or ICD-11. Selecting a code in a self-report does not confirm a diagnosis. See `CLINICAL_RECORDS.md` for workflow, permissions and verification.
