/**
 * Kidion — Kid Interface JS
 * Vanilla JS, no external dependencies
 */

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

async function apiGet(url) {
  const res = await fetch(url, { credentials: 'same-origin' });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return { status: res.status, data: await res.json() };
}

// ---------------------------------------------------------------------------
// Logout
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  const logoutBtn = document.getElementById('btn-logout');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      await apiPost('/api/kid/logout', {});
      window.location.href = '/kid/login';
    });
  }
  setupParentGateLinks();

  // Run page-specific init
  const page = document.body.dataset.page;
  if (page === 'login') initLoginPage();
  if (page === 'home')  initHomePage();
  if (page === 'lesson') initLessonPage();
  if (page === 'result') initResultPage();
});

function setupParentGateLinks() {
  const gate = document.getElementById('kid-parent-gate');
  const question = document.getElementById('kid-parent-gate-question');
  const answer = document.getElementById('kid-parent-gate-answer');
  const error = document.getElementById('kid-parent-gate-error');
  const checkBtn = document.getElementById('kid-parent-gate-check');
  const cancelBtn = document.getElementById('kid-parent-gate-cancel');
  if (!gate || !question || !answer || !checkBtn || !cancelBtn) return;

  let target = '';
  let verifying = false;

  async function openGate(nextTarget) {
    target = nextTarget;
    error.hidden = true;
    answer.value = '';
    question.textContent = '...';
    gate.classList.add('is-open');
    gate.setAttribute('aria-hidden', 'false');
    try {
      const res = await fetch('/api/kid/parent-gate/challenge', {
        method: 'POST',
        credentials: 'same-origin',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'challenge_failed');
      question.textContent = data.question;
      setTimeout(() => answer.focus(), 80);
    } catch (e) {
      question.textContent = '';
      error.textContent = 'Не получилось открыть проверку. Попробуйте ещё раз.';
      error.hidden = false;
    }
  }

  async function verifyGate() {
    if (verifying) return;
    verifying = true;
    error.hidden = true;
    try {
      const { status, data } = await apiPost('/api/kid/parent-gate/verify', {
        answer: parseInt(answer.value, 10),
        target,
      });
      if (status === 200 && data.ok) {
        window.location.href = data.redirect;
        return;
      }
      error.textContent = data.error === 'challenge_expired'
        ? 'Проверка устарела. Откройте её ещё раз.'
        : 'Неправильно, попробуйте ещё раз.';
      error.hidden = false;
      answer.value = '';
      answer.focus();
    } catch (e) {
      error.textContent = 'Ошибка соединения.';
      error.hidden = false;
    } finally {
      verifying = false;
    }
  }

  document.querySelectorAll('[data-parent-gate-target]').forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      openGate(link.dataset.parentGateTarget || link.getAttribute('href') || '/dashboard');
    });
  });
  checkBtn.addEventListener('click', verifyGate);
  answer.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') verifyGate();
  });
  cancelBtn.addEventListener('click', () => {
    gate.classList.remove('is-open');
    gate.setAttribute('aria-hidden', 'true');
  });
}

// ---------------------------------------------------------------------------
// Login Page: PIN keyboard
// ---------------------------------------------------------------------------

function initLoginPage() {
  const pinDigits = [];
  const PIN_LENGTH = 4;

  const dots = document.querySelectorAll('.pin-dot');
  const errorEl = document.getElementById('pin-error');
  const childId = document.getElementById('child-id-input')?.value;
  let submitting = false;

  function updateDots() {
    dots.forEach((d, i) => {
      d.classList.toggle('filled', i < pinDigits.length);
    });
  }

  function showError(msg) {
    if (errorEl) {
      errorEl.textContent = msg;
      errorEl.style.display = 'block';
    }
    dots.forEach(d => {
      d.classList.add('shake');
      setTimeout(() => d.classList.remove('shake'), 400);
    });
    pinDigits.length = 0;
    updateDots();
    submitting = false;
  }

  async function submitPin() {
    if (pinDigits.length !== PIN_LENGTH || submitting) return;
    submitting = true;
    const pin = pinDigits.join('');
    const cid = parseInt(childId, 10);
    if (!cid) {
      showError('Выбери ребёнка!');
      return;
    }

    try {
      const { status, data } = await apiPost('/api/kid/auth', { child_id: cid, pin });
      if (status === 200) {
        window.location.href = '/kid/home';
      } else {
        showError('Неверный PIN-код. Попробуй ещё раз!');
      }
    } catch (e) {
      showError('Ошибка соединения');
    }
  }

  document.querySelectorAll('.pin-btn[data-digit]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (pinDigits.length >= PIN_LENGTH) return;
      if (errorEl) { errorEl.textContent = ''; errorEl.style.display = 'none'; }
      pinDigits.push(btn.dataset.digit);
      updateDots();
      // Auto-submit after 4 digits
      if (pinDigits.length === PIN_LENGTH) {
        setTimeout(submitPin, 200);
      }
    });
  });

  const backBtn = document.querySelector('.pin-btn.pin-backspace');
  if (backBtn) {
    backBtn.addEventListener('click', () => {
      if (errorEl) { errorEl.textContent = ''; errorEl.style.display = 'none'; }
      pinDigits.pop();
      updateDots();
      submitting = false;
    });
  }

  // "Войти" button
  const submitBtn = document.getElementById('pin-submit-btn');
  if (submitBtn) {
    submitBtn.addEventListener('click', submitPin);
  }

  updateDots();
}

// ---------------------------------------------------------------------------
// Home Page: Load lessons
// ---------------------------------------------------------------------------

async function initHomePage() {
  const currentWrap = document.getElementById('current-lesson-wrap');
  const historyWrap = document.getElementById('history-wrap');

  try {
    const data = await apiGet('/api/kid/lessons');

    if (currentWrap) {
      if (data.current) {
        const lesson = data.current;
        const statusText = lesson.status === 'pending' ? '⏳ Готовится...' : '';
        const canStart = lesson.status === 'done' && lesson.content_url;
        const btnHtml = canStart
          ? `<a href="/kid/lesson/${lesson.id}" class="btn-start">Начать! 🚀</a>`
          : lesson.status === 'pending'
            ? `<span class="btn-start" style="opacity:0.6;cursor:default">Готовится... ⏳</span>`
            : `<a href="/kid/lesson/${lesson.id}" class="btn-start">Начать! 🚀</a>`;

        currentWrap.innerHTML = `
          <div class="current-lesson-card">
            <div class="current-lesson-label">Твой урок</div>
            <div class="current-lesson-title">${escHtml(lesson.topic_title)}</div>
            <div class="current-lesson-subject">${escHtml(lesson.subject)}</div>
            ${btnHtml}
          </div>
        `;
      } else {
        currentWrap.innerHTML = `
          <div class="empty-state">
            <div class="empty-state-icon">📚</div>
            <div class="empty-state-text">Попроси маму или папу создать урок!</div>
          </div>
        `;
      }
    }

    if (historyWrap) {
      if (data.history && data.history.length > 0) {
        document.getElementById('history-section')?.removeAttribute('hidden');
        historyWrap.innerHTML = data.history.map(lesson => `
          <a href="/kid/result/${lesson.id}" class="history-card">
            <div class="history-card-subject">${escHtml(lesson.subject)}</div>
            <div class="history-card-title">${escHtml(lesson.topic_title)}</div>
            <div class="stars-row">${renderStars(lesson.stars)}</div>
          </a>
        `).join('');
      }
    }
  } catch (err) {
    console.error('Failed to load lessons:', err);
    if (currentWrap) {
      currentWrap.innerHTML = `<div class="spinner"></div>`;
    }
  }
}

function renderStars(stars) {
  return [1, 2, 3].map(i =>
    `<span class="star ${i <= stars ? 'earned' : ''}">★</span>`
  ).join('');
}

function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ---------------------------------------------------------------------------
// Lesson Page: "Я закончил!" modal
// ---------------------------------------------------------------------------

function initLessonPage() {
  const finishBtn = document.getElementById('btn-finish');
  const modal = document.getElementById('finish-modal');
  const lessonId = document.getElementById('lesson-id')?.value;
  let selectedScore = null;

  if (!finishBtn || !modal) return;

  finishBtn.addEventListener('click', () => {
    modal.classList.add('active');
    selectedScore = null;
    document.querySelectorAll('.score-btn').forEach(b => b.classList.remove('selected'));
  });

  // Close modal on overlay click
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.remove('active');
  });

  document.querySelectorAll('.score-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      selectedScore = parseInt(btn.dataset.score, 10);
      document.querySelectorAll('.score-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
    });
  });

  const confirmBtn = document.getElementById('btn-confirm-finish');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', async () => {
      if (selectedScore === null) {
        // Shake score buttons
        document.querySelector('.score-buttons')?.classList.add('shake');
        setTimeout(() => document.querySelector('.score-buttons')?.classList.remove('shake'), 400);
        return;
      }

      confirmBtn.disabled = true;
      confirmBtn.textContent = 'Сохраняю...';

      try {
        const { status, data } = await apiPost(`/api/lessons/${lessonId}/result`, {
          correct_answers: selectedScore,
          total_answers: 5,
        });

        if (status === 200) {
          window.location.href = `/kid/result/${lessonId}`;
        } else {
          confirmBtn.disabled = false;
          confirmBtn.textContent = 'Готово!';
        }
      } catch (err) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Готово!';
        console.error(err);
      }
    });
  }
}

// ---------------------------------------------------------------------------
// Result Page: Animate stars
// ---------------------------------------------------------------------------

function initResultPage() {
  const stars = document.querySelectorAll('.result-star.earned');
  stars.forEach((star, i) => {
    star.style.animationDelay = `${0.1 + i * 0.2}s`;
    star.style.animationFillMode = 'both';
  });
}

// ---------------------------------------------------------------------------
// Global: kidLogout (used from kid/base.html nav bar)
// ---------------------------------------------------------------------------

async function kidLogout() {
  try {
    await apiPost('/api/kid/logout', {});
  } catch (e) {}
  window.location.href = '/kid/login';
}
