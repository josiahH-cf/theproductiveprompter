"""Escaped, readable views of immutable model experiment records."""
from __future__ import annotations
import html
import json
from pathlib import Path
import re

SITE = "https://theproductiveprompter.com"
PUBLIC = "docs/model-release-experiment"


def inline(text):
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return re.sub(chr(96) + "([^" + chr(96) + "]+)" + chr(96), r"<code>\1</code>", escaped)


def response_html(text):
    """Render a safe Markdown subset; preserve the downloaded source exactly."""
    output, paragraph, fence, code = [], [], None, []
    def flush():
        if paragraph:
            output.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()
    for line in text.splitlines():
        if line.strip().startswith(chr(96) * 3):
            flush()
            if fence is None:
                fence, code = line.strip()[3:], []
            else:
                label = "Receipt" if fence.strip() == "json" else "Code"
                output.append(f'<details class="run-code"><summary>{label}</summary><pre><code>' +
                              html.escape("\n".join(code)) + "</code></pre></details>")
                fence = None
            continue
        if fence is not None:
            code.append(line)
        elif not line.strip():
            flush()
        elif re.match(r"^#{1,6}\s", line):
            flush()
            output.append("<h2>" + inline(re.sub(r"^#{1,6}\s+", "", line)) + "</h2>")
        elif line.startswith("> "):
            flush()
            output.append("<blockquote><p>" + inline(line[2:]) + "</p></blockquote>")
        else:
            paragraph.append(line)
    flush()
    if fence is not None:
        output.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
    return "\n".join(output)


def label(record, evidence=None):
    variant = record.get("variant") or {}
    settings = (evidence or {}).get("settings", {})
    effort = variant.get("effort") or settings.get("effort", "medium")
    verbosity = variant.get("verbosity") or settings.get("verbosity", "default")
    return f"{effort.capitalize()} thinking · {verbosity} verbosity"


def run_path(record):
    return f"{PUBLIC}/runs/{record['key']}.html"


def settings_order(record):
    variant = record.get("variant") or {"id":"baseline"}
    identity = variant["id"]
    if identity == "baseline":
        return (0,0,"")
    if identity.startswith("effort-") and "-verbosity-" not in identity:
        levels = ["none","low","medium","high","xhigh","max","ultra"]
        return (1, levels.index(variant["effort"]) if variant["effort"] in levels else 99, identity)
    return (2, ["low","medium","high"].index(variant["verbosity"]) if variant["verbosity"] in ["low","medium","high"] else 99, identity)


def index_fragment(m, registry, pack, base=SITE, article_url=None):
    lanes = []
    for provider, name in (("claude", "Claude"), ("codex", "Codex")):
        cards = []
        for model in sorted((x for x in registry["models"] if x["provider"] == provider), key=m.chronological):
            records = [r for r in registry["records"] if r["provider"] == provider and r["model"] == model["model"]]
            groups = {}
            for r in records:
                key = m.trial_key(provider, model["model"], r.get("variant"))
                if key not in groups or groups[key]["status"] != "response captured":
                    groups[key] = r
            links = []
            for r in sorted(groups.values(),key=settings_order):
                path = m.safe_path(pack, f"records/{r['key']}/evidence.json")
                evidence = m.load(path) if path.exists() else {}
                passed = evidence.get("validation", {}).get("receipt_passed")
                status = ("Receipt passed" if passed else "Receipt failed") if r["status"] == "response captured" else r["status"].capitalize()
                href = f"{base.rstrip('/')}/{run_path(r)}"
                links.append(f'<li><a href="{html.escape(href, quote=True)}">{html.escape(label(r,evidence))}'
                             f'<span class="run-status">{html.escape(status)}</span></a></li>')
            date = (f"Released {model['release_date']}" if model.get("release_date") else
                    f"First seen {model['first_seen'][:10]}; release date unavailable")
            cards.append(f'<article class="model-card"><h3>{html.escape(model["display_name"])}</h3>'
                         f'<p class="model-date">{html.escape(date)}</p><ul class="run-links">'
                         f'{"".join(links) or "<li>No response captured</li>"}</ul></article>')
        if provider == "codex":
            cards.insert(0, '<article class="model-card"><h3>GPT-5.3-Codex-Spark</h3>'
                         '<p class="model-date">Retired 2026-09-14</p>'
                         '<a href="https://learn.chatgpt.com/docs/models">Unavailable for new runs</a></article>')
        lanes.append(f'<section class="{provider}-lane"><h2>{name}</h2><div class="release-list">{"".join(cards)}</div></section>')
    return (pack / "preview-template.html").read_text(encoding="utf-8").replace("<!-- MODEL_LANES -->", "".join(lanes))


def standalone(title, body, css, canonical):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)} | The Productive Prompter</title>'
            f'<link rel="canonical" href="{html.escape(canonical, quote=True)}"><style>{css}</style></head><body>'
            '<nav class="site-nav"><a href="/">The Productive Prompter</a><a href="/docs/blog.html">All writing</a></nav>'
            f'<main>{body}</main></body></html>')


RUN_CSS = """
*{box-sizing:border-box}body{margin:0;background:#0a192f;color:#e6f1ff;font:17px/1.75 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
a{color:#64ffda;overflow-wrap:anywhere}.site-nav{display:flex;justify-content:space-between;gap:20px;padding:24px;flex-wrap:wrap}
main{max-width:800px;margin:auto;padding:24px 28px 72px}h1{font-size:32px;line-height:1.25;font-weight:500;overflow-wrap:anywhere}
h2{font-size:24px;font-weight:500;line-height:1.4;margin-top:30px}p{margin:0 0 20px}.run-meta{color:#ccd6f6;font-size:15px}
.run-code{margin:24px 0;padding:16px;background:#172a45;border-radius:8px}summary{min-height:32px;font-weight:500}
pre{font:14px/1.6 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}code{overflow-wrap:anywhere}
blockquote{margin:20px 0;padding-left:18px;border-left:2px solid #8892b0}a:focus-visible,summary:focus-visible{outline:2px solid #64ffda;outline-offset:4px}
@media(max-width:480px){main{padding:16px 20px 48px}h1{font-size:26px}.site-nav{padding:20px;font-size:15px}summary{min-height:44px}}
"""


def site_bundle(m, registry, pack, article_url):
    fragment = index_fragment(m, registry, pack, base="")
    css = re.search(r"<style>(.*?)</style>", fragment, re.S).group(1)
    body = re.sub(r"<style>.*?</style>", "", fragment, flags=re.S)
    body += f'<p><a href="{html.escape(article_url,quote=True)}">Read the experiment article</a></p>'
    files = {f"{PUBLIC}/index.html": standalone("The Model Release Experiment", body, RUN_CSS + css,
                                            SITE + "/" + PUBLIC + "/index.html").encode()}
    files[f"{PUBLIC}/prompt.txt"] = m.freeze_prompt(pack)
    for r in registry["records"]:
        evidence = m.load(m.safe_path(pack, f"records/{r['key']}/evidence.json"))
        raw = m.safe_path(pack, f"records/{r['key']}/response.txt").read_bytes()
        actual = evidence.get("actual_model") or "Not exposed by client"
        checks = evidence.get("validation", {})
        result = ("passed" if checks.get("receipt_passed") else "failed") if r["status"] == "response captured" else "not scored"
        elapsed = evidence.get("elapsed_seconds")
        duration = f"{elapsed:g} seconds" if isinstance(elapsed, (int, float)) else "Time not reported"
        body = (f'<a href="/{PUBLIC}/index.html">← All model runs</a><h1>{html.escape(r["model"])}</h1>'
                f'<p class="run-meta">{html.escape(label(r,evidence))}<br>{html.escape(duration)} · Receipt {result}<br>'
                f'Run {html.escape(r.get("tested_at","unreported"))}<br>Responder: {html.escape(actual)}</p>'
                '<section aria-label="Original model response">' + response_html(raw.decode("utf-8", errors="replace")) + '</section>'
                f'<details class="run-code"><summary>Settings, checks and reported usage</summary><pre><code>{html.escape(json.dumps(evidence,indent=2))}</code></pre></details>'
                f'<p><a href="{r["key"]}.txt" download>Exact original response</a> · '
                f'<a href="{r["key"]}.json">Evidence</a> · <a href="../prompt.txt">Frozen prompt</a></p>')
        files[run_path(r)] = standalone(r["model"] + " · " + label(r,evidence), body, RUN_CSS, SITE + "/" + run_path(r)).encode()
        files[f"{PUBLIC}/runs/{r['key']}.txt"] = raw
        files[f"{PUBLIC}/runs/{r['key']}.json"] = m.safe_path(pack,f"records/{r['key']}/evidence.json").read_bytes()
    return files
