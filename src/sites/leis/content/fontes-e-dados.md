---
title: "Fontes e dados"
---

## De onde vêm os dados

Os dados legislativos deste site (normas, dispositivos e proposições) foram organizados a partir dos PDFs e páginas publicados pela Câmara Municipal de Pinheiro. A base local (`legislacao_pinheiro.db`) é atualizada quando novos documentos são publicados.

## Dados eleitorais (TSE)

Partido, votos e situação eleitoral dos vereadores/autores vêm do portal de dados abertos do Tribunal Superior Eleitoral (TSE), referentes à eleição municipal de 2024:

- [TSE — Candidatos 2024](https://dadosabertos.tse.jus.br/dataset/candidatos-2024)
- [TSE — Resultados 2024](https://dadosabertos.tse.jus.br/dataset/resultados-2024)

Usamos apenas informações públicas de candidatura e votação. **Não usamos dados de bens, despesas, financiamento de campanha ou qualquer informação financeira do TSE.**

## Dados que publicamos (formato aberto)

Estes arquivos são atualizados a cada publicação do site e podem ser usados livremente (com atribuição à fonte):

- `/dados/legislacao.json` — normas, dispositivos e metadados.
- `/dados/busca.json` — índice de busca (trechos de dispositivos).
- `/dados/proposicoes.json` — proposições, autores e situação.
- `/dados/autores.json` — vereadores/autores, partido, votos e proposições.

Exemplo de uso:

```bash
curl https://leis.sivaldodavi.com.br/dados/legislacao.json
```

Resposta: JSON em UTF-8.

## Termos de uso

Os dados são públicos. Ao reutilizar, cite a fonte (Câmara Municipal de Pinheiro, TSE e/ou este site) e a data de atualização. Este site não é oficial da Câmara.
