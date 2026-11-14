# Clima espacial (NASA DONKI)

O módulo importa do NASA DONKI os flares (FLR), as ejeções de massa coronal (CME) e os eventos de partículas solares energéticas (SEP), guarda as ligações entre eles e prepara as tabelas de exposição à radiação.

A fundamentação vem do NASA SP-2009-3405, capítulo 5 (*Risk of Acute Radiation Syndromes Due to Solar Particle Events*). Flares e CMEs são **precursores**; o SEP é o evento de **exposição**. A resposta da API traz esse papel em `health_relevance` (`precursor` ou `exposure`). Um evento no DONKI não significa que um tripulante recebeu dose relevante: a dose depende da intensidade, da localização da nave, da blindagem e da atividade do tripulante (EVA, IVA ou abrigo).

## Configuração

Defina `NASA_API_KEY` no `.env`. A chave gratuita é obtida em https://api.nasa.gov. Sem ela, usa-se `DEMO_KEY`, que tem limite baixo de requisições por hora e por dia. Variáveis opcionais: `DONKI_BASE_URL` e `DONKI_TIMEOUT_SECONDS`.

Aplique a migration `f9a1b2c3d4e5`:

```sh
docker compose exec api alembic upgrade head
```

## Tabelas

| Tabela | Uso |
| --- | --- |
| `space_weather_events` | Evento FLR/CME/SEP com o ID do DONKI (`activity_id`, único), horários, classe do flare e pico de fluxo de raios X (W/m²), dados da análise de CME marcada como mais precisa, instrumentos, versão e o JSON original em `raw`. |
| `space_weather_event_links` | Ligações `linkedEvents`. O evento ligado pode ser de tipo não importado (IPS, GST...); o tipo é extraído do ID. |
| `space_weather_sync_runs` | Cada consulta ao DONKI, com contagens e erro, inclusive falhas. |
| `proton_flux_readings` | Fluxo integral de prótons (GOES/NOAA SWPC) por canal de energia, em pfu. Ainda sem importação. |
| `crew_activities` | Onde cada tripulante estava: `iva`, `eva` ou `storm_shelter`. Ainda sem API. |
| `radiation_exposure_limits` | Limites por órgão e período, versionados por perfil. |
| `radiation_dose_records` | Dose por tripulante, órgão e período, com origem `dosimeter`, `model_estimate` ou `simulation`. Ainda sem API. |
| `radiation_follow_ups` | Janela de 48 h após um SEP relevante, com sintomas prodrômicos (náusea, vômito, anorexia, fadiga) e pele em caso de EVA. Ainda sem API. |

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

## Verificação

```sh
pytest tests/test_space_weather.py
```

Os testes usam respostas simuladas no formato do DONKI (cadeia de 26/10/2024: flare X1.8, CME e SEP) e não acessam a internet.
