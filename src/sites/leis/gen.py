import sqlite3, json, os, urllib.request, datetime, shutil

BASE = "/opt/servidor/src/sites/leis"
DB = "/opt/servidor/data/servicos/leis/legislacao_pinheiro.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

def q(sql, *a):
    return c.execute(sql, a).fetchall()

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

def slug(nid):
    return nid.lower()

def norma_categorias(nid):
    ids = [r["categoria_id"] for r in q("SELECT categoria_id FROM norma_categoria WHERE norma_id=?", nid)]
    return [categorias[i]["nome"] for i in ids if i in categorias]

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
    return [dict(r) for r in rows]

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
    sit = n["situacao"]
    sit_label = situacao_label_map.get(sit, sit)
    ementa = md_text(n["ementa"])
    obs = md_text(n["observacao"])
    tipo = n["tipo"]
    tipo_lbl = tipo_label.get(tipo, tipo)
    nzid, nznome, nzdesc, nzjust = norma_natureza(nid)

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

        heading = rotulo if rotulo else (tit if tit else cap)
        if not heading:
            heading = "Art. %d" % d["ordem"]
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
        for e in expls:
            titulo = md_text(e["titulo"])
            texto_e = md_text(e["texto"])
            exemplo = md_text(e["exemplo"])
            lines.append('<details class="expl">')
            lines.append('<summary class="expl-sum">💡 Explicação simples</summary>')
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
            "n_explicacoes": len(expls),
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
        "natureza_id": nzid or "",
        "natureza": nznome or "",
        "natureza_desc": nzdesc or "",
        "n_dispositivos": len(dispositivos(nid)),
    })

# --- Glossário ---
glossario_rows = q("SELECT verbo, definicao, exemplo FROM glossario ORDER BY verbo")
os.makedirs(os.path.join(BASE, "content"), exist_ok=True)
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

# --- Temas ---
temas_rows = q("SELECT id, nome FROM temas ORDER BY nome")
tm = ["---", 'title: "Temas das leis"', "---", "", "Navegue pelas normas por tema.", ""]
for t in temas_rows:
    tid = t["id"]
    tm.append("## " + t["nome"])
    tm.append("")
    devs = q("""SELECT DISTINCT d.id, d.rotulo, n.id AS norma_id, n.numero
               FROM dispositivo_tema dt
               JOIN dispositivos d ON d.id = dt.dispositivo_id
               JOIN normas n ON n.id = d.norma_id
               WHERE dt.tema_id = ?
               ORDER BY n.numero, d.ordem""", tid)
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

# Publicar JSON como endpoints estáticos (sem API/backend)
static_dados = os.path.join(BASE, "static", "dados")
os.makedirs(static_dados, exist_ok=True)
for fname in ("legislacao.json", "busca.json"):
    src = os.path.join(data_dir, fname)
    dst = os.path.join(static_dados, fname)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
# versão estável
v1_dir = os.path.join(static_dados, "v1")
os.makedirs(v1_dir, exist_ok=True)
for fname in ("legislacao.json", "busca.json"):
    src = os.path.join(static_dados, fname)
    dst = os.path.join(v1_dir, fname)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
print("static dados publicados em", static_dados)

os.makedirs(os.path.join(BASE, "content"), exist_ok=True)
os.makedirs(os.path.join(BASE, "content", "normas"), exist_ok=True)
with open(os.path.join(BASE, "content", "normas", "_index.md"), "w", encoding="utf-8") as f:
    f.write('---\ntitle: "Leis e atos da Câmara"\n---\n\nTodas as normas cadastradas.\n')

print("done: %d normas" % len(normas_list))
