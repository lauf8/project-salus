# Complete monitoring demonstration

Run from `back/`, with the Docker services running and the database migrated:

```bash
docker compose exec api python -m scripts.seed_full_demo --apply
```

To only list the real tables and their record counts:

```bash
docker compose exec api python -m scripts.seed_full_demo
```

The new account uses the login `demo.monitoramento@example.com` and the password
`Monitoramento2026!`. It has the physician and astronaut profiles. Permissions
are kept per mission: the same account is administrator in the Administração
mission, flight surgeon in Atendimento médico and astronaut in Meu monitoramento.
Select the mission that matches the role you want to test.

The script creates four fictional accounts, three missions, five exam types,
fifteen requirements, fifteen checklist items, nine results and six reviews. The
checklists show the five states: pending, scheduled, awaiting review, repeat
requested and completed. It adds 990 observations over thirty days, with the
eleven indicators and individual references for comparison in the dashboards.
The three auxiliary accounts also use the initial password above.

The script uses the application services and validations. Repeated runs keep
accounts, passwords and existing samples, and fill in missing data without
deleting records. Each service commits its own transaction: an interruption can
leave a partial load, which can be completed by running the script again. Series
dates are kept on repeated runs. The data is labeled as fictional.

The account, mission and note texts created by this script (for example
`Missão demonstração` and `dados fictícios`) are identifiers that repeated runs
match exactly. They were kept as originally created so that existing databases
are not duplicated.

## Tables identified in the models

| Table | Purpose |
| --- | --- |
| users | Users, profiles and hashed passwords |
| missions | Missions and dates |
| mission_members | Memberships and permissions per mission |
| exam_types | Exam catalog |
| mission_exam_requirements | Exams required in each mission |
| astronaut_exams | Individual checklist and scheduling |
| exam_results | Results and authorship |
| exam_result_reviews | Reviews and decisions |
| health_observations | Measurements, self-reports and references |
| knowledge_documents | NASA reference documents |
| knowledge_passages | Passages and topics of the reference base |
| revoked_tokens | Revoked sessions |

Alembic also keeps `alembic_version` for migration control. The knowledge base
uses the real documents from `knowledge_seed.json`, loaded by the normal setup;
the demonstration script does not replace them with fictional content. Revoked
tokens are created by logout, without inserting fake sessions.

## Configured database and validation

The API selects its database through `NASA_DATABASE` in `.env`, falling back to
`POSTGRES_DB`. In this installation, `NASA_DATABASE=nasa_front_validation_20261111`
points to the existing monitoring database. `app_db` belongs to another system
and was preserved, including its migration `7efe7ee6f54f`. Do not remove volumes
or change Alembic versioning to work around that error.

The load was run on PostgreSQL and validated the five checklist states and the
eleven indicators in the three missions. Login through the API was validated and
returned the three demonstration missions for the main account.
