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

PROP_TIPO_LABEL = {
    "indicacao": "Indicação",
    "mocao": "Moção",
    "requerimento": "Requerimento",
    "projeto_lei_ordinaria": "Projeto de Lei Ordinária",
    "projeto_lei_legislativo": "Projeto de Lei do Legislativo",
    "projeto_decreto_legislativo": "Projeto de Decreto Legislativo",
    "projeto_resolucao": "Projeto de Resolução",
    "emenda_lei_organica": "Emenda à Lei Orgânica",
    "emenda_projeto_lei_legislativo": "Emenda ao Projeto de Lei do Legislativo",
    "emenda_projeto_lei_ordinaria": "Emenda ao Projeto de Lei Ordinária",
    "prestacao_contas_executivo": "Prestação de Contas do Executivo",
}

tipo_label = {
    "lei_organica": "Lei Orgânica",
    "codigo_posturas": "Código de Posturas",
    "decreto_legislativo": "Decreto Legislativo",
    "resolucao": "Resolução",
    "portaria": "Portaria",
    "lei_ordinaria": "Lei Ordinária",
    "regimento_interno": "Regimento Interno",
    "indicacao": "Indicação",
    "mocao": "Moção",
    "requerimento": "Requerimento",
}

relacao_label = {
    "altera": "Altera",
    "revoga": "Revoga",
    "fundamenta": "Fundamenta-se em",
    "alterada_por": "Alterada por",
    "suspende": "Suspende",
    "depende_de": "Depende de",
}

situacao_label_map = {
    "vigente": "Em vigor",
    "projeto_em_tramitacao": "Projeto em tramitação",
    "prazo_expirado": "Prazo expirado",
    "apresentada": "Apresentada",
    "apresentado": "Apresentado",
    "a_verificar": "A verificar",
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


def humaniza(codigo):
    if not codigo or codigo in ("nao_aplicavel", "nao_identificado"):
        return ""
    return codigo.replace("_", " ").strip().capitalize()


subtipos = {r["codigo"]: dict(r) for r in q("SELECT * FROM subtipos_ato")}

# Autores + mandatos (TSE)
autores_rows = q("SELECT id, nome FROM autores ORDER BY nome")
mandatos_por_autor = {}
for r in q("SELECT * FROM autor_mandato ORDER BY ano_eleicao, autor_id"):
    m = dict(r)
    mandatos_por_autor.setdefault(m["autor_id"], []).append(m)

TSE_LABEL = {
    "ELEITO POR QP": "Eleito por quociente partidário",
    "ELEITO POR MÉDIA": "Eleito por média",
    "SUPLENTE": "Suplente",
    "#NULO": "",
}

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
    ms = sorted(mandatos_por_autor.get(a["id"], []), key=lambda x: x["ano_eleicao"])
    latest = ms[-1] if ms else {}
    for campo in ("nome_tse", "nome_urna", "partido", "cargo", "votos",
                  "situacao_tse", "eleito", "fonte_url"):
        a[campo] = latest.get(campo)
    a["ano_tse"] = latest.get("ano_eleicao")
    a["situacao_tse_label"] = label_tse(a.get("situacao_tse"))
    a["situacao_tse_ajuda"] = TSE_AJUDA.get((a.get("situacao_tse") or "").upper(), "")
    a["nome_urna_display"] = display_nome(a.get("nome_urna"))
    a["nome_urna_igual"] = bool(
        a.get("nome_urna") and norm_nome(a["nome_urna"]) == norm_nome(a.get("nome"))
    )
    a["destaques"] = []
    for m in ms:
        m["nome_tse_display"] = display_nome(m.get("nome_tse"))
        m["nome_tse_igual"] = bool(
            m.get("nome_tse") and norm_nome(m["nome_tse"]) == norm_nome(a.get("nome"))
        )
        m["situacao_label"] = label_tse(m.get("situacao_tse"))
        m["situacao_ajuda"] = TSE_AJUDA.get((m.get("situacao_tse") or "").upper(), "")
    a["mandatos"] = ms
    a["legislaturas"] = []
    for m in ms:
        if m.get("eleito") and m.get("legislatura") not in a["legislaturas"]:
            a["legislaturas"].append(m["legislatura"])
    a["atual"] = any(m["ano_eleicao"] == 2024 and m.get("eleito") for m in ms)
    a["anterior"] = any(m["ano_eleicao"] == 2020 and m.get("eleito") for m in ms)
    com_foto = [m for m in ms if m.get("foto")]
    a["foto"] = com_foto[-1]["foto"] if com_foto else ""
    a["foto_ano"] = com_foto[-1]["ano_eleicao"] if com_foto else None
    a["nome_tse_display"] = display_nome(a.get("nome_tse"))
    a["og_image"] = "/og/v/%s.jpg" % a["slug"]
    a["impacto"] = {
        "n_total": 0, "n_exclusiva": 0, "n_dupla": 0, "n_trio": 0,
        "n_coletiva": 0, "n_ampla": 0, "autoria_equivalente": 0,
        "taxa_exclusividade": 0, "peso_medio": 0, "familias": {},
        "tipos": {}, "coautores": [], "anos": {},
    }
    autores.append(a)
    autor_por_id[a["id"]] = a

# Autores por proposição
autores_por_prop = {}
for r in q("SELECT proposicao_id, autor_id FROM proposicao_autor"):
    a = autor_por_id.get(r["autor_id"])
    if a:
        autores_por_prop.setdefault(r["proposicao_id"], []).append(a)

# Texto das proposições
justificativas = {
    r["proposicao_id"]: md_text(r["justificativa"])
    for r in q("SELECT proposicao_id, justificativa FROM justificativas ORDER BY proposicao_id, rowid")
}

# Proposições
props_rows = q("SELECT * FROM proposicoes ORDER BY ano DESC, id DESC")
props = []
props_por_autor = {}
for r in props_rows:
    p = dict(r)
    autores_prop = autores_por_prop.get(p["id"], [])
    p["autores"] = [
        {"id": a["id"], "nome": a["nome"], "slug": a["slug"], "partido": a.get("partido")}
        for a in autores_prop
    ]
    p["autores_nomes"] = [a["nome"] for a in autores_prop]
    p["autor_ids"] = [a["id"] for a in autores_prop]
    p["n_autores"] = len(autores_prop)
    p["autoria_categoria"] = categoria_autoria(len(autores_prop))
    p["autoria_label"] = autoria_label(len(autores_prop))
    p["coletiva"] = len(autores_prop) >= 10
    p["ementa_limpa"] = clean_ws(p.get("ementa"))
    p["ementa_curta"] = clamp_texto(p["ementa_limpa"], 160)
    p["ementa_card"] = clamp_texto(p["ementa_limpa"], 110)
    p["ementa_truncada"] = (p.get("ementa") or "").rstrip().endswith(("...", "…"))
    p["situacao_label"] = PROP_SITUACAO_LABEL.get(
        p["situacao"] or "", p["situacao"] or ""
    )
    p["situacao_classe"] = PROP_SITUACAO_CLASSE.get(p["situacao"] or "", "off")
    p["ano_label"] = p["ano"] or "—"
    p["data_prop"] = ""
    p["especie"] = p["tipo"] or ""
    p["especie_rotulo"] = PROP_TIPO_LABEL.get(p["tipo"] or "", p["tipo"] or "")
    p["familia"] = ""
    p["familia_label"] = ""
    sub = subtipos.get(p.get("subtipo") or "", {})
    p["classe"] = p.get("subtipo") or "outro_ato"
    p["classe_rotulo"] = sub.get("nome") or humaniza(p.get("subtipo")) or "Outro ato"
    p["classe_curta"] = p["classe_rotulo"]
    p["classe_evidencia"] = sub.get("descricao") or ""
    p["tema"] = p.get("tema") or ""
    p["tema_rotulo"] = humaniza(p.get("tema"))
    p["tema_evidencia"] = ""
    p["slug"] = re.sub(r"[^a-z0-9]+", "-", (p["identificacao"] or "").lower()).strip("-") or ("prop-%s" % p["id"])
    p["texto_integral"] = justificativas.get(p["id"], "")
    p["pdf_arquivo"] = p.get("arquivo_pdf") or ""
    p["pdf_url"] = "/pdfs/%s" % p["pdf_arquivo"] if p["pdf_arquivo"] else ""
    p["tem_texto"] = len(p["texto_integral"]) > 100
    p["qualidade"] = {"pontuacao": None, "nivel": "", "problemas": []}
    props.append(p)
    for a in autores_prop:
        a["n_proposicoes"] += 1
        props_por_autor.setdefault(a["id"], []).append(p)

# Impacto e estatísticas de autoria
for a in autores:
    ps = props_por_autor.get(a["id"], [])
    imp = a["impacto"]
    imp["n_total"] = len(ps)
    pesos = 0.0
    coautores = {}
    for p in ps:
        n = max(p["n_autores"], 1)
        pesos += 1.0 / n
        imp["anos"][str(p["ano"])] = imp["anos"].get(str(p["ano"]), 0) + 1
        imp["tipos"][p["especie_rotulo"]] = imp["tipos"].get(p["especie_rotulo"], 0) + 1
        if n <= 1:
            imp["n_exclusiva"] += 1
        elif n == 2:
            imp["n_dupla"] += 1
        elif n == 3:
            imp["n_trio"] += 1
        elif n < 10:
            imp["n_coletiva"] += 1
        else:
            imp["n_ampla"] += 1
        for outro in p["autores"]:
            if outro["id"] != a["id"]:
                coautores[outro["nome"]] = coautores.get(outro["nome"], 0) + 1
    imp["autoria_equivalente"] = pesos
    imp["taxa_exclusividade"] = (imp["n_exclusiva"] / len(ps)) if ps else 0
    imp["peso_medio"] = (pesos / len(ps)) if ps else 0
    imp["coautores"] = [
        {"nome": k, "n": v} for k, v in sorted(coautores.items(), key=lambda x: -x[1])[:10]
    ]


def stats_de_proposicoes(ps):
    by_year, by_tipo, by_situacao, by_classe = {}, {}, {}, {}
    aprovadas = rejeitadas = 0
    for p in ps:
        ano = str(p.get("ano") or "")
        if re.fullmatch(r"\d{4}", ano) and 2000 <= int(ano) <= 2030:
            by_year[ano] = by_year.get(ano, 0) + 1
        by_tipo[p.get("especie_rotulo") or "Não informado"] = by_tipo.get(p.get("especie_rotulo") or "Não informado", 0) + 1
        cls = p.get("classe_rotulo") or "Outro ato"
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
        "by_familia": {},
        "by_situacao": dict(sorted(by_situacao.items(), key=lambda x: -x[1])),
        "by_classe": dict(sorted(by_classe.items(), key=lambda x: -x[1])),
    }


for a in autores:
    a["stats"] = stats_de_proposicoes(props_por_autor.get(a["id"], []))
    a["impacto_equivalente_label"] = ("%.1f" % a["impacto"].get("autoria_equivalente", 0)).replace(".", ",")
    a["parceiros"] = [
        {"nome": x["nome"], "slug": slugify(x["nome"]), "n": x["n"]}
        for x in a["impacto"].get("coautores", [])
    ]
    a["n_coletivas"] = a["impacto"].get("n_coletiva", 0) + a["impacto"].get("n_ampla", 0)


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
for f in os.listdir(props_dir):
    if f.endswith(".md") and f != "_index.md":
        os.remove(os.path.join(props_dir, f))
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
    if p["tema_rotulo"]:
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

# Normas
normas_list = []
dispositivos_list = []
busca_list = []
normas_by_id = {}

normas_rows = q("SELECT * FROM normas ORDER BY data DESC, id")
fontes = {r["id"]: dict(r) for r in q("SELECT * FROM fontes")}

for n in normas_rows:
    nid = n["id"]
    normas_by_id[nid] = {
        "id": nid,
        "slug": nid.lower(),
        "numero": n["numero"],
        "titulo": md_text(n["ementa"]) or nid,
        "tipo_label": tipo_label.get(n["tipo"], n["tipo"]),
    }

for n in normas_rows:
    nid = n["id"]
    s = nid.lower()
    sit = n["situacao"]
    sit_label = situacao_label_map.get(sit, sit)
    ementa = md_text(n["ementa"])
    obs = md_text(n["observacao"])
    tipo = n["tipo"]
    tipo_lbl = tipo_label.get(tipo, tipo)
    fonte = fontes.get(n["fonte_id"])
    dsps = q("SELECT * FROM dispositivos WHERE norma_id=? ORDER BY ordem, id", nid)
    arquivo_pdf = n["arquivo_pdf"] if "arquivo_pdf" in n.keys() else None
    normas_list.append({
        "id": nid,
        "slug": s,
        "tipo": tipo,
        "tipo_label": tipo_lbl,
        "especie": tipo,
        "especie_rotulo": tipo_lbl,
        "familia": "",
        "familia_label": "",
        "numero": n["numero"],
        "data": n["data"],
        "data_label": n["data"] if len(n["data"] or "") == 10 else (n["data"] or "Sem data"),
        "situacao": sit,
        "situacao_label": sit_label,
        "ementa": ementa,
        "ementa_curta": clamp_texto(ementa, 170),
        "observacao": obs,
        "n_dispositivos": len(dsps),
        "fonte_arquivo": (fonte or {}).get("arquivo", ""),
        "pdf_url": "/pdfs/%s" % arquivo_pdf if arquivo_pdf else "",
        "texto_disponivel": n["texto_disponivel"],
        "og_image": "/og/site.jpg",
    })

content_dir = os.path.join(BASE, "content", "normas")
os.makedirs(content_dir, exist_ok=True)
for f in os.listdir(content_dir):
    if f.endswith(".md") and f != "_index.md":
        os.remove(os.path.join(content_dir, f))

for n in normas_rows:
    nid = n["id"]
    s = nid.lower()
    sit = n["situacao"]
    sit_label = situacao_label_map.get(sit, sit)
    ementa = md_text(n["ementa"])
    obs = md_text(n["observacao"])
    tipo = n["tipo"]
    tipo_lbl = tipo_label.get(tipo, tipo)
    fonte = fontes.get(n["fonte_id"])
    dsps = q("SELECT * FROM dispositivos WHERE norma_id=? ORDER BY ordem, id", nid)
    rels = []
    for r in q("SELECT * FROM relacoes WHERE origem=?", nid):
        dest_norma = normas_by_id.get(r["destino"]) if r["destino_no_banco"] else None
        rels.append({
            "tipo_label": relacao_label.get(r["tipo"], r["tipo"]),
            "destino": r["destino"],
            "destino_norma": dest_norma,
            "observacao": md_text(r["observacao"]),
        })
    for r in q("SELECT * FROM relacoes WHERE destino=? AND destino_no_banco=1", nid):
        rels.append({
            "tipo_label": relacao_label.get(r["tipo"], r["tipo"]),
            "destino": r["origem"],
            "destino_norma": normas_by_id.get(r["origem"]),
            "observacao": md_text(r["observacao"]),
        })
    alts = [dict(r) for r in q("SELECT * FROM alteracoes WHERE norma_id=? ORDER BY rotulo, paragrafo", nid)]
    arquivo_pdf = n["arquivo_pdf"] if "arquivo_pdf" in n.keys() else None

    titulo_pagina = ementa if ementa else nid

    lines = ["---"]
    lines.append('title: "%s"' % yaml_escape(titulo_pagina))
    lines.append('norma_id: "%s"' % nid)
    lines.append('tipo: "%s"' % tipo)
    lines.append('tipo_label: "%s"' % tipo_lbl)
    lines.append('numero: "%s"' % yaml_escape(n["numero"]))
    lines.append('data: "%s"' % n["data"])
    lines.append('ano: "%s"' % (n["data"][:4] if n["data"] else ""))
    if arquivo_pdf:
        lines.append('pdf_url: "/pdfs/%s"' % yaml_escape(arquivo_pdf))
    lines.append('especie: "%s"' % tipo)
    lines.append('og_image: "/og/site.jpg"')
    lines.append('situacao: "%s"' % sit)
    lines.append('situacao_label: "%s"' % yaml_escape(sit_label))
    lines.append('ementa: "%s"' % yaml_escape(ementa))
    if obs:
        lines.append('observacao: "%s"' % yaml_escape(obs))
    if fonte:
        lines.append('fonte_arquivo: "%s"' % yaml_escape(fonte.get("arquivo") or ""))
        lines.append('fonte_paginas: %s' % (fonte.get("paginas") or 0))
    lines.append("---")
    lines.append("")
    lines.append("**%s**" % (ementa if ementa else nid))
    lines.append("")
    meta = []
    meta.append("**Tipo:** %s" % tipo_lbl)
    meta.append("**Número:** %s" % n["numero"])
    meta.append("**Data:** %s" % n["data"])
    meta.append("**Situação:** %s" % sit_label)
    if fonte and fonte.get("arquivo"):
        meta.append("**Fonte:** %s" % fonte["arquivo"])
    lines.append(" · ".join(meta))
    lines.append("")
    if arquivo_pdf:
        lines.append("**Documento original:** [ver PDF](/pdfs/%s)" % arquivo_pdf)
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

        heading = rotulo if rotulo else (tit if tit else cap)
        if not heading:
            heading = "Art. %d" % d["ordem"]
        lines.append('<a id="disp-%d"></a>' % did)
        lines.append("### " + heading)
        lines.append("")
        if status:
            lines.append("*Status: %s*" % status)
            lines.append("")
        parts = q("SELECT * FROM dispositivo_partes WHERE dispositivo_id=? ORDER BY ordem, id", did)
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
    if a.get("ano_tse"):
        lines.append('ano_tse: %d' % a["ano_tse"])
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
    share_txt += " na Câmara de Pinheiro"
    lines.append('share_text: "%s"' % yaml_escape(share_txt))
    lines.append("og_cards:")
    lines.append('  - {formato: "4:5", arquivo: "/og/v/%s-4x5.jpg"}' % a["slug"])
    lines.append('  - {formato: "9:16", arquivo: "/og/v/%s-9x16.jpg"}' % a["slug"])
    if a["parceiros"]:
        lines.append("parceiros:")
        for x in a["parceiros"]:
            lines.append('  - {nome: "%s", slug: "%s", n: %d}' % (yaml_escape(x["nome"]), x["slug"], x["n"]))
    lines.append("---")
    lines.append("")
    with open(os.path.join(autores_dir, a["slug"] + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

with open(os.path.join(props_dir, "_index.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Proposições"\n---\n\nIndicações, moções, projetos e requerimentos apresentados na Câmara de Pinheiro.\n')

# JSON
data_dir = os.path.join(BASE, "data")
os.makedirs(data_dir, exist_ok=True)

with open(os.path.join(data_dir, "legislacao.json"), "w", encoding="utf-8") as f:
    json.dump({
        "normas": normas_list,
        "dispositivos": dispositivos_list,
    }, f, ensure_ascii=False, indent=2)

with open(os.path.join(data_dir, "busca.json"), "w", encoding="utf-8") as f:
    json.dump({"partes": busca_list}, f, ensure_ascii=False)

props_json = [{k: v for k, v in p.items() if k != "texto_integral"} for p in props]
with open(os.path.join(data_dir, "proposicoes.json"), "w", encoding="utf-8") as f:
    json.dump(props_json, f, ensure_ascii=False, indent=2)

with open(os.path.join(data_dir, "autores.json"), "w", encoding="utf-8") as f:
    json.dump(autores, f, ensure_ascii=False, indent=2)

with open(os.path.join(data_dir, "glossario.json"), "w", encoding="utf-8") as f:
    json.dump(glossario_data, f, ensure_ascii=False, indent=2)

with open(os.path.join(BASE, "content", "estatisticas.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Estatísticas"\nlayout: "estatisticas"\ndescription: "Números das normas, proposições e vereadores de Pinheiro, com cruzamentos entre tipo, ano, situação, autor e partido."\n---\n')

# Endpoints estáticos
static_dados = os.path.join(BASE, "static", "dados")
os.makedirs(static_dados, exist_ok=True)
ARQUIVOS_DADOS = ("legislacao.json", "busca.json", "proposicoes.json", "autores.json", "glossario.json")
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

# Páginas descontinuadas (sem tabelas no banco novo)
for nome in ("temas.md", "qualidade.md", "tipos.md"):
    caminho = os.path.join(BASE, "content", nome)
    if os.path.exists(caminho):
        os.remove(caminho)
for fname in ("especies.json", "qualidade.json"):
    for pasta in (data_dir, static_dados, v1_dir):
        caminho = os.path.join(pasta, fname)
        if os.path.exists(caminho):
            os.remove(caminho)

with open(os.path.join(BASE, "content", "normas", "_index.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Leis e atos da Câmara"\n---\n\nTodas as normas cadastradas.\n')

print("done: %d normas, %d dispositivos, %d proposicoes, %d autores" % (len(normas_list), len(dispositivos_list), len(props), len(autores)))
