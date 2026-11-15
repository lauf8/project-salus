# NASA reference PDFs

Official NASA PDFs downloaded for the Project Salus RAG library. Original files are retained here and imported into the existing `knowledge_documents` / `knowledge_passages` tables. Embeddings live in PostgreSQL, not inside the PDF files.

`catalog.json` records the official URL, revision/date read from each document, SHA-256, file size, page count, retrieval-check query and topic tags. Three records enrich existing reference identities; the other five add new references. The already indexed Food and Nutrition reference remains unchanged.

| Reference | Revision / document date | Pages | Official PDF |
| --- | --- | ---: | --- |
| OCHMO-TB-031 Exercise Overview | 2023-10-02; no revision label identified | 26 | [NASA](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-031-exercise-overview.pdf) |
| OCHMO-TB-041 Sleep Accommodations | Rev B, 2023-10-23 | 16 | [NASA](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-041-sleep-accommodations.pdf) |
| OCHMO-TB-004 Carbon Dioxide | Rev D, 2026-03-10 | 19 | [NASA](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf) |
| OCHMO-TB-016 Behavioral Health and Performance | Rev B, 2023-10-24 | 18 | [NASA](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-016-behavioral-health.pdf) |
| OCHMO-MTB-003 Urinary Health | Rev A, 2026-03-10 | 20 | [NASA](https://www.nasa.gov/wp-content/uploads/2025/01/ochmo-mtb-003-urinary-health.pdf) |
| OCHMO-MTB-007 Venous Thrombosis in Spaceflight | 2026-01-08; no revision label identified | 18 | [NASA](https://www.nasa.gov/wp-content/uploads/2026/01/ochmo-mtb-007-venous-thrombosis-in-spaceflight.pdf) |
| OCHMO-MTB-009 Circadian Desynchrony | 2026-03-04; no revision label identified | 11 | [NASA](https://www.nasa.gov/wp-content/uploads/2026/03/ochmo-mtb-009-circadian-desynchrony.pdf) |
| OCHMO-TB-006 Health Stabilization Program | Rev F, 2025-05-19 | 10 | [NASA](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-006-health-stabilization-program.pdf) |

Total: 8 PDFs, 138 pages. Dates are document revisions, not the year in the NASA download path. Briefs remain references; importing them does not automatically change clinical alert thresholds or establish a disease-prediction model. Existing clinical review and privacy rules remain in force.

## Import and verify

From `back/`, with the API/database migrated and Ollama configured:

```bash
docker compose exec -T api python -m scripts.index_nasa_references
```

The command verifies pinned checksums/page counts, reuses file hashes and source/revision identities, indexes with the configured embedding model, assigns topic tags to PDF chunks while preserving legacy passages, and performs a document-filtered vector search for every reference. It skips a completed compatible index. It does not modify mission records, health observations, alerts or notifications.

The generated `index-report.json` contains local document/passage IDs, vector dimension, embedded-passage counts and page-aware retrieval examples. It is kept locally and ignored by Git. Failures produce a nonzero exit code and an explicit report entry.

The actual import was verified with the real Ollama `all-minilm` model, 384 dimensions, 500-character chunks and 150-character overlap. Files are also available in the app under **Mission → Risks → documents**. Search queries should describe the desired topic; source pages and official URLs are returned with the excerpts.

## Individual health assessment corpus

The catalog now also contains the original **NASA-STD-3001 Volume 1, Revision C**, **OCHMO-TB-033 Spaceflight Experience and Medical Care, Revision D**, **HRP Behavioral Health Evidence Report (2025)** and **HRP Team Cooperation and Psychosocial Adaptation Evidence Report (2022)**. Their exact URLs, revisions, checksums and page counts are pinned in `catalog.json`. These are the retained source revisions, not a claim that each is the current NASA standard.

The complete catalog has **12 PDFs, 583 pages and 5,358 indexed passages**. All 12 were verified against local originals and searched with the real `all-minilm` model at 384 dimensions. Dense tables and contents pages in three PDFs required conservative chunk subdivision to fit the embedding context. Page provenance and original PDF bytes are retained. See `CLINICAL_RECORDS.md` for individual reports and physician review.
