# Atualização 2.5.0 — Google Drive

Suite completa: 176 testes aprovados em 67,04 s na execução final. JUnit da
execução anterior, também com 176 aprovados: `tmp/tests-2.5.0.xml`.

Integração nova: OAuth PKCE com callback local e rejeição de estado incorreto,
cancelamento, DPAPI real no Windows, paginação, renovação de token, upload em
blocos, retomada após reiniciar e resposta perdida, comparação por conteúdo,
conflitos preservados, cópia manual durante a prévia e falha isolada por PDF.
UI exercitada com botões reais, cancelamento e heartbeat durante tarefa em segundo plano.

Executável 2.5.0: sete telas, sincronização incremental simulada e proteção DPAPI,
além de leitor nativo, biblioteca, leitura e geração automática de PDFs. Manifesto
e exe conferidos por `scripts/verify_build.py`; evidência `tmp/build-smoke.json`.
Captura da nova tela: `tmp/ui-review/screen-6.png`.

Nenhuma conta Google real foi autorizada. A API e o protocolo OAuth foram testados
com respostas simuladas. Falta importar uma credencial OAuth Desktop própria e
autorizar a conta para validar login, permissões e transferência real. O build foi
executado neste Windows; não foi validado em uma máquina limpa.

As seções seguintes são históricas.

# Atualização 2.4.0 — Biblioteca, leitor e concorrência

Suite completa: 146 testes aprovados em 72,68 s, incluindo o pipeline real com
dois downloads, PDFs e exclusão do cache. JUnit: `tmp/tests-2.4.0.xml`.

Cobertura nova: dois downloads simultâneos iniciados em ordem natural, limite de
concorrência, conversão PDF serializada, remoção de imagens apenas após PDF válido,
cache preservado em falha, reutilização offline de PDF sem imagens, migração schema 1
para 2, importação sem duplicar capítulos, renomeação persistente, seleção múltipla,
leitura independente do estado de download e proteção contra eventos antigos de leitura.

UI: retorno ao ponto exato dentro da página, fim de leitura automático, selo verde,
lista completa, resumo de falhas antigas com repetição funcional, ausência de concluídos
na tabela e barras de rolagem visíveis. As capas e o leitor foram inspecionados com
uma cópia isolada dos dados do usuário; alterações de marcação nessa cópia não foram
aplicadas aos dados reais. Foram obtidas três capas/miniaturas e aberto o Vagabond.
Capturas: `tmp/ui-review/library-real.png`, `chapters-real.png`, `reader-real.png`.

Memória: processo com 1.000 capítulos na fila, 50 atualizações, conversão e navegação
pelas 41 páginas reais do Vagabond. Fila: 102,53 → 105,14 MB; conversão: 146,47 MB
de pico; leitor: 235,10 MB; final: 125,98 MB. Evidência:
`tmp/memory-profile-2.4.0-real.json`. São medidas desta carga e deste computador,
não um teto universal nem um teste de downloads de rede ilimitados.

Executável 2.4.0 verificado em dados temporários: seis telas, leitor Qt PDF nativo
renderizando uma página, capas e leitura persistidas, `pdf_only=true`, geração automática,
relatório e limpeza da fila. Hashes de código e exe conferidos: `tmp/build-smoke.json`.
Ainda não representa execução em outra máquina Windows limpa.

As seções seguintes são históricas.

# Atualização 2.3.0 — RAM e novos recursos

130 testes aprovados em 51,09 s. JUnit: `tmp/tests-2.3.0.xml`.
Novos cenários: preservação dos pixels e bytes JPEG, EXIF, perfil ICC, estrutura PDF,
hash sem leitura integral, descarte de PDF modificado, links duplicados, idioma PT-BR,
falha isolada de fonte, cancelamento da consulta, clique real no lote e busca com
comandos apenas nas linhas visíveis. Inclui os testes de responsividade da 2.2.1.

Medição Windows por GetProcessMemoryInfo, amostrada a cada 20 ms, com dados isolados:
1.000 capítulos na fila (101,32 MB), 50 atualizações (103,85 MB), conversão do
Vagabond capítulo 1 com 41 páginas (pico total 159,81 MB, saída 48,16 MB), final
117,01 MB. Evidência: `tmp/memory-profile-real.json`. Outro teste de 20 páginas
sintéticas atingiu 130,76 MB. São medições de cenários específicos, não limite universal.

As páginas 1 e 41 foram renderizadas pelo Poppler e inspecionadas visualmente;
cores, texto, proporções e conteúdo foram preservados. Foram conferidas também
as telas de interface. As imagens e os PDFs originais do usuário não foram alterados.

Executável 2.3.0 validado em diretório temporário: cinco telas, PDF automático,
catálogo sem JSON, relatório e limpeza da fila; hashes conferidos.
Evidência: `tmp/build-smoke.json`.

As seções seguintes são históricas.

# Atualização 2.2.1 — Desempenho e travamentos

120 testes aprovados em 60,93 s. Após o ajuste final dos callbacks, os 13 testes
de interface passaram novamente em 7,33 s. Testes novos cobrem 1.000 capítulos,
reutilização dos itens, ausência de widgets por linha, 100 solicitações de atualização
agrupadas em um worker, timers da interface durante bloqueio do banco e cadastro
de 500 capítulos por link com proteção contra duplo clique.

Antes da correção, uma fila isolada com 1.000 capítulos levava 436,30 / 485,70 /
875,31 ms por atualização e acumulava 5.002 QProgressBar após reconstruções.
Depois, o mesmo cenário usa somente duas barras gerais, sem widgets nas linhas.
O benchmark final (`scripts/benchmark_ui.py`), executado durante o build, mediu
29,42 a 47,66 ms incluindo consulta e ordenação do banco. Evidências:
`tmp/performance-before/result.json` e `tmp/performance-after.json`.
Os tempos medem este computador e este cenário, não a velocidade de rede.

Executável 2.2.1 validado em diretório temporário: cinco telas, PDF automático,
catálogo sem JSON, relatórios e limpeza da fila; hashes conferidos. Evidência:
`tmp/build-smoke.json`. A validação usa o host atual, sem ensaio em outra máquina.

As seções abaixo são históricas.

# Atualização 2.2.0 — Interface, catálogo e ordem natural

117 testes aprovados em 55,35 s. Mais 10 testes de UI aprovados após o ajuste
final de navegação. Casos novos: 500 manifestos consolidados, falha de gravação
preservando JSONs originais, arquivos desconhecidos preservados, download/PDF
sem JSON na pasta, ordem natural com concorrência antiga configurada, cliques
reais de pausa/retomada/repetição, seleção isolada, cancelamento/remoção pelo
menu e abertura das pastas. Capturas: `tmp/ui-review/screen-0.png` a `screen-4.png`.

Migração em cópia de dados reais: 327 JSONs reconhecidos removidos após salvar
os respectivos dados no catálogo (164 manifestos); nenhum JSON restante nessa
cópia. Evidência: `tmp/catalog-real-review/evidence.json`. Nenhuma alteração na
pasta real, pois a versão anterior estava aberta.

Executável congelado 2.2.0 testado a partir de diretório temporário: cinco telas,
`clean_metadata=true`, `automatic_pdf=true`, `download_log=true`,
`queue_cleaned=true`, PDF de duas páginas e exportação em lote.
Evidência: `tmp/build-smoke.json`; hashes do código e executável conferidos.
As seções abaixo são históricas.

# Atualização 2.1.1 — Relatório antes de limpar a fila

Novos testes: PDF real preservado após arquivar a tarefa, TXT/JSON e histórico
persistentes, conclusão única, proteção da fila quando o disco falha, obra com
500 capítulos e última tarefa pausada, falhas mantidas na fila e aviso de conclusão
com remoção das linhas na interface. O smoke do executável verifica log e limpeza.
**111 testes aprovados, 0 falhas, 0 ignorados**, 47,77 s. Evidência: `tmp/test-results.xml`.
Executável 2.1.1 validado em dados temporários: `download_log=true`,
`queue_cleaned=true`, `automatic_pdf=true`, cinco telas e PDF de duas páginas.
Evidência: `tmp/build-smoke.json`; hashes conferidos.
Os resultados abaixo da seção 2.1.1 são históricos.

# Atualização 2.1.0 — 10/10/2026

Conversão automática testada no fluxo de download; somente conclui após o PDF.
Recuperação de falha de conversão usa imagens completas sem conexão. Pastas
renomeadas são reencontradas e o PDF é gerado no novo local. Novos testes cobrem
WebP, GIF/PNG em paleta, transparência, DPI inválido, páginas longas e pausa segura.
UI tem cinco telas e quatro colunas em Downloads, sem Biblioteca/Detalhes/leitor.

Teste com dados reais: cópia isolada do banco portátil 2.0.2, relocalização de
Vagabond e conversão offline do capítulo 1 em PDF de 41 páginas.
Evidência: `tmp/vagabond-recovery/evidence.json`. Os arquivos de imagens permanecem
intactos. Os demais PDFs antigos são enfileirados ao abrir a nova versão.
MangaLivre.blog consultado novamente: Vagabond, 328 capítulos; seletor próprio
remove o rótulo de navegação e limpa nomes repetidos, mantendo decimais.

**107 testes aprovados, 0 falhas, 0 ignorados**. JUnit: `tmp/test-results.xml`.
Executável 2.1.0 verificado em diretório temporário: `frozen=true`, cinco telas,
conversão automática pelo DownloadManager, PDF de duas páginas, reutilização
do PDF validado e exportação PDF/CBZ. Evidência: `tmp/build-smoke.json`.
Hashes do código e executável conferidos. Verificação no host atual; Windows
limpo sem Python permanece não testado.
As seções seguintes são histórico das versões anteriores.

# Validação — 10/10/2026

## Atualização 2.0.2

**97 testes aprovados, 0 falhas, 0 ignorados**, 41,04 s. JUnit: `tmp/test-results.xml`.
Novos testes cobrem título e capítulo direto FlorManga, ausência de navegação recursiva,
listagem deduplicada, domínio exato e robots.txt 4xx indisponível versus acesso negado
à imagem, Disallow explícito e erros 429/503/rede.
Teste real do link solicitado: nome da obra correto, um capítulo selecionado,
8 imagens baixadas e PDF com 8 páginas. Página da obra: 158 capítulos listados.
Arquivos do teste completo: `tmp/flormanga-check/1791637623393109000/` (SQLite,
manifestos, imagens e PDF). Completude HTML permanece não comprovada.
Tentativas posteriores do site retornaram falha temporária e timeout, inclusive
na instalação Python. O teste de rede no exe não foi concluído; inicialização e
exportação local no exe passaram. Não se promete disponibilidade contínua da fonte.
Os resultados da 2.0.1 abaixo são históricos.

## Atualização 2.0.1

Suíte atual: **84 aprovados, 0 falhas, 0 erros, 0 ignorados**, 41,32 s (pytest).
Inclui exportação de vários PDFs, colisões de nomes, preservação de arquivos
existentes, continuidade após capítulo inválido, progresso e interface responsiva.
Inclui também metadados MangaDex, paginação, idiomas, versões, URLs inseguras,
cache com troca de servidor, título da obra e correção de registros existentes.
Verificação real isolada (`scripts/verify_sources.py --full-chapter`): MangaLivre.blog
identificou Vagabond e 328 capítulos. MangaDex identificou o título em português,
589 registros em 11 idiomas e baixou o capítulo 1 PT-BR (Ikki Scans) completo:
14 páginas verificadas e PDF com 14 páginas. Evidência: `tmp/source-review/live-evidence.json`.
Leitor removido; a interface atual tem sete telas. Smoke atualizado verifica dois
PDFs em lote e exportação CBZ. As referências ao leitor abaixo são históricas da 2.0.0.

Executável 2.0.1 também verificado com `verify_build.py --output-name MangaManager-2.0.1
--source-check https://mangadex.org/title/39e55355-dfb4-44e9-bd0b-df1fc3a0e33e`:
`frozen=true`, sete telas, exportação de dois PDFs em lote e capítulo MangaDex PT-BR
baixado/verificado com PDF de 14 páginas. Evidência: `tmp/build-smoke.json`.

## Resultado executado
Comando final:

```powershell
.\venv\Scripts\python.exe -m pytest -q --junitxml=tmp\test-results.xml
```

**66 aprovados, 0 reprovados, 0 ignorados, 39,95 s.** Evidência JUnit em
`tmp/test-results.xml`. A suíte não acessa fontes de mangá externas: usa HTML,
cliente falso, servidor aiohttp local e Chromium com rede interceptada.
O asyncio do Windows travou no sandbox; a execução validada ocorreu fora dele.

Cobertura exercitada: URLs e DNS privados, redirecionamentos, path traversal,
MIME/assinatura, imagens pequenas/corrompidas, nomes Windows, decimais/especiais,
variantes, HTML malformado/vazio, JSON-LD, lazy loading/srcset, cinco páginas de
listagem, HTTP 404/429/500, timeout, Retry-After, robots.txt, crawl-delay,
manifestos, retomada por página, pausa/cancelamento, fila, recuperação SQLite,
esquema futuro rejeitado, importação, preservação em atualizações, CBZ/PDF,
Qt workers, erros visíveis, progresso, encerramento e redimensionamento.

## Matriz obrigatória

| Cenário | Estado | Evidência e limite |
|---|---|---|
| A — Obra nova | Validado em simulação | Extração, prévia Qt, seleção e download com fixtures; nenhuma fonte real |
| B — Interrupção | Validado em simulação | Pausa conserva primeira página, retomada só baixa a ausente; SQLite recupera running como paused. Queda de energia forçada não ensaiada |
| C — 200 para 250 | Validado em simulação | 250 capítulos finalizados, 200 páginas validadas/reutilizadas, exatamente 50 downloads |
| D — Corrupção | Validado em simulação | Hash/decodificação detectam corrupção; reparação baixa somente a página inválida |
| E — Incompatível | Validado em simulação | HTML vazio/malformado/layout desconhecido gera ExtractionError e erro visível |
| F — Falha temporária | Validado em simulação | 429/500/timeout com tentativas limitadas; falha preservada com página/tentativas/HTTP; repetição manual |
| G — Paginação | Validado em simulação | 250 capítulos em cinco páginas, URLs duplicadas eliminadas, ordenação correta |
| H — Reinício | Validado em persistência/smoke | Reabertura de SQLite recupera biblioteca/tarefas; preferências roundtrip; posição de leitura persistida |
| I — Executável | Parcialmente validado | Windows x64 atual: inicialização, oito telas, banco, leitor, posição e CBZ/PDF. Máquina limpa sem Python não disponível |

## Build e UI
Executados `scripts/build_windows.py --portable` e `scripts/verify_build.py`.
O build final tem manifesto com hashes; o verificador confirmou correspondência
com o código atual. Evidência: `tmp/build-smoke.json` (`frozen=true`, oito telas,
reader=true, cbz=true, PDF com duas páginas). Captura: `tmp/build-ui.png`.
Host: Windows 11 build 26300 x64, Python 3.13.0, PySide6 6.12.0, PyInstaller 6.22.3.

A primeira execução do exe falhou por DLL ICU incompatível capturada do PATH.
O build foi corrigido para usar ICU do Windows e runtimes VC compatíveis com Qt;
o smoke posterior passou. Warnings de módulos opcionais/plataformas do PyInstaller
foram inspecionados; os recursos efetivamente exercitados passaram no exe.

`scripts/capture_ui.py` produziu as oito telas com dados simulados, revisadas
visualmente. Tema claro e janela 960×650 passaram em teste. Leitura vertical
carrega imagens próximas da viewport. PDF sintético foi renderizado com Poppler;
páginas examinadas visualmente, sem alterar PDFs do usuário.

## Preservação real de dados
`scripts/validate_legacy_import.py`: **664 PDFs de quatro obras** importados para
banco isolado em tmp. Todos conservaram tamanho e mtime; todos são `legacy`.
Nenhuma integridade absoluta desses PDFs foi inferida. A comparação é de metadados
de arquivo, não de hashes de toda a coleção. Evidência:
`tmp/legacy-import-check/evidence.json`. Downloads originais ficaram no lugar.

## Fontes
Boruto Explorer e MangaLivre: seleção de domínio/seletores legados em fixtures;
não ensaiados contra os sites reais. HTML genérico: fixtures. Chromium opcional:
dois testes reais de motor com conteúdo sintético e requisição privada bloqueada.
Permissões, layouts atuais e fontes reais continuam não validados. Ausência de
erro numa fixture não comprova compatibilidade pública.

## Limites ainda não validados
Máquina limpa sem Python, Windows 10, ARM64, instalador Inno Setup, assinatura de
código, bibliotecas muito grandes, servidor com Range confiável e fontes autenticadas.
Não há login/cookies pessoais, browser incluído no exe, retomada de bytes parciais,
atualizador automático do programa nem integração real de fonte nesta entrega.

Verificação adicional no executável congelado, oculto, com dados isolados: 1.000
tarefas e conversão offline das 41 páginas concluída; pico de 127,25 MB. O
controlador encerrou o processo de teste ao terminar a amostragem. Evidência:
`tmp/memory-frozen.json`. O smoke separado validou encerramento normal.
