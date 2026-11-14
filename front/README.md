# NASA Health Monitor · Sistema de Monitoramento

Frontend React 19 e Vite para o backend FastAPI deste repositório. Interface em português, responsiva, com autenticação, missões, membros, catálogo de exames, requisitos, checklist, agendamento, resultados, correções e revisões.

## Executar

Na raiz do backend (`..`), inicie a API:

```sh
docker compose up --build -d
```

Nesta pasta:

```sh
npm install
npm run dev
```

Abra http://localhost:5173. O proxy do Vite encaminha `/api` para `http://localhost:8000`, sem exigir alteração de CORS. Não há dados fictícios ou credenciais pré-configuradas: crie uma conta na tela de cadastro.

## Verificação

```sh
npm test
npm run build
```

O build estático fica em `dist`. Em produção, configure o servidor/reverse proxy para encaminhar `/api/*` à API, removendo o prefixo `/api`. O proxy de desenvolvimento não é incluído no build. `npm run preview` serve apenas os arquivos compilados.

## Sessão e permissões

O JWT fica no `sessionStorage` da aba; a sessão é limpa na expiração ou em respostas 401. Sair chama o endpoint de revogação antes de limpar a sessão. Como não existe `/me`, o nome do usuário é obtido pelo diretório de usuários e pelo `sub` do token. O token decodificado serve apenas para apresentação; a API valida todas as permissões.

Administradores gerenciam missão, membros, requisitos e agendamentos. Médicos de voo registram, corrigem e revisam resultados. Astronautas consultam o próprio histórico. Tipos de exame seguem as permissões do backend, com exibição de erros 403. O estado do checklist vem exclusivamente do backend. Datas locais dos formulários são enviadas em UTC com fuso. Listagens paginadas são percorridas integralmente; missões, catálogo e diretório têm paginação visual.

Fontes do Google Fonts são opcionais, com fallback para fontes do sistema. A aplicação não depende de serviços externos para acessar os dados.

O logotipo da NASA em `public/nasa-logo.svg` foi obtido em https://www.nasa.gov/wp-content/themes/nasa/assets/images/nasa-logo.svg.

No cadastro, selecione Astronauta, Médico ou ambos. Os perfis são salvos na conta e exibidos no diretório. O login usa e-mail e senha. Os perfis cadastrais não concedem acesso clínico: o administrador continua atribuindo o papel de cada pessoa na missão.

Alterações em exames, requisitos, catálogo e agendamentos exigem perfil Médico e autorização na missão. Astronautas sem perfil médico têm acesso de leitura aos próprios exames. Resultados e revisões permanecem protegidos contra exclusão.

## Painel de saúde

O painel é a página inicial do astronauta, com 11 indicadores, mapa corporal SVG, registro manual, gráficos Recharts e histórico categórico. Médicos acompanham astronautas das missões em que atuam como médicos de voo. Veja [execução, permissões, endpoints e verificação](../HEALTH_MONITORING.md).

## Exames e resultados estruturados

A tela **Exames** permite buscar, listar, consultar os campos e cadastrar ou editar
exames vinculados aos tipos existentes. Somente médicos com permissão de catálogo
recebem ações de escrita. Cada exame define campos numéricos, texto curto ou
longo, seleção, sim/não e data, com unidades e obrigatoriedade.

Em **Missões → Requisitos**, o médico escolhe um exame cadastrado e define sua
antecedência em relação ao lançamento. Em **Checklist de monitoramento → Histórico**,
o médico de voo registra os valores, as referências do laboratório, os dados da
coleta e do laudo, e realiza a revisão. O astronauta consulta apenas os próprios
resultados. As mesmas restrições são verificadas pelo backend.

O formulário e o histórico usam a versão dos campos guardada na atribuição do
exame. Alterar o catálogo não reescreve resultados anteriores. Resultados já
revisados permanecem imutáveis e podem ser substituídos por uma nova realização.
O fluxo continua sendo de exames pré-voo: a data de realização deve anteceder o
início da missão quando ele estiver configurado.

O catálogo inicial e sua migration estão no backend. Execute na pasta `NASA`:

```bash
docker compose exec -T api alembic upgrade head
docker compose exec -T api python -m scripts.seed_exam_catalog
```

O seed adiciona 29 definições baseadas no documento NASA OCHMO-STD-100.1A, Rev. A,
e preserva cadastros já existentes. Nenhum resultado clínico é simulado pelo seed.
As referências e páginas aparecem nas telas; unidades e campos são adaptações
para registro, e os intervalos de referência são preenchidos conforme o laudo.

`npm test` verifica a serialização dos resultados, a renderização dos campos e
do histórico, a compatibilidade com resultados antigos e a ação de cadastro
conforme a permissão. `npm run build` valida o bundle completo.
