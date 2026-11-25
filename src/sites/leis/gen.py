import sqlite3, json, os, re, shutil, unicodedata, html

BASE = os.environ.get("LEIS_BASE", "/opt/servidor/src/sites/leis")
DB = os.environ.get("LEIS_DB", "/opt/servidor/data/servicos/leis/legislacao_pinheiro.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()


def q(sql, *a):
    return c.execute(sql, a).fetchall()


def md_text(s):
    return (s or "").strip()


def clean_ws(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def yaml_escape(s):
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def slugify(s):
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "autor"


PARTICULAS = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "no",
    "na", "nos", "nas", "ao", "aos", "à", "às", "pela", "pelo", "pelas",
    "pelos", "deste", "desta", "neste", "nesta",
}


def display_nome(s):
    """Nome oficial do TSE (caixa alta) em caixa normal, para leitura."""
    s = clean_ws(s)
    if not s:
        return ""
    if s != s.upper():
        return s
    out, i = [], 0
    for w in s.split(" "):
        core = re.sub(r"^[^\wÀ-ÿ]+|[^\wÀ-ÿ]+$", "", w)
        if not core:
            out.append(w)
            continue
        low = core.lower()
        if i and low in PARTICULAS:
            out.append(w.replace(core, low))
        elif len(core) <= 3 and core.isupper() and core not in ("DOS", "DAS"):
            out.append(w.replace(core, core))
        else:
            out.append(w.replace(core, low[:1].upper() + low[1:]))
        i += 1
    return " ".join(out)


def clamp_texto(s, limite):
    """Corta em limite de palavra, sem quebrar a frase no meio."""
    s = clean_ws(s)
    if len(s) <= limite:
        return s
    corte = s[:limite]
    pos = corte.rfind(" ")
    if pos > limite * 0.6:
        corte = corte[:pos]
    return corte.rstrip(" ,;:.") + "…"


MAPA_PROP_ESPECIE = {
    "Indicação": "indicacao",
    "Moção": "mocao",
    "Requerimento": "requerimento",
    "Projeto de Lei Ordinária": "projeto_lei",
    "Projeto de Lei do Legislativo": "projeto_lei",
    "Projeto de Resolução": "resolucao",
    "Projeto de Decreto Legislativo": "decreto_legislativo",
    "Projeto de Emenda à Lei Orgânica": "emenda_lo",
    "Emenda ao Projeto de Lei do Legislativo": "emenda",
    "Emenda ao Projeto de Lei Ordinária": "emenda",
    "Prestação de Contas do Executivo": "prestacao_contas",
}

PROP_SITUACAO_LABEL = {
    "nao_informada": "Não informada",
    "Proposição aprovada": "Aprovada",
    "Proposição inclusa na Ordem do Dia": "Na Ordem do Dia",
    "Proposição retirada da Ordem do Dia": "Retirada da Ordem do Dia",
    "Proposição rejeitada pelo Plenário": "Rejeitada",
}

PROP_SITUACAO_CLASSE = {
    "Proposição aprovada": "ok",
    "Proposição rejeitada pelo Plenário": "no",
    "Proposição inclusa na Ordem do Dia": "wait",
    "Proposição retirada da Ordem do Dia": "off",
    "nao_informada": "off",
}


def categoria_autoria(n):
    if n <= 1:
        return "exclusiva"
    if n == 2:
        return "dupla"
    if n == 3:
        return "trio"
    if n < 10:
        return "coletiva"
    return "ampla"


def autoria_label(n):
    if n <= 1:
        return "Autoria exclusiva"
    if n < 10:
        return "%d autores" % n
    return "Autoria coletiva (%d)" % n


temas = {r["id"]: dict(r) for r in q("SELECT * FROM temas")}
categorias = {r["id"]: dict(r) for r in q("SELECT * FROM categorias")}
naturezas = {r["id"]: dict(r) for r in q("SELECT * FROM naturezas")}

especies = []
try:
    especies = [dict(r) for r in q("SELECT * FROM especies ORDER BY ordem")]
except sqlite3.OperationalError:
    pass
especies_por_chave = {e["chave"]: e for e in especies}

qualidade_por_prop = {}
try:
    for r in q("SELECT * FROM proposicao_qualidade"):
        try:
            problemas = json.loads(r["problemas"] or "[]")
        except ValueError:
            problemas = []
        qualidade_por_prop[r["proposicao_id"]] = {
            "pontuacao": r["pontuacao"],
            "nivel": r["nivel"],
            "problemas": problemas,
        }
except sqlite3.OperationalError:
    pass

classe_por_prop = {}
try:
    for r in q("SELECT * FROM proposicao_classe"):
        classe_por_prop[r["proposicao_id"]] = {
            "classe": r["classe"],
            "rotulo": r["rotulo"],
            "evidencia": r["evidencia"],
        }
except sqlite3.OperationalError:
    pass

tema_por_prop = {}
try:
    for r in q("SELECT * FROM proposicao_tema"):
        tema_por_prop[r["proposicao_id"]] = dict(r)
except sqlite3.OperationalError:
    pass

# Texto integral e PDF das indicações (chave: numero, ano)
indicacao_extra = {}
for r in q(
    "SELECT id, numero, data, texto_integral, arquivo_pdf FROM normas "
    "WHERE tipo='indicacao'"
):
    m = re.match(r"^IND(\d+)_(\d{4})$", r["id"])
    if m:
        chave = (int(m.group(1)), int(m.group(2)))
    elif r["id"] == "IND507":
        chave = (507, 2026)
    else:
        chave = None
    if chave:
        indicacao_extra[chave] = dict(r)

CLASSE_CURTA = {
    "proposta": "Proposta",
    "denominacao": "Nomeação",
    "homenagem": "Homenagem",
    "manifestacao": "Moção",
    "indefinida": "Não classificável",
}

impacto_por_autor = {}
try:
    for r in q("SELECT * FROM autor_impacto"):
        d = dict(r)
        for campo in ("familias", "tipos", "coautores", "anos"):
            try:
                d[campo] = json.loads(d.get(campo) or "{}")
            except ValueError:
                d[campo] = {}
        impacto_por_autor[r["autor_id"]] = d
except sqlite3.OperationalError:
    pass

destaques_por_autor = {}
try:
    for r in q("SELECT * FROM autor_destaque ORDER BY autor_id, ordem"):
        destaques_por_autor.setdefault(r["autor_id"], []).append(r["texto"])
except sqlite3.OperationalError:
    pass

situacao_label_map = {
    "vigente": "Em vigor",
    "projeto_em_tramitacao": "Projeto em tramitação",
    "prazo_expirado": "Prazo expirado",
    "apresentada": "Apresentada",
    "apresentado": "Apresentado",
    "a_verificar": "A verificar",
}

tipo_label = {
    "lei_organica": "Lei Orgânica",
    "codigo_posturas": "Código de Posturas",
    "projeto_lei": "Projeto de Lei",
    "indicacao": "Indicação",
    "requerimento": "Requerimento",
    "decreto_legislativo": "Decreto Legislativo",
    "resolucao": "Resolução",
    "mocao": "Moção",
    "portaria": "Portaria",
    "lei_ordinaria": "Lei Ordinária",
    "regimento_interno": "Regimento Interno",
}

relacao_label = {
    "altera": "Altera",
    "revoga": "Revoga",
    "fundamenta": "Fundamenta-se em",
    "alterada_por": "Alterada por",
    "suspende": "Suspende",
    "depende_de": "Depende de",
}


def norma_categorias(nid):
    ids = [r["categoria_id"] for r in q("SELECT categoria_id FROM norma_categoria WHERE norma_id=?", nid)]
    return [categorias[i]["nome"] for i in ids if i in categorias]


def norma_natureza(nid):
    rows = q("SELECT natureza_id FROM norma_natureza WHERE norma_id=?", nid)
    if not rows:
        return None, None
    nzid = rows[0]["natureza_id"]
    nz = naturezas.get(nzid, {})
    return nzid, nz.get("nome")


def norma_fonte(nid):
    rows = q("SELECT * FROM fontes WHERE id=(SELECT fonte_id FROM normas WHERE id=?)", nid)
    return dict(rows[0]) if rows else None


def dispositivos(nid):
    return q("SELECT * FROM dispositivos WHERE norma_id=? ORDER BY ordem, id", nid)


def partes_do_disp(did):
    return q("SELECT * FROM dispositivo_partes WHERE dispositivo_id=? ORDER BY ordem, id", did)


def temas_do_disp(did):
    ids = [r["tema_id"] for r in q("SELECT tema_id FROM dispositivo_tema WHERE dispositivo_id=?", did)]
    return [temas[i]["nome"] for i in ids if i in temas]


def relacoes_da_norma(nid):
    out = []
    for r in q("SELECT * FROM relacoes WHERE origem=?", nid):
        dest = r["destino"]
        dest_norma = None
        if r["destino_no_banco"]:
            dest_norma = next((x for x in normas_by_id.values() if x["id"] == dest), None)
        out.append({
            "sentido": "sai",
            "tipo": r["tipo"],
            "tipo_label": relacao_label.get(r["tipo"], r["tipo"]),
            "destino": dest,
            "destino_norma": dest_norma,
            "observacao": md_text(r["observacao"]),
        })
    for r in q("SELECT * FROM relacoes WHERE destino=? AND destino_no_banco=1", nid):
        origem_norma = normas_by_id.get(r["origem"])
        out.append({
            "sentido": "entra",
            "tipo": r["tipo"],
            "tipo_label": relacao_label.get(r["tipo"], r["tipo"]),
            "destino": r["origem"],
            "destino_norma": origem_norma,
            "observacao": md_text(r["observacao"]),
        })
    return out


def alteracoes_da_norma(nid):
    return [dict(r) for r in q("SELECT * FROM alteracoes WHERE norma_id=? ORDER BY rotulo, paragrafo", nid)]


def eventos_da_norma(nid):
    return [dict(r) for r in q("SELECT * FROM projeto_eventos WHERE norma_id=? ORDER BY data", nid)]


# Autores + TSE (2024 e legislatura 2021–2024)
try:
    autores_rows = q("""
        SELECT a.id, a.nome,
               t.nome_tse, t.nome_urna, t.partido, t.cargo, t.votos,
               t.situacao_tse, t.eleito, t.ano AS ano_tse, t.fonte_url
        FROM autores a
        LEFT JOIN autor_tse t ON t.autor_id = a.id
        ORDER BY a.nome
    """)
except sqlite3.OperationalError:
    autores_rows = q("SELECT id, nome, NULL AS nome_tse, NULL AS nome_urna, NULL AS partido, NULL AS cargo, NULL AS votos, NULL AS situacao_tse, NULL AS eleito, NULL AS ano_tse, NULL AS fonte_url FROM autores ORDER BY nome")

mandatos_por_autor = {}
try:
    for r in q("SELECT * FROM autor_mandato ORDER BY ano_eleicao, autor_id"):
        m = dict(r)
        mandatos_por_autor.setdefault(m["autor_id"], []).append(m)
except sqlite3.OperationalError:
    pass

TSE_LABEL = {
    "ELEITO POR QP": "Eleito por quociente partidário",
    "ELEITO POR MÉDIA": "Eleito por média",
    "SUPLENTE": "Suplente",
    "#NULO": "",
}

# Explicações curtas para termos do TSE que não são óbvios.
TSE_AJUDA = {
    "ELEITO POR QP": (
        "O partido conquistou a vaga pelo quociente partidário: divide-se o total "
        "de votos válidos pelo quociente eleitoral para saber quantas cadeiras cada "
        "partido ou federação preenche. A vaga fica com os mais votados da lista."
    ),
    "ELEITO POR MÉDIA": (
        "A vaga veio na distribuição das sobras, pela média: divide-se a votação do "
        "partido pelo número de cadeiras que ele já obteve mais um. Quem tiver a "
        "maior média fica com a vaga."
    ),
    "SUPLENTE": (
        "Não assumiu a cadeira na eleição, mas ficou na suplência da coligação ou "
        "do partido e pode ser convocado."
    ),
}


def norm_nome(s):
    """Compara nomes sem depender de caixa, acento ou espaços."""
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def label_tse(s):
    s = clean_ws(s)
    if not s:
        return ""
    return TSE_LABEL.get(s.upper(), s.title())


autores = []
autor_por_id = {}
for r in autores_rows:
    a = dict(r)
    a["slug"] = slugify(a["nome"])
    a["n_proposicoes"] = 0
    a["stats"] = {}
    a["situacao_tse_label"] = label_tse(a.get("situacao_tse"))
    a["situacao_tse_ajuda"] = TSE_AJUDA.get((a.get("situacao_tse") or "").upper(), "")
    a["nome_urna_display"] = display_nome(a.get("nome_urna"))
    a["nome_urna_igual"] = bool(
        a.get("nome_urna") and norm_nome(a["nome_urna"]) == norm_nome(a.get("nome"))
    )
    imp = impacto_por_autor.get(a["id"])
    a["impacto"] = imp or {
        "n_total": 0, "n_exclusiva": 0, "n_dupla": 0, "n_trio": 0,
        "n_coletiva": 0, "n_ampla": 0, "autoria_equivalente": 0,
        "taxa_exclusividade": 0, "peso_medio": 0, "familias": {},
        "tipos": {}, "coautores": [], "anos": {},
    }
    a["destaques"] = destaques_por_autor.get(a["id"], [])
    ms = sorted(mandatos_por_autor.get(a["id"], []), key=lambda x: x["ano_eleicao"])
    for m in ms:
        m["nome_tse_display"] = display_nome(m.get("nome_tse"))
        m["nome_tse_igual"] = bool(
            m.get("nome_tse") and norm_nome(m["nome_tse"]) == norm_nome(a.get("nome"))
        )
        m["situacao_label"] = label_tse(m.get("situacao_tse"))
        m["situacao_ajuda"] = TSE_AJUDA.get((m.get("situacao_tse") or "").upper(), "")
    a["mandatos"] = ms
    eleitos = [m for m in ms if m.get("eleito")]
    a["legislaturas"] = []
    for m in eleitos:
        if m["legislatura"] not in a["legislaturas"]:
            a["legislaturas"].append(m["legislatura"])
    a["atual"] = any(m["ano_eleicao"] == 2024 and m.get("eleito") for m in ms)
    a["anterior"] = any(m["ano_eleicao"] == 2020 and m.get("eleito") for m in ms)
    if ms and not a.get("partido"):
        latest = ms[-1]
        for campo in ("nome_tse", "nome_urna", "partido", "cargo", "votos", "situacao_tse", "eleito", "fonte_url"):
            a[campo] = latest.get(campo)
        a["ano_tse"] = latest.get("ano_eleicao")
    com_foto = [m for m in ms if m.get("foto")]
    a["foto"] = com_foto[-1]["foto"] if com_foto else ""
    a["foto_ano"] = com_foto[-1]["ano_eleicao"] if com_foto else None
    a["nome_tse_display"] = display_nome(a.get("nome_tse"))
    a["og_image"] = "/og/v/%s.jpg" % a["slug"]
    autores.append(a)
    autor_por_id[a["id"]] = a

for a in autores:
    a["impacto_equivalente_label"] = ("%.1f" % a["impacto"].get("autoria_equivalente", 0)).replace(".", ",")
    a["parceiros"] = [
        {"nome": x["nome"], "slug": slugify(x["nome"]), "n": x["n"]}
        for x in a["impacto"].get("coautores", [])
    ]
    a["n_coletivas"] = a["impacto"].get("n_coletiva", 0) + a["impacto"].get("n_ampla", 0)

# Proposições
props_rows = q("""
    SELECT p.*, GROUP_CONCAT(a.nome, '||') AS autores_nomes
    FROM proposicoes p
    LEFT JOIN proposicao_autor pa ON pa.proposicao_id = p.id
    LEFT JOIN autores a ON a.id = pa.autor_id
    GROUP BY p.id
    ORDER BY p.ano DESC, p.id DESC
""")
props = []
props_por_autor = {}
for r in props_rows:
    p = dict(r)
    nomes = [x for x in (p.pop("autores_nomes") or "").split("||") if x]
    autores_prop = [a for a in autores if a["nome"] in nomes]
    p["autores"] = [{"id": a["id"], "nome": a["nome"], "slug": a["slug"], "partido": a.get("partido")} for a in autores_prop]
    p["autores_nomes"] = nomes
    p["autor_ids"] = [a["id"] for a in autores_prop]
    p["n_autores"] = len(autores_prop)
    p["autoria_categoria"] = categoria_autoria(len(autores_prop))
    p["autoria_label"] = autoria_label(len(autores_prop))
    p["coletiva"] = len(autores_prop) >= 10
    p["ementa_limpa"] = clean_ws(p.get("ementa_limpa") or p["ementa"])
    p["ementa_curta"] = clamp_texto(p["ementa_limpa"], 160)
    p["ementa_card"] = clamp_texto(p["ementa_limpa"], 110)
    p["ementa_truncada"] = (p["ementa"] or "").rstrip().endswith(("...", "…"))
    p["situacao_label"] = PROP_SITUACAO_LABEL.get(
        p["situacao"] or "", p["situacao"] or ""
    )
    p["situacao_classe"] = PROP_SITUACAO_CLASSE.get(p["situacao"] or "", "off")
    p["ano_label"] = p["ano"] or "—"
    esp = MAPA_PROP_ESPECIE.get(p["tipo"] or "")
    p["especie"] = esp or ""
    p["especie_rotulo"] = (especies_por_chave.get(esp) or {}).get("rotulo", p["tipo"] or "")
    p["familia"] = (especies_por_chave.get(esp) or {}).get("familia", "")
    p["familia_label"] = (especies_por_chave.get(esp) or {}).get("familia_label", "")
    cls = classe_por_prop.get(p["id"]) or {
        "classe": "indefinida",
        "rotulo": "Não classificável",
        "evidencia": "sem classificação",
    }
    p["classe"] = cls["classe"]
    p["classe_rotulo"] = cls["rotulo"]
    p["classe_curta"] = CLASSE_CURTA.get(cls["classe"], cls["rotulo"])
    p["classe_evidencia"] = cls["evidencia"]
    tema = tema_por_prop.get(p["id"])
    p["tema"] = tema["tema"] if tema else ""
    p["tema_rotulo"] = tema["rotulo"] if tema else ""
    p["tema_evidencia"] = tema["evidencia"] if tema else ""
    p["slug"] = re.sub(r"[^a-z0-9]+", "-", (p["identificacao"] or "").lower()).strip("-") or ("prop-%s" % p["id"])
    p["texto_integral"] = ""
    p["pdf_arquivo"] = ""
    p["data_prop"] = ""
    if (p["tipo"] or "").lower().startswith("indica"):
        try:
            extra = indicacao_extra.get((int(p["numero"]), int(str(p["ano"]).strip())))
        except (TypeError, ValueError):
            extra = None
        if extra:
            p["texto_integral"] = extra["texto_integral"] or ""
            p["pdf_arquivo"] = extra["arquivo_pdf"] or ""
            p["data_prop"] = extra["data"] or ""
    p["pdf_url"] = "/pdfs/%s" % p["pdf_arquivo"] if p["pdf_arquivo"] else ""
    p["tem_texto"] = len(p["texto_integral"]) > 100
    p["qualidade"] = qualidade_por_prop.get(p["id"]) or {
        "pontuacao": None,
        "nivel": "",
        "problemas": [],
    }
    props.append(p)
    for a in autores_prop:
        a["n_proposicoes"] += 1
        props_por_autor.setdefault(a["id"], []).append(p)


def stats_de_proposicoes(ps):
    by_year, by_tipo, by_situacao, by_familia = {}, {}, {}, {}
    by_classe = {}
    aprovadas = rejeitadas = 0
    for p in ps:
        ano = str(p.get("ano") or "")
        if re.fullmatch(r"\d{4}", ano) and 2000 <= int(ano) <= 2030:
            by_year[ano] = by_year.get(ano, 0) + 1
        by_tipo[p.get("tipo") or "Não informado"] = by_tipo.get(p.get("tipo") or "Não informado", 0) + 1
        fam = p.get("familia_label") or "Não informado"
        by_familia[fam] = by_familia.get(fam, 0) + 1
        cls = p.get("classe_rotulo") or "Não classificável"
        by_classe[cls] = by_classe.get(cls, 0) + 1
        sit = p.get("situacao") or "nao_informada"
        by_situacao[sit] = by_situacao.get(sit, 0) + 1
        if "aprovada" in sit.lower():
            aprovadas += 1
        if "rejeitada" in sit.lower():
            rejeitadas += 1
    total = len(ps)
    com_situacao = total - by_situacao.get("nao_informada", 0)
    return {
        "total": total,
        "aprovadas": aprovadas,
        "rejeitadas": rejeitadas,
        "com_situacao": com_situacao,
        "taxa_aprovacao": round(100 * aprovadas / com_situacao) if com_situacao else 0,
        "by_year": dict(sorted(by_year.items())),
        "by_tipo": dict(sorted(by_tipo.items(), key=lambda x: -x[1])),
        "by_familia": dict(sorted(by_familia.items(), key=lambda x: -x[1])),
        "by_situacao": dict(sorted(by_situacao.items(), key=lambda x: -x[1])),
        "by_classe": dict(sorted(by_classe.items(), key=lambda x: -x[1])),
        "n_proposta": by_classe.get("Proposta com objeto", 0),
        "n_nomeacao": by_classe.get("Nomeação de lugar", 0),
        "n_homenagem": by_classe.get("Homenagem ou título", 0),
        "n_indefinida": by_classe.get("Não classificável", 0),
    }

for a in autores:
    a["stats"] = stats_de_proposicoes(props_por_autor.get(a["id"], []))


RE_TITULO_LINHA = re.compile(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 ,.\-ºª]{3,42}$")


def paragrafos(texto):
    blocos = [b.strip() for b in re.split(r"\n\s*\n", texto or "") if b.strip()]
    saida = []
    for b in blocos:
        linhas = [l.strip() for l in b.split("\n") if l.strip()]
        atual = []
        for l in linhas:
            if RE_TITULO_LINHA.match(l) and not l.endswith("."):
                if atual:
                    saida.append(" ".join(atual))
                    atual = []
                saida.append(l)
            else:
                atual.append(l)
        if atual:
            saida.append(" ".join(atual))
    return [html.escape(x) for x in saida if x.strip()]


# Páginas individuais das proposições
props_dir = os.path.join(BASE, "content", "proposicoes")
os.makedirs(props_dir, exist_ok=True)
slug_usado = {}
for p in props:
    slug = p["slug"]
    if slug in slug_usado:
        slug_usado[slug] += 1
        slug = "%s-%d" % (slug, slug_usado[slug])
    else:
        slug_usado[slug] = 1
    p["slug"] = slug

for p in props:
    lines = ["---"]
    lines.append('title: "%s"' % yaml_escape(p["identificacao"]))
    lines.append('proposicao_id: %d' % p["id"])
    lines.append('tipo: "%s"' % yaml_escape(p["tipo"] or ""))
    lines.append('tipo_label: "%s"' % yaml_escape(p["especie_rotulo"]))
    lines.append('numero: "%s"' % yaml_escape(str(p["numero"] or "")))
    lines.append('ano: "%s"' % yaml_escape(str(p["ano_label"])))
    lines.append('data: "%s"' % yaml_escape(p["data_prop"]))
    lines.append('situacao: "%s"' % yaml_escape(p["situacao"] or ""))
    lines.append('situacao_label: "%s"' % yaml_escape(p["situacao_label"]))
    lines.append('classe: "%s"' % yaml_escape(p["classe"]))
    lines.append('classe_rotulo: "%s"' % yaml_escape(p["classe_rotulo"]))
    lines.append('classe_evidencia: "%s"' % yaml_escape(p["classe_evidencia"] or ""))
    if p["tema"]:
        lines.append('tema: "%s"' % yaml_escape(p["tema"]))
        lines.append('tema_rotulo: "%s"' % yaml_escape(p["tema_rotulo"]))
        lines.append('tema_evidencia: "%s"' % yaml_escape(p["tema_evidencia"] or ""))
    if p["pdf_url"]:
        lines.append('pdf_url: "%s"' % yaml_escape(p["pdf_url"]))
        lines.append('pdf_arquivo: "%s"' % yaml_escape(p["pdf_arquivo"]))
    lines.append('tem_texto: %s' % ("true" if p["tem_texto"] else "false"))
    lines.append('ementa: "%s"' % yaml_escape(p["ementa_limpa"]))
    if p["autores"]:
        lines.append("autores:")
        for a in p["autores"]:
            lines.append('  - {nome: "%s", slug: "%s"}' % (yaml_escape(a["nome"]), a["slug"]))
    lines.append("---")
    lines.append("")
    paras = paragrafos(p["texto_integral"])
    if paras:
        lines.append('<div class="texto-integral">')
        for par in paras:
            lines.append("<p>%s</p>" % par)
        lines.append("</div>")
    with open(os.path.join(props_dir, p["slug"] + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

normas_list = []
dispositivos_list = []
busca_list = []
normas_by_id = {}

normas_rows = q("SELECT * FROM normas ORDER BY data DESC, id")
for n in normas_rows:
    nid = n["id"]
    s = nid.lower()
    cats = norma_categorias(nid)
    sit = n["situacao"]
    sit_label = situacao_label_map.get(sit, sit)
    if sit_label == "nao_informada":
        sit_label = "Não informada"
    ementa = md_text(n["ementa"])
    obs = md_text(n["observacao"])
    tipo = n["tipo"]
    tipo_lbl = tipo_label.get(tipo, tipo)
    nzid, nznome = norma_natureza(nid)
    fonte = norma_fonte(nid)
    dsps = dispositivos(nid)
    normas_by_id[nid] = {
        "id": nid,
        "slug": s,
        "numero": n["numero"],
        "titulo": ementa or nid,
        "tipo_label": tipo_lbl,
    }
    esp = tipo if tipo in especies_por_chave else ""
    normas_list.append({
        "id": nid,
        "slug": s,
        "tipo": tipo,
        "tipo_label": tipo_lbl,
        "especie": esp,
        "especie_rotulo": (especies_por_chave.get(esp) or {}).get("rotulo", tipo_lbl),
        "familia": (especies_por_chave.get(esp) or {}).get("familia", ""),
        "familia_label": (especies_por_chave.get(esp) or {}).get("familia_label", ""),
        "numero": n["numero"],
        "data": n["data"],
        "data_label": n["data"] if len(n["data"] or "") == 10 else (n["data"] or "Sem data"),
        "situacao": sit,
        "situacao_label": sit_label,
        "ementa": ementa,
        "ementa_curta": clamp_texto(ementa, 170),
        "observacao": obs,
        "categorias": cats,
        "natureza": nznome or "",
        "n_dispositivos": len(dsps),
        "fonte_arquivo": (fonte or {}).get("arquivo", ""),
        "teor_status": n["teor_status"] or "",
        "og_image": "/og/tipos/%s.jpg" % esp if esp else "/og/site.jpg",
    })

content_dir = os.path.join(BASE, "content", "normas")
os.makedirs(content_dir, exist_ok=True)
for f in os.listdir(content_dir):
    if f.endswith(".md") and f != "_index.md":
        os.remove(os.path.join(content_dir, f))

for n in normas_rows:
    nid = n["id"]
    s = nid.lower()
    cats = norma_categorias(nid)
    sit = n["situacao"]
    sit_label = situacao_label_map.get(sit, sit)
    if sit_label == "nao_informada":
        sit_label = "Não informada"
    ementa = md_text(n["ementa"])
    obs = md_text(n["observacao"])
    tipo = n["tipo"]
    tipo_lbl = tipo_label.get(tipo, tipo)
    esp = tipo if tipo in especies_por_chave else ""
    nzid, nznome = norma_natureza(nid)
    fonte = norma_fonte(nid)
    dsps = dispositivos(nid)
    rels = relacoes_da_norma(nid)
    alts = alteracoes_da_norma(nid)
    evs = eventos_da_norma(nid)

    if tipo == "indicacao" and n["numero"]:
        titulo_pagina = "%s nº %s%s" % (
            tipo_lbl, n["numero"],
            (" de " + n["data"][:4]) if n["data"] else "",
        )
    else:
        titulo_pagina = ementa if ementa else nid

    lines = ["---"]
    lines.append('title: "%s"' % yaml_escape(titulo_pagina))
    lines.append('norma_id: "%s"' % nid)
    lines.append('tipo: "%s"' % tipo)
    lines.append('tipo_label: "%s"' % tipo_lbl)
    lines.append('numero: "%s"' % yaml_escape(n["numero"]))
    lines.append('data: "%s"' % n["data"])
    lines.append('ano: "%s"' % (n["data"][:4] if n["data"] else ""))
    arquivo_pdf = n["arquivo_pdf"] if "arquivo_pdf" in n.keys() else None
    if arquivo_pdf:
        lines.append('pdf_url: "/pdfs/%s"' % yaml_escape(arquivo_pdf))
    lines.append('especie: "%s"' % esp)
    lines.append('og_image: "%s"' % ("/og/tipos/%s.jpg" % esp if esp else "/og/site.jpg"))
    lines.append('situacao: "%s"' % sit)
    lines.append('situacao_label: "%s"' % yaml_escape(sit_label))
    lines.append('ementa: "%s"' % yaml_escape(ementa))
    if obs:
        lines.append('observacao: "%s"' % yaml_escape(obs))
    lines.append("categorias: [%s]" % ", ".join('"%s"' % yaml_escape(x) for x in cats))
    if nznome:
        lines.append('natureza: "%s"' % yaml_escape(nznome))
    if fonte:
        lines.append('fonte_arquivo: "%s"' % yaml_escape(fonte.get("arquivo") or ""))
        lines.append('fonte_paginas: %s' % (fonte.get("paginas") or 0))
    lines.append('teor_status: "%s"' % yaml_escape(n["teor_status"] or ""))
    if n["teor_obs"]:
        lines.append('teor_obs: "%s"' % yaml_escape(n["teor_obs"]))
    lines.append("---")
    lines.append("")
    lines.append("**%s**" % (ementa if ementa else nid))
    lines.append("")
    meta = []
    meta.append("**Tipo:** %s" % tipo_lbl)
    meta.append("**Número:** %s" % n["numero"])
    meta.append("**Data:** %s" % n["data"])
    meta.append("**Situação:** %s" % sit_label)
    if cats:
        meta.append("**Categorias:** %s" % ", ".join(cats))
    if nznome:
        meta.append("**Natureza:** %s" % nznome)
    if fonte and fonte.get("arquivo"):
        meta.append("**Fonte:** %s" % fonte["arquivo"])
    lines.append(" · ".join(meta))
    lines.append("")
    if arquivo_pdf:
        lines.append("**Documento original:** [ver PDF da indicação](/pdfs/%s)" % arquivo_pdf)
        lines.append("")
    if obs:
        lines.append("> %s" % obs)
        lines.append("")

    if rels:
        lines.append("## Relações com outras normas")
        lines.append("")
        for r in rels:
            if r["destino_norma"]:
                alvo = "[%s — %s](/normas/%s/)" % (
                    r["destino_norma"]["numero"],
                    r["destino_norma"]["tipo_label"],
                    r["destino_norma"]["slug"],
                )
            else:
                alvo = r["destino"]
            txt = "- **%s** %s" % (r["tipo_label"], alvo)
            if r["observacao"]:
                txt += " — %s" % r["observacao"]
            lines.append(txt)
        lines.append("")

    if alts:
        lines.append("## Alterações registradas")
        lines.append("")
        for a in alts:
            partes = []
            if a.get("rotulo"):
                partes.append(a["rotulo"])
            if a.get("paragrafo"):
                partes.append(a["paragrafo"])
            if a.get("emenda"):
                partes.append("Emenda %s" % a["emenda"])
            if a.get("data_texto"):
                partes.append(a["data_texto"])
            if a.get("trecho"):
                partes.append("“%s”" % clean_ws(a["trecho"]))
            lines.append("- " + " · ".join(partes))
        lines.append("")

    if evs:
        lines.append("## Tramitação")
        lines.append("")
        for e in evs:
            txt = "- **%s** — %s" % (e.get("data") or "", e.get("evento") or "")
            if e.get("observacao"):
                txt += " (%s)" % e["observacao"]
            lines.append(txt)
        lines.append("")

    lines.append("## Dispositivos")
    lines.append("")
    if not dsps:
        if n["texto_integral"] and md_text(n["texto_integral"]):
            lines.append("### Texto integral")
            lines.append("")
            lines.append(md_text(n["texto_integral"]))
            lines.append("")
        else:
            lines.append("_Texto ainda não extraído. A norma está cadastrada apenas com os metadados._")
            lines.append("")

    for d in dsps:
        did = d["id"]
        rotulo = md_text(d["rotulo"])
        cap = md_text(d["capitulo"])
        tit = md_text(d["titulo"])
        texto = md_text(d["texto"])
        status = md_text(d["status"])
        temas_list = temas_do_disp(did)

        heading = rotulo if rotulo else (tit if tit else cap)
        if not heading:
            heading = "Art. %d" % d["ordem"]
        lines.append('<a id="disp-%d"></a>' % did)
        lines.append("### " + heading)
        lines.append("")
        if status:
            lines.append("*Status: %s*" % status)
            lines.append("")
        parts = partes_do_disp(did)
        if parts:
            for p in parts:
                ident = md_text(p["identificador"])
                ptexto = md_text(p["texto"])
                if ident:
                    lines.append("**%s.** %s" % (ident, ptexto))
                else:
                    lines.append(ptexto)
                lines.append("")
                busca_list.append({
                    "norma_id": nid,
                    "norma_slug": s,
                    "norma_numero": n["numero"],
                    "dispositivo_id": did,
                    "rotulo": rotulo,
                    "anchor": "disp-%d" % did,
                    "tipo_parte": p["tipo"],
                    "identificador": ident,
                    "texto": ptexto,
                })
        elif texto:
            lines.append(texto)
            lines.append("")
            busca_list.append({
                "norma_id": nid,
                "norma_slug": s,
                "norma_numero": n["numero"],
                "dispositivo_id": did,
                "rotulo": rotulo,
                "anchor": "disp-%d" % did,
                "tipo_parte": "caput",
                "identificador": "",
                "texto": texto,
            })
        if temas_list:
            lines.append("*Temas:* " + ", ".join(temas_list))
            lines.append("")
        lines.append("")

        dispositivos_list.append({
            "id": did,
            "norma_id": nid,
            "norma_slug": s,
            "norma_numero": n["numero"],
            "rotulo": rotulo,
            "heading": heading,
            "anchor": "disp-%d" % did,
            "status": status,
        })

    out_path = os.path.join(content_dir, s + ".md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# Glossário
glossario_rows = q("SELECT verbo, definicao, exemplo FROM glossario ORDER BY verbo")
gl = ["---", 'title: "Glossário de termos legislativos"', "---", "", "Termos usados nas leis e atos da Câmara de Pinheiro. Para entender o efeito de cada verbo com exemplos reais, veja o guia [Como ler uma lei](/como-ler/).", ""]
for r in glossario_rows:
    gl.append("## " + (r["verbo"] or "").strip())
    gl.append("")
    gl.append((r["definicao"] or "").strip())
    if r["exemplo"]:
        gl.append("")
        gl.append("*Exemplo:* " + r["exemplo"].strip())
    gl.append("")
with open(os.path.join(BASE, "content", "glossario.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(gl))

# Guia "Como ler": cada verbo com um exemplo real do banco.
busca_verbo = {
    "criar": "cria",
    "instituir": "institui",
    "regulamentar / dispor sobre": "regulamenta",
    "denominar": "denomina",
    "reconhecer": "reconhece",
    "suspender": "suspende",
    "alterar / dar nova redação": "altera",
    "revogar": "revoga",
    "designar": "designa",
    "julgar": "julga",
    "requerer / indicar": "indica",
    "homenagear / aplaudir": "aplausos",
}
glossario_data = []
for r in glossario_rows:
    verbo = (r["verbo"] or "").strip()
    termo = busca_verbo.get(verbo.lower(), verbo.split(" / ")[0].lower())
    alvo = q("SELECT * FROM normas WHERE lower(ementa) LIKE ? ORDER BY data DESC LIMIT 1", "%" + termo + "%") if termo else []
    if not alvo:
        tipo_fallback = {"requerer / indicar": "indicacao", "homenagear / aplaudir": "mocao"}.get(verbo.lower())
        if tipo_fallback:
            alvo = q("SELECT * FROM normas WHERE tipo=? ORDER BY data DESC LIMIT 1", tipo_fallback)
    norma = None
    if alvo:
        n = alvo[0]
        norma = {
            "id": n["id"],
            "slug": n["id"].lower(),
            "numero": n["numero"],
            "tipo_label": tipo_label.get(n["tipo"], n["tipo"]),
            "data": n["data"],
            "ementa": clean_ws(n["ementa"]),
        }
    glossario_data.append({
        "verbo": verbo,
        "definicao": clean_ws(r["definicao"]),
        "exemplo": clean_ws(r["exemplo"]),
        "norma": norma,
    })

with open(os.path.join(BASE, "content", "como-ler.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Como ler uma lei"\nlayout: "como-ler"\ndescription: "O que cada verbo faz e um exemplo real de aplicação na Câmara de Pinheiro."\n---\n')

# Temas
temas_rows = q("SELECT id, nome FROM temas ORDER BY nome")
tm = ["---", 'title: "Temas das leis"', "---", "", "Navegue pelas normas por tema.", ""]
for t in temas_rows:
    tid = t["id"]
    tm.append("## " + t["nome"])
    tm.append("")
    devs = q("""
        SELECT DISTINCT d.id, d.rotulo, n.id AS norma_id, n.numero
        FROM dispositivo_tema dt
        JOIN dispositivos d ON d.id = dt.dispositivo_id
        JOIN normas n ON n.id = d.norma_id
        WHERE dt.tema_id = ?
        ORDER BY n.numero, d.ordem
    """, tid)
    if not devs:
        tm.append("_Nenhum dispositivo vinculado._")
        tm.append("")
        continue
    for d in devs:
        slug_n = d["norma_id"].lower()
        tm.append("- [%s — %s](/normas/%s/#disp-%d)" % (d["norma_id"], d["rotulo"], slug_n, d["id"]))
    tm.append("")
with open(os.path.join(BASE, "content", "temas.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(tm))

# Autores / vereadores
autores_dir = os.path.join(BASE, "content", "vereadores")
os.makedirs(autores_dir, exist_ok=True)
for f in os.listdir(autores_dir):
    if f.endswith(".md") and f != "_index.md":
        os.remove(os.path.join(autores_dir, f))

with open(os.path.join(autores_dir, "_index.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Vereadores e autores"\n---\n\nQuem propôs o quê na Câmara de Pinheiro. Partido, votos e situação eleitoral vêm do TSE, nas eleições de 2020 e 2024.\n')

for a in autores:
    lines = ["---"]
    lines.append('title: "%s"' % yaml_escape(a["nome"]))
    lines.append('autor_id: %d' % a["id"])
    lines.append('slug: "%s"' % a["slug"])
    if a.get("partido"):
        lines.append('partido: "%s"' % yaml_escape(a["partido"]))
    if a.get("nome_urna"):
        lines.append('nome_urna: "%s"' % yaml_escape(a["nome_urna"]))
        lines.append('nome_urna_display: "%s"' % yaml_escape(a["nome_urna_display"]))
        if a.get("nome_urna_igual"):
            lines.append("nome_urna_igual: true")
    if a.get("votos") is not None:
        lines.append('votos: %d' % int(a["votos"] or 0))
    if a.get("situacao_tse"):
        lines.append('situacao_tse: "%s"' % yaml_escape(a["situacao_tse"]))
    if a.get("situacao_tse_ajuda"):
        lines.append('situacao_tse_ajuda: "%s"' % yaml_escape(a["situacao_tse_ajuda"]))
    lines.append('n_proposicoes: %d' % a["n_proposicoes"])
    if a.get("foto"):
        lines.append('foto: "%s"' % yaml_escape(a["foto"]))
        lines.append('foto_ano: %d' % a["foto_ano"])
    lines.append('atual: %s' % ("true" if a.get("atual") else "false"))
    lines.append('anterior: %s' % ("true" if a.get("anterior") else "false"))
    lines.append("legislaturas: [%s]" % ", ".join('"%s"' % yaml_escape(x) for x in a.get("legislaturas", [])))
    if a.get("fonte_url"):
        lines.append('fonte_tse: "%s"' % yaml_escape(a["fonte_url"]))
    imp = a["impacto"]
    lines.append('impacto_total: %d' % imp.get("n_total", 0))
    lines.append('impacto_equivalente: %.1f' % imp.get("autoria_equivalente", 0))
    lines.append('exclusivas: %d' % imp.get("n_exclusiva", 0))
    lines.append('coletivas: %d' % a["n_coletivas"])
    lines.append('taxa_exclusividade: %d' % round(imp.get("taxa_exclusividade", 0) * 100))
    lines.append('peso_medio: %.2f' % imp.get("peso_medio", 0))
    lines.append('og_image: "%s"' % a["og_image"])
    share_txt = a["nome"]
    if imp.get("n_total"):
        share_txt += " — %d proposições" % imp["n_total"]
        if imp.get("n_exclusiva"):
            share_txt += ", %d de autoria exclusiva" % imp["n_exclusiva"]
        if a["stats"].get("n_proposta"):
            share_txt += ", %d com objeto definido" % a["stats"]["n_proposta"]
    share_txt += " na Câmara de Pinheiro"
    lines.append('share_text: "%s"' % yaml_escape(share_txt))
    lines.append("og_cards:")
    lines.append('  - {formato: "4:5", arquivo: "/og/v/%s-4x5.jpg"}' % a["slug"])
    lines.append('  - {formato: "9:16", arquivo: "/og/v/%s-9x16.jpg"}' % a["slug"])
    if a["destaques"]:
        lines.append("destaques:")
        for d in a["destaques"]:
            lines.append('  - "%s"' % yaml_escape(d))
    if a["parceiros"]:
        lines.append("parceiros:")
        for x in a["parceiros"]:
            lines.append('  - {nome: "%s", slug: "%s", n: %d}' % (yaml_escape(x["nome"]), x["slug"], x["n"]))
    lines.append("---")
    lines.append("")
    with open(os.path.join(autores_dir, a["slug"] + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# Página de proposições
props_dir = os.path.join(BASE, "content", "proposicoes")
os.makedirs(props_dir, exist_ok=True)
with open(os.path.join(props_dir, "_index.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Proposições"\n---\n\nIndicações, moções, projetos e requerimentos apresentados na Câmara de Pinheiro.\n')

# JSON
data_dir = os.path.join(BASE, "data")
os.makedirs(data_dir, exist_ok=True)

with open(os.path.join(data_dir, "legislacao.json"), "w", encoding="utf-8") as f:
    json.dump({
        "normas": normas_list,
        "dispositivos": dispositivos_list,
        "temas": list(temas.values()),
        "naturezas": list(naturezas.values()),
        "categorias": list(categorias.values()),
    }, f, ensure_ascii=False, indent=2)

with open(os.path.join(data_dir, "busca.json"), "w", encoding="utf-8") as f:
    json.dump({"partes": busca_list}, f, ensure_ascii=False)

# o texto integral fica nas páginas; o JSON público leva só os metadados
props_json = [{k: v for k, v in p.items() if k != "texto_integral"} for p in props]
with open(os.path.join(data_dir, "proposicoes.json"), "w", encoding="utf-8") as f:
    json.dump(props_json, f, ensure_ascii=False, indent=2)

with open(os.path.join(data_dir, "autores.json"), "w", encoding="utf-8") as f:
    json.dump(autores, f, ensure_ascii=False, indent=2)

with open(os.path.join(data_dir, "glossario.json"), "w", encoding="utf-8") as f:
    json.dump(glossario_data, f, ensure_ascii=False, indent=2)

# Espécies normativas: catálogo com contagens e exemplos
normas_por_especie = {}
for n in normas_list:
    normas_por_especie.setdefault(n["especie"], []).append(n)
props_por_especie = {}
for p in props:
    props_por_especie.setdefault(p["especie"], []).append(p)

especies_view = []
for e in especies:
    k = e["chave"]
    ns = sorted(normas_por_especie.get(k, []), key=lambda x: (x["data"] or ""), reverse=True)
    ps = props_por_especie.get(k, [])
    exemplos = []
    for n in ns[:3]:
        exemplos.append({
            "titulo": n["tipo_label"] + " nº " + str(n["numero"]),
            "url": "/normas/%s/" % n["slug"],
            "data": n["data_label"],
            "ementa": clamp_texto(n["ementa"], 120),
        })
    for p in ps[:2]:
        exemplos.append({
            "titulo": p["identificacao"],
            "url": "/proposicoes/%s/" % p["slug"],
            "data": p["ano_label"],
            "ementa": p["ementa_card"],
        })
    ev = dict(e)
    ev["n_normas"] = len(ns)
    ev["n_props"] = len(ps)
    ev["exemplos"] = exemplos
    ev["ultima"] = ns[0]["data_label"] if ns else ""
    especies_view.append(ev)

especies_json = [dict(e) for e in especies_view]
with open(os.path.join(data_dir, "especies.json"), "w", encoding="utf-8") as f:
    json.dump(especies_json, f, ensure_ascii=False, indent=2)

# Qualidade das proposições
niveis_n = {"bom": 0, "regular": 0, "frágil": 0}
problemas_n = {}
notas = []
q_itens = []
for p in props:
    qual = p["qualidade"]
    if qual["nivel"]:
        niveis_n[qual["nivel"]] = niveis_n.get(qual["nivel"], 0) + 1
    if qual["pontuacao"] is not None:
        notas.append(qual["pontuacao"])
    for pr in qual["problemas"]:
        problemas_n[pr] = problemas_n.get(pr, 0) + 1
    q_itens.append({
        "id": p["id"],
        "identificacao": p["identificacao"],
        "tipo": p["especie_rotulo"],
        "ano": p["ano_label"],
        "situacao": p["situacao_label"],
        "pontuacao": qual["pontuacao"],
        "nivel": qual["nivel"],
        "problemas": qual["problemas"],
        "ementa": p["ementa_card"],
        "autores": p["autores_nomes"],
        "url": "/proposicoes/%s/" % p["slug"],
    })

por_ano_q = {}
for p in props:
    a = p["ano_label"]
    d = por_ano_q.setdefault(a, {"ano": a, "n": 0, "soma": 0, "bom": 0, "fragil": 0})
    d["n"] += 1
    if p["qualidade"]["pontuacao"] is not None:
        d["soma"] += p["qualidade"]["pontuacao"]
    if p["qualidade"]["nivel"] == "bom":
        d["bom"] += 1
    if p["qualidade"]["nivel"] == "frágil":
        d["fragil"] += 1
for d in por_ano_q.values():
    d["media"] = round(d["soma"] / d["n"], 1) if d["n"] else 0

qualidade_json = {
    "resumo": {
        "total": len(props),
        "media": round(sum(notas) / len(notas), 1) if notas else 0,
        "niveis": niveis_n,
        "problemas": [
            {"texto": k, "n": v}
            for k, v in sorted(problemas_n.items(), key=lambda x: -x[1])
        ],
        "por_ano": sorted(por_ano_q.values(), key=lambda x: x["ano"]),
    },
    "itens": q_itens,
}
with open(os.path.join(data_dir, "qualidade.json"), "w", encoding="utf-8") as f:
    json.dump(qualidade_json, f, ensure_ascii=False)

with open(os.path.join(BASE, "content", "estatisticas.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Estatísticas"\nlayout: "estatisticas"\ndescription: "Números das normas, proposições e vereadores de Pinheiro, com cruzamentos entre tipo, ano, situação, autor e partido."\n---\n')

# Endpoints estáticos
static_dados = os.path.join(BASE, "static", "dados")
os.makedirs(static_dados, exist_ok=True)
ARQUIVOS_DADOS = (
    "legislacao.json", "busca.json", "proposicoes.json", "autores.json",
    "especies.json", "qualidade.json",
)
for fname in ARQUIVOS_DADOS:
    src = os.path.join(data_dir, fname)
    dst = os.path.join(static_dados, fname)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
v1_dir = os.path.join(static_dados, "v1")
os.makedirs(v1_dir, exist_ok=True)
for fname in ARQUIVOS_DADOS:
    src = os.path.join(static_dados, fname)
    dst = os.path.join(v1_dir, fname)
    if os.path.exists(src):
        shutil.copyfile(src, dst)

with open(os.path.join(BASE, "content", "normas", "_index.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Leis e atos da Câmara"\n---\n\nTodas as normas cadastradas.\n')

with open(os.path.join(BASE, "content", "tipos.md"), "w", encoding="utf-8") as f:
    f.write(
        '---\ntitle: "Espécies normativas"\nlayout: "tipos"\ndescription: "O que é cada tipo de ato da Câmara de Pinheiro: lei ordinária, decreto legislativo, resolução, portaria e o que é proposição."\n---\n'
    )

with open(os.path.join(BASE, "content", "qualidade.md"), "w", encoding="utf-8") as f:
    f.write(
        '---\ntitle: "Qualidade do registro"\nlayout: "qualidade"\ndescription: "Como cada proposição foi avaliada: ementa, autor, ano, situação e identificação. Transparência sobre lacunas da fonte."\n---\n'
    )

print("done: %d normas, %d dispositivos, %d proposicoes, %d autores" % (len(normas_list), len(dispositivos_list), len(props), len(autores)))
