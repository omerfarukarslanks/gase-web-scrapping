# GASE News Scraper

13 buyuk haber kaynagindan (Reuters, AP, BBC, Bloomberg vb.) gunluk gundem haberlerini otomatik olarak ceken, saklayan ve dashboard uzerinden goruntuleyen bir sistem.

## Mimari

```
Docker Compose
├── postgres:16        → Veritabani
├── redis:7            → Celery broker + cache
├── api                → FastAPI REST API (port 8000)
├── worker             → Celery worker (scraping)
├── beat               → Celery beat (zamanlayici - saatte bir)
├── frontend           → React + Vite dashboard (port 3000)
└── nginx              → Reverse proxy (port 80)
```

## Haber Kaynaklari

**Genel Haber:** Reuters, AP News, AFP, BBC News, Al Jazeera, The Guardian, ABC News, CBS News, PBS NewsHour

**Finans & Ekonomi:** Bloomberg, Financial Times, Wall Street Journal, The Economist

## Onkoşullar

- [Docker](https://docs.docker.com/get-docker/) ve [Docker Compose](https://docs.docker.com/compose/install/) kurulu olmali
- Git

## Kurulum

### 1. Projeyi klonla

```bash
git clone <repo-url>
cd gase-web-scrapiing-news
```

### 2. Environment degiskenlerini ayarla

```bash
cp .env.example .env
```

`.env` dosyasini duzenle (varsayilan degerler local gelistirme icin uygundur):

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/news_scraper
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=news_scraper
REDIS_URL=redis://redis:6379/0
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=true
SCRAPE_INTERVAL_MINUTES=60
DEFAULT_RATE_LIMIT_RPM=10
USER_AGENT=GaseNewsScraper/1.0
CORS_ORIGINS=["http://localhost:3000","http://localhost:80"]
```

### 3. Docker imajlarini build et ve servisleri baslat

```bash
# Build et
make build

# Tum servisleri baslat (arka planda)
make up
```

Veya dogrudan Docker Compose ile:

```bash
docker compose build
docker compose up -d
```

### 4. Veritabani migration'larini calistir

```bash
make migrate
```

Veya:

```bash
docker compose exec api alembic upgrade head
```

### 5. Haber kaynaklarini seed et

13 haber kaynagini veritabanina ekler (RSS feed URL'leri ile birlikte):

```bash
make seed
```

Veya:

```bash
docker compose exec api python -m scripts.seed_sources
```

### 6. Ilk scrape'i tetikle (opsiyonel)

Celery beat saatte bir otomatik calisir, ancak hemen test etmek istersen:

```bash
make scrape
```

## Erisim

| Servis | URL |
|--------|-----|
| Dashboard (Nginx) | http://localhost |
| Frontend (direkt) | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Health Check | http://localhost:8000/api/health |

## Kullanim

### Makefile Komutlari

```bash
make up              # Servisleri baslat
make down            # Servisleri durdur
make build           # Docker imajlarini build et
make logs            # Tum servislerin loglarini goster
make api-logs        # Sadece API loglarini goster
make worker-logs     # Worker ve beat loglarini goster
make migrate         # Alembic migration calistir
make seed            # Haber kaynaklarini seed et
make scrape          # Manuel scrape tetikle
make test            # Testleri calistir
```

### Yeni Migration Olusturma

```bash
make migrate-create msg="add new column"
```

### API Endpoints

```
GET  /api/v1/articles              → Haber listesi (filtre: source, category, search, date)
GET  /api/v1/articles/trending     → Gundem haberleri (son 24 saat)
GET  /api/v1/articles/{id}         → Haber detayi
GET  /api/v1/sources               → Kaynak listesi (istatistiklerle)
GET  /api/v1/sources/{slug}        → Kaynak detayi
PATCH /api/v1/sources/{slug}       → Kaynak guncelle (aktif/pasif, aralik)
POST /api/v1/sources/scrape/trigger → Manuel scrape tetikle
GET  /api/v1/scrape-runs           → Scrape gecmisi
GET  /api/v1/scrape-runs/latest    → Her kaynak icin son scrape
GET  /api/v1/scrape-runs/dashboard → Dashboard istatistikleri
```

### Ornek API Kullanimi

```bash
# Tum haberleri getir
curl http://localhost:8000/api/v1/articles

# BBC haberlerini filtrele
curl "http://localhost:8000/api/v1/articles?source=bbc&per_page=10"

# Finans haberlerini getir
curl "http://localhost:8000/api/v1/articles?source_category=finance"

# Arama yap
curl "http://localhost:8000/api/v1/articles?search=economy"

# Manuel scrape tetikle
curl -X POST "http://localhost:8000/api/v1/sources/scrape/trigger?source_slug=bbc"
```

## Gelistirme

### Backend (local, Docker disinda)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# PostgreSQL ve Redis'in calistigina emin ol
# .env'deki DATABASE_URL ve REDIS_URL'i localhost'a guncelle
uvicorn app.main:app --reload --port 8000
```

### Frontend (local, Docker disinda)

```bash
cd frontend
npm install
npm run dev
```

Vite dev server `http://localhost:3000` adresinde baslar ve API isteklerini `http://localhost:8000`'e proxy eder.

## Proje Yapisi

```
├── backend/
│   ├── app/
│   │   ├── api/v1/          → FastAPI route'lari
│   │   ├── db/              → SQLAlchemy base, session
│   │   ├── models/          → Article, Source, ScrapeRun
│   │   ├── schemas/         → Pydantic request/response
│   │   ├── scrapers/        → Scraper framework
│   │   │   ├── base.py      → BaseNewsScraper ABC
│   │   │   ├── rss_scraper.py → Generic RSS parser
│   │   │   ├── sources/     → 13 kaynak-spesifik scraper
│   │   │   └── utils/       → Rate limiter, dedup, robots.txt
│   │   ├── services/        → Article service, orchestrator
│   │   └── workers/         → Celery app, tasks
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/             → Axios API client
│       ├── components/      → React component'leri
│       ├── pages/           → Dashboard, Haberler, Kaynaklar
│       ├── stores/          → Zustand state management
│       └── types/           → TypeScript tipleri
├── nginx/                   → Nginx reverse proxy config
├── scripts/                 → Seed ve yardimci scriptler
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Teknolojiler

**Backend:** Python 3.12, FastAPI, SQLAlchemy (async), PostgreSQL, Celery, Redis, feedparser, httpx, BeautifulSoup4

**Frontend:** React 18, TypeScript, Vite, TailwindCSS, Zustand, TanStack Query, Recharts, React Router v6

**Altyapi:** Docker Compose, Nginx
