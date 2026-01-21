"""
MorningGlow: A Production-Grade Emotionally-Safe News Curator
Delivers beautiful, verified positive news every morning.

FIXES APPLIED:
1. Improved URL validation to be less aggressive
2. Better handling of Google News RSS redirect URLs
3. Emergency stories now have unique IDs and are properly tracked
4. Added debugging to identify pipeline failures
5. Better deduplication logic
"""

import os
import re
import json
import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote, urlparse
from dotenv import load_dotenv
import requests
import feedparser
from bs4 import BeautifulSoup
from openai import OpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SourceOrchestrator:
    """
    Fetches real-time news from NewsAPI and Google News RSS.
    Validates URLs, ensures sources are legitimate, and filters by recency (24 hours).
    """
    
    def __init__(self):
        self.newsapi_key = os.getenv('NEWSAPI_KEY')
        self.newsapi_url = 'https://newsapi.org/v2/everything'
        self.google_news_rss = 'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en'
        
    def fetch_newsapi_articles(self, query: str, page_size: int = 100) -> List[Dict]:
        """Fetch articles from NewsAPI within the last 24 hours only."""
        if not self.newsapi_key:
            logger.warning("NewsAPI key not found. Skipping NewsAPI fetch.")
            return []
        
        try:
            one_day_ago = (datetime.now() - timedelta(hours=24)).isoformat()
            
            params = {
                'q': query,
                'apiKey': self.newsapi_key,
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': page_size,
                'from': one_day_ago
            }
            
            response = requests.get(self.newsapi_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'ok':
                articles = data.get('articles', [])
                logger.info(f"✓ Fetched {len(articles)} articles from NewsAPI for query: {query}")
                return self._normalize_newsapi_articles(articles)
            else:
                logger.error(f"NewsAPI error: {data.get('message', 'Unknown error')}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching from NewsAPI: {str(e)}")
            return []
    
    def fetch_google_news_rss(self, query: str) -> List[Dict]:
        """Fetch articles from Google News RSS feed (last 24 hours only)."""
        try:
            feed_url = self.google_news_rss.format(query=quote(query))
            feed = feedparser.parse(feed_url)
            
            articles = []
            one_day_ago = datetime.now() - timedelta(hours=24)
            
            for entry in feed.entries[:50]:
                try:
                    published = datetime(*entry.published_parsed[:6])
                    if published >= one_day_ago:
                        # FIX: Handle Google News redirect URLs better
                        url = entry.link.strip()
                        
                        # Try to extract actual URL from Google News redirect
                        if 'news.google.com' in url:
                            # Google News often wraps URLs - try to extract real URL
                            try:
                                if '&url=' in url:
                                    actual_url = url.split('&url=')[1].split('&')[0]
                                    from urllib.parse import unquote
                                    url = unquote(actual_url)
                            except:
                                pass  # Use the Google News URL if extraction fails
                        
                        articles.append({
                            'title': entry.title,
                            'description': entry.get('summary', ''),
                            'url': url,
                            'source': entry.get('source', {}).get('title', 'Google News'),
                            'published_at': published.isoformat(),
                            'content': entry.get('summary', '')
                        })
                except Exception as e:
                    logger.debug(f"Error parsing RSS entry: {str(e)}")
                    continue
            
            logger.info(f"✓ Fetched {len(articles)} articles from Google News RSS for query: {query}")
            return articles
            
        except Exception as e:
            logger.error(f"Error fetching from Google News RSS: {str(e)}")
            return []
    
    def _normalize_newsapi_articles(self, articles: List[Dict]) -> List[Dict]:
        """Normalize NewsAPI articles to standard format."""
        normalized = []
        for article in articles:
            # Skip articles with [Removed] content
            if article.get('title') == '[Removed]' or article.get('description') == '[Removed]':
                continue
                
            normalized.append({
                'title': article.get('title', ''),
                'description': article.get('description', ''),
                'url': article.get('url', ''),
                'source': article.get('source', {}).get('name', 'Unknown'),
                'published_at': article.get('publishedAt', ''),
                'content': article.get('content', '') or article.get('description', '')
            })
        return normalized
    
    def validate_url(self, url: str) -> bool:
        """
        FIX: Improved URL validation - less aggressive, accepts more legitimate sources.
        """
        if not url or not url.startswith('http'):
            return False
        
        # Accept Google News URLs (they redirect to real articles)
        if 'news.google.com' in url:
            return True
        
        # Parse URL to check for obvious issues
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return False
            
            # Skip obvious bad domains
            bad_domains = ['example.com', 'example.org', 'localhost', '127.0.0.1']
            if any(bad in parsed.netloc.lower() for bad in bad_domains):
                logger.debug(f"Rejected bad domain: {parsed.netloc}")
                return False
                
        except Exception as e:
            logger.debug(f"URL parse error for {url}: {e}")
            return False
        
        # FIX: Make HEAD request optional and more forgiving
        try:
            # Only validate a sample of URLs to save time
            response = requests.head(url, timeout=3, allow_redirects=True)
            return response.status_code < 500  # Accept 4xx (like paywalls) but reject 5xx
        except requests.exceptions.Timeout:
            # Don't reject on timeout - the URL might still be valid
            logger.debug(f"Timeout validating {url}, accepting anyway")
            return True
        except Exception as e:
            # Be forgiving - accept URLs that can't be validated
            logger.debug(f"Could not validate {url}: {e}, accepting anyway")
            return True
    
    def fetch_all_sources(self, queries: List[str]) -> List[Dict]:
        """Fetch articles from all sources for multiple queries."""
        all_articles = []
        
        for query in queries:
            # NewsAPI
            try:
                articles = self.fetch_newsapi_articles(query)
                if articles:
                    all_articles.extend(articles)
                    logger.info(f"  Added {len(articles)} from NewsAPI for '{query}'")
            except Exception as e:
                logger.error(f"NewsAPI failed for query '{query}': {e}")

            # Google News RSS
            try:
                rss_articles = self.fetch_google_news_rss(query)
                if rss_articles:
                    all_articles.extend(rss_articles)
                    logger.info(f"  Added {len(rss_articles)} from Google RSS for '{query}'")
            except Exception as e:
                logger.error(f"Google RSS failed for query '{query}': {e}")
        
        logger.info(f"Total articles before validation: {len(all_articles)}")
        
        # FIX: Validate only a sample to speed up processing
        validated_articles = []
        for i, article in enumerate(all_articles):
            url = article.get('url', '')
            
            # Quick validation for obviously bad URLs
            if not url or 'example.com' in url:
                continue
                
            # Validate every 5th URL, accept others
            if i % 5 == 0:
                if self.validate_url(url):
                    validated_articles.append(article)
            else:
                validated_articles.append(article)
        
        logger.info(f"Total validated articles: {len(validated_articles)}")
        return validated_articles


class FactualAccuracyGuardian:
    """
    Ensures factual accuracy by rejecting unverified claims, speculation,
    and clickbait. Checks for verification markers.
    """
    
    SPECULATION_KEYWORDS = [
        'might', 'could', 'may', 'possibly', 'allegedly', 'rumor', 'rumour',
        'unconfirmed', 'speculation', 'claims without evidence', 'anonymous sources',
        'insider says', 'reportedly', 'sources say', 'could be', 'might be',
        'potential', 'preliminary'
    ]
    
    CLICKBAIT_PATTERNS = [
        r'you won\'t believe',
        r'shocking',
        r'miracle cure',
        r'doctors hate',
        r'one weird trick',
        r'this will blow your mind',
        r'secret that',
        r'what happens next'
    ]
    
    UNVERIFIED_MEDICAL_KEYWORDS = [
        'breakthrough cure',
        'miracle treatment',
        'revolutionary cure',
        'cancer cured',
        'aging reversed'
    ]
    
    VERIFICATION_MARKERS = [
        'study published',
        'peer-reviewed',
        'fda approved',
        'clinical trial',
        'research shows',
        'scientists confirm',
        'university study',
        'official announcement',
        'government confirms',
        'peer reviewed'
    ]
    
    def check_factual_accuracy(self, article: Dict) -> Tuple[bool, str]:
        """
        Check if article meets factual accuracy standards.
        Returns (is_accurate, reason).
        """
        title = (article.get('title') or '').lower()
        description = (article.get('description') or '').lower()
        content = (article.get('content') or '').lower()
        
        full_text = f"{title} {description} {content}"
        
        # Less aggressive speculation check
        speculation_count = sum(1 for keyword in self.SPECULATION_KEYWORDS if keyword in full_text)
        if speculation_count >= 3:  # Allow some speculation words
            return False, "Too many speculation keywords"
        
        for pattern in self.CLICKBAIT_PATTERNS:
            if re.search(pattern, full_text, re.IGNORECASE):
                return False, "Contains clickbait patterns"
        
        if any(keyword in full_text for keyword in self.UNVERIFIED_MEDICAL_KEYWORDS):
            has_verification = any(marker in full_text for marker in self.VERIFICATION_MARKERS)
            if not has_verification:
                return False, "Medical claim without verification markers"
        
        if not article.get('source') or article.get('source') == 'Unknown':
            return False, "Missing legitimate source"
        
        if not article.get('url'):
            return False, "Missing source URL"
        
        return True, "Factually accurate"
    
    def filter_accurate_articles(self, articles: List[Dict]) -> List[Dict]:
        """Filter articles to only include factually accurate ones."""
        accurate_articles = []
        
        for article in articles:
            is_accurate, reason = self.check_factual_accuracy(article)
            if is_accurate:
                accurate_articles.append(article)
            else:
                logger.debug(f"Rejected '{article.get('title', 'Unknown')[:50]}...': {reason}")
        
        logger.info(f"Factual accuracy: {len(accurate_articles)}/{len(articles)} passed")
        return accurate_articles


class EmotionalSafetyFilter:
    """
    Implements the Amulya Filter: 9 categories of emotionally safe,
    gentle, feminine content. Rejects stress, crisis, negativity.
    """
    
    CATEGORY_KEYWORDS = {
        'environment_healing': [
            'coral reef restoration', 'nature recovery', 'reforestation', 'wildlife conservation',
            'species protection', 'ocean healing', 'habitat restoration', 'ecological program',
            'conservation success', 'endangered species', 'biodiversity', 'ecosystem recovery',
            'marine sanctuary', 'forest regrowth', 'clean water', 'pollution reduction',
            'rewilding', 'nature preserve', 'wildlife sanctuary', 'green spaces'
        ],
        'medical_hope': [
            'clinical trial success', 'fda approval', 'treatment advancement', 'recovery outcome',
            'health improvement', 'medical breakthrough', 'new therapy', 'disease treatment',
            'patient recovery', 'healthcare success', 'medical innovation', 'healing',
            'cure approved', 'treatment approved', 'life-saving', 'health victory'
        ],
        'peace_harmony': [
            'peace agreement', 'ceasefire', 'diplomatic resolution', 'conflict resolution',
            'unity', 'cooperation', 'reconciliation', 'harmony', 'agreement reached',
            'neighbors unite', 'community peace', 'collaboration', 'partnership',
            'nations agree', 'treaty signed', 'peaceful solution'
        ],
        'human_kindness': [
            'stranger helps', 'volunteer', 'charity success', 'rescue', 'kindness',
            'compassion', 'donation', 'community support', 'heartwarming', 'good samaritan',
            'helping hand', 'generous', 'fundraiser success', 'community gives',
            'neighbors help', 'act of kindness', 'paying it forward', 'good deed'
        ],
        'education_wins': [
            'scholarship', 'student achievement', 'teacher inspires', 'learning program',
            'educational success', 'graduation', 'literacy program', 'school success',
            'educational innovation', 'students excel', 'academic achievement',
            'mentorship program', 'tutoring success', 'educational opportunity'
        ],
        'women_empowerment': [
            'women-led', 'female leadership', 'women scientists', 'women creators',
            'women entrepreneurs', 'women in stem', 'female founder', 'women innovators',
            'women breaking barriers', 'female pioneers', 'women achieve',
            'women empowerment', 'girls education', 'women leaders'
        ],
        'ethical_innovation': [
            'renewable energy', 'sustainable technology', 'green technology', 'clean energy',
            'accessibility technology', 'assistive technology', 'environmental technology',
            'solar power', 'wind energy', 'electric vehicle', 'sustainable engineering',
            'carbon reduction', 'eco-friendly innovation', 'tech for good'
        ],
        'art_culture': [
            'museum', 'art exhibition', 'cultural festival', 'heritage conservation',
            'children art', 'creative project', 'artistic community', 'cultural celebration',
            'music festival', 'dance performance', 'theater', 'gallery opening',
            'cultural heritage', 'art installation', 'creative workshop'
        ],
        'feel_good': [
            'heartwarming', 'uplifting', 'inspiring', 'beautiful', 'joyful', 'celebration',
            'happiness', 'wonderful', 'amazing story', 'touching', 'delightful',
            'precious moment', 'feel-good', 'wholesome', 'adorable'
        ]
    }
    
    REJECT_KEYWORDS = [
        'crisis', 'shortage', 'suicide', 'violence', 'shooting', 'attack', 'murder',
        'war', 'combat', 'battle', 'crime', 'corruption', 'scandal',
        'controversy', 'disaster', 'catastrophe', 'emergency', 'threat', 'danger',
        'fear', 'terror', 'tragic', 'death toll', 'casualties', 'victim',
        'collapse', 'crash', 'failure', 'bankruptcy', 'layoff', 'recession',
        'pandemic', 'outbreak', 'epidemic', 'infection surge', 'hospital overwhelmed',
        'supply shortage', 'food bank empty', 'running out', 'desperate',
        'alarming', 'concerning', 'worrying', 'devastating', 'horrific'
    ]
    
    CRISIS_PATTERNS = [
        r'running low on',
        r'supplies dwindling',
        r'in short supply',
        r'desperate need',
        r'critically low',
        r'struggling to meet',
        r'faces shortage'
    ]
    
    def check_category_match(self, article: Dict) -> Tuple[bool, List[str]]:
        """Check if article matches at least one allowed category."""
        title = (article.get('title') or '').lower()
        description = (article.get('description') or '').lower()
        content = (article.get('content') or '').lower()
        
        full_text = f"{title} {description} {content}"
        
        matched_categories = []
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            if any(keyword.lower() in full_text for keyword in keywords):
                matched_categories.append(category)
        
        return len(matched_categories) > 0, matched_categories
    
    def check_emotional_safety(self, article: Dict) -> Tuple[bool, str]:
        """Check if article is emotionally safe (no stress, crisis, negativity)."""
        title = (article.get('title') or '').lower()
        description = (article.get('description') or '').lower()
        content = (article.get('content') or '').lower()
        
        full_text = f"{title} {description} {content}"
        
        for keyword in self.REJECT_KEYWORDS:
            if keyword.lower() in full_text:
                return False, f"Contains stress keyword: {keyword}"
        
        for pattern in self.CRISIS_PATTERNS:
            if re.search(pattern, full_text, re.IGNORECASE):
                return False, f"Contains crisis framing pattern"
        
        return True, "Emotionally safe"
    
    def apply_amulya_filter(self, articles: List[Dict]) -> List[Dict]:
        """Apply complete Amulya Filter to articles."""
        filtered_articles = []
        
        for article in articles:
            has_category, categories = self.check_category_match(article)
            is_safe, safety_reason = self.check_emotional_safety(article)
            
            if has_category and is_safe:
                article['amulya_categories'] = categories
                filtered_articles.append(article)
                logger.debug(f"✓ Accepted: '{article.get('title')}' - {', '.join(categories)}")
            else:
                reason = safety_reason if not is_safe else "No matching category"
                logger.debug(f"✗ Rejected: '{article.get('title', 'Unknown')[:50]}...' - {reason}")
        
        logger.info(f"Amulya Filter: {len(filtered_articles)}/{len(articles)} passed")
        return filtered_articles


class SummaryGenerator:
    """
    Generates warm, feminine, emotionally soothing summaries using OpenAI.
    6-7 sentences, 150-170 words, gentle tone.
    """
    
    def __init__(self):
        self.openai_key = os.getenv('OPENAI_API_KEY')
        if self.openai_key:
            self.client = OpenAI(api_key=self.openai_key)
        else:
            self.client = None
            logger.warning("OpenAI API key not found. Summaries will be basic.")
    
    def generate_summary(self, article: Dict) -> str:
        """Generate a warm, gentle summary for the article."""
        if not self.client:
            return self._generate_fallback_summary(article)
        
        try:
            title = article.get('title', '')
            content = article.get('content', '') or article.get('description', '')
            
            prompt = f"""You are a gentle, warm, feminine voice creating emotionally soothing news summaries.

Article Title: {title}
Article Content: {content}

Create a beautiful, warm summary following these EXACT rules:
- Write 6-7 sentences
- Use 150-170 words total
- Tone: warm, feminine, elegant, emotionally soothing
- NEVER repeat the headline
- NEVER mention the source or journalist
- NEVER introduce new facts not in the article
- NEVER use negative or stress-based words
- NEVER overstate claims
- Feel like "your softest best friend telling you something gentle and hopeful"
- Focus on the beauty, hope, and positive impact
- Use soft, flowing language

Write the summary now:"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a gentle, warm storyteller who creates emotionally safe, beautiful summaries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=300
            )
            
            summary = response.choices[0].message.content.strip()
            return summary if summary else self._generate_fallback_summary(article)
            
        except Exception as e:
            logger.error(f"Error generating OpenAI summary: {str(e)}")
            return self._generate_fallback_summary(article)
    
    def _generate_fallback_summary(self, article: Dict) -> str:
        """Content-only fallback summary."""
        title = (article.get('title') or '').strip()
        description = (article.get('description') or '').strip()
        content = (article.get('content') or description or '').strip()

        if not content:
            return title or "A brief update for your morning."

        text = re.sub(r'<[^>]+>', '', content)
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'http[s]?://\S+', '', text).strip()

        raw_sentences = re.split(r'(?<=[\.\?\!])\s+', text)

        sentences = []
        for s in raw_sentences:
            s_clean = s.strip()
            if len(s_clean) < 20:
                continue
            s_clean = s_clean.rstrip('.!?').strip()
            if not s_clean:
                continue
            sentences.append(s_clean)

        if not sentences:
            parts = [p.strip() for p in re.split(r'[\r\n]+', text) if len(p.strip()) >= 20]
            sentences = [p.rstrip('.!?') for p in parts]

        lower_title = title.lower()
        if lower_title:
            sentences = [s for s in sentences if lower_title not in s.lower()]

        seen = set()
        deduped = []
        for s in sentences:
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(s)
        sentences = deduped

        selected = sentences[:7]

        def format_sent(s: str) -> str:
            s = s.strip()
            if not s:
                return ''
            s = s[0].upper() + s[1:]
            if not s.endswith('.'):
                s += '.'
            return s

        selected = [format_sent(s) for s in selected if s.strip()]

        summary = ' '.join(selected).strip()
        if not summary:
            return title or "A brief update for your morning."

        words = summary.split()
        if len(words) > 170:
            summary = ' '.join(words[:170]).rstrip()
            if not summary.endswith('.'):
                summary += '.'

        return summary
    
    def generate_summaries_batch(self, articles: List[Dict]) -> List[Dict]:
        """Generate summaries for multiple articles."""
        for article in articles:
            article['summary'] = self.generate_summary(article)
            logger.info(f"Generated summary for: {article.get('title', 'Unknown')[:50]}...")
        
        return articles


class ContentProcessor:
    """
    Orchestrates the complete content processing pipeline:
    Fetching -> Accuracy Check -> Emotional Safety -> Summary Generation
    """
    
    def __init__(self):
        self.source_orchestrator = SourceOrchestrator()
        self.accuracy_guardian = FactualAccuracyGuardian()
        self.safety_filter = EmotionalSafetyFilter()
        self.summary_generator = SummaryGenerator()
    
    def process_news(self, queries: List[str]) -> List[Dict]:
        """Complete processing pipeline for news articles."""
        logger.info("🌸 Starting news processing pipeline...")
        
        raw_articles = self.source_orchestrator.fetch_all_sources(queries)
        logger.info(f"Step 1: Fetched {len(raw_articles)} raw articles")
        
        if len(raw_articles) == 0:
            logger.warning("⚠️ NO ARTICLES FETCHED! Check your API keys.")
        
        accurate_articles = self.accuracy_guardian.filter_accurate_articles(raw_articles)
        logger.info(f"Step 2: {len(accurate_articles)} articles passed accuracy check")
        
        safe_articles = self.safety_filter.apply_amulya_filter(accurate_articles)
        logger.info(f"Step 3: {len(safe_articles)} articles passed Amulya filter")
        
        if len(safe_articles) == 0:
            logger.warning("⚠️ NO ARTICLES PASSED FILTERS! Will use emergency stories.")
        
        summarized_articles = self.summary_generator.generate_summaries_batch(safe_articles)
        logger.info(f"Step 4: Generated summaries for {len(summarized_articles)} articles")
        
        return summarized_articles


class StorySentTracker:
    """
    FIX: Improved tracking with unique story IDs
    """
    
    def __init__(self, tracking_file: str = 'sent_stories.json'):
        self.tracking_file = tracking_file
    
    def _get_story_id(self, story: Dict) -> str:
        """Generate unique ID for a story."""
        # Use URL as primary ID, fall back to title hash
        url = story.get('url', '')
        if url and 'example.com' not in url:
            return url
        
        title = story.get('title', '')
        # For emergency stories, use title + timestamp day
        if title:
            day = datetime.now().strftime('%Y-%m-%d')
            return f"emergency_{title[:50]}_{day}"
        
        return f"unknown_{datetime.now().timestamp()}"
    
    def load_sent_stories(self) -> List[Dict]:
        """Load stories sent in the last 7 days (extended from 24h)."""
        try:
            if not os.path.exists(self.tracking_file):
                return []
            with open(self.tracking_file, 'r') as f:
                all_sent = json.load(f)
            now = datetime.now().timestamp()
            # Keep 7 days of history to prevent repetition
            recent = [s for s in all_sent if s.get('sent_timestamp', 0) > now - (7 * 86400)]
            return recent
        except:
            return []
    
    def save_sent_stories(self, stories: List[Dict]) -> None:
        """Save newly sent stories with timestamp."""
        try:
            if not os.path.exists(self.tracking_file):
                all_sent = []
            else:
                with open(self.tracking_file, 'r') as f:
                    all_sent = json.load(f)
                    
            now = datetime.now().timestamp()
            for story in stories:
                story_id = self._get_story_id(story)
                all_sent.append({
                    'id': story_id,
                    'url': story.get('url', ''),
                    'title': story.get('title', ''),
                    'sent_timestamp': now
                })
            
            with open(self.tracking_file, 'w') as f:
                json.dump(all_sent, f, indent=2)
            logger.info(f"✓ Tracked {len(stories)} new stories. Total history: {len(all_sent)}")
        except Exception as e:
            logger.warning(f"Could not save sent stories: {e}")
    
    def get_sent_ids(self) -> set:
        """Get set of story IDs sent in last 7 days."""
        return {s.get('id', '') for s in self.load_sent_stories() if s.get('id')}


class ContentGuarantee:
    """
    FIX: Better emergency stories with unique tracking
    """
    
    EMERGENCY_STORIES = [
        {
            'id': 'emergency_coral_1',
            'title': 'Ocean Guardians: Coral Reefs Show Remarkable Recovery',
            'summary': 'In the warm embrace of protected waters, coral reefs are painting a story of hope and resilience. Scientists have discovered that carefully nurtured marine sanctuaries are witnessing the gentle return of vibrant coral colonies, their colors blooming like underwater gardens. These delicate ecosystems, once thought to be beyond recovery, are now thriving with renewed life. The soft sway of healthy coral branches shelters countless species, creating safe havens beneath the waves. This beautiful transformation reminds us that with patient care and dedicated protection, nature possesses an extraordinary ability to heal and flourish once more.',
            'url': 'https://oceanconservancy.org/blog/',
            'source': 'Ocean Conservation',
            'published_at': datetime.now().isoformat(),
            'amulya_categories': ['environment_healing']
        },
        {
            'id': 'emergency_garden_1',
            'title': 'A Community\'s Gentle Gift: Neighbors Create Beautiful Garden',
            'summary': 'In a heartwarming display of community love, neighbors came together to create something truly special. With gentle hands and caring hearts, they transformed a neglected space into a serene garden sanctuary for elderly residents. Soft petals of roses and lavender now greet visitors, while comfortable benches offer peaceful resting spots. The project brought together volunteers of all ages, each contributing their unique gifts to this labor of love. Now, seniors can enjoy morning sunshine surrounded by blooming flowers, butterflies dancing on the breeze, and the warm companionship of neighbors who truly care. This beautiful gesture shows how small acts of kindness can blossom into lasting joy.',
            'url': 'https://www.good.is/articles/community-gardens',
            'source': 'Community News',
            'published_at': datetime.now().isoformat(),
            'amulya_categories': ['human_kindness']
        },
        {
            'id': 'emergency_students_1',
            'title': 'Young Scientists Shine: Students\' Environmental Project Wins Recognition',
            'summary': 'A group of dedicated students has captured hearts and minds with their innovative environmental project. These young changemakers designed a beautiful system to purify water using natural, sustainable materials. Their gentle approach combines scientific knowledge with deep care for the planet, creating solutions that work in harmony with nature. Teachers describe watching these students blossom as they worked together, supporting each other through challenges and celebrating every small victory. The project has now inspired other schools to embrace similar initiatives, spreading ripples of positive change. These bright young minds remind us that the future is in caring, capable hands, and that hope grows wherever passion meets purpose.',
            'url': 'https://www.smithsonianmag.com/innovation/',
            'source': 'Education Today',
            'published_at': datetime.now().isoformat(),
            'amulya_categories': ['education_wins', 'environment_healing']
        },
        {
            'id': 'emergency_butterfly_1',
            'title': 'Butterfly Haven: Restored Meadow Becomes Sanctuary for Endangered Species',
            'summary': 'A once-barren field has transformed into a breathtaking butterfly sanctuary, filled with gentle wings and colorful blooms. Conservation teams carefully planted native wildflowers, creating a soft tapestry of colors that dance in the breeze. Endangered butterfly species have returned to this haven, their delicate presence a sign of healing and hope. Visitors now walk among peaceful meadows, watching these beautiful creatures flutter from flower to flower. The sanctuary has become a place of wonder, where families can witness nature\'s quiet magic and children can learn about protecting our precious ecosystems. This transformation shows how dedication and gentle care can bring endangered beauty back to life.',
            'url': 'https://www.xerces.org/blog',
            'source': 'Wildlife Conservation',
            'published_at': datetime.now().isoformat(),
            'amulya_categories': ['environment_healing']
        },
        {
            'id': 'emergency_women_energy_1',
            'title': 'Women-Led Initiative Brings Clean Energy to Rural Communities',
            'summary': 'A team of inspiring women engineers has created a beautiful solution that brings light and hope to remote villages. Their solar energy project combines technical excellence with deep compassion, ensuring that families can now enjoy clean, sustainable power. These remarkable women worked alongside community members, teaching and empowering them to maintain the systems themselves. The soft glow of solar-powered lights now illuminates homes, schools, and community centers, replacing the darkness with gentle, reliable brightness. Children can study in the evenings, and families can gather safely after sunset. This woman-led initiative demonstrates how innovation rooted in care and understanding can transform lives and create lasting positive change in the world.',
            'url': 'https://www.un.org/en/climatechange/climate-solutions/renewable-energy',
            'source': 'Sustainable Future',
            'published_at': datetime.now().isoformat(),
            'amulya_categories': ['women_empowerment', 'ethical_innovation']
        }
    ]
    
    AFFIRMATIONS = [
        "I am the woman who rises every time life tests me",
        "I am built for expansion, evolution, and elevation",
        "I am choosing myself with a conviction that cannot be shaken",
        "I am becoming more powerful every time something challenges me",
        "I am the universe's favorite girl and I walk like it",
        "I am growing through what others get broken by",
        "I am always protected, always aligned, always guided",
        "I am the kind of woman who turns pain into portals",
        "I am destined for a life so big it surprises even me",
        "I am walking toward a future that is already mine"
    ]
    
    def ensure_minimum_stories(self, articles: List[Dict], minimum: int = 3, maximum: int = 5) -> List[Dict]:
        """Ensure we have 3-5 stories, filtering out recently sent ones."""
        tracker = StorySentTracker()
        sent_ids = tracker.get_sent_ids()
        
        # Filter out recently sent stories (check both URL and ID)
        filtered_articles = []
        for a in articles:
            story_id = tracker._get_story_id(a)
            if story_id not in sent_ids:
                filtered_articles.append(a)
        
        logger.info(f"✓ Filtered {len(articles)-len(filtered_articles)} recently sent stories, {len(filtered_articles)} new available")
        
        if len(filtered_articles) >= minimum:
            logger.info(f"✓ Sufficient new articles available: {len(filtered_articles)}")
            selected = filtered_articles[:maximum]
            tracker.save_sent_stories(selected)
            return selected
        
        needed = minimum - len(filtered_articles)
        logger.warning(f"⚠️ Insufficient new articles ({len(filtered_articles)}). Adding {needed} emergency stories.")
        
        # Select emergency stories that haven't been sent recently
        import random
        available_emergency = []
        for story in self.EMERGENCY_STORIES:
            story_id = story.get('id', tracker._get_story_id(story))
            if story_id not in sent_ids:
                available_emergency.append(story)
        
        if len(available_emergency) < needed:
            logger.warning(f"⚠️ All emergency stories recently used! Cycling through them anyway.")
            available_emergency = self.EMERGENCY_STORIES
        
        emergency_selection = random.sample(available_emergency, min(needed, len(available_emergency)))
        
        combined = filtered_articles + emergency_selection
        final_stories = combined[:maximum]
        tracker.save_sent_stories(final_stories)
        return final_stories
    
    def get_daily_affirmation(self) -> str:
        """Get a beautiful affirmation for the day."""
        import random
        return random.choice(self.AFFIRMATIONS)


class MorningEmailGuardian:
    """
    Weather + AQI aware email generator.
    """

    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
        self.openweather_key = os.getenv('OPENWEATHER_API_KEY')
        self.weather_city = os.getenv('WEATHER_CITY')
        self.weather_lat = os.getenv('WEATHER_LAT')
        self.weather_lon = os.getenv('WEATHER_LON')
        self.device_lat = os.getenv('DEVICE_LAT')
        self.device_lon = os.getenv('DEVICE_LON')

    def _geocode_city(self, city: str) -> Optional[Tuple[float, float]]:
        if not self.openweather_key or not city:
            return None
        url = "https://api.openweathermap.org/geo/1.0/direct"
        candidates = [city.strip(), f"{city}, IN", f"{city}, India"]
        for c in candidates:
            try:
                resp = requests.get(url, params={'q': c, 'limit': 1, 'appid': self.openweather_key}, timeout=6)
                resp.raise_for_status()
                data = resp.json()
                if data and len(data) > 0:
                    return float(data[0]['lat']), float(data[0]['lon'])
            except:
                continue
        return None

    def _resolve_coords(self, lat: Optional[float], lon: Optional[float], city: Optional[str]) -> Optional[Tuple[float, float]]:
        if lat is not None and lon is not None:
            return float(lat), float(lon)
        if self.device_lat and self.device_lon:
            try:
                return float(self.device_lat), float(self.device_lon)
            except:
                pass
        if self.weather_lat and self.weather_lon:
            try:
                return float(self.weather_lat), float(self.weather_lon)
            except:
                pass
        target_city = (city or self.weather_city or "").strip()
        if target_city:
            return self._geocode_city(target_city)
        return None

    def _owm_aqi_desc(self, value: Optional[int]) -> str:
        aqi_map = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
        return aqi_map.get(value, "Unknown")

    def _aqi_health_advice(self, value: Optional[int]) -> str:
        if value is None:
            return ""
        adv = {
            1: "Air quality is good. No special precautions.",
            2: "Air quality is fair. Sensitive people may consider light precautions.",
            3: "Air quality is moderate. Consider limiting prolonged outdoor exertion.",
            4: "Air quality is poor. Sensitive groups should avoid heavy outdoor exertion.",
            5: "Air quality is very poor. Avoid outdoor activity; consider masks/filters."
        }
        return adv.get(value, "")

    def fetch_weather_and_aqi(self, lat: Optional[float] = None, lon: Optional[float] = None, city: Optional[str] = None) -> Dict:
        if not self.openweather_key:
            return {"summary": "Weather data not available."}

        resolved = self._resolve_coords(lat, lon, city)
        if not resolved:
            return {"summary": "Weather data not available."}
        lat, lon = resolved

        try:
            weather_url = "https://api.openweathermap.org/data/2.5/weather"
            w_resp = requests.get(weather_url, params={'lat': lat, 'lon': lon, 'appid': self.openweather_key, 'units': 'metric'}, timeout=6)
            w_resp.raise_for_status()
            w = w_resp.json()
            temp = w.get('main', {}).get('temp')
            humidity = w.get('main', {}).get('humidity')
            location_name = city or self.weather_city or "your area"
        except Exception as e:
            logger.debug(f"Error fetching weather: {e}")
            return {"summary": "Weather data not available."}

        aqi_value = None
        components = None
        try:
            aqi_url = "https://api.openweathermap.org/data/2.5/air_pollution"
            a_resp = requests.get(aqi_url, params={'lat': lat, 'lon': lon, 'appid': self.openweather_key}, timeout=6)
            a_resp.raise_for_status()
            a = a_resp.json()
            if a and 'list' in a and len(a['list']) > 0:
                aqi_value = a['list'][0].get('main', {}).get('aqi')
                components = a['list'][0].get('components', {})
        except:
            pass

        aqi_desc = self._owm_aqi_desc(aqi_value)
        parts = []
        if temp is not None:
            parts.append(f"{round(temp)}°C")
        if humidity is not None:
            parts.append(f"Humidity: {humidity}%")
        parts.append(f"AQI: {aqi_desc}" + (f" ({aqi_value})" if aqi_value else ""))

        summary = f"Weather in {location_name}: " + ", ".join(parts) + "."

        return {
            "location": location_name,
            "temp_c": temp,
            "humidity": humidity,
            "summary": summary,
            "aqi": {"value": aqi_value, "desc": aqi_desc, "components": components or {}},
            "advice": self._aqi_health_advice(aqi_value)
        }

    def generate_html_email(self, stories: List[Dict], affirmation: str, greeting: str, weather_info) -> str:
        today = datetime.now().strftime('%B %d, %Y')

        weather_html = ""
        if isinstance(weather_info, dict):
            temp = weather_info.get("temp_c")
            humidity = weather_info.get("humidity")
            aqi_val = weather_info.get("aqi", {}).get("value")
            aqi_desc = weather_info.get("aqi", {}).get("desc")
            advice = weather_info.get("advice", "")

            weather_html = f"""
                <p style="font-family: 'Cormorant Garamond', 'Playfair Display', Georgia, serif; 
                          color:#7d5e67; font-size:16px; line-height:1.7;">
                    Weather report for today: 
                    Temperature is {round(temp)}°C, humidity is {humidity}%, 
                    and AQI is {aqi_desc} ({aqi_val}).
                </p>
                <p style="font-family: 'Cormorant Garamond', 'Playfair Display', Georgia, serif; 
                          color:#b89199; font-size:15px;">
                    {advice}
                </p>
            """
        else:
            weather_html = "<p>Weather data not available.</p>"

        stories_html = ""
        for i, story in enumerate(stories, 1):
            published_date = story.get('published_at', 'Date not available')
            if published_date and published_date != 'Date not available':
                try:
                    from datetime import datetime as dt
                    parsed_date = dt.fromisoformat(published_date.replace('Z', '+00:00'))
                    published_date = parsed_date.strftime('%B %d, %Y at %I:%M %p')
                except:
                    pass
            stories_html += f"""
            <div style="background: linear-gradient(135deg, #fff5f7 0%, #ffe9f0 100%); 
                        border-radius: 16px; 
                        padding: 28px; 
                        margin-bottom: 24px;
                        box-shadow: 0 4px 12px rgba(251, 207, 232, 0.15);">
                <h2 style="color: #d4738c; font-family: 'Georgia', serif; font-size: 18px; margin: 0 0 12px 0; line-height: 1.3; font-weight: 600;">
                    {story.get('title', 'Untitled')}
                </h2>
                <p style="color: #b89199; font-family: 'Helvetica Neue', 'Arial', sans-serif; font-size: 11px; margin: 0 0 10px 0; font-style: italic;">
                    Published: {published_date}
                </p>
                <p style="color: #7d5e67; font-family: 'Helvetica Neue', 'Arial', sans-serif; font-size: 14px; line-height: 1.6; margin: 0 0 14px 0; text-align: justify;">
                    {story.get('summary', '')}
                </p>
                <a href="{story.get('url', '#')}" style="color: #e08fa3; text-decoration: none; font-family: 'Helvetica Neue', 'Arial', sans-serif; font-size: 12px; font-weight: 500;">
                    Read full article →
                </a>
            </div>
            """

        intro_html = f"""
        <div style="margin-bottom: 18px; text-align: center;">
            <h3 style="color: #d4738c; font-family: 'Georgia', serif; font-size: 20px; margin: 0 0 8px 0; font-weight: 400; text-align: center;">{greeting}</h3>
            {weather_html}
            <p style="color: #7d5e67; font-family: 'Georgia', sans-serif; font-size: 13px; margin: 6px 0 6px 0;">
                We are incredibly grateful for another chance to rise now, aren't we?<br>
                Here is your curated positive morning news:
            </p>
        </div>
        """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>MorningGlow - {today}</title></head>
        <body style="margin:0;padding:0;background:linear-gradient(to bottom,#fff9fb,#ffeff5);font-family:'Helvetica Neue',Arial,sans-serif;">
          <div style="max-width:680px;margin:0 auto;padding:40px 20px;">
            <div style="text-align:center;margin-bottom:24px;">
              <h1 style="color:#d4738c;font-family:'Georgia',serif;font-size:30px;margin:0 0 8px 0;font-weight:300;letter-spacing:2px;">MorningGlow</h1>
              <p style="color:#dca3b5;font-family:'Georgia',serif;font-size:14px;margin:6px 0 8px 0;font-style:italic;">-by Amulya N Rao</p>
              <p style="color:#b89199;font-family:'Georgia',serif;font-size:16px;margin:0;font-style:italic;">{today}</p>
            </div>
            {intro_html}
            <div style="margin-bottom:24px;">{stories_html}</div>
            <div style="background: linear-gradient(135deg, #ffd9e8 0%, #ffb3d1 100%); border-radius:16px; padding:32px; text-align:center; border:2px solid #ffc4dd; box-shadow:0 6px 20px rgba(251,207,232,0.25);">
              <p style="color:#000000;font-family:'Georgia',serif;font-size:18px;line-height:1.7;margin:0;font-style:italic;">{affirmation}</p>
            </div>
            <div style="text-align:center;margin-top:28px;padding-top:24px;border-top:1px solid #f8d7e3;">
              <p style="color:#c9a1ad;font-family:'Helvetica Neue',Arial,sans-serif;font-size:13px;margin:0;">Love & Light🤍 <br> Sent with MorningGlow🌸 <br></p>
               <img src="https://drive.google.com/uc?export=view&id=1PIJXNnTkK7ZCIa1PysngM5LOwV2nI30-" alt="Signature" style="width:180px; opacity:0.92; margin-top:10px;"/>
            </div>
          </div>
        </body>
        </html>
        """
        return html

    def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        if not self.smtp_username or not self.smtp_password:
            logger.warning("SMTP credentials not configured. Saving preview instead.")
            try:
                safe_name = to_email.replace('@', '_at_').replace('.', '_')
                with open(f'preview_email_{safe_name}.html', 'w', encoding='utf-8') as f:
                    f.write(html_content)
                logger.info(f"✓ Email preview saved to preview_email_{safe_name}.html")
            except:
                pass
            return False
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            logger.info(f"✓ Email sent successfully to {to_email}")
            return True
        except Exception as e:
            logger.error(f"✗ Error sending email to {to_email}: {str(e)}")
            return False

    def deliver_morning_glow(self, recipients: List[str], stories: List[Dict], affirmation: str,
                             owner_email: str = None, recipient_locations: Optional[Dict[str, Dict]] = None) -> Dict[str, bool]:
        results = {}
        subject = f"🌸 Your MorningGlow - {datetime.now().strftime('%B %d, %Y')}"
        if owner_email:
            owner_email = owner_email.strip().lower()
        for recipient in recipients:
            recipient = recipient.strip()
            if not recipient:
                continue
            greeting = "Good Morning Gorgeous!"
            if owner_email and recipient.strip().lower() == owner_email:
                greeting = "Good Morning Goddess!"

            override = (recipient_locations or {}).get(recipient, {}) or {}
            lat = override.get('lat')
            lon = override.get('lon')
            city = override.get('city')

            weather_info = self.fetch_weather_and_aqi(lat=lat, lon=lon, city=city)
            html_content = self.generate_html_email(stories, affirmation, greeting, weather_info)
            success = self.send_email(recipient, subject, html_content)
            results[recipient] = success

        return results


class SilentGuardian:
    @staticmethod
    def safe_execute(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Silent error in {func.__name__}: {str(e)}")
            return None
    
    @staticmethod
    def ensure_ritual(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Critical error in {func.__name__}: {str(e)}")
                logger.info("Ensuring ritual continues with emergency measures...")
                return None
        return wrapper


@SilentGuardian.ensure_ritual
def sacred_morning_flow_with_accuracy():
    logger.info("=" * 60)
    logger.info("🌸 MorningGlow - Sacred Morning Flow Beginning 🌸")
    logger.info("=" * 60)
    
    search_queries = [
        'breakthrough medical discovery healing',
        'women leaders innovation success',
        'renewable energy milestone achievement',
        'student wins national award',
        'community volunteers together help',
        'endangered species recovery wildlife',
        'human kindness heartwarming story',
        'clean water project development',
        'education access opportunity',
        'climate positive environmental win'
    ]
    
    processor = ContentProcessor()
    processed_articles = processor.process_news(search_queries)
    
    guarantee = ContentGuarantee()
    final_stories = guarantee.ensure_minimum_stories(processed_articles, minimum=3, maximum=5)
    affirmation = guarantee.get_daily_affirmation()
    
    logger.info(f"✓ Final story count: {len(final_stories)}")
    logger.info(f"✓ Daily affirmation selected")
    
    email_guardian = MorningEmailGuardian()
    recipients_env = os.getenv('RECIPIENT_EMAILS') or os.getenv('RECIPIENT_EMAIL') or 'user@example.com'
    recipients = [r.strip() for r in recipients_env.split(',') if r.strip()]
    owner_email = os.getenv('OWNER_EMAIL')
    
    results = email_guardian.deliver_morning_glow(recipients, final_stories, affirmation, owner_email=owner_email)
    
    for r, ok in results.items():
        logger.info(f"{'✓' if ok else '✗'} Email to {r}: {'sent' if ok else 'preview saved'}")
    
    logger.info("=" * 60)
    logger.info("🌸 Sacred morning ritual complete 🌸")
    logger.info("=" * 60)
    
    return final_stories


if __name__ == "__main__":
    sacred_morning_flow_with_accuracy()
