from __future__ import annotations

import html
import re
from pathlib import Path


DOCS_DIR = Path(__file__).resolve().parent
SOURCE_MD = DOCS_DIR / "methodology.md"
OUTPUT_HTML = DOCS_DIR / "methodology.html"
REPO_ROOT = "/E:/Barton/repositories/motel-platform/"
REPO_URL = "https://github.com/BartonChenTW/motel-platform"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
    return slug.strip("-") or "section"


def rewrite_repo_link(url: str) -> str:
    if not url.startswith(REPO_ROOT):
        return url
    relative = url[len(REPO_ROOT) :].replace("\\", "/")
    is_file = bool(re.search(r"\.[a-z0-9]+$", relative, flags=re.I))
    kind = "blob" if is_file else "tree"
    return f"{REPO_URL}/{kind}/main/{relative}"


def render_inline(text: str) -> str:
    placeholders: list[str] = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"@@PLACEHOLDER{len(placeholders) - 1}@@"

    text = re.sub(
        r"`([^`]+)`",
        lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"),
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: stash(
            f'<a href="{html.escape(rewrite_repo_link(m.group(2)), quote=True)}">'
            f"{html.escape(m.group(1))}</a>"
        ),
        text,
    )
    rendered = html.escape(text)
    for index, value in enumerate(placeholders):
        rendered = rendered.replace(f"@@PLACEHOLDER{index}@@", value)
    return rendered


def split_table_row(line: str) -> list[str]:
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def render_table(lines: list[str], start: int) -> tuple[str, int]:
    header = split_table_row(lines[start])
    rows: list[list[str]] = []
    index = start + 2
    while index < len(lines):
        line = lines[index]
        if not line.strip().startswith("|"):
            break
        rows.append(split_table_row(line))
        index += 1

    thead = "".join(f"<th>{render_inline(cell)}</th>" for cell in header)
    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>" + "".join(f"<td>{render_inline(cell)}</td>" for cell in row) + "</tr>"
        )
    table_html = (
        "<table>"
        f"<thead><tr>{thead}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )
    return table_html, index


def render_markdown(markdown: str) -> tuple[str, list[tuple[int, str, str]]]:
    lines = markdown.splitlines()
    blocks: list[str] = []
    toc: list[tuple[int, str, str]] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            language = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code = "\n".join(code_lines)
            class_attr = f' class="language-{html.escape(language)}"' if language else ""
            blocks.append(
                f"<pre><code{class_attr}>{html.escape(code)}</code></pre>"
            )
            i += 1
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped[level:].strip()
            heading_id = slugify(heading_text)
            if level in (2, 3):
                toc.append((level, heading_text, heading_id))
            blocks.append(
                f"<h{level} id=\"{heading_id}\">{render_inline(heading_text)}</h{level}>"
            )
            i += 1
            continue

        if (
            stripped.startswith("|")
            and i + 1 < len(lines)
            and lines[i + 1].strip().startswith("|")
            and is_table_separator(lines[i + 1])
        ):
            table_html, i = render_table(lines, i)
            blocks.append(table_html)
            continue

        if re.match(r"^[-*] ", stripped):
            items = []
            while i < len(lines) and re.match(r"^[-*] ", lines[i].strip()):
                items.append(lines[i].strip()[2:].strip())
                i += 1
            blocks.append(
                "<ul>"
                + "".join(f"<li>{render_inline(item)}</li>" for item in items)
                + "</ul>"
            )
            continue

        if re.match(r"^\d+\. ", stripped):
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i].strip()):
                items.append(re.sub(r"^\d+\. ", "", lines[i].strip()))
                i += 1
            blocks.append(
                "<ol>"
                + "".join(f"<li>{render_inline(item)}</li>" for item in items)
                + "</ol>"
            )
            continue

        paragraph_lines = [stripped]
        i += 1
        while i < len(lines):
            next_line = lines[i].strip()
            if not next_line:
                i += 1
                break
            if (
                next_line.startswith("#")
                or next_line.startswith("```")
                or next_line.startswith("|")
                or re.match(r"^[-*] ", next_line)
                or re.match(r"^\d+\. ", next_line)
            ):
                break
            paragraph_lines.append(next_line)
            i += 1
        blocks.append(f"<p>{render_inline(' '.join(paragraph_lines))}</p>")

    return "\n".join(blocks), toc


def build_html(body_html: str, toc: list[tuple[int, str, str]]) -> str:
    toc_links = ['<a href="#top">Top</a>']
    for level, label, anchor in toc:
        class_attr = ' class="toc-subitem"' if level == 3 else ""
        toc_links.append(
            f'<a href="#{anchor}"{class_attr}>{html.escape(label)}</a>'
        )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>MOTEL Methodology</title>
    <meta
      name="description"
      content="Readable web version of the MOTEL methodology documentation."
    />
    <link rel="stylesheet" href="style.css" />
  </head>
  <body>
    <div class="docs-shell">
      <aside class="sidebar" aria-label="Methodology navigation">
        <div class="sidebar-inner">
          <a class="brand" href="index.html#overview">
            <span class="brand-title">MOTEL Platform</span>
            <span class="brand-subtitle">Methodology</span>
          </a>

          <nav class="toc" id="methodology-toc">
            {"".join(toc_links)}
          </nav>

          <div class="sidebar-actions">
            <a href="index.html">Back to homepage</a>
            <a href="workflow.mmd">Workflow source</a>
            <a href="methodology.md">Markdown source</a>
          </div>
        </div>
      </aside>

      <main class="content">
        <header class="doc-hero" id="top">
          <p class="kicker">MOTEL Platform</p>
          <h1>MOTEL Methodology</h1>
          <p class="subtitle">
            A browser-friendly view of the methodology document, with
            <code>docs/methodology.md</code> kept as the source of truth.
          </p>
          <div class="actions">
            <a class="btn primary" href="index.html">Back to homepage</a>
            <a class="btn" href="methodology.md">View Markdown source</a>
          </div>
        </header>

        <article class="doc-section markdown-body" id="methodology-body">
{body_html}
        </article>
      </main>
    </div>
  </body>
</html>
"""


def main() -> None:
    markdown = SOURCE_MD.read_text(encoding="utf-8")
    body_html, toc = render_markdown(markdown)
    document = build_html(body_html, toc)
    OUTPUT_HTML.write_text(document, encoding="utf-8")
    print(f"Rendered {SOURCE_MD.name} -> {OUTPUT_HTML.name}")


if __name__ == "__main__":
    main()
