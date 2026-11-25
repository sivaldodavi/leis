import sqlite3, json, os, re, shutil, unicodedata

BASE = "/opt/servidor/src/sites/leis"
DB = "/opt/servidor/data/servicos/leis/legislacao_pinheiro.db"
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


temas = {r["id"]: dict(r) for r in q("SELECT * FROM temas")}
categorias = {r["id"]: dict(r) for r in q("SELECT * FROM categorias")}
naturezas = {r["id"]: dict(r) for r in q("SELECT * FROM naturezas")}

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


# Autores + TSE
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

autores = []
autor_por_id = {}
for r in autores_rows:
    a = dict(r)
    a["slug"] = slugify(a["nome"])
    a["n_proposicoes"] = 0
    autores.append(a)
    autor_por_id[a["id"]] = a

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
for r in props_rows:
    p = dict(r)
    nomes = [x for x in (p.pop("autores_nomes") or "").split("||") if x]
    p["autores"] = [a for a in autores if a["nome"] in nomes]
    p["autores_nomes"] = nomes
    p["ementa_curta"] = clean_ws(p["ementa"])
    if len(p["ementa_curta"]) > 220:
        p["ementa_curta"] = p["ementa_curta"][:217].rstrip() + "..."
    props.append(p)
    for a in p["autores"]:
        a["n_proposicoes"] += 1

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
    normas_list.append({
        "id": nid,
        "slug": s,
        "tipo": tipo,
        "tipo_label": tipo_lbl,
        "numero": n["numero"],
        "data": n["data"],
        "situacao": sit,
        "situacao_label": sit_label,
        "ementa": ementa,
        "observacao": obs,
        "categorias": cats,
        "natureza": nznome or "",
        "n_dispositivos": len(dsps),
        "fonte_arquivo": (fonte or {}).get("arquivo", ""),
        "teor_status": n["teor_status"] or "",
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
    ementa = md_text(n["ementa"])
    obs = md_text(n["observacao"])
    tipo = n["tipo"]
    tipo_lbl = tipo_label.get(tipo, tipo)
    nzid, nznome = norma_natureza(nid)
    fonte = norma_fonte(nid)
    dsps = dispositivos(nid)
    rels = relacoes_da_norma(nid)
    alts = alteracoes_da_norma(nid)
    evs = eventos_da_norma(nid)

    lines = ["---"]
    lines.append('title: "%s"' % yaml_escape(ementa if ementa else nid))
    lines.append('norma_id: "%s"' % nid)
    lines.append('tipo: "%s"' % tipo)
    lines.append('tipo_label: "%s"' % tipo_lbl)
    lines.append('numero: "%s"' % yaml_escape(n["numero"]))
    lines.append('data: "%s"' % n["data"])
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
gl = ["---", 'title: "Glossário de termos legislativos"', "---", "", "Termos usados nas leis e atos da Câmara de Pinheiro.", ""]
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
    f.write('---\ntitle: "Vereadores e autores"\n---\n\nQuem propôs o quê na Câmara de Pinheiro. Partido, votos e situação eleitoral vêm do TSE (eleição de 2024).\n')

for a in autores:
    props_autor = [p for p in props if a["id"] in [x["id"] for x in p["autores"]]]
    lines = ["---"]
    lines.append('title: "%s"' % yaml_escape(a["nome"]))
    lines.append('autor_id: %d' % a["id"])
    lines.append('slug: "%s"' % a["slug"])
    if a.get("partido"):
        lines.append('partido: "%s"' % yaml_escape(a["partido"]))
    if a.get("nome_urna"):
        lines.append('nome_urna: "%s"' % yaml_escape(a["nome_urna"]))
    if a.get("votos") is not None:
        lines.append('votos: %d' % int(a["votos"] or 0))
    if a.get("situacao_tse"):
        lines.append('situacao_tse: "%s"' % yaml_escape(a["situacao_tse"]))
    lines.append('n_proposicoes: %d' % len(props_autor))
    if a.get("fonte_url"):
        lines.append('fonte_tse: "%s"' % yaml_escape(a["fonte_url"]))
    lines.append("---")
    lines.append("")
    if a.get("partido"):
        lines.append("**Partido:** %s · **Votos em 2024:** %s · **Situação no TSE:** %s" % (
            a["partido"], a.get("votos") or 0, a.get("situacao_tse") or "—"))
    else:
        lines.append("_Sem correspondência identificada nos dados do TSE._")
    lines.append("")
    lines.append("**Proposições:** %d" % len(props_autor))
    lines.append("")
    if a.get("fonte_url"):
        lines.append("Fonte: [TSE — Candidatos 2024](%s)." % a["fonte_url"])
        lines.append("")
    if props_autor:
        lines.append("## Proposições")
        lines.append("")
        ano_atual = None
        for p in props_autor:
            if p["ano"] != ano_atual:
                ano_atual = p["ano"]
                lines.append("### %s" % (ano_atual or "Sem ano"))
                lines.append("")
            nome = p.get("identificacao") or ("%s %s/%s" % (p.get("tipo") or "", p.get("numero") or "", p.get("ano") or ""))
            lines.append("- [%s](/proposicoes/#prop-%d) — %s" % (nome, p["id"], p["ementa_curta"]))
        lines.append("")
    else:
        lines.append("_Nenhuma proposição registrada._")
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

with open(os.path.join(data_dir, "proposicoes.json"), "w", encoding="utf-8") as f:
    json.dump(props, f, ensure_ascii=False, indent=2)

with open(os.path.join(data_dir, "autores.json"), "w", encoding="utf-8") as f:
    json.dump(autores, f, ensure_ascii=False, indent=2)

# Endpoints estáticos
static_dados = os.path.join(BASE, "static", "dados")
os.makedirs(static_dados, exist_ok=True)
for fname in ("legislacao.json", "busca.json", "proposicoes.json", "autores.json"):
    src = os.path.join(data_dir, fname)
    dst = os.path.join(static_dados, fname)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
v1_dir = os.path.join(static_dados, "v1")
os.makedirs(v1_dir, exist_ok=True)
for fname in ("legislacao.json", "busca.json", "proposicoes.json", "autores.json"):
    src = os.path.join(static_dados, fname)
    dst = os.path.join(v1_dir, fname)
    if os.path.exists(src):
        shutil.copyfile(src, dst)

with open(os.path.join(BASE, "content", "normas", "_index.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Leis e atos da Câmara"\n---\n\nTodas as normas cadastradas.\n')

print("done: %d normas, %d dispositivos, %d proposicoes, %d autores" % (len(normas_list), len(dispositivos_list), len(props), len(autores)))
