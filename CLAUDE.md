# Kidion — Project Context

## Rules

- **All documentation in English**, regardless of the language the user writes in.
- **Prompts (AI generation prompts) stay in Russian** — they are part of the product logic.
- **Keep this file updated** as the project evolves. Auto-update after significant changes.
- **Size limit: 200–300 lines** (optimal), max 400. Beyond 400 lines the model loses focus on instructions. Move details to `.claude/handoff/` or `docs/` if needed.
- **Do NOT modify** files outside `/Users/anastasiamisenko/Documents/projects/kidion/`.
- **Do NOT modify** the original `school-bot` or `tales` projects — generation logic is copied into `services/`.

## What This Is

**kidion.ru** — a personalized educational platform for children ages 6–10. Parents create child profiles with interests, AI generates a personalized universe and character, then creates interactive lessons set in that universe. Children access lessons through a kid-friendly interface, earn stars, and spend them on character customization. **chat.kidion.ru** — AI chat for children with 4 characters (including Arty the artist with photo style transfer).

### Core Flow
Parent creates child (name, grade, interests) → AI generates universe + character + shop → parent generates lessons → child completes them → earns stars → customizes character in star shop.

## Stack

- **Backend:** FastAPI + uvicorn + SQLite (sqlite3, no ORM)
- **Frontend:** Jinja2 templates + vanilla JS (no React/Vue)
- **Auth:** bcrypt (passwords) + itsdangerous (signed cookies `kid_session` for parents, `kid_session_child` for kids)
- **AI Generation:** Google AI Studio (primary, API key) + Vertex AI (fallback). Together AI (FLUX photo style transfer). See AI Models section below.
- **Payments:** Prodamus (edtale.payform.ru, HMAC-SHA256 webhook via Sign header, demo mode active)
- **Tests:** pytest + pytest-asyncio + httpx (306 tests)

## File Structure

```
kidion/
├── main.py                    # FastAPI app, all routes (~4800 lines)
├── db.py                      # SQLite: 22 tables, all CRUD functions
├── auth.py                    # bcrypt, session tokens (parent + child)
├── payments.py                # Prodamus integration, crystal packages
├── referral.py                # Referral codes, promo codes, bonuses (find_referrer supports both)
├── callbacks.py               # HMAC validation for legacy bot callbacks
├── services/
│   ├── generation.py          # Generation Adapter: build_question() + generate_lesson_content()
│   ├── ai_client.py           # AI Studio wrapper (StudioModel), fallback to Vertex AI
│   ├── gemini_client.py       # Lesson generation (AI Studio first, Vertex fallback, stub if neither)
│   ├── prompts.py             # Russian prompts for Methodologist + Tutor-Gamer
│   ├── image_generator.py     # Image generation (Vertex AI Imagen) + photo style transfer (Together AI FLUX)
│   ├── content_generator.py   # Saves lesson HTML/PNG/JSON to content/
│   ├── curricula.py           # Load/search curriculum JSON files
│   ├── universe.py            # Universe/character/shop generation (Gemini)
│   ├── kid_chat.py            # Киди AI chat: 4 characters (incl. Arty artist), per-character safety prompts
│   └── worksheet/             # Printable worksheet generation (from metodist)
│       ├── models.py           # Pydantic models: 24 task types + 3 activities
│       ├── prompts.py          # Prompts for worksheet/activity generation
│       ├── grids.py            # Word search & crossword grid builders
│       └── generator.py        # Orchestrates generation, renders HTML, stubs
├── templates/worksheets/
│   ├── worksheet.html          # 4-task A4 worksheet (lessons 1-4)
│   ├── base_activity.html      # Base for full-page activities
│   ├── cipher.html             # Cipher activity (lesson 5)
│   ├── cafe.html               # Cafe activity (lesson 5, math)
│   └── shop.html               # Shop activity (lesson 5, math)
├── templates/kid/
│   ├── base.html              # Kid base template (nav: home, name, stars, logout)
│   ├── login.html             # Child picker cards + PIN keyboard
│   ├── onboarding.html        # First-login: name the character
│   ├── home.html              # Kid home: character avatar + subjects + streak + shop btn
│   ├── character.html         # RPG character page + star shop + name editing + speech bubble
│   ├── subject_map.html       # Duolingo-style vertical lesson map with tooltip
│   ├── chat.html              # Киди AI chat (single assistant, simple layout)
│   ├── lesson.html            # Lesson iframe + auto-score via postMessage
│   └── result.html            # Stars animation + confetti + shop button
├── templates/chat/
│   ├── chat.html              # Киди Chat (multi-character, Geist font)
│   ├── landing.html           # Киди Chat landing page (/)
│   ├── login.html             # Киди Chat login (parent email → pick child, no PIN)
│   ├── register.html          # Киди Chat registration (simplified)
│   ├── subscribe.html         # Subscription purchase page (/chat/subscribe) + referral block
│   ├── report.html            # Weekly parent report page
│   ├── partners.html          # Blogger partner program landing + application form
│   ├── friends.html           # Referral stats page for regular users
│   └── blogger.html           # Blogger dashboard (balance, promo code, withdrawal)
├── static/spark/
│   ├── chat.css               # Chat CSS (oklch, per-character tints)
│   ├── landing.css            # Landing page CSS
│   ├── chat.js                # Multi-character chat JS
│   ├── spark-hero.png         # Киди character PNG
│   ├── owl.png                # Зуми character PNG
│   ├── captain.png            # Лоро character PNG
│   ├── favicon.ico            # Favicon (from Киди image)
│   └── apple-touch-icon.png   # Apple touch icon
├── static/kid/style.css       # Kid CSS (Nunito, pastels, mobile-first)
├── static/kid/img/spark.png   # Киди avatar image (legacy kid interface)
├── static/kid/chat.js         # Chat page JS (legacy single-Киди)
├── templates/admin.html        # Admin mini-CRM (blogger apps, withdrawals, stats)
├── content/                   # Generated lesson HTML/PNG + characters/ (gitignored)
├── content/characters/        # Generated character PNGs: {child_id}.png
└── tests/                     # 306 tests across 16 test files
```

## Database Schema (22 tables)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `users` | Parent accounts | email, password_hash, crystals, ref_code, **promo_code**, **is_blogger**, **blogger_balance_rub** |
| `children` | Child profiles | parent_id, name, gender, grade, universe, pin_hash, difficulty_level, **stars**, **interests** (JSON), **universe_description**, **character_prompt**, **character_image_url**, **character_name**, **character_onboarded** |
| `lessons` | All lessons | child_id, mode, topic_title, subject, status, worksheet_url |
| `lesson_results` | Completion results | lesson_id, child_id, correct_answers, stars (1-3) |
| `curriculum_topics` | Seeded topics (12 per subject/grade) | subject, grade, theme_order, title_ru, icon |
| `curriculum_lessons` | Seeded lessons (5 per topic) | topic_id, lesson_order, title_ru |
| `child_lesson_progress` | Per-child progress | child_id, curriculum_lesson_id, status, stars_earned |
| `**shop_items**` | **Per-child shop catalog** (AI-generated) | child_id, category, title_ru, emoji, price_stars |
| `**child_items**` | **Purchased/equipped items** | child_id, item_id, equipped |
| `streaks` | Daily activity streaks | child_id, current_streak, longest_streak |
| `curriculum_templates` | FGOS curricula (legacy JSON) | subject, grade, topics_json |
| `curriculum_enrollments` | Program routes (legacy) | child_id, curriculum_id, current_topic_index |
| `weekly_plans` | Weekly topic plans | child_id, curriculum_id, topic_ids_json |
| `transactions` | Crystal transaction log | user_id, delta, reason |
| `payments` | Prodamus payments | user_id, yookassa_payment_id (=order_id), amount_rub, crystals, status |
| `generations` | Legacy generation records | user_id, type, status, result_url |
| `referrals` | Referral relationships | referrer_id, referred_id |
| `kid_chats` | Kid AI chat sessions | child_id, character_key, title |
| `kid_chat_messages` | Chat messages | chat_id, role (user/assistant), content, image_url |
| `chat_subscriptions` | Chat subscription (parent) | user_id, started_at, expires_at, images_remaining, amount_rub |
| `chat_characters` | Seeded chat characters (3) | key, name_ru, role_ru, system_prompt, greeting_ru, is_free |
| `blogger_applications` | Partner program applications | name, email, telegram, social_url, subscribers, status |
| `withdrawal_requests` | Blogger payout requests | user_id, amount_rub, payment_details, status, admin_note |

## Personalized Universe & Character System

### Child Creation Flow
1. Parent fills form: name, gender, grade, **interests** (free text, comma-separated)
2. `POST /api/children` creates child record, then fires `_setup_child_universe()` as background task
3. Background task calls `services/universe.py`:
   - `generate_universe()` → Gemini generates universe_description + character_prompt (stored in children table)
   - `generate_character_image()` → Gemini Flash generates PNG → saved to `content/characters/{child_id}.png`
   - `generate_shop_items()` → Gemini Flash generates ~17 themed items (4 categories) → saved to `shop_items` table

### Stub Mode
All generation functions return predefined defaults when neither `GEMINI_API_KEY` nor `GOOGLE_CLOUD_PROJECT` is set. Character image returns `None` (UI shows placeholder).

### Kid Onboarding (`/kid/onboarding`)
- First login redirects here if `character_onboarded=0`
- Shows character image + speech bubble: "Привет! Я твой новый друг. Как меня зовут?"
- Child enters character name (default: "Искатель") → `POST /api/kid/character/name`
- Sets `character_onboarded=1`, redirects to `/kid/home`

### Character Page (`/kid/character`)
- Left: character PNG + **character name with edit pencil** + speech bubble (contextual phrases based on star count)
- Right: star shop with category tabs (outfit, accessory, pet, background)
- Buying item: deducts stars → creates `child_items` record → triggers background character regeneration
- Insufficient stars: grey button, tooltip on click "Нужно еще немного поучиться!"
- Equip/unequip: toggles `child_items.equipped` → triggers background character regeneration

### Kid Login (`/kid/login`)
- Multi-child: shows child picker cards (avatar + name)
- Single child: auto-selects
- No PIN required (removed)

### Shop Item Categories & Pricing
- outfit (5 items, 5-20 stars), accessory (5 items, 10-25 stars), pet (4 items, 20-40 stars), background (3 items, 15-30 stars)

## Two Currencies

- **Crystals**: Parent currency. Bought with real money, spent on lesson generation and chat subscription. Child never sees crystals.
- **Stars**: Child currency. Earned by completing lessons (+1 per correct task, max 5 per lesson). Spent in character shop. Stored in `children.stars`.

## Киди Chat (chat.kidion.ru)

Multi-character AI chat for children. Templates in `templates/chat/`. Old `/spark/*` URLs redirect 301 → `/chat/*`.

### 4 Characters
| Character | Key | Role | Tier | Model |
|-----------|-----|------|------|-------|
| Киди | spark | Универсальный друг | free | gemini-2.5-flash |
| Зуми | owl | Учитель | free | gemini-2.5-flash |
| Лоро | captain | Рассказчик | free | gemini-2.5-flash |
| Арти | artist | Художник | free | Together AI FLUX (photo) / Vertex AI Imagen (text) |

Each has a unique system prompt layered on shared safety rules (10 rules in `_SAFETY_BASE`). Per-character chat history (separate `kid_chats` row per child+character). All characters use PNG avatar images (`static/spark/`).

**Арти special logic:** Photo + style → `stylize_photo()` via Together AI FLUX.1-kontext-pro (direct style transfer). Text "нарисуй X" → AI generates DRAW: prompt → Imagen generates image. No photo, no draw request → auto-response (no AI tokens). Red dot on avatar when quota exhausted.

### Subscription & Limits
- **Free:** 10 messages/day, all characters, 3 images/month
- **Pro (500 ₽/month real money):** 100 msg/day, all 4 characters, voice input, 30 AI images/month included, parent reports
- **Extra images:** 10💎 per image (from crystal balance)
- **Crystal pack "Волшебные краски":** 100💎 = 100₽ (10 images, don't expire)
- Subscription is per parent account (all children share it)
- Subscription page: `/chat/subscribe` (subscription + crystal packs) and `/buy` (parent auth)
- Payment via Prodamus (500 ₽/month, same as crystal packages)
- When images/messages exhausted: red dot on character avatar, "Волшебные краски закончились" message

### Chat API
- `GET /api/kid/chat?character=spark` — get chat + messages + limits
- `POST /api/kid/chat/send?character=owl` — send message (checks subscription for pro chars)
- `POST /api/kid/chat/clear?character=spark` — clear history
- `GET /api/kid/characters` — list all characters + locked status
- `POST /api/chat/subscribe` — buy subscription (500 rub/month)

### Voice Input
Web Speech API (browser-side, free). Opens overlay, speech → text → editable before send. **BROKEN** — needs fix (see TODO). Report button hidden from kids.

## Key Business Logic

- **Crystals:** 60 on registration (120 with referral). Prices: 1 lesson=20, 1 topic (5 lessons)=100, 1 month (20 lessons)=400. Skip test=FREE. **First 1 lesson per subject=FREE** (auto-generated on first enrollment).
- **Stars:** +1 per correct task (5 tasks = 5 max per lesson).
- **Packages:** 100/100 rub (10 images), 60/60 rub, 360/320 rub, 600/490 rub, 1000/800 rub
- **Adaptive difficulty** (1-3): auto-adjusts based on last 2 lesson results
- **Auto-scoring:** iframe postMessage → auto-submit result. Stub mode → 5/5.
- **Chat subscription:** 500 ₽/month via Prodamus, 100 msg/day (10 free), 30 images/month, extra images 10💎 each. 4 characters. Per-parent (covers all children).
- **Payment polling:** `/buy` page polls `/api/payment/status-by-order` after Prodamus redirect, shows animated success banner when crystals credited.
- **Referral system:** shared between kidion.ru and chat.kidion.ru (same DB). Regular users get `ref_code` (auto `U-XXXX`), bloggers get custom `promo_code` (e.g. `MASHA`). Both work in `?ref=` param. Registration bonus: 60💎 (120💎 with referral). Referrer gets 120💎 on first payment (bloggers get 10% in rub instead).
- **Admin CRM:** `/admin`, access via `ADMIN_EMAILS` env var (comma-separated). Manages blogger applications and withdrawal requests with Telegram notifications.

## API Endpoints

### Auth
- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`

### Children (parent auth)
- CRUD: `POST /api/children` (max 3, accepts `interests: list[str]`), `GET`, `PUT`, `DELETE`
- Progress: `/stats`, `/lessons`, `/program-progress`, `/curriculum/{subject}`, `/free-lessons`, `/enrolled-subjects`, `/subject-progress/{subject}`
- Actions: `/enroll-subject` (auto-generates first 4 lessons FREE), `/skip-test` (inline fullscreen test), `/generate-topic`, `/generate-month`

### Kid Interface (child auth, no PIN)
- Auth: `POST /api/kid/auth`, `POST /api/kid/logout`
- Data: `GET /api/kid/me` (includes character_image_url, universe_description), `/lessons`, `/lessons/{id}`, `/subjects`, `/subject/{s}/map`, `/free-lessons`
- Actions: `POST /api/kid/lessons/{curriculum_lesson_id}/start`
- **Character & Shop:** `GET /api/kid/character`, `POST /api/kid/character/name`, `POST /api/kid/shop/buy/{item_id}`, `POST /api/kid/shop/equip/{item_id}`
- **Chat:** `GET /api/kid/chat?character=X`, `POST /api/kid/chat/send?character=X`, `POST /api/kid/chat/clear?character=X`, `GET /api/kid/characters`

### Payments & Lessons (parent auth)
- `POST /api/lessons/generate`, `POST /api/lessons/generate-topic`, `GET /api/lessons/{id}/poll`, `POST /api/lessons/{id}/result`
- `POST /api/payment/create`, `POST /api/payment/webhook` (Sign header HMAC), `GET /api/payment/status/{id}`, `GET /api/payment/status-by-order?order_id=X`
- `GET /api/children/{id}/worksheets?topic_id=X` — batch print worksheets for topic (5 pages)
- `GET /api/children/{id}/worksheets?subject=X` — batch print all worksheets for subject
- `POST /api/chat/subscribe` — buy chat subscription (500 rub/month)
- `GET /api/chat/subscription` — check subscription status + images_remaining

### Referral & Partners
- `POST /api/partners/apply` — submit blogger application (→ Telegram notification)
- `POST /api/blogger/withdraw` — request payout (min 500 rub, → Telegram notification)
- `POST /api/admin/applications/{id}/approve` — approve blogger + assign promo code (admin)
- `POST /api/admin/applications/{id}/reject` — reject application (admin)
- `POST /api/admin/withdrawals/{id}` — process withdrawal: paid/rejected (admin)

## Pages

### Kid
- `/kid/login` — child picker cards (no PIN)
- `/kid/onboarding` — first-login character naming (redirects to home after)
- `/kid/home` — character avatar + subjects + streak + shop button
- `/kid/character` — RPG character page + star shop + name editing + speech bubble
- `/kid/subject/{subject}` — Duolingo-style lesson map with tooltip
- `/kid/lesson/{id}` — lesson iframe + print button
- `/kid/chat` — AI chat with Киди (legacy single assistant)
- `/kid/result/{id}` — confetti + stars animation + shop button

### Киди Chat
- `/` — landing page on chat.kidion.ru (public, no auth)
- `/chat` — multi-character chat (child auth)
- `/chat/login` — login page (parent email → pick child, no PIN)
- `/chat/register` — simplified registration (accepts `?ref=` for referrals/promo codes)
- `/chat/subscribe` — subscription + crystal packs + referral block (parent auth)
- `/chat/report/{child_id}` — weekly parent report
- Old `/spark/*` URLs redirect 301 → `/chat/*`

### Referral & Partners
- `/partners` — public landing: partner program description + blogger application form
- `/friends` — referral stats for regular users (invited, paid, crystals earned)
- `/blogger` — blogger dashboard (balance, promo code, withdrawal requests)
- `/admin` — mini-CRM (blogger applications, withdrawal requests, stats). Access: `ADMIN_EMAILS` env var

### Parent
- `/dashboard`, `/children/new`, `/children/{id}`, `/children/{id}/subject/{subject}`, `/children/{id}/history`
- `/profile`, `/buy`, `/login`, `/register`

## AI Models & Backend

### Priority: AI Studio (API key) → Vertex AI → Stub mode
- `GEMINI_API_KEY` set → uses Google AI Studio (google-genai SDK)
- `GOOGLE_CLOUD_PROJECT` set → uses Vertex AI (vertexai SDK)
- Neither → returns stubs (for local dev/tests)
- Image generation (PNG) always requires Vertex AI
- Photo style transfer requires Together AI (`TOGETHER_API_KEY`)

### Models by Function

| Model | Function | File |
|-------|----------|------|
| `gemini-2.5-pro` | Lesson Step 1: Methodologist (rules, mnemonics) | gemini_client.py |
| `gemini-3.1-pro-preview` | Lesson Step 2: Tutor-Gamer (JSON lesson + tasks), Universe + character generation | gemini_client.py, universe.py |
| `gemini-2.5-flash-lite` | Lesson Step 3: Visual layout, image prompts | gemini_client.py |
| `gemini-2.5-flash` | Kid chat (Киди), shop items, character/lesson images (Vertex only) | kid_chat.py, universe.py, image_generator.py |
| `FLUX.1-kontext-pro` | Arty photo style transfer (Together AI, $0.04/image, 40 steps) | image_generator.py |
| `imagen-3.0-generate-002` | Text-to-image generation (Vertex AI) | image_generator.py |

### Architecture
- `services/ai_client.py` — `StudioModel` class wraps google-genai to mimic Vertex AI `GenerativeModel` interface
- `get_studio_model(name)` returns `StudioModel` if `GEMINI_API_KEY` is set, else `None`
- Each file's model-creation function tries Studio first, then Vertex, then returns `None` (stub)

## Running

```bash
cd /Users/anastasiamisenko/Documents/projects/kidion
source venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8003 --reload
# Tests: pytest tests/ -v
```

## Deploy

- **Domain:** kidion.ru
- **VPS:** 5.42.101.215 (Moscow, Russia — TimeWeb), SSH: `ssh -i ~/.ssh/id_ed25519 root@5.42.101.215`
- **Port:** 8004, **Path:** /opt/kidion, **SSH Key:** `~/.ssh/id_ed25519`
- **GitHub:** https://github.com/kotyadji-coder/kidion
- **Status:** deployed (SSL active)

## TODO

- [ ] Add curricula for grades 3-4 and more subjects (world)
- [ ] Update registry.json with kidion entry
- [ ] 404 page, rate limiting on auth
- [ ] Cloud backup for DB (Cloudflare R2) — when real users appear
- [ ] Fix voice input (Web Speech API broken on Chrome Mac + Safari iOS — overlay doesn't work)

## Eval System (Quality Monitoring)

Automated evaluation of lesson generation and chat quality. Three levels:

### Architecture
```
evals/
├── __main__.py       # CLI: python -m evals run|compare|list
├── dataset.py        # 16 lesson + 12 chat test cases
├── validators.py     # Level 1: deterministic checks (JSON, math, safety)
├── llm_judge.py      # Level 2: Gemini scores (5 criteria, 1-5 scale)
├── runner.py         # Orchestrator + Level 3 regression tracking
```
- **DB:** `evals_data.db` (SQLite, gitignored) — tables: `eval_runs`, `eval_lesson_results`, `eval_chat_results`
- **Dashboard:** `/evals/dashboard` (parent auth required)
- **Cron:** every Monday 4:00 AM Moscow → `/opt/kidion/run_evals.sh`

### CLI Commands
```bash
python -m evals run              # Full run (16 lessons + 12 chats)
python -m evals run --quick      # Quick run (3+3)
python -m evals compare          # Compare last two runs (regression check)
python -m evals list             # List all runs
```

### When to Run
- **Automatically:** weekly via cron (Monday 4 AM)
- **Manually:** after changing prompts in `services/prompts.py` or chat system prompts in `services/kid_chat.py`
- **Quick mode** for fast iteration, **full mode** before deploy

### Metrics
- **Lessons:** curriculum_match, correctness, universe_integration, child_friendliness, engagement (1-5)
- **Chat:** safety, character_consistency, helpfulness, age_appropriateness, engagement (1-5)
- **Deterministic:** json_structure, task_count, math_correctness, content_safety, universe_reference, etc.

## LLM Dashboard Integration

Token usage from every Gemini call is sent to the centralized LLM Dashboard (`http://5.42.101.215:8005/`).

- **How:** fire-and-forget `httpx.post()` in a daemon thread after each `generate_content()` call
- **Where:** `services/ai_client.py` — `_send_to_dashboard()` function, called from `StudioModel.generate_content()` and `_StudioChat.send_message()`
- **Dashboard project:** `~/Documents/projects/llm-dashboard`
- **If dashboard is down:** errors silently logged at DEBUG level, bot works normally
