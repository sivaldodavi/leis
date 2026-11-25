---
title: "Fontes e dados"
---

## De onde vêm os dados

O site da **Câmara Municipal de Pinheiro não oferece uma API pública**. A única fonte estruturada é o **Portal de Transparência (Fiorilli)**, que publica endpoints JSON para despesas, receitas, licitações, contratos, transferências e (quando disponível) pessoal.

Os dados legislativos deste site (leis, dispositivos e explicações por perfil) **foram criados e organizados por nós**, a partir dos PDFs publicados pela Câmara. Como o portal não permite automação de download, os PDFs foram baixados e processados manualmente para montar o banco de dados local (`legislacao_pinheiro.db`). A base é atualizada quando novos documentos são publicados.

## Fundamento legal

- **Lei 12.527/2011 (Lei de Acesso à Informação)** — transparência ativa e divulgação de informações de interesse coletivo.
- **Lei Complementar 131/2009** — transparência na gestão fiscal.
- **Decreto 8.777/2016** — política de dados abertos: dados públicos, acessíveis, em formato aberto, legíveis por máquina e atualizados.

## Dados que publicamos (formato aberto)

Estes arquivos são atualizados a cada publicação do site e podem ser usados livremente (com atribuição à fonte):

- `/dados/legislacao.json` — leis e atos da Câmara, dispositivos e metadados.
- `/dados/busca.json` — índice de busca (trechos de dispositivos) para pesquisa client-side.
- `/dados/dinheiro_publico.json` — despesas, fornecedores, licitações, contratos e emendas (a partir do portal Fiorilli).

Exemplo de uso:

```bash
curl https://leis.sivaldodavi.com.br/dados/legislacao.json
```

```js
const r = await fetch('https://leis.sivaldodavi.com.br/dados/dinheiro_publico.json');
const dados = await r.json();
console.log(dados.resumo);
```

Resposta: JSON em UTF-8. Valores monetários vêm como texto com vírgula decimal (formato brasileiro).

## API do portal Fiorilli (Câmara)

A API oficial da Câmara pode ser consultada diretamente no portal:

- [Portal de Transparência (Fiorilli)](http://177.136.250.170:5656/SCPIWEB_CMDEPINHEIRO/versaoJson/)

Este site não reproduz a documentação completa da API; use o link acima para consultar endpoints e parâmetros.

## Termos de uso

Os dados são públicos. Ao reutilizar, cite a fonte (Câmara Municipal de Pinheiro e/ou este site) e a data de atualização. Este site não é oficial da Câmara.