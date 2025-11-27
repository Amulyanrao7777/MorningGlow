"""
MorningGlow: A Production-Grade Emotionally-Safe News Curator
Delivers beautiful, verified positive news every morning.
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
from urllib.parse import quote
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
    Validates URLs, ensures sources are legitimate, and filters by recency (14 days).
    """
    
    def __init__(self):
        self.newsapi_key = os.getenv('NEWSAPI_KEY')
        self.newsapi_url = 'https://newsapi.org/v2/everything'
        self.google_news_rss = 'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en'
        
    def fetch_newsapi_articles(self, query: str, page_size: int = 100) -> List[Dict]:
        """Fetch articles from NewsAPI within the last 14 days."""
        if not self.newsapi_key:
            logger.warning("NewsAPI key not found. Skipping NewsAPI fetch.")
            return []
        
        try:
            fourteen_days_ago = (datetime.now() - timedelta(days=14)).isoformat()
            
            params = {
                'q': query,
                'apiKey': self.newsapi_key,
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': page_size,
                'from': fourteen_days_ago
            }
            
            response = requests.get(self.newsapi_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'ok':
                articles = data.get('articles', [])
                logger.info(f"Fetched {len(articles)} articles from NewsAPI for query: {query}")
                return self._normalize_newsapi_articles(articles)
            else:
                logger.error(f"NewsAPI error: {data.get('message', 'Unknown error')}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching from NewsAPI: {str(e)}")
            return []
    
    def fetch_google_news_rss(self, query: str) -> List[Dict]:
        """Fetch articles from Google News RSS feed."""
        try:
            feed_url = self.google_news_rss.format(query=quote(query))
            feed = feedparser.parse(feed_url)
            
            articles = []
            fourteen_days_ago = datetime.now() - timedelta(days=14)
            
            for entry in feed.entries[:50]:
                try:
                    published = datetime(*entry.published_parsed[:6])
                    if published >= fourteen_days_ago:
                        url = entry.link.replace(' ', '')
                        
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
            
            logger.info(f"Fetched {len(articles)} articles from Google News RSS for query: {query}")
            return articles
            
        except Exception as e:
            logger.error(f"Error fetching from Google News RSS: {str(e)}")
            return []
    
    def _normalize_newsapi_articles(self, articles: List[Dict]) -> List[Dict]:
        """Normalize NewsAPI articles to standard format."""
        normalized = []
        for article in articles:
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
        """Validate that URL is accessible and legitimate."""
        if not url or not url.startswith('http'):
            return False
        
        try:
            response = requests.head(url, timeout=5, allow_redirects=True)
            return response.status_code < 400
        except Exception:
            return False
    
    def fetch_all_sources(self, queries: List[str]) -> List[Dict]:
        """Fetch articles from all sources for multiple queries."""
        all_articles = []
        
        for query in queries:
            try:
                articles = self.fetch_newsapi_articles(query)
                if articles:
                    all_articles.extend(articles)
            except Exception as e:
                logger.error(f"NewsAPI failed for query '{query}', continuing pipeline: {e}")

            all_articles.extend(self.fetch_google_news_rss(query))
        
        validated_articles = []
        for article in all_articles:
            if article.get('url') and self.validate_url(article['url']):
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
        'potential', 'preliminary', 'early study', 'early results'
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
        
        if any(keyword in full_text for keyword in self.SPECULATION_KEYWORDS):
            return False, "Contains speculation or unverified claims"
        
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
                logger.debug(f"Rejected article '{article.get('title', 'Unknown')}': {reason}")
        
        logger.info(f"Factual accuracy check: {len(accurate_articles)}/{len(articles)} passed")
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
        'war', 'combat', 'battle', 'conflict', 'crime', 'corruption', 'scandal',
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
        
        if title in description or description in title:
            if len(description) < len(title) * 1.5:
                return False, "Description repeats headline"
        
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
                logger.debug(f"Accepted: '{article.get('title')}' - Categories: {', '.join(categories)}")
            else:
                reason = safety_reason if not is_safe else "No matching category"
                logger.debug(f"Rejected: '{article.get('title', 'Unknown')}' - {reason}")
        
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
            
            summary = response.choices[0].message.content
            if summary:
                summary = summary.strip()
            else:
                return self._generate_fallback_summary(article)
            
            word_count = len(summary.split())
            if word_count < 140 or word_count > 200:
                logger.debug(f"Summary word count {word_count} outside ideal range 150-170")
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating OpenAI summary: {str(e)}")
            return self._generate_fallback_summary(article)
    
    def _generate_fallback_summary(self, article: Dict) -> str:
        """
        Content-only fallback summary for when OpenAI is unavailable.
        - Uses only sentences present in article content/description (no invented or tonal lines).
        - Prefers up to 7 real sentences; will return fewer if the article lacks enough sentence content.
        - Cleans HTML/URLs and enforces punctuation and a soft 170-word maximum.
        """
        title = (article.get('title') or '').strip()
        description = (article.get('description') or '').strip()
        content = (article.get('content') or description or '').strip()

        # If nothing to work with, return title or a very short neutral fallback
        if not content:
            return title or "A brief update for your morning."

        # Clean HTML and links
        text = re.sub(r'<[^>]+>', '', content)
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'http[s]?://\S+', '', text).strip()

        # Split into sentences (basic rule: split after . ? ! followed by space)
        raw_sentences = re.split(r'(?<=[\.\?\!])\s+', text)

        # Keep only reasonably long sentences, remove trailing punctuation, trim
        sentences = []
        for s in raw_sentences:
            s_clean = s.strip()
            # ignore very short fragments
            if len(s_clean) < 20:
                continue
            # drop trailing punctuation for normalized comparison
            s_clean = s_clean.rstrip('.!?').strip()
            if not s_clean:
                continue
            sentences.append(s_clean)

        # If nothing after sentence-splitting, try newline-based parts as a fallback
        if not sentences:
            parts = [p.strip() for p in re.split(r'[\r\n]+', text) if len(p.strip()) >= 20]
            sentences = [p.rstrip('.!?') for p in parts]

        # Avoid sentences that just repeat the title verbatim
        lower_title = title.lower()
        if lower_title:
            sentences = [s for s in sentences if lower_title not in s.lower()]

        # Deduplicate very similar entries (simple exact-match dedupe)
        seen = set()
        deduped = []
        for s in sentences:
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(s)
        sentences = deduped

        # Select up to 7 sentences (prefer earlier sentences)
        selected = sentences[:7]

        # Ensure punctuation at the end of each sentence and capitalization
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

        # Soft truncate to 170 words (trim at word boundary, preserve punctuation)
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
        logger.info("Starting news processing pipeline...")
        
        raw_articles = self.source_orchestrator.fetch_all_sources(queries)
        logger.info(f"Step 1: Fetched {len(raw_articles)} raw articles")
        
        accurate_articles = self.accuracy_guardian.filter_accurate_articles(raw_articles)
        logger.info(f"Step 2: {len(accurate_articles)} articles passed accuracy check")
        
        safe_articles = self.safety_filter.apply_amulya_filter(accurate_articles)
        logger.info(f"Step 3: {len(safe_articles)} articles passed Amulya filter")
        
        summarized_articles = self.summary_generator.generate_summaries_batch(safe_articles)
        logger.info(f"Step 4: Generated summaries for {len(summarized_articles)} articles")
        
        return summarized_articles


class StorySentTracker:
    """
    Tracks stories sent in the last 24 hours to avoid repetition.
    Stores sent article URLs with timestamps.
    """
    
    def __init__(self, tracking_file: str = 'sent_stories.json'):
        self.tracking_file = tracking_file
    
    def load_sent_stories(self) -> List[Dict]:
        """Load stories sent in the last 24 hours."""
        try:
            if not os.path.exists(self.tracking_file):
                return []
            with open(self.tracking_file, 'r') as f:
                all_sent = json.load(f)
            now = datetime.now().timestamp()
            recent = [s for s in all_sent if s.get('sent_timestamp', 0) > now - 86400]
            return recent
        except: return []
    
   def save_sent_stories(self, stories: List[Dict]) -> None:
        """Save newly sent stories with timestamp - keep full history."""
       try:
           if not os.path.exists(self.tracking_file):
            all_sent = []
           else:
               with open(self.tracking_file, 'r') as f:
                   all_sent = json.load(f)
                   
           now = datetime.now().timestamp()
           for story in stories:
               all_sent.append({'url': story.get('url', ''), 'title': story.get('title', ''), 'sent_timestamp': now})
            
           with open(self.tracking_file, 'w') as f:
               json.dump(all_sent, f, indent=2) 
           logger.info(f"Tracked {len(stories)} new stories sent. Total history: {len(all_sent)}")
      except Exception as e:
          logger.warning(f"Could not save sent stories: {e}")
            
    def get_sent_urls(self) -> set:
        """Get set of URLs sent in last 24 hours."""
        return {s.get('url', '') for s in self.load_sent_stories() if s.get('url')}


class ContentGuarantee:
    """
    Guarantees 3-5 beautiful stories are always available.
    Uses emergency fallback stories when real-time news is insufficient.
    """
    
    EMERGENCY_STORIES = [
        {
            'title': 'Ocean Guardians: Coral Reefs Show Remarkable Recovery',
            'summary': 'In the warm embrace of protected waters, coral reefs are painting a story of hope and resilience. Scientists have discovered that carefully nurtured marine sanctuaries are witnessing the gentle return of vibrant coral colonies, their colors blooming like underwater gardens. These delicate ecosystems, once thought to be beyond recovery, are now thriving with renewed life. The soft sway of healthy coral branches shelters countless species, creating safe havens beneath the waves. This beautiful transformation reminds us that with patient care and dedicated protection, nature possesses an extraordinary ability to heal and flourish once more.',
            'url': 'https://oceanconservancy.org',
            'source': 'Ocean Conservation',
            'published_at': datetime.now().isoformat(),
            'amulya_categories': ['environment_healing']
        },
        {
            'title': 'A Community\'s Gentle Gift: Neighbors Create Beautiful Garden for Elderly Residents',
            'summary': 'In a heartwarming display of community love, neighbors came together to create something truly special. With gentle hands and caring hearts, they transformed a neglected space into a serene garden sanctuary for elderly residents. Soft petals of roses and lavender now greet visitors, while comfortable benches offer peaceful resting spots. The project brought together volunteers of all ages, each contributing their unique gifts to this labor of love. Now, seniors can enjoy morning sunshine surrounded by blooming flowers, butterflies dancing on the breeze, and the warm companionship of neighbors who truly care. This beautiful gesture shows how small acts of kindness can blossom into lasting joy.',
            'url': 'https://example.com/community-garden',
            'source': 'Community News',
            'published_at': datetime.now().isoformat(),
            'amulya_categories': ['human_kindness']
        },
        {
            'title': 'Young Scientists Shine: Students\' Environmental Project Wins National Recognition',
            'summary': 'A group of dedicated students has captured hearts and minds with their innovative environmental project. These young changemakers designed a beautiful system to purify water using natural, sustainable materials. Their gentle approach combines scientific knowledge with deep care for the planet, creating solutions that work in harmony with nature. Teachers describe watching these students blossom as they worked together, supporting each other through challenges and celebrating every small victory. The project has now inspired other schools to embrace similar initiatives, spreading ripples of positive change. These bright young minds remind us that the future is in caring, capable hands, and that hope grows wherever passion meets purpose.',
            'url': 'https://example.com/student-achievement',
            'source': 'Education Today',
            'published_at': datetime.now().isoformat(),
            'amulya_categories': ['education_wins', 'environment_healing']
        },
        {
            'title': 'Butterfly Haven: Restored Meadow Becomes Sanctuary for Endangered Species',
            'summary': 'A once-barren field has transformed into a breathtaking butterfly sanctuary, filled with gentle wings and colorful blooms. Conservation teams carefully planted native wildflowers, creating a soft tapestry of colors that dance in the breeze. Endangered butterfly species have returned to this haven, their delicate presence a sign of healing and hope. Visitors now walk among peaceful meadows, watching these beautiful creatures flutter from flower to flower. The sanctuary has become a place of wonder, where families can witness nature\'s quiet magic and children can learn about protecting our precious ecosystems. This transformation shows how dedication and gentle care can bring endangered beauty back to life.',
            'url': 'https://example.com/butterfly-sanctuary',
            'source': 'Wildlife Conservation',
            'published_at': datetime.now().isoformat(),
            'amulya_categories': ['environment_healing']
        },
        {
            'title': 'Women-Led Initiative Brings Clean Energy to Rural Communities',
            'summary': 'A team of inspiring women engineers has created a beautiful solution that brings light and hope to remote villages. Their solar energy project combines technical excellence with deep compassion, ensuring that families can now enjoy clean, sustainable power. These remarkable women worked alongside community members, teaching and empowering them to maintain the systems themselves. The soft glow of solar-powered lights now illuminates homes, schools, and community centers, replacing the darkness with gentle, reliable brightness. Children can study in the evenings, and families can gather safely after sunset. This woman-led initiative demonstrates how innovation rooted in care and understanding can transform lives and create lasting positive change in the world.',
            'url': 'https://example.com/women-clean-energy',
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
"I am the universe’s favorite girl and I walk like it",
"I am growing through what others get broken by",
"I am always protected, always aligned, always guided",
"I am the kind of woman who turns pain into portals",
"I am destined for a life so big it surprises even me",
"I am walking toward a future that is already mine",

"I am worthy of everything I desire simply because I exist",
"I am letting abundance flow to me without resistance",
"I am attracting opportunities that match my highest self",
"I am claiming the things I used to shy away from",
"I am walking with a royalty mindset every day",
"I am letting my confidence speak louder than my fear",
"I am not asking permission to shine anymore",
"I am becoming the version of me I always daydreamed about",
"I am trusting myself even when I’m uncomfortable",
"I am releasing every belief that tried to make me small",

"I am divinely supported in everything I do",
"I am magnetic to blessings, miracles, and breakthroughs",
"I am the luckiest woman alive because I decide to be",
"I am attracting success effortlessly because I embody it",
"I am moving through life like everything bends for me",
"I am worthy of desires that scare me",
"I am ready for the abundance meant for me",
"I am releasing doubt and stepping into destiny",
"I am a powerful creator of my own life",
"I am always in the right place at the right time",

"I am not afraid of change because I evolve with ease",
"I am guided toward everything that is meant for me",
"I am trusting the process even when I can’t see the end",
"I am allowed to take up limitless space",
"I am aligning with higher versions of myself daily",
"I am choosing growth over fear every single morning",
"I am shifting into the woman who holds everything she prays for",
"I am allowing my energy to speak before my words do",
"I am bigger than any obstacle in front of me",
"I am worthy of taking up space loudly and unapologetically",

"I am embracing a future that feels like freedom",
"I am prioritizing my peace, my power, and my standards",
"I am the kind of woman who gets everything she asks for",
"I am not settling for anything less than extraordinary",
"I am becoming too aligned to be overlooked",
"I am rewriting every story that tried to box me in",
"I am receiving love, success, and abundance without guilt",
"I am done doubting what I already know about myself",
"I am the reason my life keeps getting better",
"I am becoming unstoppable in every aspect of my life",

"I am choosing myself with love and intention",
"I am trusting that everything happening is happening for me",
"I am open to receiving miracles in unexpected ways",
"I am worthy of a life that feels deep, delicious, and divine",
"I am blooming into someone powerful and grounded",
"I am safe within myself even when life feels chaotic",
"I am becoming the woman who inspires even her future self",
"I am letting the universe work for me, not against me",
"I am learning, unlearning, and evolving with grace",
"I am embracing a mindset that feels like gold",

"I am walking like the world was built for me to experience",
"I am giving myself permission to want more",
"I am becoming the type of woman who intimidates her old fears",
"I am done shrinking myself for anyone",
"I am stepping into my power with full awareness",
"I am worthy of devotion, loyalty, and deep love",
"I am attracting love that worships the ground I walk on",
"I am choosing relationships that honor who I am",
"I am a magnetic force of feminine power",
"I am nurturing my spirit the way I deserve",

"I am not afraid to redesign my life",
"I am choosing abundance every single morning",
"I am remembering who I am even on hard days",
"I am rebuilding myself into someone unbreakable",
"I am attracting experiences that elevate me",
"I am choosing paths that align with my highest identity",
"I am not moved by temporary chaos",
"I am protected by karma and guided by intuition",
"I am worthy of wealth that flows consistently",
"I am shifting into a rich and abundant version of myself",

"I am claiming opportunities without hesitation",
"I am trusting that everything I desire is already on its way",
"I am moving forward with clarity and certainty",
"I am making choices aligned with my future self",
"I am building a life that reflects my worth",
"I am embracing confidence as my natural state",
"I am no longer negotiating with my old identity",
"I am stepping into my destiny fearlessly",
"I am becoming a woman of strong standards and deeper boundaries",
"I am aligned with the energy of massive success",

"I am deserving of a love that feels like obsession and devotion",
"I am attracting a partner who sees me as a universe",
"I am worthy of a relationship that feels like home and fire",
"I am letting myself desire deeply without apology",
"I am choosing loyalty, depth, and passion",
"I am receiving the kind of love people pray for",
"I am becoming someone who attracts worship-level affection",
"I am letting love show up fully for me",
"I am trusting that the right person will choose me loudly",
"I am walking toward the kind of love that mirrors my soul",

"I am attracting stability in every area of my life",
"I am choosing alignment over confusion",
"I am moving with intention at every step",
"I am deserving of a soft and abundant existence",
"I am calling in wealth, luxury, and opportunities",
"I am nurturing habits that empower my future",
"I am expanding into a version of myself that feels limitless",
"I am rewriting my life with clarity and power",
"I am stepping into an identity that commands abundance",
"I am becoming a magnet for everything meant for me",

"I am no longer apologizing for wanting big things",
"I am the creator of a life that feels unbelievable",
"I am attracting luxury because my energy is luxury",
"I am thinking like a queen because I am one",
"I am trusting my intuition like a compass",
"I am deserving of a future that feels cinematic",
"I am aligning with goals that stretch and excite me",
"I am celebrating every version of myself",
"I am choosing discipline wrapped in self-love",
"I am becoming the woman who makes her dreams normal",

"I am a vessel of divine feminine power",
"I am walking in a body guided by spirit and fire",
"I am transforming pain into purpose effortlessly",
"I am letting everything flow toward my highest good",
"I am attracting miracles even in silence",
"I am glowing differently because I’m healing differently",
"I am proud of the woman I’m becoming",
"I am stepping into seasons that honor my heart",
"I am deserving of endings that lead to better beginnings",
"I am trusting the universe more than my fears",

"I am worthy of living in alignment with my truth",
"I am moving with grace even when I feel overwhelmed",
"I am becoming someone who inspires herself",
"I am choosing gratitude as my frequency",
"I am letting abundance rest within me",
"I am the masterpiece and the work in progress",
"I am capable of achieving everything I dream of",
"I am surrounded by energy that supports my rise",
"I am growing in ways I prayed for",
"I am letting myself embody the life I want",

"I am living with intention, clarity, and purpose",
"I am trusting that everything is unfolding perfectly",
"I am learning to love the process, not just the outcome",
"I am releasing everything that does not serve the woman I’m becoming",
"I am holding space for myself with softness",
"I am showing up for my dreams consistently",
"I am listening to the voice within me that knows the way",
"I am claiming the abundance that belongs to me",
"I am allowing myself to evolve without fear",
"I am stepping into the fullness of who I am",

"I am letting my energy lead the way",
"I am worthy of love, wealth, peace, and fulfillment",
"I am embracing each day as a chance to grow",
"I am choosing myself even when it’s difficult",
"I am building a mindset that attracts blessings",
"I am ready for the success my future holds",
"I am glowing with inner power and quiet certainty",
"I am aligned with a higher timeline",
"I am letting myself rise without resistance",
"I am walking toward a life that feels like destiny",

"I am trusting the timing of everything I desire",
"I am deserving of a life that feels effortless",
"I am becoming the woman who attracts everything she envisions",
"I am embracing softness and strength together",
"I am surrendering what harms me",
"I am welcoming what heals me",
"I am taking the steps my future self thanks me for",
"I am breathing abundance into every choice I make",
"I am building a future full of depth, love, and luxury",
"I am ready for more because I was built for more",

"I am releasing fear and embodying my highest self",
"I am done doubting my power",
"I am stepping into my greatness without hesitation",
"I am attracting blessings left and right",
"I am aligned with infinite opportunities",
"I am moving with divine purpose",
"I am letting success feel natural to me",
"I am shifting into a life that honors my worth",
"I am claiming everything that belongs to me",
"I am unstoppable when I choose to be",

"I am rewriting my story with elegance and certainty",
"I am becoming someone impossible to shake",
"I am deserving of a life that feels extraordinary",
"I am allowing myself to receive with open hands",
"I am rooted, powerful, and divinely guided",
"I am done entertaining anything beneath my standards",
"I am attracting the life I always dreamed of",
"I am walking into days filled with clarity and confidence",
"I am choosing the highest version of myself today",
"I am ready for everything the universe has been saving for me",
        "I am living on a frequency where everything rearranges itself for me",
"I am the woman everything works out for, every single time",
"I am constantly operating in divine timing and divine alignment",
"I am the luckiest girl alive because my energy demands it",
"I am the universe’s favorite and my life reflects that truth",
"I am always supported by invisible forces that adore me",
"I am walking on a path that cannot miss me",
"I am attracting miracles because I speak the language of miracles",
"I am tuned into a frequency where blessings chase me",
"I am naturally chosen by opportunities that matter",

"I am becoming stronger, wiser, and sharper with every challenge",
"I am guided into rooms and timelines meant for my victory",
"I am divinely orchestrated in ways I can’t even see yet",
"I am always receiving answers at the perfect moment",
"I am aligned with abundance without forcing anything",
"I am effortlessly stepping into higher versions of myself",
"I am transforming pressure into power",
"I am the kind of woman whose destiny is undeniable",
"I am connected to an inner wisdom that never fails me",
"I am always held, always watched over, always protected",

"I am attracting wealth with a mind that feels royal",
"I am never without options because the universe prioritizes me",
"I am letting money circulate to me with ease and respect",
"I am the frequency of fortune and divine overflow",
"I am energetically wealthy even before the money arrives",
"I am being guided toward luxury, stability, and elevation",
"I am receiving proof of my luck every single day",
"I am allowing abundance to flow through me without resistance",
"I am stepping into financial and spiritual wealth simultaneously",
"I am wealthy because my energy feels like gold",

"I am unshakeably confident in my destiny",
"I am on the vibration where what I want wants me harder",
"I am consistently chosen by opportunities aligned with my greatness",
"I am becoming someone who never questions her worth",
"I am the blueprint for a life that gets better and better",
"I am worthy of sudden upgrades and unexpected blessings",
"I am walking like I already have everything I desire",
"I am connected to the timeline where I always win",
"I am stepping into days where life feels effortless and abundant",
"I am open to receiving everything I once thought was impossible",

"I am becoming too aligned to ever be overlooked",
"I am leaving behind energies that do not match my expansion",
"I am choosing frequency over force, alignment over anxiety",
"I am stepping into my goddess energy fully and unapologetically",
"I am embodying the kind of power that feels calm and inevitable",
"I am moving like someone who knows she is carried",
"I am claiming the gifts the universe has already assigned to me",
"I am becoming the woman everything flows to naturally",
"I am letting my inner divinity guide every decision I make",
"I am protected beyond my understanding",

"I am walking with the confidence of someone who always rises",
"I am choosing the timeline where I am deeply and endlessly lucky",
"I am magnetizing people who treat me with devotion and respect",
"I am attracting love that feels like worship and remembrance",
"I am stepping into relationships that honor my soul",
"I am the kind of woman who inspires obsession-level loyalty",
"I am receiving the kind of love that feels fated and destined",
"I am choosing standards that protect my heart and essence",
"I am trusting that the right person will recognize me immediately",
"I am letting my energy call in the kind of love I deserve",

"I am always in the right place because I move with intuition",
"I am thriving even in moments that once scared me",
"I am becoming a woman who listens to her inner knowing",
"I am reclaiming my power every time I choose peace",
"I am walking with clarity even through chaos",
"I am surrendering the things that are beneath my evolution",
"I am allowing my life to unfold without fear controlling me",
"I am leaning into growth that feels deep and transformative",
"I am trusting myself more than ever before",
"I am evolving at a pace that feels natural and divine",

"I am bowing only to karma because karma keeps me safe",
"I am letting the universe handle anything not meant for me",
"I am releasing all battles that drain my divine energy",
"I am protected from anything that isn't aligned with my soul",
"I am walking with the quiet assurance that I am supported",
"I am knowing that nothing meant for me will ever pass me",
"I am letting my spirit lead the way toward blessings",
"I am aligned with the version of me that always succeeds",
"I am staying rooted in peace even when tested",
"I am trusting that everything is unfolding in perfect order",

"I am remembering my power even when I feel lost",
"I am recalibrating every time I fall out of alignment",
"I am using confusion as a compass for deeper clarity",
"I am moving forward until new information finds me",
"I am honoring the moments where I feel uncertain",
"I am guided even when I cannot feel the guidance",
"I am walking through fog with the confidence of a goddess",
"I am finding direction in the stillest places",
"I am trusting that lostness is temporary and purposeful",
"I am rising into a clearer version of myself after every low",

"I am learning faster than most people ever realize",
"I am absorbing lessons that elevate me instantly",
"I am evolving at a speed that surprises even me",
"I am the kind of woman who levels up in days, not months",
"I am becoming unstoppable because I adapt so quickly",
"I am absorbing wisdom like it’s oxygen",
"I am turning every setback into a tactical advantage",
"I am rising from every challenge with upgraded strength",
"I am always five steps ahead because my intuition is loud",
"I am proud of how fast and fiercely I grow",

"I am living a life where nothing is too expensive or out of reach",
"I am attracting wealth that matches the size of my dreams",
"I am choosing to think like someone who deserves everything",
"I am letting the world respond to my sense of worth",
"I am becoming the woman who walks into luxury naturally",
"I am refusing to limit myself based on current circumstances",
"I am letting my desires be instructions, not fantasies",
"I am treating everything I want as destined, not distant",
"I am choosing a life that feels rich in every way",
"I am letting my standards shape my reality",

"I am becoming someone who feels safe in her own skin",
"I am loving myself with devotion and honesty",
"I am proud of my instincts, morals, and convictions",
"I am honoring myself even on days when it’s hard",
"I am treating my reflection with admiration, not judgment",
"I am falling in love with the woman I am becoming",
"I am letting self-love be my foundation for everything",
"I am choosing habits that honor my future",
"I am celebrating my mind and spirit daily",
"I am becoming someone I would worship if I met her",

"I am attracting a future that feels cinematic and abundant",
"I am aligned with timelines that feel too good to describe",
"I am living in a reality where everything unfolds beautifully for me",
"I am drawing in opportunities that multiply my power",
"I am sitting on a frequency where everything works out perfectly",
"I am deeply connected to the version of me who already made it",
"I am stepping into the billionaire version of my destiny",
"I am learning to trust the future I’m building",
"I am becoming the woman who lives out her wildest dreams",
"I am watching my manifestations arrive faster every day",

"I am walking with feminine power that feels ancient and divine",
"I am embodying the blend of softness and fire that defines me",
"I am choosing to live as the goddess I know I am",
"I am a channel for beauty, power, grace, and magic",
"I am rewriting what femininity feels like for myself",
"I am breathing life into my dreams with every step",
"I am shifting into deeper versions of my own divinity",
"I am aligning with energies that worship my presence",
"I am choosing softness as my strength",
"I am letting my feminine power guide the entire room"
        "I am learning to love myself in deeper ways every single day",
"I am treating myself like someone worth worshipping",
"I am showing up for myself in ways no one else ever has",
"I am choosing to be proud of the woman I look at in the mirror",
"I am loving the parts of me that once felt unlovable",
"I am falling in love with my voice, my power, my essence",
"I am giving myself the devotion I used to expect from others",
"I am becoming my own safest and softest place",
"I am worthy of the kind of love I always dreamed of",
"I am honoring myself like something divine",

"I am loving my flaws because they helped shape my strength",
"I am grateful for the woman I’ve become through hardship",
"I am celebrating my softness because it makes me powerful",
"I am choosing to love myself without conditions",
"I am letting self-love be the foundation of everything I do",
"I am treating my heart with patience, affection, and loyalty",
"I am loving the way I think, the way I feel, the way I grow",
"I am choosing to see myself as someone worth fighting for",
"I am proud of how far I’ve come without giving up",
"I am allowing self-love to guide every decision I make",

"I am the love I used to beg for",
"I am giving myself the attention I once chased",
"I am the place my heart returns to for safety",
"I am choosing myself even when it’s uncomfortable",
"I am falling in love with my resilience and my rebellion",
"I am letting my inner child feel seen and protected",
"I am becoming someone I trust with my whole life",
"I am loving my past selves for surviving long enough to grow",
"I am celebrating my present self for evolving fearlessly",
"I am honoring my future self with every step I take",

"I am letting self-love be my loudest language",
"I am worthy of tenderness from myself",
"I am showing myself the loyalty I once begged others for",
"I am giving my mind the respect it deserves",
"I am learning to love my body in all its seasons",
"I am treating my spirit with reverence",
"I am speaking to myself with kindness, not cruelty",
"I am healing the wounds I used to ignore",
"I am letting love flow inward first",
"I am loving myself in a way that feels like freedom",

"I am embracing the woman I am becoming with open arms",
"I am allowing myself to make mistakes without punishment",
"I am choosing compassion over criticism",
"I am letting my heart rest in its own hands",
"I am loving myself in the quiet moments no one sees",
"I am gifting myself peace whenever I need it",
"I am worthy of taking care of myself intentionally",
"I am allowing myself to be my own greatest love story",
"I am choosing a life where I never abandon myself",
"I am loving myself loudly, proudly, fearlessly",

"I am learning to trust my own love more than external validation",
"I am honoring my sensitivity as something sacred",
"I am choosing to love myself even when I feel imperfect",
"I am releasing shame that never belonged to me",
"I am letting my heart feel safe inside my own presence",
"I am teaching myself how to love better, softer, deeper",
"I am embracing the parts of me I used to hide",
"I am becoming the love I once thought I had to find",
"I am choosing self-respect as my baseline",
"I am building a relationship with myself that feels holy",

"I am worthy of loving myself the way I crave to be loved",
"I am treating my dreams as worthy because I am worthy",
"I am becoming someone I would admire if I met her",
"I am recognizing my beauty in every version of me",
"I am loving the fire inside me that never goes out",
"Iam letting my self-love be louder than my doubts",
"I am worthy of gentleness even on my hardest days",
"I am choosing to show up for myself with full devotion",
"I am remembering that I am a blessing in human form",
"I am loving myself in ways that feel like truth",

"I am letting self-love be the reason I never shrink",
"I am replacing self-judgment with self-honoring",
"I am becoming too in love with myself to settle",
"I am allowing my own affection to heal me",
"Iam speaking to myself with the respect I deserve",
"I am choosing to be kind to myself at every turn",
"I am loving the parts of me that are still learning",
"I am forgiving myself for the moments I didn’t know better",
"I am embracing every version of myself with compassion",
"I am choosing a life where I am my own priority",

"I am the love that stays when everything else leaves",
"I am building a home inside myself",
"I am loving myself fiercely, gently, endlessly",
"I am choosing to rise in ways that honor my worth",
"I am making my self-love impossible to break",
"I am letting my love for myself set the tone for my whole life",
"I am worthy of being chosen by myself first",
"I am choosing self-love as my lifelong commitment",
"I am rooted in love for who I am and who I’m becoming",
"I am celebrating myself because I am a miracle",
"I am loving myself without hesitation, limit, or apology"
    ]
    
    def ensure_minimum_stories(self, articles: List[Dict], minimum: int = 3, maximum: int = 5) -> List[Dict]:
        """Ensure we have 3-5 stories, filtering out recently sent ones."""
        tracker = StorySentTracker()
        sent_urls = tracker.get_sent_urls()
        
        filtered_articles = [a for a in articles if a.get('url') not in sent_urls]
        logger.info(f"Filtered {len(articles)-len(filtered_articles)} recently sent stories, {len(filtered_articles)} new available")
        
        if len(filtered_articles) >= minimum:
            logger.info(f"Sufficient new articles available: {len(filtered_articles)}")
            selected = filtered_articles[:maximum]
            tracker.save_sent_stories(selected)
            return selected
        
        needed = minimum - len(filtered_articles)
        logger.warning(f"Insufficient new articles ({len(filtered_articles)}). Adding {needed} emergency stories.")
        
        import random
        emergency_selection = random.sample(self.EMERGENCY_STORIES, min(needed, len(self.EMERGENCY_STORIES)))
        
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

    fetch_weather_and_aqi(...) returns a structured dict:
      {
        "location": "San Francisco",
        "temp_c": 10.3,
        "humidity": 86,
        "summary": "Weather in San Francisco: 10°C, Humidity: 86%, AQI: Good (1).",
        "aqi": {
           "value": 1,                 # OpenWeatherMap index 1..5
           "desc": "Good",
           "components": { "pm2_5": 3.1, "pm10": 5.0, ... }
        },
        "advice": "Air quality is good..."
      }
    If weather cannot be fetched returns {"summary": "Weather data not available."}
    """

    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
        # Weather config
        self.openweather_key = os.getenv('OPENWEATHER_API_KEY')
        self.weather_city = os.getenv('WEATHER_CITY')
        self.weather_lat = os.getenv('WEATHER_LAT')
        self.weather_lon = os.getenv('WEATHER_LON')
        # Optional device coords
        self.device_lat = os.getenv('DEVICE_LAT')
        self.device_lon = os.getenv('DEVICE_LON')

    def _geocode_city(self, city: str) -> Optional[Tuple[float, float]]:
        if not self.openweather_key or not city:
            logger.debug("Geocode skipped: missing api key or city")
            return None
        url = "https://api.openweathermap.org/geo/1.0/direct"
        candidates = [city.strip()]
        city_lower = city.lower()
        # helpful fallbacks for Bengaluru/Bangalore
        if 'bangalore' in city_lower or 'bengaluru' in city_lower:
            candidates += [f"{city}, IN", "Bengaluru, IN", "Bangalore, IN"]
        else:
            candidates += [f"{city}, IN", f"{city}, India"]
        for c in candidates:
            try:
                resp = requests.get(url, params={'q': c, 'limit': 1, 'appid': self.openweather_key}, timeout=6)
                resp.raise_for_status()
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    lat = data[0].get('lat')
                    lon = data[0].get('lon')
                    logger.debug(f"Geocode '{c}' -> lat={lat}, lon={lon}")
                    if lat is not None and lon is not None:
                        return float(lat), float(lon)
                else:
                    logger.debug(f"Geocode returned empty for '{c}'")
            except Exception as e:
                logger.debug(f"Geocoding attempt for '{c}' failed: {e}")
        return None

    def _resolve_coords(self, lat: Optional[float], lon: Optional[float], city: Optional[str]) -> Optional[Tuple[float, float]]:
        # 1) explicit args
        if lat is not None and lon is not None:
            try:
                return float(lat), float(lon)
            except Exception:
                logger.debug("Invalid explicit lat/lon passed; falling through")
        # 2) device env
        if self.device_lat and self.device_lon:
            try:
                return float(self.device_lat), float(self.device_lon)
            except Exception as e:
                logger.debug(f"DEVICE_LAT/DEVICE_LON parse error: {e}")
        # 3) explicit weather env
        if self.weather_lat and self.weather_lon:
            try:
                return float(self.weather_lat), float(self.weather_lon)
            except Exception as e:
                logger.debug(f"WEATHER_LAT/WEATHER_LON parse error: {e}")
        # 4) geocode
        target_city = (city or self.weather_city or "").strip()
        if target_city:
            coords = self._geocode_city(target_city)
            if coords:
                return coords
            else:
                logger.debug(f"Geocoding failed for city '{target_city}'")
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
        """
        Returns structured weather + AQI dict, or {"summary": "Weather data not available."}
        """
        if not self.openweather_key:
            logger.warning("OPENWEATHER_API_KEY not configured. Skipping weather.")
            return {"summary": "Weather data not available."}

        resolved = self._resolve_coords(lat, lon, city)
        if not resolved:
            logger.info("Weather coordinates not available (after resolution). Skipping weather.")
            return {"summary": "Weather data not available."}
        lat, lon = resolved

        # Fetch current weather
        try:
            weather_url = "https://api.openweathermap.org/data/2.5/weather"
            w_resp = requests.get(weather_url, params={'lat': lat, 'lon': lon, 'appid': self.openweather_key, 'units': 'metric'}, timeout=6)
            w_resp.raise_for_status()
            w = w_resp.json()
            temp = w.get('main', {}).get('temp')
            humidity = w.get('main', {}).get('humidity')
            location_name = city or self.weather_city or "your area"
            logger.debug(f"Weather for {location_name}: temp={temp}, humidity={humidity}")
        except Exception as e:
            logger.debug(f"Error fetching current weather: {e}")
            return {"summary": "Weather data not available."}

        # Fetch AQI (optional)
        aqi_value = None
        components = None
        try:
            aqi_url = "https://api.openweathermap.org/data/2.5/air_pollution"
            a_resp = requests.get(aqi_url, params={'lat': lat, 'lon': lon, 'appid': self.openweather_key}, timeout=6)
            a_resp.raise_for_status()
            a = a_resp.json()
            if a and 'list' in a and len(a['list']) > 0:
                main = a['list'][0].get('main', {})
                aqi_value = main.get('aqi')  # 1..5
                components = a['list'][0].get('components', {})  # pm2_5, pm10, no2, so2 etc
                logger.debug(f"AQI for {location_name}: {aqi_value}, components: {components}")
        except Exception as e:
            logger.debug(f"AQI fetch non-fatal error: {e}")
            aqi_value = None
            components = None

        aqi_desc = self._owm_aqi_desc(aqi_value)
        parts = []
        if temp is not None:
            parts.append(f"{round(temp)}°C")
        if humidity is not None:
            parts.append(f"Humidity: {humidity}%")
        parts.append(f"AQI: {aqi_desc}" + (f" ({aqi_value})" if aqi_value is not None else ""))

        summary = f"Weather in {location_name}: " + ", ".join(parts) + "."

        result = {
            "location": location_name,
            "temp_c": temp,
            "humidity": humidity,
            "summary": summary,
            "aqi": {
                "value": aqi_value,
                "desc": aqi_desc,
                "components": components or {}
            },
            "advice": self._aqi_health_advice(aqi_value)
        }
        return result

    def generate_html_email(self, stories: List[Dict], affirmation: str, greeting: str, weather_info) -> str:
        """
        Accepts weather_info as either a string (old behavior) or a dict (as returned above).
        Renders AQI badge + components + advice when dict is provided.
        """
        today = datetime.now().strftime('%B %d, %Y')

        # Build weather HTML block
               # Build weather HTML block
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

        # Build stories HTML (keeps previous style)
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
        """Send the beautiful email (unchanged behavior)."""
        if not self.smtp_username or not self.smtp_password:
            logger.warning("SMTP credentials not configured. Email not sent.")
            logger.info("Email HTML content would be (preview truncated):")
            logger.info(html_content[:500] + "...")
            try:
                safe_name = to_email.replace('@', '_at_').replace('.', '_')
                with open(f'preview_email_{safe_name}.html', 'w', encoding='utf-8') as f:
                    f.write(html_content)
                logger.info(f"Email preview saved to preview_email_{safe_name}.html")
            except Exception:
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
            logger.info(f"Email sent successfully to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {str(e)}")
            return False

    def deliver_morning_glow(self, recipients: List[str], stories: List[Dict], affirmation: str,
                             owner_email: str = None, recipient_locations: Optional[Dict[str, Dict]] = None) -> Dict[str, bool]:
        """
        Per-recipient weather/AQI: pass recipient_locations mapping (email -> {lat, lon} or {city: "..."}).
        """
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

            # Get structured weather+AQI
            weather_info = self.fetch_weather_and_aqi(lat=lat, lon=lon, city=city)
            html_content = self.generate_html_email(stories, affirmation, greeting, weather_info)
            success = self.send_email(recipient, subject, html_content)
            results[recipient] = success

        return results

class SilentGuardian:
    """
    Handles errors silently to never disturb the user.
    Ensures the ritual is never broken.
    """
    
    @staticmethod
    def safe_execute(func, *args, **kwargs):
        """Execute function with silent error handling."""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Silent error in {func.__name__}: {str(e)}")
            return None
    
    @staticmethod
    def ensure_ritual(func):
        """Decorator to ensure the morning ritual never breaks."""
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
    """
    The complete MorningGlow flow:
    Fetch → Filter → Verify → Summarize → Guarantee → Email
    """
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
        'climate positive environmental win',
        'mental health wellness progress',
        'accessibility technology helping people',
        'ocean conservation marine life',
        'reforestation tree planting initiative',
        'disaster relief community support'
    ]
    
    processor = ContentProcessor()
    processed_articles = processor.process_news(search_queries)
    
    guarantee = ContentGuarantee()
    final_stories = guarantee.ensure_minimum_stories(processed_articles, minimum=3, maximum=5)
    affirmation = guarantee.get_daily_affirmation()
    
    logger.info(f"Final story count: {len(final_stories)}")
    logger.info(f"Daily affirmation: {affirmation}")
    
    email_guardian = MorningEmailGuardian()
    # RECIPIENT_EMAILS can be a comma-separated list
    recipients_env = os.getenv('RECIPIENT_EMAILS') or os.getenv('RECIPIENT_EMAIL') or 'user@example.com'
    recipients = [r.strip() for r in recipients_env.split(',') if r.strip()]
    owner_email = os.getenv('OWNER_EMAIL')  # set this to your own email so you get Goddess greeting
    
    results = email_guardian.deliver_morning_glow(recipients, final_stories, affirmation, owner_email=owner_email)
    
    for r, ok in results.items():
        logger.info(f"Email to {r}: {'sent' if ok else 'previewed/not-sent'}")
    
    logger.info("=" * 60)
    logger.info("Sacred morning ritual complete. Peace and beauty prevail.")
    logger.info("=" * 60)
    
    return final_stories


if __name__ == "__main__":
    sacred_morning_flow_with_accuracy()
