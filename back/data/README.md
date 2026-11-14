# Catálogo inicial de medicamentos

`common_medicines.json` contém 100 entradas para os EUA e 100 para o Brasil. Há 39 entradas compartilhadas, totalizando 161 medicamentos e 160 princípios ativos distintos. Os nomes genéricos são apresentados em português e as composições usam a mesma identidade de princípio ativo nos dois países.

A seleção dos EUA corresponde aos 100 primeiros medicamentos genéricos do ClinCalc DrugStats por prescrições ambulatoriais em 2024, consultado em 12/11/2026. Nomes foram traduzidos e combinações foram preservadas. Fonte: https://clincalc.com/drugstats/Top200Drugs.aspx . A lista de referência é disponibilizada pelo ClinCalc sob CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/ . A seleção dos EUA e sua tradução mantêm essa licença.

A seleção brasileira é uma curadoria de 100 medicamentos comuns, e não um ranking nacional validado de vendas ou prescrições. A RENAME foi consultada como referência de medicamentos essenciais, sem presumir que todos os itens selecionados integrem a relação. As fontes são registradas no campo `sources` do JSON. `markets` indica a seleção à qual cada entrada pertence; não certifica o registro sanitário de cada apresentação em um país.

`main_indications` contém resumos informativos em português. Não inclui doses, recomendação individual ou lista exaustiva de indicações. As indicações variam com a apresentação e o país. Foram consultadas informações de rotulagem FDA/DailyMed, Bulário da Anvisa e bulas de fabricantes. Os textos permanecem editáveis pela equipe autorizada.

NPH e insulina humana regular são medicamentos separados associados ao mesmo princípio ativo, `Insulina humana`. As preparações tópicas e nasais também são associadas ao princípio ativo sem incluir a via de uso no nome do ingrediente.

Para importar, a partir da pasta `NASA`, após aplicar as migrations:

```sh
docker compose exec -T api alembic upgrade head
docker compose exec -T api python -m scripts.seed_medicines --dry-run
docker compose exec -T api python -m scripts.seed_medicines
```

A importação ocorre numa transação e usa lock para serializar execuções concorrentes. Reexecuções reaproveitam cadastros pelo nome normalizado, preservam indicações já preenchidas e rejeitam composições divergentes sem gravar alterações. Não é executada automaticamente na inicialização da API.
