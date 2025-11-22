# MorningGlow - Emotionally-Safe News Curation System

## Overview

MorningGlow is a production-grade news curation system that delivers verified positive news through beautifully formatted HTML emails. The system fetches real-time news from NewsAPI and Google News RSS feeds, filters content through a 9-category emotional safety system (the "Amulya Filter"), and generates warm, feminine AI-powered summaries using OpenAI. The application guarantees delivery of 3-5 uplifting stories daily with emergency fallback content, ensuring users receive gentle, factual, and emotionally-safe news every morning.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Components

**1. News Fetching Architecture**
- **Multi-Source Strategy**: The system uses a dual-source approach combining NewsAPI (REST API) and Google News RSS feeds to ensure content availability and diversity
- **Rationale**: Multiple sources provide redundancy and broader content coverage, reducing dependency on a single news provider
- **Recency Filter**: Only accepts articles published within the last 14 days to ensure freshness and relevance
- **URL Validation**: Implements validation logic to ensure legitimate source URLs and filter out unreliable content

**2. Content Filtering System (Amulya Filter)**
- **9-Category Classification**: Articles are evaluated against nine positive categories: Environment Healing, Medical Hope, Peace & Harmony, Human Kindness, Education Wins, Women Empowerment, Ethical Innovation, Art & Culture, and Feel-Good stories
- **Dual-Layer Filtering**: 
  - Category matching ensures content aligns with positive themes
  - Factual accuracy guardian rejects speculation, clickbait, and unverified claims
- **Design Decision**: Categorical filtering provides structure while the accuracy layer prevents misinformation, balancing emotional safety with factual integrity

**3. AI Summarization Layer**
- **OpenAI Integration**: Uses OpenAI's API to generate summaries with specific tonal requirements
- **Constraints**: 6-7 sentences, 150-170 word count, warm and feminine tone
- **Approach**: AI summarization enables consistent emotional tone while maintaining factual accuracy from source material
- **Alternative Considered**: Rule-based extraction was rejected in favor of AI for better narrative quality and emotional resonance

**4. Content Guarantee System**
- **Target Delivery**: 3-5 stories per email
- **Emergency Fallback**: System includes fallback stories to ensure delivery even when real-time sources fail
- **Rationale**: Guarantees user experience consistency and prevents empty/failed email sends

**5. Email Delivery System**
- **SMTP Protocol**: Uses standard SMTP for email delivery with MIME multipart messages
- **HTML Templating**: Inline CSS with soft pink/rose color palette (#d4738c, #fff9fb, #ffeff5)
- **Design Philosophy**: Beautiful, calming visual design matches the emotional safety of content
- **Structure**: Title, date, story cards with summaries, source links, and daily affirmations

### Data Flow

1. **Ingestion**: SourceOrchestrator fetches from NewsAPI + Google News RSS
2. **Filtering**: Articles pass through Amulya Filter categories and factual accuracy checks
3. **Enrichment**: OpenAI generates warm summaries for approved articles
4. **Selection**: Top 3-5 stories selected, fallbacks added if needed
5. **Delivery**: HTML email compiled and sent via SMTP

### Configuration Management

**Environment Variables**: Uses `.env` file for sensitive configuration
- `NEWSAPI_KEY`: NewsAPI authentication
- `OPENAI_API_KEY`: OpenAI API access
- `SMTP_USERNAME`, `SMTP_PASSWORD`: Email server credentials
- `RECIPIENT_EMAIL`: Destination address

**Rationale**: Environment-based configuration enables easy deployment across environments without code changes

### Error Handling & Logging

- **Structured Logging**: Python logging module with timestamp, level, and message formatting
- **Graceful Degradation**: System continues operation with available sources if one fails
- **Fallback Content**: Ensures email delivery even during API failures

### Technology Stack

- **Language**: Python
- **HTTP Requests**: `requests` library for REST API calls
- **Feed Parsing**: `feedparser` for RSS consumption
- **HTML Parsing**: `BeautifulSoup` for content extraction
- **AI**: OpenAI Python SDK
- **Email**: Standard library `smtplib` and `email.mime`

## External Dependencies

### Third-Party APIs

**1. NewsAPI (newsapi.org)**
- **Purpose**: Primary source for real-time news articles
- **Endpoint**: `https://newsapi.org/v2/everything`
- **Authentication**: API key via query parameter
- **Rate Limits**: Dependent on subscription tier
- **Data Retrieved**: Article title, description, URL, publish date, source

**2. OpenAI API (platform.openai.com)**
- **Purpose**: Generate emotionally-safe, warm summaries of news articles
- **Model**: Likely GPT-3.5/GPT-4 (specific model not specified in code)
- **Authentication**: API key via bearer token
- **Usage**: Summary generation with strict word count and tone requirements

**3. Google News RSS**
- **Purpose**: Secondary news source via RSS feeds
- **Endpoint**: `https://news.google.com/rss/search`
- **Authentication**: None (public RSS)
- **Format**: XML/RSS feed
- **Parsing**: Via feedparser library

### External Services

**SMTP Email Server**
- **Purpose**: Email delivery for daily MorningGlow digest
- **Protocol**: SMTP (standard email protocol)
- **Authentication**: Username/password credentials
- **Configuration**: User-provided via environment variables

### Python Package Dependencies

- `python-dotenv`: Environment variable management
- `requests`: HTTP client for API calls
- `feedparser`: RSS/Atom feed parsing
- `beautifulsoup4`: HTML content parsing and extraction
- `openai`: Official OpenAI Python client
- Standard library: `smtplib`, `email`, `logging`, `datetime`, `json`, `re`, `os`, `urllib`

### Data Storage

- **No Database**: System operates statelessly, fetching fresh content on each run
- **Design Trade-off**: Stateless design simplifies deployment but doesn't track sent stories (may result in duplicates across days)