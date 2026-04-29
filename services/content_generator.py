"""
content_generator.py — Renders lesson JSON into HTML files and saves to content/ directory.
"""

import os

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONTENT_DIR = os.path.join(_BASE_DIR, "content")


def save_lesson_html(image_bytes: bytes | None, lesson_json: dict,
                     content_id: str, server_url: str) -> str:
    """
    Render lesson JSON + optional image into an HTML file.
    Returns the content_url for the lesson.
    """
    os.makedirs(_CONTENT_DIR, exist_ok=True)

    story_blocks = lesson_json.get("story_blocks", [])
    tasks = lesson_json.get("tasks", [])

    # Save image if provided
    image_tag = ""
    if image_bytes:
        img_path = os.path.join(_CONTENT_DIR, f"{content_id}.png")
        with open(img_path, "wb") as f:
            f.write(image_bytes)
        image_tag = f'<img src="{server_url}/content/{content_id}.png" class="lesson-hero" alt="Иллюстрация">'

    # Build story HTML
    story_html = ""
    for block in story_blocks:
        story_html += f'<div class="story-block"><p>{block.get("text", "")}</p></div>\n'

    # Build tasks HTML
    tasks_html = _build_tasks_html(tasks)

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Урок</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Nunito', sans-serif; background: #f8f7ff; color: #333; padding: 20px; max-width: 600px; margin: 0 auto; }}
.lesson-hero {{ width: 100%; border-radius: 16px; margin: 16px 0; }}
.story-block {{ background: white; border-radius: 12px; padding: 16px; margin: 12px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.task-card {{ background: white; border-radius: 16px; padding: 20px; margin: 16px 0; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }}
.task-card h3 {{ color: #6c5ce7; margin-bottom: 12px; }}
.task-option {{ display: block; width: 100%; padding: 12px 16px; margin: 8px 0; border: 2px solid #e0e0e0; border-radius: 12px; background: white; font-size: 16px; cursor: pointer; text-align: left; transition: all 0.2s; }}
.task-option:hover {{ border-color: #6c5ce7; background: #f8f7ff; }}
.task-option.correct {{ border-color: #00b894; background: #d4f5e9; }}
.task-option.wrong {{ border-color: #ff6b6b; background: #ffe0e0; animation: shake 0.3s; }}
@keyframes shake {{ 0%,100% {{ transform: translateX(0); }} 25% {{ transform: translateX(-5px); }} 75% {{ transform: translateX(5px); }} }}
.task-done {{ text-align: center; padding: 12px; color: #00b894; font-weight: bold; font-size: 18px; }}
.all-done {{ text-align: center; padding: 40px 20px; }}
.all-done h2 {{ color: #6c5ce7; font-size: 24px; margin-bottom: 8px; }}
</style>
</head>
<body>
{image_tag}
{story_html}
{tasks_html}
<div id="all-done" style="display:none" class="all-done">
  <h2>Урок завершён!</h2>
  <p>Отличная работа!</p>
</div>
<script>
var totalTasks = {len(tasks)};
var completedTasks = 0;
var correctCount = 0;
var wrongAttempts = {{}};

function checkAnswer(card, btn, correctIdx) {{
  if (card.dataset.done === '1') return;
  var idx = parseInt(btn.dataset.idx);
  if (idx === correctIdx) {{
    btn.classList.add('correct');
    card.dataset.done = '1';
    completedTasks++;
    if (!wrongAttempts[card.id]) correctCount++;
    card.querySelector('.task-done-msg').style.display = 'block';
    if (completedTasks >= totalTasks) finishLesson();
  }} else {{
    btn.classList.add('wrong');
    wrongAttempts[card.id] = true;
    setTimeout(function() {{ btn.classList.remove('wrong'); }}, 600);
  }}
}}

function markWrongAttempt(card) {{
  wrongAttempts[card.id] = true;
}}

function finishLesson() {{
  document.getElementById('all-done').style.display = 'block';
  if (window.parent && window.parent !== window) {{
    window.parent.postMessage({{
      type: 'kidion_lesson_complete',
      correct: correctCount,
      total: totalTasks
    }}, '*');
  }}
}}
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
        f.write(html.replace('class="task-option"', 'class="task-option" style="cursor:default"'))

    return f"{server_url}/content/{content_id}.html"


def _build_tasks_html(tasks: list[dict]) -> str:
    """Build interactive task cards HTML."""
    html = ""
    for i, task in enumerate(tasks):
        question = task.get("question", "")
        options = task.get("options", [])
        correct = task.get("correct_index", 0)
        card_id = f"task-{i}"

        options_html = ""
        for j, opt in enumerate(options):
            options_html += (
                f'<button class="task-option" data-idx="{j}" '
                f'onclick="checkAnswer(document.getElementById(\'{card_id}\'), this, {correct})">'
                f'{opt}</button>\n'
            )

        html += f"""
<div class="task-card" id="{card_id}" data-done="0">
  <h3>Задание {i + 1}</h3>
  <p style="margin-bottom:12px">{question}</p>
  {options_html}
  <div class="task-done-msg task-done" style="display:none">✓ Правильно!</div>
</div>
"""
    return html
