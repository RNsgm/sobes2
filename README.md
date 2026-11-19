# Keitaro Wrapper

Обёртка над [Keitaro Admin API](https://admin-api.docs.keitaro.io/) для быстрого создания и редактирования рекламных кампаний.

- **Backend:** FastAPI + SQLAlchemy 2 (async) + Alembic, SQLite
- **Frontend:** React + TypeScript (Vite)

## Возможности

### 1. «Создаватор» кампаний
Принимает название, гео (`MX, AU, RO`) и оффер (поиск с автокомплитом), а также домен, группу и источник, выбранные из уже существующих в Keitaro. Создаёт кампанию с двумя потоками:

| # | Поток | Фильтр | Действие |
|---|-------|--------|----------|
| 1 | Geo   | страна ∈ указанные гео | редирект на `https://google.com` |
| 2 | Offers | — (весь остальной трафик) | выбранный оффер, 100% |

Если поток создать не удалось, кампания отправляется в архив, чтобы в трекере не оставалось наполовину созданных кампаний. Каждая созданная кампания записывается в локальную БД (`created_campaigns`).

### 2. Редактор офферов кампании
Вкладка «Редактор офферов»: выберите кампанию по названию или ID. Если в кампании несколько потоков с офферами, выберите нужный. Все правки сначала попадают в черновик, а после каждого действия проценты пересчитываются.

- **Добавить**: оффер появляется с пометкой «новый», доли пересчитываются.
- **Удалить**: строка зачёркивается с пометкой «будет удалён», её доля распределяется между остальными. Пока изменения не применены, удаление можно отменить кнопкой «Не удалять».
- **Пин 📌**: закрепляет текущую долю оффера, при пересчёте она не меняется. Ручная правка процента автоматически ставит пин.
- **Применить** отправляет черновик в Keitaro (`PUT /streams/{id}`). **Отменить** сбрасывает черновик к текущему состоянию в Keitaro.
- **Удалённые офферы** запоминаются в БД (`removed_offers`) вместе с долей на момент удаления. Их можно вернуть позже кнопкой «Вернуть».

Правила пересчёта (`app/services/offer_editor.py::rebalance`):
1. Офферы, помеченные на удаление, в расчёте не участвуют.
2. Запиненные офферы сохраняют свою долю.
3. Остаток `100 − сумма запиненных` делится поровну между незапиненными целыми процентами, лишние единицы получают первые по порядку (например, 34/33/33).
4. «Применить» недоступно, если сумма запиненных больше 100%, если все офферы запинены и в сумме не дают 100%, или если в потоке не осталось ни одного оффера.

Пины хранятся в таблице `pinned_offers` и сохраняются при «Применить».

## Запуск

Нужны Python 3.11+ и Node.js 18+.

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # и впишите KEITARO_API_KEY
alembic upgrade head          # миграции -> создаёт app.db
uvicorn app.main:app --reload --port 8000
```

Swagger обёртки: http://127.0.0.1:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Откройте http://localhost:5173. Dev-сервер проксирует `/api` на `127.0.0.1:8000`.

## Конфигурация (`backend/.env`)

| Переменная | Описание | По умолчанию |
|---|---|---|
| `KEITARO_URL` | Базовый URL Admin API | `https://tlgk.host/admin_api/v1` |
| `KEITARO_API_KEY` | API-ключ (Keitaro → Профиль → API ключи) | — |
| `DATABASE_URL` | Строка подключения SQLAlchemy | `sqlite+aiosqlite:///./app.db` |
| `GEO_REDIRECT_URL` | Куда редиректит гео-поток | `https://google.com` |
| `CORS_ORIGINS` | Разрешённые origin фронта через запятую | `http://localhost:5173` |

## Миграции

```bash
cd backend
alembic upgrade head                                  # применить
alembic revision --autogenerate -m "описание"         # новая миграция после изменения app/models.py
alembic downgrade -1                                  # откатить последнюю
```

## Тесты

```bash
cd backend
pytest
```

Keitaro в тестах замокан через `respx`, сеть не нужна.

## API обёртки

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/domains` | Домены Keitaro |
| GET | `/api/groups` | Группы кампаний |
| GET | `/api/traffic-sources` | Источники трафика |
| GET | `/api/offers?q=` | Поиск офферов по названию / ID |
| POST | `/api/campaigns` | Создать кампанию с двумя потоками |
| GET | `/api/campaigns/created` | Кампании, созданные через обёртку |
| GET | `/api/campaigns?q=` | Поиск кампаний Keitaro |
| GET | `/api/campaigns/{id}/offer-streams` | Потоки кампании с офферами |
| GET | `/api/streams/{id}/editor` | Состояние редактора: офферы, доли, пины, удалённые |
| POST | `/api/streams/{id}/rebalance` | Пересчёт долей черновика (без записи) |
| POST | `/api/streams/{id}/apply` | Применить черновик в Keitaro |

## Структура

```
backend/
  app/
    main.py                 # FastAPI-приложение, CORS, обработка ошибок Keitaro
    config.py               # настройки из .env
    db.py, models.py        # SQLAlchemy
    schemas.py              # Pydantic-схемы + валидация гео
    keitaro/client.py       # httpx-клиент Keitaro Admin API
    services/campaign_creator.py, offer_editor.py
    api/routes.py
  alembic/                  # миграции
  tests/
frontend/
  src/
    api.ts
    components/CampaignCreator.tsx, OfferEditor.tsx, Autocomplete.tsx
```
