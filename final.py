#!/usr/bin/env python3
"""
🎵 JioSaavn Ultimate Bot v2.1 - With Lyrics Search
Added: Google-based lyrics detection (Free & Unlimited)
Render Deployment Ready
"""

import os, sys, time, logging, asyncio, requests, re, random, threading
from dotenv import load_dotenv
from flask import Flask
from bs4 import BeautifulSoup
import urllib.parse

load_dotenv()
from datetime import datetime
from typing import Dict, List, Optional
from io import BytesIO
from collections import defaultdict
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask App for Render Keep-Alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running! 🚀\nUse this URL in UptimeRobot to keep the bot alive.", 200

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8334511601:AAGpaDzTXbZrGKSlWWNBbg7q3Iq1-xfJ_yU")
API_BASE_URL = "https://jiosaavanapi.onrender.com"
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "7097905601").split(",") if x.strip().isdigit()]
SONGS_PER_PAGE = 10
MAX_RETRIES = 5

REQUEST_TIMEOUT = 300

# Session with retry logic
def create_session():
    session = requests.Session()
    retry = Retry(total=MAX_RETRIES, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504, 429])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

SESSION = create_session()

# ==================== NEW: LYRICS SEARCH ====================
class LyricsDetector:
    """Detect song name from lyrics using Google Search"""
    
    @staticmethod
    def search_song_by_lyrics(lyrics_query):
        """Search song using lyrics via Google - Multiple methods"""
        try:
            clean_query = lyrics_query.strip()[:100]
            
            # Method 1: Try direct Google scraping
            song_name = LyricsDetector._google_search(clean_query)
            if song_name:
                logger.info(f"✅ Detected via Google: {song_name}")
                return song_name
            
            # Method 2: Try with "song name" addition
            song_name = LyricsDetector._google_search(f"{clean_query} song name")
            if song_name:
                logger.info(f"✅ Detected via Google (song name): {song_name}")
                return song_name
            
            # Method 3: Extract key phrases and search
            keywords = LyricsDetector._extract_keywords(clean_query)
            if keywords:
                song_name = LyricsDetector._google_search(f"{keywords} song")
                if song_name:
                    logger.info(f"✅ Detected via keywords: {song_name}")
                    return song_name
            
            logger.warning(f"❌ Could not detect song from lyrics: {clean_query}")
            return None
            
        except Exception as e:
            logger.error(f"Lyrics detection error: {e}")
            return None
    
    @staticmethod
    def _google_search(query):
        """Perform Google search and extract song name"""
        try:
            encoded_query = urllib.parse.quote(f"{query} lyrics")
            url = f"https://www.google.com/search?q={encoded_query}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            response = SESSION.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                logger.warning(f"Google returned status: {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Method 1: Try all h3 tags (search result titles)
            for h3 in soup.find_all('h3', limit=5):
                text = h3.get_text()
                song_name = LyricsDetector._extract_song_name(text)
                if song_name:
                    return song_name
            
            # Method 2: Try divs with specific classes
            for div in soup.find_all('div', {'class': ['BNeawe', 'vvjwJb']}, limit=5):
                text = div.get_text()
                song_name = LyricsDetector._extract_song_name(text)
                if song_name:
                    return song_name
            
            # Method 3: Try spans
            for span in soup.find_all('span', limit=10):
                text = span.get_text()
                if 'lyrics' in text.lower() and len(text) < 100:
                    song_name = LyricsDetector._extract_song_name(text)
                    if song_name:
                        return song_name
            
            # Method 4: Extract from page text
            all_text = soup.get_text()
            lines = [l.strip() for l in all_text.split('\n') if 5 < len(l) < 100]
            for line in lines[:20]:
                if any(keyword in line.lower() for keyword in ['lyrics', 'song', 'by']):
                    song_name = LyricsDetector._extract_song_name(line)
                    if song_name:
                        return song_name
            
            return None
            
        except Exception as e:
            logger.error(f"Google search error: {e}")
            return None
    
    @staticmethod
    def _extract_song_name(text):
        """Extract clean song name from text"""
        if not text:
            return None
        
        original_text = text
        
        # Remove URLs
        text = re.sub(r'http\S+|www\.\S+', '', text)
        
        # Remove common suffixes and noise
        text = re.sub(r'\s*[-–—|]\s*(lyrics|official|video|song|audio|full|hd|ft\.|feat\.|featuring).*$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\((lyrics|official|video|audio|full|hd)\).*$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+lyrics\s*$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^lyrics\s+', '', text, flags=re.IGNORECASE)
        
        # Remove "by artist" if exists
        text = re.sub(r'\s+by\s+\w+.*$', '', text, flags=re.IGNORECASE)
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        text = text.strip()
        
        # Must be reasonable length
        if 3 < len(text) < 80:
            # Avoid common noise words
            noise_words = ['google', 'search', 'youtube', 'spotify', 'apple music', 'amazon', 'click here', 
                          'subscribe', 'download', 'watch', 'listen', 'play', 'genius', 'azlyrics']
            
            if not any(noise.lower() in text.lower() for noise in noise_words):
                logger.info(f"Extracted: '{text}' from '{original_text}'")
                return text
        
        return None
    
    @staticmethod
    def _extract_keywords(text):
        """Extract key phrases from lyrics"""
        # Get first 5-6 meaningful words
        words = text.split()
        keywords = ' '.join(words[:6])
        return keywords
    
    @staticmethod
    def is_lyrics_query(text):
        """Check if query looks like lyrics"""
        # Check if it's not a URL
        if 'http' in text.lower() or '.com' in text.lower() or 'jiosaavn' in text.lower():
            return False
        
        # Check if it has multiple words (lyrics usually do)
        words = text.split()
        if len(words) < 4:  # Increased to 4 words minimum
            return False
        
        # Check if it looks like a song name (short queries)
        if len(text) < 20:  # Increased minimum length
            return False
        
        # Check for common song name patterns (likely NOT lyrics)
        song_name_patterns = [
            r'^\w+\s+\w+$',  # Just 2 words
            r'^[\w\s]{1,25}$'  # Very short
        ]
        
        for pattern in song_name_patterns:
            if re.match(pattern, text):
                return False
        
        # Lyrics patterns - more strict
        lyrics_patterns = [
            r'\b(kal|aaj|raat|din|dil|pyar|mohabbat|ishq|tere|meri|tumhe|mere|mein|tha|hai|ho)\b',
            r'\b(love|heart|night|day|feel|life|baby|know|want|need|never|always|when|where)\b',
            r'\b(mil|gaya|tha|hai|ho|na|tu|main|kar|de|le|ja)\b'
        ]
        
        match_count = 0
        for pattern in lyrics_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                match_count += 1
        
        # Need at least 2 pattern matches for lyrics
        if match_count >= 2:
            logger.info(f"Detected as lyrics query: {text}")
            return True
        
        return False

lyrics_detector = LyricsDetector()
# ==================== END NEW CODE ====================

class DataStore:
    def __init__(self):
        self.user_searches: Dict[int, Dict] = {}
        self.user_favorites: Dict[int, List] = defaultdict(list)
        self.user_history: Dict[int, List] = defaultdict(list)
        self.user_playlists: Dict[int, Dict[str, List]] = defaultdict(dict)
        self.global_downloads = 0
        self.global_searches = 0
        self.user_stats: Dict[int, Dict] = defaultdict(lambda: {
            'searches': 0, 'downloads': 0, 'favorites': 0,
            'first_seen': datetime.now().isoformat(), 'last_active': datetime.now().isoformat(),
            'awaiting_playlist': False
        })
        self.user_settings: Dict[int, Dict] = defaultdict(lambda: {
            'quality': '160kbps', 'language': 'hindi', 'notifications': True
        })
    
    def add_to_history(self, uid, song):
        sid = song.get('songid') or song.get('id', '')
        self.user_history[uid] = [s for s in self.user_history[uid] if (s.get('songid') or s.get('id', '')) != sid]
        self.user_history[uid].insert(0, song)
        self.user_history[uid] = self.user_history[uid][:100]
        self.user_stats[uid]['last_active'] = datetime.now().isoformat()
    
    def add_to_favorites(self, uid, song):
        sid = song.get('songid') or song.get('id', '')
        if any((s.get('songid') or s.get('id', '')) == sid for s in self.user_favorites[uid]):
            return False
        self.user_favorites[uid].append(song)
        self.user_stats[uid]['favorites'] += 1
        return True
    
    def remove_from_favorites(self, uid, sid):
        orig = len(self.user_favorites[uid])
        self.user_favorites[uid] = [s for s in self.user_favorites[uid] if (s.get('songid') or s.get('id', '')) != sid]
        return len(self.user_favorites[uid]) < orig
    
    def create_playlist(self, uid, name):
        if name in self.user_playlists[uid]:
            return False
        self.user_playlists[uid][name] = []
        return True
    
    def add_to_playlist(self, uid, name, song):
        if name not in self.user_playlists[uid]:
            return False
        sid = song.get('songid') or song.get('id', '')
        if any((s.get('songid') or s.get('id', '')) == sid for s in self.user_playlists[uid][name]):
            return False
        self.user_playlists[uid][name].append(song)
        return True

db = DataStore()

def fmt_dur(s):
    try: sec = int(s); return f"{sec//60}:{sec%60:02d}"
    except: return "0:00"

def esc(t):
    if not t: return ""
    for c in ['_','*','[',']','(',')','~','`','>','#','+','-','=','|','{','}','.','!']:
        t = str(t).replace(c, f'\\{c}')
    return t

def trunc(t, m=30): return (t[:m]+"…") if t and len(t)>m else (t or "Unknown")

def is_url(t): return any(x in t.lower() for x in ['jiosaavn.com/', 'saavn.com/'])
def url_type(u):
    if '/song/' in u: return 'song'
    if '/album/' in u: return 'album'
    if '/playlist/' in u: return 'playlist'
    if '/featured/' in u: return 'playlist'    
    if '/artist/' in u: return 'artist'
    return None

def get_quality_url(song, quality='160kbps'):
    """Get appropriate quality download URL"""
    media_url = song.get('media_url') or song.get('url', '')
    if not media_url:
        return None
    quality_map = {'96kbps': '96', '160kbps': '160', '320kbps': '320'}
    q = quality_map.get(quality, '160')
    for old_q in ['320', '160', '96']:
        if f'_{old_q}.' in media_url:
            return media_url.replace(f'_{old_q}.', f'_{q}.')
    return media_url

class API:
    @staticmethod
    def norm(s):
        if not s: return s
        if 'id' in s and 'songid' not in s: s['songid'] = s['id']
        if 'song' in s and 'title' not in s: s['title'] = s['song']
        return s
    
    @staticmethod
    def _request(endpoint, params, retries=MAX_RETRIES):
        for attempt in range(retries):
            try:
                r = SESSION.get(f"{API_BASE_URL}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout attempt {attempt+1}/{retries}")
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
            except Exception as e:
                logger.error(f"Request error: {e}")
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
        return None
    
    @staticmethod
    def search(q):
        data = API._request("/result/", {'query': q})
        if data and isinstance(data, list):
            return [API.norm(s) for s in data]
        return None
    
    @staticmethod
    def song(url, lyrics=False):
        data = API._request("/song/", {'query': url, 'lyrics': str(lyrics).lower()})
        return API.norm(data) if data else None
    
    @staticmethod
    def album(url):
        data = API._request("/album/", {'query': url})
        if data and 'songs' in data:
            data['songs'] = [API.norm(s) for s in data['songs']]
        return data
    
    @staticmethod
    def playlist(url):
        data = API._request("/playlist/", {'query': url})
        if data and 'songs' in data:
            data['songs'] = [API.norm(s) for s in data['songs']]
        return data
    
    @staticmethod
    def download(url, retries=MAX_RETRIES):
        for attempt in range(retries):
            try:
                r = SESSION.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}, 
                               timeout=REQUEST_TIMEOUT, stream=True)
                if r.status_code == 200:
                    buf = BytesIO()
                    for c in r.iter_content(16384):
                        buf.write(c)
                    buf.seek(0)
                    return buf.read()
            except Exception as e:
                logger.error(f"Download attempt {attempt+1}: {e}")
                if attempt < retries - 1:
                    time.sleep(1)
        return None

api = API()

# Loading messages - IMPROVED
LOADING_MSGS = ["⏳ Loading your music…", "🎵 Fetching the beats…", "🔄 Almost there…", "🎧 Preparing your track…", "✨ Magic happening…"]
SEARCH_MSGS = ["🔍 Searching the universe…", "🎵 Finding your vibe…", "🔎 Hunting for tracks…"]
LYRICS_MSGS = ["🎼 Detecting song from lyrics…", "🔍 Analyzing your lyrics…", "🎵 Finding the perfect match…"]

class KB:
    @staticmethod
    def main():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Search Songs", callback_data="m_search"),
             InlineKeyboardButton("🔥 Trending", callback_data="m_trend")],
            [InlineKeyboardButton("💖 Favorites", callback_data="m_fav"),
             InlineKeyboardButton("📜 History", callback_data="m_hist")],
            [InlineKeyboardButton("🎭 By Mood", callback_data="m_mood"),
             InlineKeyboardButton("🎤 Artists", callback_data="m_artist")],
            [InlineKeyboardButton("🎼 Lyrics Search", callback_data="m_lyrics"),  # NEW
             InlineKeyboardButton("📊 My Stats", callback_data="m_stats")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="m_settings"),
             InlineKeyboardButton("📋 Playlists", callback_data="m_playlist")],
            [InlineKeyboardButton("❓ Help", callback_data="m_help")]
        ])
    
    @staticmethod
    def songs(songs, start, total, source='search'):
        kb = []
        end = min(start + SONGS_PER_PAGE, len(songs))
        for i in range(start, end):
            s = songs[i]
            t = trunc(s.get('title') or s.get('song','?'), 22)
            a = trunc(s.get('singers','?'), 12)
            d = fmt_dur(s.get('duration','0'))
            kb.append([InlineKeyboardButton(f"🎵 {t} • {a} [{d}]", callback_data=f"s_{i}")])
        
        nav = []
        if start > 0: nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"p_{start-SONGS_PER_PAGE}"))
        pg = (start//SONGS_PER_PAGE)+1
        tot = (total+SONGS_PER_PAGE-1)//SONGS_PER_PAGE
        nav.append(InlineKeyboardButton(f"📄 {pg}/{tot}", callback_data="x"))
        if end < total: nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"p_{end}"))
        if nav: kb.append(nav)
        
        kb.append([
            InlineKeyboardButton("⬇️ Download All", callback_data="dall"),
            InlineKeyboardButton("🔀 Shuffle", callback_data="shuffle")
        ])
        kb.append([InlineKeyboardButton("🏠 Home", callback_data="menu"), InlineKeyboardButton("❌ Close", callback_data="close")])
        return InlineKeyboardMarkup(kb)
    
    @staticmethod
    def detail(idx, fav, pg):
        f = "💔 Remove" if fav else "💖 Favorite"
        fc = f"uf_{idx}" if fav else f"f_{idx}"
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⬇️ Download Now", callback_data=f"d_{idx}")],
            [InlineKeyboardButton("📝 Lyrics", callback_data=f"l_{idx}"),
             InlineKeyboardButton("📤 Share", callback_data=f"sh_{idx}")],
            [InlineKeyboardButton(f, callback_data=fc),
             InlineKeyboardButton("➕ Playlist", callback_data=f"addpl_{idx}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"b_{pg}"),
             InlineKeyboardButton("🏠 Home", callback_data="menu")]
        ])
    
    @staticmethod
    def collection(songs, start=0, col_type='album'):
        kb = []
        end = min(start + SONGS_PER_PAGE, len(songs))
        for i in range(start, end):
            s = songs[i]
            t = trunc(s.get('title') or s.get('song','?'), 28)
            d = fmt_dur(s.get('duration','0'))
            kb.append([InlineKeyboardButton(f"🎵 {t} [{d}]", callback_data=f"c_{i}")])
        
        nav = []
        if start > 0:
            nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"cp_{start-SONGS_PER_PAGE}"))
        pg = (start//SONGS_PER_PAGE)+1
        tot = (len(songs)+SONGS_PER_PAGE-1)//SONGS_PER_PAGE
        nav.append(InlineKeyboardButton(f"📄 {pg}/{tot}", callback_data="x"))
        if end < len(songs):
            nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"cp_{end}"))
        if nav:
            kb.append(nav)
        
        kb.append([
            InlineKeyboardButton("⬇️ Download All", callback_data="dall"),
            InlineKeyboardButton("💖 Save All", callback_data="savall")
        ])
        kb.append([InlineKeyboardButton("🏠 Home", callback_data="menu"), InlineKeyboardButton("❌ Close", callback_data="close")])
        return InlineKeyboardMarkup(kb)
    
    @staticmethod
    def favs(favs):
        kb = []
        for i, s in enumerate(favs[:10]):
            t = trunc(s.get('title') or s.get('song','?'), 28)
            kb.append([InlineKeyboardButton(f"💖 {t}", callback_data=f"fp_{i}")])
        if len(favs) > 10:
            kb.append([InlineKeyboardButton(f"📋 +{len(favs)-10} more songs", callback_data="morefav")])
        if favs:
            kb.append([
                InlineKeyboardButton("🔀 Shuffle Play", callback_data="shfav"),
                InlineKeyboardButton("🗑️ Clear All", callback_data="cfav")
            ])
        kb.append([InlineKeyboardButton("🏠 Home", callback_data="menu")])
        return InlineKeyboardMarkup(kb)
    
    @staticmethod
    def hist(hist):
        kb = []
        for i, s in enumerate(hist[:10]):
            t = trunc(s.get('title') or s.get('song','?'), 28)
            kb.append([InlineKeyboardButton(f"📜 {t}", callback_data=f"hp_{i}")])
        if len(hist) > 10:
            kb.append([InlineKeyboardButton(f"📋 +{len(hist)-10} more songs", callback_data="morehist")])
        if hist: 
            kb.append([
                InlineKeyboardButton("🔁 Replay Recent", callback_data="replay"),
                InlineKeyboardButton("🗑️ Clear", callback_data="chist")
            ])
        kb.append([InlineKeyboardButton("🏠 Home", callback_data="menu")])
        return InlineKeyboardMarkup(kb)
    
    @staticmethod
    def moods():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("😊 Happy", callback_data="mood_happy"),
             InlineKeyboardButton("😢 Sad", callback_data="mood_sad")],
            [InlineKeyboardButton("💪 Workout", callback_data="mood_workout"),
             InlineKeyboardButton("😴 Sleep", callback_data="mood_sleep")],
            [InlineKeyboardButton("🎉 Party", callback_data="mood_party"),
             InlineKeyboardButton("💕 Romance", callback_data="mood_romance")],
            [InlineKeyboardButton("🧘 Chill", callback_data="mood_chill"),
             InlineKeyboardButton("🔥 Energy", callback_data="mood_energy")],
            [InlineKeyboardButton("🏠 Home", callback_data="menu")]
        ])
    
    @staticmethod
    def artists():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Arijit Singh", callback_data="art_arijit"),
             InlineKeyboardButton("Shreya Ghoshal", callback_data="art_shreya")],
            [InlineKeyboardButton("Atif Aslam", callback_data="art_atif"),
             InlineKeyboardButton("Neha Kakkar", callback_data="art_neha")],
            [InlineKeyboardButton("AP Dhillon", callback_data="art_apdhillon"),
             InlineKeyboardButton("Jubin Nautiyal", callback_data="art_jubin")],
            [InlineKeyboardButton("KK", callback_data="art_kk"),
             InlineKeyboardButton("Sonu Nigam", callback_data="art_sonu")],
            [InlineKeyboardButton("🔍 Search Artist", callback_data="art_search")],
            [InlineKeyboardButton("🏠 Home", callback_data="menu")]
        ])
    
    @staticmethod
    def settings(uid):
        s = db.user_settings[uid]
        q = s.get('quality', '160kbps')
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📶 Quality: {q}", callback_data="set_quality")],
            [InlineKeyboardButton("🇮🇳 Hindi", callback_data="lang_hindi"),
             InlineKeyboardButton("🇬🇧 English", callback_data="lang_english")],
            [InlineKeyboardButton("🔔 Notifications", callback_data="set_notif")],
            [InlineKeyboardButton("🏠 Home", callback_data="menu")]
        ])
    
    @staticmethod
    def quality():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📶 96kbps (Fast)", callback_data="q_96")],
            [InlineKeyboardButton("📶 160kbps (Balanced) ✓", callback_data="q_160")],
            [InlineKeyboardButton("📶 320kbps (Best)", callback_data="q_320")],
            [InlineKeyboardButton("🔙 Back", callback_data="m_settings")]
        ])
    
    @staticmethod
    def playlists(uid):
        pls = db.user_playlists[uid]
        kb = []
        for name, songs in list(pls.items())[:8]:
            kb.append([InlineKeyboardButton(f"📁 {name} ({len(songs)})", callback_data=f"pl_{name}")])
        kb.append([InlineKeyboardButton("➕ Create New", callback_data="newpl")])
        kb.append([InlineKeyboardButton("🏠 Home", callback_data="menu")])
        return InlineKeyboardMarkup(kb)

kb = KB()

# === COMMANDS ===
async def cmd_start(u: Update, c):
    user = u.effective_user
    name = esc(user.first_name)
    
    welcome = f"""
╔══════════════════════════╗
   🎵 *Groovia Bot*    
╚══════════════════════════╝

Hey *{name}*\\! Welcome\\! 🎉

🎧 *What I can do:*
• Search millions of songs
• Download in high quality
• 🆕 Find songs by lyrics
• Create your playlists
• Track your listening history

💡 *Quick Start:*
Send me a song name, lyrics,
or paste a JioSaavn link\\!

━━━━━━━━━━━━━━━━━━━━━
"""
    await u.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())

async def cmd_help(u: Update, c):
    help_text = """
📚 *Help Guide*

*🔍 Search Songs:*
Send any song name to search

*🎼 Lyrics Search:* 🆕
Send lyrics like:
"kal raste mein gham mil gya tha"
Bot will detect the song\\!

*🔗 Direct Links:*
Paste JioSaavn URL for:
• Songs • Albums • Playlists

*📋 Commands:*
/start \\- Start bot
/menu \\- Main menu
/favorites \\- Your saved songs
/history \\- Recently played
/stats \\- Your statistics
/settings \\- Bot settings

*💡 Tips:*
• Add songs to favorites
• Create custom playlists
• Explore by mood or artist

━━━━━━━━━━━━━━━━━━━━━
"""
    await u.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())

async def cmd_menu(u: Update, c):
    await u.message.reply_text(
        "╔═══════════════════╗\n   🎵 *Main Menu*\n╚═══════════════════╝",
        parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main()
    )

async def cmd_fav(u: Update, c):
    uid = u.effective_user.id
    favs = db.user_favorites[uid]
    if not favs:
        await u.message.reply_text("💔 *No favorites yet\\!*\n\nSearch songs and tap 💖 to save", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
        return
    await u.message.reply_text(f"💖 *Your Favorites*\n📊 {len(favs)} songs saved", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.favs(favs))

async def cmd_hist(u: Update, c):
    uid = u.effective_user.id
    hist = db.user_history[uid]
    if not hist:
        await u.message.reply_text("📜 *No history yet\\!*\n\nStart exploring music\\!", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
        return
    await u.message.reply_text(f"📜 *Your History*\n📊 {len(hist)} songs", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.hist(hist))

async def cmd_stats(u: Update, c):
    uid = u.effective_user.id
    st = db.user_stats[uid]
    favs = len(db.user_favorites[uid])
    hist = len(db.user_history[uid])
    pls = len(db.user_playlists[uid])
    
    stats_text = f"""
╔══════════════════════════╗
       📊 *Your Statistics*       
╚══════════════════════════╝

🔍 *Searches:* {st['searches']}
⬇️ *Downloads:* {st['downloads']}
💖 *Favorites:* {favs}
📜 *History:* {hist}
📁 *Playlists:* {pls}

📅 *First seen:* {st['first_seen'][:10]}
⏰ *Last active:* {st['last_active'][:10]}

━━━━━━━━━━━━━━━━━━━━━
🌍 *Global Stats*
📥 Total Downloads: {db.global_downloads}
🔍 Total Searches: {db.global_searches}
"""
    await u.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())

async def cmd_settings(u: Update, c):
    uid = u.effective_user.id
    await u.message.reply_text("⚙️ *Settings*\n\nCustomize your experience:", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.settings(uid))

# === MESSAGE HANDLER ===
async def on_text(u: Update, c):
    txt = u.message.text.strip()
    uid = u.effective_user.id
    
    # Check if awaiting playlist name
    if db.user_stats[uid].get('awaiting_playlist', False):
        db.user_stats[uid]['awaiting_playlist'] = False
        if len(txt) > 50:
            await u.message.reply_text("❌ *Playlist name too long\\!*\n\nMax 50 characters", parse_mode=ParseMode.MARKDOWN_V2)
            return
        if db.create_playlist(uid, txt):
            await u.message.reply_text(f"✅ *Playlist created\\!*\n\n📁 {esc(txt)}", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.playlists(uid))
        else:
            await u.message.reply_text("❌ *Playlist already exists\\!*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.playlists(uid))
        return
    
    if len(txt) < 2:
        await u.message.reply_text("❌ Query too short\\!", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    if is_url(txt):
        await handle_url(u, c, txt, uid)
    # NEW: Check if it's lyrics query
    elif lyrics_detector.is_lyrics_query(txt):
        await handle_lyrics_search(u, c, txt, uid)
    else:
        await handle_search(u, c, txt, uid)

# ==================== NEW: LYRICS SEARCH HANDLER ====================
async def handle_lyrics_search(u, c, lyrics, uid):
    """Handle lyrics-based song search with animated loader"""
    loading_msg = random.choice(LYRICS_MSGS)
    
    # Animated loader frames
    loader_frames = [
        "🎼 Analyzing lyrics\n\n⠋",
        "🎼 Analyzing lyrics\n\n⠙",
        "🎼 Analyzing lyrics\n\n⠹",
        "🎼 Analyzing lyrics\n\n⠸",
        "🎼 Analyzing lyrics\n\n⠼",
        "🎼 Analyzing lyrics\n\n⠴",
        "🎼 Analyzing lyrics\n\n⠦",
        "🎼 Analyzing lyrics\n\n⠧",
        "🎼 Analyzing lyrics\n\n⠇",
        "🎼 Analyzing lyrics\n\n⠏"
    ]
    
    msg = await u.message.reply_text(loader_frames[0], parse_mode=ParseMode.MARKDOWN_V2)
    
    # Animate loader while detecting
    async def animate_loader():
        for i in range(30):  # Run for ~3 seconds
            try:
                await msg.edit_text(esc(loader_frames[i % len(loader_frames)]), parse_mode=ParseMode.MARKDOWN_V2)
                await asyncio.sleep(0.1)
            except:
                break
    
    # Run animation and detection in parallel
    animation_task = asyncio.create_task(animate_loader())
    
    # Detect song name from lyrics
    song_name = await asyncio.to_thread(lyrics_detector.search_song_by_lyrics, lyrics)
    
    # Stop animation
    animation_task.cancel()
    
    if not song_name:
        # Try searching with first few words as fallback
        fallback_query = ' '.join(lyrics.split()[:6])
        logger.info(f"Fallback: Searching with '{fallback_query}'")
        await msg.edit_text(f"🔍 *Searching with:*\n`{esc(fallback_query)}`\n\n_Finding best matches\\.\\.\\._", parse_mode=ParseMode.MARKDOWN_V2)
        await asyncio.sleep(0.5)
        await handle_search_internal(msg, c, fallback_query, uid, is_lyrics=True)
        return
    
    # Show detected song
    await msg.edit_text(f"✅ *Song Detected\\!*\n\n🎵 `{esc(song_name)}`\n\n🔍 Searching JioSaavn\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
    await asyncio.sleep(0.5)
    
    # Search for the detected song
    await handle_search_internal(msg, c, song_name, uid, is_lyrics=True)

async def handle_search_internal(msg, c, q, uid, is_lyrics=False):
    """Internal search function used by both regular and lyrics search"""
    db.user_stats[uid]['searches'] += 1
    db.global_searches += 1
    
    songs = api.search(q)
    if not songs:
        await msg.edit_text(
            "😕 *No results found\\!*\n\n💡 Try different keywords",
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main()
        )
        return
    
    db.user_searches[uid] = {'q': q, 'songs': songs}
    
    prefix = "🎼 *From Lyrics*" if is_lyrics else "🔍 *Search Results*"
    result_text = f"""
╔══════════════════════════╗
    {prefix}
╚══════════════════════════╝

🎵 *Query:* `{esc(q)}`
📊 *Found:* {len(songs)} songs

━━━━━━━━━━━━━━━━━━━━━
"""
    await msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.songs(songs, 0, len(songs)))
# ==================== END NEW CODE ====================

async def handle_search(u, c, q, uid):
    db.user_stats[uid]['searches'] += 1
    db.global_searches += 1
    
    loading_msg = random.choice(SEARCH_MSGS)
    msg = await u.message.reply_text(f"{loading_msg}", parse_mode=ParseMode.MARKDOWN_V2)
    
    songs = api.search(q)
    if not songs:
        await msg.edit_text(
            "😕 *No results found\\!*\n\n💡 Try different keywords",
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main()
        )
        return
    
    db.user_searches[uid] = {'q': q, 'songs': songs}
    
    result_text = f"""
╔══════════════════════════╗
    🔍 *Search Results*
╚══════════════════════════╝

🎵 *Query:* `{esc(q)}`
📊 *Found:* {len(songs)} songs

━━━━━━━━━━━━━━━━━━━━━
"""
    await msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.songs(songs, 0, len(songs)))

async def handle_url(u, c, url, uid):
    msg = await u.message.reply_text("🔗 *Processing link\\.\\.\\.*", parse_mode=ParseMode.MARKDOWN_V2)
    
    t = url_type(url)
    
    if t == 'song':
        song = api.song(url)
        if song:
            db.user_searches[uid] = {'q': url, 'songs': [song]}
            db.add_to_history(uid, song)
            await send_song_detail(msg, c, uid, song, 0, 0)
        else:
            await msg.edit_text("❌ *Could not fetch song\\!*\n\nTry again later", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
    
    elif t == 'album':
        album = api.album(url)
        if album and album.get('songs'):
            db.user_searches[uid] = {'q': url, 'songs': album['songs'], 'col': album, 'type': 'album'}
            name = album.get('title') or album.get('name', 'Album')
            year = album.get('year', '')
            
            album_text = f"""
╔══════════════════════════╗
       💿 *Album*
╚══════════════════════════╝

📀 *{esc(name)}*
📅 Year: {year}
🎵 {len(album['songs'])} songs

━━━━━━━━━━━━━━━━━━━━━
"""
            await msg.edit_text(album_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.collection(album['songs'], 0, 'album'))
        else:
            await msg.edit_text("❌ *Could not fetch album\\!*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
    
    elif t == 'playlist':
        pl = api.playlist(url)
        if pl and pl.get('songs'):
            db.user_searches[uid] = {'q': url, 'songs': pl['songs'], 'col': pl, 'type': 'playlist'}
            name = pl.get('listname') or pl.get('title', 'Playlist')
            
            pl_text = f"""
╔══════════════════════════╗
       📋 *Playlist*
╚══════════════════════════╝

📝 *{esc(name)}*
🎵 {len(pl['songs'])} songs

━━━━━━━━━━━━━━━━━━━━━
"""
            await msg.edit_text(pl_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.collection(pl['songs'], 0, 'playlist'))
        else:
            await msg.edit_text("❌ *Could not fetch playlist\\!*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
    else:
        await msg.edit_text("❌ *Invalid URL\\!*\n\nSupported: song/album/playlist", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())

async def send_song_detail(msg, c, uid, song, idx, pg):
    title = song.get('title') or song.get('song', 'Unknown')
    singers = song.get('singers', 'Unknown')
    album = song.get('album', 'Unknown')
    dur = fmt_dur(song.get('duration', '0'))
    year = song.get('year', 'N/A')
    lang = str(song.get('language', 'N/A')).title()
    
    sid = song.get('songid') or song.get('id', '')
    fav = any((s.get('songid') or s.get('id', '')) == sid for s in db.user_favorites[uid])
    
    info = f"""
╔══════════════════════════╗
       🎵 *Now Playing*
╚══════════════════════════╝

🎶 *{esc(title)}*

👤 *Artist:* {esc(singers)}
💿 *Album:* {esc(album)}
⏱ *Duration:* {dur}
📅 *Year:* {year}
🌐 *Language:* {lang}

━━━━━━━━━━━━━━━━━━━━━
"""
    img = song.get('image') or song.get('image_url', '')
    
    try: await msg.delete()
    except: pass
    
    if img:
        try:
            await c.bot.send_photo(chat_id=msg.chat.id, photo=img, caption=info,
                parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.detail(idx, fav, pg))
            return
        except: pass
    
    await c.bot.send_message(chat_id=msg.chat.id, text=info,
        parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.detail(idx, fav, pg))

# === CALLBACKS ===
async def on_callback(u: Update, c):
    q = u.callback_query
    await q.answer()
    uid = u.effective_user.id
    d = q.data
    
    if d == "close":
        try: await q.message.delete()
        except: pass
        return
    if d == "x": return
    if d == "menu":
        await q.edit_message_text("╔═══════════════════╗\n   🎵 *Main Menu*\n╚═══════════════════╝", 
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
        return
    
    # Menu items
    if d == "m_search":
        await q.edit_message_text("🔍 *Search Mode*\n\nSend me a song name or JioSaavn link\\!", parse_mode=ParseMode.MARKDOWN_V2)
    
    # NEW: Lyrics search info
    elif d == "m_lyrics":
        await q.edit_message_text(
            "🎼 *Lyrics Search Mode*\n\n"
            "Send me any lyrics and I'll find the song\\!\n\n"
            "📝 *Example:*\n"
            "`kal raste mein gham mil gya tha`\n\n"
            "✨ Works with Hindi \\& English lyrics\\!",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="menu")]])
        )
    
    elif d == "m_trend":
        await q.edit_message_text("🔥 *Loading Trending\\.\\.\\.*", parse_mode=ParseMode.MARKDOWN_V2)
        songs = api.search("top songs 2024")
        if songs:
            db.user_searches[uid] = {'q': 'Trending', 'songs': songs}
            await q.edit_message_text(f"🔥 *Trending Now*\n📊 {len(songs)} hot tracks", 
                parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.songs(songs, 0, len(songs)))
        else:
            await q.edit_message_text("❌ *Failed to load\\!*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
    
    elif d == "m_fav":
        favs = db.user_favorites[uid]
        if not favs:
            await q.edit_message_text("💔 *No favorites yet\\!*\n\nSearch songs and tap 💖", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
        else:
            await q.edit_message_text(f"💖 *Your Favorites*\n📊 {len(favs)} songs", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.favs(favs))
    
    elif d == "m_hist":
        hist = db.user_history[uid]
        if not hist:
            await q.edit_message_text("📜 *No history yet\\!*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
        else:
            await q.edit_message_text(f"📜 *Your History*\n📊 {len(hist)} songs", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.hist(hist))
    
    elif d == "m_mood":
        await q.edit_message_text("🎭 *Browse by Mood*\n\nSelect your vibe:", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.moods())
    
    elif d == "m_artist":
        await q.edit_message_text("🎤 *Popular Artists*\n\nSelect an artist:", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.artists())
    
    elif d == "m_stats":
        st = db.user_stats[uid]
        favs = len(db.user_favorites[uid])
        await q.edit_message_text(
            f"📊 *Your Stats*\n\n🔍 Searches: {st['searches']}\n⬇️ Downloads: {st['downloads']}\n💖 Favorites: {favs}\n📜 History: {len(db.user_history[uid])}",
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
    
    elif d == "m_settings":
        await q.edit_message_text("⚙️ *Settings*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.settings(uid))
    
    elif d == "m_playlist":
        await q.edit_message_text("📋 *Your Playlists*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.playlists(uid))
    
    elif d == "m_help":
        await q.edit_message_text(
            "💡 *Quick Help*\n\n"
            "• Send song name to search\n"
            "• Send lyrics to find song 🆕\n"
            "• Paste JioSaavn URL\n"
            "• Tap song to download", 
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
    
    # Mood searches
    elif d.startswith("mood_"):
        mood = d[5:]
        mood_queries = {
            'happy': 'happy songs', 
            'sad': 'sad songs',
            'workout': 'workout songs', 
            'sleep': 'sleep music',
            'party': 'party songs', 
            'romance': 'romantic songs',
            'chill': 'chill songs', 
            'energy': 'energetic songs'
        }
        query = mood_queries.get(mood, 'top songs')
        await q.edit_message_text(f"🎭 *Loading {mood.title()} vibes\\.\\.\\.*", parse_mode=ParseMode.MARKDOWN_V2)
        songs = api.search(query)
        if songs:
            db.user_searches[uid] = {'q': f'{mood.title()} Mood', 'songs': songs}
            await q.edit_message_text(f"🎭 *{esc(mood.title())} Vibes*\n📊 {len(songs)} songs", 
                parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.songs(songs, 0, len(songs)))
        else:
            await q.edit_message_text("❌ *Failed\\!*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
    
    # Artist searches
    elif d.startswith("art_"):
        artist = d[4:]
        artist_names = {
            'arijit': 'Arijit Singh', 
            'shreya': 'Shreya Ghoshal', 
            'atif': 'Atif Aslam',
            'neha': 'Neha Kakkar', 
            'apdhillon': 'AP Dhillon', 
            'jubin': 'Jubin Nautiyal',
            'kk': 'KK', 
            'sonu': 'Sonu Nigam'
        }
        if artist == 'search':
            await q.edit_message_text("🎤 *Artist Search*\n\nSend artist name:", parse_mode=ParseMode.MARKDOWN_V2)
            return
        name = artist_names.get(artist, artist)
        await q.edit_message_text(f"🎤 *Loading {esc(name)}\\.\\.\\.*", parse_mode=ParseMode.MARKDOWN_V2)
        songs = api.search(name)
        if songs:
            db.user_searches[uid] = {'q': name, 'songs': songs}
            await q.edit_message_text(f"🎤 *{esc(name)}*\n📊 {len(songs)} songs", 
                parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.songs(songs, 0, len(songs)))
        else:
            await q.edit_message_text("❌ *No songs found\\!*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
    
    # Quality settings
    elif d == "set_quality":
        await q.edit_message_text("📶 *Select Quality*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.quality())
    
    elif d.startswith("q_"):
        quality = d[2:] + 'kbps'
        db.user_settings[uid]['quality'] = quality
        await q.answer(f"✅ Quality set to {quality}", show_alert=True)
        await q.edit_message_text("⚙️ *Settings*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.settings(uid))
    
    # Song select
    elif d.startswith("s_"):
        idx = int(d[2:])
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        if idx >= len(songs): return
        song = songs[idx]
        pg = (idx // SONGS_PER_PAGE) * SONGS_PER_PAGE
        
        purl = song.get('perma_url', '')
        if purl:
            det = api.song(purl)
            if det: song.update(det); db.user_searches[uid]['songs'][idx] = song
        
        db.add_to_history(uid, song)
        await send_song_detail(q.message, c, uid, song, idx, pg)
    
    # Collection song
    elif d.startswith("c_"):
        idx = int(d[2:])
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        if idx >= len(songs): return
        song = songs[idx]
        db.add_to_history(uid, song)
        await send_song_detail(q.message, c, uid, song, idx, 0)
    
    # Collection pagination
    elif d.startswith("cp_"):
        start = int(d[3:])
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        col_type = db.user_searches[uid].get('type', 'album')
        await q.edit_message_reply_markup(reply_markup=kb.collection(songs, start, col_type))
    
    # Pagination
    elif d.startswith("p_"):
        start = int(d[2:])
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        await q.edit_message_reply_markup(reply_markup=kb.songs(songs, start, len(songs)))
    
    # Shuffle
    elif d == "shuffle":
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs'].copy()
        random.shuffle(songs)
        db.user_searches[uid]['songs'] = songs
        await q.edit_message_reply_markup(reply_markup=kb.songs(songs, 0, len(songs)))
        await q.answer("🔀 Shuffled!", show_alert=False)
    
    # Back
    elif d.startswith("b_"):
        pg = int(d[2:])
        if uid not in db.user_searches:
            await q.message.reply_text("⚠️ Session expired\\!", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
            return
        songs = db.user_searches[uid]['songs']
        qry = db.user_searches[uid].get('q', 'Results')
        try: await q.message.delete()
        except: pass
        await c.bot.send_message(q.message.chat.id, f"🎵 *{esc(str(qry)[:30])}*\n📊 {len(songs)} songs",
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.songs(songs, pg, len(songs)))
    
    # Download
    elif d.startswith("d_"):
        idx = int(d[2:])
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        if idx >= len(songs): return
        song = songs[idx]
        
        await q.answer("⬇️ Starting download...")
        
        loading_text = """
╔══════════════════════════╗
    ⏳ *Downloading*
╚══════════════════════════╝

🎵 Fetching your music\\.\\.\\.

⣾⣿⣿⣿⣿⣿⣿⣿⣿⣷
█░░░░░░░░░░░░░░░░░░░░░░█
█░░▓▓▓▓▓▓▓░░░░░░░░░░░░░█  
█░░░░░░░░░░░░░░░░░░░░░░█
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿

_Please wait\\.\\.\\._
"""
        msg = await q.message.reply_text(loading_text, parse_mode=ParseMode.MARKDOWN_V2)
        
        try:
            await c.bot.send_chat_action(q.message.chat.id, "upload_audio")
            
            dl_url = song.get('media_url') or song.get('url', '')
            if not dl_url:
                purl = song.get('perma_url', '')
                if purl:
                    det = api.song(purl)
                    if det: 
                        dl_url = det.get('media_url') or det.get('url', '')
                        song.update(det)
            
            if not dl_url:
                await msg.edit_text("❌ *Download URL not found\\!*", parse_mode=ParseMode.MARKDOWN_V2)
                return
            
            quality = db.user_settings[uid].get('quality', '160kbps')
            dl_url = get_quality_url(song, quality) or dl_url
            
            await msg.edit_text("""
╔══════════════════════════╗
    ⏳ *Downloading*
╚══════════════════════════╝

🎵 Fetching your music\\.\\.\\.

⣾⣿⣿⣿⣿⣿⣿⣿⣿⣷
█░░░░░░░░░░░░░░░░░░░░░░█
█░░▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░█  
█░░░░░░░░░░░░░░░░░░░░░░█
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿

_Almost there\\.\\.\\._
""", parse_mode=ParseMode.MARKDOWN_V2)
            
            data = api.download(dl_url)
            if not data:
                await msg.edit_text("❌ *Download failed\\!* Try again", parse_mode=ParseMode.MARKDOWN_V2)
                return
            
            title = song.get('title') or song.get('song', 'Unknown')
            singers = song.get('singers', 'Unknown')
            dur = int(song.get('duration', 0))
            img = song.get('image') or song.get('image_url', '')
            
            thumb = None
            if img:
                try:
                    tr = SESSION.get(img, timeout=15)
                    if tr.status_code == 200: thumb = BytesIO(tr.content)
                except: pass
            
            audio = BytesIO(data)
            safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]
            audio.name = f"{safe_title}.mp3"
            
            await msg.edit_text("""
╔══════════════════════════╗
    📤 *Uploading*
╚══════════════════════════╝

🎵 Sending to you\\.\\.\\.

⣾⣿⣿⣿⣿⣿⣿⣿⣿⣷
█░░░░░░░░░░░░░░░░░░░░░░█
█░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░█  
█░░░░░░░░░░░░░░░░░░░░░░█
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿

_Uploading\\.\\.\\._
""", parse_mode=ParseMode.MARKDOWN_V2)
            
            caption = f"🎵 *{esc(title)}*\n👤 {esc(singers)}\n\n_Downloaded via @Grooviabot_"
            
            await c.bot.send_audio(
                chat_id=q.message.chat.id, 
                audio=audio, 
                thumbnail=thumb,
                title=title, 
                performer=singers, 
                duration=dur, 
                filename=f"{safe_title}.mp3",
                caption=caption, 
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
            db.user_stats[uid]['downloads'] += 1
            db.global_downloads += 1
            await msg.delete()
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            await msg.edit_text("❌ *Error occurred\\!*\n\nPlease try again", parse_mode=ParseMode.MARKDOWN_V2)
    
    # Download all
    elif d == "dall":
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        max_dl = len(songs)

        await q.answer(f"⬇️ Downloading {max_dl} songs...")
        
        msg = await q.message.reply_text(f"📥 *Batch Download*\n\n⏳ Downloading 0/{max_dl}\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
        
        done = 0
        for i, song in enumerate(songs[:max_dl]):
            try:
                dl_url = song.get('media_url') or song.get('url', '')
                if not dl_url:
                    purl = song.get('perma_url', '')
                    if purl:
                        det = api.song(purl)
                        if det: dl_url = det.get('media_url') or det.get('url', '')
                
                if dl_url:
                    quality = db.user_settings[uid].get('quality', '160kbps')
                    dl_url = get_quality_url(song, quality) or dl_url
                    data = api.download(dl_url)
                    
                    if data:
                        title = song.get('title') or song.get('song', 'Song')
                        safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]
                        audio = BytesIO(data)
                        audio.name = f"{safe_title}.mp3"
                        
                        await c.bot.send_audio(chat_id=q.message.chat.id, audio=audio, title=title, filename=f"{safe_title}.mp3")
                        done += 1
                        db.user_stats[uid]['downloads'] += 1
                        db.global_downloads += 1
                        
                        await msg.edit_text(f"📥 *Batch Download*\n\n⏳ Downloaded {done}/{max_dl}\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
                
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.error(f"Batch download error: {e}")
        
        await msg.edit_text(f"✅ *Download Complete\\!*\n\n📊 {done}/{max_dl} songs downloaded", parse_mode=ParseMode.MARKDOWN_V2)
    
    # Save all to favorites
    elif d == "savall":
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        added = 0
        for song in songs:
            if db.add_to_favorites(uid, song): 
                added += 1
        if added > 0:
            await q.answer(f"💖 Added {added} songs to favorites!", show_alert=True)
        else:
            await q.answer("All songs already in favorites!", show_alert=True)
    
    # Lyrics
    elif d.startswith("l_"):
        idx = int(d[2:])
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        if idx >= len(songs): return
        song = songs[idx]
        
        purl = song.get('perma_url', '')
        if not purl:
            await q.message.reply_text("❌ *Lyrics not available\\!*", parse_mode=ParseMode.MARKDOWN_V2)
            return
        
        await q.answer("📝 Fetching lyrics...")
        det = api.song(purl, lyrics=True)
        lyrics = det.get('lyrics', '') if det else ''
        
        if not lyrics:
            await q.message.reply_text("😕 *No lyrics found\\!*", parse_mode=ParseMode.MARKDOWN_V2)
            return
        
        title = det.get('title') or det.get('song', '')
        txt = f"📝 *{esc(title)}*\n\n━━━━━━━━━━━━━━━━━━━━━\n\n{esc(lyrics)}"
        if len(txt) > 4000: txt = txt[:4000] + "\\.\\.\\."
        await q.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN_V2)
    
    # Share
    elif d.startswith("sh_"):
        idx = int(d[3:])
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        if idx >= len(songs): return
        song = songs[idx]
        
        purl = song.get('perma_url', '')
        title = song.get('title') or song.get('song', 'Song')
        singers = song.get('singers', '')
        
        share_text = f"🎵 Check out this song!\n\n*{title}*\nby {singers}\n\n{purl}"
        await q.message.reply_text(share_text, parse_mode=ParseMode.MARKDOWN_V2)
    
    # Fav/Unfav
    elif d.startswith("f_"):
        idx = int(d[2:])
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        if idx >= len(songs): return
        if db.add_to_favorites(uid, songs[idx]):
            await q.answer("💖 Added to favorites!", show_alert=True)
            pg = (idx // SONGS_PER_PAGE) * SONGS_PER_PAGE
            try: await q.edit_message_reply_markup(reply_markup=kb.detail(idx, True, pg))
            except: pass
        else:
            await q.answer("Already in favorites!", show_alert=True)
    
    elif d.startswith("uf_"):
        idx = int(d[3:])
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        if idx >= len(songs): return
        sid = songs[idx].get('songid') or songs[idx].get('id', '')
        if db.remove_from_favorites(uid, sid):
            await q.answer("💔 Removed from favorites!", show_alert=True)
            pg = (idx // SONGS_PER_PAGE) * SONGS_PER_PAGE
            try: await q.edit_message_reply_markup(reply_markup=kb.detail(idx, False, pg))
            except: pass
    
    # Fav play
    elif d.startswith("fp_"):
        idx = int(d[3:])
        favs = db.user_favorites[uid]
        if idx >= len(favs): return
        song = favs[idx]
        db.user_searches[uid] = {'q': 'Favorites', 'songs': favs}
        await send_song_detail(q.message, c, uid, song, idx, 0)
    
    # History play
    elif d.startswith("hp_"):
        idx = int(d[3:])
        hist = db.user_history[uid]
        if idx >= len(hist): return
        song = hist[idx]
        db.user_searches[uid] = {'q': 'History', 'songs': hist}
        await send_song_detail(q.message, c, uid, song, idx, 0)
    
    # Clear favorites
    elif d == "cfav":
        db.user_favorites[uid] = []
        await q.answer("🗑️ Favorites cleared!", show_alert=True)
        await q.edit_message_text("💔 *Favorites cleared\\!*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
    
    # Clear history
    elif d == "chist":
        db.user_history[uid] = []
        await q.answer("🗑️ History cleared!", show_alert=True)
        await q.edit_message_text("📜 *History cleared\\!*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.main())
    
    # Create new playlist
    elif d == "newpl":
        await q.edit_message_text("📁 *Create Playlist*\n\nSend playlist name:", parse_mode=ParseMode.MARKDOWN_V2)
        db.user_stats[uid]['awaiting_playlist'] = True
    
    # Add to playlist
    elif d.startswith("addpl_"):
        idx = int(d[6:])
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        if idx >= len(songs): return
        
        pls = db.user_playlists[uid]
        if not pls:
            await q.answer("📁 Create a playlist first!", show_alert=True)
            return
        
        kb_pl = []
        for name in list(pls.keys())[:8]:
            kb_pl.append([InlineKeyboardButton(f"📁 {name}", callback_data=f"plsel_{idx}_{name}")])
        kb_pl.append([InlineKeyboardButton("🔙 Back", callback_data=f"s_{idx}")])
        
        await q.edit_message_text("📁 *Select Playlist*\n\nChoose where to add:", 
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup(kb_pl))
    
    # Playlist selection
    elif d.startswith("plsel_"):
        parts = d[6:].split('_', 1)
        idx = int(parts[0])
        pl_name = parts[1] if len(parts) > 1 else ""
        
        if uid not in db.user_searches: return
        songs = db.user_searches[uid]['songs']
        if idx >= len(songs): return
        
        if db.add_to_playlist(uid, pl_name, songs[idx]):
            await q.answer(f"✅ Added to {pl_name}!", show_alert=True)
        else:
            await q.answer("Already in playlist!", show_alert=True)
        
        pg = (idx // SONGS_PER_PAGE) * SONGS_PER_PAGE
        sid = songs[idx].get('songid') or songs[idx].get('id', '')
        fav = any((s.get('songid') or s.get('id', '')) == sid for s in db.user_favorites[uid])
        await q.edit_message_reply_markup(reply_markup=kb.detail(idx, fav, pg))
    
    # View playlist
    elif d.startswith("pl_"):
        pl_name = d[3:]
        if pl_name not in db.user_playlists[uid]:
            await q.answer("Playlist not found!", show_alert=True)
            return
        
        songs = db.user_playlists[uid][pl_name]
        if not songs:
            await q.edit_message_text(f"📁 *{esc(pl_name)}*\n\n📋 Empty playlist", 
                parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.playlists(uid))
            return
        
        db.user_searches[uid] = {'q': f'Playlist: {pl_name}', 'songs': songs, 'type': 'playlist'}
        await q.edit_message_text(f"📁 *{esc(pl_name)}*\n📊 {len(songs)} songs",
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb.collection(songs, 0, 'playlist'))

async def on_error(u: Update, c):
    logger.error(f"Error: {c.error}")

async def post_init(app):
    await app.bot.set_my_commands([
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("menu", "🎵 Main menu"),
        BotCommand("favorites", "💖 Your favorites"),
        BotCommand("history", "📜 Listening history"),
        BotCommand("stats", "📊 Your statistics"),
        BotCommand("settings", "⚙️ Bot settings"),
        BotCommand("help", "❓ Help guide"),
    ])
    
    if os.environ.get('RENDER_EXTERNAL_URL'):
        webhook_url = f"{os.environ.get('RENDER_EXTERNAL_URL', '')}/{BOT_TOKEN}"
        try:
            await app.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
            logger.info(f"✅ Webhook set successfully: {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")
    else:
        logger.info("ℹ️ Skipping webhook setup (Polling mode)")
        try:
            await app.bot.delete_webhook(drop_pending_updates=True)
        except:
            pass

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ BOT_TOKEN missing!")
        return

    try:
        logger.info("🔄 Force deleting webhook to ensure polling works...")
        requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=True")
        logger.info("✅ Webhook deleted successfully")
    except Exception as e:
        logger.error(f"⚠️ Failed to delete webhook: {e}")

    PORT = int(os.environ.get("PORT", 8000))
    RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
    
    logger.info(f"🚀 Starting bot on port {PORT}")
    logger.info("🎼 NEW: Lyrics search enabled!")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("favorites", cmd_fav))
    app.add_handler(CommandHandler("history", cmd_hist))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_error_handler(on_error)

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("✅ Flask keep-alive server started")

    if RENDER_URL:
        logger.info(f"🔗 Render URL detected: {RENDER_URL}")
        logger.info("ℹ️ Running in POLLING mode with Flask keep-alive")
    else:
        logger.info("ℹ️ Running in Local POLLING mode")

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
