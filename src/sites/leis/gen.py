import sqlite3, json, os, urllib.request, datetime, shutil

BASE = "/opt/servidor/src/sites/leis"
DB = "/opt/servidor/data/servicos/leis/legislacao_pinheiro.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

def q(sql, *a):
    return c.execute(sql, a).fetchall()

publicos = {r["id"]: dict(r) for r in q("SELECT * FROM publicos")}
temas = {r["id"]: dict(r) for r in q("SELECT * FROM temas")}
categorias = {r["id"]: dict(r) for r in q("SELECT * FROM categorias")}
naturezas = {r["id"]: dict(r) for r in q("SELECT * FROM naturezas")}

situacao_label_map = {
    "vigente": "Em vigor",
    "projeto_em_tramitacao": "Projeto em tramitação",
    "prazo_expirado": "Prazo expirado",
    "apresentada": "Apresentada",
    "apresentado": "Apresentado",
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

short_profile = {"cidadao":"Morador","comerciante":"Comerciante","estudante":"Estudante","responsavel":"Responsável","servidor":"Servidor"}

def slug(nid):
    return nid.lower()

def norma_categorias(nid):
    ids = [r["categoria_id"] for r in q("SELECT categoria_id FROM norma_categoria WHERE norma_id=?", nid)]
    return [categorias[i]["nome"] for i in ids if i in categorias]

def norma_publicos(nid):
    rows = q("SELECT publico_id, motivo FROM norma_publico WHERE norma_id=?", nid)
    return [(r["publico_id"], r["motivo"]) for r in rows]

def norma_natureza(nid):
    rows = q("SELECT natureza_id, justificativa FROM norma_natureza WHERE norma_id=?", nid)
    if not rows:
        return None, None, None, None
    r = rows[0]
    nzid = r["natureza_id"]
    nz = naturezas.get(nzid, {})
    return nzid, nz.get("nome"), nz.get("descricao"), r["justificativa"]

def dispositivos(nid):
    return q("SELECT * FROM dispositivos WHERE norma_id=? ORDER BY ordem", nid)

def partes_do_disp(did):
    return q("SELECT * FROM dispositivo_partes WHERE dispositivo_id=? ORDER BY ordem", did)

def temas_do_disp(did):
    ids = [r["tema_id"] for r in q("SELECT tema_id FROM dispositivo_tema WHERE dispositivo_id=?", did)]
    return [temas[i]["nome"] for i in ids if i in temas]

def explicacoes_do_disp(did):
    rows = q("SELECT * FROM explicacoes WHERE dispositivo_id=?", did)
    out = {}
    for r in rows:
        out.setdefault(r["publico_id"], []).append(dict(r))
    return out

def md_text(s):
    return (s or "").strip()

content_dir = os.path.join(BASE, "content", "normas")
os.makedirs(content_dir, exist_ok=True)
for f in os.listdir(content_dir):
    if f.endswith(".md") and f != "_index.md":
        os.remove(os.path.join(content_dir, f))

normas_list = []
dispositivos_list = []
busca_list = []
for n in q("SELECT * FROM normas ORDER BY id"):
    nid = n["id"]
    s = slug(nid)
    cats = norma_categorias(nid)
    pubs = norma_publicos(nid)
    pub_names = [publicos[p[0]]["nome"] if p[0] in publicos else p[0] for p in pubs]
    sit = n["situacao"]
    sit_label = situacao_label_map.get(sit, sit)
    ementa = md_text(n["ementa"])
    obs = md_text(n["observacao"])
    tipo = n["tipo"]
    tipo_lbl = tipo_label.get(tipo, tipo)
    nzid, nznome, nzdesc, nzjust = norma_natureza(nid)

    norma_expl_perfis = set()
    lines = []
    lines.append("---")
    lines.append('title: "%s"' % (ementa if ementa else nid).replace('"', '\\"'))
    lines.append('norma_id: "%s"' % nid)
    lines.append('tipo: "%s"' % tipo)
    lines.append('numero: "%s"' % n["numero"])
    lines.append('data: "%s"' % n["data"])
    lines.append('situacao: "%s"' % sit)
    lines.append('situacao_label: "%s"' % sit_label)
    lines.append('ementa: "%s"' % ementa.replace('"', '\\"'))
    if obs:
        lines.append('observacao: "%s"' % obs.replace('"', '\\"'))
    lines.append("categorias: [%s]" % ", ".join('"%s"' % c for c in cats))
    lines.append("publicos: [%s]" % ", ".join('"%s"' % p[0] for p in pubs))
    lines.append("explicacoes_perfis: [%s]" % ", ".join('"%s"' % p for p in sorted(norma_expl_perfis)))
    if pubs:
        lines.append("publicos_motivos:")
        for p in pubs:
            motivo = md_text(p[1]).replace('"', '\\"')
            lines.append('  %s: "%s"' % (p[0], motivo))
    if nzid:
        lines.append('natureza_id: "%s"' % nzid)
    if nznome:
        lines.append('natureza: "%s"' % nznome.replace('"', '\\"'))
    if nzdesc:
        lines.append('natureza_desc: "%s"' % nzdesc.replace('"', '\\"'))
    lines.append("---")
    lines.append("")
    lines.append("**%s**" % (ementa if ementa else nid))
    lines.append("")
    if cats:
        lines.append("**Categorias:** " + ", ".join(cats))
        lines.append("")
    if nznome:
        lines.append("**Natureza:** " + nznome)
        lines.append("")
    if pub_names:
        lines.append("**Para quem interessa:** " + ", ".join(pub_names))
        lines.append("")
    if obs:
        lines.append("> " + obs)
        lines.append("")
    lines.append("## Dispositivos")
    lines.append("")

    for d in dispositivos(nid):
        did = d["id"]
        rotulo = md_text(d["rotulo"])
        cap = md_text(d["capitulo"])
        tit = md_text(d["titulo"])
        texto = md_text(d["texto"])
        temas_list = temas_do_disp(did)
        expls = explicacoes_do_disp(did)
        expl_perfis_disp = set(expls.keys())
        for _pid in expl_perfis_disp:
            norma_expl_perfis.add(_pid)

        heading = tit if tit else (cap + " " + rotulo).strip()
        if not heading:
            heading = rotulo or ("Art. %d" % d["ordem"])
        lines.append('<a id="disp-%d"></a>' % did)
        lines.append("### " + heading)
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
        for pub_id, lst in expls.items():
            for e in lst:
                short = short_profile.get(pub_id, pub_id)
                titulo = md_text(e["titulo"])
                texto_e = md_text(e["texto"])
                exemplo = md_text(e["exemplo"])
                lines.append('<details class="expl" data-perfil="%s">' % pub_id)
                lines.append('<summary class="expl-sum">💡 Como isso te afeta (%s)</summary>' % short)
                lines.append('<div class="expl-body">')
                if titulo:
                    lines.append('<p class="expl-titulo"><strong>%s</strong></p>' % titulo)
                if texto_e:
                    lines.append('<p>%s</p>' % texto_e)
                if exemplo:
                    lines.append('<p class="expl-exemplo"><em>Exemplo:</em> %s</p>' % exemplo)
                lines.append('</div>')
                lines.append('</details>')
                lines.append("")
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
            "explicacoes_perfis": sorted(expl_perfis_disp),
            "n_explicacoes": sum(len(v) for v in expls.values()),
        })

    out_path = os.path.join(content_dir, s + ".md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

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
        "publicos": [p[0] for p in pubs],
        "publicos_nomes": pub_names,
        "publicos_motivos": {p[0]: md_text(p[1]) for p in pubs},
        "explicacoes_perfis": sorted(norma_expl_perfis),
        "natureza_id": nzid or "",
        "natureza": nznome or "",
        "natureza_desc": nzdesc or "",
        "n_dispositivos": len(dispositivos(nid)),
    })

data_dir = os.path.join(BASE, "data")
os.makedirs(data_dir, exist_ok=True)
with open(os.path.join(data_dir, "legislacao.json"), "w", encoding="utf-8") as f:
    json.dump({
        "normas": normas_list,
        "dispositivos": dispositivos_list,
        "publicos": list(publicos.values()),
        "temas": list(temas.values()),
        "naturezas": list(naturezas.values()),
        "categorias": list(categorias.values()),
    }, f, ensure_ascii=False, indent=2)

with open(os.path.join(data_dir, "busca.json"), "w", encoding="utf-8") as f:
    json.dump({"partes": busca_list}, f, ensure_ascii=False)

# --- Dados abertos (Portal de Transparência Fiorilli) ---
def parse_br(v):
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def fmt_br(x):
    s = "{:.2f}".format(x)
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s

def fetch_json(path):
    url = "http://177.136.250.170:5656/SCPIWEB_CMDEPINHEIRO/" + path
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        print("WARN fetch", path, e)
        return []

base = "versaoJson/"
desp_orgao = fetch_json(base + "Despesas/?ConectarExercicio=2026&Listagem=DespesasPorOrgao&DiaInicioPeriodo=01&MesInicialPeriodo=01&DiaFinalPeriodo=31&MesFinalPeriodo=12&Ano=2026&Empresa=1&MostraDadosConsolidado=False")
desp_forn = fetch_json(base + "Despesas/?ConectarExercicio=2026&Listagem=DespesasPorFornecedor&DiaInicioPeriodo=01&MesInicialPeriodo=01&DiaFinalPeriodo=31&MesFinalPeriodo=12&Ano=2026&Empresa=1&MostrarFornecedor=True&MostraDadosConsolidado=False")
diarias = fetch_json(base + "Despesas/?ConectarExercicio=2026&Listagem=Diarias&DiaInicioPeriodo=01&MesInicialPeriodo=01&DiaFinalPeriodo=31&MesFinalPeriodo=12&Ano=2026&Empresa=1&MostraDadosConsolidado=False")
licitacoes = fetch_json(base + "LicitacoesEContratos/?ConectarExercicio=2026&Listagem=Licitacoes&Ano=2026&Empresa=1&MostraDadosConsolidado=False")
contratos = fetch_json(base + "LicitacoesEContratos/?ConectarExercicio=2026&Listagem=Contratos&Ano=2026&Empresa=1&MostraDadosConsolidado=False&ContratosApenasPublicados=False")
emendas = fetch_json(base + "Transferencias/?ConectarExercicio=2026&Listagem=EmendasImpositivasArt166A&Empresa=1&MostraDadosConsolidado=False")

total_emp = sum(parse_br(x.get("EMPENHADO")) for x in desp_orgao)
total_liq = sum(parse_br(x.get("LIQUIDADO")) for x in desp_orgao)
total_pag = sum(parse_br(x.get("PAGO")) for x in desp_orgao)
diarias_total = sum(parse_br(x.get("VALOR")) for x in diarias) if diarias else 0.0
# fallback: some diarias records may use other field names
if diarias and diarias_total == 0.0:
    for x in diarias:
        for k, v in x.items():
            if "VALOR" in k.upper() or "PAGO" in k.upper():
                diarias_total += parse_br(v)

dinheiro = {
    "atualizado_em": datetime.date.today().isoformat(),
    "fonte": "Portal de Transparência (Fiorilli) - Câmara Municipal de Pinheiro",
    "resumo": {
        "total_empenhado": fmt_br(total_emp),
        "total_liquidado": fmt_br(total_liq),
        "total_pago": fmt_br(total_pag),
        "fornecedores": len(desp_forn),
        "diarias_total": fmt_br(diarias_total),
        "licitacoes": len(licitacoes),
        "contratos": len(contratos),
        "emendas": len(emendas),
    },
    "despesas_orgao": desp_orgao,
    "despesas_fornecedor": desp_forn,
    "diarias": diarias,
    "licitacoes": licitacoes,
    "contratos": contratos,
    "emendas": emendas,
}
with open(os.path.join(data_dir, "dinheiro_publico.json"), "w", encoding="utf-8") as f:
    json.dump(dinheiro, f, ensure_ascii=False, indent=2)
print("dinheiro: orgaos=%d fornecedores=%d diarias=%d licitacoes=%d contratos=%d emendas=%d" % (len(desp_orgao), len(desp_forn), len(diarias), len(licitacoes), len(contratos), len(emendas)))

# Publicar JSON como endpoints estáticos (sem API/backend)
static_dados = os.path.join(BASE, "static", "dados")
os.makedirs(static_dados, exist_ok=True)
for fname in ("legislacao.json", "dinheiro_publico.json", "busca.json"):
    src = os.path.join(data_dir, fname)
    dst = os.path.join(static_dados, fname)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
print("static dados publicados em", static_dados)

os.makedirs(os.path.join(BASE, "content"), exist_ok=True)
os.makedirs(os.path.join(BASE, "content", "normas"), exist_ok=True)
with open(os.path.join(BASE, "content", "normas", "_index.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Leis e atos da Câmara"\n---\n\nTodas as normas cadastradas.\n')

print("done: %d normas" % len(normas_list))
