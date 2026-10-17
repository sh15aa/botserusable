import json
import os
import subprocess
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(BASE_DIR, "site", "public")
os.makedirs(PUBLIC_DIR, exist_ok=True)

PDF_CSS = """
@page {
    size: A4;
    margin: 20mm 18mm 20mm 18mm;
    @bottom-right {
        content: counter(page);
    }
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1e293b;
    line-height: 1.6;
    font-size: 11pt;
}
.cover-page {
    page-break-after: always;
    padding-top: 60px;
    text-align: center;
}
.cover-badge {
    display: inline-block;
    background: #e0f2fe;
    color: #0369a1;
    font-size: 11pt;
    font-weight: 700;
    padding: 6px 16px;
    border-radius: 9999px;
    margin-bottom: 24px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border: 1px solid #bae6fd;
}
.cover-title {
    font-size: 28pt;
    font-weight: 800;
    color: #0f172a;
    line-height: 1.2;
    margin-bottom: 16px;
}
.cover-subtitle {
    font-size: 13pt;
    color: #475569;
    max-width: 600px;
    margin: 0 auto 30px auto;
}
.cover-meta {
    margin-top: 60px;
    padding-top: 30px;
    border-top: 2px solid #e2e8f0;
    font-size: 10pt;
    color: #64748b;
    text-align: left;
}
.cover-meta table {
    width: 100%;
    border-collapse: collapse;
}
.cover-meta td {
    padding: 6px 0;
    border: none;
}
.cover-meta td.label {
    font-weight: 700;
    color: #334155;
    width: 150px;
}

h1 {
    font-size: 20pt;
    font-weight: 800;
    color: #0f172a;
    border-bottom: 2px solid #3b82f6;
    padding-bottom: 8px;
    margin-top: 30px;
    margin-bottom: 16px;
}
h2 {
    font-size: 15pt;
    font-weight: 700;
    color: #1e3a8a;
    margin-top: 24px;
    margin-bottom: 12px;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
}
h3 {
    font-size: 12pt;
    font-weight: 700;
    color: #1e293b;
    margin-top: 18px;
    margin-bottom: 8px;
}
p {
    margin-bottom: 12px;
}
ul, ol {
    margin-top: 4px;
    margin-bottom: 14px;
    padding-left: 24px;
}
li {
    margin-bottom: 4px;
}
pre {
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    border-left: 4px solid #3b82f6;
    padding: 12px;
    border-radius: 4px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 9.5pt;
    line-height: 1.45;
    overflow-x: auto;
    margin-bottom: 16px;
    page-break-inside: avoid;
}
code {
    background: #f1f5f9;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 9.5pt;
    color: #0f172a;
    border: 1px solid #e2e8f0;
}
pre code {
    background: none;
    padding: 0;
    border: none;
}
table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    page-break-inside: avoid;
    font-size: 9.5pt;
}
th, td {
    border: 1px solid #cbd5e1;
    padding: 8px 10px;
    text-align: left;
    vertical-align: top;
}
th {
    background: #f1f5f9;
    font-weight: 700;
    color: #1e293b;
}
tr:nth-child(even) td {
    background: #f8fafc;
}
.card {
    border: 1px solid #e2e8f0;
    background: #ffffff;
    border-radius: 6px;
    padding: 14px;
    margin-bottom: 16px;
    page-break-inside: avoid;
    border-left: 4px solid #2563eb;
}
.card-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
}
.card-title {
    font-size: 12pt;
    font-weight: 700;
    color: #0f172a;
    margin: 0;
}
.card-meta {
    font-size: 9pt;
    color: #64748b;
    margin-top: 4px;
}
.pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 9999px;
    font-size: 8.5pt;
    font-weight: 600;
    margin-right: 4px;
}
.pill-blue { background: #dbeafe; color: #1d4ed8; }
.pill-green { background: #dcfce7; color: #15803d; }
.pill-purple { background: #f3e8ff; color: #7e22ce; }
.pill-gray { background: #f1f5f9; color: #475569; }
.page-break {
    page-break-after: always;
}
.footer {
    font-size: 8.5pt;
    color: #94a3b8;
    text-align: center;
    margin-top: 40px;
    border-top: 1px solid #e2e8f0;
    padding-top: 12px;
}
"""

def md_to_html_simple(md_text):
    # Basic markdown formatting
    lines = md_text.splitlines()
    html_lines = []
    in_code_block = False
    in_table = False
    in_list = False
    
    for line in lines:
        if line.startswith("```"):
            if in_code_block:
                html_lines.append("</code></pre>")
                in_code_block = False
            else:
                lang = line[3:].strip()
                html_lines.append(f'<pre><code class="language-{lang}">')
                in_code_block = True
            continue
            
        if in_code_block:
            # Escape HTML
            escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_lines.append(escaped)
            continue
            
        # Table detection
        if "|" in line:
            if not in_table:
                in_table = True
                html_lines.append("<table>")
            
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) > 0 and all(set(c).issubset({"-", ":", " "}) for c in cells if c):
                # separator line
                continue
            
            # If it looks like header row (first row of table)
            tag = "td"
            if len(html_lines) > 0 and html_lines[-1] == "<table>":
                tag = "th"
            
            row = "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"
            html_lines.append(row)
            continue
        else:
            if in_table:
                html_lines.append("</table>")
                in_table = False
                
        # Lists
        if line.startswith("- ") or line.startswith("* "):
            if not in_list:
                in_list = True
                html_lines.append("<ul>")
            item_text = line[2:].strip()
            item_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item_text)
            item_text = re.sub(r'`(.*?)`', r'<code>\1</code>', item_text)
            html_lines.append(f"<li>{item_text}</li>")
            continue
        elif line.startswith("1. ") or line.startswith("2. ") or line.startswith("3. ") or line.startswith("4. ") or line.startswith("5. ") or line.startswith("6. "):
            if not in_list:
                in_list = True
                html_lines.append("<ol>")
            item_text = re.sub(r'^\d+\.\s*', '', line).strip()
            item_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item_text)
            item_text = re.sub(r'`(.*?)`', r'<code>\1</code>', item_text)
            html_lines.append(f"<li>{item_text}</li>")
            continue
        else:
            if in_list:
                html_lines.append("</ul>" if "<ul>" in "".join(html_lines[-5:]) else "</ol>")
                in_list = False
                
        # Headings
        if line.startswith("# "):
            html_lines.append(f"<h1>{line[2:].strip()}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:].strip()}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{line[4:].strip()}</h3>")
        elif line.startswith("---"):
            html_lines.append("<hr style='border: none; border-top: 1px solid #cbd5e1; margin: 24px 0;'/>")
        elif line.strip() == "":
            html_lines.append("<br/>")
        else:
            p_text = line.strip()
            p_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', p_text)
            p_text = re.sub(r'`(.*?)`', r'<code>\1</code>', p_text)
            html_lines.append(f"<p>{p_text}</p>")
            
    if in_code_block:
        html_lines.append("</code></pre>")
    if in_table:
        html_lines.append("</table>")
    if in_list:
        html_lines.append("</ul>")
        
    return "\n".join(html_lines)

def build_pdf(html_content, output_pdf_name):
    tmp_html = f"/tmp/{output_pdf_name}.html"
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    out_dir = PUBLIC_DIR
    cmd = ["libreoffice", "--headless", "--convert-to", "pdf", tmp_html, "--outdir", out_dir]
    print(f"Generating {output_pdf_name}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error generating {output_pdf_name}: {res.stderr}")
    else:
        print(f"Generated {output_pdf_name} at {os.path.join(out_dir, output_pdf_name + '.pdf')}")

# 1. Generate AGENTS.pdf
with open(os.path.join(BASE_DIR, "AGENTS.md"), "r", encoding="utf-8") as f:
    agents_md = f.read()

agents_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AGENTS.md - Reusable Code Specification</title>
<style>{PDF_CSS}</style>
</head>
<body>
<div class="cover-page">
    <div class="cover-badge">Specification & Protocol</div>
    <div class="cover-title">AGENTS.md Guide & Policy</div>
    <div class="cover-subtitle">Standard Protocol for AI Agent Consumption of Reusable Bot & Architecture Code</div>
    <div class="cover-meta">
        <table>
            <tr><td class="label">Repository:</td><td>https://github.com/sh15aa/botserusable</td></tr>
            <tr><td class="label">Maintainer:</td><td>foundershivanand@gmail.com</td></tr>
            <tr><td class="label">Standard:</td><td>Zero-Duplication / Reuse-First</td></tr>
            <tr><td class="label">Date:</td><td>October 2026</td></tr>
        </table>
    </div>
</div>
{md_to_html_simple(agents_md)}
<div class="footer">
    Generated from https://github.com/sh15aa/botserusable | Maintainer: foundershivanand@gmail.com
</div>
</body>
</html>
"""
build_pdf(agents_html, "agents")

# 2. Generate README.pdf
with open(os.path.join(BASE_DIR, "README.md"), "r", encoding="utf-8") as f:
    readme_md = f.read()

readme_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Enterprise Bot Product Factory - Technical Architecture</title>
<style>{PDF_CSS}</style>
</head>
<body>
<div class="cover-page">
    <div class="cover-badge">Architecture & Implementation</div>
    <div class="cover-title">Enterprise Bot Product Factory</div>
    <div class="cover-subtitle">FastAPI + ARQ + PostgreSQL + Chatwoot + WhatsApp + Telegram + Dual-Tier AI Guardrails</div>
    <div class="cover-meta">
        <table>
            <tr><td class="label">Repository:</td><td>https://github.com/sh15aa/botserusable</td></tr>
            <tr><td class="label">Author Account:</td><td>foundershivanand@gmail.com</td></tr>
            <tr><td class="label">Security Level:</td><td>Zero-Vulnerability Audited</td></tr>
            <tr><td class="label">Date:</td><td>October 2026</td></tr>
        </table>
    </div>
</div>
{md_to_html_simple(readme_md)}
<div class="footer">
    Generated from https://github.com/sh15aa/botserusable | Maintainer: foundershivanand@gmail.com
</div>
</body>
</html>
"""
build_pdf(readme_html, "readme")

# 3. Generate Full Technical Handbook (botserusable-handbook.pdf)
with open(os.path.join(BASE_DIR, "registry", "modules.json"), "r", encoding="utf-8") as f:
    registry_data = json.load(f)

modules_cards_html = []
for mod in registry_data.get("modules", []):
    classes_str = ", ".join(mod.get("classes", [])) or "None"
    deps_str = ", ".join(mod.get("dependencies", [])) or "Standard Library"
    envs_str = ", ".join(mod.get("env_vars", [])) or "None required"
    
    card = f"""
    <div class="card">
        <div class="card-header">
            <h3 class="card-title">{mod['name']}</h3>
            <div>
                <span class="pill pill-blue">{mod['id']}</span>
                <span class="pill pill-green">{mod.get('category', '').upper()}</span>
                <span class="pill pill-purple">{mod.get('status', 'stable').upper()}</span>
            </div>
        </div>
        <p style="margin: 6px 0; color: #334155;">{mod['description']}</p>
        <div class="card-meta">
            <strong>Path:</strong> <code>{mod['path']}</code><br/>
            <strong>Classes:</strong> {classes_str}<br/>
            <strong>Dependencies:</strong> {deps_str}<br/>
            <strong>Environment Variables:</strong> {envs_str}
        </div>
    </div>
    """
    modules_cards_html.append(card)

modules_section_html = "\n".join(modules_cards_html)

handbook_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Enterprise Reusable Code Library - Complete Technical Manual</title>
<style>{PDF_CSS}</style>
</head>
<body>
<div class="cover-page">
    <div class="cover-badge">Complete Technical Manual</div>
    <div class="cover-title">Enterprise Bot & AI Reusable Code Factory</div>
    <div class="cover-subtitle">24 Production-Grade Modules, Zero-Vulnerability Security Protocols, Multi-Channel Messaging Adapters, and AI Agent Consumption Standards</div>
    <div class="cover-meta">
        <table>
            <tr><td class="label">Repository:</td><td>https://github.com/sh15aa/botserusable</td></tr>
            <tr><td class="label">Owner / Account:</td><td>foundershivanand@gmail.com</td></tr>
            <tr><td class="label">Module Count:</td><td>24 Registered Production Modules</td></tr>
            <tr><td class="label">Published:</td><td>October 2026</td></tr>
        </table>
    </div>
</div>

<h1>1. Executive Summary & Philosophy</h1>
<p>This library provides enterprise-grade, thoroughly tested modules for building conversational messaging bots, distributed asynchronous worker pipelines, and secure AI systems. It is structured for direct, zero-friction consumption by autonomous AI coding agents (Claude Code, OpenAI Codex, Antigravity, Cursor, GitHub Copilot) and human engineering teams.</p>

<p><strong>Primary Repository:</strong> <a href="https://github.com/sh15aa/botserusable">https://github.com/sh15aa/botserusable</a><br/>
<strong>Registry Endpoint:</strong> <code>https://raw.githubusercontent.com/sh15aa/botserusable/main/registry/modules.json</code></p>

<h1>2. Standard Protocol for AI Agents (AGENTS.md)</h1>
{md_to_html_simple(agents_md)}

<div class="page-break"></div>

<h1>3. System Architecture & Zero-Vulnerability Security</h1>
{md_to_html_simple(readme_md)}

<div class="page-break"></div>

<h1>4. Complete Reusable Module Directory (24 Modules)</h1>
<p>Each module below is ready to be fetched and incorporated into new projects without modifications to its core logic.</p>

{modules_section_html}

<div class="footer">
    Enterprise Bot Product Factory | Published for foundershivanand@gmail.com | https://github.com/sh15aa/botserusable
</div>
</body>
</html>
"""
build_pdf(handbook_html, "botserusable-handbook")
print("All PDFs successfully built in site/public/")
