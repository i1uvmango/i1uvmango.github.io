#!/usr/bin/env python3
"""로컬 미리보기 빌더 — GitHub Pages(Jekyll) 결과를 근사해서 _site/ 에 렌더.
실제 배포는 Jekyll이 하며, 이 스크립트는 검수용이다."""
import os, re, glob, shutil, yaml, markdown

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, '_site')
cfg = yaml.safe_load(open(os.path.join(ROOT, '_config.yml'), encoding='utf-8'))
CATS = cfg['project_cats']

def split_fm(path):
    t = open(path, encoding='utf-8').read()
    m = re.match(r'^---\n(.*?)\n---\n?(.*)$', t, re.S)
    return yaml.safe_load(m.group(1)) or {}, m.group(2)

def nav():
    links = ''.join(f'<a href="/#{c["key"]}">{c["name"]}</a>\n      ' for c in CATS)
    return f'''<nav>
  <div class="nav-inner">
    <a class="brand" href="/">MK — 정만교</a>
    <div class="nav-links">
      {links}<a href="https://github.com/{cfg["github_username"]}">GitHub ↗</a>
    </div>
  </div>
</nav>'''

def shell(title, body, desc):
    return f'''<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title><meta name="description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/css/style.css"></head><body>
{nav()}
{body}
<footer><div class="foot-inner">
<span>© 2026 정만교 (MK) — Kwangwoon Univ. · Deep Imaging &amp; Graphics Lab</span>
<span><a href="https://github.com/{cfg["github_username"]}">github.com/{cfg["github_username"]}</a> · <a href="mailto:{cfg["email"]}">{cfg["email"]}</a></span>
</div></footer></body></html>'''

# ---- collect projects
projects = []
for f in sorted(glob.glob(os.path.join(ROOT, '_projects', '*.md'))):
    fm, body = split_fm(f)
    fm['_body'] = body
    fm['_url'] = '/projects/%s/' % os.path.splitext(os.path.basename(f))[0]
    projects.append(fm)

def media(p, key_v, key_i, aria):
    if p.get(key_v):
        srcs = ''.join(f'<source src="{s["src"]}" type="{s["type"]}">' for s in p[key_v])
        return (f'<video autoplay muted loop playsinline preload="metadata" poster="{p[key_i]}" '
                f'aria-label="{aria}">{srcs}<img src="{p[key_i]}" alt="{aria}"></video>')
    return f'<img loading="lazy" src="{p[key_i]}" alt="{aria}">'

# ---- index
fm_i, body_i = split_fm(os.path.join(ROOT, 'index.html'))
sections = []
for c in CATS:
    items = sorted([p for p in projects if p.get('category') == c['key']], key=lambda x: x.get('order', 99))
    if not items: continue
    cards = []
    for p in items:
        alt = p.get('hero_alt', '')
        thumb = media(p, 'thumb_video', 'thumb', alt)
        href = p['_url']
        badge = f'<span class="badge">{p["award"]}</span>' if p.get('award') else ''
        tags = ' · '.join(p.get('tags', []))
        links = f'<a class="repo-link" href="{p["_url"]}">글 읽기 →</a>'
        cards.append(f'''<article class="proj">
          <a class="thumb-link" href="{href}"><div class="thumb">{thumb}</div></a>
          <h3><a href="{href}">{p["title"]}</a></h3>
          <div class="read">{badge}<svg viewBox="0 0 16 16" fill="none" stroke="#6B7480" stroke-width="1.5"><circle cx="8" cy="8" r="6.5"/><path d="M8 4.5V8l2.5 1.5"/></svg>{tags}</div>
          <p>{p.get("summary","")}</p>
          <div class="read">{links}</div>
        </article>''')
    sections.append(f'<section id="{c["key"]}"><div class="cat">{c["name"]}</div>'
                    f'<div class="grid">{"".join(cards)}</div></section>')

idx = re.sub(r'<!-- PROJECTS -->.*?<!-- /PROJECTS -->', lambda m: chr(10).join(sections), body_i, flags=re.S)
os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(
    shell(cfg['title'] + ' — Projects', idx, cfg['description']))

# ---- articles
md = markdown.Markdown(extensions=['tables', 'md_in_html', 'fenced_code', 'attr_list'])
for p in projects:
    if p.get('article') is False: continue
    cat = next(c for c in CATS if c['key'] == p['category'])
    body = re.sub(r"\{\{\s*'([^']+)'\s*\|\s*relative_url\s*\}\}", r'\1', p['_body'])
    md.reset()
    html = md.convert(body)
    alt = p.get('hero_alt', '')
    hero = f'<div class="hero">{media(p, "hero_video", "hero", alt)}</div>'
    cap = f'<figcaption style="max-width:760px;margin-bottom:26px">{p["hero_caption"]}</figcaption>' if p.get('hero_caption') else ''
    meta = ''
    if p.get('award'): meta += f'<span class="tag hot">{p["award"]}</span>'
    meta += ''.join(f'<span class="tag">{t}</span>' for t in p.get('tags', []))
    meta += f'<a href="{p["repo"]}">GitHub ↗</a>'
    if p.get('demo'): meta += f'<a href="{p["demo"]}">Play ↗</a>'
    art = f'''<article class="article">
  <div class="crumb"><a href="/">Projects</a> &nbsp;/&nbsp; {cat["name"]}</div>
  <header class="art-head">
    <div class="art-cat">{cat["name"]}</div>
    <h1>{p["title"]}</h1>
    <p class="lede">{p.get("lede","")}</p>
    <div class="art-meta">{meta}</div>
  </header>
  {hero}{cap}
  <div class="body">{html}</div>
  <div class="art-nav"><a href="/">← 프로젝트 목록</a><a href="{p["repo"]}">저장소에서 코드 보기 ↗</a></div>
</article>'''
    d = os.path.join(OUT, p['_url'].strip('/'))
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(
        shell(p['title'] + ' · MK', art, p.get('lede', '')))

if os.path.exists(os.path.join(OUT, 'assets')): shutil.rmtree(os.path.join(OUT, 'assets'))
shutil.copytree(os.path.join(ROOT, 'assets'), os.path.join(OUT, 'assets'))
print('built:', len([p for p in projects if p.get('article') is not False]), 'articles')
