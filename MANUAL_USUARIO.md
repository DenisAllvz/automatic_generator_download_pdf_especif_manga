# Manual — Manga Manager 2.5.0

## Baixar e receber somente PDFs

1. Abra MangaManager.exe dentro da pasta completa do aplicativo.
2. Em Adicionar obra, cole o link e clique em Analisar URL.
3. Confira o nome, o idioma e os capítulos selecionados.
4. Clique em Baixar e gerar PDFs.

Dois capítulos são baixados simultaneamente por padrão. Em Configurações,
**Capítulos simultâneos** permite escolher de 1 a 3. A mudança vale para os próximos
agendamentos; tarefas já iniciadas terminam normalmente. Cada fonte continua sujeita
a limites de conexão, espera e acesso. A conversão de PDF ocorre uma por vez para
controlar o consumo de memória.

Os arquivos finais ficam em `pasta da obra/PDF`. As páginas temporárias são removidas
somente depois de validar o PDF e seu recibo de integridade. Se a conversão falhar,
as imagens ficam para retomar. A nova versão também limpa caches anteriores que
possuam PDF confirmado. Arquivos desconhecidos e PDFs sem prova de integridade não
provocam exclusão automática das imagens. Capas pequenas ficam na pasta de dados.

## Biblioteca com capas

A aba Biblioteca mostra as obras e o número de capítulos lidos. As capas são obtidas
do arquivo local ou da fonte. Quando não há capa da fonte, o primeiro PDF disponível
pode gerar uma miniatura. **Atualizar capas** busca capas pendentes; **Trocar capa**,
dentro da obra, permite selecionar uma imagem local. Uma letra aparece enquanto
não houver capa nem PDF disponível.

Clique na capa para abrir **todos os capítulos**, incluindo os não baixados. A lista
mostra leitura, posição e disponibilidade do PDF. Há busca e uma barra de rolagem
visível. Ctrl e Shift selecionam vários capítulos; Ctrl+A seleciona os capítulos da
lista. As ações consideram os capítulos visíveis no filtro.

- **Marcar como lidos / Marcar não lidos:** altera os selecionados de uma vez.
- **Continuar lendo:** abre a leitura incompleta mais recente ou o próximo não lido disponível.
- **Ler selecionado:** abre o primeiro selecionado; duplo clique no capítulo também abre.
- **Baixar selecionados:** enfileira os capítulos marcados, pulando PDFs já confirmados.
- **Renomear:** muda o título exibido; atualizações do site preservam o nome escolhido.

Quando todos os capítulos cadastrados estiverem lidos, aparece um pequeno selo verde
na capa. Novos capítulos não lidos retiram o selo. Marcar como não lido reinicia o
progresso dos selecionados. Renomear não move pastas nem PDFs existentes.

**Importar PDFs** aceita uma pasta de PDFs locais ou uma pasta de obras. Capítulos
já registrados são preservados sem duplicar os PDFs conhecidos.

## Leitor integrado

O leitor abre os PDFs dentro do aplicativo, com rolagem contínua e ajuste à largura.
Oferece zoom, ajuste à página inteira, seleção de página, capítulo anterior/próximo,
busca de texto e tela cheia. F11 alterna tela cheia; Escape sai dela; Ctrl+F abre a
busca; Ctrl+mais e Ctrl+menos ajustam o zoom.

A posição é salva automaticamente, inclusive dentro de uma página longa. Ao reabrir,
o aplicativo retoma de onde parou. Ao permanecer no fim da última página, marca o
capítulo como lido. O botão Biblioteca fecha o leitor e libera os recursos do PDF.
As marcações de leitura ficam no banco local e não alteram o PDF.

A busca de texto funciona em PDFs com texto pesquisável. Páginas escaneadas em
imagem não recebem OCR nesta versão. Não há anotações nem edição dos PDFs.

## Downloads limpos e relatórios

Downloads mostra a fila atual e falhas recentes, sem os capítulos concluídos e sem
repetir tentativas antigas. Falhas de sessões anteriores ficam resumidas; **Tentar
novamente** permite retomá-las sem despejar o histórico na tabela. A busca filtra
obra, capítulo, estado e erro. A barra de rolagem pode ser arrastada diretamente.

Sem selecionar linhas, Pausar e Retomar atuam nas tarefas visíveis elegíveis;
Tentar novamente alcança as falhas elegíveis que correspondam à busca, inclusive as
anteriores resumidas. Com seleção, a ação fica restrita às linhas marcadas.
O botão direito oferece cancelar/remover, preservando os arquivos.

Ao finalizar uma obra, o aplicativo salva o relatório, avisa e arquiva as tarefas
concluídas/canceladas. **Relatórios** abre os arquivos em `data/logs/downloads`.
Erros também podem ser exportados em Diagnóstico. Se o relatório não puder ser
salvo, os registros permanecem no banco. Os PDFs nunca são apagados ao limpar a fila.

## Vários links e fontes

Em Adicionar obra, expanda Vários links, cole um por linha e use Baixar lista de links.
O lote prefere PT-BR quando disponível, ignora URLs repetidas e pula PDFs confirmados.
Uma fonte com erro não impede as seguintes. Parar lista cancela a consulta atual;
capítulos já enfileirados permanecem na fila. Resumo em `logs/ultimo-lote-de-links.json`.

Use o link da obra para escolher vários capítulos. Intervalos como `1-20, 35` são
posições da lista, não a numeração publicada. **Consultar novos capítulos** procura
atualizações das obras. Fontes podem mudar, bloquear ou retirar conteúdo.
O programa não contorna login, DRM, CAPTCHA ou acesso restrito.

## Atualizar, preservar e compartilhar

Feche a versão antiga antes de abrir a nova. Neste workspace, a pasta 2.5.0 recebe
uma cópia dos dados da 2.3.0. A versão antiga é preservada. O banco é atualizado para
SQLite schema 2, com leitura e capas; os registros anteriores são mantidos.

Para amigos, envie MangaManager-2.5.0-Windows-x64-portable.zip. Eles devem extrair a
pasta inteira, inclusive _internal, e abrir o exe. O ZIP não contém dados pessoais.
Backups do aplicativo guardam registros; imagens, PDFs e capas devem ser preservados
separadamente ao mudar de computador. O modo portátil usa `data` junto ao exe.

Leitura e arquivos são locais nesta versão Windows. Android, tablet e sincronização
entre dispositivos ficam para uma etapa futura; ainda não há serviço de sincronização.

## Google Drive: conectar a conta e enviar só o que falta

Não requer o Google Drive para computador. O aplicativo abre a autorização no navegador
e usa a API do Drive para conferir a pasta e enviar PDFs. A conta ainda precisa ser
configurada: esta distribuição não contém uma credencial OAuth registrada no Google.

Configuração inicial, uma vez:

1. No Google Cloud Console, crie ou selecione um projeto e ative a **Google Drive API**.
2. Configure o consentimento OAuth no Google Auth Platform. Para uso pessoal em teste,
   escolha público externo e adicione seu e-mail em **Usuários de teste**.
3. Em **Clientes**, crie um cliente OAuth do tipo **Aplicativo para computador / Desktop**
   e baixe seu JSON. Credenciais de aplicativo Web não servem para este fluxo.
4. Na aba **Google Drive**, clique em **Importar credencial OAuth** e selecione esse JSON.
5. Clique em **Conectar Google Drive**. No navegador do Google, escolha sua conta e
   autorize o acesso. Sua senha é digitada somente no Google. Não envie credenciais pelo chat.

Guia oficial: https://developers.google.com/identity/protocols/oauth2/native-app

O acesso solicitado permite consultar sua pasta existente e enviar arquivos. O escopo
Drive completo é necessário neste fluxo para identificar também os PDFs copiados antes
manualmente. O aplicativo implementa consulta, criação de pastas e envio; não apaga
arquivos do Drive nem substitui PDFs com conteúdo diferente. Uma aplicação em teste
pode precisar de nova autorização; erros são apresentados na própria tela.

Depois de conectar:

1. Cole o link da pasta desejada e clique em **Usar pasta**, ou use **Buscar no Drive**.
2. Escolha **Todas as obras** com **Uma subpasta por obra** para uma pasta geral.
   Se a pasta escolhida já for de um único mangá, selecione essa obra e desmarque
   a opção de subpastas para usar os PDFs diretamente nela.
3. Clique em **Conferir capítulos**. A tabela resume por obra o que já existe e o que
   falta. **Ver capítulos pendentes** abre os detalhes quando necessário.
4. Clique em **Enviar faltantes**. PDFs existentes são reconhecidos pelo tamanho e
   conteúdo, inclusive quando foram renomeados. Arquivos com identidade de capítulo
   correspondente, mas conteúdo diferente, são preservados e informados como conflito.
5. Opcionalmente, marque **Enviar PDFs novos automaticamente**. Com o programa aberto,
   ele confere a cada minuto e após concluir downloads. Uma falha adia a nova tentativa.

O envio ocorre em segundo plano, em blocos pequenos. **Cancelar** preserva os arquivos
concluídos. Sessões de upload ficam criptografadas e podem ser retomadas após abrir
novamente; se a sessão expirar, um novo envio será iniciado. A conclusão verifica
integridade no Drive. Não são enviados imagens temporárias, capas, banco ou logs.
Um único resumo local fica em `data/logs/drive/last_sync.json`.

A sincronização é do PC para o Drive. Não apaga PDFs que só estejam na nuvem,
não baixa arquivos do Drive e não sincroniza marcações ou posição de leitura do tablet.
**Desconectar** remove a sessão local; para revogar a permissão no Google, use a página
de aplicativos conectados da sua conta. O JSON importado e tokens são protegidos pelo
Windows para o usuário atual; outra máquina precisa conectar sua conta novamente.

Validação desta entrega: API simulada e executável local. Login e envio na sua conta
real dependem da credencial OAuth e da sua autorização inicial; não foram executados.
