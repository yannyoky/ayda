---
name: ayda-engineering
description: Use for Ayda technical work: architecture and ADRs, Python FastAPI backend with the AI assistant, Telegram Mini App (React), KMP Android/iOS, DB schema, APIs and CI/CD.
---

# Ayda: архитектор и инженерная команда

Отвечай по-русски; код, коммиты, PR и комментарии в коде на английском. Владелец сильнее всего в Python + FastAPI, Kotlin и Swift изучает: в мобильном коде коротко объясняй идиомы языка.

## Роль: архитектор
Перед крупной задачей проверь `docs/architecture.md` и `docs/decisions/`. Новое решение = новый ADR.

Базовая архитектура (ADR 0002, 0003; менять только через новый ADR):
- `backend/` Python 3.13 + FastAPI, модульный монолит: модули в `backend/src/ayda/modules/` (auth, quests, assistant, events, social, chat, habits, analytics). Модули не импортируют друг друга (import-linter в CI); связь через общий прикладной код и доменные события. uv, SQLAlchemy 2, Alembic-миграции в репозитории. Воркер (очередь задач в PostgreSQL) запускается из того же кода.
- AI-помощник внутри бэкенда (модуль assistant): LLM-провайдер за интерфейсом `LLMProvider`, только бесплатные API, Ollama локально. LLM только ранжирует и формулирует кандидатов, отобранных кодом; ответ строго по JSON-схеме с валидацией и fallback. Утренние квесты можно генерировать батчем ночью.
- БД: PostgreSQL + PostGIS (гео, афиши) + pgvector. Медиа в S3-совместимом хранилище в РФ. Realtime (ЛС, чаты коопа) через Centrifugo. Telegram-бот на aiogram 3 только уведомляет.
- `miniapp/` Telegram Mini App: React 19 + TypeScript + Vite + Tailwind v4, API-клиент генерируется из OpenAPI бэкенда; `initData` проверяется на бэкенде по HMAC.
- Натив: Kotlin Multiplatform для общей логики, Compose (Android) и SwiftUI (iOS).
- Таблица `events` (append-only лог действий с квестами) с первого дня.
- UI по `docs/design/themes.md`: две темы (Графит, Слива), бенто-виджеты, Unbounded + Manrope.
- Локальный запуск: `docker compose up` (postgres, backend, worker, centrifugo, ollama опционально).

## Роль: инженер
1. Прочитай issue и критерии приёмки; неясное в деталях реши разумным дефолтом и напиши, какой выбран.
2. Маленькие PR (одна задача), ветка `feat/<area>-<short>`, Conventional Commits.
3. Тесты вместе с кодом: pytest (+ Testcontainers с реальным PostgreSQL) для backend, тесты Mini App через `npm test`, unit-тесты общей KMP-логики.
4. Перед пушем линтеры и тесты затронутой части (команды в CLAUDE.md).
5. Описание PR: Before / After / How, ссылка на issue.

Стандарты:
- Python: типы везде (pyright strict там, где можно), pydantic-модели на входе и выходе, async до конца, единый формат ошибок (problem+json), ruff check + ruff format.
- TypeScript: strict, без ручных fetch-обёрток мимо сгенерированного клиента.
- Секреты только из переменных окружения.
- Геолокация и фото = персональные данные: храним минимум, точные координаты не логируем.

## CI/CD (GitHub Actions)
- `ci.yml` на каждый PR: сборка и тесты только затронутых частей; job запускается только при изменениях в своей папке и когда в ней уже есть проект.
- `deploy.yml` на push в `main`: Docker-образы, GHCR, деплой на VPS в РФ через Docker Compose. Деплой в прод только после подтверждения владельца (GitHub Environment `production`).
- Деплой: Docker Compose на VPS в РФ за Caddy.
- Dependabot для uv/pip, npm, gradle, github-actions.
