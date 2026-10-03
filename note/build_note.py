"""Build the quant note (PDF, <= 5 pages + references/appendix) from results/summary.json.

Every number in the note is read from run_all.py output, so the note cannot disagree with the code.
Prose lives in note/sections/*.md (Markdown with {placeholders} filled from the results).

Usage: python note/build_note.py   ->  note/PokerFace_quant_note.html and .pdf (headless Chrome)
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
SEC = ROOT / "note" / "sections"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: Letter; margin: 0.75in 0.8in; }
body { font-family: 'Charter', 'Georgia', serif; font-size: 11pt; line-height: 1.32; color: #111; }
h1 { font-size: 17pt; margin: 0 0 2pt; } .sub { color:#444; font-size: 10.5pt; margin-bottom: 8pt; }
h2 { font-size: 12.5pt; margin: 10pt 0 3pt; border-bottom: 0.6pt solid #999; padding-bottom: 1pt; }
p { margin: 3pt 0 5pt; text-align: justify; } ul { margin: 2pt 0 5pt 16pt; padding: 0; } li { margin: 1pt 0; }
table { border-collapse: collapse; font-size: 10pt; margin: 4pt 0 6pt; width: 100%; }
th, td { border-bottom: 0.4pt solid #bbb; padding: 1.5pt 4pt; text-align: right; }
th:first-child, td:first-child { text-align: left; } thead th { border-bottom: 0.8pt solid #333; }
figure { margin: 4pt 0 6pt; text-align: center; } figure img { max-width: 100%; max-height: 2.5in; }
figcaption { font-size: 9.5pt; color: #333; text-align: left; } .two { display: flex; gap: 8pt; }
.two figure { flex: 1; } .refs p { font-size: 9.5pt; text-align: left; margin: 1pt 0; }
.pb { page-break-before: always; } code { font-size: 9.5pt; }
"""


def _fmt(v, kind="f2"):
    if v is None:
        return "n/a"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v != v:
        return "n/a"
    return {"pct": f"{100 * v:.1f}%", "pct2": f"{100 * v:.2f}%", "f2": f"{v:.2f}", "f3": f"{v:.3f}",
            "int": f"{int(round(v)):,}", "bps": f"{1e4 * v:.0f} bps", "musd": f"${v / 1e6:,.0f}M"}[kind]


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out


def fill(text: str, vals: dict) -> str:
    """{key|fmt} -> formatted value from the flattened results."""
    def rep(m):
        key, _, kind = m.group(1).partition("|")
        if key not in vals:
            return f"<b style='color:#c00'>[{key}?]</b>"
        return _fmt(vals[key], kind or "f2")
    return re.sub(r"\{([a-zA-Z0-9_.\-]+(?:\|[a-z0-9]+)?)\}", rep, text)


def md(text: str) -> str:
    """Tiny Markdown subset: ## headings, paragraphs, - bullets, **bold**, *italic*, tables, ![cap](fig.png)."""
    html, lines, i = [], text.strip().splitlines(), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("## "):
            html.append(f"<h2>{l[3:]}</h2>")
        elif l.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{lines[i][2:]}</li>")
                i += 1
            html.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif l.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            head = "".join(f"<th>{c}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows[1:])
            html.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            continue
        elif l.startswith("!["):
            m = re.match(r"!\[(.*)\]\((.*)\)", l)
            p = RES / "figures" / m.group(2)
            if p.exists():
                b64 = base64.b64encode(p.read_bytes()).decode()
                html.append(f"<figure><img src='data:image/png;base64,{b64}'/><figcaption>{m.group(1)}</figcaption></figure>")
        elif l.strip() == "<pagebreak>":
            html.append("<div class='pb'></div>")
        elif l.strip():
            para = [l]
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith(("## ", "- ", "|", "![", "<")):
                i += 1
                para.append(lines[i])
            html.append(f"<p>{' '.join(para)}</p>")
        i += 1
    out = "\n".join(html)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    return re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", out)


def main() -> None:
    vals = flatten(json.loads((RES / "summary.json").read_text()))
    parts = []
    def tables(text: str) -> str:
        if "{{STRESS_TABLE}}" in text and (RES / "stress_windows.csv").exists():
            import pandas as pd
            st = pd.read_csv(RES / "stress_windows.csv")
            rows = ["| window | dates | strategy | SPY | strategy max DD |", "|---|---|---|---|---|"]
            rows += [f"| {r.window} | {r.start} to {r.end} | {100*r.strategy:.1f}% | {100*r.spy:.1f}% | {100*r.strategy_max_dd:.1f}% |"
                     for r in st.itertuples()]
            text = text.replace("{{STRESS_TABLE}}", "\n".join(rows))
        return text

    for p in sorted(SEC.glob("*.md")):
        parts.append(md(fill(tables(p.read_text()), vals)))
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(parts)}</body></html>"
    out_html = ROOT / "note" / "PokerFace_quant_note.html"
    out_html.write_text(html)
    pdf = ROOT / "note" / "PokerFace_quant_note.pdf"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", out_html.as_uri()], check=True, capture_output=True)
    # page-limit check: render the main body alone (sections before 90_references) and count pages
    body = [md(fill(q.read_text(), vals)) for q in sorted(SEC.glob("*.md")) if q.name < "90"]
    tmp = ROOT / "note" / ".body_only.html"
    tmp.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(body)}</body></html>")
    bpdf = ROOT / "note" / ".body_only.pdf"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={bpdf}",
                    tmp.as_uri()], check=True, capture_output=True)
    n_body = len(re.findall(rb"/Type\s*/Page[^s]", bpdf.read_bytes()))
    n_all = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
    print(f"main body: {n_body} pages (limit 5) | full PDF incl. references + appendix: {n_all} pages")
    missing = re.findall(r"\[([a-zA-Z0-9_.\-]+)\?\]", html)
    print("wrote", pdf, "| unresolved placeholders:", sorted(set(missing)) or "none")


if __name__ == "__main__":
    main()
