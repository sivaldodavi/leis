# Como atualizar

## Pré-requisitos

- Python 3.12+
- Hugo Extended 0.154.5+
- Acesso ao repositório `sivaldodavi/leis`
- Acesso ao bucket R2 `camara-pinheiro` (para novos PDFs)

## 1. Atualizar o banco

O banco oficial é `db/legislacao_pinheiro.db`. Alterações de dados devem ser feitas nele, com cuidado para preservar as tabelas de correspondência e a tabela `observacao`.

Antes de mudanças estruturais:

```bash
cp db/legislacao_pinheiro.db /tmp/legislacao_pinheiro.db.bak
```

Registre decisões e pendências em `observacao`, não em comentários soltos.

## 2. Regenerar o site

```bash
export LEIS_BASE="$PWD"
export LEIS_DB="$PWD/db/legislacao_pinheiro.db"
python3 gen.py
```

O comando reescreve `content/`, `data/` e `static/dados/`. Confira o diff antes de commitar:

```bash
git status --short
git diff --stat
```

## 3. Adicionar PDFs ao R2

Os PDFs não entram no Git. Use variáveis de ambiente temporárias; nunca grave credenciais no repositório.

```bash
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="..."
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="..."
export RCLONE_CONFIG_R2_ENDPOINT="https://SEU_ENDPOINT.r2.cloudflarestorage.com"

rclone copy ./acervo "R2:camara-pinheiro" \
  --include "*.pdf" \
  --transfers 12 --checkers 16 \
  --header-upload "Content-Type: application/pdf"
```

Preserve a estrutura relativa:

```text
acervo/documentos/mocoes/MOC_059_2026.pdf
→ camara-pinheiro/documentos/mocoes/MOC_059_2026.pdf
```

Verifique a contagem e os tamanhos:

```bash
find ./acervo -type f -iname '*.pdf' | wc -l
rclone lsf R2:camara-pinheiro --recursive --files-only --include '*.pdf' | wc -l
rclone check ./acervo R2:camara-pinheiro --include '*.pdf' --size-only
```

## 4. Atualizar os links

O `gen.py` usa:

```python
PDF_BASE = "https://pub-c9e7f83be13a4ced872b3bd4d04c075a.r2.dev/documentos"
```

Se o domínio público do R2 mudar, atualize essa constante e rode o `gen.py` novamente. Os relatórios usam a base `.../relatorios/` e não são gerados pelo `gen.py`.

## 5. Publicar

```bash
git add -A
git commit -m "Atualiza dados e acervo"
git push origin main
```

O GitHub Actions executa o `gen.py`, constrói com Hugo e publica no Pages.

## 6. Validar

```bash
curl -I https://leis.sivaldodavi.com.br/
curl -I https://leis.sivaldodavi.com.br/proposicoes/moc-059-2026/
curl -I https://leis.sivaldodavi.com.br/dados/camara.json
```

Confira também:

- uma página de norma com PDF;
- uma sessão com votação;
- um perfil de vereador;
- o workflow em **Actions → Publicar site**.

## 7. Reverter

Se o build falhar:

```bash
git revert HEAD
git push origin main
```

Se o problema for só de dados, restaure o banco do backup e rode o `gen.py` novamente.

## Regras

- Não commite PDFs.
- Não use Git LFS.
- Não commite credenciais do R2.
- Não altere `content/` gerado à mão sem ajustar o `gen.py`.
- Mantenha `observacao` atualizada.
- Confira a fonte oficial antes de publicar correções factuais.
