# Exportação do banco da aplicação

O preparo troca rótulos de demonstração por nomes ficcionais plausíveis, mantendo a origem gerada em um registro externo. Não atribui autenticidade clínica ou histórica aos dados. Os documentos de referência e códigos técnicos de protocolos/origens permanecem originais.

O banco ativo mantém 56 missões: 50 do histórico gerado e 6 anteriores. As novas missões vão de Aurora 01 a Cruzeiro 05. Na interface, Rafael Andrade tem o perfil Mission administrator e Helena Monteiro tem o perfil Physician.

## Preparar nomes

Em `back/`, faça primeiro um backup do banco e execute:

```bash
docker compose exec -T -e SALUS_SYNTHETIC_ENV=development api python -m scripts.prepare_database_export
```

O script usa `data/synthetic_missions_public/manifest.json` para conferir os 50 IDs e registra a relação entre nomes anteriores e atuais em `data/synthetic_missions_public/presentation.json`. O registro fica fora do banco e contém a configuração original e a origem dos dados. Repetições conferem os IDs/nomes e não recriam nem renomeiam novamente o conjunto. O gerador `--publish` também usa esse registro para evitar duplicação após a troca dos nomes. Preserve esses arquivos ao continuar o desenvolvimento.

Os nomes de tripulantes são determinísticos e os contatos usam o domínio reservado `crew.salus.example`. As substituições em snapshots JSON preservam valores numéricos, datas e referências por ID. Fontes documentais não são reescritas. Campos técnicos como `profile_id`, `rule_version`, códigos e origem de telemetria são preservados. O preparo exige ambiente de desenvolvimento/teste e é transacional.

## Exportar

O pacote local está em `back/exports/`. Essa pasta é ignorada pelo Git. Para repetir a exportação, substitua `SEU_BANCO` pelo banco configurado na API:

```bash
mkdir -p exports
docker compose exec -T -e SOURCE_DATABASE=SEU_BANCO db sh -c 'pg_dump -U "$POSTGRES_USER" --no-owner --no-acl --schema=public -Fc "$SOURCE_DATABASE"' > exports/salus_database.dump
```

A exportação inclui todas as tabelas e registros do schema da aplicação, sequências, funções, índices, constraints, PDFs, passagens e revisão Alembic. Schemas auxiliares de validação ficam fora, evitando duplicar o histórico. Credenciais de ambiente não são exportadas. Os registros de usuários e permissões existentes fazem parte do banco solicitado.

O pacote `salus_database_20261115.zip` contém o dump PostgreSQL, instruções de restauração, hashes SHA-256, o manifesto externo de origem e o resultado da verificação de restauração.

## Verificações executadas

- A API retornou HTTP 200 e as 50 missões com os novos nomes para Rafael Andrade; as 6 missões anteriores continuam presentes.
- Comparação com o backup: 189.691 registros, 62 tabelas, sem alterações nos valores numéricos, datas de origem, chaves, vínculos ou binários. O horário de enriquecimento automático das recomendações pelo worker foi excluído dessa comparação.
- O dump foi restaurado em outro banco PostgreSQL e conferido com os 50 IDs, nomes e saldos do histórico e com as 56 missões totais.
- Testes: `tests/test_database_export.py` e `tests/test_synthetic_missions.py`, com `PREDICTIVE_POSTGRES_TESTS=1`: 9 aprovados. Compilação Python e `git diff --check` passaram.

A correspondência de nomes e os desfechos esperados permanecem fora das entradas do recomendador. As métricas anteriores continuam sendo verificações funcionais com dados gerados, não validação clínica.
