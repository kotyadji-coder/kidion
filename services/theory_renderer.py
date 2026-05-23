"""
theory_renderer.py — Renders rich visual theory blocks into HTML.

Takes the structured JSON from the "visual layout" step (Gemini Flash Lite)
and produces scroll-based HTML with diverse block types and animations.
Design: Cozy Quest — warm palette (coral/teal/marigold), Fredoka + Nunito.

Block types:
  title, speech, text, emoji_hero, fact, diagram, compare,
  before_after, steps, keywords, example, scale, grid, list, summary
"""

import re as _re

# ── CSS: Cozy Quest warm palette ────────────────────────────────────────────

THEORY_CSS = r"""
/* ── Variables ── */
:root {
    --bg: #FFF8EC;
    --surface: #FFFFFF;
    --ink: #2A1F1A;
    --ink-soft: #7B6657;
    --primary: #FF6B4A;
    --star: #FFB627;
    --streak: #3DAEA3;
    --line: rgba(42,31,26,.10);
    --radius: 20px;
    /* subject accent — overridden per lesson */
    --subj-accent: #FF6B4A;
    --subj-bg: #FFE3D6;
}

/* ── Theory container ── */
.theory {
    max-width: 760px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 22px;
    padding-bottom: 24px;
}

/* ── Card base ── */
.block {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    box-shadow: 0 1px 0 var(--line), 0 8px 20px -14px rgba(0,0,0,.18);
    padding: 16px;
    opacity: 0;
    transform: translateY(24px);
    transition: opacity 0.5s ease, transform 0.5s ease;
}
.block.visible {
    opacity: 1;
    transform: translateY(0);
}

/* ── Highlight spans ── */
.hl {
    background: rgba(255,107,74,0.13);
    color: var(--subj-accent);
    padding: 1px 6px;
    border-radius: 6px;
    font-weight: 800;
    line-height: 2;
    display: inline;
}

/* ── Title ── */
.block-title {
    padding: 24px 18px 22px;
    background: linear-gradient(155deg, var(--subj-bg) 0%, var(--surface) 75%);
    border: 1px solid var(--line);
    border-radius: 24px;
    position: relative;
    overflow: hidden;
}
.block-title .topic-label {
    display: inline-block;
    font-size: 0.72em;
    font-weight: 800;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--subj-accent);
    margin-bottom: 6px;
}
.block-title h1 {
    font-family: 'Fredoka', sans-serif;
    font-size: clamp(1.4em, 5vw, 1.8em);
    font-weight: 700;
    line-height: 1.1;
    color: var(--ink);
    letter-spacing: -.01em;
    margin: 0;
}
.block-title .topic-emoji {
    font-size: 44px;
    display: inline-block;
    margin-top: 12px;
    animation: kBob 3s ease-in-out infinite;
}

/* ── Animations ── */
@keyframes kBob { 0%,100%{transform:translateY(0) rotate(-1deg)} 50%{transform:translateY(-3px) rotate(1deg)} }
@keyframes kFloat { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-8px)} }

/* ── Text ── */
.block-text {
    font-size: 1rem;
    color: var(--ink);
    line-height: 1.55;
    padding: 0 4px;
    background: transparent;
    border: none;
    box-shadow: none;
}

/* ── Speech bubble ── */
.block-speech {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 0;
}
.speech-avatar {
    flex-shrink: 0;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.6rem;
    background: linear-gradient(160deg, var(--primary), var(--star));
    border: 3px solid var(--surface);
    border-radius: 50%;
    box-shadow: 0 6px 16px -6px rgba(255,107,74,.35);
    color: #fff;
    font-family: 'Fredoka', sans-serif;
    font-weight: 700;
}
.speech-name {
    font-size: 0.72em;
    font-weight: 800;
    color: var(--ink-soft);
    letter-spacing: 0.04em;
    margin-bottom: 4px;
    padding-left: 4px;
}
.speech-text {
    flex: 1;
    font-size: 0.95rem;
    color: var(--ink);
    line-height: 1.4;
    background: var(--surface);
    border-radius: 18px;
    border-top-left-radius: 4px;
    padding: 12px 14px;
    border: 1px solid var(--line);
    box-shadow: 0 8px 20px -16px rgba(0,0,0,.15);
}

/* ── Emoji hero ── */
.block-emoji-hero {
    text-align: center;
    padding: 22px 16px;
}
.emoji-big {
    font-size: 56px;
    display: inline-block;
    margin-bottom: 10px;
    animation: kFloat 2.5s ease-in-out infinite;
}
.emoji-caption {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--ink-soft);
}

/* ── Fact box ── */
.block-fact {
    background: rgba(61,174,163,.07);
    border-left: 4px solid var(--streak);
    border-radius: 16px;
}
.fact-label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: 'Fredoka', sans-serif;
    font-weight: 700;
    font-size: 0.82rem;
    color: var(--streak);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
}
.fact-label::before {
    content: '\2728';
    font-size: 14px;
}
.fact-text {
    font-size: 0.95rem;
    color: var(--ink);
    line-height: 1.45;
}

/* ── Diagram ── */
.block-diagram { padding: 16px 12px; }
.diagram-title {
    font-size: 0.72rem;
    font-weight: 800;
    color: var(--streak);
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 10px;
}
.diagram-title::before {
    content: '';
    display: inline-block;
    width: 4px; height: 4px;
    border-radius: 50%;
    background: var(--streak);
    margin-right: 6px;
    vertical-align: middle;
}
.diagram-row {
    display: flex;
    align-items: stretch;
    gap: 4px;
}
.diagram-item {
    flex: 1;
    padding: 10px 6px;
    border-radius: 14px;
    text-align: center;
    border: 1px solid var(--line);
    background: rgba(61,174,163,.07);
    opacity: 0;
    transform: scale(0.8);
    transition: all 0.4s ease;
}
.diagram-item:last-child { background: rgba(255,107,74,.08); }
.block.visible .diagram-item { opacity: 1; transform: scale(1); }
.block.visible .diagram-item:nth-child(1) { transition-delay: 0.1s; }
.block.visible .diagram-item:nth-child(2) { transition-delay: 0.3s; }
.block.visible .diagram-item:nth-child(3) { transition-delay: 0.5s; }
.block.visible .diagram-item:nth-child(4) { transition-delay: 0.7s; }
.block.visible .diagram-item:nth-child(5) { transition-delay: 0.9s; }
.diagram-icon { font-size: 28px; display: block; margin-bottom: 4px; line-height: 1; }
.diagram-label { font-size: 0.72rem; font-weight: 700; color: var(--ink); margin-top: 6px; line-height: 1.2; }
.diagram-sub { font-size: 0.7rem; color: var(--ink-soft); margin-top: 2px; }
.diagram-arrow { font-size: 16px; color: var(--ink-soft); display: flex; align-items: center; opacity: 0; transition: opacity 0.4s ease 0.3s; }
.block.visible .diagram-arrow { opacity: 1; }

/* ── Compare table ── */
.block-compare { padding: 14px 4px 14px; }
.compare-title {
    font-size: 0.72rem;
    font-weight: 800;
    color: var(--star);
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 10px;
    padding: 0 12px;
}
.compare-title::before {
    content: '';
    display: inline-block;
    width: 4px; height: 4px;
    border-radius: 50%;
    background: var(--star);
    margin-right: 6px;
    vertical-align: middle;
}
.compare-row {
    display: grid;
    grid-template-columns: 36px 1fr auto;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: 10px;
    margin: 0 8px 4px;
    opacity: 0;
    transform: translateX(-12px);
    transition: all 0.4s ease;
}
.compare-row:nth-child(odd) { background: rgba(255,107,74,.06); }
.block.visible .compare-row { opacity: 1; transform: translateX(0); }
.block.visible .compare-row:nth-child(2) { transition-delay: 0.15s; }
.block.visible .compare-row:nth-child(3) { transition-delay: 0.3s; }
.block.visible .compare-row:nth-child(4) { transition-delay: 0.45s; }
.block.visible .compare-row:nth-child(5) { transition-delay: 0.6s; }
.compare-icon { font-size: 24px; text-align: center; line-height: 1; }
.compare-label { font-family: 'Fredoka', sans-serif; font-weight: 700; font-size: 1.3rem; color: var(--subj-accent); letter-spacing: -.02em; }
.compare-value { font-size: 0.88rem; font-weight: 700; color: var(--ink); }

/* ── Before / After ── */
.block-before-after {
    display: flex; gap: 8px; padding: 0;
    background: transparent; border: none; box-shadow: none;
}
.ba-side {
    flex: 1;
    text-align: center;
    padding: 14px 10px;
    border-radius: 16px;
    opacity: 0;
    transition: all 0.5s ease;
}
.ba-before { background: rgba(61,174,163,.06); border: 1px solid rgba(61,174,163,.2); transform: translateX(-12px); }
.ba-after { background: rgba(255,107,74,.06); border: 1px solid rgba(255,107,74,.2); transform: translateX(12px); }
.block.visible .ba-side { opacity: 1; transform: translateX(0); }
.block.visible .ba-after { transition-delay: 0.3s; }
.ba-label { font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }
.ba-before .ba-label { color: var(--streak); }
.ba-after .ba-label { color: var(--primary); }
.ba-emoji { font-size: 44px; display: block; margin-bottom: 8px; line-height: 1; }
.ba-text { font-size: 0.88rem; font-weight: 700; color: var(--ink); }
.ba-sub { font-size: 0.78rem; color: var(--ink-soft); margin-top: 2px; }

/* ── Steps ── */
.block-steps { padding: 16px; }
.steps-title {
    font-size: 0.72rem;
    font-weight: 800;
    color: var(--primary);
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 10px;
}
.steps-title::before {
    content: '';
    display: inline-block;
    width: 4px; height: 4px;
    border-radius: 50%;
    background: var(--primary);
    margin-right: 6px;
    vertical-align: middle;
}
.step-item {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px dashed var(--line);
    opacity: 0;
    transform: translateY(10px);
    transition: all 0.4s ease;
}
.step-item:last-child { border-bottom: none; }
.block.visible .step-item { opacity: 1; transform: translateY(0); }
.block.visible .step-item:nth-child(2) { transition-delay: 0.15s; }
.block.visible .step-item:nth-child(3) { transition-delay: 0.3s; }
.block.visible .step-item:nth-child(4) { transition-delay: 0.45s; }
.block.visible .step-item:nth-child(5) { transition-delay: 0.6s; }
.step-num {
    width: 28px; height: 28px;
    border-radius: 50%;
    background: rgba(255,107,74,.1);
    color: var(--primary);
    display: flex; align-items: center; justify-content: center;
    font-family: 'Fredoka', sans-serif;
    font-size: 0.88rem; font-weight: 700; flex-shrink: 0;
}
.step-icon { font-size: 22px; line-height: 1; width: 24px; text-align: center; }
.step-text { font-size: 0.95rem; color: var(--ink); line-height: 1.3; }

/* ── Keywords ── */
.block-keywords {
    background: transparent; border: none; box-shadow: none; padding: 0;
}
.keywords-title {
    font-size: 0.72rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 8px;
}
.keywords-row { display: flex; flex-wrap: wrap; gap: 6px; }
.keyword {
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 700;
    opacity: 0;
    transform: scale(0.5);
    transition: all 0.4s ease;
}
.keyword:nth-child(6n+1) { background: rgba(255,107,74,.1); color: var(--primary); border: 1px solid rgba(255,107,74,.2); }
.keyword:nth-child(6n+2) { background: rgba(61,174,163,.1); color: var(--streak); border: 1px solid rgba(61,174,163,.2); }
.keyword:nth-child(6n+3) { background: rgba(255,182,39,.1); color: #8C5A00; border: 1px solid rgba(255,182,39,.2); }
.keyword:nth-child(6n+4) { background: rgba(124,179,66,.1); color: #456B1F; border: 1px solid rgba(124,179,66,.2); }
.keyword:nth-child(6n+5) { background: rgba(142,107,255,.1); color: #5A3DBE; border: 1px solid rgba(142,107,255,.2); }
.keyword:nth-child(6n+6) { background: rgba(255,107,74,.1); color: var(--primary); border: 1px solid rgba(255,107,74,.2); }
.block.visible .keyword { opacity: 1; transform: scale(1); }
.block.visible .keyword:nth-child(1) { transition-delay: 0.05s; }
.block.visible .keyword:nth-child(2) { transition-delay: 0.12s; }
.block.visible .keyword:nth-child(3) { transition-delay: 0.19s; }
.block.visible .keyword:nth-child(4) { transition-delay: 0.26s; }
.block.visible .keyword:nth-child(5) { transition-delay: 0.33s; }
.block.visible .keyword:nth-child(6) { transition-delay: 0.40s; }

/* ── Example ── */
.block-example {
    text-align: center;
    padding: 20px 16px;
}
.example-label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    border-radius: 999px;
    background: rgba(255,107,74,.1);
    color: var(--subj-accent);
    font-size: 0.65rem;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-bottom: 10px;
}
.example-label::before {
    content: '';
    width: 4px; height: 4px;
    border-radius: 50%;
    background: var(--subj-accent);
}
.example-expr {
    font-family: 'Fredoka', sans-serif;
    font-size: 2.4rem;
    font-weight: 700;
    color: var(--ink);
    letter-spacing: 1px;
}
.example-explain { font-size: 0.85rem; color: var(--ink-soft); margin-top: 8px; line-height: 1.5; font-weight: 600; }

/* ── Scale ── */
.block-scale { padding: 16px; }
.scale-title {
    font-size: 0.72rem;
    font-weight: 800;
    color: var(--subj-accent);
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 10px;
}
.scale-title::before {
    content: '';
    display: inline-block;
    width: 4px; height: 4px;
    border-radius: 50%;
    background: var(--subj-accent);
    margin-right: 6px;
    vertical-align: middle;
}
.scale-row {
    display: grid;
    grid-template-columns: 46px 1fr auto;
    align-items: center;
    gap: 10px;
    margin-top: 8px;
}
.scale-row:first-of-type { margin-top: 0; }
.scale-row-label {
    font-family: 'Fredoka', sans-serif;
    font-weight: 700;
    font-size: 1rem;
    color: var(--subj-accent);
}
.scale-bar { height: 14px; background: rgba(255,107,74,.1); border-radius: 999px; overflow: hidden; }
.scale-fill { height: 100%; border-radius: 999px; width: 0%; transition: width 1.5s ease; }
.block.visible .scale-fill { width: var(--w); }
.sf1, .sf2, .sf3 { background: linear-gradient(90deg, var(--subj-accent), var(--star)); }
.scale-pct { font-size: 0.78rem; font-weight: 700; color: var(--ink-soft); width: 32px; text-align: right; }

/* ── Grid ── */
.block-grid { text-align: center; }
.grid-title {
    font-size: 0.72rem;
    font-weight: 800;
    color: var(--streak);
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 10px;
}
.grid-title::before {
    content: '';
    display: inline-block;
    width: 4px; height: 4px;
    border-radius: 50%;
    background: var(--streak);
    margin-right: 6px;
    vertical-align: middle;
}
.grid-row { display: inline-grid; gap: 6px; margin: 4px 0 8px; }
.grid-cell {
    width: 56px; height: 56px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 26px;
    background: var(--bg);
    border: 2px dashed var(--line);
    opacity: 0; transform: scale(0); transition: all 0.3s ease;
}
.grid-cell.filled {
    background: rgba(255,107,74,.1);
    border: 2px solid var(--subj-accent);
}
.block.visible .grid-cell { opacity: 1; transform: scale(1); }
.grid-caption { margin-top: 8px; font-size: 0.85rem; font-weight: 600; color: var(--ink-soft); }

/* ── List ── */
.block-list { padding: 16px; }
.list-title {
    font-size: 0.72rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 10px;
}
.list-item {
    display: flex; align-items: center; gap: 12px;
    padding: 8px 0;
    border-bottom: 1px solid var(--line);
    font-size: 0.95rem; color: var(--ink);
    opacity: 0; transform: translateX(-10px); transition: all 0.4s ease;
}
.list-item:last-child { border-bottom: none; }
.block.visible .list-item { opacity: 1; transform: translateX(0); }
.block.visible .list-item:nth-child(2) { transition-delay: 0.1s; }
.block.visible .list-item:nth-child(3) { transition-delay: 0.2s; }
.block.visible .list-item:nth-child(4) { transition-delay: 0.3s; }
.block.visible .list-item:nth-child(5) { transition-delay: 0.4s; }
.list-icon {
    width: 36px; height: 36px;
    border-radius: 10px;
    background: rgba(124,179,66,.1);
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; flex-shrink: 0;
}

/* ── Summary ── */
.block-summary {
    background: linear-gradient(160deg, var(--subj-bg), var(--surface) 80%);
    border: 1px solid var(--line);
    padding: 18px;
}
.summary-title {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: 'Fredoka', sans-serif;
    font-weight: 700;
    font-size: 1.1rem;
    color: var(--ink);
    margin-bottom: 10px;
}
.summary-title::before { content: '\1f4dd'; font-size: 22px; }
.summary-item {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 6px 0; font-size: 0.95rem; font-weight: 600; color: var(--ink);
    opacity: 0; transform: translateX(-10px); transition: all 0.4s ease;
    word-break: break-word;
    line-height: 1.35;
}
.block.visible .summary-item { opacity: 1; transform: translateX(0); }
.block.visible .summary-item:nth-child(2) { transition-delay: 0.12s; }
.block.visible .summary-item:nth-child(3) { transition-delay: 0.24s; }
.block.visible .summary-item:nth-child(4) { transition-delay: 0.36s; }
.block.visible .summary-item:nth-child(5) { transition-delay: 0.48s; }
.summary-check {
    width: 22px; height: 22px; border-radius: 50%;
    background: var(--streak);
    color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.72rem; font-weight: 900; flex-shrink: 0;
}

/* ── Responsive ── */
@media (max-width: 480px) {
    .block { padding: 14px 12px; }
    .block-title { padding: 20px 16px 18px; }
    .block-speech { gap: 10px; }
    .speech-avatar { width: 42px; height: 42px; font-size: 1.3rem; }
    .block-before-after { flex-direction: column; }
    .diagram-row { gap: 4px; }
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

# Common AI model typos in HTML tags
_TAG_TYPOS = {
    "<stong>": "<strong>", "</stong>": "</strong>",
    "<strng>": "<strong>", "</strng>": "</strong>",
    "<storng>": "<strong>", "</storng>": "</strong>",
    "<strog>": "<strong>", "</strog>": "</strong>",
    "<srong>": "<strong>", "</srong>": "</strong>",
}


def _fix_broken_tags(text: str) -> str:
    """Fix common AI-generated HTML typos and unclosed tags."""
    for typo, fix in _TAG_TYPOS.items():
        text = text.replace(typo, fix)
    # Close unclosed <strong> tags
    opens = text.count("<strong>")
    closes = text.count("</strong>")
    if opens > closes:
        text += "</strong>" * (opens - closes)
    # Close unclosed <em> tags
    opens = text.count("<em>")
    closes = text.count("</em>")
    if opens > closes:
        text += "</em>" * (opens - closes)
    return text


def _esc(text: str) -> str:
    """Escape HTML but preserve safe formatting tags (span.hl, strong, br, em)."""
    text = _fix_broken_tags(str(text))
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
.page {{ max-width: 900px; margin: 0 auto; padding: 48px 20px 80px; }}
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
