# Crawl Console: CLI-Driven AI Chat Crawler

A CLI-driven web crawler with an interactive interface for crawling websites, extracting structured content, and storing crawl results locally or in AWS S3.

The project focuses on reliable web crawling, configurable execution, structured JSON output, and secure cloud storage integration.

---

## 🚀 Features

- **Web Crawling:** Crawl publicly accessible websites and extract page content.
- **Interactive Interface:** Use the application interface to configure and monitor crawl jobs.
- **Structured JSON Output:** Save crawl results in a structured JSON format.
- **AWS S3 Integration:** Optionally upload successful crawl results to Amazon S3.
- **Local Storage:** Preserve crawl results locally.
- **Configurable Crawling:** Configure crawling behavior through environment variables.
- **Error Handling:** Handle failed requests and crawling errors.
- **Security:** Validate URLs and block requests to localhost and private network addresses to reduce SSRF risks.
- **Automated Testing:** Unit tests for application functionality and storage integration.

---

## 🏗️ Architecture

The application follows a modular architecture:

```text
User
  |
  v
Interactive Interface
  |
  v
Crawler Application
  |
  v
URL Validation & Security Checks
  |
  v
Web Crawling Engine
  |
  v
Content Extraction
  |
  v
JSON Result Generation
  |
  +----------------------+
  |                      |
  v                      v
Local JSON Storage    AWS S3 Storage
                       (Optional)
```

### AWS S3 Storage Workflow

When AWS S3 storage is enabled:

1. The crawler completes a crawl successfully.
2. The application generates a structured JSON result.
3. The result is saved locally.
4. The application uploads the JSON file to the configured S3 bucket.
5. The uploaded object is stored under:

```text
crawl-results/<run_id>.json
```

6. If the S3 upload fails, the local result is preserved.

---

## 🛠️ Technology Stack

| Category | Technologies |
|---|---|
| Language | Python |
| Backend | FastAPI |
| Web Crawling | Python HTTP and crawling libraries |
| Cloud Storage | Amazon S3 |
| AWS SDK | Boto3 |
| Cloud Security | AWS IAM |
| Configuration | Environment Variables |
| Testing | Pytest |
| Version Control | Git & GitHub |
| Cloud Tools | AWS CLI |

---

## 📂 Project Structure

```text
cli-chat-crawler/
│
├── app/
│   ├── main.py
│   ├── config.py
│   └── storage.py
│
├── tests/
│   └── test_storage.py
│
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── ...
```

---

## ⚙️ Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/pankajbhattacharjee/cli-chat-crawler.git
```

### 2. Navigate to the Project

```bash
cd cli-chat-crawler
```

### 3. Create a Virtual Environment

Windows:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables

Create a `.env` file using the example configuration:

Windows:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Update the values in `.env` according to your configuration.

---

## 🔐 Environment Variables

The application uses environment variables for configuration.

Example:

```env
# Application Configuration
# Add your existing application settings here.

# AWS S3 Storage
S3_ENABLED=0
S3_BUCKET=
AWS_REGION=ap-southeast-2
```

### AWS Configuration

| Variable | Description | Example |
|---|---|---|
| `S3_ENABLED` | Enables or disables S3 uploads | `1` |
| `S3_BUCKET` | Name of the destination S3 bucket | `your-s3-bucket` |
| `AWS_REGION` | AWS region where the bucket is located | `ap-southeast-2` |

**Important:** Keep `S3_ENABLED=0` if you want local storage only.

To enable S3 uploads:

```env
S3_ENABLED=1
S3_BUCKET=your-s3-bucket
AWS_REGION=ap-southeast-2
```

Replace `your-s3-bucket` with your actual S3 bucket name.

Never commit your actual `.env` file or AWS credentials to GitHub.

---

## ☁️ AWS S3 Integration

The project supports optional cloud storage using Amazon Simple Storage Service (Amazon S3).

### Implementation

- Uses Python's Boto3 SDK.
- Uploads successful crawl results in JSON format.
- Uses the AWS default credential provider chain.
- Supports configurable S3 bucket names.
- Supports configurable AWS regions.
- Uses server-side encryption with Amazon S3-managed keys (SSE-S3).
- Keeps local crawl results if an S3 upload fails.

### AWS Authentication

AWS credentials should be configured securely using one of the supported AWS credential mechanisms.

For local development, AWS CLI can be configured using:

```bash
aws configure
```

Enter your AWS access key, secret access key, and region when prompted.

Do not hardcode AWS credentials in Python files.

### Verify S3 Uploads

To list objects in your S3 bucket:

```bash
aws s3 ls s3://YOUR_BUCKET_NAME/crawl-results/
```

Replace `YOUR_BUCKET_NAME` with your configured bucket name.

Example object structure:

```text
your-s3-bucket/
└── crawl-results/
    ├── run-id-1.json
    ├── run-id-2.json
    └── run-id-3.json
```

### IAM Permissions

The IAM identity used by the application needs the permissions required for the configured S3 operations.

For uploading objects, the relevant permission is:

```text
s3:PutObject
```

If you also want to list objects through the AWS CLI, the identity needs:

```text
s3:ListBucket
```

Apply least-privilege permissions and restrict access to the required bucket and prefix.

---

## ▶️ Running the Application

Activate your virtual environment and start the application using the project's configured entry point.

For a FastAPI application, the typical command is:

```bash
uvicorn app.main:app --reload
```

Open the local application address shown in your terminal.

If your project uses a different startup command, use the command configured in your deployment or project instructions.

---

## 🧪 Testing

The project uses Pytest for automated testing.

Run all tests:

```bash
python -m pytest -q
```

**Latest verified test result:**

```text
32 passed
```

The tests cover application functionality and storage-related behavior.

---

## 🔒 Security Considerations

Security is an important part of the crawler.

The project includes protections such as:

- URL validation before crawling.
- Blocking localhost and private network destinations.
- Avoiding requests to non-public IP addresses.
- Secure handling of configuration through environment variables.
- No hardcoded AWS access keys or secret keys.
- Private S3 bucket storage.
- Server-side encryption for uploaded objects.

These protections reduce common risks such as Server-Side Request Forgery (SSRF).

Security controls should be reviewed and tested before exposing the application publicly.

---

## 📦 Dependencies

Install all dependencies using:

```bash
pip install -r requirements.txt
```

The project uses Boto3 for AWS S3 integration.

If you want to install it separately:

```bash
pip install boto3
```

---

## 🔮 Future Improvements

Potential improvements include:

- Background crawling using task queues.
- Advanced crawl scheduling.
- Crawl history and analytics dashboard.
- Improved monitoring and logging.
- Additional cloud storage options.
- More comprehensive integration tests.
- Docker-based deployment improvements.
- Advanced AI-based content analysis.

---

## 👨‍💻 Author

**Pankaj Bhattacharjee**

B.Tech – Computer Science and Engineering

Interested in Artificial Intelligence, Machine Learning, Python Development, Backend Engineering, and Cloud Technologies.

### 💻 Source Code

[View GitHub Repository](https://github.com/pankajbhattacharjee/cli-chat-crawler)

## 🚀 Live Demo

**Live Application:** [Crawl Console – Open App](https://cli-chat-crawler.onrender.com/)

Try the application directly in your browser without installing anything.

### Project Repository

https://github.com/pankajbhattacharjee/cli-chat-crawler

---

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
---

