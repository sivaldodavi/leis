# Dados

## Snapshot atual

| Indicador | Total |
| --- | ---: |
| Normas | 108 |
| Dispositivos publicados | 1.252 |
| Proposições | 1.911 |
| Autores | 34 |
| Vereadores | 42 |
| Sessões | 246 |
| Presenças | 3.205 |
| Matérias de sessão | 1.825 |
| Votações | 416 |
| Votos nominais | 5.441 |
| PDFs no R2 | 1.742 |

Período: **27/03/2023 a 25/11/2026**.

O banco tem `PRAGMA integrity_check = ok` no snapshot publicado.

## Entidades

### Normas e dispositivos

Cada norma tem identificação, tipo, número, data, situação, ementa e, quando disponível, texto integral e dispositivos. O site publica 1.252 dispositivos; o banco contém 1.503 registros, incluindo estruturas auxiliares de numeração e hierarquia.

### Proposições

As proposições cobrem indicações, moções, requerimentos, projetos de lei, projetos de decreto legislativo, projetos de resolução, emendas e prestações de contas. Cada registro pode ter:

- identificação e ano;
- tipo e classe;
- situação;
- ementa/assunto;
- autores;
- tema, objeto e local;
- texto integral ou justificativa;
- arquivo PDF de origem;
- vínculo com sessões e votações.

### Autores e vereadores

`autores` representa quem assina proposições, incluindo o Executivo e outros órgãos. `vereador` representa os parlamentares e seus mandatos. O vínculo `vereador_autor` conecta as duas visões.

Os dados eleitorais vêm do TSE: nome de urna, nome completo, partido, votos, situação da candidatura e legislatura. Quando um autor não tem correspondência direta com um vereador, o perfil é mantido separado.

### Sessões, presenças e votações

- `sessao`: 246 sessões, com data, tipo e número.
- `presenca`: 3.205 registros de presença.
- `materia`: 1.825 matérias registradas nos relatórios.
- `votacao`: 416 votações.
- `voto`: 5.441 votos nominais.

As votações são exibidas por sessão e por proposição. O voto nominal é preservado com o nome do vereador e o resultado.

## Correspondência entre matérias e proposições

O processo de unificação adotou estas regras:

1. Matérias com identificação compatível foram ligadas a proposições existentes.
2. Matérias sem correspondência e com ano válido viraram novas proposições com `origem_registro = 'relatorio'`.
3. Matérias com ano inválido ficaram fora de `proposicoes` e foram registradas em `observacao` como exceção.
4. Autores sem perfil correspondente receberam um novo registro em `autores`.

Resultado do snapshot:

- **1.819 matérias mapeadas** para proposições;
- **155 proposições novas** vindas dos relatórios;
- **6 matérias com ano inválido** fora da base de proposições;
- **2 autorias novas** pendentes de revisão.

## PDFs

O acervo documental tem 1.742 PDFs no Cloudflare R2:

- **1.442** documentos de proposições e normas em `documentos/`;
- **300** relatórios de sessões em `relatorios/`.

O site referencia **1.437 URLs únicas** de proposições e normas. Os 300 relatórios estão armazenados, mas não são linkados nas telas do site. Cinco documentos do acervo não aparecem em links no snapshot atual.

Os PDFs não são versionados no Git. O `gen.py` monta as URLs a partir de `PDF_BASE`; o restante do acervo é publicado no R2.

## Observações e qualidade

A tabela `observacao` registra decisões e pendências com `categoria`, `descricao` e `status`. Exemplos de categorias:

- **Correção do relatório** — ajustes feitos durante a migração;
- **Exceção** — matérias que não entraram na base principal;
- **Limitação** — decisões de escopo e dados que ficaram fora;
- **Pendência de revisão** — autorias ou correspondências que precisam de conferência.

Essas observações são parte da documentação viva da base. Antes de alterar uma regra de migração, consulte os registros existentes para não perder o contexto.

## Limitações conhecidas

- O recorte termina em **25/11/2026**.
- A correspondência entre matérias e proposições é heurística e pode ter casos ambíguos.
- Seis matérias com ano inválido ficaram fora de `proposicoes`.
- Duas autorias novas ainda não têm revisão manual concluída.
- Nem todo PDF possui link no site; os relatórios são um acervo à parte.
- A base não substitui a publicação oficial no Diário Oficial nem os sistemas da Câmara.

## Consultas úteis

```sql
-- Proposições por ano
SELECT ano, COUNT(*) AS total
FROM proposicoes
GROUP BY ano
ORDER BY ano;

-- Vereadores com mais presenças
SELECT v.nome, COUNT(*) AS presencas
FROM presenca p
JOIN vereador v ON v.id = p.vereador_id
GROUP BY v.id
ORDER BY presencas DESC
LIMIT 10;

-- Votações por resultado
SELECT resultado, COUNT(*) AS total
FROM votacao
GROUP BY resultado
ORDER BY total DESC;

-- Observações da migração
SELECT categoria, status, COUNT(*) AS total
FROM observacao
GROUP BY categoria, status
ORDER BY categoria;
```
