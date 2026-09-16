# Memo

**Search finds what the world wrote. Memo finds what you thought.**

A reading tool. Highlight a passage, write what you make of it, save. Later, find
it again by half-remembering the idea — and when you read something that argues
with a note you took months ago, Memo says so.

The article stays on the internet and can be re-found and re-summarised any time.
Your reaction to it can't be recovered from anywhere. Memo stores that half.

---

## The rule

**The machine never writes your opinion.** A note without your own words is
rejected by the API, not just discouraged by the UI:

```
$ curl -X POST localhost:8000/v1/notes -d '{"url":"...","note":"   "}'
{"detail":[{"msg":"Value error, A note needs your own words — that is the point of the tool."}]}
```

The LLM's job is to describe the *source* — one sentence on what the passage
argues, one genuine open question, a few tags — and to label how a new note
relates to your earlier ones (`agrees`, `contradicts`, `extends`, `example_of`).
It never drafts your take.

## Running it

Memo runs at three tiers and picks the best one available without being told.

| | What you get | Setup |
|---|---|---|
| **Keyword** | Full capture; search by word (SQLite FTS5) | none |
| **Ollama** | Search by meaning, free, offline, private | `ollama pull nomic-embed-text` |
| **OpenAI** | Search by meaning + enrichment and link labelling | `OPENAI_API_KEY` |

No tier is a stub. The keyword tier saves, lists, searches, and surfaces related
notes — it just needs roughly the right words, where semantic search doesn't.

```bash
./scripts/start-dev.sh          # creates a venv, installs, serves on :8000
```

```bash
cd extension && npm install && npm run build
# chrome://extensions -> Developer mode -> Load unpacked -> extension/dist/
```

Check which tier you're on:

```bash
curl -s localhost:8000/v1/health
{"status":"healthy","notes":0,"search":"keyword",
 "embeddings":{"provider":"none","state":"off","detail":"..."},
 "enrichment":"off (no OPENAI_API_KEY)"}
```

A key that is present but **rejected** reports `"state":"error"` with the
provider's message, rather than claiming to be on and then silently returning no
results.

### Going semantic

```bash
# free, private, offline — nothing leaves the machine
ollama pull nomic-embed-text

# or, for enrichment as well
cp backend/.env.example backend/.env && echo 'OPENAI_API_KEY=sk-...' >> backend/.env
```

Vectors from different models aren't comparable even at the same dimension, so
the store records which model built it and **refuses to open** under a different
one rather than returning plausible nonsense. Switching means a new database.

## API

| | |
|---|---|
| `POST /v1/notes` | Save a highlight + your take; enrich and link it |
| `GET /v1/notes` | Recent notes, newest first |
| `GET /v1/notes/{id}` · `DELETE /v1/notes/{id}` | One note |
| `GET /v1/search?q=&scope=note\|passage\|both` | Search your takes, your reading, or both |
| `POST /v1/related` | What prior reading bears on the page you're on |
| `GET /v1/health` · `GET /v1/metrics` | Status; Prometheus metrics |

`scope` is the part worth noticing: your words and the author's words are
embedded separately, so *"where was I sceptical about scaling"* and *"what have I
read about scaling"* are different queries.

## Design notes

**Storage.** SQLite + [sqlite-vec](https://github.com/asg017/sqlite-vec), keyed
by note id. 768-dim embeddings, measured at ~7 KB per note — about 70 MB at
10,000 notes, which is five years of reading at five notes a day.

**Degradation is a feature.** No key, no network, no model: the app still boots,
still saves, still searches. Every failure path was chosen so the visible symptom
matches the actual cause.

## Tests

```bash
cd backend && pytest -q        # 29 tests, no API key, no network
```

The stub embedder is a hashed bag-of-words, so similarity thresholds are
genuinely exercised rather than mocked past. CI additionally builds from an empty
container with no key and asserts a real request round-trips — the state in which
most of this project's early bugs were invisible.

## Project layout

```
backend/
  app/
    api/v1.py            HTTP surface
    services/
      embeddings.py      provider resolution: openai -> ollama -> none
      llm.py             enrichment and link labelling
    database.py          SQLite + sqlite-vec + FTS5
    models.py            Note is the unit; `note` is required
  tests/                 29 tests, all offline
extension/
  src/shared/            typed API client, safe DOM builders
  src/sidepanel/         capture, search, recent
  src/content/           reports the current selection
```

## License

MIT
