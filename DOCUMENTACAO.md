# Biblioteca Escolar — Documentação de Projeto

> Status: **em documentação** (antes de qualquer código)
> Data: 11/08/2026

---

## 1. Visão geral

Site web para a biblioteca de uma escola. A biblioteca empresta livros (vários títulos e gêneros) para os alunos.

- **Login sem cadastro**: RA + senha, validado pela API da Secretaria Digital (SED). Não existe tela de cadastro — quem tem RA da escola entra.
- **Catálogo** de livros com capas, busca e filtros.
- **Duas áreas separadas**: área do usuário (aluno) e área administrativa (bibliotecário/admin).
- **Empréstimos**: registrar aluguel, devolução, controle de atraso e disponibilidade de exemplares.

---

## 2. Autenticação (SED)

> Sistema: **SED SP** (sed.educacao.sp.gov.br). Código de referência já existente em `~/automateava/Server/`:
> - `get_course.py` → `_authenticate_async` (API JSON, validação em ~2s)
> - `get_user_data.py` → `make_login` + `get_user_info` (fluxo antigo com Playwright)

### Fluxo proposto
1. Usuário informa **RA + senha** na tela de login.
2. Backend envia as credenciais para a verificação via script/API da SED.
3. SED responde: válido/inválido + dados do aluno (nome, turma, etc.).
4. Se válido: backend cria sessão própria da aplicação (token) e o aluno entra.
5. Se inválido: mensagem de erro, sem cadastro possível.

### Verificação de credenciais (API JSON — validada com RA real em 11/08/2026)
```
POST https://sedintegracoes.educacao.sp.gov.br/saladofuturobffapi/credenciais/api/LoginCompletoToken
Content-Type: application/json
Ocp-Apim-Subscription-Key: <SED_SUBSCRIPTION_KEY>   ← vem do ambiente (mvp/.env); nunca no frontend nem no repositório

Body: { "user": "<RA>sp", "senha": "<senha>" }
```
- RA precisa do sufixo `sp` (função `normalize_ra`)
- **HTTP 200** → `token` (JWT de sessão, expira em 24h) + `tokenResumo` (claims: LOGIN, NAME, CPF, NICKNAME) + `DadosUsuario`:
  - `NAME` (nome completo, em maiúsculas), `NR_CPF`, `EMAIL`, `PERFIS` (CD_PERFIL 6 = Aluno), `A[0].DT_NASC` (nascimento), `A[0].NR_TELEFONE`
  - **Turma NÃO vem nesse endpoint** → espelho guarda nome/CPF/email/nascimento; turma fica vazia (preencher futuramente via página ConsultaAluno ou outra API)
- **HTTP 401** → `{"statusCode":401,"statusRetorno":"Usuário ou senha incorretos!"}` (não distingue RA de senha — bom pra segurança)
- **HTTP 403** → `{"statusCode":403,"statusRetorno":"Usuário não pertence a rede estadual!"}` = **a SED aceitou a
  credencial e recusou a conta**. Verificado em 08/10/2026: aconteceu com TODAS as contas testadas ao mesmo
  tempo (9 RAs) e voltou a 200 sem qualquer mudança de código — é janela do lado da SED, não senha errada e
  não bug do site. `sed_client.mensagem_de_recusa()` mostra esse motivo ao usuário em vez de "RA ou senha
  incorretos"; o log da aplicação registra `SED recusou o login: HTTP <code> statusRetorno=... <ra>` (nunca a
  senha). Também foi medido que não adianta reforçar cliente/cabeçalhos: `requests` puro e
  `curl_cffi impersonate="chrome120"` recebem o mesmo 403, e Origin/Referer do app oficial não desbloqueiam.
- Sucesso cria/atualiza o **espelho do aluno** no banco local (nome normalizado: "MARIA DA SILVA SOUZA" → "Maria da Silva Souza")
- Usa `requests` com User-Agent de Chrome + timeout de 8s (mensagem amigável se a SED cair)

### Puxamento de dados do aluno (método atual: scraping)
- Login via POST `https://sed.educacao.sp.gov.br/Logon/Logon/` (form: `usuario`, `senha`, `tipo='A'`, `__RequestVerificationToken`)
- Resposta com "invalid" no texto → credenciais erradas
- Com os cookies da sessão, abre `https://sed.educacao.sp.gov.br/MinhasTurmas/ConsultaAluno` via Playwright headless e extrai por XPath: **CPF, nome, sexo, data de nascimento**
- Turma: a página ConsultaAluno deve ter o campo — confirmar na implementação

> **Pendência**: verificar se existe endpoint de API JSON que retorne nome/turma direto (evita Playwright). Se não existir, mantemos o scraping só no login (custo único por sessão).

### Regras
- Validação SED **isolada em um único módulo** (`sed_client.py`) — se a SED mudar, só esse arquivo muda.
- Senha nunca é logada nem guardada em banco. Sessão da app usa token próprio após validação.
- Subscription key e token anti-CSRF ficam **no backend** (nunca no frontend).

### Riscos da SED
- **Migração para gov.br**: a SED SP anunciou que o acesso passará a ser exclusivamente via gov.br (artigo SED-08356 do portal de atendimento) — o endpoint `LoginCompletoToken` pode ser descontinuado. Monitorar; quando migrar, o login vai precisar do fluxo gov.br (ou o site fica só para quem já tem espelho)
- `__RequestVerificationToken` hardcoded (fluxo antigo) pode expirar — por isso usamos o `LoginCompletoToken`, que não usa token anti-CSRF
- Chave de assinatura (`Ocp-Apim-Subscription-Key`) pode ser rotacionada pela SED
- SED fora do ar: timeout curto + mensagem clara ("serviço indisponível, tente de novo")
- Scraping Playwright é frágil (mudança de HTML quebra) — manter isolado

### Como alguém vira admin?
**Em aberto.** Opções:
- a) Tabela `admins` (só o RA) — admin define quem é admin no painel;
- b) Login admin separado.
> Recomendação: (a) — simples e controlável. Aluno que tentar área admin leva "acesso negado".

#### Implementado (a), com uma condição que confunde: o aluno precisa ter logado antes

`POST /api/admin/admins` e `GET /api/admin/alunos/{ra}` **não aceitam RA arbitrário**: procuram o aluno na
tabela `alunos` (o espelho do 1º login). Sem linha, a resposta é *"Aluno não encontrado. Ele precisa ter
feito login ao menos uma vez."* — é requisito do desenho, não bug.

**Chave canônica (08/10/2026).** O espelho era gravado com o RA **cru digitado**, então a mesma pessoa
virava duas linhas (`123456789sp` e `000123456789sp`) e o painel, que casa string exata, errava a busca.
Agora tudo passa por `sed_client.chave_aluno()` — sem pontos/traços/espaços, minúscula, sem zeros à
esquerda, com `sp` — e os endpoints de admin aceitam qualquer grafia (`123456789`, `123456789sp`,
`000123456789sp` caem na mesma pessoa). Bases antigas se corrigem com
`mvp/tools/migrar_ra_canonico.py --aplicar` (faz backup antes e MOVE empréstimos/sessões/admins para a
linha canônica antes de apagar as duplicatas).

---

## 3. Papéis e permissões

| Ação | Aluno | Admin |
|---|---|---|
| Ver catálogo e capas | ✅ | ✅ |
| Buscar/filtrar livros | ✅ | ✅ |
| Alugar livro | ✅ | — |
| Ver meus empréstimos | ✅ | — |
| Devolver livro | ❌ (só admin) | ✅ |
| Cadastrar/editar/remover livros | ❌ | ✅ |
| Ver todos os empréstimos (quem pegou o quê) | ❌ | ✅ |
| Registrar devolução de qualquer aluno | ❌ | ✅ |
| Ver dashboard (atrasados, mais alugados) | ❌ | ✅ |

---

## 4. Modelagem de dados (rascunho)

> **O banco é de LIVROS**: catálogo, exemplares, empréstimos e configurações.
> **Usuário não é cadastrado no banco** — autenticação é 100% SED, sem credenciais guardadas.
> Único resquício de aluno é um espelho mínimo (RA + nome + turma) gravado na 1ª vez que loga, só pra exibir histórico de empréstimos sem depender da SED a cada tela.

```
livros
  id, titulo, autor, genero, isbn, capa_url,
  sinopse, ano_publicacao, total_exemplares, disponiveis

alunos (espelho MÍNIMO da SED — sem senha, sem cadastro)
  ra (PK), nome, turma
  → criado automaticamente no primeiro login válido

emprestimos
  id, livro_id (FK), aluno_ra (FK),
  data_emprestimo, data_prevista_devolucao,
  data_devolucao_real (NULL até devolver),
  status: ativo | devolvido | atrasado

reservas (opcional — ver decisões em aberto)
  id, livro_id, aluno_ra, data_reserva

configuracoes (chave-valor, editável pelo admin)
  prazo_emprestimo_dias = 14   (configurável)
  limite_livros_por_aluno = 3  (configurável)
```

**Regra de ouro**: `disponiveis` só muda dentro de transação ao alugar/devolver — evita dois alunos alugarem o último exemplar ao mesmo tempo.

---

## 5. Telas

### Área do usuário (`/`)
- **Login** — RA + senha (única porta de entrada)
- **Catálogo** — grid de capas; busca por título/autor; filtro por gênero
- **Detalhe do livro** — capa grande, sinopse, disponibilidade ("X disponíveis"), botão alugar
- **Meus empréstimos** — livros que pegou, status (ativo/atrasado), data prevista de devolução

### Área administrativa (`/admin`) — **separada da do usuário**
- **Dashboard** — livros emprestados agora, atrasados, ranking dos mais alugados
- **Livros** — CRUD completo: cadastrar com capa (upload ou URL), editar, remover, ajustar exemplares
- **Empréstimos** — listar ativos/atrasados, registrar devolução, histórico
- **Alunos** — consultar por RA (dados puxados da SED no login)
- **Admins** — gerenciar quem tem acesso admin (se opção "a" da seção 2)

---

## 6. Arquitetura

```
[Aluno/Admin] → [React + Vite] → [API Python] → [SQLite (MVP)]
                                    │
                                    └→ [API SED] (só no login)
```

- **Frontend**: React + Vite (padrão dos projetos atuais, ex: automateava)
- **Backend**: Python (FastAPI ou Flask) — rotas separadas `/api/user/*` e `/api/admin/*`
- **Banco**: SQLite para MVP (arquivo único, zero setup); migra pra Postgres se crescer
- **Capas**: Google Books API por ISBN (grátis, sem chave em uso básico) — cadastrou ISBN, capa vem sozinha; fallback: capa genérica
- **Deploy**: Cloudflare Tunnel → porta local (padrão automateava)

---

## 7. Fluxos principais

1. **Login**: RA+senha → valida na SED → cria sessão → redireciona (admin vai pra `/admin`, aluno pra `/`)
2. **Alugar**: aluno abre livro → tem `disponiveis > 0`? → registra empréstimo + decrementa (atômico) → "alugado com sucesso"
3. **Devolver** (só admin): busca o empréstimo ativo por **nome do aluno + livro** → registra devolução → incrementa `disponiveis` → status vira `devolvido`
4. **Atraso**: todo login/abertura do painel compara `data_prevista_devolucao < hoje` em empréstimos ativos → marca `atrasado`

---

## 8. Decisões

| # | Questão | Decisão |
|---|---|---|
| 1 | Prazo padrão de empréstimo | **Configurável** no painel admin (default 14 dias) |
| 2 | Limite de livros por aluno | **Configurável** no painel admin (default 3) |
| 3 | Multa por atraso | Em aberto (ou só bloqueio de novos empréstimos) |
| 4 | Quem registra devolução | **Só admin**. Identificação do empréstimo por **nome do aluno + livro** |
| 5 | Reserva de livro indisponível | Em aberto (estrutura já prevista) |
| 6 | Nome do site/biblioteca | Em aberto (pra logo e título) |

---

## 9. Riscos / pontos de atenção

- **SED fora do ar**: login precisa de timeout curto + mensagem clara ("serviço indisponível, tente de novo"). Não cachear senha.
- **Mudanças na SED**: mitigado pelo módulo isolado (`sed_client.py`).
- **Capa inexistente no Google Books**: fallback visual obrigatório.
- **Corrida no último exemplar**: transação no ato do empréstimo.
- **RA de ex-aluno**: se a SED invalidar, o acesso morre junto — comportamento correto, documentar.

---

## 10. Checklist antes de codar

- [x] Script de credenciais SED localizado (autoava: `get_course.py` + `get_user_data.py`) e documentado na seção 2
- [x] Direção visual escolhida (seção 11)
- [ ] Confirmar se existe API JSON p/ nome/turma do aluno (ou manter scraping no login)
- [ ] Fechar decisões em aberto da seção 8
- [ ] Confirmar stack (React+Vite + Python + SQLite)
- [ ] Definir nome do projeto/pasta

---

## 11. Identidade visual

**Decisão (11/08/2026): estilo "Catálogo Clássico" + modo escuro.**

- Fundo papel envelhecido, tinta marrom escura, serifada (Playfair Display / Source Serif)
- Carimbo circular "Biblioteca Escolar" no header, bordas duplas, ficha de catálogo com número CDD no hover
- Capas são blocos de cor com moldura interna — protótipo usa cores por livro; na versão final, capas reais via Google Books com fallback na cor
- **Modo escuro**: papel marrom-escuro (#201a13), tinta creme, carimbo vermelho vivo; toggle persistente (localStorage, default segue o sistema)
- **Design system compartilhado**: `prototipos/estilo.css` (componentes: capas, fichas, tabelas, badges, tabs, stats, forms) + `prototipos/tema.js` (toggle com a mesma chave `biblio_tema` em todas as páginas)
- Protótipos em `~/biblioteca_escolar/prototipos/`:
  - `01-catalogo-classico.html` — catálogo (escolhido) · `04-login.html` — login
  - `05-detalhe-livro.html` — ficha do livro + solicitar empréstimo
  - `06-meus-emprestimos.html` — empréstimos do aluno (ativo/atrasado/devolvido)
  - `07-admin-dashboard.html` — painel (stats, atrasados, ranking, recentes)
  - `08-admin-livros.html` — CRUD de obras (formulário + tabela)
  - `09-admin-emprestimos.html` — devolução por nome+livro, ativos, histórico
  - `10-admin-alunos.html` — consulta por RA + gestão de admins

---

## 12. MVP funcional (11/08/2026)

**Rodando em `http://localhost:8123`** (FastAPI + SQLite + SPA vanilla com o design system aprovado). Código em `~/biblioteca_escolar/mvp/` — subir com `./run.sh` (porta: `PORTA=9000 ./run.sh`).

### Credenciais demo (modo mock)
| Perfil | RA | Senha |
|---|---|---|
| Bibliotecário | 123456789 | admin123 |
| Aluno | 987654321 | aluno123 |
| Aluno 2 | 555666777 | aluno123 |

### Autenticação
- Login RA+senha → **bearer token opaco** (32 bytes, salvo com hash SHA-256 no banco, nunca em texto plano)
- **TTL 24h** (`TOKEN_TTL_MIN` para teste) — expirado não passa em nenhuma rota
- **Logout revoga na hora**: marca `revogada_em`; purge automático de sessões velhas a cada login
- Token vai no header `Authorization: Bearer` (guardado em `sessionStorage`)
- Todos os `/api/*` exigem token; rotas admin exigem papel admin (403 para aluno)

### Segurança aplicada
- **Rate limit + lockout** no login: 5 falhas por RA+IP → bloqueio de 15 min (429)
- **Headers**: CSP estrita (sem inline scripts), X-Frame-Options DENY, nosniff, no-referrer, `Cache-Control: no-store` em `/api`, HSTS opcional (`FORCE_HTTPS=true`)
- **Validação**: Pydantic em todas as entradas, limites de tamanho, SQL 100% parametrizado
- **Transação atômica** no empréstimo (BEGIN IMMEDIATE) — dois alunos não pegam o último exemplar
- **Limite de livros** e **prazo** configuráveis no painel admin (tabela `configuracoes`)
- Admin não pode remover a si mesmo; livro com exemplares emprestados não pode ser reduzido/removido
- **Anti-bot Cloudflare (Turnstile)**: hook pronto no login — ativa definindo `TURNSTILE_SECRET_KEY`; sem a secret, fica inerte (o Okai pluga depois)
- Senhas nunca são logadas; tokens não expiram no cliente por inatividade (só TTL + logout)

### SED
- **Integrada e testada com RA real em 11/08/2026** (login 200, espelho com nome/CPF/email/nascimento)
- Modo **mock por padrão** (`SED_ENABLED != true`) — valida contra alunos seed (admin123/aluno123), sistema funciona offline e a suíte de testes roda nesse modo
- `SED_ENABLED=true` → valida na SED real via `LoginCompletoToken` (sedintegracoes); credenciais mock NÃO funcionam nesse modo
- Timeout de 8s com mensagem amigável se a SED cair; 401 vira "RA ou senha incorretos" e **403 mostra o
  motivo da SED** ("conta recusada") em vez de culpar a senha — ver a tabela de status no item 2
- Espelho do aluno criado no primeiro login (nome normalizado, CPF, email, nascimento); turma pendente (não vem do endpoint)

### Testes
`mvp/tests/test_api.py` — 28 asserts cobrindo auth, 401/403, CRUD, empréstimo, devolução, logout/revogação, rate limit, config e admins. **28/28 verdes.** (Atenção: a suíte mexe no banco — rode com banco descartável.)

## 13. Animações e interatividade ("Catálogo vivo") — 12/08/2026

Pacote de micro-interações aplicado em `mvp/web/` (CSS puro + JS vanilla, sem libs):

- **Transição entre views** — fade + slide ao trocar de rota (`.view.leave` → `.view.active`).
- **Skeleton loading** no catálogo — shimmer enquanto o fetch roda.
- **Busca com debounce** — filtra ao digitar (260ms), sem precisar do botão Buscar.
- **Clique nas capas** — agora via delegação de evento (`data-livro` + `gridOut` listener). Antes usava `onclick` inline, **bloqueado pela CSP**.
- **Count-up animado** nos números do dashboard (respeita `prefers-reduced-motion`).
- **Selo "Disponível/Esgotado"** carimba (stampIn) ao abrir o detalhe; capa do detalhe flutua levemente.
- **Hover nas capas** — elevação + "brilho varrendo" (::after animado).
- **Modal de confirmação** customizado no lugar do `confirm()` nativo (remover livro / admin), com Esc e clique fora para cancelar.
- **Toast** com saída animada; **shake** no card de login em erro; **spinner** no botão de login; botões com efeito press.
- `prefers-reduced-motion: reduce` desativa tudo.

### Correção de CSP (importante)
A CSP tinha `style-src 'self'` **sem `'unsafe-inline'`**, o que bloqueia silenciosamente os `style="..."` inline — **todas as capas ficavam na cor padrão (marrom)** e o `onclick` inline não executava. Corrigido em `main.py`:

```
style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
```

`script-src 'self'` continua estrito (sem inline JS) — qualquer handler novo deve ser registrado via `addEventListener`, nunca `onclick` inline.

## 14. Fluxo de preparação (solicitado → pronto → ativo) — 12/08/2026

Decisão de produto com o Okai: quando o aluno pede um livro pelo site, o **bibliotecário separa** o exemplar e o aluno **busca no balcão durante o recreio**. O empréstimo agora tem ciclo de status:

```
solicitado → pronto → ativo → devolvido
             (expirada / cancelada a qualquer momento antes da retirada)
```

### Regras
- **Limite de solicitações**: cada aluno pode ter no máximo `limite_solicitacoes_pendentes` (default **2**) entre `solicitado` e `pronto`. O limite de `limite_livros_por_aluno` (default 3) continua valendo para livros `ativo` (com o aluno).
- **Prazo de preparação**: o bibliotecário tem `prazo_preparacao_dias` (default **2**) para separar. Solicitações não preparadas no prazo **expirar sozinhas** (`status='expirada'`) e o exemplar volta ao acervo. A expiração roda sob demanda (a cada leitura/escrita de empréstimos), sem cron.
- **Reserva do exemplar**: solicitar já decrementa `livros.disponiveis` (o exemplar fica reservado). Cancelar/expirada devolve; retirada não muda; devolução devolve.
- **Prazo de devolução começa na retirada**: `data_prevista` só é preenchida em `retirar` (hoje + prazo de empréstimo).
- **Duplicidade**: aluno não pode ter duas solicitações/empréstimos do mesmo livro ao mesmo tempo.
- **Cancelamento**: aluno (dono) ou admin pode cancelar `solicitado`/`pronto`; aluno não cancela solicitação alheia (403).

### Endpoints novos
- `POST /api/emprestimos` → cria com `status='solicitado'` (antes já nascia ativo)
- `POST /api/emprestimos/preparar` {emprestimo_id} → `solicitado` → `pronto` (admin)
- `POST /api/emprestimos/retirar` {emprestimo_id} → `pronto` → `ativo` + `data_prevista` (admin)
- `POST /api/emprestimos/cancelar` {emprestimo_id} → `solicitado`/`pronto` → `cancelada` (dono ou admin)
- `GET /api/emprestimos?status=solicitado` → filtro por status (admin)

### Frontend
- Header do admin mostra pill vermelha pulsante **"N solicitações p/ preparar"** (clica e vai para a aba Empréstimos).
- Dashboard: stats **A preparar** e **Pronto p/ retirada** + painéis com ações (Separar livro / Registrar retirada / Cancelar).
- Área do leitor: badges Solicitado / Pronto p/ retirada / Expirada / Cancelada; texto "Pronto para retirada! Passe no balcão no recreio"; botão Cancelar nas pendentes.
- Configurações: `prazo_preparacao_dias` e `limite_solicitacoes_pendentes` editáveis no dashboard.

### Banco
Migração automática em `db.migrar()` (recria a tabela `emprestimos`): registros antigos viram `ativo`/`devolvido` conforme `data_devolucao`. `BIBLIO_DB` (env) permite rodar com banco alternativo (usado nos testes).

### Testes
`mvp/tests/test_api.py` reescrito para o fluxo completo — **44 asserts verdes** (solicitação, reserva, limites, cancelamento, preparo, retirada, devolução, expiração, busca, logout, rate limit, config, admins). Rode com banco descartável:
`BIBLIO_DB=/tmp/x.db PORTA=8124 ./venv/bin/python server/main.py` + `TEST_BASE=http://127.0.0.1:8124 ./venv/bin/python tests/test_api.py`

## 15. Leitura de capa por IA (preenchimento automático) — 12/08/2026

No formulário "Novo registro" (admin), o botão **📷 Foto da capa** envia a imagem para
`POST /api/livros/ler-capa`, que usa o **chat multimodal GRÁTIS da Zoice** (`~/zoice_api/zoice_chat.py` —
Gemini 2.5, 0 créditos) para extrair título, autor, gênero, ano, ISBN e sinopse e preencher o form.

- **Isolamento**: o `ZoiceChat` é importado de forma lazy dentro da rota (nunca no boot). Se a Zoice cair,
  a rota responde 502 com mensagem amigável e o resto do sistema funciona normalmente.
- **Prompt calibrado** pede JSON estrito; o parser (`_extrair_json_ia`) tolera fences markdown e texto solto.
- Gênero é validado contra a lista do sistema (fora da lista → campo não preenchido). Ano validado 1000-2100.
- Upload: JPG/PNG/WebP, máx 8MB (`MAX_BODY` subiu para 10MB para caber o multipart).
- **Dependência nova**: `python-multipart` (requerido pelo `UploadFile` do FastAPI).
- **Pitfall ativo (12/08/2026)**: a Zoice está devolvendo **429 em TODAS as contas e modelos** — quota FREE
  do Google AI Studio upstream zerada (compartilhada entre todas as contas; trocar conta NÃO resolve).
  Enquanto isso, a funcionalidade fica indisponível com erro amigável — sem mudança de código quando voltar.

## 16. Melhorias de operação (13/08/2026)

### Backup automático do banco
- `mvp/backup.sh` copia `biblioteca.db` para `mvp/backups/biblioteca_<data>.db` e mantém os 14 mais recentes
  (com `PRAGMA quick_check` de integridade). Cron diário às 22h via Hermes (`biblio_backup.sh`, silencioso em sucesso).

### Capa real por ISBN (Google Books)
- Campo `capa_url` em `livros` (migração automática) — o catálogo e o detalhe mostram a **imagem real da capa**
  quando preenchido (o texto desenhado fica como fallback).
- Botão **"Buscar capa"** no formulário (admin): consulta o Google Books API pelo ISBN (sem chave) e preenche
  título, autor, ano, sinopse e a capa (`fCapaUrl` oculto enviado no POST/PUT).
- CSP: `img-src` liberado para `books.google.com` e `upload.wikimedia.org` (capas). **Pitfall**: a quota do
  Google Books sem chave é por IP/dia — em IPs de datacenter costuma estar esgotada; em IP residencial funciona.

### Relatório CSV para a secretaria
- `GET /api/admin/relatorio?tipo=emprestimos|ativos|atrasados|devolvidos` → CSV separado por `;` com BOM
  (Excel abre acentos corretamente) + `Content-Disposition` para download.
- Botão **"Exportar CSV"** no dashboard (fetch + blob + download).

### Turnstile (adiado de propósito)
As chaves do autoava são vinculadas ao domínio autoava.us — Turnstile rejeita sitekey em outro domínio.
Ativar só quando o site tiver domínio próprio (deploy real). O código do backend já aceita o token.

## 17. Preparação para a apresentação de MVP (27/10/2026)

Objetivo: o site precisava parecer uma biblioteca em uso na frente da banca, não um seed de agosto.

### Acervo com capas reais hospedadas no próprio site
- `mvp/tools/capas_acervo.py` baixa a capa de cada obra do Open Library para `mvp/web/capas/<id>-<slug>.jpg`
  e grava o caminho relativo em `livros.capa_url` (`capas/...`, servido por `img-src 'self'`). Assim a
  apresentação **não depende de internet de terceiros** — só do servidor.
- Busca em duas etapas: `q=` com `language=por` (pega a edição brasileira) e, se falhar, a edição em inglês
  via mapa `ALIASES`. Entre os candidatos, escolhe o JPEG de maior resolução (mínimo desejado 280 px de largura).
- Acervo subiu de 12 para **36 obras** (`--semear`, títulos em `ACERVO_EXTRA` com sinopse escrita em PT-BR;
  a sinopse automática do Open Library vem em inglês e não serve para o público da escola).
- Rodar de novo: `./venv/bin/python tools/capas_acervo.py --semear --aplicar` (simula sem `--aplicar`).

### Estado de demonstração coerente com a data
- `mvp/tools/demo_apresentacao.py` reescreve os empréstimos em datas relativas a hoje: 3 ativos (um atrasado
  em 6 dias), 1 pronto p/ retirada, 1 solicitação pendente e 10 devoluções no histórico — e recalcula
  `livros.disponiveis`. Antes, todo empréstimo ativo aparecia como "atrasado há 70 dias".

### Correções de interface encontradas nesta rodada
- **Capas reais não apareciam nas listas de empréstimos**: `_emprestimo_dict` não expunha `capa_url` e as
  queries não selecionavam `l.capa_url`, então aluno, painel e dashboard desenhavam a capa sintética. Todas
  as 8 queries que alimentam o dicionário foram ajustadas, e as listas passaram a usar `coverHtml()`.
- `coverHtml()` marca a capa com `tem-capa` — com imagem real, o título/autor desenhados somem.
- Selo "Disponível/Esgotado" ficava **atrás** da capa (`.selo` sem `z-index`); agora `z-index:3`.
- Ficha do livro rotulava o ISBN como "Classificação".
- Rotas inexistentes mostravam "Página não encontrada"; agora `#/admin` e similares redirecionam para a tela
  inicial do perfil (e visitante vai para o login).
- KPI "1 ATRASADOS" virou singular quando o número é 1.
- "Empréstimos recentes" do dashboard ordenava por `id` (ordem de inserção); agora por `data_solicitacao`.
- **Cache**: `index.html` passou a responder `Cache-Control: no-cache`. Sem isso o navegador segurava o HTML
  antigo e continuava rodando o `app.js?v=` velho depois de publicar (aconteceu nesta rodada, no Chrome do
  Okai). O `?v=` do `index.html` deve ser bumpado a cada mudança de front.

### Antes de abrir o repositório ao público (27/10/2026)
- `mvp/tools/sed_monitor.log` saiu do versionamento **e do histórico** (`git filter-branch`):
  o arquivo tinha RAs de alunos. Logs em `mvp/tools/*.log` agora estão no `.gitignore`.
- Os exemplos que citavam RA de aluno de verdade (DOCUMENTACAO, `sed_client.py`, `main.py`,
  `demo_apresentacao.py`) passaram a usar os RAs fictícios do seed (123456789 / 555666777 / 987654321).
- O script de demonstração agora usa só os alunos fictícios do seed; a base local deixou de amarrar
  empréstimos em nome de aluno real.
- `biblioteca.db`, `backups/` e `.env` continuam fora do repositório (`.gitignore`) — conferido no
  histórico inteiro com `git rev-list --all --objects`.

### Pendências conhecidas (não mexidas aqui)
- **Solicitação "pronta" nunca expira**: `db.expirar_solicitacoes` só trata `status='solicitado'`; um livro
  separado e não retirado fica reservado para sempre. Exigiria regra nova (prazo de retirada) — decisão do Okai.
- **ISBNs do seed são fictícios** (`978-85-01-0000X-Y`); as 24 obras novas ficaram sem ISBN.
- Turma do aluno continua vazia (não vem do `LoginCompletoToken`).
- Login de demonstração depende da SED real (`SED_ENABLED=true`); em modo mock o `admin123` do seed entra
  como ADMIN e por isso nunca deve ser usado no hostname público.

## 18. Anti-bot (Cloudflare Turnstile) no login — 28/10/2026

Motivo: o bloqueio local de tentativas (`auth.py`) engasgava o próprio dono. Atrás do túnel o
`request.client.host` é sempre `127.0.0.1`, então a chave do rate limit era "RA + IP da Cloudflare" e
qualquer erro de outra pessoa travava a conta para todo mundo. Com captcha, o bloqueio deixa de ser a
única defesa.

- **Backend**: `_validar_turnstile` já existia e ficava inerte sem `TURNSTILE_SECRET_KEY`. Agora valida
  com `remoteip` do visitante real (`CF-Connecting-IP`). Ativo só quando a secret existe; sem ela o login
  funciona como antes.
- **Chave pública**: `GET /api/publico` devolve `turnstile_sitekey` (sem autenticação) — o front só monta o
  widget quando recebe uma chave, então ligar/desligar é só mexer no `.env` e reiniciar.
- **Rate limit**: chave por `CF-Connecting-IP` (não mais o IP do túnel) e defaults `8` falhas / `10 min`
  (`LOGIN_MAX_TENTATIVAS`, `LOGIN_JANELA_SEG`).
- **Front**: widget explícito no cartão de login (`#cfTurnstile`), token enviado como `cf_turnstile_token`,
  reset em erro de login e re-render ao trocar de tema.
- **CSP**: `challenges.cloudflare.com` liberado em `script-src`, `connect-src` e `frame-src` — sem os três
  o widget não carrega (os iframes internos da Cloudflare ainda usam subdomínios próprios, bloqueados pelo
  CSP *deles*, sem quebrar o login).
- **Chaves**: as mesmas do projeto autoava (`~/automateava/Server/.env.local`). O widget aceitou
  `library.autoava.us` por ser subdomínio do domínio já configurado — não foi preciso criar widget novo.
  Ao editar o `.env` por script, cuidado com o BOM do `.env.local`: copiar o valor errado deixou a sitekey
  vazia e o widget não montava (sintoma: `/api/publico` devolvendo `""`).

- **Estado do botão de entrar**: ele só fica clicável com RA **e** senha preenchidos e, quando o anti-bot
  está ativo, com o token do captcha já resolvido (o endpoint devolve 400 sem token, então clique antecipado
  só geraria erro). Enquanto o widget resolve, o rótulo é "Aguardando verificação…"; se o captcha falha,
  "Verificação falhou" e o botão continua travado.

Prova medida no domínio público: token real do widget (730 chars) → login com senha errada devolveu
**401 da SED** (captcha aceito); sem token → **400 anti-bot**.

## 19. Modo escuro com tratamento próprio — 28/10/2026

O escuro era o claro invertido: toda borda `var(--ink)` virava um traço creme quase branco, e o
resultado parecia wireframe. Agora a linha estrutural tem token próprio:

- `--line` (light `#1d2234`, dark `rgba(221,219,199,.26)`) e `--line-soft` (dark `.13`) — 20 regras de
  borda passaram a usá-los; no claro nada muda porque `--line` é a própria tinta.
- Superfícies no escuro não têm contorno duro: ganham gradiente sutil + brilho interno no topo
  (`inset 0 1px 0`) e sombra quente. O cartão de login mantém o deslocamento verde-limão da identidade,
  em opacidade .22.
- Fundo: três glows (azul no topo, limão à direita, coral embaixo) + textura de pontos em 4 px + gradiente
  vertical, para o escuro ter profundidade em vez de ser um retângulo chapado.
- Detalhes de identidade no escuro: aba ativa e links em verde-limão, `btn.primary` limão com texto escuro,
  foco de input com halo limão, hover de tabela esverdeado.

O modo claro foi conferido depois da troca (mesmos valores visuais de antes).

## 20. Catálogo com prateleiras + notas externas — 28/10/2026

Decisão de produto: **híbrido**, não "Netflix puro". Carrossel resolve descoberta; aluno de biblioteca
normalmente já sabe o que procura, então grade + filtro continuam sendo o caminho principal.

- `GET /api/catalogo` (autenticado) devolve `mais_alugados` (contagem real de empréstimos),
  `melhores_avaliados` e `novidades` (últimas catalogadas).
- **Notas**: `livros.nota_media/nota_qtd/nota_fonte`, preenchidas por `tools/notas_acervo.py`.
  Fonte primária é o Open Library (`search.json` com `ratings_average`/`ratings_count`; também existe
  `works/<id>/ratings.json` por obra). O Google Books tem `averageRating`/`ratingsCount` no `volumeInfo`
  (é o campo que aparece no preenchimento automático), mas a API sem chave responde **429** neste IP — o
  script tenta Google por ISBN e cai para o Open Library. Cobertura medida: **34 de 36 obras**.
- Títulos brasileiros quase nunca têm nota na edição nacional; o script usa mapa `ALIASES` (título em
  inglês) e fica com o candidato de **maior número de avaliações**, então "A Revolução dos Bichos" pega a
  nota de *Animal Farm* (604 avaliações) em vez de 2 avaliações da edição PT.
- Ranking usa nota ponderada `(media*qtd + 4*25)/(qtd+25)` — sem isso um livro com 5 avaliações de 5,0
  passaria na frente de um com 405 de 4,3.
- Front: três prateleiras com deslize horizontal (setas no desktop, swipe no celular, ocultas abaixo de
  760 px) + grade paginada de 24 por página (6×4). Busca ou filtro de gênero escondem as prateleiras —
  é o modo "quero achar este livro".
- **Sem nota inventada**: a prateleira diz que a nota é do catálogo externo. Avaliação dos próprios alunos
  (estrelas + comentário) exigiria tabela nova e ficou fora deste escopo.

## 21. Turma/série do aluno — agora automática (28/10/2026)

Primeiro tentei o caminho do HTML (`sed.educacao.sp.gov.br/GradeAulaAluno/Index`) e ele **não serve**:
o JWT do `LoginCompletoToken` não é sessão do site (a página devolve 200 com a home de login), o
`POST /Logon/Logon/` com usuário/senha voltou 200 com 0 bytes e sem o cookie `SED=`, e o `DadosUsuario`
não tem campo de série.

O caminho que **funciona** é a API de declaração de matrícula do mesmo BFF:

```
GET https://sedintegracoes.educacao.sp.gov.br/saladofuturobffapi/ncaapi/api/DeclaracaoMatriculaSF/Matriculas
     ?anoLetivo=2026&codigoAluno=<codigo>
     Ocp-Apim-Subscription-Key: <a mesma chave do login>
```

Devolve `escola`, `tipoDeEnsino`, `turma` (ex.: `6082 - DESENVOLVIMENTO DE SISTEMAS - 3ª SERIE B MANHA
ANUAL`) e `situacaoAluno`.

Três detalhes que custaram a descoberta:

1. **A sessão vem do próprio login.** O `LoginCompletoToken` responde com `Set-Cookie: sf_sid=<uuid>;
   domain=.educacao...` (+ `ApplicationGatewayAffinity*`). Por isso `sed_client` passou a usar
   `requests.Session()`: sem o cookie `sf_sid` a matrícula responde **401**.
2. **`codigoAluno` não é o `CD_USUARIO`.** Com o `CD_USUARIO` inteiro a resposta é 200 com
   `Matriculas: []`; o código certo é o **CD_USUARIO sem o último dígito** (confirmado em 3 contas).
3. **Precisa de User-Agent de navegador.** Com o UA do `python-requests` o gateway responde **403** com
   ~200 KB de HTML; com UA de Chrome, 200 e o JSON. (A resposta também vem com BOM UTF-8, então
   `resp.json()` estoura — daí o `_json_bom()`.)

Implementação em `sed_client.py`: `_turma_da_matricula()` roda depois do login, tenta o ano corrente e o
anterior, prefere a matrícula com `situacaoAluno = Ativo` e formata para `3ª série B · Manhã`
(`_formatar_turma`). Falha em silêncio: sem turma o login continua funcionando e a UI mostra "—".
O espelho (`alunos.turma`) só é sobrescrito quando vem algo.
