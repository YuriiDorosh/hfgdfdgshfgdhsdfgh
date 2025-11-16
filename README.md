# FastAPI Single Proxy

Simple FastAPI-based reverse proxy for a single upstream service with:
- async SQLAlchemy + PostgreSQL
- request/response logging into `proxy_logs` table
- retry logic (max retries & delay configurable via env)
- separate dev/prod docker-compose setups
- Nginx as reverse proxy in front of FastAPI

## Dev

```bash
make build-dev
make up-dev
```

Dev Nginx endpoint: http://localhost:8080  
Direct FastAPI (bypassing Nginx): http://localhost:8000

## Prod

```bash
make build-prod
make up-prod
```

Prod Nginx endpoint: http://localhost:80









---
---
---
---
---


Окей, все вже крутиться — тепер давай реально постріляємо по проксі й подивимось, що воно пише в БД 🔫📊

---

## 1️⃣ Перевір, що API живе

Через nginx (dev-режим, порт 8080):

```bash
curl http://localhost:8080/health
```

Очікуємо:

```json
{"status": "ok"}
```

Якщо ок — можна тестити проксі.

(Якщо хочеш напряму без nginx — `http://localhost:8000/health`.)

---

## 2️⃣ Тестуємо проксі: GET і POST

У `.env.dev` в нас було:

```env
UPSTREAM_BASE_URL=https://httpbin.org
```

Тобто все, що полетить на `/api/v1/proxy/...` → піде на `https://httpbin.org/...`.

### GET-запит

```bash
curl "http://localhost:8080/api/v1/proxy/get?hello=world&user=test" -i
```

Що відбувається:

* твій сервіс приймає `GET /api/v1/proxy/get?hello=world&user=test`
* прокидує це на `https://httpbin.org/get?hello=world&user=test`
* повертає відповідь як є (JSON від httpbin) через nginx назад тобі

Відповідь буде щось типу:

```json
{
  "args": {
    "hello": "world",
    "user": "test"
  },
  "headers": {
    ...
  },
  "url": "https://httpbin.org/get?hello=world&user=test",
  ...
}
```

---

### POST JSON

```bash
curl -X POST "http://localhost:8080/api/v1/proxy/post" \
  -H "Content-Type: application/json" \
  -d '{"foo": "bar", "n": 123}' -i
```

Це полетить на:

```text
POST https://httpbin.org/post
Content-Type: application/json
Body: {"foo":"bar","n":123}
```

І назад отримаєш JSON від `httpbin` з полем `json`, в якому буде твій payload.

---

### POST form (на всякий)

```bash
curl -X POST "http://localhost:8080/api/v1/proxy/post" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "login=apacer&password=supersecret" -i
```

---

## 3️⃣ Де тепер лежать логи в БД

Ми пишемо все в таблицю `proxy_logs` в Postgres.

Якщо ти .env не міняв, стандартні дані такі:

* host з хоста: `localhost`
* порт: `5433` (бо в `docker-compose.dev.yml`: `5433:5432`)
* база: `proxy_db`
* користувач: `proxy`
* пароль: `proxy`

### Варіант А: залізти в контейнер `db` і там відкрити psql

```bash
docker exec -it hfgdfdgshfgdhsdfgh-db-1 psql -U proxy -d proxy_db
```

(Якщо юзер/БД інші — підстав свої.)

Далі в консолі psql:

1. Подивитись, що є таблиця:

```sql
\dt
```

Має бути щось типу:

```text
 public | proxy_logs | table | proxy
```

2. Подивитись останні логи (лайт-варіант):

```sql
SELECT
    id,
    created_at,
    client_ip,
    method,
    path,
    upstream_url,
    response_status,
    duration_ms,
    error
FROM proxy_logs
ORDER BY id DESC
LIMIT 20;
```

3. Подивитися повністю один останній запис:

```sql
SELECT
    id,
    created_at,
    client_ip,
    method,
    path,
    upstream_url,
    query_params,
    request_headers,
    request_body,
    response_status,
    response_headers,
    response_body,
    duration_ms,
    error
FROM proxy_logs
ORDER BY id DESC
LIMIT 1;
```

Там побачиш:

* `query_params` / `request_headers` / `response_headers` як `JSONB`
* `request_body` / `response_body` як `TEXT` (можуть бути обрізані, якщо дуже довгі — я робив truncate з поміткою `...(truncated...)`)
* `duration_ms` — скільки в мс зайняв весь проксований запит (включно з ретраями)
* `error` — або `NULL`, або щось типу `attempts=3, delay=3s` чи текст помилки, якщо upstream недоступний

Вийти з psql:

```sql
\q
```

---

### Варіант B: під’єднатися з хоста (через psql / DBeaver)

Якщо в тебе на WSL стоїть `psql`, можеш зразу:

```bash
psql -h localhost -p 5433 -U proxy -d proxy_db
```

Пароль: `proxy` (якщо не міняв у `.env`).

Далі ті ж `SELECT`-и, що вище.

---

## 4️⃣ Швидкий чек, що логування працює

1. Зроби GET:

```bash
curl "http://localhost:8080/api/v1/proxy/get?hello=world" -i
```

2. Потім залізь в БД і виконай:

```sql
SELECT id, created_at, method, path, response_status, duration_ms
FROM proxy_logs
ORDER BY id DESC
LIMIT 5;
```

Має з’явитися запис з:

* `method = 'GET'`
* `path = '/api/v1/proxy/get'`
* `response_status = 200` (якщо httpbin віддав 200)
* `duration_ms` ≈ кілька десятків/сотень мс

3. Зроби POST і ще раз той самий `SELECT` – побачиш другий запис.
