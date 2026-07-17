"""
content_generator.py — Renders lesson JSON into HTML files and saves to content/ directory.
Design: glass morphism matching school-bot (indigo accent, pastel gradients).
"""

import os
import re

from services.theory_renderer import THEORY_CSS, THEORY_JS, render_theory_html

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONTENT_DIR = os.path.join(_BASE_DIR, "content")


def _normalize_utf8_text(value: str) -> str:
    """Convert JSON surrogate pairs to real Unicode before writing HTML."""
    if not re.search(r"[\ud800-\udfff]", value):
        return value
    try:
        return value.encode("utf-16", "surrogatepass").decode("utf-16")
    except UnicodeDecodeError:
        return value.encode("utf-8", "replace").decode("utf-8")

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
<link href="https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}

:root {{
    --bg: #FFF8EC;
    --surface: #FFFFFF;
    --ink: #2A1F1A;
    --ink-soft: #7B6657;
    --primary: #FF6B4A;
    --star: #FFB627;
    --streak: #3DAEA3;
    --line: rgba(42,31,26,.10);
    --green: #3DAEA3;
    --red: #FF6B4A;
    --radius: 20px;
    --subj-accent: #FF6B4A;
    --subj-bg: #FFE3D6;
}}

html, body {{ min-height: 100%; background: var(--bg); }}

.bg-layer {{
    position: fixed; inset: 0; z-index: -2;
    background-size: cover; background-position: center;
    opacity: .18;
}}
body {{
    font-family: 'Nunito', sans-serif;
    color: var(--ink);
    line-height: 1.6;
    min-height: 100vh;
}}

.bg-overlay {{
    position: fixed; inset: 0; z-index: -1;
    background: linear-gradient(180deg,
        rgba(255,248,236,.96) 0%,
        rgba(255,248,236,.98) 35%,
        rgba(255,248,236,.98) 70%,
        rgba(255,248,236,.96) 100%);
}}

.page {{
    max-width: 760px;
    margin: 0 auto;
    padding: 20px 16px 80px;
}}

/* ── Hero image ── */
.lesson-hero {{
    width: 100%;
    border-radius: 24px;
    margin-bottom: 20px;
    box-shadow: 0 24px 60px -28px rgba(0,0,0,.18);
    border: 1px solid var(--line);
}}

/* ── Old-style story blocks (fallback) ── */
.story-block {{
    display: flex; gap: 14px; align-items: flex-start;
    padding: 16px; margin-bottom: 12px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    box-shadow: 0 1px 0 var(--line), 0 8px 20px -14px rgba(0,0,0,.18);
    font-size: 1rem; line-height: 1.55;
    opacity: 0; transform: translateY(24px);
    transition: opacity 0.5s ease, transform 0.5s ease;
}}
.story-block.visible {{ opacity: 1; transform: translateY(0); }}
.story-emoji {{
    flex-shrink: 0; width: 44px; height: 44px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.6rem;
    background: var(--subj-bg);
    border-radius: 12px;
}}
.story-text {{ flex: 1; min-width: 0; }}

/* ── Tasks section ── */
.tasks-section {{ margin-top: 2rem; }}

.tasks-heading {{
    display: inline-flex; align-items: center; gap: 10px;
    font-family: 'Fredoka', sans-serif;
    font-weight: 700;
    font-size: 1.3rem;
    color: var(--ink);
    margin-bottom: 8px;
}}
.tasks-heading::before, .tasks-heading::after {{
    content: ''; height: 1px; width: 48px; background: var(--line);
}}
.tasks-sub {{
    text-align: center;
    font-family: 'Fredoka', sans-serif;
    font-weight: 700;
    font-size: 1rem;
    color: var(--ink-soft);
    margin-bottom: 16px;
}}

/* ── Task card ── */
.task-card {{
    background: var(--surface);
    border-radius: 22px;
    border: 1px solid var(--line);
    box-shadow: 0 2px 0 var(--line), 0 16px 30px -22px rgba(0,0,0,.20);
    padding: 16px 16px 18px;
    margin-bottom: 18px;
    position: relative;
    overflow: hidden;
}}

.task-header {{
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 12px;
}}

.task-num {{
    font-size: 0.78rem; font-weight: 800; color: var(--ink-soft);
}}

.task-type-label {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; border-radius: 999px;
    font-size: 0.68rem; font-weight: 800;
    letter-spacing: 0.06em; text-transform: uppercase;
}}
.task-type-label::before {{
    content: ''; width: 5px; height: 5px; border-radius: 50%;
}}
.task-type-quiz            {{ background: rgba(255,107,74,0.08); color: var(--primary); }}
.task-type-quiz::before    {{ background: var(--primary); }}
.task-type-multiple_choice {{ background: rgba(61,174,163,0.08); color: var(--streak); }}
.task-type-multiple_choice::before {{ background: var(--streak); }}
.task-type-drag_and_drop   {{ background: rgba(255,182,39,0.08); color: #8C5A00; }}
.task-type-drag_and_drop::before {{ background: #FFB627; }}
.task-type-fill_in_the_blank {{ background: rgba(124,179,66,0.08); color: #456B1F; }}
.task-type-fill_in_the_blank::before {{ background: #7CB342; }}
.task-type-ordering        {{ background: rgba(142,107,255,0.08); color: #5A3DBE; }}
.task-type-ordering::before {{ background: #8E6BFF; }}

.task-question {{
    font-family: 'Fredoka', sans-serif;
    font-weight: 600;
    font-size: 1.1rem;
    color: var(--ink);
    line-height: 1.25;
    margin-bottom: 12px;
}}

/* ── Options (quiz / multiple choice) ── */
.options-grid {{ display: flex; flex-direction: column; gap: 8px; }}

.option-btn {{
    padding: 12px 14px; border-radius: 14px;
    border: 1.5px solid var(--line);
    background: var(--bg);
    color: var(--ink);
    font-family: 'Nunito', sans-serif;
    font-size: 0.95rem; font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
    user-select: none;
    display: flex; align-items: center; gap: 10px;
    text-align: left;
    width: 100%;
}}
.option-btn:hover:not(:disabled):not(.correct):not(.wrong) {{
    background: rgba(255,107,74,0.05);
    border-color: var(--primary);
}}
.option-btn.correct {{
    background: rgba(61,174,163,0.1);
    border-color: var(--streak);
}}
.option-btn.wrong {{
    background: rgba(255,107,74,0.08);
    border-color: var(--primary);
    animation: shake 0.4s;
}}
.option-btn:disabled {{ cursor: default; }}

@keyframes shake {{
    0%,100% {{ transform: translateX(0); }}
    20% {{ transform: translateX(-4px); }}
    40% {{ transform: translateX(4px); }}
    60% {{ transform: translateX(-2px); }}
    80% {{ transform: translateX(2px); }}
}}

/* ── Check button ── */
.check-btn {{
    display: inline-block;
    margin-top: 14px;
    padding: 12px 28px;
    border-radius: 14px;
    border: none;
    background: var(--primary);
    color: #fff;
    font-family: 'Fredoka', sans-serif;
    font-size: 0.95rem;
    font-weight: 700;
    cursor: pointer;
    transition: opacity 0.15s, transform 0.15s;
    box-shadow: 0 10px 24px -10px rgba(255,107,74,.45);
}}
.check-btn:hover  {{ opacity: 0.9; transform: translateY(-1px); }}
.check-btn:active {{ transform: translateY(0); }}

/* ── Multiple choice (selected state) ── */
.option-btn.selected {{
    background: rgba(255,107,74,0.08);
    border-color: var(--primary);
    color: var(--ink);
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
    padding: 12px 18px;
    border-radius: 14px;
    border: 2px solid var(--line);
    background: var(--bg);
    font-family: 'Fredoka', sans-serif;
    font-size: 1.1rem; font-weight: 700;
    color: var(--ink);
    outline: none;
    transition: border-color 0.15s, background 0.15s;
}}
.fill-input:focus {{ border-color: var(--primary); }}
.fill-input.correct {{ border-color: var(--streak); background: rgba(61,174,163,0.06); }}
.fill-input.wrong   {{ border-color: var(--primary); background: rgba(255,107,74,0.06); }}

/* ── Drag and drop ── */
.dnd-wrapper {{ display: flex; flex-direction: column; gap: 10px; }}
.drag-pool {{
    display: flex; flex-wrap: wrap; gap: 8px;
    min-height: 48px; padding: 10px 12px;
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: 14px;
}}
.drag-item {{
    padding: 6px 14px; border-radius: 999px;
    background: var(--surface);
    border: 1.5px solid var(--primary);
    color: var(--primary);
    font-family: 'Fredoka', sans-serif;
    font-weight: 700; font-size: 0.95rem;
    cursor: grab; user-select: none;
    transition: all 0.15s;
    box-shadow: 0 4px 10px -6px rgba(255,107,74,.45);
}}
.drag-item:hover {{ transform: translateY(-2px); }}
.drag-item.dragging {{ opacity: 0.35; cursor: grabbing; }}
.drop-zones {{ display: flex; flex-direction: column; gap: 8px; }}
.drop-zone {{
    display: flex; align-items: center; gap: 10px;
    padding: 8px 10px; border-radius: 14px;
    border: 1.5px dashed var(--line);
    background: var(--bg);
    transition: all 0.15s;
}}
.drop-zone.drag-over  {{ border-color: var(--star); background: rgba(255,182,39,.08); box-shadow: 0 0 0 6px rgba(255,182,39,.14); }}
.drop-zone.matched    {{ border-color: var(--streak); background: rgba(61,174,163,.06); border-style: solid; }}
.drop-zone.wrong-match {{ border-color: var(--primary); background: rgba(255,107,74,.06); border-style: solid; }}
.zone-slot {{ min-height: 38px; flex: 0 0 70px; display: flex; align-items: center; justify-content: center; border-radius: 999px; border: 2px dashed var(--line); }}
.zone-slot:has(.drag-item) {{ border: none; }}
.zone-label {{ font-size: 0.85rem; font-weight: 700; color: var(--ink); flex: 1; }}

/* ── Ordering ── */
.ordering-list {{ list-style: none; display: flex; flex-direction: column; gap: 6px; }}
.ordering-item {{
    display: flex; align-items: center; gap: 10px;
    padding: 10px 12px; border-radius: 14px;
    background: var(--bg);
    border: 1.5px solid var(--line);
    font-family: 'Fredoka', sans-serif;
    font-weight: 700; font-size: 1.1rem; color: var(--subj-accent);
    cursor: grab; user-select: none;
    transition: all 0.15s;
}}
.ordering-item:hover {{ border-color: var(--primary); }}
.ordering-item.dragging {{ opacity: 0.32; cursor: grabbing; }}
.ordering-item.drag-over {{ border-color: var(--star); background: rgba(255,182,39,.08); }}
.ordering-item.correct {{ border-color: var(--streak); background: rgba(61,174,163,.06); }}
.drag-handle {{ color: var(--ink-soft); font-size: 1rem; line-height: 1; flex-shrink: 0; display: flex; flex-direction: column; gap: 2px; }}
.drag-handle span {{ width: 14px; height: 2px; background: var(--ink-soft); border-radius: 1px; display: block; }}

/* ── Feedback ── */
.task-feedback {{
    margin-top: 12px;
    font-size: 0.85rem; font-weight: 700;
    padding: 8px 12px; border-radius: 12px;
    display: none;
}}
.task-feedback.visible {{ display: flex; align-items: center; gap: 6px; }}
.task-feedback.success {{ background: rgba(61,174,163,.08); color: var(--streak); }}
.task-feedback.error   {{ background: rgba(255,107,74,.08); color: var(--primary); }}

/* ── Congrats banner ── */
.congrats-banner {{
    margin-top: 24px; padding: 22px 18px 18px;
    text-align: center;
    background: linear-gradient(160deg, var(--subj-bg), var(--surface) 65%);
    border: 1px solid var(--line);
    border-radius: 24px;
    position: relative; overflow: hidden;
    opacity: 0; transform: translateY(24px);
    pointer-events: none;
    transition: opacity 0.6s ease, transform 0.6s ease;
}}
.congrats-banner.visible {{
    opacity: 1; transform: translateY(0); pointer-events: auto;
}}
.congrats-trophy {{
    width: 88px; height: 88px; border-radius: 50%;
    background: linear-gradient(160deg, var(--star), var(--primary));
    margin: 0 auto; display: flex; align-items: center; justify-content: center;
    font-size: 46px; line-height: 1;
    box-shadow: 0 14px 30px -10px rgba(255,107,74,.5);
    border: 4px solid var(--surface);
    animation: kFloat 3s ease-in-out infinite;
    position: relative; z-index: 1;
}}
.congrats-title {{
    margin: 14px 0 4px;
    font-family: 'Fredoka', sans-serif;
    font-weight: 700;
    font-size: 1.6rem;
    color: var(--ink);
    letter-spacing: -.01em;
}}
.congrats-sub {{ font-size: 0.95rem; color: var(--ink-soft); font-weight: 600; }}
@keyframes kFloat {{ 0%,100%{{transform:translateY(0)}} 50%{{transform:translateY(-8px)}} }}

/* ── Responsive ── */
@media (max-width: 480px) {{
    .page {{ padding: 14px 12px 60px; }}
    .task-card {{ padding: 14px 14px 16px; }}
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
    <div style="text-align:center;padding:22px 16px 4px;">
      <span class="tasks-heading">Теперь твоя очередь</span>
    </div>
    {tasks_html}
</div>

<div class="congrats-banner" id="congrats">
    <div class="congrats-trophy">🏆</div>
    <div class="congrats-title">Урок завершён!</div>
    <div class="congrats-sub">Отличная работа! 🎉</div>
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
  fb.innerHTML = (ok ? '\u2728 ' : '\uD83D\uDCAA ') + (msg || (ok ? 'Точно! Молодец!' : 'Почти! Попробуй ещё раз'));
  fb.className = 'task-feedback visible ' + (ok ? 'success' : 'error');
  if (!ok) setTimeout(function() {{ fb.className = 'task-feedback'; }}, 2000);
}}

function markDone(cardId, ok) {{
  var card = document.getElementById(cardId);
  card.dataset.done = '1';
  completedTasks++;
  if (ok && !wrongAttempts[cardId]) correctCount++;
  showFeedback(cardId, true, 'Точно! Молодец!');
  // Notify parent about progress
  if (window.parent && window.parent !== window) {{
    window.parent.postMessage({{
      type: 'kidion_task_progress',
      completed: completedTasks
    }}, '*');
  }}
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
    html = _normalize_utf8_text(html)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

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
<div class="task-card" id="{card_id}" data-done="0">
    <div class="task-header">
        <span class="task-type-label task-type-{task_type}">{type_label}</span>
        <span class="task-num">{i + 1}<span style="opacity:.4">/{len(tasks)}</span></span>
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
