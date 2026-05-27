# MyChatbot — KYC/AML Compliance RAG Chatbot

A local, privacy-preserving Retrieval-Augmented Generation (RAG) chatbot for KYC and AML compliance teams. Analysts ask plain-English questions about internal SOPs and get grounded, citation-backed answers — all running on-device, no cloud calls.

> **Status:** Proof of concept. Milestones 1–2 complete (skeleton + ingestion). Milestone 3 (`/chat` endpoint with citations) is next.

---

## Stack

| Layer        | Choice                                                   |
|--------------|----------------------------------------------------------|
| LLM          | Ollama — `qwen:4b` (dev) → larger Qwen variant in prod   |
| Embeddings   | Ollama — `nomic-embed-text` (768-dim, local)             |
| Vector store | ChromaDB (embedded, persistent on disk)                  |
| PDF/DOCX     | `python-docx` with a repair fallback for malformed zips  |
| Backend      | FastAPI + Uvicorn                                        |
| Frontend     | Streamlit (planned)                                      |
| Evaluator    | Ragas (planned)                                          |

---

## Prerequisites

- macOS / Linux (tested on macOS Apple Silicon)
- Python 3.11+
- [Ollama](https://ollama.com/download) installed and running

Pull the required models once:

```bash
ollama pull qwen:4b
ollama pull nomic-embed-text
ollama list  # verify both are present
```

---

## Setup

```bash
# 1. Clone
git clone <your-repo-url> MyChatbot
cd MyChatbot

# 2. Create and activate a venv
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip3 install --upgrade pip
pip3 install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# (edit .env if you need different Ollama host/model/paths)

# 5. Drop your SOP .docx files into resources/
#    They are gitignored by design (compliance — never commit source SOPs).
ls resources/
```

---

## Running the API

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

Then open the interactive Swagger UI: **http://127.0.0.1:8000/docs**

Available endpoints today:

| Method | Path           | Purpose                                                       |
|--------|----------------|---------------------------------------------------------------|
| GET    | `/health`      | Ollama reachability + which models are pulled                 |
| POST   | `/smoke`       | One-shot prompt against `qwen:4b` (sanity check)              |
| POST   | `/ingest`      | Parse + chunk + embed all `.docx` in `resources/` into Chroma |
| GET    | `/documents`   | Chunk count and list of ingested doc names                    |

---

## Ingesting SOPs

After dropping `.docx` files into `resources/`, run either:

```bash
# Option A — CLI
python3 -m app.rag.pipeline ingest

# Option B — API (server must be running)
curl -X POST http://127.0.0.1:8000/ingest
```

Re-running is safe: chunks for a given filename are deleted and re-inserted, so there are no duplicates or stale rows.

Inspect what's stored:

```bash
python3 -m app.rag.pipeline stats
# {'chunk_count': 235, 'documents': ['ZPTPL - SOP for Negative Due Diligence.docx', ...]}
```

---

## Testing retrieval (without the chat layer)

Before the `/chat` endpoint lands, you can hand-test the retrieval layer directly:

```bash
python3 -m app.rag.pipeline query "What is the V-CIP process?" --k 5
```

You'll see ranked chunks with cosine similarity scores (1.0 = identical meaning, 0.0 = unrelated), the SOP filename, and the heading breadcrumb of the chunk's location.

---

## Project layout

```
MyChatbot/
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── config.py            # pydantic-settings (.env loader)
│   ├── api/
│   │   └── ingest.py        # /ingest, /documents
│   ├── llm/
│   │   └── ollama_client.py # Thin async client over Ollama
│   ├── rag/
│   │   ├── loader.py        # .docx → DocBlocks (heading-aware)
│   │   ├── chunker.py       # Section-aware splitter
│   │   ├── vectorstore.py   # ChromaDB persistent wrapper
│   │   └── pipeline.py      # ingest_file/dir + retrieve + CLI
│   ├── eval/                # (Milestone 5: Ragas evaluator)
│   └── schemas.py
├── ui/                       # (Milestone 4: Streamlit)
├── data/
│   ├── chroma/              # Persistent vector store (gitignored)
│   └── eval/                # Golden Q&A + reports (gitignored)
├── resources/               # Drop .docx SOPs here (contents gitignored)
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

---

## Configuration (.env)

| Key                  | Default                  | Notes                                              |
|----------------------|--------------------------|----------------------------------------------------|
| `OLLAMA_HOST`        | `http://localhost:11434` | Where Ollama is running                            |
| `CHAT_MODEL`         | `qwen:4b`                | Used by `/smoke` (and `/chat` once built)          |
| `EMBED_MODEL`        | `nomic-embed-text`       | **Don't change after ingest** — embeddings tied to model |
| `SOPS_DIR`           | `resources`              | Where ingestion looks for `.docx` files            |
| `CHROMA_DIR`         | `data/chroma`            | Where Chroma persists vectors                      |
| `CHROMA_COLLECTION`  | `sops`                   | Collection name inside Chroma                      |
| `RETRIEVAL_TOP_K`    | `5`                      | Default chunks returned per query                  |
| `RETRIEVAL_MIN_SCORE`| `0.25`                   | Below this similarity, treat as no-match           |

> If you change `EMBED_MODEL` after ingesting, **wipe `data/chroma/` and re-ingest** — vectors from one model are not comparable to vectors from another.

---

## Roadmap

- [x] **M1** — FastAPI skeleton, Ollama client, `/health`, `/smoke`
- [x] **M2** — `.docx` loader, section-aware chunker, ChromaDB ingestion, `/ingest`, `/documents`
- [ ] **M3** — `/chat` endpoint with citation-enforcing prompt + refusal on low retrieval confidence
- [ ] **M4** — Streamlit UI (chat surface + sources panel)
- [ ] **M5** — Ragas evaluator: golden Q&A set, `POST /eval/run`, persisted reports
- [ ] **M6** — Unit + integration tests

---

## Security & compliance notes

- **SOP files are gitignored.** `.docx`, `.doc`, and `.pdf` files in `resources/` are excluded by `.gitignore`. Never commit source SOPs.
- **No cloud LLM calls.** Both the chat model and embedding model run locally via Ollama. Customer data and SOP content never leave the machine.
- **Citations are mandatory.** Once `/chat` lands, every answer will include the source SOP filename, section, and excerpt used. The system prompt will refuse to answer when retrieval confidence is below threshold.

---

## License

Internal / proprietary. Not for redistribution.
