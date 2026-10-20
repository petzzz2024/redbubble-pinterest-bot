#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redbubble bot v2

Tok:
  1. Izbor životinja: Gemini + Google Search grounding (šta se traži sada) + Google autosuggest
     (stvarne pretrage) kao procena potražnje + zaštita od ponavljanja.
  2. Za svaku životinju: istraživanje ključnih reči (autosuggest), pa 5 dizajna, svaki za drugog kupca
     (poklon za mamu, hobi, zanimanje, praznik, humor...). Naslov / opis / tagovi se proveravaju i
     popravljaju u KODU (limiti, duplikati, zaštićeni pojmovi, prazni tagovi), ne samo u promptu.
  3. Slika: Fal.ai Z-Image Turbo -> provera teksta na traci (Gemini vision) -> BiRefNet -> glatke ivice -> 8000x8000.
  4. Izlaz: u folderu svake životinje je <životinja>_podaci.txt (Naslov / Opis / Tagovi za svaki dizajn,
     spremno za copy-paste u Redbubble) + jedan zajednički podaci_<datum>.txt; sve ide na Telegram
     (txt poseban, slike u ZIP paketima). Slike se zovu po naslovu (npr. "Pug Pizza Lover.png"). Nema CSV-a.

Opcije (environment promenljive, sve su opcione):
  ANIMALS_PER_RUN=5   DESIGNS_PER_ANIMAL=5   IMAGE_ATTEMPTS=3   TARGET_SIZE=8000
  METADATA_ONLY=1        -> samo ideje/naslovi/tagovi, bez slika i Telegrama (jeftin test)
  VERIFY_IMAGE_TEXT=0    -> isključi proveru teksta na slici
  USE_SEARCH_GROUNDING=0 -> isključi Google Search u Gemini-ju
  USE_AUTOSUGGEST=0      -> isključi Google autosuggest
"""
import os
import re
import sys
import json
import time
import random
import zipfile
import difflib
import datetime
import unicodedata
from io import BytesIO

import requests
from PIL import Image, ImageFilter
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# KONFIGURACIJA
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


ANIMALS_PER_RUN = env_int("ANIMALS_PER_RUN", 5)
DESIGNS_PER_ANIMAL = env_int("DESIGNS_PER_ANIMAL", 5)
MIN_DESIGNS_PER_ANIMAL = min(3, DESIGNS_PER_ANIMAL)
IMAGE_ATTEMPTS = max(1, env_int("IMAGE_ATTEMPTS", 3))
TARGET_SIZE = env_int("TARGET_SIZE", 8000)
VERIFY_IMAGE_TEXT = os.getenv("VERIFY_IMAGE_TEXT", "1") != "0"
METADATA_ONLY = os.getenv("METADATA_ONLY", "0") == "1"
USE_SEARCH_GROUNDING = os.getenv("USE_SEARCH_GROUNDING", "1") != "0"
USE_AUTOSUGGEST = os.getenv("USE_AUTOSUGGEST", "1") != "0"

USED_FILE = "used_animals.txt"
HISTORY_FILE = "design_history.json"
BLOCKED_FILE = "blocked_terms.txt"      # opciono: dodatni zaštićeni pojmovi, jedan po liniji
OUTPUT_DIR = "output_images"

# Ograničenja polja na Redbubble-u (prema vodičima trećih strana; proveri u svom nalogu)
TITLE_MAX = 60
DESC_MAX = 500
TAGS_COUNT = 15
TAG_MAX_LEN = 30
MAX_ANIMAL_TAGS = 7          # najviše toliko tagova sme da sadrži samo ime životinje (ostalo: kupac, prilika, tema, stil)

AVAILABLE_MODELS = [
    'gemini-3.8-flash',
    'gemini-3.5-flash-lite',
    'gemini-3.1-flash-lite',
    'gemini-3.7-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash'
]

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# ---------------------------------------------------------------------------
# REČNICI I PRAVILA
# ---------------------------------------------------------------------------
# Cele reči (ne podstringovi: 'are' je u starom kodu odbijao 'hare'). Hvata i "razgovor" modela umesto imena životinje.
BANNED_ANIMAL_WORDS = {
    'forbidden', 'wait', 'waiting', 'none', 'nema', 'zabranjeno', 'animal', 'animals', 'unknown', 'here', 'are',
    'trending', 'example', 'species', 'na', 'null', 'other', 'various', 'result', 'results', 'list', 'note',
    'sure', 'okay', 'ok', 'sorry', 'cannot', 'can', 'will', 'please', 'following', 'below', 'above', 'based',
    'search', 'for', 'the', 'and', 'is', 'sources', 'source', 'json', 'array', 'item', 'items', 'name', 'type',
}

# Zaštićeni nazivi: ovo je mera opreza, a ne pravni savet. Dopuni preko blocked_terms.txt.
BLOCKED_TERMS = [
    # filmovi, crtani, igre
    "disney", "pixar", "marvel", "dc comics", "batman", "superman", "spiderman", "spider-man", "avengers",
    "star wars", "yoda", "baby yoda", "grogu", "mandalorian", "harry potter", "hogwarts", "pokemon", "pokémon",
    "pikachu", "nintendo", "mario", "zelda", "sonic the hedgehog", "sanrio", "hello kitty", "kuromi",
    "cinnamoroll", "my melody", "pusheen", "snoopy", "charlie brown", "garfield", "bluey", "peppa pig",
    "paw patrol", "minion", "minions", "mickey", "minnie", "winnie the pooh", "pooh", "tigger", "eeyore",
    "lion king", "simba", "nemo", "bambi", "dumbo", "totoro", "ghibli", "studio ghibli", "naruto",
    "dragon ball", "spongebob", "nickelodeon", "cartoon network", "looney tunes", "bugs bunny",
    "tom and jerry", "scooby doo", "sesame street", "muppets", "kung fu panda", "madagascar", "zootopia",
    "stranger things", "game of thrones", "squid game", "baby shark", "cocomelon", "wednesday addams",
    "fortnite", "minecraft", "roblox", "among us", "angry birds", "lego", "barbie", "hot wheels",
    # igračke i trend-brendovi koji se pojavljuju u pretragama
    "needoh", "nee doh", "nee-doh", "squishmallow", "squishmallows", "labubu", "stanley cup",
    # memovi i poznate životinje (prava na lik)
    "grumpy cat", "nyan cat", "keyboard cat", "doge", "cheems", "harambe", "moo deng",
    # brendovi
    "nike", "adidas", "gucci", "louis vuitton", "chanel", "the north face", "under armour", "starbucks",
    "coca cola", "coca-cola", "pepsi", "mcdonalds", "mcdonald's", "netflix", "hbo", "tesla",
    # sport i muzika
    "nfl", "nba", "mlb", "nhl", "fifa", "taylor swift", "beyonce", "blackpink", "bts",
]

# Pretrage koje nisu kupovne namere za majice/stikere (ne koristimo ih kao tagove)
NON_MERCH_WORDS = {
    "svg", "png", "pdf", "clipart", "clip", "wallpaper", "wallpapers", "coloring", "colouring", "drawing",
    "tattoo", "cake", "pattern", "crochet", "knitting", "amigurumi", "plush", "plushie", "stuffed", "toy",
    "toys", "free", "amazon", "etsy", "walmart", "target", "ebay", "near", "price", "prices", "for sale",
    "adopt", "adoption", "buy", "diy", "template", "templates", "vector", "emoji", "font", "keyboard",
    "recipe", "recipes", "facts", "habitat", "diet", "lifespan", "pet", "vet", "care", "meme", "memes",
    "video", "videos", "song", "movie", "game", "games", "app", "download", "stock", "photo", "photos",
    "image", "images", "picture", "pictures", "pics", "gif", "sound", "sounds", "noise", "noises",
    # druga značenja iste reči (iz pravog izlaza: poodle skirt, turkey tail mushroom, reindeer moss, turkey trot...)
    "meaning", "names", "name", "skirt", "skirts", "mushroom", "mushrooms", "shuttle", "trot", "vulture",
    "moss", "cuts",
}

# Fraza iz autosuggest-a se koristi samo ako je ostatak (posle imena životinje) SAMO ove reči: kupac/prilika/proizvod.
# Time otpadaju nevezane pretrage ("turkey run state park", "poodle skirt", "reindeer needoh").
_INTENT_RAW = """
gift gifts idea ideas for him her his hers men man women woman kid kids boy boys girl girls adult adults teen teens
mom moms mother mothers dad dads father fathers mama papa mommy daddy grandma grandpa grandmother grandfather aunt
uncle sister brother wife husband girlfriend boyfriend friend friends teacher teachers nurse nurses coworker
coworkers boss lover lovers love fan fans funny cute adorable kawaii shirt shirts tshirt t tee tees sticker stickers
hoodie hoodies mug mugs christmas birthday halloween thanksgiving valentine valentines easter anniversary graduation
holiday holidays present presents themed theme style aesthetic vibe vibes quote quotes saying sayings humor joke
jokes pun puns and with the a an of to in on s clothing apparel outfit outfits decor owner owners parent parents
people person lady ladies stuff things dog dogs cat cats puppy puppies kitten kittens bird birds animal animals
wildlife farm secret santa stocking stuffer stuffers party college student students work office day baby babies
"""

GENERIC_TAGS = {
    "art", "design", "cool", "new", "awesome", "trending", "best", "sale", "nice", "great", "good", "amazing",
    "popular", "redbubble", "trend", "viral", "hot", "top", "unique", "original", "artwork", "illustration",
    "graphic", "graphics", "image", "picture", "gift", "gifts", "present", "shirt", "tshirt", "t-shirt",
}

TITLE_BANNED_RE = re.compile(
    r"(?i)\b(stickers?|designs?|t-?shirts?|tshirts?|shirts?|hoodies?|posters?|redbubble)\b")

# Druga značenja reči iz pravog izlaza (poodle skirt, turkey tail mushroom, reindeer moss, turkey trot, llama vs alpaca...)
TITLE_OFFTOPIC_RE = re.compile(r"(?i)\b(skirts?|mushrooms?|shuttle|trot|vultures?|moss|meaning|state park|vs\.?|versus)\b")

CLAIM_RE = re.compile(
    r"(?i)(free shipping|best[- ]?sell|limited (time|edition)|guarantee|\d+\s?% off|\bsale\b|\$\s?\d|"
    r"\bdiscount|premium quality|high[- ]quality|100% cotton|ships? (in|within)|fast delivery|"
    r"order now|buy now|click)")

ANIMAL_COLOR_WORDS = {
    "red", "black", "blue", "white", "green", "grey", "gray", "brown", "little", "giant", "common", "great",
    "lesser", "greater", "golden", "yellow", "orange", "pink", "purple", "spotted", "striped", "american",
    "african", "asian", "european", "arctic", "wild", "baby", "mini", "miniature", "toy"
}

# Rezervni spisak ako Gemini potpuno zakaže (bot nikad ne staje zbog toga)
FALLBACK_ANIMALS = [
    "capybara", "red panda", "axolotl", "sea otter", "highland cow", "sloth", "hedgehog", "frog", "owl", "fox",
    "raccoon", "penguin", "llama", "alpaca", "corgi", "french bulldog", "pug", "sphynx cat", "black cat",
    "maine coon", "hamster", "bunny", "duck", "chicken", "goat", "giraffe", "koala", "quokka", "platypus",
    "wolf", "bear", "moose", "bat", "manatee", "harbor seal", "narwhal", "jellyfish", "octopus", "turtle",
    "gecko", "bearded dragon", "chameleon", "ferret", "guinea pig", "shiba inu", "dachshund", "golden retriever",
    "husky", "border collie", "bernese mountain dog", "pigeon", "crow", "flamingo", "toucan", "puffin",
    "hummingbird", "bee", "butterfly", "moth", "ladybug", "snail", "sheep", "horse", "donkey", "deer",
    "squirrel", "otter", "badger", "mole", "hippo", "pygmy hippo", "tapir", "pangolin", "armadillo",
    "meerkat", "lemur", "red fox", "arctic fox", "snow leopard", "tiger", "lion", "elephant", "zebra",
]

# Životinje čija je prirodna boja ružičasta/magenta: pozadina za uklanjanje ide u plavu (word-boundary: "pig" != "pigeon")
PINK_ANIMAL_RE = re.compile(r"\b(flamingos?|pigs?|piglets?|axolotls?|spoonbills?|pink fairy armadillos?)\b", re.I)

# ---------------------------------------------------------------------------
# UGLOVI (kome je dizajn namenjen) I SEZONE
# Svaki dizajn iste životinje dobija drugi ugao -> drugačija pretraga, drugačiji kupac, bez kanibalizacije.
# ---------------------------------------------------------------------------
ANGLES = {
    "funny-relatable": "a relatable everyday joke (coffee, naps, Mondays, snacks, procrastination, social battery) told through this animal's real traits",
    "sarcastic": "dry, sarcastic or deadpan humor with a grumpy or unimpressed pose (never offensive, no politics, no profanity)",
    "wholesome-affirmation": "a warm positive message (be kind, you've got this, soft but strong) that works as a comfort or encouragement gift",
    "gift-for-person": "a gift design for ONE specific buyer identity: {animal} mom, dad, grandma, aunt, teacher, nurse, best friend or 'proud {animal} person'. Make that identity part of the title keyword",
    "hobby-lifestyle": "the animal doing a popular hobby (gaming, reading, gardening, hiking, camping, baking, yoga, cycling, fishing, coding) so fans of that hobby find it",
    "work-life": "the animal in a recognisable job (nurse, teacher, chef, farmer, firefighter, mechanic, barista, librarian) with a job-related pun",
    "introvert-selfcare": "introvert, self-care and cozy-night-in humor (recharging, cancelled plans, anxious but trying)",
    "cozy-cottagecore": "cozy cottagecore / nature aesthetic: mushrooms, flowers, tea, moon, books, plants; gentle text",
    "foodie": "the animal with a favourite food (pizza, tacos, ramen, donuts, coffee, bubble tea, sushi) and a snack-themed pun",
    "nerdy-bookish": "nerdy, science or bookish humor (reading, space, chemistry, math, gaming)",
    "fitness-sports": "gym, running, yoga or team-sport energy with a motivational or funny line",
    "music-chill": "music, headphones and chill-vibes energy",
}

# (id, opis, početak (mesec, dan), kraj). Objavljuj 6-10 nedelja ranije jer indeksiranje traje.
SEASONS = [
    ("halloween", "Halloween (spooky-cute: pumpkins, bats, witch hats)", (8, 15), (10, 5)),
    ("thanksgiving", "Thanksgiving / autumn (pumpkin pie, leaves, gratitude)", (9, 10), (10, 20)),
    ("christmas", "Christmas / winter holidays (santa hats, cozy sweaters, candy canes, wrapped gifts)", (9, 15), (12, 5)),
    ("valentines", "Valentine's Day (hearts, love, friendship, anti-valentine humor)", (12, 15), (1, 25)),
    ("spring-easter", "Spring / Easter (flowers, bunny ears, eggs)", (2, 10), (3, 25)),
    ("mothers-day", "Mother's Day (gift for mom, flowers, hugs)", (3, 15), (4, 25)),
    ("fathers-day", "Father's Day (gift for dad, grill, fishing, dad jokes)", (4, 25), (5, 31)),
    ("summer", "Summer / vacation (sunglasses, ice cream, beach)", (3, 25), (5, 31)),
    ("back-to-school", "Back to school (backpacks, books, pencils)", (6, 10), (7, 25)),
]

SEASON_TAGS = {
    "halloween": ["halloween", "halloween gift", "spooky season", "autumn"],
    "thanksgiving": ["thanksgiving", "fall", "autumn", "grateful"],
    "christmas": ["christmas gift", "holiday gift", "christmas", "stocking stuffer", "winter"],
    "valentines": ["valentines day gift", "valentines day", "love", "galentines"],
    "spring-easter": ["easter gift", "spring", "easter"],
    "mothers-day": ["mothers day gift", "gift for mom", "mothers day"],
    "fathers-day": ["fathers day gift", "gift for dad", "fathers day"],
    "summer": ["summer", "vacation", "beach"],
    "back-to-school": ["back to school", "student gift", "teacher gift"],
}

ANIMAL_TAG_TEMPLATES = ["{a} lover", "{a} gift idea", "cute {a}", "funny {a}", "{a} mom", "{a} dad", "{a} lovers gift"]
PADDING_TAGS = [
    "animal lover", "animal lover gift", "gift for animal lovers", "funny animal", "cute animal", "cartoon animal",
    "kawaii", "cute cartoon", "wildlife", "nature lover", "birthday gift", "gift for her", "gift for him",
    "best friend gift", "funny gift", "novelty gift", "gift idea"
]


# ---------------------------------------------------------------------------
# POMOĆNE FUNKCIJE
# ---------------------------------------------------------------------------
def redact(text):
    """Skida tajne iz poruka o grešci (requests ume da ubaci Telegram token u URL u poruci)."""
    text = str(text)
    for secret in (GEMINI_API_KEY, FAL_KEY, TELEGRAM_BOT_TOKEN):
        if secret:
            text = text.replace(secret, "***")
    return text


def safe_name(text, limit=80):
    """Ime fajla/foldera kao u starom botu: obične reči sa razmacima ("Pug Pizza Lover.png"), bez brojeva i donjih crta."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().replace("'", "")
    text = re.sub(r"[^A-Za-z0-9 \-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] if " " in text[:limit] else text[:limit]
    return text.strip(" -") or "design"


def unique_name(folder_path, base, ext, taken):
    """Ako dva dizajna dobiju isto ime, drugi postaje 'Ime 2.png' (ne prepisuje prvi)."""
    name, n = f"{base}{ext}", 2
    while name.lower() in taken or os.path.exists(os.path.join(folder_path, name)):
        name = f"{base} {n}{ext}"
        n += 1
    taken.add(name.lower())
    return name


def singular(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and re.search(r"(sses|shes|ches|xes|zes)$", w):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def tokens(text):
    return [singular(w) for w in re.findall(r"[a-z0-9]+", str(text).lower())]


def phrase_key(text):
    """'cute capybara' == 'capybaras cute': ključ za otkrivanje duplikata."""
    return " ".join(sorted(tokens(text)))


def mentions_animal(text, animal):
    core = set(tokens(animal)) - ANIMAL_COLOR_WORDS or set(tokens(animal))
    return bool(core & set(tokens(text)))


def canon(text):
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())


def in_window(today, start, end):
    s = datetime.date(today.year, start[0], start[1])
    e = datetime.date(today.year, end[0], end[1])
    if s <= e:
        return s <= today <= e
    return today >= s or today <= e


def active_seasons(today):
    return [{"id": sid, "brief": brief} for sid, brief, s, e in SEASONS if in_window(today, s, e)]


def load_blocked_terms():
    terms = list(BLOCKED_TERMS)
    if os.path.exists(BLOCKED_FILE):
        try:
            with open(BLOCKED_FILE, "r", encoding="utf-8") as f:
                terms += [l.strip().lower() for l in f if l.strip() and not l.startswith("#")]
        except OSError:
            pass
    terms = sorted(set(t.lower() for t in terms), key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(t) for t in terms) + r")(?![a-z0-9])", re.I)


BLOCKED_RE = load_blocked_terms()
INTENT_WORDS = {singular(w) for w in _INTENT_RAW.split()}     # isti oblik (jednina) kao tokens(): "christmas" -> "christma" na obe strane


def find_blocked(text):
    return sorted({m.group(1).lower() for m in BLOCKED_RE.finditer(str(text))})


def smart_title(text):
    return " ".join(w[:1].upper() + w[1:] if w.islower() else w for w in text.split())


def extract_json(text):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text).strip(), flags=re.I).strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    for opener, closer in (("[", "]"), ("{", "}")):
        s, e = t.find(opener), t.rfind(closer)
        if s != -1 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except ValueError:
                continue
    raise ValueError("Nema validnog JSON-a u odgovoru")


# ---------------------------------------------------------------------------
# HTTP SA PONAVLJANJEM (stari kod nije imao timeout ni retry)
# ---------------------------------------------------------------------------
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def http_request(method, url, retries=3, backoff=4, timeout=120, **kwargs):
    last = "nepoznato"
    for attempt in range(1, retries + 1):
        try:
            r = requests.request(method, url, timeout=timeout, **kwargs)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}: {redact(r.text)[:200]}"
            if r.status_code not in RETRY_STATUS:
                break
        except requests.exceptions.RequestException as e:
            last = redact(e)
        if attempt < retries:
            time.sleep(backoff * attempt)
    raise RuntimeError(f"{method} {redact(url)[:80]} nije uspeo: {last}")


# ---------------------------------------------------------------------------
# GEMINI
# ---------------------------------------------------------------------------
_client = None


def get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("Nedostaje GEMINI_API_KEY u GitHub Secrets!")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def gemini(prompt, json_mode=False, grounded=False, image=None, validator=None, label="gemini"):
    """Prolazi kroz modele dok jedan ne vrati odgovor koji prođe validator."""
    client = get_client()
    contents = prompt
    if image is not None:
        data, mime = image
        contents = [types.Part.from_bytes(data=data, mime_type=mime), prompt]

    cfg = {}
    if grounded:
        cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    elif json_mode:
        cfg["response_mime_type"] = "application/json"
    config = types.GenerateContentConfig(**cfg) if cfg else None

    last_err = None
    for model in AVAILABLE_MODELS:
        try:
            kwargs = {"model": model, "contents": contents}
            if config is not None:
                kwargs["config"] = config
            resp = client.models.generate_content(**kwargs)
            text = (getattr(resp, "text", None) or "").strip()
            if not text:
                raise ValueError("prazan odgovor")
            if validator is not None and not validator(text):
                raise ValueError("odgovor ne prolazi proveru oblika")
            return text
        except Exception as e:
            last_err = e
            print(f"    [!] {label}: model {model} nije uspeo ({redact(e)[:150]}). Sledeći...")
            time.sleep(2)
    raise RuntimeError(f"Svi Gemini modeli su otkazali ({label}): {redact(last_err)[:200]}")


# ---------------------------------------------------------------------------
# TRAJNO ČUVANJE (snima se posle SVAKE životinje, ne tek na kraju)
# ---------------------------------------------------------------------------
def load_used_animals(filename=USED_FILE):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    return []


def save_used_animals(animals, filename=USED_FILE):
    with open(filename, "w", encoding="utf-8") as f:
        for animal in sorted(set(animals)):
            if animal:
                f.write(f"{animal}\n")


def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("animals", {})
                data.setdefault("failed", {})
                return data
    except (OSError, ValueError):
        pass
    return {"animals": {}, "failed": {}}


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# 1) IZBOR ŽIVOTINJA
# ---------------------------------------------------------------------------
def valid_animal(name):
    name = re.sub(r"[^a-z\s-]", " ", str(name).lower())
    name = re.sub(r"\s+", " ", name).strip(" -")
    if not (2 <= len(name) <= 24) or len(name.split()) > 3 or any(len(w) < 2 for w in name.split()):
        return None
    if set(name.split()) & BANNED_ANIMAL_WORDS:      # cele reči (stari kod: 'are' je odbijao 'hare')
        return None
    if find_blocked(name):
        return None
    return name


def parse_animal_candidates(text):
    data = extract_json(text)
    if isinstance(data, dict):
        for key in ("animals", "candidates", "items", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError("očekivan je JSON niz")
    out = []
    for item in data:
        if isinstance(item, str):
            out.append({"animal": item, "reason": "", "kind": ""})
        elif isinstance(item, dict):
            name = item.get("animal") or item.get("name")
            if name:
                out.append({"animal": str(name), "reason": str(item.get("reason", "")), "kind": str(item.get("kind", ""))})
    return out


def animal_prompt(count, forbidden, today, grounded):
    forbidden_str = ", ".join(forbidden[-300:]) if forbidden else "none"
    research = ("Use Google Search to find what is selling and trending RIGHT NOW. " if grounded
                else "Use your knowledge of print-on-demand demand. ")
    return f"""You are a print-on-demand market researcher for Redbubble (stickers, t-shirts, gifts). Today is {today.strftime('%B %d, %Y')}.
{research}Suggest {count} animals that buyers actively search for as stickers, t-shirts and gifts.
Mix: about 40% currently viral or trending animals (last 1-2 months: memes, social media, news, popular culture),
40% evergreen bestsellers with steady demand (popular dog and cat breeds, cute wild animals), and 20% animals that fit the
upcoming season. Prefer animals that are visually distinctive and easy to draw as a cute cartoon mascot.

RULES
- Real species or dog/cat breeds only. NO fictional characters, brands, franchises, named individual animals or memes.
- Common English name, 1-3 words, lowercase (e.g. "capybara", "red panda", "bernese mountain dog").
- STRICTLY EXCLUDE these animals (already used): [{forbidden_str}]
- Return ONLY a JSON array, no other text. Each item: {{"animal": "...", "reason": "max 12 words", "kind": "trending" or "evergreen" or "seasonal"}}"""


def google_suggest(query):
    """Google autosuggest: stvarni upiti koje ljudi ukucavaju. Vraća [] ako je nedostupan."""
    try:
        r = requests.request("GET", "https://suggestqueries.google.com/complete/search",
                             params={"client": "firefox", "hl": "en", "gl": "us", "q": query},
                             headers={"User-Agent": UA}, timeout=8)
        if r.status_code != 200:
            return []
        data = r.json()
        return [s for s in data[1] if isinstance(s, str)] if isinstance(data, list) and len(data) > 1 else []
    except Exception:
        return []


def demand_score(animal):
    if not USE_AUTOSUGGEST:
        return None
    total = 0
    for seed in ("gift", "t shirt", "sticker"):
        total += len(google_suggest(f"{animal} {seed}"))
        time.sleep(0.3)
    return total


def pick_animals(used, history, today, count):
    used_keys = {phrase_key(a) for a in used}
    failed = history.get("failed", {})
    seen = set(used_keys)
    candidates = []

    def consider(items):
        for it in items:
            name = valid_animal(it["animal"])
            if not name:
                continue
            key = phrase_key(name)
            if key in seen or failed.get(name, 0) >= 3:
                continue
            seen.add(key)
            candidates.append({"animal": name, "reason": it.get("reason", ""), "kind": it.get("kind", ""), "score": None})

    want = max(count * 3, 12)
    for round_no in range(3):
        if len(candidates) >= want:
            break
        forbidden = list(used) + [c["animal"] for c in candidates]
        modes = []
        if USE_SEARCH_GROUNDING and round_no == 0:
            modes.append(True)
        modes.append(False)
        for grounded in modes:
            try:
                txt = gemini(animal_prompt(want, forbidden, today, grounded), json_mode=not grounded, grounded=grounded,
                             validator=lambda t: bool(parse_animal_candidates(t)), label="životinje")
                before = len(candidates)
                consider(parse_animal_candidates(txt))
                print(f"  -> Gemini ({'Google Search' if grounded else 'bez pretrage'}): {len(candidates) - before} novih kandidata")
                if len(candidates) > before:
                    break
            except Exception as e:
                print(f"  -> Predlog životinja nije uspeo ({'grounded' if grounded else 'običan'}): {redact(e)[:150]}")

    if candidates:
        pool = candidates[:want]
        if USE_AUTOSUGGEST:
            print("  -> Procenjujem potražnju preko Google autosuggest-a...")
            for c in pool:
                c["score"] = demand_score(c["animal"])
            if any(c["score"] for c in pool):
                order = {id(c): i for i, c in enumerate(pool)}
                pool.sort(key=lambda c: (-(c["score"] or 0), order[id(c)]))
        chosen = pool[:count]
    else:
        chosen = []

    if len(chosen) < count:
        print("  -> Dopunjavam iz rezervnog spiska životinja.")
        rest = [a for a in FALLBACK_ANIMALS if phrase_key(a) not in seen and failed.get(a, 0) < 3]
        random.shuffle(rest)
        for a in rest[:count - len(chosen)]:
            chosen.append({"animal": a, "reason": "rezervni spisak", "kind": "evergreen", "score": None})

    for c in chosen:
        score = "" if c["score"] is None else f" | potražnja: {c['score']}"
        print(f"     • {c['animal']} [{c['kind'] or '?'}]{score} {('- ' + c['reason']) if c['reason'] else ''}")
    return [c["animal"] for c in chosen]


# ---------------------------------------------------------------------------
# 2) ISTRAŽIVANJE KLJUČNIH REČI
# ---------------------------------------------------------------------------
def usable_keyword(phrase, animal):
    k = re.sub(r"[^a-z0-9\s'-]", " ", phrase.lower())
    k = re.sub(r"\s+", " ", k).strip()
    n = len(k.split())
    if n < 2 or n > 5 or len(k) > TAG_MAX_LEN + 10:
        return None
    if not mentions_animal(k, animal) or set(k.split()) & NON_MERCH_WORDS or find_blocked(k):
        return None
    if not (set(tokens(k)) - set(tokens(animal))) <= INTENT_WORDS:      # nešto što nije kupac/prilika/proizvod
        return None
    return k


def research_keywords(animal):
    """Stvarne pretrage vezane za životinju (Google autosuggest). Vraća listu fraza."""
    if not USE_AUTOSUGGEST:
        return []
    seeds = [f"{animal} ", f"{animal} gift", f"{animal} gifts for", f"{animal} lover", f"{animal} mom",
             f"{animal} dad", f"funny {animal}", f"cute {animal}", f"{animal} shirt", f"{animal} sticker",
             f"{animal} lovers", f"{animal} themed"]
    found, seen = [], set()
    for seed in seeds:
        for s in google_suggest(seed):
            k = usable_keyword(s, animal)
            if k and phrase_key(k) not in seen and phrase_key(k) != phrase_key(animal):
                seen.add(phrase_key(k))
                found.append(k)
        time.sleep(0.3)
    print(f"  -> Pronađeno {len(found)} stvarnih fraza pretrage za '{animal}'.")
    return found[:40]


# ---------------------------------------------------------------------------
# 3) DIZAJNI: PROMPT, ČIŠĆENJE I VALIDACIJA
# ---------------------------------------------------------------------------
def choose_angles(today, n):
    seasons = active_seasons(today)
    chosen = [{"id": random.choice(["funny-relatable", "sarcastic"])}, {"id": "gift-for-person"}]
    if seasons:
        s = random.choice(seasons)
        chosen.append({"id": "season-" + s["id"], "brief": f"a seasonal design for {s['brief']}; the holiday must be obvious from the scene and the title", "season": s["id"]})
    else:
        chosen.append({"id": "wholesome-affirmation"})
    taken = {c["id"] for c in chosen}
    rest = [a for a in ANGLES if a not in taken]
    random.shuffle(rest)
    while len(chosen) < n and rest:
        chosen.append({"id": rest.pop()})
    for c in chosen:
        c.setdefault("brief", ANGLES.get(c["id"], ""))
    return chosen[:n]


def build_design_prompt(animal, keywords, angles, avoid_titles, avoid_texts, feedback, today):
    kw_block = "\n".join(f"- {k}" for k in keywords[:30]) or "- (live data unavailable; rely on how real buyers search)"
    angle_lines = "\n".join(f"{i}. {a['id']}: {a['brief'].replace('{animal}', animal)}" for i, a in enumerate(angles, 1))
    titles_block = "\n".join(f"- {t}" for t in avoid_titles[-40:]) or "- (none)"
    texts_block = ", ".join(avoid_texts[-100:]) or "(none)"
    fix_block = ""
    if feedback:
        fix_block = "\nFIX THESE PROBLEMS FROM YOUR PREVIOUS ANSWER (do not repeat them):\n" + "\n".join(f"- {f}" for f in feedback[:12]) + "\n"
    n = len(angles)
    return f"""You are an experienced Redbubble seller and print-on-demand SEO specialist. Today is {today.strftime('%B %d, %Y')}.

ANIMAL: {animal}

REAL GOOGLE SEARCHES for buying or giving items with this animal (already filtered for shopping intent). Use them for keywords when they fit the artwork. If a search is about anything other than the artwork's audience, occasion or theme (a place, event, food, plant, brand, product, definition or another meaning of the word), IGNORE it:
{kw_block}

TASK: create {n} COMPLETELY DIFFERENT sticker / t-shirt artworks. Each artwork must follow its own ANGLE and must be aimed at a different buyer and a different search:
ANGLES:
{angle_lines}

Think like a buyer, not like an artist: shoppers search "capybara gifts for mom", not "cool capybara art".

ALREADY USED, do NOT repeat or paraphrase these titles:
{titles_block}
ALREADY USED banner phrases (a new banner phrase must NOT repeat or closely resemble any of them): {texts_block}
{fix_block}
FIELDS FOR EVERY ARTWORK
- angle: copy the angle id exactly.
- primary_keyword: ONE phrase a buyer would type (2-4 words, lowercase, contains "{animal}"). Different for every artwork. It must be about THIS artwork's audience, occasion or theme. NEVER a place, event, plant, food, brand, product or definition (bad examples: "turkey trot", "poodle skirt", "reindeer moss", "llama vs alpaca").
- title: 3-6 words, max 55 characters. It must read like a natural product title written by a human (grammatical, NOT a chain of keywords) with the main keyword near the start. GOOD: "Sleepy Pug Nap Club Gift for Adults". BAD: "Pug Gifts For Adults Tired Nap Club". It names the ARTWORK, so NEVER use the words sticker, design, shirt, t-shirt, hoodie, poster or Redbubble. No quotation marks.
- description: 250-450 characters, 2-3 sentences that sound like a person, not a keyword list. Work the primary keyword in naturally (do NOT simply start the sentence with it). Say what the artwork shows (must match visual_scene) and name the species ("pug", "llama"), never just "animal" or "pup". Then say who it is for or which occasion it suits (gift idea). No prices, shipping, quality or sales claims, no URLs, no hashtags, no emojis.
- tags: JSON array of EXACTLY 15 distinct lowercase tags, 1-3 words, max 30 characters each:
    tag 1 = "{animal}"; then 3-4 phrases with the animal that buyers search (from the real searches above);
    3-4 buyer/occasion tags (e.g. "gift for mom", "animal lover gift", "birthday gift", "christmas gift");
    3-4 tags about the actual scene or phrase (hobby, food, mood, job);
    2 style tags (e.g. "cute cartoon", "kawaii");
    1-2 broad category tags (e.g. "wildlife", "funny animal").
  Only 6-7 tags may contain the animal's name. Every tag must describe THIS artwork or its buyer: never use a tag with another meaning (places, events, foods, other products, definitions, e.g. "poodle skirt", "turkey tail mushroom", "reindeer moss"). Never use filler tags (art, design, cool, new, awesome, trending, best, sale, gift) and never use brand, franchise, character, celebrity or meme names.
- visual_scene: max 25 words, English: the animal's pose, expression, outfit and props only. NO background, frame, banner or text. It must visibly match the angle and the banner phrase.
  COLOR RULE: if the animal wears clothes, a hat or glasses or holds a prop, state each item's color using ONLY ORANGE, YELLOW, RED, NAVY BLUE or WHITE (e.g. "wearing an orange t-shirt and sunglasses", "holding a red coffee mug"). Never leave clothing without a color. Never use the words magenta, pink, purple or fuchsia.
- text: the banner phrase, ENGLISH, UPPERCASE, 1-4 words, max 22 characters, letters/numbers/space/apostrophe/!/? only. Original wordplay, no famous quotes or brand slogans, no color instructions, no translations. Short words render best. It must be NEW: never reuse any phrase from the ALREADY USED list, never repeat a phrase inside your answer, and avoid the overused clichés NEED COFFEE FIRST, CURRENTLY UNPLUGGED, STRIDE WITH PRIDE, PIZZA MY HEART, MERRY AND FLUFFY.

Return ONLY a JSON array of exactly {n} objects with the keys: angle, primary_keyword, title, description, tags, visual_scene, text."""


def clean_title(raw, animal):
    t = re.sub(r"[\"“”`]", "", str(raw))
    t = TITLE_BANNED_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—:|,.;!")
    t = smart_title(t)
    if not t:
        t = f"{smart_title(animal)} Lover"
    if not mentions_animal(t, animal):
        t = f"{smart_title(animal)} {t}"
    return shorten(t, TITLE_MAX)


def shorten(text, limit):
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if text[limit] != " " and " " in cut:
        cut = cut[:cut.rfind(" ")]
    words = cut.split()
    while words and words[-1].lower() in {"and", "for", "the", "of", "with", "a", "an", "&", "to", "in", "on", "-", "your", "my"}:
        words.pop()
    return " ".join(words).strip(" -–—:|,.")


def fallback_description(animal, title, scene):
    scene = scene.strip().rstrip(".")
    scene = re.sub(rf"(?i)^(an?|the)?\s*{re.escape(animal)}s?\s+", "", scene)   # "a hare wearing..." -> "wearing..."
    scene = scene[:1].lower() + scene[1:] if scene else "looking adorable"
    return f"{title}. A cute cartoon {animal} {scene}. A fun gift idea for {animal} lovers, birthdays and everyday fans."


def clean_description(raw, animal, title, scene):
    d = re.sub(r"<[^>]+>", " ", str(raw))
    d = re.sub(r"https?://\S+|www\.\S+", " ", d)
    d = re.sub(r"#\w+", " ", d)
    d = re.sub(r"[\U00010000-\U0010ffff☀-➿]", "", d)
    d = re.sub(r"\s+", " ", d).strip()
    sentences = re.split(r"(?<=[.!?])\s+", d)
    d = " ".join(s for s in sentences if s and not CLAIM_RE.search(s) and "redbubble" not in s.lower()).strip()
    if len(d) > DESC_MAX:
        cut = d[:DESC_MAX]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind(".") if cut.endswith(".") else -1)
        d = cut[:end + 1] if end > 120 else cut[:cut.rfind(" ")].rstrip(" ,;:-") + "."
    if len(d) < 80 or not mentions_animal(d, animal):
        d = fallback_description(animal, title, scene)
    return d[:DESC_MAX]


def clean_banner_text(raw):
    t = unicodedata.normalize("NFKD", str(raw)).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9 '!?&-]", " ", t)
    return re.sub(r"\s+", " ", t).strip().upper()


def normalize_tag(tag, title_key=None):
    t = str(tag).lower().replace("#", " ")
    t = re.sub(r"[^a-z0-9 '-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -'")
    if not t or len(t) > TAG_MAX_LEN or len(t.split()) > 4 or len(t) < 3:
        return None
    if t in GENERIC_TAGS or set(t.split()) & (NON_MERCH_WORDS | {"vs", "versus"}) or find_blocked(t):
        return None
    if title_key and phrase_key(t) == title_key:
        return None
    return t


def clean_tags(raw, animal, title, keywords, season=None, allowed_extra=None):
    """Tačno 15 različitih, relevantnih tagova; prvi je životinja.
    Tag koji sadrži životinju mora da se oslanja SAMO na reči kupca/prilike/proizvoda (INTENT_WORDS) ili na reči iz
    ovog dizajna (scena, natpis, naslov): tako otpadaju 'pug skull', 'poodle skirt', 'llama vs alpaca', 'turkey run state park'."""
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, list):
        raw = []
    title_key = phrase_key(title)
    out, seen = [], set()
    animal_tags = 0
    animal_tokens = set(tokens(animal))
    allowed = INTENT_WORDS | set(allowed_extra or ())

    def add(tag, force=False):
        nonlocal animal_tags
        if len(out) >= TAGS_COUNT:
            return False
        t = animal if force else normalize_tag(tag, title_key)
        if not t:
            return False
        key = phrase_key(t)
        if key in seen:
            return False
        has_animal = mentions_animal(t, animal)
        if has_animal and not force:
            extra = set(tokens(t)) - animal_tokens
            if not extra <= allowed or extra == {"animal"}:       # nevezano značenje ili prazan tag ("llama animal")
                return False
        if has_animal and animal_tags >= MAX_ANIMAL_TAGS and not force:
            return False
        seen.add(key)
        out.append(t)
        animal_tags += 1 if has_animal else 0
        return True

    add(animal, force=True)
    for t in raw:
        add(t)
    pools = []
    if season:
        pools.append(SEASON_TAGS.get(season, []))
    pools.append(keywords)
    pools.append([tpl.format(a=animal) for tpl in ANIMAL_TAG_TEMPLATES])
    pools.append(PADDING_TAGS)
    for pool in pools:
        for t in pool:
            if len(out) >= TAGS_COUNT:
                break
            add(t)
    return out[:TAGS_COUNT]


def clean_design(raw, animal, ctx):
    """Vraća (design, []) ili (None, [problemi]). Sve što se može popraviti popravlja se u kodu."""
    if not isinstance(raw, dict):
        return None, ["objekat nije validan JSON objekat"]
    issues = []

    title = clean_title(raw.get("title", ""), animal)
    pk = re.sub(r"[^a-z0-9\s'-]", " ", str(raw.get("primary_keyword", "")).lower())
    pk = re.sub(r"\s+", " ", pk).strip()
    # Reči koje dizajn zaista prikazuje (scena + natpis). Naslov se NE računa: model ume da prepiše nevezanu pretragu u naslov
    # ("Turkey Run State Park ..."), pa bi tagovi onda "opravdali" isti promašaj.
    shown_tokens = set(tokens(str(raw.get("visual_scene", "")))) | set(tokens(raw.get("text", "")))
    if (not pk or not mentions_animal(pk, animal) or len(pk.split()) > 5
            or not (set(tokens(pk)) - set(tokens(animal))) <= (INTENT_WORDS | shown_tokens)):
        pk = " ".join(title.lower().split()[:4])          # ključna reč mora biti o OVOM dizajnu, ne o drugom značenju reči
    if len(title) < 20:
        # posle skidanja reči poput "sticker design" naslov ume da ostane kratak: dopuni ga ključnom rečju
        longer = clean_title(smart_title(pk), animal)
        if len(longer) > len(title):
            title = longer
    if len(title.split()) < 2 or len(title) < 12:
        issues.append(f"title '{title}' je prekratak")
    off = TITLE_OFFTOPIC_RE.search(title)
    if off:
        issues.append(f"title '{title}' sadrži '{off.group(1)}': to je drugo značenje reči ili poređenje, ne tema dizajna")
    if phrase_key(title) in ctx["titles"]:
        issues.append(f"title '{title}' je duplikat ili previše sličan postojećem")
    if phrase_key(pk) in ctx["keywords_used"]:
        alt = " ".join(title.lower().split()[:4])
        if phrase_key(alt) in ctx["keywords_used"]:
            issues.append(f"primary_keyword '{pk}' već koristi drugi dizajn")
        else:
            pk = alt

    scene = re.sub(r"\s+", " ", str(raw.get("visual_scene", ""))).strip().rstrip(".")
    scene = re.sub(r"(?i)\b(magenta|pink|fuchsia|purple)\b", "red", scene)
    if len(scene) < 20:
        issues.append("visual_scene je prekratak ili ga nema")

    text = clean_banner_text(raw.get("text", ""))
    words = text.split()
    if not (1 <= len(words) <= 4) or not (3 <= len(text) <= 24):
        issues.append(f"text '{text}' mora imati 1-4 reči i najviše 22-24 karaktera")
    elif canon(text) in ctx["texts"]:
        issues.append(f"text '{text}' je već korišćen")

    description = clean_description(raw.get("description", ""), animal, title, scene)
    tags = clean_tags(raw.get("tags", []), animal, title, ctx["keywords"], ctx.get("season_hint"), allowed_extra=shown_tokens)

    blocked = find_blocked(" ".join([title, description, text, scene, pk]))
    if blocked:
        issues.append(f"sadrži zaštićeni/brend pojam: {', '.join(blocked)}")

    if issues:
        return None, issues
    return {
        "title": title, "primary_keyword": pk, "description": description, "tags": tags,
        "visual_scene": scene, "text": text,
    }, []


def generate_designs(animal, keywords, today, history):
    wanted = choose_angles(today, DESIGNS_PER_ANIMAL)
    print(f"  -> Uglovi: {', '.join(a['id'] for a in wanted)}")
    avoid_titles = [d["title"] for rec in history["animals"].values() for d in rec.get("designs", [])]
    # Natpisi se tvrdo proveravaju protiv poslednjih 100 (isti spisak vidi i model u promptu): pravi izlaz je pokazao da
    # model sam ponavlja iste ("CURRENTLY UNPLUGGED" kod 4 životinje, "NEED COFFEE FIRST" kod 4), pa sam savet nije dovoljan.
    avoid_texts = [d["text"] for rec in history["animals"].values() for d in rec.get("designs", [])][-100:]
    ctx = {
        "titles": {phrase_key(t) for t in avoid_titles},
        "texts": {canon(t) for t in avoid_texts},
        "keywords_used": set(),
        "keywords": keywords,
    }
    accepted, feedback = [], []

    for attempt in range(1, 4):
        todo = [a for a in wanted if a["id"] not in {d["angle"] for d in accepted}]
        if not todo:
            break
        prompt = build_design_prompt(animal, keywords, todo, avoid_titles, avoid_texts, feedback, today)
        feedback = []
        try:
            txt = gemini(prompt, json_mode=True, label="dizajni",
                         validator=lambda t: isinstance(extract_json(t), (list, dict)))
            data = extract_json(txt)
            if isinstance(data, dict):
                data = next((v for v in data.values() if isinstance(v, list)), [data])
        except Exception as e:
            print(f"  -> Pokušaj {attempt}: generisanje dizajna nije uspelo: {redact(e)[:150]}")
            continue

        for i, raw in enumerate(data):
            if not isinstance(raw, dict):
                continue
            ids = {a["id"] for a in todo}
            echoed = raw.get("angle")
            angle = next((a for a in todo if a["id"] == echoed), None) or (todo[i] if i < len(todo) else None)
            if angle is None or angle["id"] in {d["angle"] for d in accepted}:
                continue
            ctx["season_hint"] = angle.get("season")
            design, issues = clean_design(raw, animal, ctx)
            if design is None:
                label = raw.get("title", "?")
                print(f"     ✗ '{str(label)[:50]}' odbijen: {'; '.join(issues)}")
                feedback.append(f"[{angle['id']}] {'; '.join(issues)}")
                continue
            design["angle"] = angle["id"]
            design["season"] = angle.get("season")
            accepted.append(design)
            ctx["titles"].add(phrase_key(design["title"]))
            ctx["texts"].add(canon(design["text"]))
            ctx["keywords_used"].add(phrase_key(design["primary_keyword"]))
            if len(accepted) >= DESIGNS_PER_ANIMAL:
                break
        print(f"  -> Pokušaj {attempt}: prihvaćeno {len(accepted)}/{DESIGNS_PER_ANIMAL} dizajna.")
        if len(accepted) >= DESIGNS_PER_ANIMAL:
            break

    order = {a["id"]: i for i, a in enumerate(wanted)}
    accepted.sort(key=lambda d: order.get(d["angle"], 99))
    return accepted


# ---------------------------------------------------------------------------
# 4) SLIKE
# ---------------------------------------------------------------------------
def fal_headers():
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}


def fal_text_to_image(design, animal):
    """Z-Image Turbo. Prompt ostaje tvoj, proveren: ravni vektor, crna kontura, traka sa tekstom na dnu."""
    if PINK_ANIMAL_RE.search(animal):
        chroma_bg = "PURE SOLID NEON BLUE (#0044FF) CHROMA KEY BACKGROUND"
        color_ban_negative = "blue, neon blue, cyan, teal,"
    else:
        chroma_bg = "PURE SOLID HOT MAGENTA (#FF00FF) CHROMA KEY BACKGROUND"
        color_ban_negative = "magenta, hot pink, pink, fuchsia, purple,"

    q = '"' if "'" in design["text"] else "'"        # natpis sa apostrofom (WORLD'S) ne sme da lomi navodnike u promptu
    image_prompt = (
        f"A standalone flat 2D vector mascot illustration graphic for a t-shirt design. "
        f"Subject: A cute 2D cartoon {animal} {design['visual_scene']}. "
        f"Style: Flat 2D vector art, clean crisp sharp edges, solid highly saturated vibrant colors. "
        f"Outline: The entire illustration, character, props, and banner MUST have a thick solid bold black outline enclosing every single shape. "
        f"Banner & Text: Positioned strictly at the very bottom below the animal, there is a horizontal ribbon banner or rectangle filled with solid bright yellow, orange, or red with a thick black outline, containing bold black typography reading exactly {q}{design['text']}{q}. "
        f"Composition: The artwork is completely isolated on a {chroma_bg}."
    )
    negative_prompt = (
        f"{color_ban_negative} white background, black background, green background, transparent background, gradient background, scenery, "
        f"sticker peel, die cut, drop shadow, 3d render, realistic, photograph, glow, blurry edges, brush strokes, "
        f"border, circular frame, watermark, messy edges, floating text outside banner, beige, pastels, washed out colors"
    )
    r = http_request("POST", "https://fal.run/fal-ai/z-image/turbo", headers=fal_headers(),
                     json={"prompt": image_prompt, "negative_prompt": negative_prompt, "image_size": "square_hd"})
    url = r.json()["images"][0]["url"]
    content = http_request("GET", url).content
    return url, content


def fal_remove_background(image_url):
    r = http_request("POST", "https://fal.run/fal-ai/birefnet", headers=fal_headers(), json={"image_url": image_url})
    transparent_url = r.json()["image"]["url"]
    return http_request("GET", transparent_url).content


def check_banner_text(img_bytes, expected):
    """Gemini vision proverava da li traka piše TAČNO traženi tekst. Greška API-ja = prolazi (ne blokira posao)."""
    try:
        fmt = (Image.open(BytesIO(img_bytes)).format or "PNG").upper()
        mime = "image/jpeg" if fmt in ("JPEG", "JPG") else "image/png"
        prompt = ('Look at this t-shirt/sticker illustration. Read the text on the ribbon banner exactly as written.\n'
                  'Return ONLY JSON: {"banner_text": "<exact text you read>", "extra_text": true/false (any other readable '
                  'text outside the banner), "major_defect": true/false (extra heads or limbs, merged bodies, cropped subject, '
                  'banner cut off, banner missing), "defect": "<short description or empty>"}')
        txt = gemini(prompt, json_mode=True, image=(img_bytes, mime),
                     validator=lambda t: isinstance(extract_json(t), dict), label="provera slike")
        data = extract_json(txt)
        read = canon(data.get("banner_text", ""))
        ratio = difflib.SequenceMatcher(None, read, canon(expected)).ratio()
        if ratio < 0.92 or data.get("extra_text") is True or data.get("major_defect") is True:
            return False, f"očekivano '{expected}', pročitano '{data.get('banner_text', '')}' {data.get('defect', '')}".strip()
        return True, ""
    except Exception as e:
        print(f"    (provera teksta preskočena: {redact(e)[:100]})")
        return True, ""


# LUT: alpha < 100 -> 0, > 155 -> 255, između glatki prelaz (antialiasing umesto tvrdog praga)
_ALPHA_LUT = [0] * 100 + [round((i - 100) * 255 / 55) for i in range(100, 155)] + [255] * 101


def to_canvas(transparent_bytes, size):
    """Transparentni PNG -> centrirano na platno size x size.
    Razlike u odnosu na staru verziju: ivice se glačaju PRILIKOM uvećanja (a ne tvrdim pragom na 1024px, što je
    posle 8x uvećanja davalo stepenaste ivice), a boja ispod providnih piksela se crni da nema magenta oboda."""
    img = Image.open(BytesIO(transparent_bytes)).convert("RGBA")
    r, g, b, a = img.split()
    a = a.filter(ImageFilter.MinFilter(3))                       # 1px erozija: skida ostatak pozadine
    # Boja se zadržava samo ispod (skoro) neprozirnih piksela; polu-providni obod postaje crn. Tvoj prompt traži crnu
    # konturu oko svega, pa je obod crn i ne vidi se, a nestaje magenta/plavi oreol koji ostane od hroma pozadine.
    black = Image.new("RGB", img.size, (0, 0, 0))
    rgb = Image.composite(Image.merge("RGB", (r, g, b)), black, a.point(lambda p: 255 if p >= 250 else 0))
    bbox = a.point(lambda p: 255 if p > 40 else 0).getbbox()
    if bbox:
        rgb, a = rgb.crop(bbox), a.crop(bbox)

    ratio = min(size / rgb.width, size / rgb.height)
    new_w, new_h = max(1, int(rgb.width * ratio)), max(1, int(rgb.height * ratio))
    rgb = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)
    a = a.resize((new_w, new_h), Image.Resampling.LANCZOS).point(_ALPHA_LUT)
    art = Image.merge("RGBA", (*rgb.split(), a))
    del rgb, a

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(art, ((size - new_w) // 2, (size - new_h) // 2))   # bez maske: alfa se kopira tačno
    return canvas


def make_design_image(design, animal, out_path):
    note = ""
    for attempt in range(1, IMAGE_ATTEMPTS + 1):
        try:
            url, original = fal_text_to_image(design, animal)
            ok, note = (True, "")
            if VERIFY_IMAGE_TEXT:
                ok, note = check_banner_text(original, design["text"])
                if not ok and attempt < IMAGE_ATTEMPTS:
                    print(f"    ⟳ Tekst/anatomija na slici nisu u redu ({note}). Pokušaj {attempt + 1}/{IMAGE_ATTEMPTS}...")
                    continue
            transparent = fal_remove_background(url)
            canvas = to_canvas(transparent, TARGET_SIZE)
            canvas.save(out_path, "PNG", compress_level=6)
            del canvas
            size_mb = os.path.getsize(out_path) / 1024 / 1024
            if size_mb > 45:
                print(f"    ⚠ Fajl je {size_mb:.0f} MB; Telegram limit je 50 MB.")
            return {"needs_review": not ok, "review_note": note}
        except Exception as e:
            print(f"    ✗ Slika, pokušaj {attempt}/{IMAGE_ATTEMPTS}: {redact(e)[:200]}")
            time.sleep(4 * attempt)
    raise RuntimeError("slika nije uspela ni posle svih pokušaja")


# ---------------------------------------------------------------------------
# 5) IZLAZ: LISTING FAJLOVI
# ---------------------------------------------------------------------------
def format_design_block(index, it):
    """Isti oblik kao u starom botu, da se naslov / opis / tagovi lako kopiraju u Redbubble."""
    lines = [f"--- DIZAJN {index} ---"]
    if it.get("needs_review"):
        lines.append(f"!!! PROVERI SLIKU PRE UPLOADA: {it.get('review_note', '')}".rstrip())
    lines += [
        f"Naslov: {it['title']}",
        f"Opis: {it['description']}",
        f"Tagovi: {', '.join(it['tags'])}",
        f"Slika (Ime fajla): {it['file_name']}",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_listings(results, today):
    """Za svaku životinju: <životinja>_podaci.txt u NJENOM folderu + jedan zajednički podaci_<datum>.txt za Telegram.
    Bez CSV-a. Vraća ({folder: putanja}, putanja_zajedničkog_fajla)."""
    by_animal = {}
    for item in results:
        by_animal.setdefault(item["folder"], []).append(item)

    txt_paths, combined = {}, []
    for folder, items in by_animal.items():
        path = os.path.join(OUTPUT_DIR, folder, f"{folder}_podaci.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        blocks = [format_design_block(index, it) for index, it in enumerate(items, 1)]
        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(blocks))
        txt_paths[folder] = path
        combined.append(f"==================== {folder.upper()} ====================\n\n" + "".join(blocks))

    combined_path = f"podaci_{today.isoformat()}.txt"
    with open(combined_path, "w", encoding="utf-8") as f:
        f.write("\n".join(combined))
    return txt_paths, combined_path


# ---------------------------------------------------------------------------
# 6) TELEGRAM
# ---------------------------------------------------------------------------
def tg_url(method):
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def tg_send_message(text):
    try:
        requests.request("POST", tg_url("sendMessage"), data={"chat_id": TELEGRAM_CHAT_ID, "text": text[:4000]}, timeout=30)
    except Exception as e:
        print(f"Telegram poruka nije poslata: {redact(e)[:150]}")


def tg_send_document(path, caption, retries=3):
    for attempt in range(1, retries + 1):
        try:
            with open(path, "rb") as f:
                r = requests.request("POST", tg_url("sendDocument"), data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]},
                                     files={"document": f}, timeout=180)
            if r.status_code == 200:
                return True
            print(f"❌ Telegram {r.status_code}: {redact(r.text)[:200]}")
        except requests.exceptions.RequestException as e:
            print(f"⏳ Pokušaj {attempt} nije uspeo: {redact(e)[:150]}")
        time.sleep(5 * attempt)
    return False


def build_chunks(files_by_folder, max_bytes):
    """Pakuje po životinjama: u jedan ZIP idu cele životinje (ceo folder) dok staje u limit;
    tek ako jedna životinja sama prelazi limit, deli se na više ZIP-ova."""
    chunks, current, size = [], {}, 0
    for folder, files in files_by_folder.items():
        total = sum(os.path.getsize(local) for local, _ in files)
        if current and size + total > max_bytes:
            chunks.append(current)
            current, size = {}, 0
        for local, arc in files:
            fsize = os.path.getsize(local)
            if fsize > max_bytes:
                print(f"⚠ {arc} ima {fsize / 1024 / 1024:.0f} MB i ne može preko Telegrama (limit 50 MB); ostaje u {OUTPUT_DIR}/.")
                continue
            if current and size + fsize > max_bytes:
                chunks.append(current)
                current, size = {}, 0
            current[local] = arc
            size += fsize
    if current:
        chunks.append(current)
    return chunks


def send_telegram(files_by_folder, txt_paths, summary, combined_txt, today):
    """files_by_folder: {folder: [(putanja_slike, ime_u_zip-u), ...]}; txt_paths: {folder: putanja do *_podaci.txt};
    combined_txt: zajednički txt sa svim naslovima, opisima i tagovima (šalje se kao poseban fajl, pre ZIP-ova)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram podaci nedostaju u GitHub Secrets.")
        return
    chunks = build_chunks(files_by_folder, 48 * 1024 * 1024)

    tg_send_message(summary)
    ok_txt = tg_send_document(combined_txt, "📋 Naslovi, opisi i tagovi za sve dizajne (txt)")
    print(f"{'✅' if ok_txt else '🚨'} Telegram txt {'poslan' if ok_txt else 'NIJE poslan'}")
    today = today.isoformat()
    for i, chunk in enumerate(chunks, 1):
        zip_name = f"redbubble_{today}_deo_{i}.zip"
        with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
            for local, arc in chunk.items():
                z.write(local, arcname=arc)
            # svaki folder u ZIP-u dobija svoj *_podaci.txt (naslov, opis, tagovi), čak i kad je životinja podeljena na više ZIP-ova
            for folder in sorted({arc.split("/")[0] for arc in chunk.values()}):
                if folder in txt_paths:
                    z.write(txt_paths[folder], arcname=f"{folder}/{os.path.basename(txt_paths[folder])}")
        ok = tg_send_document(zip_name, f"🚀 Redbubble dizajni, deo {i}/{len(chunks)} ({TARGET_SIZE}x{TARGET_SIZE} px)")
        print(f"{'✅' if ok else '🚨'} Telegram paket {i}/{len(chunks)} {'poslan' if ok else 'NIJE poslan'}")


# ---------------------------------------------------------------------------
# GLAVNI TOK
# ---------------------------------------------------------------------------
def main():
    today = datetime.date.today()
    if not GEMINI_API_KEY:
        sys.exit("Nedostaje GEMINI_API_KEY u GitHub Secrets!")
    if not FAL_KEY and not METADATA_ONLY:
        sys.exit("Nedostaje FAL_KEY u GitHub Secrets!")

    used = load_used_animals()
    history = load_history()

    print("🤖 [FAZA 1] Biram životinje (trend + evergreen + stvarna potražnja)...")
    animals = pick_animals(used, history, today, ANIMALS_PER_RUN)
    print(f"🎯 Lista za danas: {', '.join(a.upper() for a in animals)}")

    results = []
    for i, animal in enumerate(animals, 1):
        print(f"\n--- Životinja {i}/{len(animals)}: {animal.upper()} ---")
        try:
            keywords = research_keywords(animal)
            designs = generate_designs(animal, keywords, today, history)
            if len(designs) < MIN_DESIGNS_PER_ANIMAL:
                raise RuntimeError(f"samo {len(designs)} validnih dizajna (minimum {MIN_DESIGNS_PER_ANIMAL})")

            folder = safe_name(animal)
            folder_path = os.path.join(OUTPUT_DIR, folder)
            os.makedirs(folder_path, exist_ok=True)
            made, taken_names = [], set()
            for j, d in enumerate(designs, 1):
                print(f"  -> Dizajn {j}/{len(designs)} [{d['angle']}]: {d['title']}  |  traka: {d['text']}")
                file_name = unique_name(folder_path, safe_name(d["title"]), ".png", taken_names)
                item = dict(d, animal=animal, folder=folder, file_name=file_name,
                            file_path=os.path.join(OUTPUT_DIR, folder, file_name), needs_review=False, review_note="")
                if METADATA_ONLY:
                    item["file_name"] = "(slika nije generisana: METADATA_ONLY)"
                else:
                    try:
                        item.update(make_design_image(d, animal, item["file_path"]))
                    except Exception as e:
                        print(f"  ✗ Dizajn preskočen: {redact(e)[:150]}")
                        continue
                    time.sleep(2)
                made.append(item)

            if len(made) >= MIN_DESIGNS_PER_ANIMAL:
                results.extend(made)
                if not METADATA_ONLY:        # METADATA_ONLY je suvi test: životinje se ne troše
                    used.append(animal)
                    save_used_animals(used)
                    history["animals"][animal] = {
                        "date": today.isoformat(),
                        "designs": [{"title": m["title"], "text": m["text"], "primary_keyword": m["primary_keyword"], "angle": m["angle"]} for m in made],
                    }
                    save_history(history)
            else:
                raise RuntimeError(f"uspelo samo {len(made)} slika")
        except Exception as e:
            print(f"❌ Greška na životinji {animal}: {redact(e)[:200]}")
            if not METADATA_ONLY:
                history["failed"][animal] = history["failed"].get(animal, 0) + 1
                save_history(history)
        time.sleep(5)

    if not results:
        sys.exit("Nijedan dizajn nije napravljen. Pogledaj greške iznad.")

    txt_paths, combined_txt = write_listings(results, today)
    review = [r for r in results if r.get("needs_review")]
    summary = (f"✅ Redbubble bot {today.isoformat()}: {len(results)} dizajna, {len(txt_paths)} životinja "
               f"({', '.join(txt_paths)}).\n"
               + (f"⚠ {len(review)} slika za ručnu proveru (u *_podaci.txt piše !!! PROVERI SLIKU).\n" if review else "")
               + "U folderu svake životinje je <životinja>_podaci.txt sa naslovom, opisom i tagovima za svaki dizajn.")
    print("\n" + summary)

    if METADATA_ONLY:
        for it in results:
            print(f"\n[{it['animal']}] {it['title']}\n  tagovi: {', '.join(it['tags'])}\n  opis: {it['description']}\n  traka: {it['text']}")
        return

    files_by_folder = {}
    for it in results:
        files_by_folder.setdefault(it["folder"], []).append((it["file_path"], f"{it['folder']}/{it['file_name']}"))
    send_telegram(files_by_folder, txt_paths, summary, combined_txt, today)


if __name__ == "__main__":
    main()
