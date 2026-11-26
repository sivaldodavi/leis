# -*- coding: utf-8 -*-
"""Une o banco de sessões (camara_pinheiro.db) ao banco oficial do site.

Uso:
    python3 migrar_camara.py --oficial /caminho/legislacao_pinheiro.db \
        --camara /caminho/camara_pinheiro.db

O script é idempotente: pode ser rodado de novo sobre o mesmo banco oficial.
Ele NÃO apaga leis, dispositivos, proposições ou autores existentes.
"""
import argparse
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# Tabelas do banco de sessões que entram no banco oficial
# ---------------------------------------------------------------------------
CORE_TABLES = [
    "arquivo_origem",
    "vereador",
    "vereador_grafia",
    "vereador_partido",
    "sessao",
    "presenca",
    "cargo_mesa",
    "materia",
    "materia_autor",
    "destinatario",
    "materia_destinatario",
    "pauta_ocorrencia",
    "votacao",
    "voto",
    "excecao",
    "observacao",
    "pessoa_politica",
]

# Grafias curtas que são a mesma pessoa de uma grafia completa.
# A chave aponta para o registro canônico (o de maior ocorrência).
CANON = {
    1: 2,    # Abdias de -> Abdias de Jesus Silva
    17: 18,  # Jaelson -> Jaelson Pereira Souza
    19: 18,  # Jaelson Souza -> Jaelson Pereira Souza
    20: 22,  # João -> João Jose Martins Frazão
    21: 22,  # João Jose Martins -> João Jose Martins Frazão
    24: 25,  # Jose Albino Costa -> Jose Albino Costa Araujo
    29: 30,  # José Maria Naziazeno -> José Maria Naziazeno Filho
    32: 33,  # Keimilson Sodré -> Keimilson Sodré Guterres
    37: 38,  # Paulo Henrique Trinta -> Paulo Henrique Trinta Marques
    40: 41,  # Rubemar de Jesus Diniz -> Rubemar de Jesus Diniz Ribeiro
}

TIPO_MAP = {
    ("Indicação", None): ("indicacao", "IND", "Indicação"),
    ("Moção", None): ("mocao", "MOC", "Moção"),
    ("Requerimento", None): ("requerimento", "REQ", "Requerimento"),
    ("Projeto de Lei", "Legislativo"): ("projeto_lei_legislativo", "PLL", "Projeto de Lei do Legislativo"),
    ("Projeto de Lei", "Executivo"): ("projeto_lei_ordinaria", "PLO", "Projeto de Lei Ordinária"),
    ("Projeto de Decreto Legislativo", None): ("projeto_decreto_legislativo", "PDL", "Projeto de Decreto Legislativo"),
    ("Projeto de Resolução", None): ("projeto_resolucao", "PRE", "Projeto de Resolução"),
    ("Projeto de Emenda à Lei Orgânica", None): ("emenda_lei_organica", "PELO", "Emenda à Lei Orgânica"),
    ("Emenda ao Projeto de Lei", None): ("emenda_projeto_lei_legislativo", "EMD", "Emenda a Projeto de Lei"),
}

SUBTIPO_MAP = {
    "Pesar": "pesar",
    "Aplausos": "aplauso",
    "Parabenização": "parabenizacao",
    "Agradecimento": "agradecimento",
    "Homenagem": "homenagem",
    "Convite": "convite",
}

RESULTADO_SITUACAO = {
    "Aprovado": "Proposição aprovada",
    "Rejeitado": "Proposição rejeitada pelo Plenário",
    "Em votação": "Proposição inclusa na Ordem do Dia",
    "Em discussão": "Proposição inclusa na Ordem do Dia",
    "Adiado votação": "Proposição inclusa na Ordem do Dia",
}

PARTICULAS = {"de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "no", "na", "nos", "nas"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def tokens(s):
    return {t for t in norm(s).split() if t and t not in PARTICULAS}


def similar(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0
    return len(ta & tb) / max(len(ta), len(tb))


def num(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def site_tipo(m):
    key = (m["tipo"], m.get("origem"))
    if key in TIPO_MAP:
        return TIPO_MAP[key]
    return TIPO_MAP.get((m["tipo"], None), (m["tipo"], m["tipo"], m["tipo"]))


def identificacao(m, prefix):
    return "%s-%03d/%s" % (prefix, num(m["numero"]) or 0, m["ano"])


def tabela_existe(conn, nome):
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone()
    return bool(row)


def coluna_existe(conn, tabela, coluna):
    return any(r[1] == coluna for r in conn.execute("PRAGMA table_info(%s)" % tabela))


def criar_estrutura(conn, cam):
    """Cria as tabelas/views do banco de sessões, copiando o DDL de origem."""
    for nome in CORE_TABLES:
        sql = cam.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (nome,)
        ).fetchone()
        if not sql:
            continue
        ddl = re.sub(r"^CREATE TABLE", "CREATE TABLE IF NOT EXISTS", sql[0], flags=re.I)
        conn.execute(ddl)
    for row in cam.execute("SELECT sql FROM sqlite_master WHERE type='view' ORDER BY name"):
        if row[0]:
            ddl = re.sub(r"^CREATE VIEW", "CREATE VIEW IF NOT EXISTS", row[0], flags=re.I)
            conn.execute(ddl)
    for row in cam.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"
    ):
        try:
            conn.execute(row[0].replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1))
        except sqlite3.OperationalError:
            pass


def copiar_dados(conn, cam):
    for nome in CORE_TABLES:
        if not tabela_existe(cam, nome):
            continue
        cols = [r[1] for r in cam.execute("PRAGMA table_info(%s)" % nome)]
        cols_sql = ", ".join(cols)
        conn.execute("INSERT OR REPLACE INTO main.%s (%s) SELECT %s FROM cam.%s" % (nome, cols_sql, cols_sql, nome))


def adicionar_colunas(conn):
    if not coluna_existe(conn, "proposicoes", "origem_registro"):
        conn.execute("ALTER TABLE proposicoes ADD COLUMN origem_registro TEXT DEFAULT 'site'")
    if not coluna_existe(conn, "autores", "origem_registro"):
        conn.execute("ALTER TABLE autores ADD COLUMN origem_registro TEXT DEFAULT 'site'")


def criar_mapeamentos(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS materia_proposicao (
               materia_id INTEGER PRIMARY KEY REFERENCES materia(id),
               proposicao_id INTEGER NOT NULL REFERENCES proposicoes(id),
               metodo TEXT,
               confianca TEXT,
               observacao TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS vereador_canonico (
               vereador_id INTEGER PRIMARY KEY REFERENCES vereador(id),
               canonico_id INTEGER NOT NULL REFERENCES vereador(id),
               motivo TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS vereador_autor (
               vereador_id INTEGER PRIMARY KEY REFERENCES vereador(id),
               autor_id INTEGER NOT NULL REFERENCES autores(id),
               metodo TEXT,
               confianca TEXT,
               observacao TEXT)"""
    )


def migrar(oficial_path, camara_path):
    if not os.path.exists(oficial_path):
        sys.exit("Banco oficial não encontrado: %s" % oficial_path)
    if not os.path.exists(camara_path):
        sys.exit("Banco de sessões não encontrado: %s" % camara_path)

    conn = sqlite3.connect(oficial_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    cam = sqlite3.connect(camara_path)
    cam.row_factory = sqlite3.Row
    conn.execute("ATTACH DATABASE ? AS cam", (camara_path,))

    criar_estrutura(conn, cam)
    copiar_dados(conn, cam)
    adicionar_colunas(conn)
    criar_mapeamentos(conn)

    # ------------------------------------------------------------------
    # Matérias ↔ proposições
    # ------------------------------------------------------------------
    props = [dict(r) for r in conn.execute("SELECT id, tipo, numero, ano, identificacao, situacao FROM proposicoes")]
    by_key = defaultdict(list)
    by_num = defaultdict(list)
    by_ident = {}
    for p in props:
        by_key[(p["tipo"], num(p["numero"]), num(p["ano"]))].append(p)
        by_num[(num(p["numero"]), num(p["ano"]))].append(p)
        if p["identificacao"]:
            by_ident[p["identificacao"]] = p

    materias = [dict(r) for r in conn.execute("SELECT * FROM materia ORDER BY id")]
    votos_por_materia = defaultdict(list)
    for v in conn.execute("SELECT * FROM votacao"):
        votos_por_materia[v["materia_id"]].append(dict(v))

    mapa = {}          # materia_id -> proposicao_id
    metodos = Counter()
    ambiguas = []
    inseridas = []
    invalidas = []

    conn.execute("DELETE FROM materia_proposicao")
    for m in materias:
        st, prefix, _ = site_tipo(m)
        key = (st, num(m["numero"]), num(m["ano"]))
        alvo = None
        metodo = ""
        confianca = "Alta"
        if len(by_key[key]) == 1:
            alvo = by_key[key][0]
            metodo = "tipo+número+ano"
        else:
            cand = by_num.get((num(m["numero"]), num(m["ano"])), [])
            if len(cand) == 1:
                alvo = cand[0]
                metodo = "número+ano"
                confianca = "Alta"
            else:
                same = [c for c in cand if c["tipo"] == st]
                if len(same) == 1:
                    alvo = same[0]
                    metodo = "número+ano (tipo reconciliado)"
                    confianca = "Média"
                elif len(same) > 1:
                    # mais de uma proposição do mesmo tipo: não escolhe no chute
                    ambiguas.append(m)
                    continue

        if alvo is None:
            # tenta pela identificação exata antes de criar uma nova
            ident = identificacao(m, prefix)
            alvo = by_ident.get(ident)
            if alvo:
                metodo = "identificação existente"
                confianca = "Média"

        if alvo is None:
            ano = num(m["ano"])
            if ano is None or not (2000 <= ano <= 2030):
                invalidas.append(m)
                continue
            # cria uma proposição a partir da matéria
            votos = votos_por_materia.get(m["id"], [])
            resultado = ""
            if votos:
                votos.sort(key=lambda x: (x.get("sessao_id") or 0, x.get("id") or 0))
                resultado = votos[-1].get("resultado") or ""
            situacao = RESULTADO_SITUACAO.get(resultado, "nao_informada")
            subtipo = SUBTIPO_MAP.get(m.get("subtipo") or "")
            if not subtipo:
                if st == "indicacao":
                    subtipo = "indicacao"
                elif st in ("projeto_lei_legislativo", "projeto_lei_ordinaria", "projeto_decreto_legislativo", "projeto_resolucao", "emenda_lei_organica"):
                    subtipo = "projeto_normativo"
                elif st == "requerimento":
                    subtipo = "procedimento"
                elif st == "mocao":
                    subtipo = "outro_ato"
                else:
                    subtipo = "outro_ato"
            cur = conn.execute(
                """INSERT INTO proposicoes
                   (tipo, identificacao, numero, ano, situacao, observacao, arquivo_pdf,
                    ementa, objeto, tema, local, subtipo, origem_registro)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    st,
                    ident,
                    "%03d" % (num(m["numero"]) or 0),
                    str(ano),
                    situacao,
                    "Importada dos relatórios de sessão; sem PDF no site.",
                    None,
                    (m.get("ementa") or "").strip(),
                    None,
                    None,
                    None,
                    subtipo,
                    "relatorio",
                ),
            )
            alvo = {"id": cur.lastrowid, "identificacao": ident, "situacao": situacao}
            metodo = "nova proposição (relatório)"
            confianca = "Alta"
            inseridas.append((m, cur.lastrowid))
            by_ident[ident] = alvo

        mapa[m["id"]] = alvo["id"]
        conn.execute(
            "INSERT OR REPLACE INTO materia_proposicao (materia_id, proposicao_id, metodo, confianca, observacao) VALUES (?,?,?,?,?)",
            (m["id"], alvo["id"], metodo, confianca, None),
        )
        metodos[metodo] += 1

        # enriquece a situação do site quando ela está vazia e há votação
        if alvo.get("situacao") in (None, "", "nao_informada"):
            votos = votos_por_materia.get(m["id"], [])
            if votos:
                votos.sort(key=lambda x: (x.get("sessao_id") or 0, x.get("id") or 0))
                resultado = votos[-1].get("resultado") or ""
                nova = RESULTADO_SITUACAO.get(resultado)
                if nova:
                    conn.execute("UPDATE proposicoes SET situacao=? WHERE id=?", (nova, alvo["id"]))

    # ------------------------------------------------------------------
    # Vereadores ↔ autores
    # ------------------------------------------------------------------
    vereadores = [dict(r) for r in conn.execute("SELECT id, nome FROM vereador ORDER BY id")]
    autor_por_id = {r["id"]: r["nome"] for r in conn.execute("SELECT id, nome FROM autores")}
    autor_por_norm = {norm(n): i for i, n in autor_por_id.items()}

    def canon(vid):
        visto = set()
        while vid in CANON and vid not in visto:
            visto.add(vid)
            vid = CANON[vid]
        return vid

    # coocorrência (vereador, autor) nas matérias ligadas
    co = Counter()
    materias_por_canon = Counter()
    for mid, pid in mapa.items():
        autores_site = [r["autor_id"] for r in conn.execute("SELECT autor_id FROM proposicao_autor WHERE proposicao_id=?", (pid,))]
        for r in conn.execute("SELECT vereador_id FROM materia_autor WHERE materia_id=? AND vereador_id IS NOT NULL", (mid,)):
            vid = r["vereador_id"]
            cid = canon(vid)
            materias_por_canon[cid] += 1
            for a in autores_site:
                co[(cid, a)] += 1

    # pistas explícitas de correspondência (site_slug -> vereador_id)
    pistas = defaultdict(set)  # canon -> {autor_id}
    # a tabela site_vereador_correspondencia não foi importada; lê da origem
    for r in cam.execute("SELECT * FROM site_vereador_correspondencia"):
        vid = r["vereador_id"]
        if not vid or r["confianca"] == "Sem correspondência":
            continue
        slug = r["slug"]
        # descobre o autor do site pelo slug do nome
        for aid, nome in autor_por_id.items():
            if re.sub(r"[^a-z0-9]+", "-", norm(nome)).strip("-") == slug:
                pistas[canon(vid)].add(aid)
                break

    conn.execute("DELETE FROM vereador_canonico")
    conn.execute("DELETE FROM vereador_autor")
    for v in vereadores:
        vid = v["id"]
        cid = canon(vid)
        motivo = "grafia curta/duplicada" if cid != vid else "registro canônico"
        conn.execute(
            "INSERT OR REPLACE INTO vereador_canonico (vereador_id, canonico_id, motivo) VALUES (?,?,?)",
            (vid, cid, motivo),
        )

    novos_autores = []
    sem_materia = []
    for cid in sorted({canon(v["id"]) for v in vereadores}):
        nome = next((v["nome"] for v in vereadores if v["id"] == cid), "")
        candidatos = [(a, c) for (v, a), c in co.items() if v == cid]
        candidatos.sort(key=lambda x: (-x[1], -similar(nome, autor_por_id.get(x[0], ""))))
        melhor = None
        metodo = ""
        confianca = ""
        if candidatos and candidatos[0][1] > 0:
            a, c = candidatos[0]
            total = materias_por_canon.get(cid, 0)
            if c >= 3 or (total and c / total >= 0.5):
                melhor = a
                metodo = "coautoria em matérias"
                confianca = "Alta" if (total and c / total >= 0.8) else "Média"
        if melhor is None and cid in pistas and len(pistas[cid]) == 1:
            melhor = next(iter(pistas[cid]))
            metodo = "correspondência sugerida pelo site"
            confianca = "Média"
        if melhor is None:
            # tenta nome exato ou muito parecido
            exato = autor_por_norm.get(norm(nome))
            if exato:
                melhor = exato
                metodo = "nome idêntico"
                confianca = "Alta"
            else:
                parecidos = sorted(
                    ((similar(nome, n), a) for a, n in autor_por_id.items()),
                    reverse=True,
                )
                if parecidos and parecidos[0][0] >= 0.75:
                    melhor = parecidos[0][1]
                    metodo = "nome semelhante"
                    confianca = "Baixa"
        if melhor is None:
            cur = conn.execute(
                "INSERT INTO autores (nome, origem_registro) VALUES (?, 'relatorio')",
                (nome,),
            )
            melhor = cur.lastrowid
            autor_por_id[melhor] = nome
            autor_por_norm[norm(nome)] = melhor
            metodo = "novo perfil (relatório)"
            confianca = "Alta"
            novos_autores.append((nome, melhor))
        for v in vereadores:
            if canon(v["id"]) == cid:
                conn.execute(
                    "INSERT OR REPLACE INTO vereador_autor (vereador_id, autor_id, metodo, confianca, observacao) VALUES (?,?,?,?,?)",
                    (v["id"], melhor, metodo, confianca, None),
                )
        if materias_por_canon.get(cid, 0) == 0:
            sem_materia.append(nome)

    # Autores das proposições criadas a partir dos relatórios
    executivo = conn.execute("SELECT id FROM autores WHERE nome='Executivo Municipal'").fetchone()
    executivo_id = executivo["id"] if executivo else None
    for m, pid in inseridas:
        for r in conn.execute(
            "SELECT autor_tipo, vereador_id FROM materia_autor WHERE materia_id=?", (m["id"],)
        ):
            aid = None
            if r["vereador_id"]:
                row = conn.execute(
                    "SELECT autor_id FROM vereador_autor WHERE vereador_id=?", (r["vereador_id"],)
                ).fetchone()
                aid = row["autor_id"] if row else None
            elif r["autor_tipo"] == "Executivo":
                aid = executivo_id
            if aid:
                conn.execute(
                    "INSERT OR IGNORE INTO proposicao_autor (proposicao_id, autor_id) VALUES (?,?)",
                    (pid, aid),
                )

    # ------------------------------------------------------------------
    # Observações da migração
    # ------------------------------------------------------------------
    conn.execute("DELETE FROM observacao WHERE descricao LIKE 'Migração:%'")

    def obs(categoria, descricao, status="Aberta"):
        conn.execute(
            "INSERT INTO observacao (categoria, descricao, status) VALUES (?,?,?)",
            (categoria, descricao, status),
        )

    obs(
        "Correção do relatório",
        "Migração: %d matérias casadas por tipo+número+ano, %d por número+ano, %d criadas como novas proposições e %d com ano inválido não inseridas."
        % (
            metodos.get("tipo+número+ano", 0),
            metodos.get("número+ano", 0) + metodos.get("número+ano (tipo reconciliado)", 0),
            len(inseridas),
            len(invalidas),
        ),
    )
    mapeadas_site = len(set(mapa.values()) & {p["id"] for p in props})
    obs(
        "Limitação",
        "Migração: %d proposições do site não aparecem nos relatórios de sessão e foram mantidas como estavam."
        % (len(props) - mapeadas_site),
    )
    obs(
        "Limitação",
        "Migração: as tabelas site_*, hubpolitico_* e instagram_perfil ficaram apenas no banco de origem; o banco oficial recebeu as tabelas de sessão e as correspondências."
    )
    for m in ambiguas:
        obs(
            "Pendência de revisão",
            "Migração: matéria %s %s/%s não foi ligada automaticamente porque há mais de uma proposição candidata."
            % (m["tipo"], m["numero"], m["ano"]),
        )
    for m in invalidas:
        obs(
            "Exceção",
            "Migração: matéria %s %s/%s tem ano inválido e não entrou em proposicoes."
            % (m["tipo"], m["numero"], m["ano"]),
        )
    for nome, aid in novos_autores:
        obs(
            "Pendência de revisão",
            "Migração: vereador %s não tinha autor correspondente no site; perfil novo criado (autor_id %d)." % (nome, aid),
        )
    for nome in sem_materia:
        obs(
            "Limitação",
            "Migração: vereador %s não tem matéria de autoria nos relatórios; presença e votos ficam disponíveis, mas sem matérias próprias." % nome,
        )

    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    integridade = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.commit()

    # ------------------------------------------------------------------
    # Resumo
    # ------------------------------------------------------------------
    resumo = {
        "materias": len(materias),
        "mapeadas": len(mapa),
        "inseridas": len(inseridas),
        "ambiguas": len(ambiguas),
        "invalidas": len(invalidas),
        "metodos": dict(metodos),
        "vereadores": len(vereadores),
        "autores_site_antes": len(autor_por_id) - len(novos_autores),
        "novos_autores": len(novos_autores),
        "integridade": integridade,
        "proposicoes_total": conn.execute("SELECT COUNT(*) FROM proposicoes").fetchone()[0],
        "autores_total": conn.execute("SELECT COUNT(*) FROM autores").fetchone()[0],
        "sessoes": conn.execute("SELECT COUNT(*) FROM sessao").fetchone()[0],
        "votos": conn.execute("SELECT COUNT(*) FROM voto").fetchone()[0],
    }
    conn.close()
    return resumo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oficial", required=True)
    ap.add_argument("--camara", required=True)
    args = ap.parse_args()
    resumo = migrar(args.oficial, args.camara)
    import json

    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
