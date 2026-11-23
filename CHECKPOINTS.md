# Checkpoints

1. Auditoria concluída antes das alterações de implementação. Originais preservados
   em legacy/, dados mantidos. Caracterização AST executada separadamente.
2. Modelos, validação de URLs, cliente HTTP, extratores e SQLite implementados.
3. Fila persistente, download por página e manifestos implementados.
4. Interface Qt, biblioteca, leitor, diagnóstico e exportações implementados.
5. Chromium opcional restaurado com mediação HTTP; DOM simulado e bloqueio de
   requisição privada testados. Pacote portátil mantém HTML, sem navegador.
6. Importação dos 664 PDFs existentes para banco isolado validada, sem mudar
   tamanhos/datas dos arquivos. Cenário 200 existentes + 50 novos aprovado.
7. Testes de regressão, revisão visual e correção de empacotamento ICU/VC runtime.
8. Documentação e pacote Windows preparados. Validação em máquina limpa e fontes
   reais permanece pendente e está declarada na matriz de aceitação.

As evidências de testes e build serão registradas em VALIDACAO.md.
