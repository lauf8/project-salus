# Demonstração completa do monitoramento

Execute na pasta `NASA`, com os serviços Docker ativos e o banco já migrado:

```bash
docker compose exec api python -m scripts.seed_full_demo --apply
```

Para apenas listar as tabelas reais e suas contagens:

```bash
docker compose exec api python -m scripts.seed_full_demo
```

A conta nova usa o login `demo.monitoramento@example.com` e a senha
`Monitoramento2026!`. Ela tem os perfis médico e astronauta. As permissões por
missão são preservadas: a mesma conta é administradora na missão Administração,
médica de voo em Atendimento médico e astronauta em Meu monitoramento.
Selecione a missão correspondente à função que deseja testar.

São criadas quatro contas fictícias, três missões, cinco tipos de exame, quinze
requisitos, quinze itens de checklist, nove resultados e seis revisões. Os
checklists mostram os cinco estados: pendente, agendado, aguardando revisão,
repetição solicitada e concluído. São adicionadas 990 observações em trinta dias,
com os onze indicadores e referências individuais para comparação nos painéis.
As três contas auxiliares também usam a senha inicial acima.

O script usa os serviços e validações da aplicação. Reexecuções mantêm contas,
senhas e amostras existentes; completam dados faltantes sem apagar registros.
Cada serviço confirma sua própria transação: uma interrupção pode deixar carga
parcial, que pode ser completada executando novamente. As datas das séries são
mantidas em reexecuções. Os dados são identificados como fictícios.

## Tabelas identificadas nos modelos

| Tabela | Finalidade |
| --- | --- |
| users | Usuários, perfis e senhas protegidas por hash |
| missions | Missões e datas |
| mission_members | Vínculos e permissões por missão |
| exam_types | Catálogo de exames |
| mission_exam_requirements | Exames exigidos em cada missão |
| astronaut_exams | Checklist individual e agendamentos |
| exam_results | Resultados e autoria |
| exam_result_reviews | Revisões e decisões |
| health_observations | Medições, autorrelatos e referências |
| knowledge_documents | Documentos de referência NASA |
| knowledge_passages | Trechos e tópicos da base de referência |
| revoked_tokens | Sessões revogadas |

O Alembic também mantém `alembic_version` para controle de migração. A base de
conhecimento usa os documentos reais do `knowledge_seed.json`, carregados pelo
setup normal; o script de demonstração não os substitui por conteúdo fictício.
Tokens revogados são gerados pelo logout, sem inserir sessões falsas.

## Banco configurado e validação

A API seleciona seu banco por `NASA_DATABASE` no `.env`, com fallback para
`POSTGRES_DB`. Nesta instalação, `NASA_DATABASE=nasa_front_validation_20261111`
aponta para o banco existente do monitoramento. O `app_db` pertence a outro
sistema e foi preservado, incluindo sua migração `7efe7ee6f54f`.
Não remova volumes nem altere o versionamento Alembic para contornar esse erro.

A carga foi executada no PostgreSQL e validou os cinco estados de checklist e
os onze indicadores nas três missões. O login pela API foi validado e retornou
as três missões de demonstração para a conta principal.
