"""
content_generator.py — Renders lesson JSON into HTML files and saves to content/ directory.
Design: glass morphism matching school-bot (indigo accent, pastel gradients).
"""

import os

from services.theory_renderer import THEORY_CSS, THEORY_JS, render_theory_html

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONTENT_DIR = os.path.join(_BASE_DIR, "content")

# ── Task type labels and colors ─────────────────────────────────────────────

_TASK_TYPE_LABELS = {
    "quiz": "Выбери ответ",
    "multiple_choice": "Несколько ответов",
    "drag_and_drop": "Соотнеси",
    "fill_in_the_blank": "Впиши ответ",
    "ordering": "Расставь по порядку",
}


def save_lesson_html(image_bytes: bytes | None, lesson_json: dict,
                     content_id: str, server_url: str,
                     visual_blocks: list[dict] | None = None) -> str:
    """
    Render lesson JSON + optional image into an HTML file.
    Returns the content_url for the lesson.
    """
    os.makedirs(_CONTENT_DIR, exist_ok=True)

    story_blocks = lesson_json.get("story_blocks", [])
    tasks = lesson_json.get("tasks", [])

    # Save image if provided — used as background layer (like school-bot)
    bg_image_url = ""
    if image_bytes:
        img_path = os.path.join(_CONTENT_DIR, f"{content_id}.png")
        with open(img_path, "wb") as f:
            f.write(image_bytes)
        bg_image_url = f"{server_url}/content/{content_id}.png"

    # Build theory HTML
    if visual_blocks:
        story_html = '<div class="theory">\n' + render_theory_html(visual_blocks) + '\n</div>'
        theory_css = THEORY_CSS
        theory_js = THEORY_JS
    else:
        story_html = ""
        for block in story_blocks:
            emoji = block.get("emoji", "")
            text = block.get("text", "")
            story_html += (
                f'<div class="story-block glass-card">'
                f'<div class="story-emoji">{emoji}</div>'
                f'<div class="story-text">{text}</div>'
                f'</div>\n'
            )
        theory_css = ""
        theory_js = ""

    # Build background layer HTML
    bg_layer_html = ""
    if bg_image_url:
        bg_layer_html = f'<div class="bg-layer" style="background-image:url({bg_image_url})"></div>'

    # Build tasks HTML
    tasks_html = _build_tasks_html(tasks)

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Урок</title>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}

:root {{
    --glass-bg: rgba(255,255,255,0.70);
    --glass-border: rgba(255,255,255,0.90);
    --glass-shadow: 0 8px 32px rgba(99,102,241,0.12);
    --blur: blur(16px);
    --text-dark: #1f2937;
    --text-muted: #6b7280;
    --accent: #6366f1;
    --accent-glow: rgba(99,102,241,0.12);
    --green: #10b981;
    --red: #ef4444;
    --radius: 20px;
}}

html, body {{ min-height: 100%; background: #f0f0f5; }}

.bg-layer {{
    position: fixed; inset: 0; z-index: -2;
    background-size: cover; background-position: center;
}}
body {{
    font-family: 'Nunito', sans-serif;
    color: var(--text-dark);
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

.page {{
    max-width: 700px;
    margin: 0 auto;
    padding: 48px 20px 80px;
}}

.glass-card {{
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    border-radius: var(--radius);
    box-shadow: var(--glass-shadow);
}}

/* ── Hero image ── */
.lesson-hero {{
    width: 100%;
    border-radius: var(--radius);
    margin-bottom: 20px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.12);
}}

/* ── Old-style story blocks (fallback) ── */
.story-block {{
    display: flex; gap: 20px; align-items: flex-start;
    padding: 24px 28px; margin-bottom: 16px;
    font-size: 1.15rem; line-height: 1.8;
    opacity: 0; transform: translateY(30px);
    transition: opacity 0.55s ease, transform 0.55s ease;
}}
.story-block.visible {{ opacity: 1; transform: translateY(0); }}
.story-emoji {{
    flex-shrink: 0; width: 54px; height: 54px;
    display: flex; align-items: center; justify-content: center;
    font-size: 2rem; background: rgba(255,255,255,0.55);
    border: 1px solid rgba(255,255,255,0.88);
    border-radius: 14px;
}}
.story-text {{ flex: 1; min-width: 0; }}

/* ── Tasks section ── */
.tasks-section {{ margin-top: 3rem; }}

.tasks-heading {{
    font-size: 1.4rem; font-weight: 900; color: #fff;
    background: var(--accent);
    display: inline-block;
    padding: 5px 18px; border-radius: 50px;
    margin-bottom: 16px;
    box-shadow: 0 2px 10px rgba(99,102,241,0.35);
}}

/* ── Task card ── */
.task-card {{
    padding: 28px 32px;
    margin-bottom: 16px;
}}

.task-header {{
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 14px;
}}

.task-num {{
    width: 26px; height: 26px;
    background: var(--accent); color: #fff;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 900; font-size: 0.82rem; flex-shrink: 0;
}}

.task-type-label {{
    font-size: 0.72rem; font-weight: 800;
    letter-spacing: 0.07em; text-transform: uppercase;
    padding: 4px 12px; border-radius: 50px;
}}
.task-type-quiz            {{ background: rgba(99,102,241,0.12);  color: #4338ca; }}
.task-type-multiple_choice {{ background: rgba(139,92,246,0.12);  color: #6d28d9; }}
.task-type-drag_and_drop   {{ background: rgba(13,148,136,0.12);  color: #0f766e; }}
.task-type-fill_in_the_blank {{ background: rgba(245,158,11,0.12); color: #b45309; }}
.task-type-ordering        {{ background: rgba(236,72,153,0.12);  color: #be185d; }}

.task-question {{
    font-size: 1.05rem; font-weight: 700;
    color: var(--text-dark); line-height: 1.5;
    margin-bottom: 16px;
}}

/* ── Options (quiz / multiple choice) ── */
.options-grid {{ display: flex; flex-wrap: wrap; gap: 10px; }}

.option-btn {{
    padding: 9px 20px; border-radius: 50px;
    border: 2px solid rgba(99,102,241,0.25);
    background: rgba(255,255,255,0.80);
    color: var(--text-dark);
    font-family: 'Nunito', sans-serif;
    font-size: 1rem; font-weight: 700;
    cursor: pointer;
    transition: all 0.15s ease;
    user-select: none;
}}
.option-btn:hover:not(:disabled):not(.correct):not(.wrong) {{
    background: rgba(99,102,241,0.08);
    border-color: rgba(99,102,241,0.55);
    transform: translateY(-1px);
}}
.option-btn.correct {{
    background: rgba(16,185,129,0.14);
    border-color: var(--green); color: #065f46;
}}
.option-btn.wrong {{
    background: rgba(239,68,68,0.11);
    border-color: var(--red); color: #991b1b;
    animation: shake 0.3s;
}}
.option-btn:disabled {{ cursor: default; }}

@keyframes shake {{
    0%,100% {{ transform: translateX(0); }}
    25% {{ transform: translateX(-5px); }}
    75% {{ transform: translateX(5px); }}
}}

/* ── Check button ── */
.check-btn {{
    display: inline-block;
    margin-top: 14px;
    padding: 10px 28px;
    border-radius: 50px;
    border: none;
    background: var(--accent);
    color: #fff;
    font-family: 'Nunito', sans-serif;
    font-size: 0.95rem;
    font-weight: 800;
    cursor: pointer;
    transition: opacity 0.15s, transform 0.15s;
}}
.check-btn:hover  {{ opacity: 0.87; transform: translateY(-1px); }}
.check-btn:active {{ transform: translateY(0); }}

/* ── Multiple choice (selected state) ── */
.option-btn.selected {{
    background: rgba(99,102,241,0.12);
    border-color: var(--accent);
    color: #4338ca;
}}

/* ── Fill in the blank ── */
.fitb-row {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
}}
.fitb-row .check-btn {{ margin-top: 0; }}
.fill-input {{
    flex: 1; min-width: 160px;
    padding: 10px 18px;
    border-radius: 50px;
    border: 2px solid rgba(99,102,241,0.25);
    background: rgba(255,255,255,0.85);
    font-family: 'Nunito', sans-serif;
    font-size: 1rem; font-weight: 600;
    color: var(--text-dark);
    outline: none;
    transition: border-color 0.15s, background 0.15s;
}}
.fill-input:focus {{ border-color: var(--accent); }}
.fill-input.correct {{ border-color: var(--green); background: rgba(16,185,129,0.09); }}
.fill-input.wrong   {{ border-color: var(--red);   background: rgba(239,68,68,0.08); }}

/* ── Drag and drop ── */
.dnd-wrapper {{ display: flex; flex-direction: column; gap: 14px; }}
.drag-pool {{
    display: flex; flex-wrap: wrap; gap: 10px;
    min-height: 52px; padding: 10px 14px;
    background: rgba(255,255,255,0.45);
    border: 2px dashed rgba(99,102,241,0.28);
    border-radius: 14px;
}}
.drag-item {{
    padding: 8px 20px; border-radius: 50px;
    background: rgba(255,255,255,0.92);
    border: 2px solid rgba(99,102,241,0.28);
    color: var(--text-dark);
    font-weight: 800; font-size: 1rem;
    cursor: grab; user-select: none;
    transition: border-color 0.15s, transform 0.15s, opacity 0.15s;
    box-shadow: 0 2px 8px rgba(0,0,0,0.07);
}}
.drag-item:hover {{ border-color: var(--accent); transform: translateY(-2px); }}
.drag-item.dragging {{ opacity: 0.35; cursor: grabbing; }}
.drop-zones {{ display: flex; gap: 10px; flex-wrap: wrap; }}
.drop-zone {{
    flex: 1; min-width: 100px;
    display: flex; flex-direction: column; align-items: center; gap: 6px;
    padding: 10px 8px; border-radius: 14px;
    border: 2px dashed rgba(99,102,241,0.25);
    background: rgba(255,255,255,0.38);
    transition: all 0.15s;
}}
.drop-zone.drag-over  {{ border-color: var(--accent); background: rgba(99,102,241,0.08); }}
.drop-zone.matched    {{ border-color: var(--green);  background: rgba(16,185,129,0.09); border-style: solid; }}
.drop-zone.wrong-match {{ border-color: var(--red);   background: rgba(239,68,68,0.08);  border-style: solid; }}
.zone-slot {{ min-height: 44px; width: 100%; display: flex; align-items: center; justify-content: center; }}
.zone-label {{ font-size: 0.82rem; font-weight: 700; color: var(--text-muted); text-align: center; }}

/* ── Ordering ── */
.ordering-list {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
.ordering-item {{
    display: flex; align-items: center; gap: 12px;
    padding: 12px 18px; border-radius: 14px;
    background: rgba(255,255,255,0.85);
    border: 2px solid rgba(99,102,241,0.18);
    font-weight: 700; font-size: 1rem; color: var(--text-dark);
    cursor: grab; user-select: none;
    transition: all 0.15s;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}}
.ordering-item:hover {{ border-color: rgba(99,102,241,0.42); }}
.ordering-item.dragging {{ opacity: 0.32; cursor: grabbing; }}
.ordering-item.drag-over {{ border-color: var(--accent); background: rgba(99,102,241,0.07); }}
.ordering-item.correct {{ border-color: var(--green); background: rgba(16,185,129,0.10); }}
.drag-handle {{ color: #9ca3af; font-size: 1.15rem; line-height: 1; flex-shrink: 0; }}

/* ── Feedback ── */
.task-feedback {{
    margin-top: 12px;
    font-size: 0.95rem; font-weight: 700;
    padding: 9px 16px; border-radius: 12px;
    display: none;
}}
.task-feedback.visible {{ display: block; }}
.task-feedback.success {{ background: rgba(16,185,129,0.13); color: #065f46; }}
.task-feedback.error   {{ background: rgba(239,68,68,0.11);  color: #991b1b; }}

/* ── Congrats banner ── */
.congrats-banner {{
    margin-top: 24px; padding: 32px 28px;
    text-align: center;
    opacity: 0; transform: translateY(24px);
    pointer-events: none;
    transition: opacity 0.6s ease, transform 0.6s ease;
}}
.congrats-banner.visible {{
    opacity: 1; transform: translateY(0); pointer-events: auto;
}}
.congrats-trophy {{ font-size: 3rem; line-height: 1; margin-bottom: 12px; }}
.congrats-title  {{ font-size: 1.35rem; font-weight: 900; color: var(--text-dark); margin-bottom: 6px; }}
.congrats-sub    {{ font-size: 1rem; color: var(--text-muted); font-weight: 600; }}

/* ── Responsive ── */
@media (max-width: 480px) {{
    .page {{ padding: 24px 12px 60px; }}
    .task-card {{ padding: 22px 18px; }}
    .options-grid {{ flex-direction: column; }}
    .option-btn {{ width: 100%; text-align: left; }}
    .drop-zones {{ flex-direction: column; }}
    .fitb-row {{ flex-direction: column; align-items: stretch; }}
    .fitb-row .check-btn {{ align-self: flex-start; }}
}}

{theory_css}
</style>
</head>
<body>

{bg_layer_html}
<div class="bg-overlay"></div>

<div class="page">
{story_html}

<div class="tasks-section">
    <span class="tasks-heading">Задания</span>
    {tasks_html}
</div>

<div class="congrats-banner glass-card" id="congrats">
    <div class="congrats-trophy">🏆</div>
    <div class="congrats-title">Урок завершён!</div>
    <div class="congrats-sub">Отличная работа!</div>
</div>

</div>

<script>
var totalTasks = {len(tasks)};
var completedTasks = 0;
var correctCount = 0;
var wrongAttempts = {{}};

function showFeedback(cardId, ok, msg) {{
  var fb = document.getElementById(cardId).querySelector('.task-feedback');
  if (!fb) return;
  fb.textContent = msg || (ok ? 'Правильно!' : 'Попробуй ещё раз!');
  fb.className = 'task-feedback visible ' + (ok ? 'success' : 'error');
  if (!ok) setTimeout(function() {{ fb.className = 'task-feedback'; }}, 1500);
}}

function markDone(cardId, ok) {{
  var card = document.getElementById(cardId);
  card.dataset.done = '1';
  completedTasks++;
  if (ok && !wrongAttempts[cardId]) correctCount++;
  showFeedback(cardId, true, 'Правильно!');
  if (completedTasks >= totalTasks) finishLesson();
}}

/* ── Quiz ── */
function checkQuiz(cardId, btn, correctText) {{
  var card = document.getElementById(cardId);
  if (card.dataset.done === '1') return;
  if (btn.textContent.trim() === correctText) {{
    btn.classList.add('correct');
    card.querySelectorAll('.option-btn').forEach(function(b) {{ b.disabled = true; }});
    markDone(cardId, true);
  }} else {{
    btn.classList.add('wrong');
    wrongAttempts[cardId] = true;
    setTimeout(function() {{ btn.classList.remove('wrong'); }}, 600);
    showFeedback(cardId, false);
  }}
}}

/* ── Multiple choice ── */
function toggleMC(btn) {{
  var card = btn.closest('.task-card');
  if (card.dataset.done === '1') return;
  btn.classList.toggle('selected');
}}

function checkMC(cardId, correctArr) {{
  var card = document.getElementById(cardId);
  if (card.dataset.done === '1') return;
  var selected = [];
  card.querySelectorAll('.option-btn.selected').forEach(function(b) {{ selected.push(b.textContent.trim()); }});
  var ok = selected.length === correctArr.length && correctArr.every(function(c) {{ return selected.indexOf(c) >= 0; }});
  if (ok) {{
    card.querySelectorAll('.option-btn.selected').forEach(function(b) {{ b.classList.add('correct'); }});
    card.querySelectorAll('.option-btn').forEach(function(b) {{ b.disabled = true; }});
    card.querySelector('.check-btn').disabled = true;
    markDone(cardId, true);
  }} else {{
    wrongAttempts[cardId] = true;
    card.querySelectorAll('.option-btn.selected').forEach(function(b) {{
      if (correctArr.indexOf(b.textContent.trim()) < 0) b.classList.add('wrong');
    }});
    setTimeout(function() {{ card.querySelectorAll('.option-btn.wrong').forEach(function(b) {{ b.classList.remove('wrong'); }}); }}, 600);
    showFeedback(cardId, false);
  }}
}}

/* ── Fill in the blank ── */
function checkFill(cardId, correctText) {{
  var card = document.getElementById(cardId);
  if (card.dataset.done === '1') return;
  var input = card.querySelector('.fill-input');
  var val = input.value.trim().toLowerCase();
  if (val === correctText.toLowerCase()) {{
    input.classList.add('correct');
    input.disabled = true;
    card.querySelector('.check-btn').disabled = true;
    markDone(cardId, true);
  }} else {{
    input.classList.add('wrong');
    wrongAttempts[cardId] = true;
    setTimeout(function() {{ input.classList.remove('wrong'); }}, 600);
    showFeedback(cardId, false);
  }}
}}

/* ── Drag and drop ── */
var dndDragging = null;

function dndStart(e) {{
  dndDragging = e.target.closest('.drag-item');
  if (dndDragging) dndDragging.classList.add('dragging');
}}
function dndEnd() {{
  if (dndDragging) dndDragging.classList.remove('dragging');
  dndDragging = null;
  document.querySelectorAll('.drop-zone').forEach(function(z) {{ z.classList.remove('drag-over'); }});
}}
function dndOver(e) {{ e.preventDefault(); e.currentTarget.classList.add('drag-over'); }}
function dndLeave(e) {{ e.currentTarget.classList.remove('drag-over'); }}
function dndDrop(e, cardId) {{
  var correctMap = JSON.parse(e.currentTarget.dataset.correct);
  e.preventDefault();
  var zone = e.currentTarget;
  zone.classList.remove('drag-over');
  if (!dndDragging) return;
  var card = document.getElementById(cardId);
  if (card.dataset.done === '1') return;

  var item = dndDragging.dataset.item;
  var zoneName = zone.dataset.zone;
  var slot = zone.querySelector('.zone-slot');

  if (correctMap[item] === zoneName) {{
    slot.innerHTML = '';
    slot.appendChild(dndDragging);
    dndDragging.style.cursor = 'default';
    dndDragging.setAttribute('draggable', 'false');
    zone.classList.add('matched');
    // Check if all matched
    var allZones = card.querySelectorAll('.drop-zone');
    var matchedCount = card.querySelectorAll('.drop-zone.matched').length;
    if (matchedCount === allZones.length) markDone(cardId, true);
  }} else {{
    zone.classList.add('wrong-match');
    wrongAttempts[cardId] = true;
    setTimeout(function() {{ zone.classList.remove('wrong-match'); }}, 600);
    showFeedback(cardId, false);
  }}
  dndDragging = null;
}}

/* ── Ordering ── */
var ordDragging = null;

function ordStart(e) {{
  ordDragging = e.target.closest('.ordering-item');
  if (ordDragging) ordDragging.classList.add('dragging');
}}
function ordEnd() {{
  if (ordDragging) ordDragging.classList.remove('dragging');
  ordDragging = null;
  document.querySelectorAll('.ordering-item').forEach(function(i) {{ i.classList.remove('drag-over'); }});
}}
function ordOver(e) {{
  e.preventDefault();
  var target = e.currentTarget;
  if (target !== ordDragging) target.classList.add('drag-over');
}}
function ordLeave(e) {{ e.currentTarget.classList.remove('drag-over'); }}
function ordDrop(e) {{
  e.preventDefault();
  var target = e.currentTarget;
  target.classList.remove('drag-over');
  if (!ordDragging || ordDragging === target) return;
  var list = target.parentNode;
  var items = Array.from(list.children);
  var fromIdx = items.indexOf(ordDragging);
  var toIdx = items.indexOf(target);
  if (fromIdx < toIdx) list.insertBefore(ordDragging, target.nextSibling);
  else list.insertBefore(ordDragging, target);
  ordDragging = null;
}}

function checkOrdering(cardId, correctOrder) {{
  var card = document.getElementById(cardId);
  if (card.dataset.done === '1') return;
  var items = Array.from(card.querySelectorAll('.ordering-item'));
  var current = items.map(function(i) {{ return i.dataset.item; }});
  var ok = current.length === correctOrder.length && current.every(function(v, i) {{ return v === correctOrder[i]; }});
  if (ok) {{
    items.forEach(function(i) {{ i.classList.add('correct'); i.setAttribute('draggable', 'false'); i.style.cursor = 'default'; }});
    card.querySelector('.check-btn').disabled = true;
    markDone(cardId, true);
  }} else {{
    wrongAttempts[cardId] = true;
    showFeedback(cardId, false);
  }}
}}

/* ── Touch support for drag ── */
document.addEventListener('touchstart', function(e) {{
  var item = e.target.closest('.drag-item, .ordering-item');
  if (item) {{
    e.preventDefault();
    if (item.classList.contains('drag-item')) dndStart({{target: item}});
    else ordStart({{target: item}});
  }}
}}, {{passive: false}});
document.addEventListener('touchend', function() {{ dndEnd(); ordEnd(); }});

function finishLesson() {{
  document.getElementById('congrats').classList.add('visible');
  if (window.parent && window.parent !== window) {{
    window.parent.postMessage({{
      type: 'kidion_lesson_complete',
      correct: correctCount,
      total: totalTasks
    }}, '*');
  }}
}}

{theory_js}
</script>
</body>
</html>"""

    # Save main HTML
    html_path = os.path.join(_CONTENT_DIR, f"{content_id}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Save print version (simplified)
    print_path = os.path.join(_CONTENT_DIR, f"{content_id}_print.html")
    with open(print_path, "w", encoding="utf-8") as f:
        f.write(html.replace('class="option-btn"', 'class="option-btn" style="cursor:default"'))

    return f"{server_url}/content/{content_id}.html"


def _html_attr(s: str) -> str:
    """Escape a string for safe use inside an HTML attribute value."""
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _build_tasks_html(tasks: list[dict]) -> str:
    """Build interactive task cards HTML for all 5 task types."""
    import json as _json
    html = ""
    for i, task in enumerate(tasks):
        task_type = task.get("type", "quiz")
        question = task.get("question", "")
        card_id = f"task-{i}"
        type_label = _TASK_TYPE_LABELS.get(task_type, "Задание")

        if task_type == "quiz":
            body = _build_quiz(card_id, task)
        elif task_type == "multiple_choice":
            body = _build_mc(card_id, task, _json)
        elif task_type == "drag_and_drop":
            body = _build_dnd(card_id, task, _json)
        elif task_type == "fill_in_the_blank":
            body = _build_fill(card_id, task)
        elif task_type == "ordering":
            body = _build_ordering(card_id, task, _json)
        else:
            body = _build_quiz(card_id, task)

        html += f"""
<div class="task-card glass-card" id="{card_id}" data-done="0">
    <div class="task-header">
        <span class="task-num">{i + 1}</span>
        <span class="task-type-label task-type-{task_type}">{type_label}</span>
    </div>
    <div class="task-question">{question}</div>
    {body}
    <div class="task-feedback"></div>
</div>
"""
    return html


def _build_quiz(card_id: str, task: dict) -> str:
    options = task.get("options", [])
    correct = task.get("correct", "")
    # Escape quotes in correct answer for JS
    correct_js = correct.replace("\\", "\\\\").replace("'", "\\'")
    btns = ""
    for opt in options:
        btns += (
            f'<button class="option-btn" '
            f"onclick=\"checkQuiz('{card_id}', this, '{correct_js}')\">"
            f'{opt}</button>\n'
        )
    return f'<div class="options-grid">{btns}</div>'


def _build_mc(card_id: str, task: dict, _json) -> str:
    options = task.get("options", [])
    correct = task.get("correct", [])
    correct_attr = _html_attr(_json.dumps(correct, ensure_ascii=False))
    btns = ""
    for opt in options:
        btns += f'<button class="option-btn" onclick="toggleMC(this)">{opt}</button>\n'
    return (
        f'<div class="options-grid">{btns}</div>\n'
        f'<button class="check-btn" data-correct="{correct_attr}" '
        f'onclick="checkMC(\'{card_id}\', JSON.parse(this.dataset.correct))">Проверить</button>'
    )


def _build_dnd(card_id: str, task: dict, _json) -> str:
    items = task.get("items", [])
    zones = task.get("zones", [])
    correct = task.get("correct", {})
    correct_attr = _html_attr(_json.dumps(correct, ensure_ascii=False))

    pool = ""
    for item in items:
        pool += (
            f'<div class="drag-item" draggable="true" data-item="{_html_attr(item)}" '
            f'ondragstart="dndStart(event)" ondragend="dndEnd()">{item}</div>\n'
        )

    zones_html = ""
    for zone in zones:
        zones_html += (
            f'<div class="drop-zone" data-zone="{_html_attr(zone)}" data-correct="{correct_attr}" '
            f'ondragover="dndOver(event)" ondragleave="dndLeave(event)" '
            f"ondrop=\"dndDrop(event, '{card_id}')\">"
            f'<div class="zone-slot"></div>'
            f'<div class="zone-label">{zone}</div>'
            f'</div>\n'
        )

    return (
        f'<div class="dnd-wrapper">\n'
        f'<div class="drag-pool">{pool}</div>\n'
        f'<div class="drop-zones">{zones_html}</div>\n'
        f'</div>'
    )


def _build_fill(card_id: str, task: dict) -> str:
    correct = task.get("correct", "")
    correct_js = correct.replace("\\", "\\\\").replace("'", "\\'")
    return (
        f'<div class="fitb-row">\n'
        f'<input class="fill-input" type="text" placeholder="Введи ответ..." autocomplete="off">\n'
        f"<button class=\"check-btn\" onclick=\"checkFill('{card_id}', '{correct_js}')\">Проверить</button>\n"
        f'</div>'
    )


def _build_ordering(card_id: str, task: dict, _json) -> str:
    items = task.get("items", [])
    correct_order = task.get("correct_order", [])
    correct_attr = _html_attr(_json.dumps(correct_order, ensure_ascii=False))

    items_html = ""
    for item in items:
        items_html += (
            f'<div class="ordering-item" draggable="true" data-item="{_html_attr(item)}" '
            f'ondragstart="ordStart(event)" ondragend="ordEnd()" '
            f'ondragover="ordOver(event)" ondragleave="ordLeave(event)" '
            f'ondrop="ordDrop(event)">'
            f'<span class="drag-handle">\u2800\u2800\u2800</span>'
            f'{item}'
            f'</div>\n'
        )

    return (
        f'<div class="ordering-list">{items_html}</div>\n'
        f'<button class="check-btn" data-correct="{correct_attr}" '
        f"onclick=\"checkOrdering('{card_id}', JSON.parse(this.dataset.correct))\">Проверить</button>"
    )
