---
title: "API"
---

## Endpoints (JSON estático)

Base: `https://leis.sivaldodavi.com.br/dados/`

- `/dados/legislacao.json` — normas, dispositivos e metadados.
- `/dados/busca.json` — índice de busca (trechos de dispositivos).
- `/dados/proposicoes.json` — proposições, autores e situação.
- `/dados/autores.json` — vereadores/autores, partido, votos, mandatos e proposições.

Versão estável: `/dados/v1/...` (mesmos arquivos).

## Exemplos

```bash
curl https://leis.sivaldodavi.com.br/dados/legislacao.json
```

```js
const r = await fetch('https://leis.sivaldodavi.com.br/dados/proposicoes.json');
const dados = await r.json();
console.log(dados.length);
```

## CORS

CORS habilitado (`Access-Control-Allow-Origin: *`) para `/dados/*`.

## Termos

Dados públicos. Cite a fonte e a data de atualização. Sem autenticação e sem garantia de disponibilidade.
