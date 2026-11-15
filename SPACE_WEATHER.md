# Clima espacial (NASA DONKI)

O módulo importa do NASA DONKI os flares (FLR), as ejeções de massa coronal (CME) e os eventos de partículas solares energéticas (SEP), guarda as ligações entre eles e prepara as tabelas de exposição à radiação.

A fundamentação vem do NASA SP-2009-3405, capítulo 5 (*Risk of Acute Radiation Syndromes Due to Solar Particle Events*). Flares e CMEs são **precursores**; o SEP é o evento de **exposição**. A resposta da API traz esse papel em `health_relevance` (`precursor` ou `exposure`). Um evento no DONKI não significa que um tripulante recebeu dose relevante: a dose depende da intensidade, da localização da nave, da blindagem e da atividade do tripulante (EVA, IVA ou abrigo).

## Configuração

Defina `NASA_API_KEY` no `.env`. A chave gratuita é obtida em https://api.nasa.gov. Sem ela, usa-se `DEMO_KEY`, que tem limite baixo de requisições por hora e por dia. Variáveis opcionais: `DONKI_BASE_URL` e `DONKI_TIMEOUT_SECONDS`.

Aplique as migrations `f9a1b2c3d4e5` e `0b7c1d2e3f40`:

```sh
docker compose exec api alembic upgrade head
```

## Tabelas

| Tabela | Uso |
| --- | --- |
| `space_weather_events` | Evento FLR/CME/SEP com o ID do DONKI (`activity_id`, único), horários, classe do flare e pico de fluxo de raios X (W/m²), dados da análise de CME marcada como mais precisa, instrumentos, versão e o JSON original em `raw`. |
| `space_weather_event_links` | Ligações `linkedEvents`. O evento ligado pode ser de tipo não importado (IPS, GST...); o tipo é extraído do ID. |
| `space_weather_sync_runs` | Cada consulta ao DONKI, com contagens e erro, inclusive falhas. |
| `proton_flux_readings` | Fluxo integral de prótons (GOES/NOAA SWPC) por canal de energia, em pfu. Fonte `noaa_swpc` ou `simulation`. |
| `crew_activities` | Onde cada tripulante estava: `iva`, `eva` ou `storm_shelter`. |
| `radiation_exposure_limits` | Limites por órgão e período, versionados por perfil. |
| `radiation_dose_records` | Dose por tripulante, órgão e período, com origem `dosimeter`, `model_estimate` ou `simulation`. |
| `radiation_follow_ups` | Janela de 48 h após um SEP, aberta para quem estava em EVA, com os sintomas relatados. |
| `radiation_symptom_reports` | Cada relato de sintomas na janela, do formulário ou de uma medição de saúde. |
| `radiation_alerts` | Alertas de radiação. Tabela própria porque `health_alerts` exige uma medição de origem. |

A migration carrega o perfil `nasa-sp-2009-3405-table-5-1`, que reproduz a Tabela 5-1 do livro (2009). A NASA revisou esses limites depois (NASA-STD-3001); para valores atuais, crie um novo perfil em vez de alterar o existente.

## Endpoints

Prefixo `/v1/space-weather`, autenticação bearer JWT.

| Método | Caminho | Uso |
| --- | --- | --- |
| POST | `/sync` | Importa do DONKI. Corpo: `start_date`, `end_date` (até 366 dias) e `event_types` (padrão `FLR`, `CME`, `SEP`). Exige médico vinculado como `flight_surgeon` ou `mission_admin` em alguma missão. |
| GET | `/sync-runs` | Últimas sincronizações. |
| GET | `/events` | Lista paginada. Filtros: `event_type`, `start` e `end` (com fuso). |
| GET | `/events/{activity_id}` | Evento com as ligações nos dois sentidos; eventos ligados não importados aparecem com `stored=false`. |
| GET | `/missions/{mission_id}/events` | Eventos que se sobrepõem ao período da missão. Exige vínculo com a missão. |
| GET | `/exposure-limits` | Limites de dose; filtro opcional `profile_id`. |

Exemplo:

```json
POST /v1/space-weather/sync
{"start_date": "2024-10-01", "end_date": "2024-11-14", "event_types": ["FLR", "CME", "SEP"]}
```

O intervalo é consultado em janelas de 30 dias. Cada tipo é gravado numa transação própria: se um tipo falha, os outros continuam e a falha fica registrada. Se todos falham, a resposta é 502. Uma nova sincronização do mesmo período não duplica eventos; versões revisadas pelo DONKI atualizam os campos e substituem as ligações.

## Sincronização agendada

```sh
docker compose exec api python -m scripts.sync_space_weather --days 7
docker compose exec api python -m scripts.sync_space_weather --start 2024-10-01 --end 2024-11-14 --types SEP
```

O script retorna código 1 se algum tipo falhar.

## Fluxo de radiação

Prefixo `/v1/radiation`. Tela: aba **Radiation** da missão.

1. **Atividade da tripulação.** O astronauta (para si), o médico de voo ou o administrador da missão registra IVA, EVA ou abrigo. Atividades do mesmo astronauta não podem se sobrepor e devem estar dentro do período da missão.
2. **SEP em EVA.** Ao importar um SEP pelo DONKI (API ou script), o sistema procura EVAs que cobrem o início do SEP. Uma EVA sem fim só conta se começou até 12 h antes. Para cada tripulante encontrado, abre um acompanhamento com janela de 48 h a partir do início do SEP e cria o alerta `sep_during_eva`. Uma EVA registrada depois da importação também dispara a verificação. Também há reprocessamento manual em `POST /events/{activity_id}/process`.
3. **Sintomas.** Náusea, vômito, perda de apetite, fadiga e pele (`nausea`, `vomiting`, `anorexia`, `fatigue`, `skin_erythema`) entram na lista de sintomas das medições de saúde. Se a medição cai dentro de uma janela aberta, vira um relato do acompanhamento. Os relatos também podem ser feitos diretamente no acompanhamento.
4. **Fluxo de prótons.** `POST /proton-flux/sync` importa o fluxo integral do GOES pela NOAA SWPC. O serviço só publica os últimos 7 dias, então agende `python -m scripts.sync_proton_flux`. Para eventos passados ou demonstrações, `POST /proton-flux/simulate` gera um perfil sintético de ≥10 MeV para um SEP.
5. **Doses.** O médico de voo registra doses medidas ou estimadas (`POST /missions/{id}/doses`) ou gera doses simuladas (`POST /missions/{id}/doses/simulate`). A simulação integra o fluxo ≥10 MeV com a atividade de cada tripulante e é **didática**: 0,02 mGy-Eq/h por pfu na pele em EVA, blindagem de 0,15 em IVA e 0,05 no abrigo, e fatores por órgão. Não é dosimetria. `GET /missions/{id}/astronauts/{id}/dose-summary` compara a dose acumulada com o perfil de limites.

### Alertas

| Regra | Quando | Severidade |
| --- | --- | --- |
| `sep_during_eva` | Tripulante em EVA no início do SEP | urgente; crítico se o pico ≥10 MeV nas 48 h for ≥ 1000 pfu (S3) |
| `proton_flux_during_eva` | Fluxo ≥10 MeV ≥ 10 pfu (S1) durante uma EVA | atenção (S1), urgente (S2), crítico (S3+) |
| `prodromal_vomiting` | Vômito na janela de 48 h | crítico |
| `prodromal_symptoms` | Náusea, perda de apetite ou fadiga na janela | urgente |
| `skin_reaction` | Reação de pele na janela | urgente |
| `late_symptoms` | Sintomas relatados depois da janela | atenção |
| `dose_limit` | Dose acumulada ≥ 50%, 75% ou 100% do limite | atenção, urgente, crítico |

Os limiares são de simulação. Há um alerta ativo por astronauta e regra lógica: um novo achado mais grave eleva a severidade e reabre o alerta. O astronauta pode reconhecer os próprios alertas; só o médico de voo os resolve e encerra o acompanhamento. Alertas de radiação ainda não geram notificações na central de notificações.

### Endpoints

| Método | Caminho | Uso |
| --- | --- | --- |
| GET | `/missions/{id}/timeline` | Eventos do período, cadeias flare → CME → SEP, atividades, acompanhamentos e alertas ativos (estes só para o médico de voo ou o próprio astronauta). |
| GET, POST | `/missions/{id}/crew-activities` | Lista e registra atividades. |
| POST | `/missions/{id}/crew-activities/{activity_id}/end` | Encerra uma atividade. |
| GET, POST | `/missions/{id}/doses` | Lista e registra doses. |
| POST | `/missions/{id}/doses/simulate` | Doses simuladas a partir do fluxo. |
| GET | `/missions/{id}/astronauts/{astronaut_id}/dose-summary` | Dose acumulada × limites. |
| GET | `/missions/{id}/follow-ups[/{follow_up_id}]` | Acompanhamentos. |
| POST | `/missions/{id}/follow-ups/{follow_up_id}/reports` | Relato de sintomas. |
| POST | `/missions/{id}/follow-ups/{follow_up_id}/close` | Encerramento pelo médico de voo. |
| GET | `/missions/{id}/alerts` | Alertas (`status`: `active`, `open`, `acknowledged`, `resolved`, `all`). |
| POST | `/missions/{id}/alerts/{alert_id}/acknowledge`, `/resolve` | Reconhecer e resolver. |
| POST | `/events/{activity_id}/process` | Reprocessa um SEP. |
| GET | `/proton-flux` | Leituras por canal e período. |
| POST | `/proton-flux/sync`, `/proton-flux/simulate` | Importação da NOAA SWPC e simulação. |

Variáveis opcionais: `SWPC_BASE_URL`, `SWPC_GOES_SATELLITE` (`primary` ou `secondary`) e `SWPC_TIMEOUT_SECONDS`.

## Cenário de demonstração

Em um banco de desenvolvimento migrado, sem acesso à internet:

```sh
docker compose exec api python -m scripts.seed_radiation_demo
```

Cria a missão "Radiation Demo" com uma cadeia fictícia flare X2.3 → CME → SEP de 10 horas atrás, a EVA de uma astronauta durante o SEP (com janela de 48 h aberta), fluxo e doses simulados e um relato de sintomas. No topo da tela, escolha o Perfil **Physician** e o Usuário **Dr. Rivera** (médico de voo), ou o Perfil **Astronaut** e a Usuária **Ada Lima**. Depois abra Missions → Radiation Demo → aba Radiation.

## Verificação

```sh
pytest tests/test_space_weather.py tests/test_radiation.py
```

Os testes usam respostas simuladas no formato do DONKI (cadeia de 26/10/2024: flare X1.8, CME e SEP) e não acessam a internet.
