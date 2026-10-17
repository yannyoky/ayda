# Продакшен

[English](../deploy.md) · Русский

Всё работает на одном VPS в России под Docker Compose (ADR 0002): Caddy (TLS, статика Mini App, обратный прокси), API, воркер, бот, PostgreSQL с PostGIS и pgvector, Centrifugo и GlitchTip для ошибок. Фото и бэкапы базы хранятся у российского S3-совместимого провайдера. Файлы: `deploy/`.

```
Telegram ──▶ Caddy :443 ─┬─ /            Mini App (static, baked into ayda-web)
                         ├─ /api/*       api:8000
                         ├─ /telegram/webhook   bot:8081
                         └─ /connection/*       centrifugo (M2)
             errors.<domain> ──▶ glitchtip:8000
api / worker / bot ──▶ postgres     worker ──▶ S3 (photos, daily pg_dump)
```

## Как выходит релиз

1. Каждый пуш в `main` собирает три образа и пушит их в GHCR с тегом в виде sha коммита: `ayda-backend`, `ayda-web` (Mini App + Caddy) и `ayda-postgres`.
2. Продакшен меняется, только когда кто-то запускает **Actions → Deploy → Run workflow**. Джоба `deploy` ждёт одобрения ревьюера защищённого окружения `production`, затем копирует Compose-файл на VPS, скачивает образы этого коммита и перезапускает то, что изменилось. Сначала выполняются миграции (сервис `migrate`); API стартует только после их успеха. В конце джоба проверяет здоровье по `https://<domain>/api/v1/health`.
3. Откат: запустить workflow ещё раз, указав в `tag` sha более раннего коммита `main`. Миграции только вперёд: между коммитами с одинаковыми миграциями откатываться можно свободно; если между ними есть миграция, старый код должен работать с новой схемой, иначе нужно восстановить бэкап, сделанный до неё.

Пулл-реквесты, затрагивающие `deploy/` или `infra/`, проверяют Compose-файл и собирают веб-образ.

## Разовая настройка (владелец)

1. **VPS в России**: для MVP хватит Ubuntu 26.04 LTS, 2 vCPU, 4 ГБ RAM, 60 ГБ SSD и одного статического публичного IPv4. Установить Docker Engine с плагином Compose, создать пользователя `deploy` в группе `docker` с SSH-ключом, открыть только порты 22, 80 и 443. `sudo mkdir /opt/ayda && sudo chown deploy /opt/ayda`.
2. **Домен**: A-запись для приложения (`AYDA_DOMAIN`, например `app.example.ru`) и для ошибок (`ERRORS_DOMAIN`, например `errors.example.ru`), обе указывают на IPv4 VPS. AAAA-записи не добавлять, пока IPv6 не настроен на VPS и в Docker. Сертификаты Caddy получает сам.
3. **S3 в России**: два приватных бакета (`ayda-media`, `ayda-backups`) и один ключ доступа. На медиа-бакете разрешить CORS `PUT` и `GET` с `https://<AYDA_DOMAIN>` (Mini App загружает фото прямо в S3 по presigned URL).
4. **Секреты на VPS**: скопировать `deploy/env.prod.example` в `/opt/ayda/.env`, заполнить, `chmod 600`. Случайные значения: `openssl rand -base64 32`. `SENTRY_DSN` заполняется после шага 7.
5. **GitHub**: Settings → Environments → `production`: обязательный ревьюер (владелец), ветка деплоя `main`. Секреты окружения `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` (приватный ключ пользователя deploy), `DEPLOY_KNOWN_HOSTS` (`ssh-keyscan <host>`), переменная окружения `AYDA_DOMAIN`.
6. **Первый деплой**: запустить workflow Deploy и одобрить его.
7. **GlitchTip**: `docker compose -f docker-compose.prod.yml exec glitchtip ./manage.py createsuperuser`, войти на `https://<ERRORS_DOMAIN>`, создать организацию и проект `ayda`, записать его DSN в `SENTRY_DSN` в `.env`, снова запустить workflow Deploy. Регистрация пользователей отключена; события хранятся 30 дней.
8. **@BotFather**: Bot Settings → Configure Mini App → Main Mini App URL `https://<AYDA_DOMAIN>/`; Menu Button → тот же URL. При старте бот сам ставит вебхук на `https://<AYDA_DOMAIN>/telegram/webhook` с `TELEGRAM_WEBHOOK_SECRET`.
9. **LLM-провайдеры**: с VPS запустить смоук-проверку эвала (`docs/llm-eval.md`, `--limit 3`) и убедиться, что Groq и Cloudflare отвечают на российский IP. Если Groq заблокирован, поставить `cloudflare-llama70b` первым в `LLM_PROVIDERS`.
10. **Локальные события** (M3, ADR 0008): настраивать ничего не нужно; Timepad и KudaGo работают без ключей (`TIMEPAD_TOKEN` необязателен). Воркер загружает события раз в день после 04:00 по Москве, а также сразу после первого деплоя, если это время уже прошло; `docker compose -f docker-compose.prod.yml logs worker | grep events:` показывает количество по источникам.

## Бэкапы

Воркер каждый день после 03:30 по Москве выгружает `pg_dump` в `BACKUP_BUCKET` и хранит 14 дней (`docs/architecture.md`, «Бэкапы и отслеживание ошибок»). Неудачный бэкап повторяется; если попытки исчерпаны, ошибка появляется в GlitchTip.

Вручную, на VPS в `/opt/ayda`:

```sh
alias ayda='docker compose -f docker-compose.prod.yml run --rm migrate'
ayda python -m ayda.core.backup list
ayda python -m ayda.core.backup create
```

### Ежемесячная проверка восстановления

Восстановить последний дамп во временную базу, сравнить несколько счётчиков с продакшеном, затем удалить её:

```sh
docker compose -f docker-compose.prod.yml exec postgres createdb -U ayda ayda_restore_check
ayda python -m ayda.core.backup restore <key> \
  --target-url "postgresql://ayda:<POSTGRES_PASSWORD from .env>@postgres:5432/ayda_restore_check"
docker compose -f docker-compose.prod.yml exec postgres psql -U ayda -d ayda_restore_check \
  -c "select count(*) from auth.users" -c "select max(occurred_at) from analytics.events"
docker compose -f docker-compose.prod.yml exec postgres dropdb -U ayda ayda_restore_check
```

### Аварийное восстановление

Новый VPS (шаги 1, 4, 6 выше), остановить `api`, `worker` и `bot`, восстановить последний дамп в пустую базу `ayda` той же командой (`--target-url` указывает на `ayda`), запустить всё, затем повторить удаление аккаунтов, удалённых после снятия дампа (152-ФЗ: восстановление не должно возвращать стёртые данные).

## Логи

`docker compose -f docker-compose.prod.yml logs -f api worker bot`. Логи остаются на VPS (с ротацией, 5 × 20 МБ на контейнер), Caddy не пишет access-лог, а логи приложения проходят через фильтр редактирования (`ayda.core.logging`).
