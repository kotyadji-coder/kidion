"""
theory_renderer.py — Renders rich visual theory blocks into HTML.

Takes the structured JSON from the "visual layout" step (Gemini Flash Lite)
and produces scroll-based HTML with diverse block types and animations.
Design: glass morphism matching school-bot (indigo accent, pastel gradients).

Block types:
  title, speech, text, emoji_hero, fact, diagram, compare,
  before_after, steps, keywords, example, scale, grid, list, summary
"""

import re as _re

# ── CSS: glass morphism + theory blocks ─────────────────────────────────────

THEORY_CSS = r"""
/* ── Variables ── */
:root {
    --glass-bg: rgba(255,255,255,0.70);
    --glass-border: rgba(255,255,255,0.90);
    --glass-shadow: 0 8px 32px rgba(99,102,241,0.12);
    --blur: blur(16px);
    --text-dark: #1f2937;
    --text-muted: #6b7280;
    --accent: #6366f1;
    --accent-glow: rgba(99,102,241,0.12);
    --green: #10b981;
    --radius: 20px;
}

/* ── Theory container ── */
.theory {
    max-width: 700px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding-bottom: 24px;
}

/* ── Glass card base ── */
.block {
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    border-radius: var(--radius);
    box-shadow: var(--glass-shadow);
    padding: 24px 28px;
    opacity: 0;
    transform: translateY(30px);
    transition: opacity 0.55s ease, transform 0.55s ease, box-shadow 0.2s ease;
}
.block.visible {
    opacity: 1;
    transform: translateY(0);
}
.block.visible:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 40px rgba(99,102,241,0.18);
}

/* ── Highlight spans ── */
.hl {
    background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.25);
    padding: 2px 8px;
    border-radius: 6px;
    font-weight: 700;
    color: #4338ca;
}

/* ── Title ── */
.block-title {
    text-align: center;
    padding: 40px 36px 36px;
    background: var(--accent);
    border: none;
    color: #fff;
}
.block-title .topic-label {
    display: inline-block;
    background: rgba(255,255,255,0.18);
    border: 1px solid rgba(255,255,255,0.30);
    font-size: 0.78em;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 5px 16px;
    border-radius: 50px;
    margin-bottom: 20px;
}
.block-title h1 {
    font-size: clamp(1.6em, 5vw, 2.4em);
    font-weight: 900;
    line-height: 1.2;
}
.block-title .topic-emoji {
    font-size: 56px;
    display: block;
    margin-top: 16px;
    animation: t-float 3s ease-in-out infinite;
}
@keyframes t-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-12px); } }

/* ── Text ── */
.block-text {
    font-size: 1.15rem;
    color: var(--text-dark);
    line-height: 1.8;
}

/* ── Speech bubble ── */
.block-speech {
    display: flex;
    gap: 20px;
    align-items: flex-start;
    background: rgba(240,253,244,0.70);
    border-color: rgba(187,247,208,0.60);
}
.speech-avatar {
    flex-shrink: 0;
    width: 54px;
    height: 54px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2rem;
    background: rgba(255,255,255,0.55);
    border: 1px solid rgba(255,255,255,0.88);
    border-radius: 14px;
    box-shadow: 0 2px 8px rgba(99,102,241,0.08);
}
.speech-name {
    font-size: 0.78em;
    font-weight: 800;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 4px;
}
.speech-text {
    flex: 1;
    font-size: 1.08rem;
    color: var(--text-dark);
    line-height: 1.7;
}

/* ── Emoji hero ── */
.block-emoji-hero {
    text-align: center;
    background: rgba(255,247,237,0.70);
    border-color: rgba(253,186,116,0.40);
}
.emoji-big {
    font-size: 56px;
    display: block;
    margin-bottom: 12px;
    animation: t-float 3s ease-in-out infinite;
}
.emoji-caption {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--text-dark);
}

/* ── Fact box ── */
.block-fact {
    background: rgba(240,253,244,0.70);
    border-left: 5px solid var(--green);
    border-radius: 4px var(--radius) var(--radius) 4px;
}
.fact-label {
    display: inline-block;
    background: rgba(16,185,129,0.12);
    color: #065f46;
    font-size: 0.72rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    padding: 4px 12px;
    border-radius: 50px;
    margin-bottom: 10px;
}
.fact-text {
    font-size: 1.05rem;
    color: var(--text-dark);
    line-height: 1.7;
    font-weight: 600;
}

/* ── Diagram ── */
.block-diagram { text-align: center; }
.diagram-title {
    font-size: 1.1rem;
    font-weight: 800;
    color: var(--text-dark);
    margin-bottom: 16px;
}
.diagram-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    flex-wrap: wrap;
}
.diagram-item {
    background: rgba(255,255,255,0.85);
    border: 2px solid rgba(99,102,241,0.18);
    border-radius: 16px;
    padding: 16px 20px;
    text-align: center;
    min-width: 110px;
    opacity: 0;
    transform: scale(0.8);
    transition: all 0.4s ease;
}
.block.visible .diagram-item { opacity: 1; transform: scale(1); }
.block.visible .diagram-item:nth-child(1) { transition-delay: 0.1s; }
.block.visible .diagram-item:nth-child(2) { transition-delay: 0.3s; }
.block.visible .diagram-item:nth-child(3) { transition-delay: 0.5s; }
.block.visible .diagram-item:nth-child(4) { transition-delay: 0.7s; }
.block.visible .diagram-item:nth-child(5) { transition-delay: 0.9s; }
.diagram-icon { font-size: 28px; display: block; margin-bottom: 4px; color: var(--accent); font-weight: 800; }
.diagram-label { font-size: 0.92rem; font-weight: 700; color: var(--text-dark); }
.diagram-sub { font-size: 0.78rem; color: var(--text-muted); margin-top: 2px; }
.diagram-arrow { font-size: 24px; color: var(--accent); font-weight: 800; opacity: 0; transition: opacity 0.4s ease 0.3s; }
.block.visible .diagram-arrow { opacity: 1; }

/* ── Compare table ── */
.block-compare { padding: 24px 28px; }
.compare-title { font-size: 1.1rem; font-weight: 800; color: var(--text-dark); margin-bottom: 14px; }
.compare-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    background: rgba(255,255,255,0.55);
    border: 1px solid rgba(99,102,241,0.10);
    border-radius: 14px;
    margin-bottom: 8px;
    opacity: 0;
    transform: translateX(-20px);
    transition: all 0.4s ease;
}
.block.visible .compare-row { opacity: 1; transform: translateX(0); }
.block.visible .compare-row:nth-child(2) { transition-delay: 0.15s; }
.block.visible .compare-row:nth-child(3) { transition-delay: 0.3s; }
.block.visible .compare-row:nth-child(4) { transition-delay: 0.45s; }
.block.visible .compare-row:nth-child(5) { transition-delay: 0.6s; }
.compare-icon { font-size: 24px; flex-shrink: 0; }
.compare-label { font-weight: 700; color: var(--text-dark); font-size: 0.95rem; flex: 1; }
.compare-value { color: var(--accent); font-weight: 800; font-size: 1rem; }

/* ── Before / After ── */
.block-before-after { display: flex; gap: 12px; padding: 20px; }
.ba-side {
    flex: 1;
    text-align: center;
    padding: 16px;
    border-radius: 16px;
    opacity: 0;
    transition: all 0.5s ease;
}
.ba-before { background: rgba(16,185,129,0.08); border: 2px solid rgba(16,185,129,0.25); transform: translateX(-20px); }
.ba-after { background: rgba(239,68,68,0.06); border: 2px solid rgba(239,68,68,0.25); transform: translateX(20px); }
.block.visible .ba-side { opacity: 1; transform: translateX(0); }
.block.visible .ba-after { transition-delay: 0.3s; }
.ba-label { font-size: 0.72rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 8px; }
.ba-before .ba-label { color: #065f46; }
.ba-after .ba-label { color: #991b1b; }
.ba-emoji { font-size: 32px; display: block; margin-bottom: 8px; }
.ba-text { font-size: 0.92rem; font-weight: 600; color: var(--text-dark); line-height: 1.5; }

/* ── Steps ── */
.block-steps { padding: 24px 28px; }
.steps-title { font-size: 1.1rem; font-weight: 800; color: var(--text-dark); margin-bottom: 16px; }
.step-item {
    display: flex;
    gap: 14px;
    align-items: flex-start;
    margin-bottom: 14px;
    opacity: 0;
    transform: translateY(12px);
    transition: all 0.4s ease;
}
.block.visible .step-item { opacity: 1; transform: translateY(0); }
.block.visible .step-item:nth-child(2) { transition-delay: 0.2s; }
.block.visible .step-item:nth-child(3) { transition-delay: 0.4s; }
.block.visible .step-item:nth-child(4) { transition-delay: 0.6s; }
.block.visible .step-item:nth-child(5) { transition-delay: 0.8s; }
.step-num {
    width: 28px; height: 28px;
    border-radius: 50%;
    background: var(--accent);
    color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.82rem; font-weight: 900; flex-shrink: 0;
}
.step-text { font-size: 1rem; color: var(--text-dark); line-height: 1.6; padding-top: 2px; }

/* ── Keywords ── */
.block-keywords { text-align: center; }
.keywords-title { font-size: 1rem; font-weight: 800; color: var(--text-dark); margin-bottom: 14px; }
.keywords-row { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.keyword {
    background: var(--accent);
    color: #fff;
    padding: 6px 16px;
    border-radius: 50px;
    font-size: 0.88rem;
    font-weight: 700;
    opacity: 0;
    transform: scale(0.5);
    transition: all 0.4s ease;
    box-shadow: 0 2px 10px rgba(99,102,241,0.25);
}
.block.visible .keyword { opacity: 1; transform: scale(1); }
.block.visible .keyword:nth-child(1) { transition-delay: 0.05s; }
.block.visible .keyword:nth-child(2) { transition-delay: 0.15s; }
.block.visible .keyword:nth-child(3) { transition-delay: 0.25s; }
.block.visible .keyword:nth-child(4) { transition-delay: 0.35s; }
.block.visible .keyword:nth-child(5) { transition-delay: 0.45s; }
.block.visible .keyword:nth-child(6) { transition-delay: 0.55s; }

/* ── Example ── */
.block-example {
    text-align: center;
    background: rgba(99,102,241,0.06);
    border-color: rgba(99,102,241,0.20);
}
.example-label {
    display: inline-block;
    background: var(--accent-glow);
    color: var(--accent);
    font-size: 0.72rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    padding: 4px 12px;
    border-radius: 50px;
    margin-bottom: 14px;
}
.example-expr { font-size: 2rem; font-weight: 900; color: var(--text-dark); letter-spacing: 2px; }
.example-explain { font-size: 0.95rem; color: var(--text-muted); margin-top: 10px; line-height: 1.6; font-weight: 600; }

/* ── Scale ── */
.block-scale { text-align: center; }
.scale-title { font-size: 1rem; font-weight: 800; color: var(--text-dark); margin-bottom: 16px; }
.scale-row { margin-bottom: 14px; }
.scale-row-label { text-align: left; font-size: 0.88rem; font-weight: 700; color: var(--text-dark); margin-bottom: 4px; }
.scale-bar { height: 22px; background: rgba(99,102,241,0.08); border-radius: 50px; overflow: hidden; }
.scale-fill { height: 100%; border-radius: 50px; width: 0%; transition: width 1.5s ease; }
.block.visible .scale-fill { width: var(--w); }
.sf1 { background: linear-gradient(90deg, #a5b4fc, #6366f1); }
.sf2 { background: linear-gradient(90deg, #6ee7b7, #10b981); }
.sf3 { background: linear-gradient(90deg, #fcd34d, #f59e0b); }

/* ── Grid ── */
.block-grid { text-align: center; }
.grid-title { font-size: 1rem; font-weight: 800; color: var(--text-dark); margin-bottom: 14px; }
.grid-row { display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; }
.grid-cell {
    width: 48px; height: 48px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px;
    background: rgba(255,255,255,0.55);
    border: 1px solid rgba(99,102,241,0.12);
    opacity: 0; transform: scale(0); transition: all 0.3s ease;
}
.grid-cell.filled { background: rgba(99,102,241,0.12); border-color: rgba(99,102,241,0.25); }
.block.visible .grid-cell { opacity: 1; transform: scale(1); }
.grid-caption { margin-top: 12px; font-size: 0.95rem; font-weight: 700; color: var(--accent); }

/* ── List ── */
.list-title { font-size: 1.1rem; font-weight: 800; color: var(--text-dark); margin-bottom: 14px; }
.list-item {
    display: flex; align-items: center; gap: 12px;
    padding: 8px 0; font-size: 1rem; color: var(--text-dark);
    opacity: 0; transform: translateX(-10px); transition: all 0.4s ease;
}
.block.visible .list-item { opacity: 1; transform: translateX(0); }
.block.visible .list-item:nth-child(2) { transition-delay: 0.1s; }
.block.visible .list-item:nth-child(3) { transition-delay: 0.2s; }
.block.visible .list-item:nth-child(4) { transition-delay: 0.3s; }
.block.visible .list-item:nth-child(5) { transition-delay: 0.4s; }
.list-icon { font-size: 22px; flex-shrink: 0; }

/* ── Summary ── */
.block-summary {
    background: var(--accent);
    border: none;
    color: #fff;
}
.summary-title { font-size: 1.2rem; font-weight: 900; margin-bottom: 16px; text-align: center; }
.summary-item {
    display: flex; align-items: center; gap: 12px;
    padding: 8px 0; font-size: 1rem; font-weight: 600;
    opacity: 0; transform: translateX(-10px); transition: all 0.4s ease;
}
.block.visible .summary-item { opacity: 1; transform: translateX(0); }
.block.visible .summary-item:nth-child(2) { transition-delay: 0.15s; }
.block.visible .summary-item:nth-child(3) { transition-delay: 0.3s; }
.block.visible .summary-item:nth-child(4) { transition-delay: 0.45s; }
.block.visible .summary-item:nth-child(5) { transition-delay: 0.6s; }
.summary-check {
    width: 26px; height: 26px; border-radius: 50%;
    background: rgba(255,255,255,0.20);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.82rem; font-weight: 900; flex-shrink: 0;
}

/* ── Responsive ── */
@media (max-width: 480px) {
    .block { padding: 18px 16px; }
    .block-title { padding: 28px 20px 24px; }
    .block-speech { gap: 14px; }
    .speech-avatar { width: 44px; height: 44px; font-size: 1.6rem; }
    .block-before-after { flex-direction: column; }
    .diagram-row { gap: 8px; }
}
"""

# ── JS (scroll observer) ───────────────────────────────────────────────────

THEORY_JS = """
(function() {
  var observer = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
      if (entry.isIntersecting) entry.target.classList.add('visible');
    });
  }, { threshold: 0.15 });
  document.querySelectorAll('.block').forEach(function(b) { observer.observe(b); });
})();
"""

# ── HTML helpers ────────────────────────────────────────────────────────────

_SAFE_TAGS = _re.compile(r'<(/?)(span|strong|br|em|b|i)(\s+class="[^"]*")?\s*/?>')


def _esc(text: str) -> str:
    """Escape HTML but preserve safe formatting tags (span.hl, strong, br, em)."""
    # Extract safe tags, escape everything, put safe tags back
    parts = _SAFE_TAGS.split(str(text))
    result = []
    i = 0
    for m in _SAFE_TAGS.finditer(str(text)):
        pre = text[i:m.start()]
        result.append(pre.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
        result.append(m.group(0))  # safe tag unchanged
        i = m.end()
    result.append(text[i:].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
    return "".join(result)


# ── Block renderers ─────────────────────────────────────────────────────────

def _render_title(b: dict) -> str:
    label = _esc(b.get("label", ""))
    heading = _esc(b.get("text", ""))
    emoji = b.get("emoji", "")
    return (
        f'<div class="block block-title">'
        f'<div class="topic-label">{label}</div>'
        f'<h1>{heading}</h1>'
        f'<span class="topic-emoji">{emoji}</span>'
        f'</div>'
    )


def _render_speech(b: dict) -> str:
    avatar = b.get("avatar_emoji", "")
    name = _esc(b.get("name", ""))
    text = _esc(b.get("text", ""))
    return (
        f'<div class="block block-speech">'
        f'<div class="speech-avatar">{avatar}</div>'
        f'<div class="speech-content">'
        f'<div class="speech-name">{name}</div>'
        f'<div class="speech-text">{text}</div>'
        f'</div></div>'
    )


def _render_text(b: dict) -> str:
    text = _esc(b.get("text", ""))
    return f'<div class="block block-text">{text}</div>'


def _render_emoji_hero(b: dict) -> str:
    emoji = b.get("emoji", "")
    caption = _esc(b.get("caption", ""))
    return (
        f'<div class="block block-emoji-hero">'
        f'<span class="emoji-big">{emoji}</span>'
        f'<div class="emoji-caption">{caption}</div>'
        f'</div>'
    )


def _render_fact(b: dict) -> str:
    label = _esc(b.get("label", "Запомни!"))
    text = _esc(b.get("text", ""))
    return (
        f'<div class="block block-fact">'
        f'<div class="fact-label">{label}</div>'
        f'<div class="fact-text">{text}</div>'
        f'</div>'
    )


def _render_diagram(b: dict) -> str:
    title = _esc(b.get("title", ""))
    items = b.get("items", [])
    parts = []
    for i, item in enumerate(items):
        icon = item.get("icon", "")
        label = _esc(item.get("label", ""))
        sub = _esc(item.get("sub", ""))
        parts.append(
            f'<div class="diagram-item">'
            f'<span class="diagram-icon">{icon}</span>'
            f'<div class="diagram-label">{label}</div>'
            f'<div class="diagram-sub">{sub}</div>'
            f'</div>'
        )
        if i < len(items) - 1:
            arrow = _esc(item.get("arrow", "\u2192"))
            parts.append(f'<div class="diagram-arrow">{arrow}</div>')
    return (
        f'<div class="block block-diagram">'
        f'<div class="diagram-title">{title}</div>'
        f'<div class="diagram-row">{"".join(parts)}</div>'
        f'</div>'
    )


def _render_compare(b: dict) -> str:
    title = _esc(b.get("title", ""))
    rows = b.get("rows", [])
    rows_html = ""
    for row in rows:
        icon = row.get("icon", "")
        label = _esc(row.get("label", ""))
        value = _esc(row.get("value", ""))
        rows_html += (
            f'<div class="compare-row">'
            f'<span class="compare-icon">{icon}</span>'
            f'<span class="compare-label">{label}</span>'
            f'<span class="compare-value">{value}</span>'
            f'</div>'
        )
    return (
        f'<div class="block block-compare">'
        f'<div class="compare-title">{title}</div>'
        f'{rows_html}</div>'
    )


def _render_before_after(b: dict) -> str:
    before = b.get("before", {})
    after = b.get("after", {})
    return (
        f'<div class="block block-before-after">'
        f'<div class="ba-side ba-before">'
        f'<div class="ba-label">{_esc(before.get("label", ""))}</div>'
        f'<span class="ba-emoji">{before.get("emoji", "")}</span>'
        f'<div class="ba-text">{_esc(before.get("text", ""))}</div>'
        f'</div>'
        f'<div class="ba-side ba-after">'
        f'<div class="ba-label">{_esc(after.get("label", ""))}</div>'
        f'<span class="ba-emoji">{after.get("emoji", "")}</span>'
        f'<div class="ba-text">{_esc(after.get("text", ""))}</div>'
        f'</div></div>'
    )


def _render_steps(b: dict) -> str:
    title = _esc(b.get("title", ""))
    items = b.get("items", [])
    items_html = ""
    for i, text in enumerate(items, 1):
        items_html += (
            f'<div class="step-item">'
            f'<div class="step-num">{i}</div>'
            f'<div class="step-text">{_esc(text)}</div>'
            f'</div>'
        )
    return (
        f'<div class="block block-steps">'
        f'<div class="steps-title">{title}</div>'
        f'{items_html}</div>'
    )


def _render_keywords(b: dict) -> str:
    title = _esc(b.get("title", "Новые слова"))
    words = b.get("words", [])
    pills = "".join(f'<span class="keyword">{_esc(w)}</span>' for w in words)
    return (
        f'<div class="block block-keywords">'
        f'<div class="keywords-title">{title}</div>'
        f'<div class="keywords-row">{pills}</div>'
        f'</div>'
    )


def _render_example(b: dict) -> str:
    label = _esc(b.get("label", "Пример"))
    expr = _esc(b.get("expression", ""))
    explain = _esc(b.get("explanation", ""))
    return (
        f'<div class="block block-example">'
        f'<div class="example-label">{label}</div>'
        f'<div class="example-expr">{expr}</div>'
        f'<div class="example-explain">{explain}</div>'
        f'</div>'
    )


def _render_scale(b: dict) -> str:
    title = _esc(b.get("title", ""))
    items = b.get("items", [])
    colors = ["sf1", "sf2", "sf3", "sf1", "sf2"]
    rows_html = ""
    for i, item in enumerate(items):
        label = _esc(item.get("label", ""))
        pct = int(item.get("percent", 50))
        cls = colors[i % len(colors)]
        rows_html += (
            f'<div class="scale-row">'
            f'<div class="scale-row-label">{label}</div>'
            f'<div class="scale-bar"><div class="scale-fill {cls}" style="--w:{pct}%"></div></div>'
            f'</div>'
        )
    return (
        f'<div class="block block-scale">'
        f'<div class="scale-title">{title}</div>'
        f'{rows_html}</div>'
    )


def _render_grid(b: dict) -> str:
    title = _esc(b.get("title", ""))
    total = int(b.get("total", 8))
    filled = int(b.get("filled", 3))
    filled_emoji = b.get("filled_emoji", "\U0001f7e0")
    empty_emoji = b.get("empty_emoji", "\u2b1c")
    caption = _esc(b.get("caption", ""))

    cells = ""
    for i in range(total):
        delay = f'style="transition-delay:{i * 0.05:.2f}s"'
        if i < filled:
            cells += f'<div class="grid-cell filled" {delay}>{filled_emoji}</div>'
        else:
            cells += f'<div class="grid-cell" {delay}>{empty_emoji}</div>'

    return (
        f'<div class="block block-grid">'
        f'<div class="grid-title">{title}</div>'
        f'<div class="grid-row">{cells}</div>'
        f'<div class="grid-caption">{caption}</div>'
        f'</div>'
    )


def _render_list(b: dict) -> str:
    title = _esc(b.get("title", ""))
    items = b.get("items", [])
    items_html = ""
    for item in items:
        icon = item.get("icon", "")
        text = _esc(item.get("text", ""))
        items_html += (
            f'<div class="list-item">'
            f'<span class="list-icon">{icon}</span>'
            f'{text}'
            f'</div>'
        )
    return (
        f'<div class="block block-list">'
        f'<div class="list-title">{title}</div>'
        f'{items_html}</div>'
    )


def _render_summary(b: dict) -> str:
    title = _esc(b.get("title", "Что мы узнали"))
    items = b.get("items", [])
    items_html = ""
    for text in items:
        items_html += (
            f'<div class="summary-item">'
            f'<span class="summary-check">\u2713</span>'
            f'{_esc(text)}'
            f'</div>'
        )
    return (
        f'<div class="block block-summary">'
        f'<div class="summary-title">{title}</div>'
        f'{items_html}</div>'
    )


# ── Renderer registry ──────────────────────────────────────────────────────

_RENDERERS = {
    "title": _render_title,
    "speech": _render_speech,
    "text": _render_text,
    "emoji_hero": _render_emoji_hero,
    "fact": _render_fact,
    "diagram": _render_diagram,
    "compare": _render_compare,
    "before_after": _render_before_after,
    "steps": _render_steps,
    "keywords": _render_keywords,
    "example": _render_example,
    "scale": _render_scale,
    "grid": _render_grid,
    "list": _render_list,
    "summary": _render_summary,
}


def render_theory_html(visual_blocks: list[dict]) -> str:
    """Render visual block dicts into theory HTML (no wrapper)."""
    parts = []
    for block in visual_blocks:
        renderer = _RENDERERS.get(block.get("type", ""))
        if renderer:
            parts.append(renderer(block))
    return "\n".join(parts)


def render_theory_full_html(visual_blocks: list[dict]) -> str:
    """Render visual blocks into a complete standalone HTML page (for demos)."""
    body = render_theory_html(visual_blocks)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Теория</title>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ min-height: 100%; background: transparent; }}
body {{
    font-family: 'Nunito', sans-serif;
    color: #1f2937;
    line-height: 1.7;
    min-height: 100vh;
}}
.bg-overlay {{
    position: fixed; inset: 0; z-index: -1;
    background: linear-gradient(135deg,
        rgba(199,210,254,0.38) 0%,
        rgba(167,243,208,0.28) 50%,
        rgba(253,230,138,0.25) 100%);
}}
.page {{ max-width: 700px; margin: 0 auto; padding: 48px 20px 80px; }}
{THEORY_CSS}
</style>
</head>
<body>
<div class="bg-overlay"></div>
<div class="page">
<div class="theory">
{body}
</div>
</div>
<script>
{THEORY_JS}
</script>
</body>
</html>"""
