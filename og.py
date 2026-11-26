#!/usr/bin/env python3
"""
Gera as imagens de compartilhamento (Open Graph e cartões 4:5 / 9:16).

Lê data/autores.json e data/especies.json gerados por gen.py, monta SVG e
rasteriza com rsvg-convert (SVG -> PNG) e ImageMagick (PNG -> JPEG), porque
WhatsApp, Facebook e X não aceitam SVG.

Saída em static/og/:
    site.jpg                       1200x630  (padrão do site)
    tipos/<especie>.jpg            1200x630  (por espécie normativa)
    v/<slug>.jpg                   1200x630  (perfil do vereador)
    v/<slug>-4x5.jpg               1080x1350
    v/<slug>-9x16.jpg              1080x1920

Uso:
    python3 og.py              # gera só o que falta ou está desatualizado
    python3 og.py --force      # regera tudo
    python3 og.py --only v     # só perfis (v, tipos ou site)
"""

import base64
import html
import json
import os
import subprocess
import sys
import tempfile

BASE = os.environ.get("LEIS_BASE", "/opt/servidor/src/sites/leis")
OUT = os.path.join(BASE, "static", "og")

BG = "#F4F1EA"
INK = "#1A1A1A"
GREEN = "#1E7B4F"
MUTED = "#5B5B5B"
LINE = "#B8B2A3"
CREAM = "#FBF9F3"

FONTE = "Liberation Sans, Nimbus Sans, DejaVu Sans, sans-serif"


def esc(s):
    return html.escape(str(s or ""), quote=True)


def wrap(texto, largura, tamanho, max_linhas=None, peso="400"):
    """Quebra o texto em linhas por estimativa de largura (sem Pango aqui).

    O fator muda com o peso da fonte: negrito ocupa mais espaço. O número de
    linhas é sempre limitado a max_linhas, com reticências no fim."""
    texto = " ".join(str(texto or "").split())
    if not texto:
        return []
    fator = {"800": 0.57, "700": 0.555, "600": 0.54}.get(str(peso), 0.52)
    limite = max(6, int(largura / (tamanho * fator)))
    linhas, atual = [], ""
    for p in texto.split(" "):
        teste = (atual + " " + p).strip()
        if len(teste) <= limite or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    if max_linhas and len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        linhas[-1] = linhas[-1].rstrip(" .,;:") + "…"
    return linhas


def txt(x, y, s, tamanho=24, peso="400", cor=INK, anchor="start", opacidade=None,
        espacamento=None):
    extra = ' opacity="%s"' % opacidade if opacidade is not None else ""
    extra += ' letter-spacing="%s"' % espacamento if espacamento is not None else ""
    return (
        '<text x="%s" y="%s" font-family="%s" font-size="%s" font-weight="%s" '
        'fill="%s" text-anchor="%s"%s>%s</text>'
        % (x, y, FONTE, tamanho, peso, cor, anchor, extra, esc(s))
    )


def rect(x, y, w, h, fill=INK, stroke=None, sw=0, rx=0):
    s = ' stroke="%s" stroke-width="%s"' % (stroke, sw) if stroke else ""
    return '<rect x="%s" y="%s" width="%s" height="%s" fill="%s" rx="%s"%s/>' % (
        x, y, w, h, fill, rx, s)


def linha(x1, y1, x2, y2, cor=INK, largura=2):
    return '<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="%s"/>' % (
        x1, y1, x2, y2, cor, largura)


def moldura(w, h):
    """Fundo creme com borda preta de 4 px, o traço da identidade do site."""
    return (
        rect(0, 0, w, h, BG)
        + '<rect x="2" y="2" width="%s" height="%s" fill="none" stroke="%s" stroke-width="4"/>'
        % (w - 4, h - 4, INK)
    )


def marca(x, y, tamanho=20, cor=MUTED):
    return txt(x, y, "LEIS.SIVALDODAVI.COM.BR", tamanho, "700", cor, espacamento="2")


def rodape(w, h, rotulo):
    return linha(0, h - 78, w, h - 78, INK, 3) + txt(
        64, h - 40, rotulo, 20, "600", MUTED)


_B64 = {}


def foto_data_uri(caminho):
    """O rsvg-convert não lê arquivos externos; a foto vai embutida."""
    if caminho not in _B64:
        with open(caminho, "rb") as f:
            _B64[caminho] = base64.b64encode(f.read()).decode("ascii")
    return _B64[caminho]


def avatar_svg(x, y, w, h, foto, iniciais):
    """Foto do TSE (161x225) ou bloco verde com as iniciais."""
    partes = []
    if foto:
        caminho = os.path.join(BASE, "static", foto.lstrip("/"))
        if os.path.exists(caminho):
            partes.append(
                '<image x="%s" y="%s" width="%s" height="%s" preserveAspectRatio="xMidYMid slice" '
                'href="data:image/jpeg;base64,%s"/>' % (x, y, w, h, foto_data_uri(caminho))
            )
            partes.append(rect(x, y, w, h, "none", INK, 4))
            return "".join(partes)
    partes.append(rect(x, y, w, h, GREEN))
    partes.append(txt(x + w / 2, y + h / 2 + h * 0.16, iniciais, int(h * 0.42), "800", "#FFFFFF", "middle"))
    partes.append(rect(x, y, w, h, "none", INK, 4))
    return "".join(partes)


def iniciais(nome):
    partes = [p for p in str(nome or "").split() if len(p) > 2]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:1].upper()
    return (partes[0][:1] + partes[-1][:1]).upper()


def fmt(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    if n == int(n):
        return "{:,}".format(int(n)).replace(",", ".")
    return ("%.1f" % n).replace(".", ",")


# ------------------------------------------------------------------ cartões

def card_site():
    w, h = 1200, 630
    p = [moldura(w, h)]
    p.append(rect(4, 4, 10, h - 8, GREEN))
    p.append(txt(72, 118, "CÂMARA MUNICIPAL DE PINHEIRO, MA", 22, "700", GREEN, espacamento="2"))
    for i, l in enumerate(wrap("As leis de Pinheiro, em linguagem simples.", 940, 66, 2)):
        p.append(txt(72, 210 + i * 74, l, 66, "800"))
    for i, l in enumerate(wrap("Normas, proposições e quem propôs cada uma — dados abertos da Câmara e do TSE.", 860, 28, 2)):
        p.append(txt(72, 400 + i * 38, l, 28, "400", MUTED))
    p.append(rect(72, 486, 300, 4, INK))
    p.append(marca(72, 546, 22))
    p.append(txt(1128, 546, "Entende lei.", 26, "800", GREEN, "end"))
    return w, h, "".join(p)


def card_tipo(e):
    w, h = 1200, 630
    p = [moldura(w, h)]
    p.append(rect(4, 4, 10, h - 8, GREEN))
    p.append(txt(72, 112, str(e.get("familia_label", "")).upper(), 22, "700", GREEN, espacamento="2"))
    linhas_nome = wrap(e.get("rotulo"), 1020, 60, 2)
    for i, l in enumerate(linhas_nome):
        p.append(txt(72, 196 + i * 66, l, 60, "800"))
    base = 196 + len(linhas_nome) * 66 + 26
    for i, l in enumerate(wrap(e.get("o_que_e"), 1000, 26, 4)):
        p.append(txt(72, base + i * 36, l, 26, "400", "#3A3A3A"))
    ys = h - 150
    numeros = []
    if e.get("n_normas"):
        numeros.append((fmt(e["n_normas"]), "normas"))
    if e.get("n_props"):
        numeros.append((fmt(e["n_props"]), "proposições"))
    if e.get("maioria"):
        numeros.append((e["maioria"], "maioria"))
    x = 72
    for valor, rotulo in numeros[:3]:
        p.append(txt(x, ys, valor, 34, "800", GREEN))
        p.append(txt(x, ys + 28, rotulo.upper(), 15, "700", MUTED, espacamento="1"))
        x += 300
    p.append(rodape(w, h, "Espécies normativas · Leis de Pinheiro"))
    return w, h, "".join(p)


def _fatos_vereador(a):
    """Só dados que um eleitor consegue verificar e usar para julgar o mandato."""
    st = a.get("stats") or {}
    imp = a.get("impacto") or {}
    fatos = []
    # O partido já aparece na legenda; repetir aqui só gasta espaço.
    if a.get("votos"):
        fatos.append(("Votos em %s" % (a.get("ano_tse") or ""), fmt(a["votos"])))
    if st.get("aprovadas"):
        fatos.append(("Proposições aprovadas", fmt(st["aprovadas"])))
    if st.get("n_proposta"):
        fatos.append(("Propostas com objeto", fmt(st["n_proposta"])))
    cerimonial = (st.get("n_nomeacao") or 0) + (st.get("n_homenagem") or 0)
    if cerimonial:
        fatos.append(("Nomeações e homenagens", fmt(cerimonial)))
    if imp.get("n_exclusiva"):
        fatos.append(("De autoria exclusiva", fmt(imp["n_exclusiva"])))
    return fatos


def _desenha_fatos(p, fatos, x, y, largura_col, cols=1, max_linhas=None):
    """Rótulo pequeno em cima, número grande embaixo. Devolve o y final."""
    if max_linhas:
        fatos = fatos[:max_linhas]
    for i, (rotulo, valor) in enumerate(fatos):
        col = i % cols
        row = i // cols
        xx = x + col * largura_col
        yy = y + row * 84
        p.append(txt(xx, yy, valor, 28, "800", INK))
        p.append(txt(xx, yy + 22, rotulo.upper(), 13, "700", MUTED, espacamento="1"))
    return y + ((len(fatos) + cols - 1) // cols) * 84


def _bloco_stats(p, a, x, y, largura, tamanho_num=56, gap=None):
    """Três números do perfil, em coluna."""
    imp = a.get("impacto") or {}
    itens = [
        (fmt(imp.get("n_total", a.get("n_proposicoes", 0))), "PROPOSIÇÕES"),
        (fmt(imp.get("autoria_equivalente", 0)), "AUTORIA EQUIVALENTE"),
        (fmt(imp.get("n_exclusiva", 0)), "AUTORIA EXCLUSIVA"),
    ]
    for i, (valor, rotulo) in enumerate(itens):
        yy = y + i * (tamanho_num + 44)
        p.append(txt(x, yy, valor, tamanho_num, "800", GREEN))
        p.append(txt(x, yy + 22, rotulo, 15, "700", MUTED, espacamento="1"))


def _resumo_classe(p, a, x, y, largura):
    st = a.get("stats") or {}
    partes = []
    if st.get("n_proposta"):
        partes.append("%s com objeto definido" % fmt(st["n_proposta"]))
    cerimonial = (st.get("n_nomeacao") or 0) + (st.get("n_homenagem") or 0)
    if cerimonial:
        partes.append("%s nomeações/homenagens" % fmt(cerimonial))
    if not partes:
        return
    for i, l in enumerate(wrap(" · ".join(partes), largura, 20, 1, "600")):
        p.append(txt(x, y + i * 26, l, 20, "600", "#3A3A3A"))


def _stats_linha(p, a, x, y, espaco=212, tamanho=46):
    imp = a.get("impacto") or {}
    itens = [
        (fmt(imp.get("n_total", 0)), "PROPOSIÇÕES"),
        (fmt(imp.get("autoria_equivalente", 0)), "AUTORIA EQUIV."),
        (fmt(imp.get("n_exclusiva", 0)), "EXCLUSIVAS"),
    ]
    for i, (valor, rotulo) in enumerate(itens):
        xx = x + i * espaco
        p.append(txt(xx, y, valor, tamanho, "800", GREEN))
        p.append(txt(xx, y + 28, rotulo, 14, "700", MUTED, espacamento="1"))


def card_vereador(a, formato):
    nome = a.get("nome") or ""
    partido = a.get("partido") or ""
    cargo = []
    if a.get("atual"):
        cargo.append("2025–2028")
    elif a.get("anterior"):
        cargo.append("2021–2024")
    if a.get("situacao_tse_label"):
        cargo.append(a["situacao_tse_label"])
    legenda = " · ".join([x for x in [partido] + cargo if x])
    fatos = _fatos_vereador(a)

    if formato == "4x5":
        w, h = 1080, 1350
        p = [moldura(w, h), rect(4, 4, w - 8, 10, GREEN)]
        p.append(txt(64, 96, "CÂMARA MUNICIPAL DE PINHEIRO", 20, "700", GREEN, espacamento="2"))
        linhas = wrap(nome, 600, 74, 2, "800")
        for i, l in enumerate(linhas):
            p.append(txt(64, 184 + i * 80, l, 74, "800"))
        p.append(avatar_svg(696, 150, 320, 447, a.get("foto"), iniciais(nome)))
        y = 184 + len(linhas) * 80
        fatos_y = 446
        if legenda:
            leg = wrap(legenda, 600, 25, 2, "700")
            for i, l in enumerate(leg):
                p.append(txt(64, y + 42 + i * 30, l, 25, "700", "#3A3A3A"))
            fatos_y = max(fatos_y, y + 42 + len(leg) * 30 + 30)
        # Grade de fatos: nunca encosta no traço nem nos números.
        _desenha_fatos(p, fatos, 64, fatos_y, 300, cols=2, max_linhas=4)
        p.append(linha(64, 720, w - 64, 720, INK, 3))
        _bloco_stats(p, a, 64, 800, w - 128, 54)
        p.append(linha(64, 1056, w - 64, 1056, LINE, 2))
        p.append(marca(64, 1128, 20))
        p.append(txt(w - 64, 1128, "Leis de Pinheiro", 22, "800", GREEN, "end"))
        return w, h, "".join(p)

    if formato == "9x16":
        w, h = 1080, 1920
        p = [moldura(w, h), rect(4, 4, w - 8, 12, GREEN)]
        p.append(txt(64, 110, "CÂMARA MUNICIPAL DE PINHEIRO", 22, "700", GREEN, espacamento="2"))
        linhas = wrap(nome, 960, 84, 3, "800")
        for i, l in enumerate(linhas):
            p.append(txt(64, 220 + i * 92, l, 84, "800"))
        y = 220 + len(linhas) * 92
        if legenda:
            leg = wrap(legenda, 950, 27, 2, "700")
            for i, l in enumerate(leg):
                p.append(txt(64, y + 30 + i * 32, l, 27, "700", "#3A3A3A"))
            y += (len(leg) - 1) * 32
        foto_y = y + 70
        p.append(avatar_svg(64, foto_y, 420, 585, a.get("foto"), iniciais(nome)))
        fim_fatos = _desenha_fatos(p, fatos, 534, foto_y + 26, 480, cols=1, max_linhas=5)
        hline = max(foto_y + 585, fim_fatos + 20) + 50
        p.append(linha(64, hline, w - 64, hline, INK, 3))
        _bloco_stats(p, a, 64, hline + 110, w - 128, 64)
        _resumo_classe(p, a, 64, h - 216, w - 128)
        p.append(linha(64, h - 180, w - 64, h - 180, LINE, 2))
        p.append(marca(64, h - 120, 22))
        p.append(txt(w - 64, h - 120, "Entende lei.", 26, "800", GREEN, "end"))
        return w, h, "".join(p)

    # 16:9 padrão (Open Graph)
    w, h = 1200, 630
    p = [moldura(w, h), rect(4, 4, 10, h - 8, GREEN)]
    p.append(txt(64, 86, "CÂMARA MUNICIPAL DE PINHEIRO", 18, "700", GREEN, espacamento="2"))
    linhas = wrap(nome, 620, 56, 2, "800")
    for i, l in enumerate(linhas):
        p.append(txt(64, 162 + i * 60, l, 56, "800"))
    y = 162 + len(linhas) * 60
    if legenda:
        leg = wrap(legenda, 640, 20, 2, "700")
        for i, l in enumerate(leg):
            p.append(txt(64, y + 28 + i * 24, l, 20, "700", "#3A3A3A"))
        y += (len(leg) - 1) * 24
    hline = max(318, y + 70)
    p.append(linha(64, hline, 700, hline, LINE, 2))
    _stats_linha(p, a, 64, hline + 70, 212, 44)
    if fatos:
        resumo = " · ".join("%s: %s" % (r, v) for r, v in fatos[:2])
        for l in wrap(resumo, 620, 17, 1, "600"):
            p.append(txt(64, 512, l, 17, "600", "#3A3A3A"))
    p.append(avatar_svg(772, 94, 320, 447, a.get("foto"), iniciais(nome)))
    p.append(rodape(w, h, "Perfil do vereador · Leis de Pinheiro"))
    return w, h, "".join(p)


# ------------------------------------------------------------- rasterização

def renderizar(svg, destino, largura, altura):
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    completo = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d">%s</svg>' % (largura, altura, largura, altura, svg)
    )
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8") as f:
        f.write(completo)
        svg_path = f.name
    png_path = svg_path + ".png"
    try:
        subprocess.run(
            ["rsvg-convert", "-w", str(largura), "-h", str(altura), "-o", png_path, svg_path],
            check=True,
        )
        subprocess.run(
            ["magick", png_path, "-quality", "86", "-sampling-factor", "4:2:0",
             "-strip", "-interlace", "Plane", destino],
            check=True,
        )
    finally:
        for x in (svg_path, png_path):
            if os.path.exists(x):
                os.remove(x)


def atualizado(destino, fontes):
    if not os.path.exists(destino):
        return False
    t = os.path.getmtime(destino)
    return all(os.path.exists(f) and os.path.getmtime(f) <= t for f in fontes)


def main():
    force = "--force" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    autores_path = os.path.join(BASE, "data", "autores.json")
    especies_path = os.path.join(BASE, "data", "especies.json")
    with open(autores_path, encoding="utf-8") as f:
        autores = json.load(f)
    with open(especies_path, encoding="utf-8") as f:
        especies = json.load(f)

    total = 0
    if only in (None, "site"):
        alvo = os.path.join(OUT, "site.jpg")
        w, h, svg = card_site()
        renderizar(svg, alvo, w, h)
        total += 1
        print("site.jpg")

    if only in (None, "tipos"):
        for e in especies:
            alvo = os.path.join(OUT, "tipos", "%s.jpg" % e["chave"])
            w, h, svg = card_tipo(e)
            renderizar(svg, alvo, w, h)
            total += 1
        print("%d cartões de espécie" % len(especies))

    if only in (None, "v"):
        for a in autores:
            fontes = [autores_path]
            foto = a.get("foto")
            if foto:
                fontes.append(os.path.join(BASE, "static", foto.lstrip("/")))
            for formato, nome in (("16x9", "%s.jpg"), ("4x5", "%s-4x5.jpg"), ("9x16", "%s-9x16.jpg")):
                alvo = os.path.join(OUT, "v", nome % a["slug"])
                if not force and atualizado(alvo, fontes):
                    continue
                w, h, svg = card_vereador(a, formato)
                renderizar(svg, alvo, w, h)
                total += 1
        print("perfis: %d imagens" % total)

    print("prontas: %d imagens em %s" % (total, OUT))


if __name__ == "__main__":
    main()
