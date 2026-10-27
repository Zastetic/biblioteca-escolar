# Relatório — identificação de livros por foto

**Data:** 9 de outubro de 2026 (UTC−03)
**Estado:** pausado a pedido do Okai. Nenhum livro foi cadastrado nesta investigação.

## Objetivo do fluxo

No formulário administrativo de livros, a foto anexada é referência para identificar a obra. A prévia dessa foto deve ficar separada da capa editorial retornada pelos catálogos. A busca começa somente após clicar em **Preencher automaticamente**; os dados do registro catalogado são revisados antes de salvar.

## Implementações anteriores registradas

- `mvp/web/app.js`: seleção da foto exibe uma prévia local; busca explícita pelo botão **Preencher automaticamente**; a prévia da foto e a prévia da capa catalográfica são independentes. Os campos só são reportados como preenchidos depois de conferir os valores copiados. Correspondências não confirmadas exigem seleção explícita em **Usar registro**.
- `mvp/web/estilo.css`: layout das duas prévias e dos resultados de catálogo.
- `mvp/server/main.py`: CSP permite `blob:` em `img-src`, necessário para carregar a prévia local do navegador.
- `mvp/server/book_catalog.py`: consulta Google Books e Open Library; seleciona imagens Google Books na ordem `extraLarge → large → medium → thumbnail` e usa Open Library tamanho `L` como alternativa.
- `mvp/tests/test_book_catalog.py`: suíte de catálogo ampliada para seis testes.
- Versão pública verificada anteriormente: `20261009-book-catalog-02`; serviço `biblioteca-server.service` confirmado ativo e site público respondendo HTTP 200.

### Evidências de testes anteriores

- Teste Playwright em servidor descartável com capa de *Romeu e Julieta*: a prévia carregou e título, autor e ano foram copiados. Não houve salvamento de livro.
- Seis testes unitários do catálogo passaram; `node --check`, `py_compile` e `git diff --check` também passaram na rodada registrada.
- Houve uma rodada anterior bem-sucedida da suíte de API (o histórico registra 44/44). Uma execução posterior reutilizou um banco de teste já alterado e terminou com erro; ela não deve ser tratada como teste aprovado.
- A publicação de `20261009-book-catalog-02` e a disponibilidade do serviço/site foram verificadas no histórico da tarefa anterior. Nenhuma publicação ocorreu durante a investigação atual.

## Investigação atual: gênero de *Romeu e Julieta*

1. O Okai informou que o livro da foto é de fato *Romeu e Julieta*. A interpretação visual anterior de “Holy Bible / New King James Version” estava errada; essa conclusão e a busca de catálogo feita para Bíblia foram retiradas.
2. Chamadas à rota oficial de visão Mistral leram `Romeu & Julieta`, autor William Shakespeare, sem ISBN. As variantes Ministral 14B, Ministral 8B e Mistral Medium deram resultados compatíveis com a correção do Okai; a rotação da imagem não alterou o título reconhecido.
3. Consulta correta ao catálogo (`book_catalog.search_catalogs`, título “Romeu e Julieta”, autor “William Shakespeare”):
   - Google Books: estado `quota` durante a consulta.
   - Open Library: estado `ok`; encontrou edições de 1998, 2004 e 2021, com score 100, além de outras edições.
   - O campo `genero` veio vazio em todas as correspondências consultadas.
   - As obras Open Library consultadas (`OL26416148W`, `OL20644334W`, `OL35919228W`) retornaram `subjects: null` na API de obras.
4. Em `book_catalog._genre`, o mapeamento já converte categorias que contenham `romance` ou `romantic` para `Romance`. O problema observado nesta consulta é que as fontes não forneceram categoria/assuntos para o mapeamento; não foi aplicada regra local específica para esse título.
5. O formulário oferece o gênero `Romance`, mas nenhuma correspondência consultada o trouxe automaticamente. O Okai ainda não autorizou ou pediu uma regra editorial local para esse título.

## Investigação atual: prévia piscando

- O site público respondeu HTTP 200 e serviu `app.js?v=20261009-book-catalog-02`, com o marcador da prévia `Foto enviada` e a classe de prévias independentes.
- Em teste Playwright isolado, usando a própria foto e uma resposta simulada para a busca (sem chamar o serviço de visão), a imagem permaneceu carregada e visível:
  - `preview_before_lookup_stable=True`
  - `preview_after_lookup_stable=True`
  - estado final: URL `blob:`, largura natural 4080 px, prévia não oculta.
- O código atual só revoga a URL local ao selecionar outro arquivo ou ao reiniciar/cancelar o formulário; a consulta em si não a revoga. Não foi possível reproduzir a piscada no teste isolado. Isso não descarta comportamento específico do navegador/dispositivo do Okai.
- Para continuar esse diagnóstico, é útil uma gravação curta indicando se a piscada acontece ao anexar a foto, enquanto consulta, ou depois de aparecer o resultado.

## Estado e pendências ao pausar

- Nenhum registro foi salvo no acervo durante a investigação atual.
- Nenhum arquivo do aplicativo foi alterado e nenhum novo deploy foi feito durante a investigação atual; foram criados apenas scripts temporários de diagnóstico em `/tmp`.
- Gênero automático: pendente decidir entre manter o preenchimento estritamente baseado em metadados externos ou criar uma classificação editorial local `Romeu e Julieta → Romance`, identificada como curadoria local.
- Prévia piscando: não reproduzida no teste; aguardar, se necessário, vídeo do comportamento no navegador do Okai.
- A interpretação anterior de Bíblia foi erro do assistente, não conclusão válida sobre o exemplar. A identificação corrigida é *Romeu e Julieta*.

## Arquivos principais

- `mvp/web/app.js`
- `mvp/web/estilo.css`
- `mvp/web/index.html`
- `mvp/server/main.py`
- `mvp/server/book_catalog.py`
- `mvp/tests/test_book_catalog.py`
- Relatório atual: `RELATORIO_IDENTIFICACAO_CAPA_20261009.md`
