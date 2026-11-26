# Fontes e método

## Fontes

### Câmara Municipal de Pinheiro

- Portal: <https://www.cmpinheiro.ma.gov.br/>
- Normas, proposições, sessões, presenças, votações e relatórios em PDF.
- As páginas de matéria e os relatórios de sessão são a base da camada parlamentar.

### TSE — dados abertos

- Dataset de candidaturas: <https://dadosabertos.tse.jus.br/>
- Usado para nome de urna, nome completo, partido, votos, situação eleitoral e legislatura dos vereadores.

## Coleta

O acervo foi coletado a partir de páginas e PDFs públicos. O processo prioriza:

1. **Rastreabilidade**: cada documento mantém sua origem e, quando possível, o arquivo de origem.
2. **Preservação**: os PDFs são mantidos separados do banco e do site.
3. **Reprodutibilidade**: o banco e o `gen.py` permitem reconstruir as páginas e os JSONs.
4. **Moderação no acesso**: a coleta respeita limites de requisição e não contorna bloqueios do servidor.

> [!IMPORTANT]
> Se o portal bloquear o acesso automatizado, a conduta correta é aguardar, reduzir o ritmo ou solicitar o acervo pelos canais oficiais / Lei de Acesso à Informação. O projeto não usa rotação de IP, VPN ou qualquer mecanismo para burlar bloqueios.

## Normalização

### Nomes e autores

- Nomes de urna e nomes completos do TSE são comparados com as autorias das proposições.
- Variações de grafia, partículas e acentos são normalizadas.
- Quando não há correspondência segura, o autor é mantido separado e a pendência é registrada.

### Datas e tipos

- Datas são normalizadas para `AAAA-MM-DD` quando a fonte permite.
- Tipos de proposição são mapeados para um vocabulário controlado.
- Situações são traduzidas para rótulos legíveis no site.
- Anos inválidos ou ausentes não são inventados: viram exceção registrada.

### Matérias e proposições

- A identificação da matéria é comparada com a identificação da proposição.
- Correspondências exatas e compatíveis são ligadas em `materia_proposicao`.
- Matérias sem correspondência e com ano válido geram proposições novas.
- Casos ambíguos não são forçados: ficam registrados em `observacao`.

## Geração do site

O `gen.py` transforma o banco em:

- páginas de normas, proposições, sessões e vereadores;
- JSONs de consulta e filtros;
- índices de busca;
- links para os PDFs no R2.

O Hugo consome esse material e gera o site estático. O GitHub Actions executa o processo a cada push.

## Verificações

Antes de publicar, o fluxo verifica:

- execução do `gen.py` sem erro;
- build do Hugo;
- publicação do artefato no Pages;
- disponibilidade do domínio.

Verificações manuais recomendadas após mudanças de dados:

- contar PDFs no bucket e comparar com o acervo local;
- validar que os PDFs começam com `%PDF`;
- conferir se cada `pdf_url` tem arquivo correspondente;
- abrir uma proposição, uma norma, uma sessão e um vereador.

## Limitações do método

- A correspondência de nomes e matérias é assistida por regras, não por revisão humana completa.
- A coleta representa o que estava disponível no portal no momento da captura.
- PDFs podem faltar, estar duplicados ou ter nomes que não correspondem exatamente ao identificador.
- O site é informativo e não substitui a fonte oficial.

## Como citar

Ao citar uma norma, uma proposição ou um voto, use a fonte oficial indicada na página e confira a publicação no Diário Oficial ou no sistema da Câmara. O site ajuda a localizar e comparar; não é a autoridade emissora do ato.
