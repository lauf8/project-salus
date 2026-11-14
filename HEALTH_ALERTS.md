# Alertas de saúde

A avaliação é determinística e não usa IA, diagnóstico, prescrição ou recomendação de medicamentos. As faixas são um perfil de simulação, e não regras clínicas universais.

## Configuração

O arquivo `NASA/app/config/health_alert_profiles.json` contém os perfis `simulation-v1` e `simulation-v2`, as faixas, as sequências de dias/noites e as janelas de atualização das medições. Para alterar faixas de simulação, crie uma nova versão no arquivo e atualize os perfis aceitos no schema. Não substitua a definição de uma versão já utilizada. Cada medição avaliada e cada alerta guardam uma cópia do perfil usado; os eventos guardam a versão.

No monitoramento, selecione uma missão e use **Configurar perfil da missão**. Médicos vinculados como `flight_surgeon` ou `mission_admin` podem configurar:

- Fuso IANA da missão, como `America/Bahia`.
- Canal de emergência.
- Limites de SpO₂ aprovados pela equipe médica.
- Limites opcionais de glicemia alta por contexto: jejum, após refeição ou contexto desconhecido.
- Registro da aprovação médica.

Cada alteração gera uma nova revisão. Alterações concorrentes exigem recarregar a configuração pela revisão esperada. O padrão atual é `simulation-v2`, em UTC, com alerta urgente de glicemia ≥300 mg/dL nos contextos jejum, após refeição e desconhecido. Esses limites estão explicitamente configurados para a simulação. O perfil `simulation-v1` é preservado sem regra padrão de glicemia alta; configurações de missão já aprovadas não são substituídas. Sem missão selecionada, usa-se o perfil padrão em UTC.

## Medições

O formulário apresenta apenas os campos pertinentes ao indicador. Glicemia pede valor, contexto alimentar e qualidade da leitura; oxigênio suplementar aparece apenas em saturação e frequência respiratória. Sono e escalas subjetivas não pedem qualidade de sensor. O POST de medições existente aceita os seguintes campos adicionais:

| Campo | Valores |
| --- | --- |
| `activity` | `rest`, `exercise`, `unknown` |
| `signal_quality` | `good`, `poor`, `unknown` |
| `supplemental_oxygen` | `true`, `false`, `null` |
| `glucose_context` | `fasting`, `after_meal`, `unknown` |
| `symptoms_status` | `present`, `absent`, `unknown` |
| `symptoms` | `chest_pain`, `shortness_of_breath`, `sudden_weakness`, `visual_changes`, `speech_difficulty` |
| `acute_confusion` | `true`, `false`, `null`; apenas em atenção/consciência |
| `unit` | Unidade do indicador ou uma alternativa suportada |
| `client_request_id` | UUID de reenvio |

As unidades alternativas são °F para temperatura, mmol/L para glicemia, kPa para pressão, `fraction` para SpO₂ e `h` para duração do sono. Os valores normalizados são usados nas regras e no histórico; `original_values` preserva os valores e a unidade enviados.

A ausência de registro de sintomas continua sendo desconhecida. Sintomas estruturados presentes elevam pressão muito alta a crítico. O texto livre não é interpretado como confusão aguda ou presença/ausência de sintomas.

As faixas de frequência cardíaca/respiratória em repouso só são aplicadas com `activity=rest`. Em atividade desconhecida, faixas críticas de repouso geram um alerta operacional urgente de verificação imediata, sem classificar a leitura como confirmada em repouso. Exercício preserva seu contexto; uma leitura extrema com sinal ruim também gera verificação imediata. SpO₂, temperatura, pressão, glicemia baixa e consciência usam as regras configuradas independentemente da atividade, preservando o contexto.

Uma leitura com sinal ruim permanece com qualidade insuficiente. Se atingir uma faixa de alerta, o alerta é emitido imediatamente com necessidade explícita de verificação. Nenhuma leitura de sinal ruim encerra ou reduz um alerta aberto.

O resumo distingue `no_measurement`, `stale`, `insufficient_quality`, `evaluated` e `not_evaluated`. Medições anteriores à migration ficam como não avaliadas; não há geração retroativa automática de alertas. Uma leitura antiga recebe o estado desatualizada e mantém o contexto e a qualidade no histórico.

## Tendências

Usa-se o registro válido mais recente por dia ou noite, com desempate por horário de registro e ID. Registros de qualidade insuficiente não entram nas tendências. O fuso é o da missão. Para sessões de sono, a noite é identificada pela data local do fim da sessão; sem sessão, pela data local da coleta. Várias leituras no mesmo dia/noite não completam uma sequência. Um dia/noite sem registro válido interrompe a sequência. Uma gravação atrasada pode completar a sequência, mas uma leitura fora dela não reabre uma tendência já resolvida.

## Ciclo de vida e acesso

Os estados são `open`, `acknowledged` e `resolved`. Reconhecer registra que o alerta foi visto. Uma escalada reabre o alerta e preserva o reconhecimento anterior no histórico. Alertas de atenção e urgentes são encerrados automaticamente por uma nova leitura válida, recente e fora da faixa da regra. Uma leitura antiga, com sinal ruim ou sem o contexto necessário não encerra o alerta. Em tendências, uma lacuna isolada não significa normalização. Alertas críticos continuam exigindo resolução explícita pelo médico de voo autorizado. Quando a leitura atual já saiu da faixa, a interface distingue o evento crítico anterior e a revisão médica pendente. Uma nova ocorrência após resolução cria outro alerta, preservando o anterior.

Há um único alerta ativo por regra e tripulante, independentemente da missão de origem. Os alertas são dados do prontuário do tripulante, como as alergias: o próprio tripulante pode consultar e reconhecer; o médico de voo vinculado à missão informada pode consultar, reconhecer e resolver. Outros tripulantes, médicos sem vínculo e administradores sem papel clínico não acessam os alertas. A lista e o histórico mostram as medições de origem do tripulante, inclusive quando originadas em outra missão.

O servidor serializa gravações e ações por tripulante com bloqueio de linha. Restrições únicas protegem a chave de reenvio, o conteúdo da medição e a combinação tripulante/regra ativa. Uma chave reutilizada com outro conteúdo retorna 409. Formulários mantêm o UUID durante reenvios.

## Rotas

Todas têm prefixo `/v1/health` e exigem autenticação.

| Rota | Método |
| --- | --- |
| `/astronauts/{astronaut_id}/observations` | POST existente, agora avalia alertas na mesma transação |
| `/astronauts/{astronaut_id}/summary` | GET existente, agora retorna estado e contexto da avaliação |
| `/astronauts/{astronaut_id}/history` | GET existente, agora inclui unidade original e contexto |
| `/astronauts/{astronaut_id}/alerts` | GET, `status=active/all/open/acknowledged/resolved`, `indicator`, `page`, `per_page` |
| `/astronauts/{astronaut_id}/alerts/{alert_id}` | GET |
| `/astronauts/{astronaut_id}/alerts/{alert_id}/history` | GET paginado com eventos e medições de origem |
| `/astronauts/{astronaut_id}/alerts/{alert_id}/acknowledge` | POST |
| `/astronauts/{astronaut_id}/alerts/{alert_id}/resolve` | POST com `{"note":"Avaliação registrada"}` |
| `/missions/{mission_id}/alert-settings` | GET, PUT |

Informe `mission_id` nas consultas e ações do médico de voo. O próprio tripulante também pode consultar seus alertas sem missão.

## Tela

O monitoramento mostra os alertas ativos dentro do cartão do respectivo indicador, com os mais graves primeiro em cada cartão. O cartão recebe destaque com texto, ícone e cor. O histórico acessado pelo cartão é filtrado pelo indicador. Há ações para registrar nova medição/sintomas, abrir o histórico do indicador, reconhecer, consultar os eventos do alerta e registrar resolução autorizada. As colunas de cards são independentes; a expansão de um card não estica o card vizinho. Os históricos de alertas e de eventos têm seleção de itens por página, total de registros e navegação Anterior/Próxima. Alertas críticos exibem o protocolo de emergência e o canal atual da missão. Quando o canal está ausente, isso é explicitado. O snapshot histórico do canal original é preservado.

## Migration e verificações

Dentro de `NASA`:

```sh
docker compose exec -T api alembic upgrade head
```

A revisão é `d15c6e7f8091`. Ela adiciona contexto às medições e as tabelas `health_alert_settings`, `health_alerts`, `health_alert_observations` e `health_alert_events`. A reversão é bloqueada quando há alertas, para preservar histórico.

Com pytest disponível no ambiente do backend:

```sh
python -m pytest -q
python -m scripts.verify_health_alerts
```

O segundo comando cria um banco PostgreSQL temporário, aplica todas as migrations, executa a suíte com os testes PostgreSQL e concorrentes habilitados e remove o banco ao terminar. Requer permissão para criar e remover esse banco isolado. O teste concorrente faz quatro reenvios simultâneos e duas medições simultâneas com escalada.

Dentro de `front`:

```sh
npm test
npm run build
```


## Glicemia alta no perfil de simulação

A versão `simulation-v2` adiciona um limite operacional urgente de 300 mg/dL para glicemia alta, com confirmação da leitura. O perfil não diagnostica cetoacidose nem determina tratamento. A referência consultada foi a orientação do CDC sobre glicemia persistentemente ≥300 mg/dL, que não deve ser interpretada como regra universal para uma leitura isolada: https://www.cdc.gov/diabetes/about/diabetic-ketoacidosis.html . A seleção de um único valor como gatilho inicial é uma decisão de produto para o protótipo e requer configuração clínica específica para uso fora da simulação.

Uma reavaliação explícita pode preservar o perfil e o estado anteriores em `evaluation_profile.previous_evaluation`, mantendo o ID, o horário e o valor original da medição. A troca do perfil padrão não reprocessa automaticamente todos os registros antigos.
