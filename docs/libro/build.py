"""Genera el libro "ARYA, de cero a agente" desde los capitulos en Markdown.

Uso (desde la carpeta del proyecto):  ~/.venvs/arya-industrial-demo/bin/python docs/libro/build.py

Salidas en docs/libro/:
  - libro-arya.html    documento completo (para abrir en el navegador y exportar a PDF)
  - libro-arya.page.html  el mismo contenido sin el esqueleto <html>, para publicarlo como pagina

Directivas propias, cada una en su propia linea:
  @@code <archivo.py> <Nombre o Clase.metodo>   codigo real de una funcion, clase o constante
  @@lines <archivo> <desde>-<hasta>              un rango de lineas
  @@grep <archivo> "<texto>" <n>                 n lineas desde la primera que contiene el texto
  @@img <archivo> <pie de imagen>                imagen incrustada
  > [!leccion] Titulo    (bloque destacado; tambien [!nota] y [!cuidado])
El codigo se lee del repositorio al generar: si el codigo cambia, el libro se actualiza al regenerarlo.
"""

from __future__ import annotations

import ast
import base64
import html
import re
from pathlib import Path

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer_for_filename

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CHAPTERS = sorted((HERE / "capitulos").glob("*.md"))
FORMATTER = HtmlFormatter(nowrap=True)


# ------------------------------------------------------------------ codigo real
def _source(path: str) -> list[str]:
    return (ROOT / path).read_text(encoding="utf-8").splitlines()


def code_symbol(path: str, symbol: str) -> tuple[str, int, int]:
    lines = _source(path)
    tree = ast.parse("\n".join(lines))
    parts = symbol.split(".")
    nodes = tree.body
    found = None
    for i, part in enumerate(parts):
        found = None
        for n in nodes:
            name = getattr(n, "name", None)
            if name is None and isinstance(n, (ast.Assign, ast.AnnAssign)):
                target = n.targets[0] if isinstance(n, ast.Assign) else n.target
                name = getattr(target, "id", None)
            if name == part:
                found = n
                break
        if found is None:
            raise SystemExit(f"No encontre {symbol} en {path}")
        nodes = getattr(found, "body", [])
    start = min([found.lineno] + [d.lineno for d in getattr(found, "decorator_list", [])])
    return "\n".join(lines[start - 1:found.end_lineno]), start, found.end_lineno


def code_lines(path: str, span: str) -> tuple[str, int, int]:
    a, b = (int(x) for x in span.split("-"))
    return "\n".join(_source(path)[a - 1:b]), a, b


def code_grep(path: str, text: str, n: int) -> tuple[str, int, int]:
    lines = _source(path)
    for i, line in enumerate(lines):
        if text in line:
            return "\n".join(lines[i:i + n]), i + 1, min(len(lines), i + n)
    raise SystemExit(f'No encontre "{text}" en {path}')


def code_block(code: str, path: str | None = None, start: int | None = None, end: int | None = None, lang: str | None = None) -> str:
    try:
        lexer = get_lexer_by_name(lang) if lang else guess_lexer_for_filename(path or "x.txt", code)
    except Exception:
        lexer = get_lexer_by_name("text")
    body = highlight(code.rstrip("\n"), lexer, FORMATTER)
    cap = ""
    if path:
        where = f" · líneas {start}–{end}" if start else ""
        cap = f'<figcaption><span class="file">{html.escape(path)}</span>{where}</figcaption>'
    return f'<figure class="code">{cap}<pre><code>{body}</code></pre></figure>'


# ------------------------------------------------------------------ markdown (subconjunto)
def inline(text: str) -> str:
    out = []
    for i, part in enumerate(re.split(r"(`[^`]+`)", text)):
        if i % 2:
            out.append("<code>" + html.escape(part[1:-1]) + "</code>")
            continue
        p = html.escape(part, quote=False)
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", p)
        p = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', p)
        out.append(p)
    return "".join(out)


def slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.U)
    s = s.translate(str.maketrans("áéíóúñü", "aeiounu"))
    s = re.sub(r"[\s_]+", "-", s).strip("-")[:60]
    return s if s[:1].isalpha() else "cap-" + s  # un id de HTML/CSS no debe empezar con un numero


def image(path: str, caption: str) -> str:
    data = base64.b64encode((ROOT / path).read_bytes()).decode()
    mime = "image/svg+xml" if path.endswith(".svg") else "image/png"
    return f'<figure class="shot"><img src="data:{mime};base64,{data}" alt="{html.escape(caption)}"><figcaption>{inline(caption)}</figcaption></figure>'


def render(md: str, toc: list[tuple[int, str, str]]) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            lang = s[3:].strip() or "text"
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            out.append(code_block("\n".join(buf), lang=lang))
            i = j + 1
            continue
        if s.startswith("@@code "):
            _, path, symbol = s.split(maxsplit=2)
            c = code_symbol(path, symbol)
            out.append(code_block(c[0], path=path, start=c[1], end=c[2]))
            i += 1
            continue
        if s.startswith("@@lines "):
            _, path, span = s.split()
            c = code_lines(path, span)
            out.append(code_block(c[0], path=path, start=c[1], end=c[2]))
            i += 1
            continue
        if s.startswith("@@grep "):
            m = re.match(r'@@grep (\S+) "(.+)" (\d+)$', s)
            c = code_grep(m.group(1), m.group(2), int(m.group(3)))
            out.append(code_block(c[0], path=m.group(1), start=c[1], end=c[2]))
            i += 1
            continue
        if s.startswith("@@img "):
            _, path, caption = s.split(maxsplit=2)
            out.append(image(path, caption))
            i += 1
            continue
        m = re.match(r"^(#{1,3}) (.+)$", s)
        if m:
            level, text = len(m.group(1)), m.group(2)
            anchor = slug(text)
            if level <= 2:
                toc.append((level, text, anchor))
            tag = {1: "h1", 2: "h2", 3: "h3"}[level]
            if level == 1:
                num = re.match(r"^(\d+|[A-Z])\s*·\s*(.+)$", text)
                inner = (f'<span class="ch-num">{num.group(1)}</span>{inline(num.group(2))}' if num else inline(text))
                out.append(f'<section class="chapter" id="{anchor}"><h1>{inner}</h1>')
            else:
                out.append(f'<{tag} id="{anchor}">{inline(text)}</{tag}>')
            i += 1
            continue
        if s.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            kind, title = "nota", None
            m2 = re.match(r"^\[!(leccion|nota|cuidado)\]\s*(.*)$", buf[0])
            if m2:
                kind, title = m2.group(1), m2.group(2)
                buf = buf[1:]
            label = {"leccion": "Lección aprendida", "nota": "Nota", "cuidado": "Cuidado"}[kind]
            paras, cur = [], []
            for piece in buf + [""]:
                if piece:
                    cur.append(piece)
                elif cur:
                    paras.append(" ".join(cur))
                    cur = []
            body = "".join(f"<p>{inline(p)}</p>" for p in paras)
            head = f'<p class="co-head"><span>{label}</span>{(" · " + inline(title)) if title else ""}</p>'
            out.append(f'<aside class="callout {kind}">{head}{body}</aside>')
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[2:]]
            t = "<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead>"
            t += "<tbody>" + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody>"
            out.append(f'<div class="table"><table>{t}</table></div>')
            continue
        if re.match(r"^(-|\d+\.) ", s):
            ordered = bool(re.match(r"^\d+\. ", s))
            items = []
            while i < len(lines) and re.match(r"^\s*(-|\d+\.) ", lines[i]):
                items.append(re.sub(r"^\s*(-|\d+\.) ", "", lines[i]))
                i += 1
                while i < len(lines) and lines[i].startswith("   ") and lines[i].strip() and not re.match(r"^\s*(-|\d+\.) ", lines[i]):
                    items[-1] += " " + lines[i].strip()
                    i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        buf = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|>|\||```|@@|-\s|\d+\.\s)", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")
    if out and out[0].startswith('<section class="chapter"'):
        out.append("</section>")
    return "\n".join(out)


# ------------------------------------------------------------------ pagina
CSS = (HERE / "estilo.css").read_text(encoding="utf-8")
HEAD = """<title>ARYA, de cero a agente</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=JetBrains+Mono:wght@400;600&display=swap">
<style>""" + CSS + "</style>"


def build() -> None:
    toc: list[tuple[int, str, str]] = []
    chapters = [render(p.read_text(encoding="utf-8"), toc) for p in CHAPTERS]
    nav = []
    for level, text, anchor in toc:
        label = re.sub(r"^(\d+|[A-Z])\s*·\s*", r"<b>\1</b> ", inline(text)) if level == 1 else inline(text)
        nav.append(f'<li class="l{level}"><a href="#{anchor}">{label}</a></li>')
    body = f"""<div class="book">
<nav class="toc" aria-label="Índice"><p class="toc-title">Índice</p><ol>{''.join(nav)}</ol></nav>
<main class="pages">{''.join(chapters)}
<footer class="colophon">Generado desde el repositorio con <code>docs/libro/build.py</code>. Los fragmentos de código son copias exactas de los archivos indicados.</footer>
</main></div>"""
    (HERE / "libro-arya.page.html").write_text(HEAD + "\n" + body, encoding="utf-8")
    full = f'<!doctype html>\n<html lang="es">\n<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n{HEAD}\n</head>\n<body>\n{body}\n</body>\n</html>\n'
    (HERE / "libro-arya.html").write_text(full, encoding="utf-8")
    print(f"{len(CHAPTERS)} capítulos · {len(toc)} entradas de índice · {len(full) // 1024} KB")


if __name__ == "__main__":
    build()
