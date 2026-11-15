# Histórico sintético de 50 missões

O comando `scripts.seed_synthetic_missions` cria um conjunto ficcional para validação funcional. Usa os modelos existentes, sem migration. Por padrão, não altera as tabelas públicas de missões, pacientes ou recomendações. As tabelas são criadas com o metadata do projeto em um schema PostgreSQL dedicado, sem fallback de `search_path` para `public`. O corpus público configurado é copiado com seus PDFs, passagens, URLs, revisões, hashes e datas originais. Não são criados documentos de fixture nem referências NASA novas.

## Dados visíveis na aplicação

Para criar as 50 missões no mesmo schema `public` usado pela interface, execute em `back/`:

```bash
docker compose exec -T -e SALUS_SYNTHETIC_ENV=development api python -m scripts.seed_synthetic_missions --publish --evaluate --output data/synthetic_missions_public
```

Depois, atualize a página e selecione **Mission administrator → Rafael Andrade**. Em **Missions**, as 50 missões do histórico vão de `Aurora 01` a `Cruzeiro 05`; esse usuário tem vínculo com todas elas. Para acessar saúde e prontuário, selecione **Physician → Helena Monteiro**. As permissões das contas anteriores são preservadas.

A opção `--publish` adiciona os registros ao banco da aplicação, mantém as missões preexistentes, recusa conflitos de nomes/contas e valida a distribuição somente nas 50 missões do seed. Repetições com os mesmos parâmetros reutilizam o conjunto. Os artefatos públicos ficam em `back/data/synthetic_missions_public/` e usam os IDs reais da aplicação; os artefatos do schema isolado têm IDs independentes. As contagens gerais de tabelas no relatório público incluem os registros preexistentes, enquanto a distribuição de missões é restrita ao seed. O corpus público existente é reutilizado diretamente.

## Execução isolada

Em `back/`, com a aplicação e PostgreSQL migrados:

```bash
docker compose exec -T -e SALUS_SYNTHETIC_ENV=development api python -m scripts.seed_synthetic_missions --evaluate --evidence --output data/synthetic_missions
```

Somente gerar/conferir dados:

```bash
docker compose exec -T -e SALUS_SYNTHETIC_ENV=test api python -m scripts.seed_synthetic_missions --output data/synthetic_missions
```

Repetir o primeiro comando roda/confere as recomendações e os alertas operacionais pelos serviços reais. `--evidence` usa `PredictiveKnowledgeService`, `MissionRagService` e o Ollama configurado. Ausência de corpus disponível no corte ou indisponibilidade do Ollama mantém o fallback determinístico. Sem essa opção, as evidências permanecem pendentes, como no fluxo normal antes do worker.

Parâmetros fixos: `--seed 50`, `--reference 2026-11-15T12:00:00+00:00`, `--schema salus_synthetic_50`. Outra semente/data exige outro schema `salus_synthetic_*`; parâmetros divergentes são recusados. A referência exige timezone e é normalizada para UTC. A variável `SALUS_SYNTHETIC_ENV` deve ser `development` ou `test`; marcadores explícitos de produção em `APP_ENV`, `ENVIRONMENT` ou `ENV` bloqueiam a execução. Essa proteção complementa a separação de credenciais de desenvolvimento; não identifica sozinha um banco de produção mal configurado.

O lock transacional serializa execuções no mesmo namespace. Uma transação externa inclui geração, verificações e avaliações; commits internos dos serviços usam savepoints. Falhas revertem os registros do conjunto, permitindo nova tentativa. O schema vazio pode permanecer. Não existe comando de limpeza. IDs de sequência podem ter lacunas depois de uma falha. As contas usam domínio reservado `example.test` e senha bloqueada (`!`). Não há envio externo; notificações são registros internos sintéticos.

Os arquivos `back/data/synthetic_missions/manifest.json` e `report.json` ficam fora das entradas do motor. O primeiro contém cenário, IDs, corte, contagem por série, IDs de observações disponíveis, expectativa, partição e desfechos posteriores; o segundo contém totais, recomendações e comparação por caso. Nomes/observações consumidos pelo motor não codificam o cenário nem a expectativa.

## Inventário e cobertura

Foram examinados modelos, schemas de entrada, migrations, serviços, rotas preditivas, seeds existentes, testes PostgreSQL e os módulos do frontend. As restrições reais usam missões `planned`, `in_progress`, `completed`; a frota permite apenas uma missão não concluída por nave. Não existe data de embarque individual: o vínculo é `mission_members`, com datas delimitadas pela missão.

| Área/frontend | Dados gerados / capacidade |
| --- | --- |
| Missões e operações | 35 concluídas, 10 em andamento, 5 planejadas; 2–4 astronautas; períodos de 7–180 dias e extensão das missões em andamento; nave reutilizada apenas em períodos históricos separados, frota exclusiva para missões abertas, algumas missões sem nave; módulos habitáveis variados |
| Perfis e permissões | Astronautas exclusivos por missão; médico, administrador, psicólogo, nutricionista, enfermeiro e observador vinculados com flags reais; não é concedido acesso clínico global |
| Exames e prontuário | Requisito pré-voo, agendamento, resultado e revisão aceita; condições preexistentes ficcionais em parte da tripulação; alergias a ingrediente ativo; ocorrências clínicas recuperadas e usos de medicamento posteriores ao corte |
| Saúde | Frequência cardíaca em repouso, pressão, respiração, SpO₂, temperatura, glicemia, sono em minutos, qualidade do sono, fadiga, humor, atenção e AVPU; referências pré-voo próprias; diferenças individuais, variação diária e séries irregulares com registro tardio |
| Saúde mental | Check-ins com campos reais e acompanhamentos semanais; o texto do acompanhamento não é entrada da previsão; a análise utiliza apenas ratings disponíveis |
| Nutrição | Produto composto ficcional, lotes, validade, três refeições diárias, macros, plano nutricional, movimentos imutáveis de recebimento/consumo e saldo reconciliado |
| Riscos operacionais | Planejamento alimentar versionado, projeção FEFO real, vencimento, alertas e notificações internas quando há falta projetada; ocorrências confirmadas nas missões concluídas |
| Inteligência Preditiva | Análises individuais, de missão e nave; snapshots, predictions e recommendation events reais; catálogo, ranking e contraindicações existentes |
| Composição corporal/avaliação física | Não existem tabelas longitudinais de peso, massa magra, gordura, força ou densidade óssea; cenário explicitamente sem avaliação |
| Telemetria/manutenção | Não existem séries ou ordens de manutenção; ocorrência de categoria `spacecraft` não permite previsão antecipada de falha; cenário explicitamente sem avaliação |
| Radiação | Módulo existe, mas não é usado por estas regras preditivas; o seed não simula ingestão de clima espacial externo |

Não há campo dedicado a fase dinâmica da missão; fases são representadas nas ocorrências e pelas datas/estados existentes. Os exames estruturados não representam séries clínicas longitudinais. Não há estoque de medicamentos ou desfecho clínico supervisionado universal. Os registros clínicos e as ocorrências operacionais permanecem separados.

## Cenários e expectativas

Há cinco repetições de cada um dos dez cenários. Os últimos cinco casos têm apenas dados pré-voo no corte, preservando os 5 estados planejados solicitados.

- Estável: ausência de sinais positivos injustificados no corte.
- Isolado: pico fora da janela final de sete dias e retorno à linha de base; ausência de desvio sustentado no corte. Isso não exige que a regra deixe de sinalizar a anomalia no momento do pico.
- Progressivo: aumento da frequência cardíaca de repouso; expectativa de `cardiovascular_resting_heart_rate_shift` e revisão médica.
- Sono/fadiga: menos sono com fadiga crescente; expectativa de `sleep_fatigue_combined` e revisão do repouso.
- Relato mental: estresse crescente e humor reduzido, com acompanhamento posterior; expectativa de suporte psicológico quando houver baseline suficiente.
- Composição corporal: lacuna de schema; não se inventa uma tendência avaliada.
- Alimentos: vencimento próximo, com falta projetada em parte dos períodos; expectativa de verificação do inventário.
- Incidente técnico: ocorrência posterior confirmada; ausência de telemetria impede avaliar antecipação de falha.
- Irregular: referências pré-voo presentes e lacunas extensas durante o voo; a resposta pode ser insuficiência, sem preencher lacunas com normalidade.
- Pares: sinais semelhantes de frequência cardíaca, com ocorrência clínica posterior em um grupo e sem ocorrência registrada em outro; permitem inspecionar divergências entre atenção preventiva e desfecho registrado.

As expectativas são fixadas pelo desenho do caso, não derivadas da saída do recomendador. A matriz principal compara o contrato de regras com os sinais produzidos; `expected_action_found` verifica separadamente a recomendação. Um alerta preventivo seguido de ausência de diagnóstico não é automaticamente um falso positivo clínico. O manifesto distingue confirmação posterior, ausência de evento registrado e seguimento incompleto. Não se atribui capacidade diagnóstica às regras.

## Corte temporal

Cada missão concluída é avaliada dois dias antes do encerramento; missões em andamento e planejadas usam a referência. As avaliações são executadas em ordem cronológica, com relógio controlado no limite dos serviços que já usam `utc_now`, sem alterar o relógio do banco. As análises reais persistem seus runs, snapshots e recomendações. Não há treinamento, ajuste de limiares ou ativação de modelos. Missões 1–30 são desenvolvimento e 31–50 são avaliação; a partição é por missão e preserva a ordem temporal.

A coleta de saúde exige coleta e registro anteriores ao corte. Dias alimentares só entram depois de fechados; check-ins só entram depois da atualização. A agregação de missão exclui runs individuais posteriores ao corte. Ocorrências de todas as missões/naves exigem evento, registro e confirmação disponíveis. O estoque para vencimento é reconstruído do ledger no corte; recebimentos futuros não entram. A condição de missão e a duração são reconstruídas pelas datas. O ranking exclui recommendation outcomes avaliados depois do corte. Os documentos usados em `--evidence` exigem importação e indexação até o corte; não se retrodata o corpus.

Limitações históricas existentes: edição de refeições/check-ins remove versões antigas; configuração e catálogo de ações não têm versionamento temporal completo de aprovação; metadados de nave/módulo não têm data de disponibilidade. O conjunto não edita esses dados depois da criação e não usa modelos supervisionados. O corpus indexado após um corte fica indisponível naquele corte, mesmo que o PDF seja antigo. Não é alegada reprodução histórica de políticas clínicas antigas. A geração usa inserção direta histórica pelos modelos, como os seeds existentes, para preservar datas; as recomendações e os alertas operacionais passam pelos serviços reais. Os alertas clínicos de limiar não são recalculados por este seed, evitando confundir o teste preditivo com esse protocolo separado.

No modo isolado, os dados ficam no schema dedicado e não aparecem automaticamente na instância web que usa `public`. Para utilizá-los na interface existente, use `--publish`, conforme descrito acima. Para inspecionar a interface, use uma instância de desenvolvimento separada apontando seu `search_path` exclusivamente para o schema sintético. Não altere o `search_path` do usuário do banco compartilhado. O comando e os testes cobrem o backend real; não há teste de navegador novo.

## Verificação

```bash
docker compose exec -T -e PREDICTIVE_POSTGRES_TESTS=1 api python -m pytest -q tests/test_synthetic_missions.py tests/test_predictive_engine.py tests/test_predictive_postgres.py
git diff --check
```

As FKs e constraints são verificadas pelo PostgreSQL. O comando confere distribuição e reconcilia cada lote com suas movimentações. Os testes adicionais verificam cronologia, ausência de sobreposição na nave histórica, estados no corte e exclusão de análises, eventos e confirmações futuros. Reexecute o comando completo para conferir idempotência dos registros do seed e recomendações.

## Resultado da execução local

A geração real em PostgreSQL confirmou **50 missões (35/10/5)**, 155 usuários, 449 vínculos, 102.132 observações de saúde, 7.319 check-ins, 997 acompanhamentos semanais, 21.672 refeições e 21.722 movimentações de estoque. Foram registrados 51 históricos/ocorrências clínicas e 35 ocorrências operacionais. Os 50 lotes tiveram seus saldos reconciliados.

Na comparação funcional com as regras: **23 verdadeiros positivos, 14 verdadeiros negativos, 0 falsos positivos, 0 falsos negativos e 13 casos sem avaliação**. Os casos sem avaliação são os cenários sem schema de composição corporal/telemetria e os casos somente pré-voo. Todas as ações esperadas nos casos avaliáveis foram encontradas, inclusive sugestões abertas reutilizadas por idempotência. Essas contagens não medem eficácia clínica nem capacidade de prever diagnósticos.

A repetição com a implementação final preservou os totais de origem, 291 runs acumulados, 147 recomendações e as notificações, sem criar novos registros. O banco contém 147 recomendações, 2 alertas operacionais e 2 notificações internas. A avaliação documental dos casos do manifesto encontrou 11 recomendações documentadas e 37 sem evidência disponível no corte; 99 sugestões de outros tripulantes/missões/naves permaneceram pendentes de enriquecimento, pois `--evidence` avalia os sujeitos escolhidos no manifesto. O corpus copiado tem 16 documentos. Nenhuma fonte foi retrodatada.

A suíte de Inteligência Preditiva, riscos e testes adicionais passou **57 testes, com 1 teste opcional de Ollama ignorado**. A avaliação do seed com `--evidence` utilizou o Ollama configurado, independentemente desse teste opcional. Após o ajuste de preservação das unidades do saldo histórico, o conjunto direcionado passou novamente 19 testes. `git diff --check` e compilação dos novos módulos Python passaram.

Arquivos da implementação: `back/scripts/seed_synthetic_missions.py`; coleta/estado histórico em `predictive/data_collection.py`; estoque, agregação e recorrência em `predictive/mission_risk.py`; corte dos resultados no ranking em `predictive/recommendations.py` e `predictive_service.py`; consulta documental em `mission_rag.py` e `predictive/knowledge.py`; testes `test_synthetic_missions.py` e ajuste de ledger em `test_predictive_postgres.py`; este documento e os artefatos `back/data/synthetic_missions/manifest.json` e `report.json`.

## Publicação no banco da interface

A execução com `--publish` gravou as 50 missões no schema `public`, IDs **216–265**, e preservou as **6 missões anteriores**. A API real `GET /v1/missions?per_page=100`, com o usuário `Equipe Sintética mission_admin`, respondeu HTTP 200 com exatamente 50 missões visíveis, de `Salus Synthetic 001` a `Salus Synthetic 050`, distribuídas em 35 concluídas, 10 em andamento e 5 planejadas. A avaliação nesse banco manteve 23 verdadeiros positivos, 14 verdadeiros negativos e 13 casos sem avaliação, sem falsos positivos/negativos no contrato de regras. Os novos artefatos estão em `back/data/synthetic_missions_public/`.

A correção adiciona `--publish` ao gerador, restringe a verificação da distribuição e dos saldos aos IDs sintéticos e confere que as missões preexistentes continuam presentes. O teste de coexistência com registros anteriores passou junto aos outros testes do gerador: **6 testes aprovados**. A opção isolada continua disponível para testes sem inserção na interface.

## Nomes de apresentação e exportação

O preparo de exportação, os nomes ficcionais plausíveis, a rastreabilidade externa e a restauração do banco completo estão documentados em [DATABASE_EXPORT.md](DATABASE_EXPORT.md). Após esse preparo, `--publish` reconhece os mesmos IDs pelo registro externo `presentation.json`, preservando a idempotência mesmo com os nomes novos. Os antigos nomes citados nos resultados históricos acima correspondem à execução anterior ao preparo.
