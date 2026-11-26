# Leis de Pinheiro

Portal de normas, proposições, sessões e votações da Câmara Municipal de Pinheiro.

- Site: <https://leis.sivaldodavi.com.br/>
- Publicação: GitHub Pages, construída pelo workflow `.github/workflows/pages.yml`.

## Estrutura

- `content/`, `data/`, `layouts/`, `static/`: fonte do site Hugo.
- `gen.py`: gera as páginas e os JSONs do site a partir do banco SQLite.
- `db/legislacao_pinheiro.db`: banco oficial usado na geração.

Os PDFs dos relatórios e das proposições não fazem parte do repositório. Eles são publicados no Cloudflare R2: proposições e normas em `https://pub-c9e7f83be13a4ced872b3bd4d04c075a.r2.dev/documentos/` e relatórios em `https://pub-c9e7f83be13a4ced872b3bd4d04c075a.r2.dev/relatorios/`. O `gen.py` gera os links do site apontando para essa base.

## Como o site é publicado

A cada push na branch `main`, o GitHub Actions:

1. executa `gen.py` usando `db/legislacao_pinheiro.db`;
2. constrói o site com Hugo Extended 0.154.5;
3. publica `public/` no GitHub Pages.

O domínio personalizado `leis.sivaldodavi.com.br` está configurado no repositório e o HTTPS é emitido pelo GitHub Pages.

## Execução local

Requer Python 3 e Hugo Extended 0.154.5 ou superior.

```bash
export LEIS_BASE="$PWD"
export LEIS_DB="$PWD/db/legislacao_pinheiro.db"
python3 gen.py
hugo server --minify
```
