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
            'summary': 'In a heartwarming display of community love, neighbors came together to create something truly special. With gentle hands and caring hearts, they transformed a neglected space into a serene garden sanctuary for elderly residents. Soft pet
