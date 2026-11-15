import re, os, subprocess, hashlib, html
import markdown
from weasyprint import HTML

# 使い方: python3 scripts/pdf/build.py
# 必要なもの: Python 3、markdown、weasyprint、mermaid-cli（mmdc）、Noto Sans CJK JP フォント
# Chrome の場所を変える場合は、環境変数 PUPPETEER_CONFIG に puppeteer の設定ファイルを指定する
HERE=os.path.dirname(os.path.abspath(__file__))
REPO=os.path.abspath(os.path.join(HERE,"..",".."))
OUT=os.environ.get("PDF_WORK_DIR","/tmp/engineering-notes-pdf")
IMG=f"{OUT}/img"
os.makedirs(IMG,exist_ok=True)
PUPPETEER=os.environ.get("PUPPETEER_CONFIG")
PDF_PATH=os.path.join(REPO,"pdf",os.environ.get("PDF_NAME","engineering-notes.pdf"))

PARTS=[
 ("はじめに", "このナレッジ集の考え方と、規模に応じた使い方", ["README.md","guide/how-to-use.md"]),
 ("第1部　事業と計画", "事業の目的から逆算して、何をどこまで作るかを決める", ["business/roadmap.md","business/estimation.md"]),
 ("第2部　開発の進め方", "AI を前提にした開発フロー、レビュー、チーム運営", ["process/development-flow.md","process/ai-pr-review.md","process/scrum-in-ai-era.md","process/project-onboarding.md","process/tech-debt.md"]),
 ("第3部　工程ごとのチェックリスト", "要件定義から障害対応まで、工程ごとに確認すべき観点", ["requirements/checklist.md","design/checklist.md","implementation/checklist.md","testing/strategy.md","security/checklist.md","data/migration.md","performance/release-checklist.md","release/checklist.md","operations/checklist.md","operations/incident-response.md"]),
 ("第4部　画面・AI 機能・インフラ", "領域ごとの設計と選定の観点", ["frontend/checklist.md","ai/llm-feature-design.md","infrastructure/aws-service-selection.md","infrastructure/cost-management.md"]),
 ("第5部　法務と情報収集", "守るべきルールと、知識を更新し続ける仕組み", ["legal/license-and-compliance.md","learning/catch-up.md","learning/ai-information.md"]),
 ("付録　テンプレート集", "そのまま使えるひな形", ["templates/README.md","templates/ticket.md","templates/pull-request.md","templates/adr.md","templates/postmortem.md","templates/agents-md.md"]),
]
allfiles=[f for _,_,fs in PARTS for f in fs]
cid={f:"c"+hashlib.md5(f.encode()).hexdigest()[:8] for f in allfiles}

def mermaid_png(code):
    h=hashlib.md5(code.encode()).hexdigest()[:12]
    src=f"{IMG}/{h}.mmd"; png=f"{IMG}/{h}.png"
    if not os.path.exists(png):
        open(src,"w").write(code)
        cfg=f"{IMG}/cfg.json"
        open(cfg,"w").write('{"theme":"neutral","themeVariables":{"fontFamily":"Noto Sans CJK JP","fontSize":"15px"}}')
        subprocess.run(["mmdc"]+(["-p",PUPPETEER] if PUPPETEER else [])+["-c",cfg,"-i",src,"-o",png,"-b","white","-s","3","-w","1100"],check=True,capture_output=True)
    return png

def chapter_html(f):
    s=open(f"{REPO}/{f}").read()
    lines=s.split("\n")
    title=lines[0][2:].strip()
    body="\n".join(lines[1:])
    body=re.sub(r"\n> 最終確認日：.*\n","\n",body,count=1)
    if f=="README.md":
        body=re.sub(r"(## 開発の全体像\n\n)```mermaid\n.*?\n```\n", r"\1全体像の図は、冒頭の「1ページでわかる全体像」を参照してください。\n", body, flags=re.S)
    # caption + mermaid -> one block
    def cap(m):
        png=mermaid_png(m.group(2))
        return f'\n<div class="fig"><div class="figcap">{html.escape(m.group(1))}</div><img src="file://{png}"/></div>\n'
    body=re.sub(r"\*\*([^*\n]+)\*\*\n\n```mermaid\n(.*?)\n```",cap,body,flags=re.S)
    # mermaid -> image
    def mm(m):
        png=mermaid_png(m.group(1))
        return f'\n<div class="fig"><img src="file://{png}"/></div>\n'
    body=re.sub(r"```mermaid\n(.*?)\n```",mm,body,flags=re.S)
    # README: drop the toc part (the PDF has its own)
    if f=="README.md":
        body=body.split("## はじめに")[0]
    out=[]; inc=False; prev=""
    for l in body.split("\n"):
        if l.startswith("```"): inc=not inc
        isli=bool(re.match(r"\s*([-*]|\d+\.) ",l))
        if not inc and isli and prev.strip() and not re.match(r"\s*([-*]|\d+\.) ",prev) and not prev.startswith(("|","<"," ")):
            out.append("")
        out.append(l); prev=l
    body="\n".join(out)
    h=markdown.markdown(body,extensions=["tables","fenced_code","sane_lists"])
    # checkboxes
    h=re.sub(r"<li>\[ \]\s*",'<li class="cb">',h)
    h=re.sub(r"<li>\s*<p>\[ \]\s*",'<li class="cb"><p>',h)
    # internal links
    def lk(m):
        href=m.group(1)
        if href.startswith("http"): return m.group(0)
        target=os.path.normpath(os.path.join(os.path.dirname(f),href.split("#")[0]))
        if target in cid: return f'href="#{cid[target]}"'
        return m.group(0)
    h=re.sub(r'href="([^"]+)"',lk,h)
    # mark reference sections
    h=re.sub(r'<h2>参考情報（2026年11月時点）</h2>','<h2 class="ref">参考情報（2026年11月時点）</h2>',h)
    h=h.replace("<hr />","")
    return title, h

parts_html=[]; toc=[]
n=0
for pi,(pt,pdesc,fs) in enumerate(PARTS):
    pid=f"p{pi}"
    items=[]
    chap=[]
    for f in fs:
        title,h=chapter_html(f)
        if f=="README.md": title="全体像とこのノートの考え方"
        n+=1
        items.append((cid[f],title))
        chap.append(f'<section class="chapter" id="{cid[f]}"><div class="ch-head"><div class="ch-part">{html.escape(pt)}</div><h1 class="ch-title">{html.escape(title)}</h1></div>{h}</section>')
    toc.append((pid,pt,items))
    lis="".join(f'<li><a href="#{c}">{html.escape(t)}</a></li>' for c,t in items)
    parts_html.append(f'<section class="part" id="{pid}"><div class="part-inner"><div class="part-label">{html.escape(pt.split("　")[0])}</div><h1 class="part-title">{html.escape(pt.split("　")[-1])}</h1><p class="part-desc">{html.escape(pdesc)}</p><ol class="part-list">{lis}</ol></div></section>'+"".join(chap))

toc_html="".join(
  f'<div class="toc-part"><a class="toc-ptitle" href="#{pid}">{html.escape(pt)}</a><ul>'+
  "".join(f'<li><a href="#{c}">{html.escape(t)}</a></li>' for c,t in items)+"</ul></div>"
  for pid,pt,items in toc)

overview_png=None
m=re.search(r"```mermaid\n(.*?)\n```",open(f"{REPO}/README.md").read(),re.S)
overview_png=mermaid_png(m.group(1))

css=open(os.path.join(HERE,"style.css")).read()
doc=f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>開発ナレッジ集</title><style>{css}</style></head><body>
<section class="cover">
  <div class="cover-band"></div>
  <div class="cover-body">
    <div class="cover-kicker">engineering-notes</div>
    <h1 class="cover-title">AI 時代の<br/>開発ナレッジ集</h1>
    <p class="cover-sub">事業の目的から、要件定義・設計・実装・リリース・運用まで。<br/>AI を前提にした開発の進め方とチェックリスト</p>
    <div class="cover-meta">2026年11月版</div>
  </div>
</section>
<section class="summary">
  <h1 class="sum-title">1ページでわかる全体像</h1>
  <div class="fig sum-fig"><img src="file://{overview_png}"/></div>
  <div class="sum-grid">
    <div class="sum-card"><div class="sum-h">工程ごとに漏れなく確認</div><p>要件定義から障害対応まで、各工程のチェックリストで確認の漏れを防ぎます。</p></div>
    <div class="sum-card"><div class="sum-h">網羅は AI、判断は人</div><p>AI に漏れやリスクを洗い出させ、予算・影響範囲・優先度を踏まえた判断は人が行います。</p></div>
    <div class="sum-card"><div class="sum-h">ボトルネックを先回り</div><p>障害・性能劣化・移行・運用の問題を、設計とリリース前の確認で先に見つけます。</p></div>
    <div class="sum-card"><div class="sum-h">検証を自動化</div><p>AI に自分で検証させ、人は意図とリスクの判断に集中します。</p></div>
  </div>
</section>
<section class="toc"><h1 class="toc-title">目次</h1>{toc_html}</section>
{''.join(parts_html)}
</body></html>"""
open(f"{OUT}/book.html","w").write(doc)
HTML(f"{OUT}/book.html",base_url=OUT).write_pdf(PDF_PATH)
print("built", n, "chapters ->", PDF_PATH)
