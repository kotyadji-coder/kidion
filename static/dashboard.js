'use strict';

document.addEventListener('DOMContentLoaded', async function () {
    const grid = document.getElementById('children-grid');
    if (!grid) return;

    try {
        const resp = await fetch('/api/children');
        if (!resp.ok) return;
        const children = await resp.json();

        if (children.length === 0) {
            grid.innerHTML = '<p class="empty-state">У вас пока нет профилей детей. Добавьте первого ребёнка!</p>';
            return;
        }

        // Hide "add child" button if 3 children
        if (children.length >= 3) {
            var addBtn = document.getElementById('add-child-btn');
            if (addBtn) addBtn.style.display = 'none';
        }

        for (var i = 0; i < children.length; i++) {
            var child = children[i];
            var card = await buildChildCard(child);
            grid.appendChild(card);
        }
    } catch (e) {
        grid.innerHTML = '<p class="error">Ошибка загрузки данных</p>';
    }
});


async function buildChildCard(child) {
    var card = document.createElement('div');
    card.className = 'child-card card';

    // Load stats
    var stats = null;
    try {
        var resp = await fetch('/api/children/' + child.id + '/stats');
        if (resp.ok) stats = await resp.json();
    } catch (e) {}

    // Load program progress
    var progress = null;
    try {
        var resp2 = await fetch('/api/children/' + child.id + '/program-progress');
        if (resp2.ok) progress = await resp2.json();
    } catch (e) {}

    var genderEmoji = child.gender === 'girl' ? '👧' : '👦';
    var streakText = stats ? stats.current_streak + ' дн.' : '0 дн.';
    var lessonsText = stats ? stats.total_lessons : 0;

    // Build program progress bars
    var progressHtml = '';
    if (progress && progress.subjects && progress.subjects.length > 0) {
        progressHtml += '<div class="child-card__progress">';
        for (var i = 0; i < progress.subjects.length; i++) {
            var s = progress.subjects[i];
            var subjectIcon = s.subject === 'math' ? '📐' : '📝';
            var subjectName = s.subject === 'math' ? 'Мат.' : 'Рус.';
            progressHtml += '<div class="mini-progress">';
            progressHtml += '<span class="mini-progress__label">' + subjectIcon + ' ' + subjectName + '</span>';
            progressHtml += '<div class="mini-progress__bar"><div class="mini-progress__fill" style="width:' + s.percent + '%"></div></div>';
            progressHtml += '<span class="mini-progress__pct">' + s.percent + '%</span>';
            progressHtml += '</div>';
        }
        progressHtml += '</div>';
    }

    // Active mode info
    var modeHtml = '';
    if (progress && progress.active_weekly_plan) {
        modeHtml += '<div class="child-card__mode"><span class="badge badge--blue">📅 Тема недели</span> ' +
            escapeHtml(progress.active_weekly_plan.unit_title) + '</div>';
    }
    if (progress && progress.active_enrollments && progress.active_enrollments.length > 0) {
        for (var j = 0; j < progress.active_enrollments.length; j++) {
            var enr = progress.active_enrollments[j];
            var enrName = enr.subject === 'math' ? 'Математика' : 'Русский';
            modeHtml += '<div class="child-card__mode"><span class="badge badge--green">🗺️ Маршрут</span> ' + enrName + '</div>';
        }
    }

    card.innerHTML =
        '<div class="child-card__header">' +
        '  <span class="child-card__avatar">' + genderEmoji + '</span>' +
        '  <div>' +
        '    <h3 class="child-card__name">' + escapeHtml(child.name) + '</h3>' +
        '    <span class="child-card__meta">' + child.grade + ' класс · ' + escapeHtml(child.universe) + '</span>' +
        '  </div>' +
        '</div>' +
        '<div class="child-card__stats">' +
        '  <div class="stat"><span class="stat__value">' + lessonsText + '</span><span class="stat__label">уроков</span></div>' +
        '  <div class="stat"><span class="stat__value">🔥 ' + streakText + '</span><span class="stat__label">серия</span></div>' +
        '</div>' +
        progressHtml +
        modeHtml +
        '<div class="child-card__actions">' +
        '  <a href="/children/' + child.id + '" class="btn btn--primary btn--sm">Открыть</a>' +
        '  <a href="/kid/login?child_id=' + child.id + '" class="btn btn--outline btn--sm">Кабинет ребёнка</a>' +
        '</div>';

    return card;
}

function escapeHtml(str) {
    return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
