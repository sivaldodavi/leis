---
title: "Fontes e dados"
---

## De onde vêm os dados

Os dados legislativos deste site (leis, dispositivos e explicações simples) **foram criados e organizados por nós**, a partir dos PDFs publicados pela Câmara Municipal de Pinheiro. A base local (`legislacao_pinheiro.db`) é atualizada quando novos documentos são publicados.

## Fundamento legal

- **Lei 12.527/2011 (Lei de Acesso à Informação)** — transparência ativa e divulgação de informações de interesse coletivo.
- **Lei Complementar 131/2009** — transparência na gestão fiscal.
- **Decreto 8.777/2016** — política de dados abertos: dados públicos, acessíveis, em formato aberto, legíveis por máquina e atualizados.

## Dados que publicamos (formato aberto)

Estes arquivos são atualizados a cada publicação do site e podem ser usados livremente (com atribuição à fonte):

- `/dados/legislacao.json` — leis e atos da Câmara, dispositivos e metadados.
- `/dados/busca.json` — índice de busca (trechos de dispositivos) para pesquisa client-side.

Exemplo de uso:

```bash
curl https://leis.sivaldodavi.com.br/dados/legislacao.json
```

Resposta: JSON em UTF-8.

## Termos de uso

Os dados são públicos. Ao reutilizar, cite a fonte (Câmara Municipal de Pinheiro e/ou este site) e a data de atualização. Este site não é oficial da Câmara.
