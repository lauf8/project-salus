# Salus database for import

`salus_database_20261115.dump` contains the whole application schema (`public`), with its tables, sequences, functions, indexes, constraints, records, documents and Alembic revision. It includes the 56 missions: the 50 from the generated history and the 6 earlier ones. Auxiliary test schemas are not in the file.

Missions and crews in the history use plausible fictional names, such as Aurora 01 and Rafael Andrade. The generated origin of the 50 missions is documented in `provenance.json`, separately from the database. This does not turn the records into clinical data or real missions. The original reference documents, including their PDFs and sources, were preserved.

The dump was created before the English translation of the interface data. After restoring it, run `alembic upgrade head` to convert the respiratory rate unit and the medication catalog to English. Stored free text, such as notes and alert reasons recorded at the time, stays as recorded.

## Restore

Use the PostgreSQL 17 tools, targeting a new, empty database:

```bash
createdb -U YOUR_USER salus_import
pg_restore -U YOUR_USER --clean --if-exists --no-owner --no-acl --exit-on-error --dbname=salus_import salus_database_20261115.dump
```

Point the application `PGDATABASE` to the restored database. PostgreSQL credentials and other environment variables are not part of this package.

In the interface, select **Mission administrator → Rafael Andrade** for the 50 history missions, or **Physician → Helena Monteiro** for health and medical records. Earlier profiles were also preserved. Generated contact addresses use the reserved domain `crew.salus.example`.

## Verification

`SHA256SUMS` lets you check the files. `restore-validation.json` records the check performed after restoring the dump into another PostgreSQL database.

Before the export, the comparison with the backup verified 189,691 records in 62 tables with no changes to numeric values, source dates, keys, links or binary data. The automatic recommendation enrichment time is updated by the worker and was excluded from that comparison. Technical protocol codes and telemetry origins were preserved; they are not display labels. Nine tests for the export preparation and the generator passed.

## Case with AI analysis

The updated export includes Matheus Valença in the Atlântico 03 mission, with five clinical alerts, two internal notifications and three recommendations whose explanations were actually generated and validated by Ollama, using NASA references. Open Physician → Helena Monteiro → Predictive Intelligence and select Matheus. Expand the documentary evidence of the recommendations. The case origin and its IDs are in `ai-health-case.json`. The separate clinical assessment produced no diagnostic hypotheses and was not approved automatically.
