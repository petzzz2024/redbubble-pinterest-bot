#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redbubble bot v3: formula iz tvojih stvarnih prodaja

Tok:
  1. Bira 5 različitih životinja (Gemini + Google trend + autosuggest, bez ponavljanja), za svaku 5 dizajna:
     - idiom (3):     poznat engleski idiom/fraza nacrtan DOSLOVNO sa tom životinjom + relatable humor (ADHD, introverti, umor, kafa...)
     - character (2): ta životinja sa jakim karakterom/radnjom u upečatljivim bojama, tekst opcion
  2. Stvarne pretrage (Google autosuggest) za teme i životinje -> Gemini piše koncept, frazu, naslov "Fraza - opis",
     15 tagova i kratak opis. Sve se proverava u KODU (dužine, duplikati, prezasićene i zaštićene fraze, nevezani tagovi).
  3. Slika: Fal.ai Z-Image Turbo (polu-realistična životinja, crna kontura, tekst u lenti) -> Gemini vision čita tekst
     -> pozadina se skida PO BOJI (BiRefNet samo kao rezerva) -> Gemini ponovo čita tekst da lenta nije odsečena
     -> BiRefNet -> provera da je JEDAN oblik (sitne mrlje se brišu) -> 8000x8000 transparentan PNG.
  4. Izlaz: folder po životinji sa <životinja>_podaci.txt (Naslov / Opis / Tagovi / Slika / Tip / Koncept)
     + zajednički podaci_<datum>.txt; sve na Telegram.

Opcije (environment promenljive, sve su opcione):
  ANIMALS_PER_RUN=5   DESIGNS_PER_ANIMAL=5   IDIOMS_PER_ANIMAL=3   IMAGE_ATTEMPTS=3   TARGET_SIZE=8000
  METADATA_ONLY=1        -> samo koncepti/naslovi/tagovi, bez slika i Telegrama (jeftin test)
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
from PIL import Image, ImageFilter, ImageChops
try:
    import numpy as np          # dolazi uz onnxruntime/rembg iz requirements.txt
except ImportError:             # bez numpy-ja bot radi kao ranije (samo BiRefNet)
    np = None
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
TITLE_MAX = 70                # tvoj bestseler ima 67 znakova, pa Redbubble prima i duže od 60
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
    "recipe", "recipes", "facts", "habitat", "diet", "lifespan", "pet", "vet", "care",
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
adhd anxiety anxious introvert introverted extrovert mental health chaos chaotic meme memes sarcastic sarcasm coffee
caffeine monday mondays tired sleepy lazy nap naps grumpy angry overthinker overthinking procrastination procrastinator
neurodivergent social battery awkward weird unhinged aesthetic neon retro vintage kawaii cartoon sticker stickers laptop
water bottle humor humour relatable saying sayings idiom quote quotes mood vibe club squad crew
"""

GENERIC_TAGS = {
    "art", "design", "cool", "new", "awesome", "trending", "best", "sale", "nice", "great", "good", "amazing",
    "popular", "redbubble", "trend", "viral", "hot", "top", "unique", "original", "artwork", "illustration",
    "graphic", "graphics", "image", "picture", "gift", "gifts", "present", "shirt", "tshirt", "t-shirt",
}

# Nazivi proizvoda ne idu u tagove: Redbubble ih sam dodaje po proizvodu, a kod tebe troše mesto za prave pretrage
PRODUCT_WORDS = {
    "sticker", "stickers", "decal", "decals", "shirt", "shirts", "tshirt", "tshirts", "t-shirt", "t-shirts", "tee", "tees",
    "hoodie", "hoodies", "sweatshirt", "sweatshirts", "mug", "mugs", "poster", "posters", "tote", "apparel", "merch",
    "leggings",
}

PRODUCT_RE = re.compile(r"(?i)\b(" + "|".join(sorted((re.escape(w) for w in PRODUCT_WORDS), key=len, reverse=True))
                        + r"|stick it|stick on|wear it|laptop|water bottle|planner|tumbler)\b")

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
    return " ".join(singular(w) for w in name.split())      # "red pandas" -> "red panda" (isti folder i ista provera ponavljanja)


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
# 3) KONCEPTI PO FORMULI IZ TVOJIH PRODAJA
#    - "idiom":     poznat engleski idiom nacrtan DOSLOVNO sa izabranom životinjom + relatable humor (ADHD, introverti, umor...)
#    - "character": životinja sa jakim karakterom/radnjom u upečatljivim bojama, tekst opcion
# ---------------------------------------------------------------------------
BEST_SELLERS = """- "My Ducks Are Not In A Row - Funny Chaos ADHD Mental Health Meme" (41 sales, best seller): a well-known idiom drawn LITERALLY with animals + relatable ADHD / chaos humor
- "Danger Candy Neon Poison Dart Frog Aesthetic" (16 sales): no phrase, strong neon colors
- "Lazy Turtle", "Winter Assassin White Stoat Hiding", "Majestic Running Basset Hound Flying Ears": animals with strong character and action"""

CONCEPT_TYPES = {
    "idiom": ("IDIOM DOSLOVNO",
              "a well-known English idiom, saying or pun drawn LITERALLY with the {animal} (like the best seller where ducks are "
              "literally not in a row: an idiom acted out by the animal, or a saying built on the animal's name or trait) + "
              "relatable humor about the BUYER: ADHD, introverts, tiredness, chaos, coffee, anxiety, Mondays, procrastination, "
              "social battery. The buyer must think 'this is so me'. The animal is {animal}."),
    "character": ("ZIVOTINJA SA KARAKTEROM",
                  "the animal {animal} with a strong character or action (lazy, grumpy, hiding, sneaking, running fast, "
                  "dramatic, chaotic) in bold eye-catching or neon colors. Text is optional: none, or a 2-4 word label."),
}
ANIMALS_PER_RUN = env_int("ANIMALS_PER_RUN", 5)
DESIGNS_PER_ANIMAL = env_int("DESIGNS_PER_ANIMAL", 5)
IDIOMS_PER_ANIMAL = min(DESIGNS_PER_ANIMAL, env_int("IDIOMS_PER_ANIMAL", 3))   # ostatak su "karakter" dizajni
MIN_DESIGNS_PER_ANIMAL = min(3, DESIGNS_PER_ANIMAL)
# Tvoji postojeći hitovi: bot ih nikad ne pravi ponovo, samo varijacije
OWN_BESTSELLER_TITLES = ["My Ducks Are Not In A Row - Funny Chaos ADHD Mental Health Meme",
                         "Danger Candy Neon Poison Dart Frog Aesthetic", "Lazy Turtle", "Winter Assassin White Stoat Hiding",
                         "Majestic Running Basset Hound Flying Ears"]
OWN_BESTSELLER_TEXTS = ["MY DUCKS ARE NOT IN A ROW", "DANGER CANDY", "WINTER ASSASSIN"]

# Prezasićene ili zaštićene fraze (dopuni preko blocked_terms.txt)
SATURATED_RE = re.compile(
    r"(?i)\b(not my circus|not my monkeys|keep calm|live laugh love|this is fine|good vibes only|but first coffee|"
    r"i do what i want|nope not today|resting [a-z]+ face|hangry|wine o.?clock|what the duck|duck it|"
    r"cute but psycho|i('?m| am) just here for|my therapist)\b")

TYPE_PADDING = {
    "idiom": ["funny meme", "relatable humor", "funny saying", "sarcastic", "mental health", "introvert"],
    "character": ["funny animal", "cute animal", "bold colors", "animal lover gift", "cartoon animal"],
}


def research_theme_keywords():
    """Stvarne pretrage za teme koje ti prodaju (ADHD, introvert, anksioznost...). Vraća [] ako autosuggest ne radi."""
    if not USE_AUTOSUGGEST:
        return []
    seeds = ["adhd sticker", "funny adhd", "introvert sticker", "anxiety sticker", "mental health sticker",
             "funny coffee sticker", "chaos sticker", "funny idiom", "funny animal sticker", "sarcastic sticker"]
    found, seen = [], set()
    for seed in seeds:
        for s in google_suggest(seed):
            k = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s'-]", " ", s.lower())).strip()
            if not (2 <= len(k.split()) <= 5) or set(k.split()) & NON_MERCH_WORDS or find_blocked(k):
                continue
            if phrase_key(k) not in seen:
                seen.add(phrase_key(k))
                found.append(k)
        time.sleep(0.3)
    print(f"  -> Pronađeno {len(found)} stvarnih pretraga za teme (ADHD, introvert...).")
    return found[:30]


def build_concept_prompt(slots, theme_kw, animal_kw, avoid_titles, avoid_texts, feedback, today):
    slot_lines = []
    for s in slots:
        label = CONCEPT_TYPES[s["type"]][1].replace("{animal}", s.get("animal") or "")
        fixed = f' (animal = "{s["animal"]}")' if s.get("animal") else ""
        slot_lines.append(f'- slot "{s["id"]}" type={s["type"]}{fixed}: {label}')
    kw_lines = "\n".join(f"- {k}" for k in theme_kw[:25]) or "- (live data unavailable)"
    for a, kws in animal_kw.items():
        if kws:
            kw_lines += f"\nSearches for {a}: " + ", ".join(kws[:12])
    seasons = active_seasons(today)
    season_line = ("Upcoming season: " + "; ".join(s["brief"] for s in seasons) +
                   ". At most 1-2 idiom concepts may fit it, the rest must be evergreen.\n") if seasons else ""
    titles_block = "\n".join(f"- {t}" for t in avoid_titles[-60:]) or "- (none)"
    texts_block = ", ".join(avoid_texts[-150:]) or "(none)"
    fix_block = ("\nFIX THESE PROBLEMS FROM YOUR PREVIOUS ANSWER:\n" + "\n".join(f"- {f}" for f in feedback[:15]) + "\n") if feedback else ""
    return f"""You are the creative director and SEO expert of a Redbubble sticker and t-shirt shop with animals. Today is {today.strftime('%B %d, %Y')}.

WHAT ACTUALLY SELLS IN THIS SHOP (real sales data):
{BEST_SELLERS}
People buy stickers that say something about THEM, not just a picture of an animal.

REAL GOOGLE SEARCHES (use for tags and wording when they fit; ignore anything off-topic):
{kw_lines}
{season_line}
CREATE ONE CONCEPT FOR EACH SLOT:
{chr(10).join(slot_lines)}

ALREADY USED, never repeat or paraphrase these titles:
{titles_block}
ALREADY USED phrases (never reuse or closely imitate): {texts_block}
{fix_block}
DESIGN RULES: semi-realistic cartoon illustration (real proportions, real coat colors and markings of the species, fur texture)
with a thick black outline around everything; the text ALWAYS sits in a ribbon banner or
rectangle with a thick black outline at the bottom. Few details, strong contrasting flat colors, no thin lines, no gradients.
Text 2-6 words, big and readable, it must work at thumbnail size (3-4 cm). The animal has a clear facial expression or action.
FORBIDDEN: brands, characters from movies/cartoons/games, celebrity names, trademarked or overused phrases (e.g. "Not my circus,
not my monkeys", "Keep calm", "Live laugh love", "This is fine"), copying other people's designs.

FIELDS FOR EVERY CONCEPT
- slot: copy the slot id exactly. type: copy the type.
- animal: copy the given animal.
- concept: one sentence: what is seen and why it is funny.
- text: the exact phrase on the design, ENGLISH, 2-6 words, max 32 characters, only letters, numbers, spaces, apostrophes, ! and ?.
  REQUIRED for idiom. For character: "" (no text) or 2-4 words.
- visual_scene: max 35 words, English: exactly what is drawn: the animal(s), the LITERAL depiction of the phrase, poses, facial
  expressions, props and their colors (state every color). No background, no frame, no text in the scene.
  COLOR RULE: never use magenta, pink, fuchsia, purple or violet anywhere (the background is magenta and would erase them);
  use orange, yellow, red, navy blue, white, green, teal, brown or grey instead.
- title: max 70 characters, format "<Phrase or character> - <3-6 words a buyer searches>", modeled on
  "My Ducks Are Not In A Row - Funny Chaos ADHD Mental Health Meme". Never the words sticker, design, shirt, t-shirt, hoodie, poster, Redbubble.
- primary_keyword: main search phrase, 2-4 words, lowercase (e.g. "adhd duck", "introvert cat").
- tags: exactly 15 lowercase tags (1-3 words) that a buyer would type: the phrase and its short parts, the animal, the theme
  (adhd, introvert, anxiety, mental health, coffee lover...), humor words (funny, sarcastic, meme), who it is for. No filler words
  (art, design, cool, new, awesome, trending, best), no brands, and NO product names (sticker, shirt, t-shirt, tee, hoodie, mug,
  poster, case, bag, apparel...).
- description: SEO description for Google, 2-3 natural sentences, 220-420 characters. The FIRST sentence (within the first 150
  characters) must contain the exact phrase from "text" (if there is one), the animal name and the primary_keyword, written
  naturally (Google shows only the start). Then say what the artwork shows and who will relate to it, and naturally work in 2-3
  related phrases people search (e.g. "adhd humor", "introvert gift", "funny mental health meme", "gift for coworker", "<animal>
  lover"). Readable for humans, not a keyword list, no repeated words. NEVER name products or where to put it (no sticker, shirt,
  tee, hoodie, mug, poster, laptop, water bottle, notebook...). No prices, shipping, quality claims, hashtags, emojis or URLs.

Return ONLY a JSON array with exactly {len(slots)} objects with the keys: slot, type, animal, concept, text, visual_scene, title, primary_keyword, tags, description."""


def clean_title(raw, animal):
    t = re.sub(r"[\"“”`]", "", str(raw))
    t = TITLE_BANNED_RE.sub(" ", t)
    t = re.sub(r"\s+[-–—|]\s+|:\s+", " - ", t, count=1)          # "Fraza: opis" / "Fraza | opis" -> "Fraza - opis"
    t = re.sub(r"\s+", " ", t).strip(" -–—:|,.;!")
    t = smart_title(t)
    if not t:
        t = f"Funny {smart_title(animal)}"
    if not mentions_animal(t, animal):
        if " - " in t:
            head, tail = t.split(" - ", 1)
            t = f"{head} - {smart_title(animal)} {tail}"
        else:
            t = f"{t} - Funny {smart_title(animal)}"
    if len(t) > TITLE_MAX and " - " in t:
        head, tail = t.split(" - ", 1)
        tail = shorten(tail, max(8, TITLE_MAX - len(head) - 3))
        t = f"{head} - {tail}" if tail else head
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


def fallback_description(animal, title, concept):
    head = title.split(" - ")[0]
    concept = concept.strip().rstrip(".") or f"a funny cartoon {animal}"
    return (f"{head}: {concept[:1].lower() + concept[1:]}. A funny {animal} illustration for anyone who feels this "
            f"every day, and a fun gift idea for friends, coworkers and {animal} lovers.")


def clean_description(raw, animal, title, concept):
    d = re.sub(r"<[^>]+>", " ", str(raw))
    d = re.sub(r"https?://\S+|www\.\S+", " ", d)
    d = re.sub(r"#\w+", " ", d)
    d = re.sub(r"[\U00010000-\U0010ffff☀-➿]", "", d)
    d = re.sub(r"\s+", " ", d).strip()
    sentences = re.split(r"(?<=[.!?])\s+", d)
    d = " ".join(s for s in sentences if s and not CLAIM_RE.search(s) and "redbubble" not in s.lower()
                 and not PRODUCT_RE.search(s)).strip()          # bez naziva proizvoda (sticker, hoodie, mug...)
    if len(d) > DESC_MAX:
        cut = d[:DESC_MAX]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind(".") if cut.endswith(".") else -1)
        d = cut[:end + 1] if end > 120 else cut[:cut.rfind(" ")].rstrip(" ,;:-") + "."
    if len(d) < 80:
        d = fallback_description(animal, title, concept)
        if PRODUCT_RE.search(d):                                 # koncept sam pominje proizvod
            d = PRODUCT_RE.sub("design", d)
    return d[:DESC_MAX]


def clean_banner_text(raw):
    t = unicodedata.normalize("NFKD", str(raw)).encode("ascii", "ignore").decode()
    t = t.replace("’", "'")
    t = re.sub(r"[^A-Za-z0-9 '!?&-]", " ", t)
    return re.sub(r"\s+", " ", t).strip().upper()


def normalize_tag(tag, title_key=None):
    t = str(tag).lower().replace("#", " ")
    t = re.sub(r"[^a-z0-9 '-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -'")
    if not t or len(t) > TAG_MAX_LEN or len(t.split()) > 4 or len(t) < 3:
        return None
    if t in GENERIC_TAGS or set(re.split(r"[ -]", t)) & (NON_MERCH_WORDS | PRODUCT_WORDS | {"vs", "versus", "t"}) or find_blocked(t):
        return None
    if title_key and phrase_key(t) == title_key:
        return None
    return t


def clean_tags(raw, animal, title, keywords, extra_pools=(), allowed_extra=None):
    """Tačno 15 različitih tagova; životinja je uvek među njima.
    Tag sa imenom životinje mora da se oslanja SAMO na reči kupca/teme (INTENT_WORDS) ili na reči iz ovog dizajna
    (scena, fraza, koncept): tako otpadaju 'pug skull', 'poodle skirt', 'llama vs alpaca'."""
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
            if not extra <= allowed or extra == {"animal"}:
                return False
            if animal_tags >= MAX_ANIMAL_TAGS:
                return False
        seen.add(key)
        out.append(t)
        animal_tags += 1 if has_animal else 0
        return True

    add(animal, force=True)
    for t in raw:
        add(t)
    for pool in [keywords, *extra_pools, [tpl.format(a=animal) for tpl in ANIMAL_TAG_TEMPLATES], PADDING_TAGS]:
        for t in pool:
            if len(out) >= TAGS_COUNT:
                break
            add(t)
    return out[:TAGS_COUNT]


def clean_concept(raw, slot, ctx):
    """Vraća (design, []) ili (None, [problemi]). Sve što se može popraviti popravlja se u kodu."""
    if not isinstance(raw, dict):
        return None, ["objekat nije validan JSON objekat"]
    issues = []
    ctype = slot["type"]

    if slot.get("animal"):
        animal = slot["animal"]
    else:
        animal = valid_animal(raw.get("animal", ""))
        if not animal:
            return None, [f"animal '{raw.get('animal', '')}' nije validno ime životinje"]
        animal = " ".join(singular(w) for w in animal.split())

    concept = re.sub(r"\s+", " ", str(raw.get("concept", ""))).strip()
    text = clean_banner_text(raw.get("text", ""))
    words = text.split()
    if ctype == "idiom":
        if not (2 <= len(words) <= 6) or not (5 <= len(text) <= 32):
            issues.append(f"text '{text}' mora imati 2-6 reči i najviše 32 karaktera")
    elif text and (not (1 <= len(words) <= 4) or len(text) > 26):
        issues.append(f"text '{text}' za character mora biti prazan ili 2-4 reči")
    if text and canon(text) in ctx["texts"]:
        issues.append(f"text '{text}' je već korišćen")

    style = "lenta"

    scene = re.sub(r"\s+", " ", str(raw.get("visual_scene", ""))).strip().rstrip(".")
    if len(scene) < 25:
        issues.append("visual_scene je prekratak ili ga nema")
    elif not mentions_animal(scene, animal):
        scene = f"a cartoon {animal}: {scene}"
    if not PINK_ANIMAL_RE.search(animal) or "guinea" in animal:     # magenta pozadina: roze delovi bi nestali sa njom
        scene = re.sub(r"(?i)\b(neon |hot |bright |pastel )?(magenta|pink|fuchsia|purple|violet|lilac|lavender)\b", "red", scene)

    title = clean_title(raw.get("title", ""), animal)
    if len(title.split()) < 3 or len(title) < 15:
        issues.append(f"title '{title}' je prekratak")
    if phrase_key(title) in ctx["titles"]:
        issues.append(f"title '{title}' je duplikat ili previše sličan postojećem")
    off = TITLE_OFFTOPIC_RE.search(title)
    if off:
        issues.append(f"title '{title}' sadrži '{off.group(1)}': to nije tema dizajna")
    sat = SATURATED_RE.search(f"{text} {title}")
    if sat:
        issues.append(f"fraza '{sat.group(1)}' je prezasićena ili zaštićena, smisli drugu")

    pk = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s'-]", " ", str(raw.get("primary_keyword", "")).lower())).strip()
    if not (2 <= len(pk.split()) <= 5):
        pk = " ".join(title.split(" - ")[0].lower().split()[:4])

    description = clean_description(raw.get("description", ""), animal, title, concept or scene)
    # SEO: Google u rezultatu prikazuje ~150 prvih znakova, pa fraza (ono što ljudi kucaju) i životinja moraju biti na početku.
    head = description[:170]
    seo_missing = []
    if text and canon(text) not in canon(head):
        seo_missing.append(f"tačnu frazu '{text.title()}'")
    if not mentions_animal(head, animal):
        seo_missing.append(f"reč '{animal}'")
    if seo_missing:
        if not ctx.get("last_attempt"):
            issues.append(f"description mora u PRVOJ rečenici (prvih 150 znakova) da sadrži {' i '.join(seo_missing)}")
        else:                                       # poslednji pokušaj: popravi u kodu umesto da se dizajn izgubi
            kw = pk if mentions_animal(pk, animal) else f"{animal} {pk}"
            lead = f"{text.title() if text else title.split(' - ')[0]}: a funny {kw} illustration"
            description = shorten(f"{lead}. {description}", DESC_MAX)
    shown = set(tokens(scene)) | set(tokens(text)) | set(tokens(concept))
    tags = clean_tags(raw.get("tags", []), animal, title, ctx["keywords"].get(animal, []) + ctx["theme_keywords"],
                      extra_pools=[TYPE_PADDING.get(ctype, [])], allowed_extra=shown)

    blocked = find_blocked(" ".join([title, description, text, scene, concept, pk]))
    if blocked:
        issues.append(f"sadrži zaštićeni/brend pojam: {', '.join(blocked)}")

    if issues:
        return None, issues
    return {
        "type": ctype, "animal": animal, "concept": concept or scene, "text": text, "style": style,
        "visual_scene": scene, "title": title, "primary_keyword": pk, "description": description, "tags": tags,
    }, []


def generate_concepts(slots, theme_kw, animal_kw, today, history):
    old = [d for rec in history["animals"].values() for d in rec.get("designs", [])] + history.get("designs", [])
    avoid_titles = OWN_BESTSELLER_TITLES + [d["title"] for d in old if d.get("title")]
    # Fraze se tvrdo proveravaju protiv poslednjih 150: model ume sam da ponavlja iste.
    avoid_texts = OWN_BESTSELLER_TEXTS + [d["text"] for d in old if d.get("text")][-150:]
    ctx = {
        "titles": {phrase_key(t) for t in avoid_titles},
        "texts": {canon(t) for t in avoid_texts},
        "keywords": animal_kw,
        "theme_keywords": theme_kw,
    }
    accepted = {}
    for start in range(0, len(slots), 8):                      # najviše 8 koncepata po pozivu: kraći, pouzdaniji JSON
        group = slots[start:start + 8]
        feedback = []
        for attempt in range(1, 4):
            ctx["last_attempt"] = attempt == 3
            todo = [s for s in group if s["id"] not in accepted]
            if not todo:
                break
            prompt = build_concept_prompt(todo, theme_kw, {a: k for a, k in animal_kw.items()
                                                            if any(s.get("animal") == a for s in todo)},
                                          avoid_titles, avoid_texts, feedback, today)
            feedback = []
            try:
                txt = gemini(prompt, json_mode=True, label="koncepti",
                             validator=lambda t: isinstance(extract_json(t), (list, dict)))
                data = extract_json(txt)
                if isinstance(data, dict):
                    data = next((v for v in data.values() if isinstance(v, list)), [data])
            except Exception as e:
                print(f"  -> Pokušaj {attempt}: generisanje koncepata nije uspelo: {redact(e)[:150]}")
                continue
            for i, raw in enumerate(data):
                if not isinstance(raw, dict):
                    continue
                slot = next((s for s in todo if s["id"] == str(raw.get("slot", "")).strip()), None)
                if slot is None and i < len(todo):
                    slot = todo[i]
                if slot is None or slot["id"] in accepted:
                    continue
                design, issues = clean_concept(raw, slot, ctx)
                if design is None:
                    print(f"     ✗ [{slot['type']}] '{str(raw.get('title', '?'))[:55]}' odbijen: {'; '.join(issues)}")
                    feedback.append(f"[slot {slot['id']}] {'; '.join(issues)}")
                    continue
                accepted[slot["id"]] = design
                ctx["titles"].add(phrase_key(design["title"]))
                if design["text"]:
                    ctx["texts"].add(canon(design["text"]))
                    avoid_texts.append(design["text"])
                avoid_titles.append(design["title"])
            print(f"  -> Pokušaj {attempt}: prihvaćeno {sum(s['id'] in accepted for s in group)}/{len(group)} koncepata.")
    return [accepted[s["id"]] for s in slots if s["id"] in accepted]


# ---------------------------------------------------------------------------
# 4) SLIKE
# ---------------------------------------------------------------------------
def fal_headers():
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}


def pick_chroma(design):
    """Kao ranije: uvek MAGENTA pozadina; NEON PLAVA samo za prirodno roze životinje (flamingo, svinja, aksolotl...).
    Zato dizajn ne sme da ima roze/ljubičaste delove (scena ih menja u crveno, negativni prompt ih zabranjuje)."""
    if PINK_ANIMAL_RE.search(design["animal"]) and "guinea" not in design["animal"]:
        return ("PURE SOLID NEON BLUE (#0044FF) CHROMA KEY BACKGROUND", "blue, neon blue, cyan, teal,", None)
    return ("PURE SOLID HOT MAGENTA (#FF00FF) CHROMA KEY BACKGROUND", "magenta, hot pink, pink, fuchsia, purple,", None)


def fal_text_to_image(design):
    """Z-Image Turbo: polu-realistična ilustracija (prave proporcije, prave šare vrste, tekstura krzna), debela CRNA kontura oko svega,
    tekst UVEK u lenti/pravougaoniku sa crnom ivicom, izolovano na jednobojnoj pozadini koju BiRefNet lako skine.
    Bez reči 'sticker'/'die-cut': zbog njih je generator crtao beli okvir nalepnice koji posle ostane oko dizajna."""
    chroma_bg, color_negative, _ = pick_chroma(design)
    text = design["text"]
    q = '"' if "'" in text else "'"
    if text:
        banner = (f"Banner & Text: Positioned strictly at the very bottom below the animal, there is a horizontal ribbon banner "
                  f"or rectangle filled with solid bright yellow, orange, white or red with a thick black outline, containing bold "
                  f"black typography reading exactly {q}{text}{q}. This is the ONLY text in the image, spelled exactly like that, "
                  f"all letters inside the banner. ")
    else:
        banner = "There is NO text, letters, numbers or banner anywhere. "
    image_prompt = (
        "A standalone semi-realistic cartoon illustration graphic for a t-shirt design. "
        f"Subject: A {design['animal']} drawn with true-to-life proportions, anatomy and the real natural coat colors and markings "
        f"of the species: {design['visual_scene']}. Small natural eyes and a subtle funny expression, still recognisable as the real animal. "
        "Style: semi-realistic cel-shaded illustration, detailed fur or feather texture drawn with crisp jagged strokes, "
        "2-3 tone shading, solid saturated colors, clean crisp sharp edges, no blur. "
        + ("Outline: The entire illustration, character, props, and banner MUST have a thick solid bold black outline enclosing every single shape. "
           if text else "Outline: The entire illustration, character and props MUST have a thick solid bold black outline enclosing every single shape. ")
        + banner
        + f"Composition: centered, fully visible, the artwork is completely isolated on a {chroma_bg}."
    )
    negative_prompt = (
        f"{color_negative} white background, black background, transparent background, gradient background, "
        "scenery, sticker, sticker peel, die cut, white border, white outline, white edge, sticker border, badge, circle frame, "
        "circular frame, round emblem, border, frame, drop shadow, 3d render, photorealistic, photograph, glow, blurry edges, "
        "chibi, kawaii, big anime eyes, oversized head, mascot proportions, "
        "brush strokes, watermark, signature, messy edges, floating text outside banner, curved text, arched text, "
        "misspelled text, extra words, cropped, cut off, beige, pastels, washed out colors"
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


def check_design_text(img_bytes, expected):
    """Gemini vision čita SAV tekst na slici: mora biti tačno traženi (ili nikakav, ako dizajn nema tekst).
    Greška API-ja = prolazi (ne blokira posao)."""
    try:
        fmt = (Image.open(BytesIO(img_bytes)).format or "PNG").upper()
        mime = "image/jpeg" if fmt in ("JPEG", "JPG") else "image/png"
        prompt = ('Look at this sticker illustration. Read ALL text visible in the image exactly as written.\n'
                  'Return ONLY JSON: {"text": "<all text you read, or empty>", "major_defect": true/false (extra heads or '
                  'limbs, merged bodies, cropped subject, unreadable letters), "defect": "<short description or empty>"}')
        txt = gemini(prompt, json_mode=True, image=(img_bytes, mime),
                     validator=lambda t: isinstance(extract_json(t), dict), label="provera slike")
        data = extract_json(txt)
        read = canon(data.get("text", data.get("banner_text", "")))
        if expected:
            ok = read == canon(expected)        # tačno slovo po slovo: "BRAAN" umesto "BRAIN" mora da padne
        else:
            ok = len(read) <= 2
        if not ok or data.get("major_defect") is True:
            return False, f"očekivano '{expected or '(bez teksta)'}', pročitano '{data.get('text', '')}' {data.get('defect', '')}".strip()
        return True, ""
    except Exception as e:
        print(f"    (provera teksta preskočena: {redact(e)[:100]})")
        return True, ""


def chroma_alpha(rgb_img):
    """Skida jednobojnu pozadinu PO BOJI (magenta/plava koju je generator nacrtao). Za razliku od BiRefNet-a ne "misli"
    šta je glavni objekat, pa ne briše lentu sa tekstom ispod životinje. Vraća (alpha, pozadina_je_jednobojna)."""
    a = np.asarray(rgb_img.convert("RGB")).astype(np.int32)
    h, w, _ = a.shape
    b = max(2, min(h, w) // 100)
    border = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    spread = float(np.percentile(np.sqrt(((border - bg) ** 2).sum(1)), 90))
    t1 = min(90.0, max(40.0, spread + 15))                       # do ove udaljenosti od boje pozadine: providno
    t2 = t1 + 45                                                 # od ove: potpuno vidljivo; između: glatka ivica
    d = np.sqrt(((a - bg) ** 2).sum(2))
    alpha = (np.clip((d - t1) / (t2 - t1), 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(alpha, "L"), spread < 60


def remove_background(original_bytes, url):
    """1) skidanje po boji (glavno); 2) BiRefNet samo ako pozadina nije čista (onda se dva rezultata SPAJAJU,
    pa nijedan ne može da obriše deo dizajna koji je drugi zadržao)."""
    original = Image.open(BytesIO(original_bytes)).convert("RGB")
    if np is not None:
        alpha, clean = chroma_alpha(original)
        if clean:
            out = original.convert("RGBA")
            out.putalpha(alpha)
            return out, "boja"
    birefnet = Image.open(BytesIO(fal_remove_background(url))).convert("RGBA")
    if np is None:
        return birefnet, "birefnet"
    b_alpha = birefnet.getchannel("A").resize(original.size, Image.Resampling.LANCZOS)
    out = original.convert("RGBA")
    out.putalpha(ImageChops.lighter(alpha, b_alpha))
    return out, "boja+birefnet"


def split_pieces(img, size=384):
    """Die-cut nalepnica mora biti JEDAN oblik. Briše sitne mrlje (<0,4% površine) i vraća (slika, broj_većih_delova)."""
    alpha = img.getchannel("A")
    small = alpha.resize((size, size), Image.Resampling.BILINEAR).point(lambda p: 255 if p > 100 else 0)
    px = small.load()
    w, h = small.size
    seen = bytearray(w * h)
    comps = []
    for y in range(h):
        for x in range(w):
            if seen[y * w + x] or not px[x, y]:
                continue
            seen[y * w + x] = 1
            stack, pts = [(x, y)], []
            while stack:
                cx, cy = stack.pop()
                pts.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and px[nx, ny]:
                        seen[ny * w + nx] = 1
                        stack.append((nx, ny))
            comps.append(pts)
    total = sum(len(c) for c in comps) or 1
    specks = [c for c in comps if len(c) < 0.004 * total]
    pieces = sum(1 for c in comps if len(c) >= 0.004 * total)
    if specks:
        mask = Image.new("L", (w, h), 255)
        mp = mask.load()
        for c in specks:
            for x, y in c:
                mp[x, y] = 0
        mask = mask.resize(img.size, Image.Resampling.NEAREST)
        img = img.copy()
        img.putalpha(Image.composite(alpha, Image.new("L", img.size, 0), mask))
    return img, pieces


# LUT: alpha < 100 -> 0, > 155 -> 255, između glatki prelaz (antialiasing umesto tvrdog praga)
_ALPHA_LUT = [0] * 100 + [round((i - 100) * 255 / 55) for i in range(100, 155)] + [255] * 101


def to_canvas(img, size):
    """Transparentna RGBA slika -> centrirano na platno size x size, glatke ivice, bez obojenog oboda od pozadine."""
    img = img.convert("RGBA")
    r, g, b, a = img.split()
    a = a.filter(ImageFilter.MinFilter(3))                       # 1px erozija: skida ostatak pozadine
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
    canvas.paste(art, ((size - new_w) // 2, (size - new_h) // 2))
    return canvas


def make_design_image(design, out_path):
    note = ""
    for attempt in range(1, IMAGE_ATTEMPTS + 1):
        try:
            url, original = fal_text_to_image(design)
            ok, note = (True, "")
            if VERIFY_IMAGE_TEXT:
                ok, note = check_design_text(original, design["text"])
                if not ok and attempt < IMAGE_ATTEMPTS:
                    print(f"    ⟳ Tekst/anatomija nisu u redu ({note}). Pokušaj {attempt + 1}/{IMAGE_ATTEMPTS}...")
                    continue
            transparent, method = remove_background(original, url)
            transparent, pieces = split_pieces(transparent)
            if VERIFY_IMAGE_TEXT and design["text"]:
                # Druga provera, POSLE skidanja pozadine: tekst u lenti mora i dalje da bude ceo
                preview = Image.new("RGB", transparent.size, (60, 60, 60))
                preview.paste(transparent, (0, 0), transparent)
                buf = BytesIO()
                preview.save(buf, "PNG")
                ok2, note2 = check_design_text(buf.getvalue(), design["text"])
                if not ok2:
                    if attempt < IMAGE_ATTEMPTS:
                        print(f"    ⟳ Posle skidanja pozadine ({method}) tekst nije ceo ({note2}). Pokušaj {attempt + 1}/{IMAGE_ATTEMPTS}...")
                        continue
                    ok, note = False, f"posle skidanja pozadine: {note2}"
            canvas = to_canvas(transparent, TARGET_SIZE)
            canvas.save(out_path, "PNG", compress_level=6)
            del canvas, transparent
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
        f"Tip: {CONCEPT_TYPES[it['type']][0]} | Stil: {it['style']} | Tekst na dizajnu: {it['text'] or '(bez teksta)'}",
        f"Koncept: {it['concept']}",
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
    history.setdefault("designs", [])
    print(f"🤖 [FAZA 1] Biram {ANIMALS_PER_RUN} životinja (trend + evergreen + stvarna potražnja)...")
    animals = pick_animals(used, history, today, ANIMALS_PER_RUN)
    print(f"🎯 Lista za danas: {', '.join(a.upper() for a in animals)}  "
          f"(po životinji: {IDIOMS_PER_ANIMAL} idiom + {DESIGNS_PER_ANIMAL - IDIOMS_PER_ANIMAL} karakter)")
    print("🔎 Istražujem stvarne pretrage za teme (ADHD, introvert...)...")
    theme_kw = research_theme_keywords()

    results = []
    for n, animal in enumerate(animals, 1):
        print(f"\n--- Životinja {n}/{len(animals)}: {animal.upper()} ---")
        try:
            animal_kw = {animal: research_keywords(animal)}
            slots = ([{"type": "idiom", "animal": animal} for _ in range(IDIOMS_PER_ANIMAL)]
                     + [{"type": "character", "animal": animal} for _ in range(DESIGNS_PER_ANIMAL - IDIOMS_PER_ANIMAL)])
            for i, s_ in enumerate(slots, 1):
                s_["id"] = f"s{i}"
            designs = generate_concepts(slots, theme_kw, animal_kw, today, history)
            if len(designs) < MIN_DESIGNS_PER_ANIMAL:
                raise RuntimeError(f"samo {len(designs)} validnih koncepata (minimum {MIN_DESIGNS_PER_ANIMAL})")

            folder = safe_name(animal)
            folder_path = os.path.join(OUTPUT_DIR, folder)
            os.makedirs(folder_path, exist_ok=True)
            made, taken = [], set()
            for j, d in enumerate(designs, 1):
                print(f"  -> Dizajn {j}/{len(designs)} [{CONCEPT_TYPES[d['type']][0]}] {d['title']}  |  "
                      f"tekst: {d['text'] or '(bez teksta)'}  |  {d['style']}")
                file_name = unique_name(folder_path, safe_name(d["title"].split(" - ")[0]), ".png", taken)
                item = dict(d, folder=folder, file_name=file_name, file_path=os.path.join(folder_path, file_name),
                            needs_review=False, review_note="")
                if METADATA_ONLY:
                    item["file_name"] = "(slika nije generisana: METADATA_ONLY)"
                else:
                    try:
                        item.update(make_design_image(d, item["file_path"]))
                    except Exception as e:
                        print(f"  ✗ Dizajn preskočen: {redact(e)[:150]}")
                        continue
                    time.sleep(2)
                made.append(item)

            if len(made) < MIN_DESIGNS_PER_ANIMAL:
                raise RuntimeError(f"uspelo samo {len(made)} slika")
            results.extend(made)
            if not METADATA_ONLY:        # METADATA_ONLY je suvi test: životinje se ne troše
                used.append(animal)
                save_used_animals(used)
                for m in made:
                    history["designs"].append({"date": today.isoformat(), "type": m["type"], "animal": animal,
                                               "title": m["title"], "text": m["text"], "primary_keyword": m["primary_keyword"]})
                save_history(history)
        except Exception as e:
            print(f"❌ Greška na životinji {animal}: {redact(e)[:200]}")
            if not METADATA_ONLY:
                history["failed"][animal] = history["failed"].get(animal, 0) + 1
                save_history(history)
        time.sleep(3)

    if not results:
        sys.exit("Nijedan dizajn nije napravljen. Pogledaj greške iznad.")

    txt_paths, combined_txt = write_listings(results, today)
    review = [r for r in results if r.get("needs_review")]
    counts = {t: sum(r["type"] == t for r in results) for t in CONCEPT_TYPES}
    summary = (f"✅ Redbubble bot {today.isoformat()}: {len(results)} dizajna "
               f"({counts['idiom']} idiom, {counts['character']} karakter), "
               f"{len(txt_paths)} životinja ({', '.join(txt_paths)}).\n"
               + (f"⚠ {len(review)} slika za ručnu proveru (u *_podaci.txt piše !!! PROVERI SLIKU).\n" if review else "")
               + "U folderu svake životinje je <životinja>_podaci.txt sa naslovom, opisom i tagovima za svaki dizajn.")
    print("\n" + summary)

    if METADATA_ONLY:
        for it in results:
            print(f"\n[{CONCEPT_TYPES[it['type']][0]}] {it['title']}\n  tekst: {it['text'] or '(bez teksta)'} | {it['style']}"
                  f"\n  koncept: {it['concept']}\n  tagovi: {', '.join(it['tags'])}\n  opis: {it['description']}")
        return

    files_by_folder = {}
    for it in results:
        files_by_folder.setdefault(it["folder"], []).append((it["file_path"], f"{it['folder']}/{it['file_name']}"))
    send_telegram(files_by_folder, txt_paths, summary, combined_txt, today)


if __name__ == "__main__":
    main()
