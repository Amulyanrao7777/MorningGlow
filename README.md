# 🌤️ MorningGlow

**MorningGlow** is a production-grade, emotionally-safe news curation system that sends you a gentle, beautifully formatted email with **verified positive stories every morning**.

It combines real-time news sources, safety & accuracy filters, and AI-written summaries to make sure your inbox starts the day with calm, not chaos.

---

## ✨ Key Features

- **Real-time curated news**
  - Pulls stories from **NewsAPI** and **Google News RSS**.
  - Focuses only on credible sources.

- **Emotional safety filter (“A Filter”)**
  - 9 themed categories of safe, uplifting news:
    1. Environment Healing  
    2. Medical Hope  
    3. Peace & Harmony  
    4. Human Kindness  
    5. Education Wins  
    6. Women Empowerment  
    7. Ethical Innovation  
    8. Art & Culture  
    9. Feel-Good  
  - Filters out crisis content, violence, panic, and stress-heavy stories.

- **Factual accuracy guardrails**
  - Rejects obvious clickbait, speculation, and unverified claims before summarizing.
  - Never fabricates news: summaries are always grounded in the original articles.

- **AI-powered warm summaries**
  - Uses **OpenAI** to write soft, human, hopeful summaries.
  - Each story is ~6–7 sentences (~150–170 words), written in a calm, reassuring tone.

- **Content guarantee**
  - Always sends **3–5 good stories**.
  - Has fallback stories ready in case sources are sparse.

- **Beautiful HTML email**
  - Soft, rose-toned aesthetic.
  - Gentle typography, structured layout, and a daily affirmation.
  - Previewable locally via `preview_email.html`.

---

## 🏗️ System Architecture

MorningGlow is built as a set of focused components that work together:

- **SourceOrchestrator**  
  Coordinates multiple sources (NewsAPI + Google News RSS), validates URLs, and collects candidate stories.

- **FactualAccuracyGuardian**  
  Applies basic verification & anti-clickbait checks so only trustworthy stories are allowed into the pipeline.

- **EmotionalSafetyFilter**  
  Implements the 9-category A Filter to keep only emotionally-safe, uplifting content.

- **SummaryGenerator**  
  Uses OpenAI to generate warm, humanlike summaries while staying grounded to the original article.

- **ContentProcessor**  
  Orchestrates the full pipeline: fetch → filter → verify → summarize → select → package.

- **ContentGuarantee**  
  Ensures there are always 3–5 stories by falling back to pre-validated “evergreen” positive stories if needed.

- **MorningEmailGuardian**  
  Builds the final HTML email: layout, colors, sections, affirmation, and links.

- **SilentGuardian**  
  Handles logging and errors quietly so the user gets a seamless experience without noisy error mails.

---

## 🧰 Tech Stack

- **Language:** Python  
- **News Sources:** NewsAPI, Google News RSS  
- **AI:** OpenAI API for summaries  
- **Email:** SMTP (HTML emails)  
- **Environment & Dependencies:**  
  - `pyproject.toml` / `uv.lock` (for `uv`-based workflows)  
  - `requirements.txt` (for classic `pip` installs)  
- **Other:** Logging, JSON storage (`sent_stories.json`) for deduplication

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Amulyanrao7777/MorningGlow.git
cd MorningGlow
2. Install dependencies
Using pip:

bash
Copy code
pip install -r requirements.txt
If you’re using uv or another modern environment manager, you can also rely on pyproject.toml / uv.lock.

3. Configure environment variables
Copy the example file and edit your credentials:

bash
Copy code
cp .env.example .env
Open .env and fill in:

NEWSAPI_KEY – from https://newsapi.org

OPENAI_API_KEY – from https://platform.openai.com/api-keys

SMTP_USERNAME / SMTP_PASSWORD – your email credentials (app password recommended)

RECIPIENT_EMAIL – where MorningGlow will send the curated newsletter

(If .env.example includes additional fields like SMTP host/port, configure those as well.)

▶️ Usage
Run MorningGlow manually:

bash
Copy code
python morningglow.py
On each run, MorningGlow will:

Fetch fresh stories from NewsAPI + Google News RSS

Apply factual accuracy checks

Filter using the 9-category emotional safety filter

Generate warm summaries using OpenAI

Ensure 3–5 stories make it through (using fallbacks if needed)

Render a beautiful HTML email

Send it to RECIPIENT_EMAIL via SMTP

Save a local preview as preview_email.html

You can open preview_email.html in your browser to see exactly what the email looks like.

⏰ Automation & Scheduling
You can schedule MorningGlow to run every morning.

On Linux / macOS (Cron)
Edit your crontab:

bash
Copy code
crontab -e
Add a line like:

bash
Copy code
0 7 * * * /usr/bin/python3 /path/to/MorningGlow/morningglow.py >> /path/to/MorningGlow/logs/cron.log 2>&1
This runs it every day at 7:00 AM.

On Windows (Task Scheduler)
Create a new Basic Task

Trigger: Daily at your chosen time

Action: Start a program → python.exe

Arguments: C:\path\to\MorningGlow\morningglow.py

With GitHub Actions
There is a .github/workflows directory in this repo.
You can configure a scheduled workflow (cron) to run MorningGlow on a server or container, if desired.

🔒 Privacy & Safety
No user data is stored beyond what’s needed to send the email.

Stories are pulled only from external news APIs / RSS feeds.

The system is designed to avoid crisis-heavy or triggering content.

Summaries are generated with guardrails so that the model does not invent news.

📸 Email Preview
Every run writes a preview file: preview_email.html

You can also find branding assets (like the logo / header) inside the assets/ folder.

Open the preview file in any browser to iterate on colors, fonts, or layout.

🌱 Philosophy
MorningGlow is built around a simple idea:

How you start your day matters.

Most news feeds begin with stress, conflict, and urgency.
MorningGlow is an intentional alternative: a small, consistent ritual of calm, verified, hopeful information that doesn’t ignore reality but chooses to spotlight healing, progress, and kindness.


📄 License
This project is licensed under the MIT License.
See the LICENSE file for full details.

markdown
Copy code

If you want, I can also:

- Add a **“For Recruiters”** section that explicitly spells out what *you* did (great for your resume link)  
- Or make a **shorter “lite” README** for GitHub and keep this as `docs/OVERVIEW.md`.
::contentReference[oaicite:0]{index=0}






