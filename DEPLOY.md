# Deploy to AWS EC2 (single Docker container)

Result: a live URL like `http://<EC2-public-IP>/` serving the chat UI and the API.

## 0. Before you start
- Gemini API key: https://aistudio.google.com/app/apikey (or an Anthropic key)
- Code on GitHub (or use the `scp` alternative in step 4)
- Check the model name is valid for your key. If you get "model not found", set `GEMINI_MODEL`
  in `.env` to a model listed in AI Studio.

## 1. Launch the instance (AWS Console → EC2 → Launch instance)
| Setting | Value |
|---|---|
| Name | `crawl-console` |
| AMI | Ubuntu Server 22.04 or 24.04 LTS |
| Type | `t3.micro` or `t2.micro` (check your account's free-tier terms) |
| Key pair | Create new → download the `.pem` file and keep it safe |
| Storage | 16 GB gp3 |

**Network settings → security group** (inbound rules):
| Type | Port | Source |
|---|---|---|
| SSH | 22 | **My IP** |
| HTTP | 80 | Anywhere `0.0.0.0/0` (or "My IP" if only you need it) |

Do **not** open ports 3000/8000. Only port 80 is needed.

**Advanced details → Metadata version: `V2 only`, Metadata response hop limit: `1`.**
This stops containers from reading the instance's AWS credentials.

Launch, then (optional but useful) allocate an **Elastic IP** and associate it so the URL
doesn't change when you stop/start the instance.

## 2. Connect
```bash
chmod 400 crawl-console.pem          # Mac/Linux only
ssh -i crawl-console.pem ubuntu@<EC2-public-IP>
```
Windows: use PowerShell's `ssh` the same way, or PuTTY.

## 3. Install Docker (on the server)
```bash
sudo apt-get update && sudo apt-get install -y git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit                                  # log out, then SSH back in
docker --version && docker compose version
```

## 4. Get the code on the server
**Option A: GitHub**
```bash
git clone https://github.com/<you>/<repo>.git crawl-console && cd crawl-console
```
**Option B: no GitHub (from your own computer)**
```bash
scp -i crawl-console.pem cli-chat-crawler.zip ubuntu@<EC2-public-IP>:~
# then on the server:
sudo apt-get install -y unzip && unzip cli-chat-crawler.zip && cd cli-chat-crawler
```

## 5. Configure and start
```bash
cp .env.example .env
nano .env                  # set GEMINI_API_KEY=...   (save: Ctrl+O, Enter, Ctrl+X)
docker compose up -d --build
docker compose ps          # STATUS should become "healthy" after ~15 s
```

## 6. Verify
```bash
curl http://localhost/api/health
# {"ok":true,"llm_mode":"gemini","model":"gemini-2.5-flash",...}
```
Then open `http://<EC2-public-IP>/` in your browser and run the demo prompt:
> Crawl https://example.com, extract the important information, give me a summary, and return the extracted data in JSON format.

The header should read `gemini (gemini-2.5-flash) + sitecrawl CLI`. If it says
"No API key", the key was not picked up: re-check `.env`, then `docker compose up -d --force-recreate`.

## 7. Operate
```bash
docker compose logs -f app         # live logs
docker compose restart             # restart
docker compose down                # stop
git pull && docker compose up -d --build     # deploy an update
```

## 8. Troubleshooting
| Symptom | Fix |
|---|---|
| Page doesn't load | Security group must allow HTTP 80 from your IP; use `http://` not `https://` |
| Header says "No API key" | `.env` missing/typo; run `docker compose up -d --force-recreate` |
| Result says "gemini unavailable (…)" | Bad key, wrong `GEMINI_MODEL`, or quota. The crawl still ran with the fallback. |
| `permission denied` for docker | Log out and back in after `usermod` |
| Build is killed (out of memory) | Add swap: `sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile` |
| 429 errors | Rate limit (12/min per IP) or daily cap; change in `.env` |

## 9. Cost and safety
- Stop (not terminate) the instance after judging to avoid charges; **terminate** and release the Elastic IP when finished.
- The site is public over plain HTTP. Rate limits and a daily cap protect your API quota, but for a
  longer-lived deployment put HTTPS in front (Caddy or an AWS load balancer) and restrict port 80
  to known IPs.
- Never commit `.env` or the `.pem` file.
