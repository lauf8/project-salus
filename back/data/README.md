# Initial medication catalog

`common_medicines.json` contains 100 entries for the United States and 100 for Brazil. 39 entries are shared, for a total of 161 medications and 160 distinct active ingredients. Generic names are in English, and compositions use the same active ingredient identity in both countries.

The United States selection matches the first 100 generic medications in ClinCalc DrugStats by outpatient prescriptions in 2024, consulted on 2026-11-12. Combinations were preserved. Source: https://clincalc.com/drugstats/Top200Drugs.aspx . ClinCalc provides the reference list under CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/ . The United States selection keeps that license.

The Brazilian selection is a curated list of 100 common medications, not a validated national sales or prescription ranking. RENAME was consulted as a reference for essential medicines, without assuming that every selected item is part of it. Sources are recorded in the `sources` field of the JSON. `markets` indicates which selection each entry belongs to; it does not certify the regulatory registration of each formulation in a country.

`main_indications` contains brief informative summaries in English. It does not include doses, individual recommendations or an exhaustive list of indications. Indications vary with formulation and country. FDA/DailyMed labeling, the Anvisa package insert database and manufacturer package inserts were consulted. Authorized staff can edit the texts.

NPH and regular human insulin are separate medications linked to the same active ingredient, `Human insulin`. Topical and nasal preparations are also linked to the active ingredient without including the route in the ingredient name.

To import, from `back/`, after applying the migrations:

```sh
docker compose exec -T api alembic upgrade head
docker compose exec -T api python -m scripts.seed_medicines --dry-run
docker compose exec -T api python -m scripts.seed_medicines
```

The import runs in one transaction and uses a lock to serialize concurrent runs. Repeated runs reuse records by normalized name, keep indications already filled in and reject divergent compositions without writing changes. It does not run automatically when the API starts.

Databases seeded with the earlier Portuguese catalog are converted by migration `5b3c4d5e6f72`, which renames matching medications and active ingredients and translates unchanged indications. Names that would collide with an existing record and indications edited by the team are left as they are.
