# Monitoramento de saúde

O astronauta autenticado abre o painel de monitoramento como página inicial. O perfil de astronauta também é reconhecido pelo vínculo `astronaut` de contas anteriores. Médicos acessam o painel pelo menu e escolhem a missão e o astronauta autorizado. A interface usa os componentes e a paleta azul existentes, SVG nativo e Recharts.

Os registros de monitoramento são independentes dos resultados de exames. O astronauta pode acrescentar medições próprias, mas continua sem autorização para modificar exames pré-missão. Observações de monitoramento são preservadas: não há endpoints de edição ou exclusão.

## Dados e permissões

Cada observação contém astronauta, missão opcional, indicador, valores, coleta em UTC, registro em UTC, origem, responsável, observação opcional e identificação de referência pré-missão. Pressão arterial usa sistólica e diastólica na mesma linha. Sono usa minutos inteiros; o formulário e a apresentação usam horas e minutos. Início e fim da sessão de sono são preservados e a duração é derivada, sem aceitar duração contraditória.

O backend valida formato, domínio das escalas, campos incompatíveis, datas com fuso, coleta futura e pares obrigatórios. Esses limites validam os dados; não classificam risco clínico.

O astronauta lê e registra apenas os próprios dados. Um médico com vínculo `flight_surgeon` pode consultar e registrar dados de outro astronauta da mesma missão, sempre com `mission_id` explícito. Um administrador da missão não recebe acesso clínico por ser administrador. AVPU e referências pré-missão exigem outro médico de voo autorizado. Médicos que também são astronautas não podem registrar AVPU em si mesmos.

A API reconhece `self_report`, `manual_measurement` e `device`. Não existe fonte de dispositivos no repositório; a criação com `device` é rejeitada até haver integração. A interface permite autorrelato e medição manual.

## Endpoints

Todos usam a autenticação bearer JWT existente e o prefixo `/v1`.

| Método | Caminho | Uso |
| --- | --- | --- |
| GET | `/health/context` | Elegibilidade própria e astronautas sob acompanhamento nas missões autorizadas |
| POST | `/health/astronauts/{user_id}/observations` | Acrescentar observação validada |
| GET | `/health/astronauts/{user_id}/summary` | Os 11 indicadores, leitura atual, anterior, referência, variações e permissões |
| GET | `/health/astronauts/{user_id}/history` | Histórico paginado por indicador e período |

`user_id` identifica `users.id`, não `mission_members.id`. O histórico exige `indicator` e aceita `mission_id`, `start`, `end`, `page` e `per_page` (máximo 100). Datas devem incluir fuso. Sem período, consulta os últimos 30 dias. A interface percorre todas as páginas e oferece 24 horas, 7 dias e 30 dias. Sem missão, o próprio astronauta consulta seu conjunto de observações; consultas médicas exigem uma missão e não incluem observações fora dela.

Exemplo de corpo para frequência cardíaca:

```json
{
  "indicator": "heart_rate",
  "value": 72,
  "collected_at": "2026-11-11T12:00:00Z",
  "source": "manual_measurement",
  "mission_id": null,
  "note": null
}
```

Indicadores: `heart_rate`, `blood_pressure`, `respiratory_rate`, `oxygen_saturation`, `body_temperature`, `consciousness`, `sleep_duration`, `sleep_quality`, `fatigue`, `mood`, `attention`.

Para pressão arterial, envie `systolic` e `diastolic` sem `value`. Para AVPU, envie `category` com `alert`, `voice`, `pain` ou `unresponsive`. Para atenção, `better`, `usual` ou `worse`. Para sono, envie `value` em minutos ou o par `sleep_started_at`/`sleep_ended_at`. A origem de AVPU deve ser `manual_measurement`.

## Referências e tendências

Os exames pré-missão existentes têm resumo clínico em texto; não oferecem medidas estruturadas que possam ser comparadas com segurança. Não há extração automática desse texto. Um médico de voo autorizado pode registrar uma observação com `is_preflight_reference=true`, vinculada à missão e coletada antes do início efetivo, ou do lançamento previsto enquanto não há início efetivo.

O resumo usa a referência mais recente do mesmo indicador e missão, anterior ou igual à coleta da leitura atual. As variações numéricas são diferenças absolutas, mantendo as duas componentes da pressão arterial. AVPU e atenção oferecem sequências, sem converter categorias em pontuações. Ausências são retornadas como `null` ou listas vazias e exibidas como “Sem dados”.

Histórico e resumo usam `collected_at`, depois `recorded_at` e ID para desempate. Um registro retroativo não substitui uma coleta mais recente. As tendências descrevem aumento, redução, estabilidade ou variação em sentidos diferentes das duas pressões, sem diagnosticar ou sugerir limites clínicos.

Os gráficos preservam todos os pontos, sem médias ou interpolação. Intervalos sem observações recebem pontos nulos em janelas de 1 hora, 6 horas ou 1 dia, conforme o período. A duração dessas janelas é uma regra de apresentação explícita, sem presumir frequência clínica de coleta. A tabela conserva valores e datas de cada observação. As linhas usam `connectNulls=false`, conforme a [API do Recharts](https://recharts.github.io/en-US/api/Line/).

## Execução

Em uma instalação com histórico de migrations íntegro:

```sh
cd NASA
docker compose up --build -d
docker compose exec -T api alembic upgrade head
cd ../front
npm install
npm run dev
```

O Vite encaminha `/api` para a API na porta 8000. Abra a porta informada pelo Vite (5173, ou a próxima disponível).

A base original desta máquina continua com a revisão ausente `7efe7ee6f54f`. Ela não foi alterada. A instância usada nesta implementação é `nasa-front-validation-api`, na porta 8000, com o banco separado `nasa_front_validation_20261111`. A migration de saúde também foi verificada no banco separado `nasa_health_migration_20261111`, com upgrade, downgrade e novo upgrade, preservando o usuário anterior.

## Verificação

Backend, em banco de desenvolvimento separado e migrado:

```sh
cd NASA
docker compose exec -T api pip install pytest
docker compose exec -T -e PGDATABASE=nasa_front_validation_20261111 api alembic upgrade head
docker compose exec -T -e PGDATABASE=nasa_front_validation_20261111 api alembic check
docker compose exec -T -e PGDATABASE=nasa_front_validation_20261111 -e PREFLIGHT_POSTGRES_TESTS=1 api python -m pytest -q tests/test_health_postgres.py tests/test_preflight_postgres.py tests/test_auth.py tests/test_user_profiles.py
```

Frontend:

```sh
cd front
npm test
npm run build
npx playwright install chromium
HEALTH_TEST_URL=http://127.0.0.1:5174 npm run test:health:e2e
```

O teste de navegador exige backend e Vite ativos. Cria contas e uma missão fictícias no banco da API local. Use banco separado. As capturas são gravadas em `/tmp/nasa-health-e2e` ou em `HEALTH_TEST_ARTIFACTS`. Para usar Chrome instalado, defina `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`.

## Arquivos desta implementação

Backend:

- `NASA/app/models/health.py`
- `NASA/app/schemas/health.py`
- `NASA/app/services/health_service.py`
- `NASA/app/routers/health.py`
- `NASA/app/main.py`
- `NASA/alembic/env.py`
- `NASA/alembic/versions/f718293a4b5c_add_health_observations.py`
- `NASA/tests/test_health_postgres.py`
- `NASA/README.md`

Frontend:

- `front/src/HealthDashboard.jsx`
- `front/src/health-indicators.js`
- `front/src/health.css`
- `front/src/main.jsx`
- `front/tests/health.test.js`
- `front/scripts/verify-health.mjs`
- `front/package.json`
- `front/package-lock.json`
- `front/README.md`

Documentação: `HEALTH_MONITORING.md`.

## Estruturas ainda ausentes

Não existem dispositivos conectados, valores estruturados nos resultados pré-missão nem regras clínicas configuradas e validadas. Esses pontos permanecem explícitos: sem simular sensores, extrair referências de texto ou emitir alertas clínicos. A acumulação de papéis de astronauta e médico na mesma missão ainda não existe no módulo pré-missão; o monitoramento reconhece o perfil duplo da conta, mas mantém a exigência de outro avaliador para AVPU.

## Resultado da verificação desta implementação

- 89 testes do backend aprovados, com 6 testes opcionais de conhecimento desativados.
- Testes do frontend e build de produção aprovados.
- Teste real de navegador aprovado no desktop e em 390 px: login inicial do astronauta, 11 hotspots/cartões, seleção por teclado, registro dos 11 indicadores, duas séries de pressão arterial, sono em horas/minutos e por sessão, coleta retroativa, filtro de 24 horas, linha do tempo categórica, avaliação AVPU por médico autorizado e bloqueio entre astronautas.
- Nenhum erro JavaScript durante o fluxo verificado.
- Upgrade, downgrade e novo upgrade da migration preservaram o usuário anterior no banco isolado.
- `alembic check` não encontrou diferenças entre o schema migrado e os modelos.

Capturas locais: `/tmp/nasa-health-e2e/desktop.png` e `/tmp/nasa-health-e2e/mobile.png`.

## Demonstração com dados fictícios

O comando abaixo cria contas de demonstração e 468 observações para os 11 indicadores, incluindo referências pré-missão, histórico de 30 dias e lacunas. Uma nova execução não duplica as observações. O script aceita apenas bancos com `validation`, `demo` ou `test` no nome.

```sh
cd NASA
docker compose exec -T -e PGDATABASE=nasa_front_validation_20261111 api python -m scripts.seed_health_demo
```

Acesse http://localhost:5174 com `astronauta.demo@example.com` e senha `NasaDemo2026!`. Para a visão médica, use `medica.demo@example.com` com a mesma senha e selecione a missão de demonstração e o astronauta. Todos os registros gerados são identificados como fictícios. O script está em `NASA/scripts/seed_health_demo.py`.
