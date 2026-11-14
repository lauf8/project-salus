# Notificações clínicas internas

A área Notificações e o sino no cabeçalho são exibidos para contas médicas. A lista consulta o backend a cada 30 segundos enquanto a página estiver visível. O sino também atualiza ao voltar para a janela e após ações de leitura. Não há webhook, e-mail, push, som ou integração externa.

## Quando gerar uma notificação

Somente um alerta com gravidade `critical`, gerado por uma leitura recente que ainda seja a leitura válida mais atual daquele indicador, pode gerar uma notificação. Leituras com qualidade `poor`, desatualizadas ou já substituídas por uma medição válida mais recente não geram novos avisos. Alertas de atenção e urgentes, inclusive a glicemia alta urgente do perfil de simulação, não geram notificações. O critério usa as regras de simulação existentes; não estabelece diagnóstico.

Uma escalada para crítico gera uma notificação. Se a primeira leitura crítica tiver sinal ruim, uma leitura crítica posterior válida pode gerar o primeiro aviso. Reenvios, medições críticas repetidas e reconhecimento do mesmo alerta não criam avisos duplicados. Após resolução, uma nova ocorrência cria outro alerta e pode gerar outra notificação.

As notificações são gravadas na mesma transação da medição e do alerta, com chave única por médico, missão e alerta. Os dados da notificação preservam o motivo e a medição que geraram o aviso. O estado atual do alerta é consultado ao exibir a notificação.

## Destinatários e acesso

O destinatário deve ter `is_physician=true` e estar vinculado à missão como `flight_surgeon`, sendo outro usuário que não o tripulante avaliado. Apenas o destinatário pode consultar ou marcar suas notificações como lidas. O vínculo clínico e o vínculo do tripulante são revalidados em toda consulta; remover ou alterar o papel de médico de voo revoga o acesso às notificações daquela missão.

A missão informada na medição é usada para o direcionamento. Se a medição não informar missão, usa-se a única missão não encerrada em que o tripulante tem papel `astronaut`. Se houver zero ou várias, o sistema não escolhe uma equipe arbitrariamente; o contexto da medição registra que é necessário informar a missão. Missões encerradas não recebem novos avisos. Se não houver médico de voo elegível, isso também é registrado no contexto da medição.

Marcar uma notificação como lida apenas registra a leitura. Não reconhece nem resolve o alerta. A aba Pendentes e o contador do sino mostram avisos não lidos cujo alerta ainda não foi resolvido. A aba Todas mantém o histórico, incluindo notificações de alertas resolvidos. Abrir prontuário marca a notificação como lida e seleciona missão, tripulante e indicador no monitoramento, mantendo as regras de acesso existentes.

## Rotas

Todas exigem autenticação de uma conta médica e têm prefixo `/v1`.

| Rota | Método e comportamento |
| --- | --- |
| `/notifications` | GET com `status=pending/all`, `mission_id` opcional, `page` e `per_page` |
| `/notifications/summary` | GET com contagem de não lidas e pendentes |
| `/notifications/{notification_id}/read` | POST para marcar uma notificação própria como lida |
| `/notifications/read-all` | POST para marcar todas as notificações visíveis do destinatário como lidas |

## Instalação e verificação

Dentro de `NASA`:

```sh
docker compose exec -T api alembic upgrade head
docker compose exec -T api python -m scripts.sync_health_notifications
```

A revisão `e26d7f8091a2` cria `health_notifications`. A sincronização verifica alertas críticos já existentes com os mesmos critérios de atualidade, qualidade e direcionamento; não cria avisos de eventos já superados. Pode ser repetida sem duplicação. A avaliação de novas medições já gera as notificações automaticamente, sem depender desse comando.

Com pytest instalado:

```sh
python -m pytest -q tests/test_health_notifications.py
python -m scripts.verify_health_alerts
```

O verificador PostgreSQL cria e remove um banco isolado e testa gravações concorrentes, incluindo a geração de uma única notificação na escalada crítica.
