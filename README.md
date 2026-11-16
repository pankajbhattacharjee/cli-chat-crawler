# Crawl Console: CLI-Driven AI Chat Crawler

A chat application that converts natural-language requests into **real CLI executions**.

For example, a user can ask:

> Crawl https://example.com, extract the important information, give me a summary, and return the data in JSON.

The backend validates the request, executes the `sitecrawl` CLI as a subprocess, captures stdout, stderr, exit code, and result files, validates the output, and responds with a summary and structured JSON.

## Architecture

```text
Browser (static/index.html)
   |
   | POST /api/chat (NDJSON stream: status, log, result)
   v
FastAPI (app/main.py) -- Orchestrator
   |
   | 1. llm.py
   |    Gemini (or Claude) tool use proposes:
   |    {url, max_pages, depth}
   |    Fallback: regex rules
   |
   | 2. validator.py
   |    URL scheme, port, SSRF protection,
   |    DNS validation and limit enforcement
   |
   | 3. executor.py
   |    asyncio.create_subprocess_exec()
   |    Runs the approved CLI without a shell
   |
   | 4. main.py
   |    Parses and schema-validates runs/<id>.json
   |
   | 5. llm.py
   |    Summarizes verified crawl data
   |    Uses a template fallback if the LLM is unavailable
   v
Chat Interface
   - Status badge
   - AI-generated summary
   - Execution details
   - Exit code and stderr
   - Extracted JSON viewer
```

## Which CLI and Why?

`cli/sitecrawl.py` is a purpose-built website crawler built using Requests, BeautifulSoup, and `urllib.robotparser`.

It was chosen because:

- It installs using Python's package manager (`pip`).
- It does not require separate Go or Node.js binaries.
- It generates structured JSON directly.
- It supports robots.txt checking.
- It enforces same-domain crawling and SSRF protections.

The CLI can also be used independently:

```bash
python cli/sitecrawl.py --url https://example.com --max-pages 10 --depth 2 --out result.json
```

**Exit codes:**
- `0` = Success or partial success
- `1` = Failed
- `2` = Refused or blocked

## Book Extraction

For supported listing pages containing `article.product_pod` cards, such as [Books to Scrape](https://books.toscrape.com), the CLI also extracts book information.

The output includes a top-level `books` array containing:

- `title`
- `price`
- `availability`
- `rating`
- `product_url`

Book entries are de-duplicated, and `stats.total_books_extracted` reports the total number extracted.

Other websites return an empty `books` list.

## How Results Are Captured

| Captured Information | How It Works |
|---|---|
| Live progress | stdout lines are streamed to the UI |
| Errors | stderr is collected and secrets are redacted |
| Process status | Exit code, duration, timeout and cancellation flags |
| Result | JSON output is saved in `runs/<run_id>.json` and schema-checked |

The reported status (`success`, `partial`, or `failed`) is determined using the exit code and validated JSON output.

A summary is generated only when at least one page has actually been crawled. Failures display the actual error instead of a fabricated summary.

## Setup

### Prerequisites

- Python 3.10 or later
- pip
- A Gemini API key or Anthropic API key (optional)

### Installation

```bash
# Clone the repository
git clone YOUR_GITHUB_REPOSITORY_URL

# Enter the project directory
cd cli-chat-crawler

# Create a virtual environment
python -m venv .venv

# Activate the environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Create your environment file
copy .env.example .env
```

Open `.env` and add your API key if you want to enable an AI provider.

### Run the Application

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Open the application in your browser:

http://localhost:8000

**Note:** Without an API key, the application can still perform real crawls using its rule-based fallback and template summaries.

### Docker Deployment

If the project includes the provided `Dockerfile` and `docker-compose.yml`, you can run:

```bash
docker compose up -d --build
```

The application is configured to serve on port 80. Check `docker-compose.yml` for the actual port mapping.

For AWS EC2 deployment, see [DEPLOY.md](DEPLOY.md).

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | Empty | Enables Gemini intent understanding and summaries |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model |
| `ANTHROPIC_API_KEY` | Empty | Enables the alternative Anthropic provider |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Anthropic model |
| `LLM_PROVIDER` | `auto` | Selects `auto`, `gemini`, `anthropic`, or `rules` |
| `MAX_REQUESTS_PER_DAY` | 300 | Global daily request limit |
| `MAX_PAGES_CAP` | 30 | Maximum permitted pages per crawl |
| `MAX_DEPTH_CAP` | 2 | Maximum permitted crawl depth |
| `CRAWL_TIME_BUDGET_SEC` | 45 | Maximum crawl time budget |
| `RATE_LIMIT_PER_MIN` | 12 | Per-IP request limit |
| `MAX_CONCURRENT_CRAWLS` | 2 | Maximum parallel crawler processes |
| `DEV_ALLOW_PRIVATE_HOSTS` | 0 | Testing option for allowing private hosts |

## Testing the Demo

1. Start the application and open http://localhost:8000.
2. Send the following request:

   > Crawl https://example.com, extract the important information, give me a summary, and return the extracted data in JSON format.

3. Watch the live crawler output.
4. Expand **Execution Details** to view the real command, exit code, and stderr.
5. Expand **Extracted Data (JSON)** to inspect the structured output.

### Edge Cases to Test

| Input | Expected Behaviour |
|---|---|
| `Crawl http://127.0.0.1` | Rejected by SSRF protection |
| `Crawl http://169.254.169.254` | Rejected by SSRF protection |
| `Crawl https://this-domain-does-not-exist-xyz.com` | Honest crawl failure, no fabricated summary |
| `hello` | Normal chat response without a crawl |
| Cancel a longer crawl | Process is terminated and status becomes Cancelled |

### Automated Tests

Run:

```bash
pytest -q
```

The project currently has **28 passing tests**, covering:

- URL validation and security
- Real CLI crawling using a local fixture website
- LLM functionality using fake providers

## Security Measures

- **No shell execution:** Uses `asyncio.create_subprocess_exec` with a fixed command template and validated arguments.
- **SSRF protection:** Allows HTTP/HTTPS only, checks permitted ports, rejects URL credentials, and validates DNS results against public IP addresses.
- **Redirect protection:** Rechecks destinations inside the CLI on redirect hops.
- **Resource limits:** Enforces page and depth limits, request timeouts, an overall time budget, page-size limits, and result-file limits.
- **Untrusted content:** Website content is treated as data during summarization. The LLM cannot execute system commands.
- **Safe UI rendering:** Uses `textContent` rather than injecting untrusted HTML.
- **Secret protection:** The crawler subprocess receives a minimal environment without API keys. Output is redacted, and `.env` is excluded from Git.
- **Polite crawling:** Respects robots.txt, uses same-domain crawling, applies request delays, and identifies itself with a User-Agent.

## Known Limitations

- Static HTML only; JavaScript-rendered pages are not supported.
- DNS is checked before connecting, so DNS rebinding between validation and connection remains a theoretical risk.
- Stronger isolation can be achieved using Docker and network egress filtering.
- Rate limiting and the run registry are in-memory and intended for a single application process.

## AI Tools and Services Used

- **Google Gemini API:** Default provider for intent understanding and summarization.
- **Anthropic API:** Optional alternative provider, if configured.
- **ChatGPT (OpenAI):** Used for planning, debugging assistance, and development guidance.
- **Libraries:** FastAPI, Uvicorn, Requests, BeautifulSoup4, python-dotenv, and pytest.

## Project Layout

```text
cli-chat-crawler/
|
|-- app/
|   |-- main.py
|   |-- llm.py
|   |-- validator.py
|   |-- executor.py
|   |-- security.py
|   |-- config.py
|
|-- cli/
|   |-- sitecrawl.py
|
|-- static/
|   |-- index.html
|
|-- tests/
|   |-- test_validator.py
|   |-- test_cli.py
|   |-- test_llm.py
|
|-- runs/                 # Generated crawl results (Git-ignored)
|
|-- .env.example
|-- .gitignore
|-- requirements.txt
|-- README.md
|-- Dockerfile
|-- docker-compose.yml
|-- DEPLOY.md
```
## 🎥 Project Demonstration Video

Watch the complete demonstration of Crawl Console, showcasing the AI-powered chat interface, real CLI execution, website crawling, result extraction, and error handling.

▶️ **[Watch the Full Demo Video on Google Drive](https://drive.google.com/file/d/1ZVP_WggXcTup3_qgrsJxJvS7faJknELx/view?usp=sharing)**

The video demonstrates:
- Natural-language prompt understanding using Gemini.
- AI tool calling and intent interpretation.
- Backend validation and secure CLI execution.
- Real-time crawler execution logs.
- Website summarization and structured JSON extraction.
- Error handling for inaccessible websites.
Live Application: https://cli-chat-crawler.onrender.com/
Source Code :https://github.com/pankajbhattacharjee/cli-chat-crawler
