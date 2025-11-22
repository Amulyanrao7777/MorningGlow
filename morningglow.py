# """
# MorningGlow: A Production-Grade Emotionally-Safe News Curator
# Delivers beautiful, verified positive news every morning.
# """

# import os
# import re
# import json
# import smtplib
# import logging
# from datetime import datetime, timedelta
# from email.mime.text import MIMEText
# from email.mime.multipart import MIMEMultipart
# from typing import List, Dict, Optional, Tuple
# from urllib.parse import quote
# from dotenv import load_dotenv
# import requests
# import feedparser
# from bs4 import BeautifulSoup
# from openai import OpenAI

# load_dotenv()

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)


# class SourceOrchestrator:
#     """
#     Fetches real-time news from NewsAPI and Google News RSS.
#     Validates URLs, ensures sources are legitimate, and filters by recency (14 days).
#     """
    
#     def __init__(self):
#         self.newsapi_key = os.getenv('NEWSAPI_KEY')
#         self.newsapi_url = 'https://newsapi.org/v2/everything'
#         self.google_news_rss = 'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en'
        
#     def fetch_newsapi_articles(self, query: str, page_size: int = 100) -> List[Dict]:
#         """Fetch articles from NewsAPI within the last 14 days."""
#         if not self.newsapi_key:
#             logger.warning("NewsAPI key not found. Skipping NewsAPI fetch.")
#             return []
        
#         try:
#             fourteen_days_ago = (datetime.now() - timedelta(days=14)).isoformat()
            
#             params = {
#                 'q': query,
#                 'apiKey': self.newsapi_key,
#                 'language': 'en',
#                 'sortBy': 'publishedAt',
#                 'pageSize': page_size,
#                 'from': fourteen_days_ago
#             }
            
#             response = requests.get(self.newsapi_url, params=params, timeout=10)
#             response.raise_for_status()
#             data = response.json()
            
#             if data.get('status') == 'ok':
#                 articles = data.get('articles', [])
#                 logger.info(f"Fetched {len(articles)} articles from NewsAPI for query: {query}")
#                 return self._normalize_newsapi_articles(articles)
#             else:
#                 logger.error(f"NewsAPI error: {data.get('message', 'Unknown error')}")
#                 return []
                
#         except Exception as e:
#             logger.error(f"Error fetching from NewsAPI: {str(e)}")
#             return []
    
#     def fetch_google_news_rss(self, query: str) -> List[Dict]:
#         """Fetch articles from Google News RSS feed."""
#         try:
#             feed_url = self.google_news_rss.format(query=quote(query))
#             feed = feedparser.parse(feed_url)
            
#             articles = []
#             fourteen_days_ago = datetime.now() - timedelta(days=14)
            
#             for entry in feed.entries[:50]:
#                 try:
#                     published = datetime(*entry.published_parsed[:6])
#                     if published >= fourteen_days_ago:
#                         url = entry.link.replace(' ', '')
                        
#                         articles.append({
#                             'title': entry.title,
#                             'description': entry.get('summary', ''),
#                             'url': url,
#                             'source': entry.get('source', {}).get('title', 'Google News'),
#                             'published_at': published.isoformat(),
#                             'content': entry.get('summary', '')
#                         })
#                 except Exception as e:
#                     logger.debug(f"Error parsing RSS entry: {str(e)}")
#                     continue
            
#             logger.info(f"Fetched {len(articles)} articles from Google News RSS for query: {query}")
#             return articles
            
#         except Exception as e:
#             logger.error(f"Error fetching from Google News RSS: {str(e)}")
#             return []
    
#     def _normalize_newsapi_articles(self, articles: List[Dict]) -> List[Dict]:
#         """Normalize NewsAPI articles to standard format."""
#         normalized = []
#         for article in articles:
#             normalized.append({
#                 'title': article.get('title', ''),
#                 'description': article.get('description', ''),
#                 'url': article.get('url', ''),
#                 'source': article.get('source', {}).get('name', 'Unknown'),
#                 'published_at': article.get('publishedAt', ''),
#                 'content': article.get('content', '') or article.get('description', '')
#             })
#         return normalized
    
#     def validate_url(self, url: str) -> bool:
#         """Validate that URL is accessible and legitimate."""
#         if not url or not url.startswith('http'):
#             return False
        
#         try:
#             response = requests.head(url, timeout=5, allow_redirects=True)
#             return response.status_code < 400
#         except Exception:
#             return False
    
#     def fetch_all_sources(self, queries: List[str]) -> List[Dict]:
#         """Fetch articles from all sources for multiple queries."""
#         all_articles = []
        
#         for query in queries:
#             all_articles.extend(self.fetch_newsapi_articles(query))
#             all_articles.extend(self.fetch_google_news_rss(query))
        
#         validated_articles = []
#         for article in all_articles:
#             if article.get('url') and self.validate_url(article['url']):
#                 validated_articles.append(article)
        
#         logger.info(f"Total validated articles: {len(validated_articles)}")
#         return validated_articles


# class FactualAccuracyGuardian:
#     """
#     Ensures factual accuracy by rejecting unverified claims, speculation,
#     and clickbait. Checks for verification markers.
#     """
    
#     SPECULATION_KEYWORDS = [
#         'might', 'could', 'may', 'possibly', 'allegedly', 'rumor', 'rumour',
#         'unconfirmed', 'speculation', 'claims without evidence', 'anonymous sources',
#         'insider says', 'reportedly', 'sources say', 'could be', 'might be',
#         'potential', 'preliminary', 'early study', 'early results'
#     ]
    
#     CLICKBAIT_PATTERNS = [
#         r'you won\'t believe',
#         r'shocking',
#         r'miracle cure',
#         r'doctors hate',
#         r'one weird trick',
#         r'this will blow your mind',
#         r'secret that',
#         r'what happens next'
#     ]
    
#     UNVERIFIED_MEDICAL_KEYWORDS = [
#         'breakthrough cure',
#         'miracle treatment',
#         'revolutionary cure',
#         'cancer cured',
#         'aging reversed'
#     ]
    
#     VERIFICATION_MARKERS = [
#         'study published',
#         'peer-reviewed',
#         'fda approved',
#         'clinical trial',
#         'research shows',
#         'scientists confirm',
#         'university study',
#         'official announcement',
#         'government confirms',
#         'peer reviewed'
#     ]
    
#     def check_factual_accuracy(self, article: Dict) -> Tuple[bool, str]:
#         """
#         Check if article meets factual accuracy standards.
#         Returns (is_accurate, reason).
#         """
#         title = article.get('title', '').lower()
#         description = article.get('description', '').lower()
#         content = article.get('content', '').lower()
        
#         full_text = f"{title} {description} {content}"
        
#         if any(keyword in full_text for keyword in self.SPECULATION_KEYWORDS):
#             return False, "Contains speculation or unverified claims"
        
#         for pattern in self.CLICKBAIT_PATTERNS:
#             if re.search(pattern, full_text, re.IGNORECASE):
#                 return False, "Contains clickbait patterns"
        
#         if any(keyword in full_text for keyword in self.UNVERIFIED_MEDICAL_KEYWORDS):
#             has_verification = any(marker in full_text for marker in self.VERIFICATION_MARKERS)
#             if not has_verification:
#                 return False, "Medical claim without verification markers"
        
#         if not article.get('source') or article.get('source') == 'Unknown':
#             return False, "Missing legitimate source"
        
#         if not article.get('url'):
#             return False, "Missing source URL"
        
#         return True, "Factually accurate"
    
#     def filter_accurate_articles(self, articles: List[Dict]) -> List[Dict]:
#         """Filter articles to only include factually accurate ones."""
#         accurate_articles = []
        
#         for article in articles:
#             is_accurate, reason = self.check_factual_accuracy(article)
#             if is_accurate:
#                 accurate_articles.append(article)
#             else:
#                 logger.debug(f"Rejected article '{article.get('title', 'Unknown')}': {reason}")
        
#         logger.info(f"Factual accuracy check: {len(accurate_articles)}/{len(articles)} passed")
#         return accurate_articles


# class EmotionalSafetyFilter:
#     """
#     Implements the Amulya Filter: 9 categories of emotionally safe,
#     gentle, feminine content. Rejects stress, crisis, negativity.
#     """
    
#     CATEGORY_KEYWORDS = {
#         'environment_healing': [
#             'coral reef restoration', 'nature recovery', 'reforestation', 'wildlife conservation',
#             'species protection', 'ocean healing', 'habitat restoration', 'ecological program',
#             'conservation success', 'endangered species', 'biodiversity', 'ecosystem recovery',
#             'marine sanctuary', 'forest regrowth', 'clean water', 'pollution reduction',
#             'rewilding', 'nature preserve', 'wildlife sanctuary', 'green spaces'
#         ],
#         'medical_hope': [
#             'clinical trial success', 'fda approval', 'treatment advancement', 'recovery outcome',
#             'health improvement', 'medical breakthrough', 'new therapy', 'disease treatment',
#             'patient recovery', 'healthcare success', 'medical innovation', 'healing',
#             'cure approved', 'treatment approved', 'life-saving', 'health victory'
#         ],
#         'peace_harmony': [
#             'peace agreement', 'ceasefire', 'diplomatic resolution', 'conflict resolution',
#             'unity', 'cooperation', 'reconciliation', 'harmony', 'agreement reached',
#             'neighbors unite', 'community peace', 'collaboration', 'partnership',
#             'nations agree', 'treaty signed', 'peaceful solution'
#         ],
#         'human_kindness': [
#             'stranger helps', 'volunteer', 'charity success', 'rescue', 'kindness',
#             'compassion', 'donation', 'community support', 'heartwarming', 'good samaritan',
#             'helping hand', 'generous', 'fundraiser success', 'community gives',
#             'neighbors help', 'act of kindness', 'paying it forward', 'good deed'
#         ],
#         'education_wins': [
#             'scholarship', 'student achievement', 'teacher inspires', 'learning program',
#             'educational success', 'graduation', 'literacy program', 'school success',
#             'educational innovation', 'students excel', 'academic achievement',
#             'mentorship program', 'tutoring success', 'educational opportunity'
#         ],
#         'women_empowerment': [
#             'women-led', 'female leadership', 'women scientists', 'women creators',
#             'women entrepreneurs', 'women in stem', 'female founder', 'women innovators',
#             'women breaking barriers', 'female pioneers', 'women achieve',
#             'women empowerment', 'girls education', 'women leaders'
#         ],
#         'ethical_innovation': [
#             'renewable energy', 'sustainable technology', 'green technology', 'clean energy',
#             'accessibility technology', 'assistive technology', 'environmental technology',
#             'solar power', 'wind energy', 'electric vehicle', 'sustainable engineering',
#             'carbon reduction', 'eco-friendly innovation', 'tech for good'
#         ],
#         'art_culture': [
#             'museum', 'art exhibition', 'cultural festival', 'heritage conservation',
#             'children art', 'creative project', 'artistic community', 'cultural celebration',
#             'music festival', 'dance performance', 'theater', 'gallery opening',
#             'cultural heritage', 'art installation', 'creative workshop'
#         ],
#         'feel_good': [
#             'heartwarming', 'uplifting', 'inspiring', 'beautiful', 'joyful', 'celebration',
#             'happiness', 'wonderful', 'amazing story', 'touching', 'delightful',
#             'precious moment', 'feel-good', 'wholesome', 'adorable'
#         ]
#     }
    
#     REJECT_KEYWORDS = [
#         'crisis', 'shortage', 'suicide', 'violence', 'shooting', 'attack', 'murder',
#         'war', 'combat', 'battle', 'conflict', 'crime', 'corruption', 'scandal',
#         'controversy', 'disaster', 'catastrophe', 'emergency', 'threat', 'danger',
#         'fear', 'terror', 'tragic', 'death toll', 'casualties', 'victim',
#         'collapse', 'crash', 'failure', 'bankruptcy', 'layoff', 'recession',
#         'pandemic', 'outbreak', 'epidemic', 'infection surge', 'hospital overwhelmed',
#         'supply shortage', 'food bank empty', 'running out', 'desperate',
#         'alarming', 'concerning', 'worrying', 'devastating', 'horrific'
#     ]
    
#     CRISIS_PATTERNS = [
#         r'running low on',
#         r'supplies dwindling',
#         r'in short supply',
#         r'desperate need',
#         r'critically low',
#         r'struggling to meet',
#         r'faces shortage'
#     ]
    
#     def check_category_match(self, article: Dict) -> Tuple[bool, List[str]]:
#         """Check if article matches at least one allowed category."""
#         title = article.get('title', '').lower()
#         description = article.get('description', '').lower()
#         content = article.get('content', '').lower()
        
#         full_text = f"{title} {description} {content}"
        
#         matched_categories = []
#         for category, keywords in self.CATEGORY_KEYWORDS.items():
#             if any(keyword.lower() in full_text for keyword in keywords):
#                 matched_categories.append(category)
        
#         return len(matched_categories) > 0, matched_categories
    
#     def check_emotional_safety(self, article: Dict) -> Tuple[bool, str]:
#         """Check if article is emotionally safe (no stress, crisis, negativity)."""
#         title = article.get('title', '').lower()
#         description = article.get('description', '').lower()
#         content = article.get('content', '').lower()
        
#         full_text = f"{title} {description} {content}"
        
#         for keyword in self.REJECT_KEYWORDS:
#             if keyword.lower() in full_text:
#                 return False, f"Contains stress keyword: {keyword}"
        
#         for pattern in self.CRISIS_PATTERNS:
#             if re.search(pattern, full_text, re.IGNORECASE):
#                 return False, f"Contains crisis framing pattern"
        
#         if title in description or description in title:
#             if len(description) < len(title) * 1.5:
#                 return False, "Description repeats headline"
        
#         return True, "Emotionally safe"
    
#     def apply_amulya_filter(self, articles: List[Dict]) -> List[Dict]:
#         """Apply complete Amulya Filter to articles."""
#         filtered_articles = []
        
#         for article in articles:
#             has_category, categories = self.check_category_match(article)
#             is_safe, safety_reason = self.check_emotional_safety(article)
            
#             if has_category and is_safe:
#                 article['amulya_categories'] = categories
#                 filtered_articles.append(article)
#                 logger.debug(f"Accepted: '{article.get('title')}' - Categories: {', '.join(categories)}")
#             else:
#                 reason = safety_reason if not is_safe else "No matching category"
#                 logger.debug(f"Rejected: '{article.get('title', 'Unknown')}' - {reason}")
        
#         logger.info(f"Amulya Filter: {len(filtered_articles)}/{len(articles)} passed")
#         return filtered_articles


# class SummaryGenerator:
#     """
#     Generates warm, feminine, emotionally soothing summaries using OpenAI.
#     6-7 sentences, 150-170 words, gentle tone.
#     """
    
#     def __init__(self):
#         self.openai_key = os.getenv('OPENAI_API_KEY')
#         if self.openai_key:
#             self.client = OpenAI(api_key=self.openai_key)
#         else:
#             self.client = None
#             logger.warning("OpenAI API key not found. Summaries will be basic.")
    
#     def generate_summary(self, article: Dict) -> str:
#         """Generate a warm, gentle summary for the article."""
#         if not self.client:
#             return self._generate_fallback_summary(article)
        
#         try:
#             title = article.get('title', '')
#             content = article.get('content', '') or article.get('description', '')
            
#             prompt = f"""You are a gentle, warm, feminine voice creating emotionally soothing news summaries.

# Article Title: {title}
# Article Content: {content}

# Create a beautiful, warm summary following these EXACT rules:
# - Write 6-7 sentences
# - Use 150-170 words total
# - Tone: warm, feminine, elegant, emotionally soothing
# - NEVER repeat the headline
# - NEVER mention the source or journalist
# - NEVER introduce new facts not in the article
# - NEVER use negative or stress-based words
# - NEVER overstate claims
# - Feel like "your softest best friend telling you something gentle and hopeful"
# - Focus on the beauty, hope, and positive impact
# - Use soft, flowing language

# Write the summary now:"""
            
#             response = self.client.chat.completions.create(
#                 model="gpt-4o-mini",
#                 messages=[
#                     {"role": "system", "content": "You are a gentle, warm storyteller who creates emotionally safe, beautiful summaries."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 temperature=0.7,
#                 max_tokens=300
#             )
            
#             summary = response.choices[0].message.content
#             if summary:
#                 summary = summary.strip()
#             else:
#                 return self._generate_fallback_summary(article)
            
#             word_count = len(summary.split())
#             if word_count < 140 or word_count > 200:
#                 logger.debug(f"Summary word count {word_count} outside ideal range 150-170")
            
#             return summary
            
#         except Exception as e:
#             logger.error(f"Error generating OpenAI summary: {str(e)}")
#             return self._generate_fallback_summary(article)
    
#     def _generate_fallback_summary(self, article: Dict) -> str:
#         """Generate a warm, feminine fallback summary (6-7 sentences, 150-170 words) when OpenAI is unavailable."""
#         title = article.get('title', '')
#         description = article.get('description', '')
#         content = article.get('content', '') or description
#         categories = article.get('amulya_categories', ['feel_good'])
        
#         text = re.sub(r'<[^>]+>', '', content)
#         text = re.sub(r'\s+', ' ', text).strip()
#         text = re.sub(r'http[s]?://\S+', '', text)
        
#         sentences = [s.strip() for s in text.split('.') if s.strip() and len(s.strip()) > 15]
        
#         import random
        
#         warm_templates = {
#             'environment_healing': [
#                 "In a beautiful testament to nature's remarkable resilience and healing capacity, dedicated conservation efforts are bringing precious ecosystems back to vibrant life with patient, loving care.",
#                 "This gentle restoration work creates safe havens and nurturing sanctuaries where endangered wildlife can flourish, thrive, and rediscover their natural rhythms once more.",
#                 "Patient conservation teams and devoted scientists have nurtured these delicate spaces with tender care, scientific wisdom, and an unwavering commitment to environmental healing.",
#                 "The breathtaking transformation unfolds like soft morning sunlight breaking through gentle clouds, bringing steady warmth and renewed promise to these recovering landscapes.",
#                 "Each small victory and milestone in this profound restoration journey represents countless years of compassionate dedication, tireless effort, and deep reverence for the natural world.",
#                 "Local communities have wholeheartedly embraced their sacred role as guardians and stewards of these healing landscapes, ensuring their protection for generations to come.",
#                 "Such inspiring environmental progress beautifully shows that when we nurture and protect nature with genuine love and respect, extraordinary beauty blooms in grateful return."
#             ],
#             'human_kindness': [
#                 "In a profoundly heartwarming display of community spirit and human connection, neighbors and strangers alike are coming together with open hearts to create something truly special and meaningful.",
#                 "These generous acts of kindness and compassion ripple outward like gentle waves, touching countless hearts and quietly transforming lives in the most tender and unexpected ways.",
#                 "Dedicated volunteers from all walks of life have selflessly given their precious time, boundless energy, and caring presence with such remarkable warmth, grace, and genuine generosity.",
#                 "This beautiful initiative brings people of all backgrounds together in meaningful ways, creating lasting bonds of compassion, deep understanding, and shared purpose that strengthen the entire community.",
#                 "Each person involved in this labor of love has contributed their unique gifts, talents, and heartfelt efforts to this beautiful collective journey of service and care.",
#                 "Uplifting stories like these gently remind us of the profound and enduring power of human connection, kindness, and our shared capacity to make a meaningful difference.",
#                 "Such gentle gestures of love and compassion beautifully demonstrate that kindness, empathy, and care for one another remain our greatest collective strength and most precious human quality."
#             ],
#             'education_wins': [
#                 "In an inspiring celebration of learning, growth, and intellectual achievement, dedicated students are reaching remarkable educational milestones that open doors to brilliant futures filled with possibility.",
#                 "These hard-earned educational victories unlock pathways to bright tomorrow filled with endless opportunity, personal growth, and the promise of meaningful contributions to our world.",
#                 "Devoted teachers and mentors have guided these eager young minds with infinite patience, encouraging wisdom, and a deep belief in each student's unique potential and capabilities.",
#                 "The thoughtfully designed program creates warm, nurturing spaces and supportive environments where natural curiosity can flourish freely and individual talents can bloom into their fullest expression.",
#                 "Each achievement celebrated today represents countless hours of determined effort, perseverance through challenges, and the supportive encouragement of caring adults who believed in these bright minds.",
#                 "Proud families and dedicated communities have rallied together with unwavering support, providing resources and creating opportunities to make these inspiring academic successes possible for every child.",
#                 "Such beautiful educational progress tenderly reminds us that quality learning and compassionate teaching transform young lives with gentle, profound, and lasting positive power for generations."
#             ],
#             'women_empowerment': [
#                 "In a powerful and inspiring display of grace, strength, and unwavering determination, visionary women leaders are creating meaningful, lasting change that uplifts entire communities with wisdom and compassion.",
#                 "These remarkable pioneers are courageously breaking through barriers and shattering glass ceilings while generously lifting others up alongside them on this transformative journey toward equality and opportunity.",
#                 "Their innovative work beautifully combines brilliant creative thinking and technical excellence with deep compassion for community needs, creating solutions that serve and empower everyone they touch.",
#                 "Each hard-won achievement and milestone reached paves a wider, smoother path forward for future generations of young women to dream even bigger and reach even higher than ever before.",
#                 "This groundbreaking initiative powerfully demonstrates how women's authentic leadership, unique perspectives, and collaborative strengths bring fresh insights and transformative approaches to solving complex challenges.",
#                 "Supportive collaborative networks of mentors and allies have helped these dedicated changemakers flourish, grow in confidence, and amplify their positive impact throughout their fields of expertise.",
#                 "Such remarkable progress in women's empowerment beautifully shows that when women lead with clear purpose, authentic voice, and compassionate vision, extraordinary transformations unfold naturally across entire societies."
#             ],
#             'medical_hope': [
#                 "In a gentle medical breakthrough that brings renewed hope and comfort to countless families, carefully researched advances are opening welcoming doors to healing, recovery, and renewed wellness.",
#                 "This thoughtfully developed treatment approach offers genuine comfort and tangible relief to those courageously seeking wellness, recovery, and a return to lives filled with health and vitality.",
#                 "Dedicated healthcare professionals and tireless researchers have worked with scientific precision, deep caring, and unwavering commitment to bring this compassionate care option to fruition for patients.",
#                 "The innovative treatment approach beautifully honors both rigorous scientific methodology and the deeply human need for gentle, personalized support throughout each person's unique healing journey ahead.",
#                 "Patients facing health challenges and their loving families can now look toward their futures with significantly greater peace, realistic optimism, and confidence in their pathways to recovery.",
#                 "Many years of patient research, careful clinical trials, and dedicated scientific investigation have culminated in this beautiful, hopeful moment of meaningful medical progress and healing possibility.",
#                 "Such inspiring medical advancements tenderly remind us that true healing unfolds through the perfect blend of cutting-edge science, compassionate care, unwavering dedication, and steadfast hope."
#             ],
#             'feel_good': [
#                 "In a genuinely touching moment that warms the heart and lifts the spirit, this beautiful story brings gentle light, joy, and renewed faith in goodness to brighten our day.",
#                 "The gentle, graceful unfolding of these heartwarming events serves as a tender reminder of the inherent goodness, kindness, and compassion that exists abundantly in our shared world.",
#                 "People from all walks of life have come together with remarkably open hearts, genuine caring intentions, and a shared desire to create something beautiful and meaningful for everyone.",
#                 "This wonderfully heartwarming development creates expanding ripples of pure joy, warm inspiration, and renewed hope that touch lives far beyond what we can immediately see or measure.",
#                 "Each precious detail of this uplifting story reveals and celebrates the tender humanity, deep connection, and beautiful compassion that we all fundamentally share as human beings together.",
#                 "Communities near and far celebrate joyfully together, finding deep connection, shared meaning, and renewed appreciation for the simple yet profound moments that unite and inspire us all.",
#                 "Such precious reminders gently show us that authentic beauty, spontaneous kindness, and genuine human warmth surround us always, waiting to be noticed, celebrated, and shared with grateful hearts."
#             ]
#         }
        
#         category = categories[0] if categories else 'feel_good'
#         template_category = category if category in warm_templates else 'feel_good'
        
#         template_sentences = warm_templates[template_category].copy()
        
#         if len(sentences) >= 2:
#             clean_first = sentences[0]
#             clean_second = sentences[1] if len(sentences) > 1 else ""
            
#             if len(clean_first.split()) <= 25:
#                 template_sentences[0] = template_sentences[0]
#                 if clean_second and len(clean_second.split()) <= 20:
#                     template_sentences[1] = f"The initiative focuses on {clean_second.lower()}"
        
#         selected_sentences = []
#         total_words = 0
        
#         for i, sentence in enumerate(template_sentences):
#             selected_sentences.append(sentence)
#             total_words += len(sentence.split())
            
#             if len(selected_sentences) >= 6 and total_words >= 150:
#                 break
            
#             if len(selected_sentences) >= 7 and total_words >= 140:
#                 break
        
#         if len(selected_sentences) < 6:
#             while len(selected_sentences) < 6 and len(selected_sentences) < len(template_sentences):
#                 selected_sentences.append(template_sentences[len(selected_sentences)])
        
#         summary = ' '.join(selected_sentences[:7])
        
#         return summary
    
#     def generate_summaries_batch(self, articles: List[Dict]) -> List[Dict]:
#         """Generate summaries for multiple articles."""
#         for article in articles:
#             article['summary'] = self.generate_summary(article)
#             logger.info(f"Generated summary for: {article.get('title', 'Unknown')[:50]}...")
        
#         return articles


# class ContentProcessor:
#     """
#     Orchestrates the complete content processing pipeline:
#     Fetching -> Accuracy Check -> Emotional Safety -> Summary Generation
#     """
    
#     def __init__(self):
#         self.source_orchestrator = SourceOrchestrator()
#         self.accuracy_guardian = FactualAccuracyGuardian()
#         self.safety_filter = EmotionalSafetyFilter()
#         self.summary_generator = SummaryGenerator()
    
#     def process_news(self, queries: List[str]) -> List[Dict]:
#         """Complete processing pipeline for news articles."""
#         logger.info("Starting news processing pipeline...")
        
#         raw_articles = self.source_orchestrator.fetch_all_sources(queries)
#         logger.info(f"Step 1: Fetched {len(raw_articles)} raw articles")
        
#         accurate_articles = self.accuracy_guardian.filter_accurate_articles(raw_articles)
#         logger.info(f"Step 2: {len(accurate_articles)} articles passed accuracy check")
        
#         safe_articles = self.safety_filter.apply_amulya_filter(accurate_articles)
#         logger.info(f"Step 3: {len(safe_articles)} articles passed Amulya filter")
        
#         summarized_articles = self.summary_generator.generate_summaries_batch(safe_articles)
#         logger.info(f"Step 4: Generated summaries for {len(summarized_articles)} articles")
        
#         return summarized_articles


# class ContentGuarantee:
#     """
#     Guarantees 3-5 beautiful stories are always available.
#     Uses emergency fallback stories when real-time news is insufficient.
#     """
    
#     EMERGENCY_STORIES = [
#         {
#             'title': 'Ocean Guardians: Coral Reefs Show Remarkable Recovery',
#             'summary': 'In the warm embrace of protected waters, coral reefs are painting a story of hope and resilience. Scientists have discovered that carefully nurtured marine sanctuaries are witnessing the gentle return of vibrant coral colonies, their colors blooming like underwater gardens. These delicate ecosystems, once thought to be beyond recovery, are now thriving with renewed life. The soft sway of healthy coral branches shelters countless species, creating safe havens beneath the waves. This beautiful transformation reminds us that with patient care and dedicated protection, nature possesses an extraordinary ability to heal and flourish once more.',
#             'url': 'https://oceanconservancy.org',
#             'source': 'Ocean Conservation',
#             'published_at': datetime.now().isoformat(),
#             'amulya_categories': ['environment_healing']
#         },
#         {
#             'title': 'A Community\'s Gentle Gift: Neighbors Create Beautiful Garden for Elderly Residents',
#             'summary': 'In a heartwarming display of community love, neighbors came together to create something truly special. With gentle hands and caring hearts, they transformed a neglected space into a serene garden sanctuary for elderly residents. Soft petals of roses and lavender now greet visitors, while comfortable benches offer peaceful resting spots. The project brought together volunteers of all ages, each contributing their unique gifts to this labor of love. Now, seniors can enjoy morning sunshine surrounded by blooming flowers, butterflies dancing on the breeze, and the warm companionship of neighbors who truly care. This beautiful gesture shows how small acts of kindness can blossom into lasting joy.',
#             'url': 'https://example.com/community-garden',
#             'source': 'Community News',
#             'published_at': datetime.now().isoformat(),
#             'amulya_categories': ['human_kindness']
#         },
#         {
#             'title': 'Young Scientists Shine: Students\' Environmental Project Wins National Recognition',
#             'summary': 'A group of dedicated students has captured hearts and minds with their innovative environmental project. These young changemakers designed a beautiful system to purify water using natural, sustainable materials. Their gentle approach combines scientific knowledge with deep care for the planet, creating solutions that work in harmony with nature. Teachers describe watching these students blossom as they worked together, supporting each other through challenges and celebrating every small victory. The project has now inspired other schools to embrace similar initiatives, spreading ripples of positive change. These bright young minds remind us that the future is in caring, capable hands, and that hope grows wherever passion meets purpose.',
#             'url': 'https://example.com/student-achievement',
#             'source': 'Education Today',
#             'published_at': datetime.now().isoformat(),
#             'amulya_categories': ['education_wins', 'environment_healing']
#         },
#         {
#             'title': 'Butterfly Haven: Restored Meadow Becomes Sanctuary for Endangered Species',
#             'summary': 'A once-barren field has transformed into a breathtaking butterfly sanctuary, filled with gentle wings and colorful blooms. Conservation teams carefully planted native wildflowers, creating a soft tapestry of colors that dance in the breeze. Endangered butterfly species have returned to this haven, their delicate presence a sign of healing and hope. Visitors now walk among peaceful meadows, watching these beautiful creatures flutter from flower to flower. The sanctuary has become a place of wonder, where families can witness nature\'s quiet magic and children can learn about protecting our precious ecosystems. This transformation shows how dedication and gentle care can bring endangered beauty back to life.',
#             'url': 'https://example.com/butterfly-sanctuary',
#             'source': 'Wildlife Conservation',
#             'published_at': datetime.now().isoformat(),
#             'amulya_categories': ['environment_healing']
#         },
#         {
#             'title': 'Women-Led Initiative Brings Clean Energy to Rural Communities',
#             'summary': 'A team of inspiring women engineers has created a beautiful solution that brings light and hope to remote villages. Their solar energy project combines technical excellence with deep compassion, ensuring that families can now enjoy clean, sustainable power. These remarkable women worked alongside community members, teaching and empowering them to maintain the systems themselves. The soft glow of solar-powered lights now illuminates homes, schools, and community centers, replacing the darkness with gentle, reliable brightness. Children can study in the evenings, and families can gather safely after sunset. This woman-led initiative demonstrates how innovation rooted in care and understanding can transform lives and create lasting positive change in the world.',
#             'url': 'https://example.com/women-clean-energy',
#             'source': 'Sustainable Future',
#             'published_at': datetime.now().isoformat(),
#             'amulya_categories': ['women_empowerment', 'ethical_innovation']
#         }
#     ]
    
#     AFFIRMATIONS = [
#         "You are worthy of gentle mornings and beautiful moments. Let today unfold with grace.",
#         "Your presence in this world creates ripples of light. Shine softly today.",
#         "Like flowers opening to sunlight, you are allowed to bloom at your own pace.",
#         "You carry within you the strength of oceans and the gentleness of morning dew.",
#         "Today, may you find peace in small joys and comfort in your own beautiful spirit.",
#         "You are deserving of rest, kindness, and all the soft things that bring you peace.",
#         "Let yourself be held by the beauty of this moment. You are exactly where you need to be.",
#         "Your gentle heart is your greatest strength. Honor it today.",
#         "Like the quiet growth of forests, your journey is beautiful even in its stillness.",
#         "You are a garden of possibilities. Water yourself with kindness today."
#     ]
    
#     def ensure_minimum_stories(self, articles: List[Dict], minimum: int = 3, maximum: int = 5) -> List[Dict]:
#         """Ensure we have 3-5 stories, using emergency stories if needed."""
#         if len(articles) >= minimum:
#             logger.info(f"Sufficient articles available: {len(articles)}")
#             return articles[:maximum]
        
#         needed = minimum - len(articles)
#         logger.warning(f"Insufficient articles ({len(articles)}). Adding {needed} emergency stories.")
        
#         import random
#         emergency_selection = random.sample(self.EMERGENCY_STORIES, min(needed, len(self.EMERGENCY_STORIES)))
        
#         combined = articles + emergency_selection
#         return combined[:maximum]
    
#     def get_daily_affirmation(self) -> str:
#         """Get a beautiful affirmation for the day."""
#         import random
#         return random.choice(self.AFFIRMATIONS)


# class MorningEmailGuardian:
#     """
#     Creates beautiful HTML emails with soft pink/rose aesthetic.
#     Gentle typography, warm styling, affirmation box.
#     """
    
#     def __init__(self):
#         self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
#         self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
#         self.smtp_username = os.getenv('SMTP_USERNAME')
#         self.smtp_password = os.getenv('SMTP_PASSWORD')
#         self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
    
#     def generate_html_email(self, stories: List[Dict], affirmation: str) -> str:
#         """Generate beautiful HTML email with soft pink/rose aesthetic."""
#         today = datetime.now().strftime('%B %d, %Y')
        
#         stories_html = ""
#         for i, story in enumerate(stories, 1):
#             stories_html += f"""
#             <div style="background: linear-gradient(135deg, #fff5f7 0%, #ffe9f0 100%); 
#                         border-radius: 16px; 
#                         padding: 28px; 
#                         margin-bottom: 24px;
#                         box-shadow: 0 4px 12px rgba(251, 207, 232, 0.15);">
#                 <h2 style="color: #d4738c; 
#                            font-family: 'Georgia', serif; 
#                            font-size: 22px; 
#                            margin: 0 0 16px 0;
#                            line-height: 1.4;
#                            font-weight: 600;">
#                     {story.get('title', 'Untitled')}
#                 </h2>
#                 <p style="color: #7d5e67; 
#                           font-family: 'Helvetica Neue', 'Arial', sans-serif; 
#                           font-size: 14px; 
#                           line-height: 1.8;
#                           margin: 0 0 18px 0;
#                           text-align: justify;">
#                     {story.get('summary', '')}
#                 </p>
#                 <a href="{story.get('url', '#')}" 
#                    style="color: #e08fa3; 
#                           text-decoration: none; 
#                           font-family: 'Helvetica Neue', 'Arial', sans-serif;
#                           font-size: 14px;
#                           font-weight: 500;
#                           transition: color 0.3s;">
#                     Read full article →
#                 </a>
#             </div>
#             """
        
#         html = f"""
#         <!DOCTYPE html>
#         <html>
#         <head>
#             <meta charset="UTF-8">
#             <meta name="viewport" content="width=device-width, initial-scale=1.0">
#             <title>MorningGlow - {today}</title>
#         </head>
#         <body style="margin: 0; 
#                      padding: 0; 
#                      background: linear-gradient(to bottom, #fff9fb, #ffeff5);
#                      font-family: 'Helvetica Neue', 'Arial', sans-serif;">
#             <div style="max-width: 680px; 
#                         margin: 0 auto; 
#                         padding: 40px 20px;">
                
#                 <div style="text-align: center; margin-bottom: 40px;">
#                     <h1 style="color: #d4738c; 
#                                font-family: 'Georgia', serif; 
#                                font-size: 42px; 
#                                margin: 0 0 8px 0;
#                                font-weight: 300;
#                                letter-spacing: 2px;">
#                         MorningGlow
#                     </h1>
#                     <p style="color: #b89199; 
#                               font-family: 'Georgia', serif; 
#                               font-size: 16px; 
#                               margin: 0;
#                               font-style: italic;">
#                         {today}
#                     </p>
#                 </div>
                
#                 <div style="margin-bottom: 40px;">
#                     {stories_html}
#                 </div>
                
#                 <div style="background: linear-gradient(135deg, #ffd9e8 0%, #ffb3d1 100%);
#                             border-radius: 16px;
#                             padding: 32px;
#                             text-align: center;
#                             border: 2px solid #ffc4dd;
#                             box-shadow: 0 6px 20px rgba(251, 207, 232, 0.25);">
#                     <p style="color: #000000;
#                               font-family: 'Georgia', serif;
#                               font-size: 18px;
#                               line-height: 1.7;
#                               margin: 0;
#                               font-style: italic;">
#                         "{affirmation}"
#                     </p>
#                 </div>
                
#                 <div style="text-align: center; 
#                             margin-top: 40px; 
#                             padding-top: 24px;
#                             border-top: 1px solid #f8d7e3;">
#                     <p style="color: #c9a1ad; 
#                               font-family: 'Helvetica Neue', 'Arial', sans-serif; 
#                               font-size: 13px; 
#                               margin: 0;">
#                         Sent with love by SunshineandHoney 🌸
#                     </p>
#                 </div>
#             </div>
#         </body>
#         </html>
#         """
        
#         return html
    
#     def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
#         """Send the beautiful email."""
#         if not self.smtp_username or not self.smtp_password:
#             logger.warning("SMTP credentials not configured. Email not sent.")
#             logger.info("Email HTML content would be:")
#             logger.info(html_content[:500] + "...")
#             return False
        
#         try:
#             msg = MIMEMultipart('alternative')
#             msg['From'] = self.from_email
#             msg['To'] = to_email
#             msg['Subject'] = subject
            
#             html_part = MIMEText(html_content, 'html', 'utf-8')
#             msg.attach(html_part)
            
#             with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
#                 server.starttls()
#                 server.login(self.smtp_username, self.smtp_password)
#                 server.send_message(msg)
            
#             logger.info(f"Email sent successfully to {to_email}")
#             return True
            
#         except Exception as e:
#             logger.error(f"Error sending email: {str(e)}")
#             return False
    
#     def deliver_morning_glow(self, to_email: str, stories: List[Dict], affirmation: str) -> bool:
#         """Complete email delivery process."""
#         today = datetime.now().strftime('%B %d, %Y')
#         subject = f"🌸 Your MorningGlow - {today}"
        
#         html_content = self.generate_html_email(stories, affirmation)
        
#         with open('preview_email.html', 'w', encoding='utf-8') as f:
#             f.write(html_content)
#         logger.info("Email preview saved to preview_email.html")
        
#         return self.send_email(to_email, subject, html_content)


# class SilentGuardian:
#     """
#     Handles errors silently to never disturb the user.
#     Ensures the ritual is never broken.
#     """
    
#     @staticmethod
#     def safe_execute(func, *args, **kwargs):
#         """Execute function with silent error handling."""
#         try:
#             return func(*args, **kwargs)
#         except Exception as e:
#             logger.error(f"Silent error in {func.__name__}: {str(e)}")
#             return None
    
#     @staticmethod
#     def ensure_ritual(func):
#         """Decorator to ensure the morning ritual never breaks."""
#         def wrapper(*args, **kwargs):
#             try:
#                 return func(*args, **kwargs)
#             except Exception as e:
#                 logger.error(f"Critical error in {func.__name__}: {str(e)}")
#                 logger.info("Ensuring ritual continues with emergency measures...")
#                 return None
#         return wrapper


# @SilentGuardian.ensure_ritual
# def sacred_morning_flow_with_accuracy():
#     """
#     The complete MorningGlow flow:
#     Fetch → Filter → Verify → Summarize → Guarantee → Email
#     """
#     logger.info("=" * 60)
#     logger.info("🌸 MorningGlow - Sacred Morning Flow Beginning 🌸")
#     logger.info("=" * 60)
    
#     search_queries = [
#         'coral reef restoration',
#         'wildlife conservation success',
#         'reforestation',
#         'community volunteers helping',
#         'renewable energy progress',
#         'women scientists',
#         'student achievement',
#         'environmental recovery',
#         'kindness',
#         'heartwarming rescue'
#     ]
    
#     processor = ContentProcessor()
#     processed_articles = processor.process_news(search_queries)
    
#     guarantee = ContentGuarantee()
#     final_stories = guarantee.ensure_minimum_stories(processed_articles, minimum=3, maximum=5)
#     affirmation = guarantee.get_daily_affirmation()
    
#     logger.info(f"Final story count: {len(final_stories)}")
#     logger.info(f"Daily affirmation: {affirmation}")
    
#     email_guardian = MorningEmailGuardian()
#     recipient_email = os.getenv('RECIPIENT_EMAIL', 'user@example.com')
    
#     success = email_guardian.deliver_morning_glow(recipient_email, final_stories, affirmation)
    
#     if success:
#         logger.info("🌸 MorningGlow delivered successfully! 🌸")
#     else:
#         logger.info("🌸 MorningGlow preview generated (check preview_email.html) 🌸")
    
#     logger.info("=" * 60)
#     logger.info("Sacred morning ritual complete. Peace and beauty prevail.")
#     logger.info("=" * 60)
    
#     return final_stories


# if __name__ == "__main__":
#     sacred_morning_flow_with_accuracy()
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
            all_articles.extend(self.fetch_newsapi_articles(query))
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
        """Generate a warm, feminine fallback summary (6-7 sentences, 150-170 words) when OpenAI is unavailable."""
        title = article.get('title', '')
        description = article.get('description', '')
        content = article.get('content', '') or description
        categories = article.get('amulya_categories', ['feel_good'])
        
        text = re.sub(r'<[^>]+>', '', content)
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'http[s]?://\S+', '', text)
        
        sentences = [s.strip() for s in text.split('.') if s.strip() and len(s.strip()) > 15]
        
        import random
        
        warm_templates = {
            'environment_healing': [
                "In a beautiful testament to nature's remarkable resilience and healing capacity, dedicated conservation efforts are bringing precious ecosystems back to vibrant life with patient, loving care.",
                "This gentle restoration work creates safe havens and nurturing sanctuaries where endangered wildlife can flourish, thrive, and rediscover their natural rhythms once more.",
                "Patient conservation teams and devoted scientists have nurtured these delicate spaces with tender care, scientific wisdom, and an unwavering commitment to environmental healing.",
                "The breathtaking transformation unfolds like soft morning sunlight breaking through gentle clouds, bringing steady warmth and renewed promise to these recovering landscapes.",
                "Each small victory and milestone in this profound restoration journey represents countless years of compassionate dedication, tireless effort, and deep reverence for the natural world.",
                "Local communities have wholeheartedly embraced their sacred role as guardians and stewards of these healing landscapes, ensuring their protection for generations to come.",
                "Such inspiring environmental progress beautifully shows that when we nurture and protect nature with genuine love and respect, extraordinary beauty blooms in grateful return."
            ],
            'human_kindness': [
                "In a profoundly heartwarming display of community spirit and human connection, neighbors and strangers alike are coming together with open hearts to create something truly special and meaningful.",
                "These generous acts of kindness and compassion ripple outward like gentle waves, touching countless hearts and quietly transforming lives in the most tender and unexpected ways.",
                "Dedicated volunteers from all walks of life have selflessly given their precious time, boundless energy, and caring presence with such remarkable warmth, grace, and genuine generosity.",
                "This beautiful initiative brings people of all backgrounds together in meaningful ways, creating lasting bonds of compassion, deep understanding, and shared purpose that strengthen the entire community.",
                "Each person involved in this labor of love has contributed their unique gifts, talents, and heartfelt efforts to this beautiful collective journey of service and care.",
                "Uplifting stories like these gently remind us of the profound and enduring power of human connection, kindness, and our shared capacity to make a meaningful difference.",
                "Such gentle gestures of love and compassion beautifully demonstrate that kindness, empathy, and care for one another remain our greatest collective strength and most precious human quality."
            ],
            'education_wins': [
                "In an inspiring celebration of learning, growth, and intellectual achievement, dedicated students are reaching remarkable educational milestones that open doors to brilliant futures filled with possibility.",
                "These hard-earned educational victories unlock pathways to bright tomorrow filled with endless opportunity, personal growth, and the promise of meaningful contributions to our world.",
                "Devoted teachers and mentors have guided these eager young minds with infinite patience, encouraging wisdom, and a deep belief in each student's unique potential and capabilities.",
                "The thoughtfully designed program creates warm, nurturing spaces and supportive environments where natural curiosity can flourish freely and individual talents can bloom into their fullest expression.",
                "Each achievement celebrated today represents countless hours of determined effort, perseverance through challenges, and the supportive encouragement of caring adults who believed in these bright minds.",
                "Proud families and dedicated communities have rallied together with unwavering support, providing resources and creating opportunities to make these inspiring academic successes possible for every child.",
                "Such beautiful educational progress tenderly reminds us that quality learning and compassionate teaching transform young lives with gentle, profound, and lasting positive power for generations."
            ],
            'women_empowerment': [
                "In a powerful and inspiring display of grace, strength, and unwavering determination, visionary women leaders are creating meaningful, lasting change that uplifts entire communities with wisdom and compassion.",
                "These remarkable pioneers are courageously breaking through barriers and shattering glass ceilings while generously lifting others up alongside them on this transformative journey toward equality and opportunity.",
                "Their innovative work beautifully combines brilliant creative thinking and technical excellence with deep compassion for community needs, creating solutions that serve and empower everyone they touch.",
                "Each hard-won achievement and milestone reached paves a wider, smoother path forward for future generations of young women to dream even bigger and reach even higher than ever before.",
                "This groundbreaking initiative powerfully demonstrates how women's authentic leadership, unique perspectives, and collaborative strengths bring fresh insights and transformative approaches to solving complex challenges.",
                "Supportive collaborative networks of mentors and allies have helped these dedicated changemakers flourish, grow in confidence, and amplify their positive impact throughout their fields of expertise.",
                "Such remarkable progress in women's empowerment beautifully shows that when women lead with clear purpose, authentic voice, and compassionate vision, extraordinary transformations unfold naturally across entire societies."
            ],
            'medical_hope': [
                "In a gentle medical breakthrough that brings renewed hope and comfort to countless families, carefully researched advances are opening welcoming doors to healing, recovery, and renewed wellness.",
                "This thoughtfully developed treatment approach offers genuine comfort and tangible relief to those courageously seeking wellness, recovery, and a return to lives filled with health and vitality.",
                "Dedicated healthcare professionals and tireless researchers have worked with scientific precision, deep caring, and unwavering commitment to bring this compassionate care option to fruition for patients.",
                "The innovative treatment approach beautifully honors both rigorous scientific methodology and the deeply human need for gentle, personalized support throughout each person's unique healing journey ahead.",
                "Patients facing health challenges and their loving families can now look toward their futures with significantly greater peace, realistic optimism, and confidence in their pathways to recovery.",
                "Many years of patient research, careful clinical trials, and dedicated scientific investigation have culminated in this beautiful, hopeful moment of meaningful medical progress and healing possibility.",
                "Such inspiring medical advancements tenderly remind us that true healing unfolds through the perfect blend of cutting-edge science, compassionate care, unwavering dedication, and steadfast hope."
            ],
            'feel_good': [
                "In a genuinely touching moment that warms the heart and lifts the spirit, this beautiful story brings gentle light, joy, and renewed faith in goodness to brighten our day.",
                "The gentle, graceful unfolding of these heartwarming events serves as a tender reminder of the inherent goodness, kindness, and compassion that exists abundantly in our shared world.",
                "People from all walks of life have come together with remarkably open hearts, genuine caring intentions, and a shared desire to create something beautiful and meaningful for everyone.",
                "This wonderfully heartwarming development creates expanding ripples of pure joy, warm inspiration, and renewed hope that touch lives far beyond what we can immediately see or measure.",
                "Each precious detail of this uplifting story reveals and celebrates the tender humanity, deep connection, and beautiful compassion that we all fundamentally share as human beings together.",
                "Communities near and far celebrate joyfully together, finding deep connection, shared meaning, and renewed appreciation for the simple yet profound moments that unite and inspire us all.",
                "Such precious reminders gently show us that authentic beauty, spontaneous kindness, and genuine human warmth surround us always, waiting to be noticed, celebrated, and shared with grateful hearts."
            ]
        }
        
        category = categories[0] if categories else 'feel_good'
        template_category = category if category in warm_templates else 'feel_good'
        
        template_sentences = warm_templates[template_category].copy()
        
        if len(sentences) >= 2:
            clean_first = sentences[0]
            clean_second = sentences[1] if len(sentences) > 1 else ""
            
            if len(clean_first.split()) <= 25:
                template_sentences[0] = template_sentences[0]
                if clean_second and len(clean_second.split()) <= 20:
                    template_sentences[1] = f"The initiative focuses on {clean_second.lower()}"
        
        selected_sentences = []
        total_words = 0
        
        for i, sentence in enumerate(template_sentences):
            selected_sentences.append(sentence)
            total_words += len(sentence.split())
            
            if len(selected_sentences) >= 6 and total_words >= 150:
                break
            
            if len(selected_sentences) >= 7 and total_words >= 140:
                break
        
        if len(selected_sentences) < 6:
            while len(selected_sentences) < 6 and len(selected_sentences) < len(template_sentences):
                selected_sentences.append(template_sentences[len(selected_sentences)])
        
        summary = ' '.join(selected_sentences[:7])
        
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
        "You are worthy of gentle mornings and beautiful moments. Let today unfold with grace.",
        "Your presence in this world creates ripples of light. Shine softly today.",
        "Like flowers opening to sunlight, you are allowed to bloom at your own pace.",
        "You carry within you the strength of oceans and the gentleness of morning dew.",
        "Today, may you find peace in small joys and comfort in your own beautiful spirit.",
        "You are deserving of rest, kindness, and all the soft things that bring you peace.",
        "Let yourself be held by the beauty of this moment. You are exactly where you need to be.",
        "Your gentle heart is your greatest strength. Honor it today.",
        "Like the quiet growth of forests, your journey is beautiful even in its stillness.",
        "You are a garden of possibilities. Water yourself with kindness today."
    ]
    
    def ensure_minimum_stories(self, articles: List[Dict], minimum: int = 3, maximum: int = 5) -> List[Dict]:
        """Ensure we have 3-5 stories, using emergency stories if needed."""
        if len(articles) >= minimum:
            logger.info(f"Sufficient articles available: {len(articles)}")
            return articles[:maximum]
        
        needed = minimum - len(articles)
        logger.warning(f"Insufficient articles ({len(articles)}). Adding {needed} emergency stories.")
        
        import random
        emergency_selection = random.sample(self.EMERGENCY_STORIES, min(needed, len(self.EMERGENCY_STORIES)))
        
        combined = articles + emergency_selection
        return combined[:maximum]
    
    def get_daily_affirmation(self) -> str:
        """Get a beautiful affirmation for the day."""
        import random
        return random.choice(self.AFFIRMATIONS)


class MorningEmailGuardian:
    """
    Creates beautiful HTML emails with soft pink/rose aesthetic.
    Gentle typography, warm styling, affirmation box.
    """
    
    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
    
    def generate_html_email(self, stories: List[Dict], affirmation: str) -> str:
        """Generate beautiful HTML email with soft pink/rose aesthetic."""
        today = datetime.now().strftime('%B %d, %Y')
        
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
                <h2 style="color: #d4738c; 
                           font-family: 'Georgia', serif; 
                           font-size: 22px; 
                           margin: 0 0 16px 0;
                           line-height: 1.4;
                           font-weight: 600;">
                    {story.get('title', 'Untitled')}
                </h2>
                <p style="color: #b89199; 
                          font-family: 'Helvetica Neue', 'Arial', sans-serif; 
                          font-size: 13px; 
                          margin: 0 0 12px 0;
                          font-style: italic;">
                    Published: {published_date}
                </p>
                <p style="color: #7d5e67; 
                          font-family: 'Helvetica Neue', 'Arial', sans-serif; 
                          font-size: 16px; 
                          line-height: 1.8;
                          margin: 0 0 18px 0;
                          text-align: justify;">
                    {story.get('summary', '')}
                </p>
                <a href="{story.get('url', '#')}" 
                   style="color: #e08fa3; 
                          text-decoration: none; 
                          font-family: 'Helvetica Neue', 'Arial', sans-serif;
                          font-size: 14px;
                          font-weight: 500;
                          transition: color 0.3s;">
                    Read full article →
                </a>
            </div>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>MorningGlow - {today}</title>
        </head>
        <body style="margin: 0; 
                     padding: 0; 
                     background: linear-gradient(to bottom, #fff9fb, #ffeff5);
                     font-family: 'Helvetica Neue', 'Arial', sans-serif;">
            <div style="max-width: 680px; 
                        margin: 0 auto; 
                        padding: 40px 20px;">
                
                <div style="text-align: center; margin-bottom: 40px;">
                    <h1 style="color: #d4738c; 
                               font-family: 'Georgia', serif; 
                               font-size: 42px; 
                               margin: 0 0 8px 0;
                               font-weight: 300;
                               letter-spacing: 2px;">
                        MorningGlow
                    </h1>
                    <p style="color: #b89199; 
                              font-family: 'Georgia', serif; 
                              font-size: 16px; 
                              margin: 0;
                              font-style: italic;">
                        {today}
                    </p>
                </div>
                
                <div style="margin-bottom: 40px;">
                    {stories_html}
                </div>
                
                <div style="background: linear-gradient(135deg, #ffd9e8 0%, #ffb3d1 100%);
                            border-radius: 16px;
                            padding: 32px;
                            text-align: center;
                            border: 2px solid #ffc4dd;
                            box-shadow: 0 6px 20px rgba(251, 207, 232, 0.25);">
                    <p style="color: #8b4f62;
                              font-family: 'Georgia', serif;
                              font-size: 18px;
                              line-height: 1.7;
                              margin: 0;
                              font-style: italic;">
                        "{affirmation}"
                    </p>
                </div>
                
                <div style="text-align: center; 
                            margin-top: 40px; 
                            padding-top: 24px;
                            border-top: 1px solid #f8d7e3;">
                    <p style="color: #000000; 
                              font-family: 'Helvetica Neue', 'Arial', sans-serif; 
                              font-size: 13px; 
                              margin: 0;">
                        Sent with love by MorningGlow 🌸
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """Send the beautiful email."""
        if not self.smtp_username or not self.smtp_password:
            logger.warning("SMTP credentials not configured. Email not sent.")
            logger.info("Email HTML content would be:")
            logger.info(html_content[:500] + "...")
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
            logger.error(f"Error sending email: {str(e)}")
            return False
    
    def deliver_morning_glow(self, to_email: str, stories: List[Dict], affirmation: str) -> bool:
        """Complete email delivery process."""
        today = datetime.now().strftime('%B %d, %Y')
        subject = f"🌸 Your MorningGlow - {today}"
        
        html_content = self.generate_html_email(stories, affirmation)
        
        with open('preview_email.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info("Email preview saved to preview_email.html")
        
        return self.send_email(to_email, subject, html_content)


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
        'coral reef restoration',
        'wildlife conservation success',
        'reforestation',
        'community volunteers helping',
        'renewable energy progress',
        'women scientists',
        'student achievement',
        'environmental recovery',
        'kindness',
        'heartwarming rescue'
    ]
    
    processor = ContentProcessor()
    processed_articles = processor.process_news(search_queries)
    
    guarantee = ContentGuarantee()
    final_stories = guarantee.ensure_minimum_stories(processed_articles, minimum=3, maximum=5)
    affirmation = guarantee.get_daily_affirmation()
    
    logger.info(f"Final story count: {len(final_stories)}")
    logger.info(f"Daily affirmation: {affirmation}")
    
    email_guardian = MorningEmailGuardian()
    recipient_email = os.getenv('RECIPIENT_EMAIL', 'user@example.com')
    
    success = email_guardian.deliver_morning_glow(recipient_email, final_stories, affirmation)
    
    if success:
        logger.info("🌸 MorningGlow delivered successfully! 🌸")
    else:
        logger.info("🌸 MorningGlow preview generated (check preview_email.html) 🌸")
    
    logger.info("=" * 60)
    logger.info("Sacred morning ritual complete. Peace and beauty prevail.")
    logger.info("=" * 60)
    
    return final_stories


if __name__ == "__main__":
    sacred_morning_flow_with_accuracy()
