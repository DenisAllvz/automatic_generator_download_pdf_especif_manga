# Build Windows

## Gerar

Para preservar uma pasta portátil já usada, gere a atualização separadamente:
`python scripts/build_windows.py --portable --output-name MangaManager-2.5.0`.
Use o mesmo `--output-name MangaManager-2.5.0` nos scripts verify_build.py e
package_windows.py. A saída será `dist/MangaManager-2.5.0/MangaManager.exe`;
ZIP: `dist/MangaManager-2.5.0-Windows-x64-portable.zip`.
Windows x64 com Python x64 3.11+; ambiente efetivamente utilizado: Windows 11 build
26300, Python 3.13.0, PySide6 6.12.0 e PyInstaller 6.22.3.
Alvo: Windows 10 x64 atualizado com a API ICU do sistema ou Windows 11 x64.

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe scripts/build_windows.py --portable
.\venv\Scripts\python.exe scripts/verify_build.py
```

Saída: `dist/MangaManager/MangaManager.exe`. Distribua **toda a pasta MangaManager**,
inclusive `_internal`; copiar apenas o exe não funciona. O build onedir evita
descompactação a cada abertura. É windowed (sem terminal), com ícone próprio.

`portable.flag` guarda dados em `data/` ao lado do exe. A pasta precisa ser gravável;
não use Program Files neste modo. Sem flag, os dados ficam em LocalAppData/MangaManager.
A biblioteca de imagens tem seu próprio destino configurável. Nenhum caminho do
desenvolvedor é necessário em execução. Não requer privilégios de administrador.
O script recusa reconstruir uma pasta dist que já contenha `data/`, protegendo dados
portáteis. O manifesto do build registra hashes do código e do exe.

Durante a validação, corrigiu-se a captura de ICU do PATH do desenvolvedor: o build
remove a DLL incompatível e usa a API ICU fornecida pelo Windows. Runtimes Visual C++
são alinhados com o wheel Qt para evitar misturar versões com as do Python antigo.

Playwright/Chromium não são dependências deste build. Conteúdo exclusivamente
JavaScript não está garantido. Python e Qt necessários à aplicação são incluídos.

## Verificar
O verificador inicia o exe congelado a partir de pasta temporária, cria banco isolado,
carrega as sete telas Qt, abre PDF no leitor nativo, verifica leitura e capas, exercita a conversão automática e exporta dois PDFs em lote, salva JSON e screenshot e encerra. Isso valida inicialização
no host de build; **não representa máquina limpa sem Python**. Faça ensaio separado
em Windows limpo, sem Python, com fonte autorizada, download, pausa, reinício,
diagnóstico, leitura e exportação. Windows 10 x64 é alvo previsto, ainda não validado.
ARM64 nativo, macOS e Linux não foram validados nesta entrega.

Teste real optativo no executável: acrescente ao verify_build.py
`--source-check https://mangadex.org/title/39e55355-dfb4-44e9-bd0b-df1fc3a0e33e`.
Ele usa dados temporários, baixa um capítulo PT-BR e verifica a contagem do PDF.

## Instalador
`scripts/installer.iss` é uma receita Inno Setup 6 por usuário, sem admin. Compile
somente após validar o diretório dist. O compilador não foi instalado e o instalador
não foi validado. Não remove biblioteca nem dados de LocalAppData ao desinstalar.
Assinatura de código exige certificado próprio; não foi realizada.

Referência: [PyInstaller — usage](https://www.pyinstaller.org/en/stable/usage.html).

## Google Drive no executável

A integração usa a biblioteca padrão do Python e a API oficial do Google Drive.
O smoke verifica DPAPI e sincronização incremental com serviço simulado; não autentica
contas reais. Nenhuma credencial OAuth ou conta é incluída no ZIP. Cada instalação
precisa importar uma credencial Desktop e autorizar sua conta, conforme o manual.
Tokens e sessões são protegidos por DPAPI para o usuário Windows atual; copiar
`data/drive` para outro computador não transfere uma sessão utilizável.
