# Design Brief: Lesson Page + Printable Worksheets

## Context

**Kidion.ru** — educational platform for children ages 6-10. AI generates personalized lessons set in each child's unique universe. Children complete lessons on mobile (90% traffic), earn stars, customize their character.

**Stack:** HTML/CSS/vanilla JS (no frameworks). Jinja2 templates. No dark theme.

**Target audience:** children 6-10 years old (grades 1-4). Using parent's phone or tablet. Mobile-first.

---

## PART 1: Lesson Page (`/kid/lesson/{id}`)

### What It Is

A page where a child completes one lesson. The lesson content (theory + 5 interactive tasks) lives inside an iframe. The designer's job is:
1. **The wrapper** around the iframe (top bar, progress, bottom bar)
2. **The iframe content itself** — theory blocks + interactive task cards

### Current State (Problems)

- Minimal top bar (back arrow + title + print button) + naked iframe
- No sense of adventure or gamification
- Child doesn't feel progress during the lesson
- No visual connection to the child's personal universe/character

---

### A. Wrapper Design (lesson.html)

#### Top Bar
- Back arrow (to /kid/home)
- Subject name (small text, e.g. "Математика")
- Lesson title (e.g. "Дроби: что это и зачем?")
- Print button ("Квест") — opens printable worksheet PDF
- **NEW: Progress indicator** — "Задание 3 из 5" (data comes from iframe via postMessage)

#### Progress Bar
- Horizontal bar showing task completion (0→5)
- Updates live as child answers tasks inside iframe
- Subtle animation on each step completion (pulse, glow, or star pop)
- Should feel like an adventure quest progress, not a boring loading bar

#### Bottom Bar
- "Урок создан с помощью ИИ" + "Пожаловаться" button (existing, keep small)
- Auto-save status when lesson completes

#### States
- **Loading:** spinner + "Урок готовится..." (lesson not yet generated)
- **Active:** iframe fills remaining screen height
- **Completed:** auto-redirect to results page

#### Constraints
- On mobile — maximize iframe area, minimal chrome
- Top bar must be compact (40-48px max)
- Progress bar can be inside top bar or just below it
- Do NOT obscure iframe content

---

### B. Lesson Content Design (inside iframe)

The iframe contains a self-contained HTML page with two sections:

#### Section 1: Theory (explanation)

AI generates structured JSON blocks. A renderer converts them to HTML. **15 block types exist:**

| Block Type | Purpose | Visual Idea |
|-----------|---------|-------------|
| **title** | Lesson title with emoji | Large heading + floating animated emoji |
| **speech** | Character dialogue | Avatar circle + speech bubble with character name |
| **text** | Regular paragraph | Clean text, key terms highlighted with colored `<span>` |
| **emoji_hero** | Visual quantity | Large emoji repeated to show quantity (e.g. 🍎🍎🍎 = 3) |
| **fact** | "Remember!" box | Accent left border (green), bold label, standout background |
| **diagram** | Process/flow | Horizontal chain: [Step 1] → [Step 2] → [Step 3] with icons |
| **compare** | Comparison rows | Table-like rows with icon + label + value per row |
| **before_after** | Side-by-side | Two columns: green "Before" vs red "After" |
| **steps** | Numbered instructions | Numbered list with emoji icons per step |
| **keywords** | Vocabulary | Pill-shaped tags in a row (like hashtags) |
| **example** | Math example | Centered large expression + explanation below |
| **scale** | Progress/percentage | Horizontal bars with gradient fill showing percentage |
| **grid** | Visual grid | Grid of filled/empty cells with emoji (e.g. colored/uncolored) |
| **list** | Bulleted list | Items with emoji bullet icons |
| **summary** | Final recap | Highlighted box with checkmark items |

**Current styling:** Glass morphism cards (70% white, 16px backdrop blur, indigo accent #6366f1), scroll-triggered fade-in animations, Nunito font.

**What needs design:**
- Modern, child-friendly visual language for each block type
- Blocks should feel like parts of an adventure/story, not a textbook
- Cards should have personality — rounded corners, subtle shadows, maybe themed borders
- Animations: scroll-triggered entrance (fade + slide), hover micro-interactions
- The "speech" block should feel like the child's personal character is talking to them
- "fact" blocks should feel important but fun (not like a warning)
- "diagram" and "steps" should feel like a quest/journey
- Mobile-first: single column, generous touch targets

#### Section 2: Interactive Tasks (5 per lesson)

After theory, child completes 5 tasks. **5 task types:**

| Task Type | Interaction | Visual |
|-----------|------------|--------|
| **quiz** | Single choice (4 options) | Option pills/cards, tap to select |
| **multiple_choice** | Multi-select (4-6 options) | Checkable cards, confirm button |
| **drag_and_drop** | Drag items to zones | Draggable chips + drop zones with labels |
| **fill_in_the_blank** | Text input | Sentence with highlighted blank, keyboard input |
| **ordering** | Reorder list | Draggable numbered items, snap into position |

**Current styling:** Glass cards with colored type labels, option pills with correct/wrong states (green glow / red shake).

**What needs design:**
- Each task should feel like a mini-game challenge
- Clear visual states: default → selected → correct (celebrate!) → wrong (gentle, encouraging)
- Correct answer: confetti burst or star animation on the card
- Wrong answer: subtle shake + encouraging message, not punishing
- Task number indicator: "1/5", "2/5" etc. — visible but not distracting
- Cards should have type-specific personality (quiz feels different from drag-and-drop)
- Touch-friendly: large tap targets (min 44px), clear drag handles
- Smooth transitions between tasks

#### Overall Iframe Page
- Optional background: AI-generated image (PNG) with overlay, or gradient
- Scrollable: theory blocks first, then tasks
- Celebration banner at the end: "Молодец! Все задания выполнены!" with trophy/stars
- Color palette: keep indigo (#6366f1) as accent, but open to a warmer/more playful palette
- Font: Nunito or similar rounded, child-friendly font

---

## PART 2: Printable Worksheets

### What They Are

Each lesson has a companion **printable worksheet** — a single A4 page with 4 tasks that the child solves on paper. Lesson 5 of each topic is a special full-page **activity** (cipher, cafe, or shop theme).

### Current State

Clean but clinical design — indigo/white, functional but lacks personality. Looks like a standard school worksheet, not something from the child's personal universe.

---

### A. Regular Worksheet (Lessons 1-4)

**Layout:** Single A4 page, portrait orientation.

#### Header
- Brand mark "KIDION"
- Lesson number badge (e.g. "Урок 3")
- Lesson title (large, bold)
- Metadata line: subject / grade / topic name
- Child's name (personalized)

#### Task Grid
- 4 tasks per page
- 2-column grid for compact tasks, full-width for wide tasks
- Each task has: number circle, type badge, instruction text, task-specific content

#### 24 Task Types (need visual design for each):

**Universal (all subjects):**
| Type | Visual Description |
|------|-------------------|
| **coloring** | Image (220x220) floated right + writing prompt + lined area left |
| **matching** | Two columns (numbered 1-4 vs lettered A-D) with dotted connectors |
| **fill_blanks** | Text paragraph with underlined blank spaces |
| **sorting_table** | Word bank (dashed border box) + 2-column table below |
| **odd_one_out** | 4 item cards + "Which is odd? Because:" writing line |

**Math:**
| Type | Visual Description |
|------|-------------------|
| **grid_maze** | START label → 4x4 grid → FINISH label, trace correct path |
| **number_pyramid** | Triangle of cells (filled=blue, empty=dashed), fill numbers |
| **magic_square** | 3x3 grid, some cells filled, complete to reach target sum |
| **comparison_chain** | Value pairs with empty circle between for >, <, = |
| **expression_builder** | Equations with empty circles for +/- operators |
| **number_sequence** | Number rows with filled/dashed cells, arrows between |

**Russian Language:**
| Type | Visual Description |
|------|-------------------|
| **anagram** | Scrambled letters in boxes + hint + empty answer boxes |
| **word_search** | 8x8 letter grid + word list to find |
| **syllable_builder** | Syllable blocks + plus signs + equals + answer line |
| **sentence_order** | Scrambled word chips + answer line below |
| **word_chain** | Chain of word blocks + empty blocks, connected by arrows |
| **missing_vowels** | Words with underscores replacing vowels, fill them in |

**Science/World:**
| Type | Visual Description |
|------|-------------------|
| **sequence_order** | Event cards + empty numbered boxes connected by arrows |
| **true_false_fix** | Statements with checkbox + correction line below |
| **cause_effect** | Two columns (causes numbered, effects lettered) with connectors |
| **riddle_boxes** | Riddle text (italic) + empty letter boxes for answer |

#### Footer
- "Kidion — kidion.ru" (small, subtle)

#### Print Requirements
- Must fit exactly 1 A4 page (smart scaling JS already exists)
- Clean print output: no buttons, no shadows, no background colors that waste ink
- High contrast for readability on paper
- Generous white space for writing answers

---

### B. Activity Pages (Lesson 5 — Full-Page Immersive)

Three themed activity types, each a full A4 page with a story scenario:

#### Cipher (Шифровка) — Purple theme (#7c3aed)
- Story intro (2-3 sentences)
- Cipher key table: code → letter pairs
- Encoded message: math problems in boxes, child solves to decode
- Space for decoded message

#### Cafe (Кафе) — Orange theme (#ea580c)
- Story intro ("You're the head chef!")
- Menu: emoji + item name + price in colored badge
- 3-5 math tasks related to menu
- Budget challenge: golden coin graphic + spending task

#### Shop (Магазин) — Cyan theme (#0891b2)
- Story intro ("You found a magic shop!")
- Product shelf: 2-column grid of items with prices
- 3-5 math/logic tasks
- Budget challenge: same coin + spending task

**All activities share:**
- Header with title + subject/grade/topic
- Themed color palette (not just indigo)
- More illustration-like, less worksheet-like
- Should feel like a game page from a children's magazine

---

## Design System Requirements

### Color Palette
- **Current:** Indigo #6366f1 (primary), Green #10b981 (success), Gray #6b7280 (muted)
- **Request:** Keep indigo as anchor but add warmth. Children's palette should feel playful, not corporate. Consider subject-specific accent colors (Math=blue, Russian=green, English=orange, Science=teal).

### Typography
- Rounded, child-friendly font (current: Nunito)
- Large enough for young readers (min 14px on mobile, 12pt on print)
- Clear hierarchy: headings bold 800-900, body 400-600

### Spacing & Layout
- Generous padding and margins — don't cramp content
- Rounded corners everywhere (12-20px)
- Mobile-first: single column, full-width cards
- Touch targets: min 44x44px

### Animation (digital only, not print)
- Scroll-triggered block entrance (fade + translateY)
- Task completion celebrations (confetti, star burst, glow)
- Subtle hover states
- Progress bar smooth transitions
- Character speech bubble entrance

### Illustration Style
- Not needed: custom illustrations
- Needed: a visual system that works WITH AI-generated character images (PNG, varying styles) and WITHOUT them (placeholder with first letter of name)
- Decorative elements: subtle patterns, gradient overlays, themed borders

---

## Deliverables

1. **Lesson wrapper** (lesson.html) — top bar + progress + bottom bar
2. **Theory blocks** (15 types) — CSS + HTML structure for each
3. **Task cards** (5 types) — CSS + HTML + interaction states
4. **Worksheet template** (A4) — header + grid + 24 task type renders
5. **Activity templates** (3 types) — cipher, cafe, shop full-page designs
6. **Design tokens** — colors, fonts, spacing, border-radius values

## Technical Notes

- All output: HTML + CSS + vanilla JS (no React, no Tailwind classes in output)
- Fonts: Google Fonts only (loaded via `<link>`)
- Print: use `@page` and `@media print` CSS rules
- Animations: CSS-only preferred, JS for scroll observers
- Must work in Chrome, Safari (iOS), Firefox
- iframe content is a standalone HTML page — its styles don't leak to parent and vice versa
