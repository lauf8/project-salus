# Banco Salus para importação

`salus_database_20261115.dump` contém todo o schema da aplicação (`public`), com suas tabelas, sequências, funções, índices, constraints, registros, documentos e revisão Alembic. Inclui as 56 missões: as 50 do histórico gerado e as 6 anteriores. Os schemas auxiliares de testes não estão no arquivo.

As missões e equipes do histórico usam nomes ficcionais plausíveis, como Aurora 01 e Rafael Andrade. A origem gerada das 50 missões está documentada em `provenance.json`, separadamente do banco. Isso não transforma os registros em dados clínicos ou missões reais. As referências documentais originais, incluindo seus PDFs e fontes, foram preservadas.

## Restaurar

Use as ferramentas do PostgreSQL 17, apontando para um banco novo e vazio:

```bash
createdb -U SEU_USUARIO salus_import
pg_restore -U SEU_USUARIO --clean --if-exists --no-owner --no-acl --exit-on-error --dbname=salus_import salus_database_20261115.dump
```

Configure o `PGDATABASE` da aplicação para o banco restaurado. As credenciais do PostgreSQL e outras variáveis de ambiente não fazem parte deste pacote.

Na interface, selecione **Mission administrator → Rafael Andrade** para as 50 missões do histórico, ou **Physician → Helena Monteiro** para saúde e prontuário. Os perfis anteriores também foram preservados. Os endereços de contato gerados usam o domínio reservado `crew.salus.example`.

## Conferência

`SHA256SUMS` permite conferir os arquivos. `restore-validation.json` registra a conferência executada após restaurar o dump em outro banco PostgreSQL.

Antes da exportação, a comparação com o backup verificou 189.691 registros em 62 tabelas sem alterações em valores numéricos, datas de origem, chaves, vínculos ou dados binários. O horário de enriquecimento automático de recomendações é atualizado pelo worker e foi excluído dessa comparação. Códigos técnicos dos protocolos e origens de telemetria foram preservados; não são rótulos de apresentação. Nove testes do preparo de exportação e do gerador passaram.

## Caso com análise de IA

A exportação atualizada inclui Matheus Valença na missão Atlântico 03, com cinco alertas clínicos, duas notificações internas e três recomendações com explicações efetivamente geradas e validadas pelo Ollama, usando referências NASA. Abra Physician → Helena Monteiro → Predictive Intelligence e selecione Matheus. Expanda as evidências documentais das recomendações. A origem do caso e seus IDs estão em `ai-health-case.json`. A avaliação clínica separada não produziu hipóteses diagnósticas e não recebeu aprovação automática.
