# 🌸 MorningGlow

A production-grade, emotionally-safe news curation system that delivers beautiful, verified positive news every morning.

## ✨ Features

- **Real-Time News Fetching**: Pulls verified news from NewsAPI and Google News RSS feeds
- **A Filter System**: 9-category emotional safety filter ensuring only gentle, positive content
- **Factual Accuracy Guardian**: Rejects speculation, clickbait, and unverified claims
- **AI-Powered Summaries**: Warm, feminine summaries (6-7 sentences, 150-170 words) using OpenAI
- **Content Guarantee**: Always delivers 3-5 beautiful stories with emergency fallback stories
- **Beautiful HTML Emails**: Soft pink/rose aesthetic with gentle typography and daily affirmations

## 🌿 The A Filter Categories

1. **Environment Healing** - Coral restoration, reforestation, wildlife conservation
2. **Medical Hope** - Clinical trials, FDA approvals, verified health breakthroughs
3. **Peace & Harmony** - Diplomatic resolutions, cooperation, unity
4. **Human Kindness** - Volunteers, charity, heartwarming rescues
5. **Education Wins** - Scholarships, student achievements, inspiring teachers
6. **Women Empowerment** - Women-led initiatives, female leadership
7. **Ethical Innovation** - Renewable energy, accessibility tech, sustainable engineering
8. **Art & Culture** - Museums, cultural festivals, creative projects
9. **Feel-Good** - Gentle, heartwarming, uplifting stories

## 🚀 Setup

1. **Install Dependencies**:
   ```bash
   # Dependencies are already installed via uv
   ```

2. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   ```

3. **Edit `.env` with your credentials**:
   - `NEWSAPI_KEY`: Get from https://newsapi.org/
   - `OPENAI_API_KEY`: Get from https://platform.openai.com/api-keys
   - `SMTP_USERNAME`, `SMTP_PASSWORD`: Your email credentials
   - `RECIPIENT_EMAIL`: Where to send MorningGlow

## 📧 Usage

Run MorningGlow:
```bash
python morningglow.py
```

The system will:
1. Fetch real-time news from multiple sources
2. Apply accuracy checks and emotional safety filters
3. Generate warm, gentle summaries
4. Ensure 3-5 stories are selected
5. Create a beautiful HTML email
6. Send to your configured recipient email

## 🔒 Privacy & Safety

- Never disturbs you with technical errors (SilentGuardian)
- Rejects all stress-inducing, crisis-focused, or negative content
- Verifies factual accuracy before processing
- Never hallucinates or fabricates news

## 🎨 Email Preview

The system saves an HTML preview to `preview_email.html` that you can open in your browser to see the beautiful email design.

## 🛡️ System Architecture

- **SourceOrchestrator**: Multi-source news fetching with URL validation
- **FactualAccuracyGuardian**: Verification and anti-clickbait protection
- **EmotionalSafetyFilter**: 9-category A filter implementation
- **SummaryGenerator**: OpenAI-powered warm summary creation
- **ContentProcessor**: Complete processing pipeline orchestration
- **ContentGuarantee**: Emergency fallback stories system
- **MorningEmailGuardian**: Beautiful HTML email generation
- **SilentGuardian**: Error handling without user disturbance

## 💝 Philosophy

MorningGlow is built on the principle that how we start our day matters. Every morning deserves to feel like soft sunlight - gentle, warm, and full of hope.
