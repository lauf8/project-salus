# Medicamentos e alergias

O prontuário usa o usuário do astronauta como identidade clínica. As alergias referenciam `users.id` por `crew_member_id`, independentemente da missão. O campo `users.allergy_screening_completed` começa como `false`, inclusive para usuários existentes. A missão informa o contexto de autorização do médico de voo, sem limitar as alergias àquela missão.

Os catálogos podem ser consultados por usuários autenticados. Sua edição exige médico vinculado a uma missão como `mission_admin` ou `flight_surgeon`, conforme o cadastro de tipos de exame. O astronauta consulta as próprias alergias. A consulta por terceiros e a edição exigem médico de voo vinculado à missão do astronauta, informado em `mission_id`.

## Rotas

Todas as rotas têm prefixo `/v1` e exigem autenticação.

| Recurso | Operações |
| --- | --- |
| `/medicines` | GET paginado, POST |
| `/medicines/{medicine_id}` | GET, PATCH, DELETE |
| `/active-ingredients` | GET paginado, POST |
| `/active-ingredients/{ingredient_id}` | GET, PATCH, DELETE |
| `/health/astronauts/{crew_member_id}/allergies` | GET, PUT; parâmetro opcional `mission_id` |

As listagens aceitam `search`, `page` e `per_page` (máximo 100) e retornam `data` e `pagination`.

POST e PATCH de medicamento aceitam `name` e `active_ingredient_ids`. A composição é retornada como `active_ingredients`, contendo IDs e nomes. No PATCH, omitir a composição a preserva; enviar `[]` a remove. Nome e composição são salvos na mesma transação.

PUT de alergias exige `allergy_screening_completed` e aceita `active_ingredient_ids` (lista vazia por padrão). Essa operação substitui o registro completo na mesma transação. IDs duplicados ou inexistentes são rejeitados. A exclusão de princípio ativo em uso retorna HTTP 409.

## Telas

A navegação inclui Medicamentos e Princípios ativos, com busca, paginação, cadastro e edição. O medicamento permite selecionar vários princípios ativos. A seção Alergias está no monitoramento e em Missões → Prontuário · alergias. Os controles de escrita seguem as permissões retornadas pelo backend.

Triagem aberta sempre aparece como “Triagem pendente”. Triagem concluída aparece como “Alergias registradas” quando há itens e “Nenhuma alergia conhecida” quando não há.

## Migration

Na pasta `NASA`, com o ambiente Docker configurado:

```sh
docker compose exec -T api alembic upgrade head
```

Fora do Docker, com as variáveis `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT` e `PGDATABASE` configuradas:

```sh
alembic upgrade head
```

A revisão é `a8293b4c5d6e`, posterior a `f718293a4b5c`.

## Verificação

Na pasta `NASA`, com as dependências do backend e pytest instalados:

```sh
python -m pytest -q
python -m pytest -q tests/test_medicine_service.py tests/test_medicines.py
```

Os testes de serviços usam SQLite com chaves estrangeiras habilitadas e cobrem composição múltipla, edição, rollback, busca, paginação, validação, permissões, triagem e bloqueio de exclusão. Os testes de API cobrem esses fluxos via HTTP, e o teste de migration verifica a triagem inicial pendente em registros existentes. Os testes PostgreSQL existentes exigem um banco isolado e migrado e `PREFLIGHT_POSTGRES_TESTS=1`.

Na pasta `front`:

```sh
npm test
npm run build
```

Os testes de alergias verificam as quatro combinações de estado da triagem e presença de alergias.

## Catálogo inicial e principais indicações

A revisão `b93a4c5d6e7f` adiciona `medicines.main_indications` como texto opcional. O campo é aceito no POST/PATCH de medicamento, retornado nas consultas e editável no frontend. No PATCH, omitir preserva o valor e enviar `null` o limpa.

O catálogo e sua procedência estão em `NASA/data/common_medicines.json` e `NASA/data/README.md`. A seleção reúne 100 itens por país, com 161 medicamentos e 160 princípios ativos distintos após deduplicação. A lista brasileira é uma seleção de uso comum, não um ranking oficial.
