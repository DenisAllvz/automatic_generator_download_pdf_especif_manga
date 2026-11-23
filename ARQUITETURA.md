# Fluxo atual — 2.1.0

UI Qt com cinco telas e jobs fora da thread gráfica. `DownloadManager` baixa e
valida as páginas, persiste o manifesto, chama `ensure_pdf` e só então conclui.
Conversões são serializadas para limitar uso de memória; a fila continua exibindo
progresso durante a geração. Cancelamento aguarda a gravação atômica da conversão.
`recovery.py` reencontra pastas pelo manifesto e atualiza caminhos registrados.
Capítulos completos entram no caminho de conversão local, sem consulta HTTP.
SQLite mantém metadados e histórico internamente, sem tela Biblioteca ou leitor.
`export.py` mantém funções PDF/CBZ para CLI e testes, além do PDF automático na UI.

A descrição abaixo documenta a arquitetura inicial; funcionalidades visíveis
removidas incluem Biblioteca, Detalhes e leitor interno.

# Arquitetura

## Camadas
* `main.py`: inicializa Qt, configurações, logging e SQLite; smoke test isolado.
* `app/core`: Settings centralizada, exceções acionáveis, validação de URLs,
  PublicResolver e redaction de logs. Logging rotaciona arquivos técnicos.
* `app/models`: Manga, Chapter e PageList tipados. PageList.authoritative informa
  se a fonte realmente comprova o total esperado, não apenas o HTML visível.
* `app/extractors`: protocolo, registro e adaptadores HTML. O registro escolhe
  domínios exatos/sufixos legítimos antes do fallback. Paginação tem limite e
  falha explicitamente quando excedido, sem confirmar resultado parcial.
* `app/infrastructure`: HTTP reutilizável, restrições DNS/redirect, SQLite com
  conexões curtas e lock, nomes Windows, contenção e escrita atômica.
* `app/services`: Library registra obras sem excluir capítulos ausentes na fonte;
  DownloadManager agenda capítulos e persiste progresso; integrity verifica
  assinatura, dimensões, hashes e manifesto; export mantém bytes no CBZ.
* `app/ui`: MainWindow organiza telas; Job/QueueWorker usam QThread e sinais;
  Reader carrega páginas locais visíveis para reduzir memória.

## Fluxo e concorrência
UI captura URL/seleção → Job analisa HTML via HttpClient/Registry → prévia →
Library salva metadados/chapters → tarefa SQLite → QueueWorker executa asyncio →
DownloadManager valida páginas, salva imagem `.part` + replace e manifesto →
sinais e timer atualizam UI. Até quatro capítulos configuráveis; imagens são
sequenciais dentro do capítulo, com conexões por domínio limitadas.
Banco tem chave estrangeira, WAL e migração `user_version=1`. Versões futuras
devem acrescentar migrações, nunca recriar tabelas destrutivamente.

Ao reiniciar, tarefas `running` viram `paused`. Arquivos temporários nunca são
concluídos. Manifestos mantêm cache anterior e páginas concluídas na ordem atual.
Interrupção de um arquivo reinicia esse arquivo; não se usa Range sem validação
de ETag/Last-Modified e suporte confiável da fonte.

## Integridade
`verified`: manifesto íntegro e fonte autoritativa; `downloaded`: páginas descobertas
salvas, total da fonte não comprovado; diagnóstico `unverifiable`: arquivos locais
válidos, mas completude desconhecida; `incomplete`: faltas, corrupção, temporários
ou suspeita de duplicação. `legacy`: PDF importado sem manifesto/proveniência.
Esses estados não são intercambiáveis. Imagens pequenas válidas são aceitas.

## Compatibilidade
As entradas históricas são wrappers; snapshots preservam o código original e as
alterações locais encontradas. Nenhuma pasta antiga é removida. PDFs legados são
abertos no visualizador padrão; a biblioteca de imagens usa o leitor integrado.
Importação nunca vincula automaticamente uma URL contida em metadados externos.

## Manutenção
Injeção ocorre em Registry e DownloadManager (client_factory). Testes usam fixtures,
cliente falso e servidor aiohttp local. A UI recebe serviços reais, e seus workers
limitam o tratamento genérico de exceções à fronteira com a interface: erros são
registrados e exibidos. O núcleo usa exceções específicas e não oculta falhas.

## Renderização opcional
BrowserRenderer reutiliza HttpClient para cumprir cada requisição interceptada;
contexto sem cookies pessoais, permissões vazias, service workers bloqueados,
WebSockets fechados e proxy de descarte para evitar tráfego direto. GET tem limite
de quantidade/tamanho; POST e recursos fora da lista são negados. Chromium mantém
seu sandbox e tem rolagem/tempo limitados. Fallback só ocorre quando HTML falha e
o usuário ativa a opção; o exe comunica que não inclui navegador.
Referência: [rotas e isolamento Playwright](https://playwright.dev/python/docs/api/class-browsercontext).

Referências consultadas: [QThread e sinais](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html),
[aiohttp connector/resolver](https://docs.aiohttp.org/en/stable/client_reference.html).
