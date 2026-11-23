# Relatório — Manga Manager 2.5.0

## Google Drive — 2.5.0

Nova aba com conexão OAuth Desktop, escolha de pasta, prévia por obra e envio
apenas dos PDFs que faltam. Compara tamanho e conteúdo, preserva conflitos,
retoma uploads interrompidos e oferece envio automático com o aplicativo aberto.
Credenciais e sessões ficam protegidas por DPAPI, fora do ZIP de distribuição.
O envio é PC → Drive, sem sincronização de progresso de leitura.

176 testes passaram. Executável validado com sete telas e serviço Drive simulado.
Não havia credencial OAuth no projeto nem autorização da conta Google: a primeira
conexão requer a configuração descrita em MANUAL_USUARIO.md. Não foi realizado envio
real à nuvem, nem teste em outra máquina Windows limpa.

## Biblioteca, leitor e PDF como arquivo final — 2.4.0

Dois capítulos simultâneos por padrão (limite configurável de 1 a 3), com início na
ordem natural e apenas uma conversão por vez. A biblioteca mostra capas pequenas e
todos os capítulos, permite seleção/marcação em massa, mantém renomeações e exibe um
selo verde ao completar a leitura. O leitor nativo tem rolagem contínua, zoom, tela
cheia, navegação, pesquisa de texto e retomada dentro da página. Não há OCR nem edição.

A fila visual mostra as tarefas atuais, resume falhas antigas e elimina repetições de
tentativas; relatórios continuam preservados. Barras de rolagem estão mais visíveis.
Imagens temporárias são removidas somente após PDF validado; falhas mantêm arquivos
para retomar. Capas ficam na pasta de dados e podem usar miniatura da primeira página.

Banco schema 2 guarda a leitura separadamente dos downloads. Dados antigos são copiados
sem substituir a versão anterior. Android e sincronização de leitura ficam para uma etapa futura.
No cenário de 1.000 capítulos e PDF real de 41 páginas, incluindo leitura, pico de
235,10 MB. Suite e evidências em VALIDACAO.md.

## Memória e novos fluxos — 2.3.0

Gerador PDF incremental, sem retenção das imagens do capítulo inteiro. Hash de PDF
lido em blocos, com JPEG sem recodificação, EXIF e ICC preservados. Fila usa itens
leves, atualizações agrupadas e leitura de banco fora da interface. O cadastro por
link não bloqueia a janela; cliques repetidos e segunda instância são controlados.

Adicionados lotes de links com cancelamento e preferência PT-BR, detecção de PDFs
já prontos e busca na fila com comandos restritos ao filtro. Referências de HakuNeko,
MangaDex Downloader, FMD2 e Mihon documentadas em REFERENCIAS.md.

130 testes aprovados. No cenário com 1.000 tarefas e PDF real de 41 páginas, pico
de 159,81 MB. As medições são específicas deste computador e carga. Dados de uso
preservados; build separado da versão anterior.

## Desempenho — 2.2.1

As atualizações periódicas não consultam o banco na thread gráfica nem recriam
controles por capítulo. As consultas são agrupadas e limitadas a uma por vez;
apenas valores alterados são aplicados aos itens existentes. Pausa/retomada em
lote e consultas ao analisar uma URL também ficam em workers. Cliques repetidos
durante o cadastro são ignorados até terminar a gravação.

Validação: 120 testes aprovados, incluindo 1.000 capítulos na fila, banco ocupado
e cadastro por link com 500 capítulos enquanto timers da interface continuam
funcionando. Nova versão isolada; biblioteca, imagens e PDFs anteriores preservados.

## Interface e organização — 2.2.0

Interface renovada com cartões, navegação lateral, controles essenciais e opções
avançadas recolhidas. Downloads usa Pausar, Retomar e Tentar novamente; sem seleção,
atuam em todas as tarefas elegíveis. Cancelar e remover ficam no botão direito.
Uma falha na montagem dos botões utilitários foi corrigida. Os capítulos executam
um por vez, em ordem natural, ignorando prioridades antigas.

Um único catálogo SQLite oculto por obra reúne metadados, páginas e recibos de PDF.
A migração dos JSONs antigos verifica a cópia persistida antes de remover os arquivos.
Arquivos desconhecidos ou inválidos são mantidos. A recuperação termina antes de
iniciar os downloads. Imagens e PDFs permanecem preservados.

Validação: 117 testes aprovados, inspeção das cinco telas e smoke do executável
2.2.0 com PDF automático, catálogo sem JSON, log e fila limpa. Uma cópia dos arquivos
atuais de Vagabond consolidou 327 JSONs em um catálogo com 164 capítulos.
A pasta real ainda não foi migrada porque o executável 2.1.1 estava aberto;
feche-o antes de abrir o 2.2.0, que fará a migração automaticamente.

## Conclusão e limpeza da fila — 2.1.1

Ao finalizar uma obra, o aplicativo salva os capítulos em relatórios TXT/JSON,
arquiva as tarefas concluídas/canceladas no histórico SQLite e as remove da fila.
Um aviso informa o resultado e permite abrir o relatório. Falhas permanecem para
repetir. Enquanto houver tarefas na fila, em andamento ou pausadas daquela obra,
a conclusão não é anunciada. Outras obras podem continuar baixando normalmente.
Se a gravação do relatório falhar, todas as tarefas ficam preservadas.

## Comportamento entregue

O download agora inclui a geração automática de um PDF por capítulo. A tarefa
só fica concluída depois de o PDF ser aberto e sua contagem de páginas conferida.
Os arquivos ficam em `pasta da obra/PDF`. Novas pastas usam o nome da obra;
as já existentes são preservadas, inclusive quando o usuário as renomeou.

A navegação tem Início, Adicionar obra, Downloads, Diagnóstico e Configurações.
Biblioteca, Detalhes e leitor interno não são apresentados. Downloads mostra
obra/capítulo, status, porcentagem e erro. Ao chegar a 100%, o status “Gerando PDF”
distingue a conversão da conclusão. Falhas têm detalhes por duplo clique.

MangaLivre.blog recebeu seletor próprio de capítulos para evitar nomes como
“Iniciar Leitura”, remoção de rótulos repetidos e identificação da obra para links
diretos de capítulo. O nome da obra também pode ser corrigido na prévia.
MangaDex e FlorManga mantêm seus adaptadores e a seleção por idioma.

## Recuperação e proteção dos arquivos

Na abertura, imagens completas registradas sem PDF voltam à fila automaticamente.
Pastas movidas dentro do destino são reencontradas pelo manifesto e identidade
da obra; caminhos são corrigidos no banco. O botão Recuperar pasta movida permite
selecionar outro destino. PDFs são gerados com gravação temporária e substituição
atômica; as imagens originais não são apagadas ou recomprimidas.

WebP e formatos incompatíveis são normalizados em PNG temporário sem perda;
transparência incompatível recebe fundo branco. Imagens longas são escaladas
somente nas dimensões do PDF, sem recortar pixels. JPEG/PNG compatíveis são
embutidos diretamente. Cada PDF tem um recibo `.pdf.json` de integridade.

Falha de conversão preserva o estado de imagens completas. Repetir usa o manifesto
local validado, sem consultar o site. PDFs previamente gerados e correspondentes
são reutilizados; um arquivo desconhecido não é sobrescrito. Pausar durante a
conversão aguarda a gravação segura e preserva o arquivo concluído.
Bloqueios temporários do Windows na gravação do manifesto têm tentativas limitadas.

## Evidência real e testes

Os registros de Vagabond apontavam para uma pasta antiga; as imagens estavam em
`Minha Biblioteca/vagabonde`. Em banco de teste copiado da versão 2.0.2, a recuperação
reencontrou os capítulos e gerou o PDF do capítulo 1 com 41 páginas, sem rede.
O PDF está em `C:/Users/denil/Downloads/Minha Biblioteca/vagabonde/PDF/`.
Evidência: `tmp/vagabond-recovery/evidence.json`.
Isso confirma a recuperação desse capítulo; não afirma que todos os capítulos
antigos foram convertidos nesta execução. Eles serão processados pela fila na abertura.

A suíte cobre conversão automática, falha e repetição offline, pastas movidas,
transparência/paleta/WebP, DPI inválido, página longa, pausa durante a conversão,
nomes e navegação MangaLivre, idioma MangaDex, rede e integridade.
Resultado final e executável estão registrados em VALIDACAO.md.

## Distribuição

Executável: `dist/MangaManager-2.1.1/MangaManager.exe`.
Envie aos amigos o ZIP `dist/MangaManager-2.1.1-Windows-x64-portable.zip`,
que inclui as dependências e exclui dados pessoais. É necessário extrair a pasta
inteira, inclusive `_internal`. A cópia local recebe os registros da versão 2.0.2
após empacotar o ZIP; a versão anterior e os downloads originais são preservados.

O executável é verificado em dados isolados no host atual. Uma máquina Windows
limpa, sem Python, continua não testada. Nenhum instalador ou assinatura de código
foi produzido. Disponibilidade das fontes e completude de HTML dependem do site.
