# Kidion Open Business Decisions

These items need owner decisions before implementation because they change the
paid generation flow or the product experience.

## 1. Enrollment And First Lesson Generation

Current behavior: enrolling a child in a subject creates route progress and
automatically starts generation for the first lesson.

Decision needed:

- Keep automatic first-lesson generation.
- Or enroll without generation and show a parent button: `Создать первый урок`.
- Or make automatic generation free only for the first subject, then manual.

Risk: automatic generation is convenient, but it can spend AI tokens when a
real user or operator only wanted to create a route.

## 2. Parent UX For Full-Year Routes

Current data shape: 33 weekly missions in grade 1 and 34 weekly missions in
grades 2-6, each with 5 lessons.

Decision needed:

- Show all missions as one long route.
- Or group missions by month/quarter.
- Or show only the current month by default with expandable future missions.

Risk: all 165/170 lessons are technically correct, but a long ungrouped list
may feel heavy in the parent and child UI.

## 3. Paid End-To-End Smoke

Current safe checks prove route data, enrollment logic, and UI smoke without
calling paid AI providers.

Decision needed:

- Allow one real lesson generation smoke after major curriculum changes.
- Or keep all routine verification mocked/safe and test real generation only
manually.

Risk: real generation is the strongest product proof, but it can spend tokens
and may send external notifications if a safety fence regresses.

## 4. Methodical Curriculum Editing Depth

Current route files have a strict school weekly skeleton and consistent
five-step lesson roles.

Decision needed:

- Accept this as MVP and improve from usage data.
- Or do a manual methodologist pass before driving traffic.

Risk: the structure is valid, but many lesson titles and hints are intentionally
templated until a subject-by-subject editorial pass is done.
