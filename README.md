# Catalog Ingestion & Retrieval

A Python API for uploading product CSVs, processing rows with background workers,
and querying product information with retrieval-augmented generation (RAG).

## Features

- User registration, token authentication, and authenticated CSV uploads
- Queue-based CSV ingestion into PostgreSQL
- Dense and sparse product embeddings with hybrid search and reranking
- Retrieval and generated-answer API endpoints

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL with the `pgvector` extension available
- Redis and RabbitMQ
- An OpenAI-compatible LLM server for answer generation

## Setup

Install the project dependencies:

```bash
uv sync
```

Configure environment variables as needed. For example:

```dotenv
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/csv_ingestion
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=<replace-with-a-long-random-secret>
LLAMA_SERVER_URL=http://localhost:8080/v1
```

The application reads settings from environment variables or a root `.env` file.
Set `SECRET_KEY` to a private random value of at least 32 characters.
The RabbitMQ and Taskiq result-backend URLs are currently configured in
`broker.py`.

Start the API:

```bash
uv run python main.py
```

Start workers in separate terminals:

```bash
uv run taskiq worker broker:broker tasks.csv_worker
uv run taskiq worker broker:rag_broker tasks.embedding_worker tasks.rag_worker
```

Start PostgreSQL, Redis, RabbitMQ, and the LLM server before using the endpoints.
The LLM server should be available at `LLAMA_SERVER_URL`; its model settings are
in `llama_config.json`.

## API

The API listens on port `8000` by default. Interactive documentation is available
at [http://localhost:8000/docs](http://localhost:8000/docs).

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Check API liveness |
| `POST` | `/api/v1/register` | Register a user |
| `POST` | `/api/v1/token` | Obtain an access token |
| `POST` | `/api/v1/upload` | Upload a CSV (requires the `upload` scope) |
| `POST` | `/api/v1/trigger-backfill` | Queue embedding backfill |
| `POST` | `/api/v1/rag_retrieve` | Retrieve and rerank product chunks |
| `POST` | `/api/v1/rag_generate` | Stream a generated answer |

RAG query endpoints accept JSON in the form `{"query": "..."}`. CSV uploads
must have a header row followed by `name`, `sku`, and `description` columns, in
that order. The API's CSV worker skips the first row and stores the remaining
rows in `sku_catalogue`; the RAG pipeline chunks `name`, `sku`, and
`description` from that table into `product_chunks`.

The CSV and RAG tables and their vector indexes are created by the CSV worker
when it starts. Existing `product_embeddings` tables are not migrated; the
current pipeline uses `product_chunks`, which is created if it does not exist.