# Crawl Console: CLI-Driven AI Chat Crawler

A chat interface that turns plain-English requests into safe, real crawls of public websites. An LLM (Gemini or Claude) understands the request, the backend validates it, and a separate crawler CLI does the work. You get a summary and the extracted data as JSON, with optional upload to AWS S3.

**Live demo:** [Crawl Console](https://cli-chat-crawler.onrender.com/)
**Demo video:** [Watch on Google Drive](https://drive.google.com/file/d/1ZVP_WggXcTup3_qgrsJxJvS7faJknELx/view?usp=sharing)

---

## Features

- **Chat interface:** ask in natural language, e.g. "Crawl https://example.com and summarise it".
- **LLM tool calling:** Gemini or Claude picks the URL and limits. With no API key, a rule-based parser is used instead.
- **Real crawler CLI:** polite, same-domain crawler that respects `robots.txt`.
- **Structured JSON output:** titles, descriptions, headings, links, emails, social links.
- **Live logs:** crawler output streams into the page as it runs, with a Cancel button.
- **Optional S3 upload:** successful results can be saved to Amazon S3. If the upload fails, the local result is kept and the UI shows the failure.
- **Safety limits:** rate limits, daily cap, page/depth/time caps.

---

## How it works

```text
User message
   |
   v
LLM proposes parameters (url, max_pages, depth)
   |
   v
validator.py checks and clamps them  --> rejected if unsafe
   |
   v
executor.py runs the CLI from a fixed command template (no shell)
   |
   v
cli/sitecrawl.py crawls and writes JSON
   |
   v
main.py validates the JSON, optionally uploads to S3
   |
   v
LLM summarises the verified result (crawled text is treated as untrusted data)
```

Key design rule: **the LLM never runs anything.** It only suggests parameters. The backend validates them, builds the command itself, and runs the CLI with a minimal environment (API keys are not passed to the crawler).

---

## Security

- URLs are validated: only `http`/`https`, no credentials in the URL, only ports 80/443/8080/8443.
- Localhost, private, link-local and cloud-metadata addresses are blocked (SSRF protection), and re-checked on every redirect inside the CLI.
- Redirects that leave the starting domain are not followed, and redirect targets are checked against `robots.txt`.
- The CLI runs as a subprocess with an argument list (no shell), a hard timeout, and output size caps.
- Secrets are redacted from logs and responses.
- Crawled page text is wrapped as untrusted data before it reaches the summary model.
- Docker container runs as a non-root user with dropped capabilities.

### Known limitations

- **DNS rebinding:** the host is resolved more than once (validator, CLI, HTTP library), so a hostile DNS server could in theory answer differently each time. A full fix needs connecting to the validated IP directly.
- **Rate limits are in memory:** they reset on restart and are per process.
- **Plain HTTP by default:** put HTTPS (Caddy or a load balancer) in front for anything long-lived.
- **Book extraction is a demo feature** tuned for `books.toscrape.com`.

---

## Project structure

```text
cli-chat-crawler/
├── app/
│   ├── main.py        # FastAPI app, chat flow, rate limits
│   ├── llm.py         # Gemini / Claude / rule-based intent + summary
│   ├── validator.py   # URL and limit validation
│   ├── executor.py    # runs the CLI safely
│   ├── security.py    # secret redaction
│   ├── storage.py     # optional S3 upload
│   └── config.py      # environment-based settings
├── cli/sitecrawl.py   # the crawler
├── static/index.html  # chat UI
├── scripts/test_gemini.py  # manual check for your Gemini key
├── tests/             # pytest suite
├── Dockerfile, docker-compose.yml, DEPLOY.md
└── .env.example
```

---

## Setup

```bash
git clone https://github.com/pankajbhattacharjee/cli-chat-crawler.git
cd cli-chat-crawler
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: Copy-Item .env.example .env
```

Run it:

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

---

## Configuration (`.env`)

| Variable | Purpose | Default |
|---|---|---|
| `GEMINI_API_KEY` | Gemini key (optional) | empty |
| `GEMINI_MODEL` | Gemini model name; must exist for your key | see `.env.example` |
| `ANTHROPIC_API_KEY` | Claude key (optional) | empty |
| `ANTHROPIC_MODEL` | Claude model name | see `.env.example` |
| `LLM_PROVIDER` | `auto`, `gemini`, `anthropic` or `rules` | `auto` |
| `MAX_PAGES_CAP` | max pages per crawl | 30 |
| `MAX_DEPTH_CAP` | max link depth | 2 |
| `CRAWL_TIME_BUDGET_SEC` | time budget per crawl | 45 |
| `RATE_LIMIT_PER_MIN` | requests per minute per IP | 12 |
| `MAX_REQUESTS_PER_DAY` | global daily request cap | 300 |
| `MAX_CONCURRENT_CRAWLS` | crawls at the same time | 2 |
| `DEV_ALLOW_PRIVATE_HOSTS` | allow localhost targets (local testing only) | 0 |
| `S3_ENABLED` | upload results to S3 | 0 |
| `S3_BUCKET` | bucket name | empty |
| `AWS_REGION` | bucket region | `ap-south-1` |

With no API key the app still works using rule-based parsing. To check which path ran, open "Interpreted task" in a result and look at **Intent from**. If your Gemini model name is wrong, the app falls back to rules and shows a note.

---

## AWS S3 (optional)

Set `S3_ENABLED=1`, `S3_BUCKET` and `AWS_REGION` in `.env`. Results are uploaded to `crawl-results/<run_id>.json` with server-side encryption (SSE-S3).

- Credentials come from boto3's default chain. Never hardcode them or commit them.
- On EC2 with Docker, the deploy guide blocks container access to instance credentials, so provide a dedicated IAM user's keys through `.env` (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).
- Give that user only `s3:PutObject` on `arn:aws:s3:::YOUR_BUCKET/crawl-results/*`.
- If an upload fails, the crawl result is still returned and the UI shows the upload as failed. Details are in the server logs.

---

## Docker and deployment

```bash
docker compose up -d --build
```

See [DEPLOY.md](DEPLOY.md) for the full AWS EC2 guide.

---

## Testing

```bash
python -m pytest -q
```

Latest result: **38 passed**. Tests cover the crawler (using a local test website), URL validation, the LLM layer (with fake clients), S3 storage, and result loading.

To check your Gemini key and model name manually:

```bash
python scripts/test_gemini.py
```

---

## Future improvements

- Background job queue and crawl history
- Connect-to-validated-IP fix for DNS rebinding
- HTTPS and per-IP daily limits
- More integration tests (full chat flow with a fake crawler)

---

## Author

**Pankaj Bhattacharjee**, B.Tech in Computer Science and Engineering. Interested in AI/ML, Python, backend engineering and cloud.

[GitHub repository](https://github.com/pankajbhattacharjee/cli-chat-crawler)