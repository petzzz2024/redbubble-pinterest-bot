#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Petzzz blog bot v3

Šta radi (jedan post po pokretanju, najviše MAX_POSTS_PER_DAY dnevno):
  1. Bira životinju koja STVARNO postoji u tvom Redbubble shopu: jednom dnevno pregleda stranice shopa
     (redbubble.com/people/<ti>/shop) i iz naslova vidi koje životinje imaš, pa pre pisanja još jednom pretraži shop
     za izabranu životinju. Životinju bez proizvoda preskače. Ako Redbubble ne pusti bota (blokada), koristi
     shop_animals.txt (tvoj spisak) ili životinje ranije potvrđene u shopu; ako ni toga nema, NE objavljuje post.
     Zatim bira PROIZVOD koji ta životinja ima (nalepnice / majice / duksevi) i temu (smešni dizajni, pokloni,
     vodič za proizvod, značenje idioma, "znaci da ti je duhovna životinja...", činjenice, sezonske teme).
  2. Slike: prvo pokušava da povuče proizvode DIREKTNO iz tvog Redbubble shopa (slika proizvoda, naslov i link baš na
     taj proizvod). Ako Redbubble ne dozvoli pristup, Fal.ai pravi novu ilustraciju, a bot od nje napravi nalepnicu
     (beli die-cut rub) ili mockup majice/duksa.
  3. Google Search (Gemini) skuplja proverene činjenice (o životinji ili poreklu idioma), pa Gemini piše priču:
     uvod sa scenom, proizvodi iz shopa po imenu, praktični saveti za taj proizvod, FAQ.
  4. Linkovi vode TAČNO na taj proizvod (nalepnice -> tvoje nalepnice te životinje, hoodie -> tvoji duksevi...).
  5. Popravlja stare postove koji vode na praznu pretragu (životinja za koju nemaš dizajne -> link na shop).
  6. blog.html (filter po proizvodu), sitemap.xml (sa slikama), rss.xml (sa slikom, za Pinterest RSS), IndexNow.

Opcione env promenljive:
  MAX_POSTS_PER_DAY=1     SHOP_USERNAME=Petzzz     SITE_DOMAIN=petzzz.world
  USE_STORE_IMAGES=0      (ne čitaj shop; tada je obavezan shop_animals.txt)
  shop_animals.txt        (opciono, u glavnom folderu: tvoje životinje iz shopa, jedna po redu)
  USE_SEARCH_GROUNDING=0  (isključi Google Search za činjenice)
"""
import os
import re
import io
import json
import glob
import html
import random
import time
import datetime
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from google import genai
from google.genai import types

try:
    import numpy as np
except ImportError:      # bez numpy-ja radi sve osim skidanja pozadine sa Fal rezervnih slika
    np = None

ET.register_namespace("media", "http://search.yahoo.com/mrss/")

# ---------------------------------------------------------------------------
# KONFIGURACIJA
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FAL_KEY = os.environ.get("FAL_KEY")
GA_MEASUREMENT_ID = "G-JHTGX1J5HX"


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


GEMINI_MODELS = [
    'gemini-3.5-flash-lite',
    'gemini-3.8-flash',
    'gemini-3.7-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash',
    'gemini-3.1-flash-lite'
]

SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "petzzz.world")
SHOP_USERNAME = os.environ.get("SHOP_USERNAME", "Petzzz")
INDEXNOW_KEY = "c8f1e2d3a4b5c6d7e8f9a0b1c2d3e4f5"
BRAND = "Petzzz Studio"
STORE_HOME_URL = "https://petzzz.redbubble.com"
LOGO_PATH = "/Logo%202.png"
MAX_POSTS_PER_DAY = env_int("MAX_POSTS_PER_DAY", 1)
USE_STORE_IMAGES = os.environ.get("USE_STORE_IMAGES", "1") != "0"
SHOP_CHECK_FILE = "blog/shop_check.json"     # šta je bot video u shopu: {životinja: {"count": n, "date": "..."}}
MANUAL_SHOP_FILE = "shop_animals.txt"        # opciono: tvoj spisak životinja koje su u shopu (jedna po redu)
RECHECK_DAYS = 14                            # životinja bez proizvoda se ponovo proverava posle 14 dana
MAX_SHOP_CHECKS = env_int("MAX_SHOP_CHECKS", 6)    # najviše toliko životinja proverava po pokretanju
USE_SEARCH_GROUNDING = os.environ.get("USE_SEARCH_GROUNDING", "1") != "0"
MIN_WORDS = 900
POST_IMG_DIR = "blog/images"

PRODUCTS = {
    "stickers": {"label": "stickers", "one": "sticker", "ia": "all-stickers", "kind": "sticker"},
    "t-shirts": {"label": "t-shirts", "one": "t-shirt", "ia": "u-tees", "kind": "tee"},
    "hoodies": {"label": "hoodies", "one": "hoodie", "ia": "u-sweatshirts", "kind": "hoodie"},
}

# ---------------------------------------------------------------------------
# ŽIVOTINJE IZ TVOG SHOPA: blog piše SAMO o njima.
# Kad postaviš dizajne za novu životinju, dopiši je ovde (ili u fajl shop_animals.txt, jednu po redu).
# ---------------------------------------------------------------------------
SHOP_ANIMALS = [
    # Psi i divlje vrste pasa
    "corgi", "bernese mountain dog", "golden retriever", "border collie",
    "english bulldog", "basset hound", "belgian malinois", "shiba inu",
    "red heeler", "pug", "norwegian lundehund", "chihuahua",
    "samoyed", "pitbull", "husky", "dachshund", "afghan hound",
    "newfoundland dog", "cavalier king charles spaniel", "doberman",
    "spotted hyena",

    # Mačke i divlje mačke
    "cat", "black cat", "maine coon", "sphynx cat",
    "pallas cat", "manul", "snow leopard", "jaguarundi",

    # Ptice
    "canada goose", "crow", "great potoo", "cassowary",
    "green cheeked conure", "pigeon", "silkie chicken", "duck",
    "emu", "bearded vulture",

    # Gmizavci (kornjače, zmije, gušteri)
    "turtle", "russian tortoise", "african sulcata tortoise",
    "blue pit viper", "hognose snake", "corn snake",
    "argentine tegu", "uromastyx", "leachianus gecko", "crested gecko",
    "red-eyed crocodile skink",

    # Vodozemci (žabe)
    "poison dart frog", "pacman frog", "black rain frog", "dumpy tree frog",

    # Morske, vodene životinje i beskičmenjaci
    "sea otter", "harbor seal", "shark", "vampire crab", "sea sheep nudibranch",
    "blobfish", "jumping spider", "weevil",

    # Ostali sisari i egzotične vrste
    "capybara", "wombat", "honey badger", "beaver", "platypus",
    "maned wolf", "stoat", "tibetan fox", "binturong", "hedgehog",
]

# Životinje koje niko (ili skoro niko) ne drži kao ljubimca -> publika su "fanovi", ne "vlasnici"
WILD_ANIMALS = {
    "spotted hyena", "pallas cat", "manul", "snow leopard", "jaguarundi",
    "canada goose", "crow", "great potoo", "cassowary", "pigeon", "emu",
    "bearded vulture", "blue pit viper", "black rain frog", "sea otter",
    "harbor seal", "shark", "vampire crab", "sea sheep nudibranch", "blobfish",
    "weevil", "capybara", "wombat", "honey badger", "beaver", "platypus",
    "maned wolf", "stoat", "tibetan fox", "binturong",
}

# Najtraženije životinje: dobijaju duplo više članaka u rotaciji
POPULAR_ANIMALS = {
    "cat", "black cat", "corgi", "golden retriever", "husky", "pug", "dachshund",
    "shiba inu", "chihuahua", "pitbull", "border collie", "maine coon",
    "bernese mountain dog", "english bulldog", "samoyed", "capybara", "hedgehog",
}

# Šire poznate životinje: pregled shopa ih prepoznaje u naslovima i kad nisu iz dizajn-bota (npr. ručno postavljeni dizajni)
EXTRA_ANIMALS = {
    "duck", "frog", "poison dart frog", "turtle", "tortoise", "stoat", "basset hound", "cat", "dog", "goose", "pigeon", "crow",
    "raccoon", "possum", "opossum", "sloth", "otter", "sea otter", "capybara", "axolotl", "red panda", "panda", "koala", "fox",
    "wolf", "bear", "polar bear", "penguin", "owl", "bee", "snail", "cow", "highland cow", "pig", "goat", "sheep", "llama",
    "alpaca", "horse", "donkey", "rabbit", "bunny", "hedgehog", "hamster", "guinea pig", "ferret", "chinchilla", "squirrel",
    "chipmunk", "beaver", "platypus", "wombat", "quokka", "kangaroo", "elephant", "giraffe", "zebra", "lion", "tiger",
    "leopard", "snow leopard", "cheetah", "monkey", "lemur", "sloth bear", "hippo", "rhino", "manatee", "seal", "harbor seal",
    "walrus", "whale", "orca", "dolphin", "shark", "octopus", "jellyfish", "crab", "lobster", "pufferfish", "manta ray",
    "flamingo", "toucan", "parrot", "chicken", "rooster", "turkey", "swan", "moose", "deer", "reindeer", "bat", "moth",
    "butterfly", "ladybug", "spider", "gecko", "chameleon", "bearded dragon", "snake", "dinosaur", "unicorn", "shiba inu",
    "corgi", "pug", "dachshund", "beagle", "poodle", "husky", "golden retriever", "french bulldog", "black cat", "meerkat",
}

PET_ANIMALS = {
    "australian shepherd", "beagle", "border collie", "chihuahua", "corgi", "dachshund", "dalmatian", "french bulldog",
    "german shepherd", "golden retriever", "great dane", "husky", "pomeranian", "poodle", "pug", "rottweiler", "samoyed",
    "shiba inu", "shih tzu", "black cat", "calico cat", "siamese cat", "tabby cat", "cat", "maine coon", "sphynx cat",
    "bunny", "rabbit", "guinea pig", "hamster", "ferret", "chinchilla", "bearded dragon", "gecko", "axolotl", "hedgehog",
    "budgie", "parrot", "cockatiel", "corn snake", "ball python", "tortoise", "goldfish",
}

PROFANITY_RE = re.compile(r"(?i)\b(f+u+c+k\w*|sh[i1]t\w*|bitch\w*|asshole|dick|cunt|damn|wtf|stfu|bastard|piss\w*)\b")

# Fraze koje odaju loš AI tekst; ako ih ima previše, probamo sledeći model
CLICHES = [
    "in today's fast-paced world", "look no further", "whether you're a", "delve", "elevate your", "unleash",
    "game-changer", "game changer", "furry friend", "paw-some", "pawsome", "a testament to", "in conclusion",
    "it's no secret", "embark on", "treasure trove", "look no more", "the perfect blend", "tapestry", "in the realm of",
]


# ---------------------------------------------------------------------------
# TEME (UGLOVI). {animal} {Animal} {product} {Product} {one} {year} se popunjavaju.
# products: za koje proizvode tema ima smisla. needs: "idiom" = treba dizajn sa poznatim idiomom.
# ---------------------------------------------------------------------------
ANGLES = [
    {"id": "funny-designs", "label": "relatable funny designs", "products": ["stickers", "t-shirts", "hoodies"],
     "title_hint": "Funny {Animal} {Product} for People Running on Coffee and Chaos",
     "brief": "A story-driven roundup of funny, relatable {animal} {product}. Open with a short, vivid everyday scene the reader "
              "recognises (overthinking at 2am, too many tabs open, social battery at 0%). Then walk through the shop designs "
              "listed below one by one: what the artwork shows, the joke behind it, which real {animal} trait inspired it and "
              "who will feel seen by it. Finish with practical advice for choosing {product}."},
    {"id": "gift-guide", "label": "gift guide", "products": ["stickers", "t-shirts", "hoodies"],
     "title_hint": "{Animal} {Product} Gift Ideas for Coworkers, Friends and Teens",
     "brief": "A gift guide for {animal} {product}, organised by WHO you are buying for (the overthinking coworker, the "
              "introvert best friend, the teen who lives in memes, the tired parent, treat yourself). Match each recipient "
              "with one of the shop designs listed below and explain why it fits them. Add short tips on choosing size/finish "
              "and on wrapping or presenting the gift."},
    {"id": "product-guide", "label": "practical product guide", "products": ["stickers", "t-shirts", "hoodies"],
     "title_hint": "{Animal} {Product}: How to Choose, Style and Make Them Last",
     "brief": "A genuinely useful practical guide to {animal} {product}. For stickers: where to put them (laptop, water "
              "bottle, planner, phone case, notebook), how to apply them without bubbles, how to make them last, sticker-swap "
              "and gifting ideas. For t-shirts and hoodies: choosing fit and size, how a printed design should sit, washing "
              "and care so the print lasts, outfit ideas. Use the shop designs listed below as the running examples."},
    {"id": "idiom-meaning", "label": "idiom meaning and origin", "products": ["stickers", "t-shirts", "hoodies"],
     "needs": "idiom",
     "title_hint": "{Idiom} Meaning, Origin and the {Animal} Who Lives It",
     "brief": "An article that answers 'what does \"{idiom}\" mean and where does it come from?' First a direct 40-60 word "
              "definition, then the origin using ONLY the research notes (if the origin is uncertain, say so honestly), "
              "everyday examples of how people use it today, similar idioms, and finally the funny literal take: the shop "
              "design where a {animal} acts the phrase out, why it is so relatable, and who it suits as {product}."},
    {"id": "signs-you-are", "label": "relatable list", "products": ["stickers", "t-shirts", "hoodies"],
     "title_hint": "12 Signs Your Spirit Animal Is a {Animal}",
     "brief": "A funny, relatable numbered list of signs your spirit animal is a {animal} (each sign = an <h3> with a specific "
              "40-70 word scenario that ties a real {animal} trait to everyday life: naps, snacks, chaos, social battery, "
              "Mondays). Weave the shop designs listed below in where a sign matches their joke. End with ways to own it."},
    {"id": "fun-facts", "label": "fun facts", "products": ["stickers", "t-shirts", "hoodies"],
     "title_hint": "Surprising {Animal} Facts (and Why We Turned Them Into Designs)",
     "brief": "8-10 accurate, surprising {animal} facts taken ONLY from the research notes, each an <h3> with 50-80 words, "
              "told with humour. Connect a few facts to the shop designs listed below (the real trait behind the joke). "
              "Close with the {product} for fans."},
    {"id": "christmas", "label": "Christmas gift guide", "products": ["stickers", "hoodies", "t-shirts"],
     "window": ((10, 15), (12, 10)),
     "title_hint": "{Animal} {Product} Christmas Gifts and Stocking Stuffers {year}",
     "brief": "A Christmas gift guide for {animal} {product}: Secret Santa and office gift swaps, stocking stuffers, gifts for "
              "the introvert who hates holiday small talk, cozy picks. Use the shop designs listed below. Include a short "
              "'order early' tip without making shipping promises."},
    {"id": "valentines", "label": "Valentine's / Galentine's gifts", "products": ["stickers", "t-shirts"],
     "window": ((12, 26), (2, 10)),
     "title_hint": "Funny {Animal} Valentine's Gifts for Your Favorite Weirdo",
     "brief": "Funny and low-key Valentine's or Galentine's gift ideas with {animal} {product} for a partner, best friend or "
              "yourself, using the shop designs listed below, plus card message ideas."},
    {"id": "back-to-school", "label": "back to school", "products": ["stickers", "t-shirts"],
     "window": ((7, 10), (9, 5)),
     "title_hint": "{Animal} {Product} for Back to School: Laptop, Planner and Locker Ideas",
     "brief": "Back-to-school ideas with {animal} {product}: personalising laptops, planners, lockers and water bottles, "
              "and outfits for the first week, using the shop designs listed below."},
]


# ---------------------------------------------------------------------------
# POMOĆNE FUNKCIJE
# ---------------------------------------------------------------------------
def slugify(text):
    text = str(text).lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text).strip('-')


def esc(text):
    return html.escape(str(text), quote=True)


def is_pet(animal):
    if animal in WILD_ANIMALS:
        return False
    return animal in PET_ANIMALS or animal in SHOP_ANIMALS or animal.endswith((" cat", " dog"))


def count_words(html_text):
    return len(re.sub(r'<[^>]+>', ' ', html_text).split())


def in_window(today, start, end):
    s = datetime.date(today.year, start[0], start[1])
    e = datetime.date(today.year, end[0], end[1])
    if s <= e:
        return s <= today <= e
    return today >= s or today <= e


def fill(text, animal, product, today, idiom=""):
    p = PRODUCTS[product]
    return (text.replace("{animal}", animal).replace("{Animal}", animal.title())
                .replace("{product}", p["label"]).replace("{Product}", p["label"].title())
                .replace("{one}", p["one"]).replace("{year}", str(today.year))
                .replace("{idiom}", idiom.lower()).replace("{Idiom}", idiom.title()))


def site_img(path):
    """Putanja slike za stranicu: spoljni URL ostaje, lokalna putanja postaje apsolutna (/blog/images/...)."""
    if not path:
        return LOGO_PATH
    return path if path.startswith(("http://", "https://", "/")) else "/" + path


def shop_url(query=None, product=None):
    """Pretraga u TVOM shopu: tvoj nalog + (životinja) + (vrsta proizvoda)."""
    params = {}
    if query:
        params["query"] = query
    params["artistUserName"] = SHOP_USERNAME
    if product:
        params["iaCode"] = PRODUCTS[product]["ia"]
    return "https://www.redbubble.com/shop/?" + urllib.parse.urlencode(params)


def load_shop_animals():
    """Životinje iz dizajn-bota (used_animals.txt / design_history.json). Služe SAMO kao rečnik za pregled shopa;
    blog o njima ne piše dok ih ne dopišeš u SHOP_ANIMALS ili shop_animals.txt (nisu sve postavljene u shop)."""
    animals = set()
    if os.path.exists("used_animals.txt"):
        with open("used_animals.txt", encoding="utf-8") as f:
            animals |= {l.strip().lower() for l in f if l.strip()}
    try:
        with open("design_history.json", encoding="utf-8") as f:
            hist = json.load(f)
        animals |= {a.lower() for a in hist.get("animals", {})}
        animals |= {d.get("animal", "").lower() for d in hist.get("designs", []) if d.get("animal")}
    except (OSError, ValueError):
        pass
    return {a for a in animals if a}


# ---------------------------------------------------------------------------
# PROIZVODI DIREKTNO IZ TVOG REDBUBBLE SHOPA
# ---------------------------------------------------------------------------
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
PRODUCT_SUFFIX_RE = re.compile(
    r"(?i)\s+(sticker|transparent sticker|glossy sticker|classic t-shirt|essential t-shirt|premium t-shirt|t-shirt|tee|"
    r"pullover hoodie|zipped hoodie|lightweight hoodie|hoodie|pullover sweatshirt|sweatshirt)s?\.?$")


def clean_store_title(alt):
    t = html.unescape(alt or "").strip()
    t = re.sub(r"(?i)^item preview,?\s*", "", t)
    t = re.sub(r"(?i)\s+designed and sold by\s+.*$", "", t)
    t = PRODUCT_SUFFIX_RE.sub("", t)
    return t.strip(" .,-")


def best_src(img_tag):
    """Najveća slika iz srcset-a (ako postoji), inače src / data-src."""
    srcset = re.search(r'(?:data-)?srcset="([^"]+)"', img_tag)
    if srcset:
        # Redbubble adrese same sadrže zareze ("st,small,507x507"), pa se deli samo ispred novog "https://"
        parts = re.split(r",\s+(?=https?://)", html.unescape(srcset.group(1)))
        cands = [c.strip().split(" ")[0] for c in parts if "redbubble.net" in c]
        if cands:
            return cands[-1]
    m = re.search(r'(?:data-)?src="(https://ih\d\.redbubble\.net/[^"]+)"', img_tag)
    return html.unescape(m.group(1)) if m else None


def store_get(url, timeout=25):
    """GET za Redbubble. Ako ga zaštita od botova odbije, drugi pokušaj ide preko curl_cffi koji se predstavlja kao
    pravi Chrome (često prolazi gde obični requests ne prolazi). Vraća (status_kod, tekst, bajtovi)."""
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
        code, text, content = r.status_code, r.text or "", r.content
    except Exception as e:
        code, text, content = 0, str(e), b""
    if code == 200 and "cf-chl" not in text[:20000] and "Just a moment" not in text[:5000]:
        return code, text, content
    try:
        from curl_cffi import requests as creq
        r2 = creq.get(url, impersonate="chrome", timeout=timeout)
        print(f"Shop: drugi pokušaj (kao Chrome) -> HTTP {r2.status_code}")
        return r2.status_code, r2.text or "", r2.content
    except ImportError:
        return code, text, content
    except Exception as e:
        print(f"Shop: drugi pokušaj nije uspeo ({str(e)[:100]})")
        return code, text, content


def product_type(link):
    """'/i/sticker/...' -> 'stickers', '/i/hoodie/...' ili '/i/sweatshirt/...' -> 'hoodies', '/i/t-shirt/...' -> 't-shirts'."""
    m = re.search(r"/i/([a-z0-9-]+)/", link)
    t = m.group(1) if m else ""
    if "sticker" in t:
        return "stickers"
    if "hoodie" in t or "sweatshirt" in t:
        return "hoodies"
    if "t-shirt" in t or t.endswith("tee"):
        return "t-shirts"
    return t or None


def fetch_store_products(animal, product=None, limit=4):
    """Pretraga TVOG Redbubble shopa (tvoj nalog + životinja [+ vrsta proizvoda]).
    Vraća (status, proizvodi). status: 'ok' (ima proizvoda), 'empty' (shop nema ništa za tu životinju),
    'blocked' (Redbubble odbio pristup), 'unparsed' (stranica stigla, ali joj se promenio izgled), 'off'."""
    if not USE_STORE_IMAGES:
        return "off", []
    url = shop_url(animal, product)
    code, body, _ = store_get(url)
    if code != 200 or "cf-chl" in body[:20000] or "Just a moment" in body[:5000]:
        print(f"Shop: Redbubble je odbio pristup (HTTP {code}).")
        return "blocked", []
    items = parse_store_items(body, limit)
    if not items and len(re.findall(r"ih\d\.redbubble\.net", body)) >= 5:
        print("Shop: stranica je stigla, ali bot ne prepoznaje proizvode na njoj (Redbubble je promenio izgled).")
        return "unparsed", []
    print(f"Shop: '{animal}'{' / ' + product if product else ''} -> {len(items)} proizvoda.")
    return ("ok" if items else "empty"), items


def parse_store_items(body, limit=24):
    """Proizvodi sa Redbubble stranice: naslov (iz alt teksta slike), link proizvoda, slika, vrsta proizvoda."""
    items, seen = [], set()
    for m in re.finditer(r'<a\b[^>]*href="([^"]*/i/[^"]+)"[^>]*>(.*?)</a>', body, re.S | re.I):
        img = re.search(r'<img\b[^>]*>', m.group(2), re.I)
        if not img or "redbubble.net" not in img.group(0):
            continue
        href = html.unescape(m.group(1))
        link = (href if href.startswith("http") else "https://www.redbubble.com" + href).split("?")[0]
        if link in seen:
            continue
        alt = re.search(r'alt="([^"]*)"', img.group(0))
        title = clean_store_title(alt.group(1) if alt else "")
        src = best_src(img.group(0))
        if not title or not src or PROFANITY_RE.search(title):
            continue
        seen.add(link)
        items.append({"title": title, "phrase": title.split(" - ")[0] if " - " in title else "", "link": link,
                      "img_url": src, "ptype": product_type(link)})
        if len(items) >= limit:
            break
    return items


def scan_shop_inventory(animals, check, today, max_pages=40):   # ~1500 dizajna = oko 25 strana
    """Jednom dnevno prođe kroz stranice tvog shopa (redbubble.com/people/<ti>/shop) i iz naslova dizajna vidi
    koje životinje stvarno imaš. Brže od provere jedne po jedne. Ne upisuje "nema" (shop može imati više strana)."""
    if not USE_STORE_IMAGES or check.get("__scan__", {}).get("date") == today.isoformat():
        return
    titles, page = [], 0
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(1.5)
        code, body, _ = store_get(f"https://www.redbubble.com/people/{SHOP_USERNAME}/shop?asc=u&page={page}")
        if code != 200 or "cf-chl" in body[:20000] or "Just a moment" in body[:5000]:
            if page == 1:
                print(f"Shop: pregled celog shopa nije uspeo (HTTP {code}).")
            break
        page_items = parse_store_items(body, limit=200)
        new = [it["title"] for it in page_items if it["title"] not in titles]
        if not new:
            break
        titles += new
    if not titles:
        return
    low = [t.lower() for t in titles]
    found = {}
    for a in animals:
        pat = re.compile(rf"(?<![a-z]){re.escape(a)}(?:e?s)?(?![a-z])")
        n = sum(1 for t in low if pat.search(t))
        if n:
            found[a] = n
            check[a] = {"count": n, "date": today.isoformat()}
    check["__scan__"] = {"date": today.isoformat(), "designs": len(titles)}
    print(f"Shop: pregledano {len(titles)} dizajna; životinje koje imaš: {', '.join(sorted(found)) or '(nijedna sa spiska)'}")


def download_store_image(src, side=1000):
    try:
        code, _, content = store_get(src, timeout=30)
        if code != 200:
            raise RuntimeError(f"HTTP {code}")
        im = Image.open(io.BytesIO(content)).convert("RGB")
        im.thumbnail((side, side), Image.Resampling.LANCZOS)
        return im
    except Exception as e:
        print(f"Slika proizvoda nije preuzeta: {str(e)[:120]}")
        return None


# ---------------------------------------------------------------------------
# UČITAVANJE POSTOJEĆIH ČLANAKA
# ---------------------------------------------------------------------------
def load_posts():
    posts = []
    for file in glob.glob("blog/*.html"):
        filename = os.path.basename(file)
        if filename == "index.html":
            continue
        try:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError:
            continue
        title_match = re.search(r'<h1>(.*?)</h1>', content, re.DOTALL)
        title = title_match.group(1).strip() if title_match else "Petzzz Article"
        date_known, date_str, dt_obj = False, "Unknown Date", datetime.datetime(2020, 1, 1)
        date_match = re.search(r'Published on (.*?) by', content)
        if date_match:
            date_str = date_match.group(1).strip()
            try:
                dt_obj = datetime.datetime.strptime(date_str, '%B %d, %Y')
                date_known = True
            except ValueError:
                pass
        img_url = "Logo 2.png"
        for img in re.findall(r'<img\s+src="([^"]+)"', content):
            if "logo" not in img.lower():
                img_url = img.replace("../", "")
                break
        meta = {k: html.unescape(v) for k, v in re.findall(r'<meta name="petzzz:(\w+)" content="([^"]*)">', content)}
        animal = meta.get("animal", "").lower()
        if not animal:
            m = re.search(r'alt="([^"]+?) lovers gift ideas"', content)
            animal = m.group(1).lower() if m else ""
        slug = filename[:-5]
        posts.append({
            "slug": slug, "clean_url": f"/blog/{slug}.html", "title": title, "date_str": date_str, "dt_obj": dt_obj,
            "date_known": date_known, "img_url": img_url, "animals": [animal] if animal else [],
            "angle": meta.get("angle"), "keyword": meta.get("keyword"), "product": meta.get("product"),
            "phrase": meta.get("phrase"),
        })
    return posts


def repair_old_links(shop_animals):
    # shop_animals = known_shop_animals(check): životinje za koje pretraga shopa ima smisla
    """Stari postovi su vodili na pretragu shopa za životinju za koju nemaš dizajne (prazna stranica).
    Takve linkove prebacuje na tvoj shop. Bezbedno je pokretati svaki put (menja samo pogrešne)."""
    fixed = 0
    pat = re.compile(r'https://www\.redbubble\.com/shop/\?query=([^&"]+)&(?:amp;)?artistUserName=' + re.escape(SHOP_USERNAME)
                     + r'(?:&(?:amp;)?iaCode=([a-z0-9-]+))?(?=["&<\s])')
    for file in glob.glob("blog/*.html"):
        try:
            with open(file, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        missing = set()

        def repl(m):
            q = urllib.parse.unquote_plus(m.group(1)).lower().strip()
            if q in shop_animals or q.rstrip("s") in shop_animals or any(
                    re.search(rf"(?<![a-z]){re.escape(q.rstrip('s'))}(?![a-z])", a) for a in shop_animals):
                return m.group(0)                    # npr. "cat": shop ima "black cat", "tabby cat" -> pretraga radi
            missing.add(q)
            if m.group(2):                           # zadrži vrstu proizvoda: tvoj shop filtriran na hoodie/sticker/majicu
                return f"https://www.redbubble.com/people/{SHOP_USERNAME}/shop?asc=u&amp;iaCode={m.group(2)}"
            return STORE_HOME_URL
        new = pat.sub(repl, content)
        if new != content:
            for q in missing:
                Q = q.title()
                new = new.replace(f"View Petzzz {Q} Collection", "Visit the Petzzz Shop")
                new = new.replace(f"See All Our {Q} Products", "Browse All Petzzz Designs")
                for label in ("Stickers", "T-Shirts", "Hoodies", "stickers", "t-shirts", "hoodies"):
                    new = new.replace(f"Shop {Q} {label}", f"Shop Petzzz {label}")
                    new = new.replace(f">{Q} {label}<", f">Petzzz {label}<")
                new = new.replace(f"all {q} designs", "all Petzzz designs")
            with open(file, "w", encoding="utf-8") as f:
                f.write(new)
            fixed += 1
    if fixed:
        print(f"Popravljeni linkovi u {fixed} starih postova (vodili su na praznu pretragu).")


# ---------------------------------------------------------------------------
# IZBOR ŽIVOTINJE, PROIZVODA I TEME
# ---------------------------------------------------------------------------
def load_shop_check():
    try:
        with open(SHOP_CHECK_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_shop_check(check):
    os.makedirs(os.path.dirname(SHOP_CHECK_FILE), exist_ok=True)
    with open(SHOP_CHECK_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(check.items())), f, ensure_ascii=False, indent=1)


def manual_shop_animals():
    """shop_animals.txt (ako postoji): dopune spiska, jedna životinja po redu."""
    if not os.path.exists(MANUAL_SHOP_FILE):
        return None
    with open(MANUAL_SHOP_FILE, encoding="utf-8") as f:
        names = [l.split("#")[0].strip().lower() for l in f]
    return [n for n in dict.fromkeys(names) if n]


def shop_list():
    """Sve životinje iz tvog shopa: SHOP_ANIMALS (gore u kodu) + dopune iz shop_animals.txt."""
    return list(dict.fromkeys([a.lower() for a in SHOP_ANIMALS] + (manual_shop_animals() or [])))


def checked_empty(check, animal, today):
    c = check.get(animal)
    if not c or c.get("count", 0) > 0:
        return False
    try:
        return (today - datetime.date.fromisoformat(c["date"])).days < RECHECK_DAYS
    except (KeyError, ValueError):
        return False


def known_shop_animals(check):
    """Za popravku linkova: životinje za koje pretraga shopa ima smisla (bez onih za koje je shop potvrđeno prazan)."""
    return set(shop_list()) | {a for a, c in check.items() if c.get("count", 0) > 0 and a != "__scan__"}


def choose_animal(posts, today):
    """Bira životinju SAMO sa spiska SHOP_ANIMALS (+ shop_animals.txt). Prednost imaju one o kojima je najmanje
    pisano (popularne mogu duplo više), a preskaču se životinje iz poslednja 3 posta. Ako Redbubble pusti bota,
    uz životinju uzme i prave proizvode iz shopa (slike i linkovi). Vraća (životinja, proizvodi_iz_shopa, izvor)."""
    counts = Counter(a for p in posts for a in p["animals"])
    pool = shop_list()
    check = load_shop_check()
    scan_shop_inventory(set(pool) | load_shop_animals() | EXTRA_ANIMALS | PET_ANIMALS, check, today)
    recent = {a for p in sorted(posts, key=lambda x: x["dt_obj"], reverse=True)[:3] for a in p["animals"]}
    random.shuffle(pool)
    ordered = sorted(pool, key=lambda a: (a in recent, checked_empty(check, a, today),
                                          counts[a] / (2 if a in POPULAR_ANIMALS else 1)))

    checked = set()
    if USE_STORE_IMAGES:
        for n, animal in enumerate(ordered[:MAX_SHOP_CHECKS]):
            if n:
                time.sleep(1.5)                  # pristojno prema Redbubble-u
            status, items = fetch_store_products(animal, None, limit=24)
            if status not in ("ok", "empty"):
                break                            # Redbubble ne pušta bota: bira se samo po spisku
            check[animal] = {"count": len(items), "date": today.isoformat()}
            checked.add(animal)
            if items:
                save_shop_check(check)
                print(f"Izabrana životinja: {animal} (sa spiska, u shopu nađeno {len(items)} proizvoda, "
                      f"{counts[animal]} ranijih postova)")
                return animal, items, "shop"
            print(f"Pretraga shopa za '{animal}' ne vraća proizvode (možda je u naslovima drugačije napisana): "
                  f"probam sledeću sa spiska.")
        save_shop_check(check)
    animal = next((a for a in ordered if a not in checked), ordered[0])
    print(f"Izabrana životinja sa spiska: {animal} ({counts[animal]} ranijih postova; slike pravi Fal.ai).")
    return animal, [], "spisak"


def pick_product(animal, posts, today, available=None):
    used = Counter(p["product"] for p in posts if animal in p["animals"] and p.get("product"))
    order = ["hoodies", "stickers", "t-shirts"] if today.month in (10, 11, 12, 1, 2) else ["stickers", "t-shirts", "hoodies"]
    if available:                            # samo vrste proizvoda koje ta životinja stvarno ima u shopu
        order = [p for p in order if p in available] or order
    least = min(used[p] for p in order)
    product = next(p for p in order if used[p] == least)
    print(f"Izabran proizvod: {product}")
    return product


def pick_angle(animal, product, posts, today, has_idiom):
    mine = [p for p in posts if animal in p["animals"]]
    used = Counter((p["angle"], p.get("product")) for p in mine)
    allowed = [a for a in ANGLES if product in a["products"] and (a.get("needs") != "idiom" or has_idiom)]
    seasonal = [a for a in allowed if a.get("window") and in_window(today, *a["window"])
                and not any(p["angle"] == a["id"] and p["dt_obj"].year == today.year for p in mine)]
    evergreen = [a for a in allowed if not a.get("window")]
    if seasonal and random.random() < 0.5:
        chosen = random.choice(seasonal)
    else:
        least = min(used[(a["id"], product)] for a in evergreen)
        fresh = [a for a in evergreen if used[(a["id"], product)] == least]
        if has_idiom and any(a["id"] == "idiom-meaning" for a in fresh) and random.random() < 0.45:
            chosen = next(a for a in fresh if a["id"] == "idiom-meaning")      # idiomi: velika pretraga na Google-u
        else:
            chosen = random.choice(fresh)
    print(f"Izabrana tema: {chosen['id']} ({chosen['label']})")
    return chosen


# ---------------------------------------------------------------------------
# GEMINI
# ---------------------------------------------------------------------------
def generate_with_fallback(client, prompt, label, json_mode=False, temperature=0.8, accept=None, grounded=False):
    """Prolazi kroz modele. accept(text) -> bool. Ako nijedan ne prođe, vraća najduži dobijeni tekst."""
    best = None
    for model_name in GEMINI_MODELS:
        try:
            print(f"Pokušavam ({label}) sa modelom {model_name}...")
            kw = {"temperature": temperature}
            if grounded:
                kw["tools"] = [types.Tool(google_search=types.GoogleSearch())]
            elif json_mode:
                kw["response_mime_type"] = "application/json"
            resp = client.models.generate_content(model=model_name, contents=prompt,
                                                  config=types.GenerateContentConfig(**kw))
            text = (getattr(resp, "text", None) or "").strip()
            if not text:
                continue
            if best is None or len(text) > len(best):
                best = text
            if accept is None or accept(text):
                print(f"Uspešno ({label}) sa {model_name}.")
                return text
            print(f"Rezultat sa {model_name} ne zadovoljava proveru ({label}), probam sledeći model.")
        except Exception as e:
            print(f"Greška na {model_name} ({label}): {str(e)[:200]}")
    return best


def extract_json(text):
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(text).strip(), flags=re.I).strip()
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r'\{.*\}', t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                return None
    return None


def trim_meta(desc, limit=158):
    desc = re.sub(r'\s+', ' ', desc or "").strip()
    if len(desc) <= limit:
        return desc
    cut = desc[:limit - 1]
    cut = cut[:cut.rfind(' ')] if ' ' in cut else cut
    return cut.rstrip(' ,;:-') + "…"


def designs_brief(items):
    lines = []
    for i, d in enumerate(items, 1):
        line = f'{i}. "{d["title"]}"'
        if d.get("phrase"):
            line += f' | phrase on the artwork: "{d["phrase"]}"'
        lines.append(line)
    return "\n".join(lines) or "(no specific products listed: describe the shop's style in general terms and do NOT name specific designs)"


def research_notes(client, animal, angle, idiom):
    """Google Search (grounding): proverene činjenice, da članak ne izmišlja. Greška = nastavljamo bez beleški."""
    if not USE_SEARCH_GROUNDING:
        return ""
    if angle["id"] == "idiom-meaning" and idiom:
        task = (f'Research the English idiom "{idiom}". Give: its meaning in one sentence; its documented origin and roughly '
                f'when it appeared (say clearly if the origin is disputed or unknown); 2 example sentences; 3 similar idioms. '
                f'Then 4 accurate facts about the {animal} that relate to the idiom or to the animal\'s behaviour.')
    else:
        task = (f"Find 10 accurate, interesting and well-documented facts about the {animal} (behaviour, habitat, diet, "
                f"quirks, record traits, conservation status). Prefer facts that are surprising or funny. "
                f"Use cautious wording for anything uncertain.")
    prompt = task + "\nReturn a plain bullet list (no intro, no markdown headings, no URLs). Each bullet max 35 words."
    text = generate_with_fallback(client, prompt, "istraživanje", temperature=0.3, grounded=True,
                                  accept=lambda t: t.count("\n") >= 4)
    if text:
        text = re.sub(r"https?://\S+", "", text)
        print(f"Beleške iz istraživanja: {len(text.splitlines())} redova.")
    return (text or "")[:3500]


def plan_topic(client, animal, product, angle, items, existing_titles, today):
    p = PRODUCTS[product]
    idioms = [d["phrase"] for d in items if d.get("phrase")]
    existing = "\n".join(f"- {html.unescape(t)}" for t in existing_titles) or "- (none yet)"
    prompt = f"""
You are a senior e-commerce SEO strategist for {BRAND}, an independent studio selling original, funny and relatable
animal designs (ADHD, introvert, tired, chaos and coffee humor) as {p['label']} and other products on Redbubble.

Plan ONE blog post that can realistically rank on Google for a small, new website and send readers to the shop.

ANIMAL: {animal}
PRODUCT FOCUS: {p['label']}
ANGLE: {angle['label']}
ANGLE DESCRIPTION: {fill(angle['brief'], animal, product, today, '<idiom>')}
TITLE STYLE EXAMPLE (adapt, do not copy): "{fill(angle['title_hint'], animal, product, today, '<idiom>')}"
TODAY: {today.strftime('%B %d, %Y')}
PHRASES ON THE SHOP'S PRODUCTS FOR THIS ANIMAL: {', '.join(f'"{i.title()}"' for i in idioms) or '(none found)'}

EXISTING POSTS ABOUT THIS ANIMAL (do NOT repeat or paraphrase them; target a different keyword):
{existing}

RULES
- featured_idiom: ONLY for the angle "idiom meaning and origin": a real, well-known English idiom or saying that people
  search the meaning of and that fits the {animal} (prefer one from the list above if it is a real idiom; otherwise pick a
  real idiom that a {animal} could act out literally, e.g. "Barking Up The Wrong Tree" for a dog). Normal case.
  If there is no good real idiom, return "". For other angles return "".
- image_phrase: 2-5 word original, funny, relatable phrase for an illustration of this post (for the idiom angle use the
  idiom itself). English, no brand names, no famous quotes.
- image_scene: max 30 words: what the {animal} does in the illustration (pose, expression, props and their colors;
  never pink, magenta or purple), acting out the phrase literally.
- primary_keyword: ONE phrase a real person types into Google (2-6 words, lowercase), specific long-tail. For the idiom
  angle use "<idiom> meaning". Otherwise it must contain "{animal}" and usually "{p['label']}" or "{p['one']}".
- secondary_keywords: 4-6 related long-tail phrases people genuinely search.
- title: max 60 characters (hard limit 66), primary keyword (or close variant) near the start, one concrete hook.
  Year {today.year} only for gift guides or seasonal posts. No clickbait, no ALL CAPS, no quotes, no trailing period.
- meta_description: 140-155 characters, includes the primary keyword once, a concrete benefit and a soft call to action.
- search_intent: "commercial", "informational" or "transactional".

Return ONLY a JSON object with the keys: featured_idiom, image_phrase, image_scene, title, primary_keyword,
secondary_keywords, meta_description, search_intent.
"""

    def ok(t):
        d = extract_json(t)
        return isinstance(d, dict) and 15 <= len(str(d.get("title", "")).strip()) <= 66 and d.get("primary_keyword")

    text = generate_with_fallback(client, prompt, "plan teme", json_mode=True, temperature=0.9, accept=ok)
    data = extract_json(text) if text else None
    if isinstance(data, dict) and ok(json.dumps(data)):
        idiom = str(data.get("featured_idiom") or "").strip().strip('"')
        if PROFANITY_RE.search(idiom):
            idiom = ""
        phrase = re.sub(r"[^A-Za-z0-9 '!?]", "", str(data.get("image_phrase") or idiom or ""))[:32].strip()
        plan = {
            "image_phrase": "" if PROFANITY_RE.search(phrase) else phrase,
            "image_scene": re.sub(r"(?i)\b(pink|magenta|purple|fuchsia|violet)\b", "red", str(data.get("image_scene") or ""))[:220],
            "title": str(data["title"]).strip().strip('"\'').rstrip('.'),
            "primary_keyword": str(data["primary_keyword"]).strip().lower(),
            "secondary_keywords": [str(x).strip().lower() for x in (data.get("secondary_keywords") or []) if str(x).strip()][:6],
            "meta_description": trim_meta(str(data.get("meta_description", ""))),
            "search_intent": str(data.get("search_intent", "commercial")).lower(),
            "featured_idiom": idiom,
        }
        print(f"Plan: '{plan['title']}' | ključna reč: {plan['primary_keyword']}" + (f" | idiom: {idiom}" if idiom else ""))
        return plan
    print("Plan teme nije uspeo, koristim rezervni plan.")
    kw = f"funny {animal} {p['label']}"
    return {"title": f"Funny {animal.title()} {p['label'].title()} for Every Mood"[:66], "primary_keyword": kw,
            "secondary_keywords": [f"{animal} {p['one']}", f"{animal} gift ideas", f"cute {animal} {p['label']}"],
            "meta_description": trim_meta(f"Looking for {kw}? Relatable, funny {animal} designs and practical tips for "
                                          f"choosing {p['label']}. See the collection."),
            "search_intent": "commercial", "featured_idiom": "", "image_phrase": "", "image_scene": ""}


# ---------------------------------------------------------------------------
# ČLANAK
# ---------------------------------------------------------------------------
def clean_article_html(raw):
    text = raw.strip()
    text = re.sub(r'^```(?:html)?\s*', '', text, flags=re.I)
    text = re.sub(r'\s*```$', '', text)
    text = re.sub(r'<!DOCTYPE[^>]*>', '', text, flags=re.I)
    text = re.sub(r'<head\b.*?</head>', '', text, flags=re.I | re.S)
    text = re.sub(r'</?(html|body|article|section|div|span)\b[^>]*>', '', text, flags=re.I)
    text = re.sub(r'<(script|style|iframe)\b.*?</\1>', '', text, flags=re.I | re.S)
    text = re.sub(r'<h1\b.*?</h1>', '', text, flags=re.I | re.S)
    text = re.sub(r'<(img|a)\b[^>]*>', '', text, flags=re.I)
    text = re.sub(r'</a>', '', text, flags=re.I)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'^###\s+(.+)$', r'<h3>\1</h3>', text, flags=re.M)
    text = re.sub(r'^##\s+(.+)$', r'<h2>\1</h2>', text, flags=re.M)
    text = re.sub(r'<!--\s*design\s*:\s*(\d+)\s*-->', r'<!--DESIGN:\1-->', text, flags=re.I)
    return text.strip()


def build_article_prompt(animal, product, angle, plan, designs, notes, today):
    p = PRODUCTS[product]
    sec = ", ".join(plan["secondary_keywords"]) or "(none)"
    idiom = plan.get("featured_idiom", "")
    audience = (f"{animal} owners, pet parents and gift shoppers" if is_pet(animal)
                else f"people who love {animal}s, meme lovers and gift shoppers")
    notes_block = notes.strip() or "(no research notes available: stay general, do not invent specific facts or dates)"
    n = len(designs)
    marker_rule = (f"- After the paragraph where you discuss a shop product, put the exact marker <!--DESIGN:k--> on its own "
                   f"line (k = the product's number, 1-{n}). Use each marker once; markers for at least {min(n, 3)} products. "
                   f"The marker is replaced by a picture of that product with a shop button, so do not describe buttons or links."
                   if n else "- There are no specific products to show; do not use any markers and do not name specific designs.")
    return f"""
You are a warm, funny and knowledgeable writer for {BRAND}, an independent studio that turns real animal traits and
everyday struggles (ADHD brain, introvert life, Mondays, coffee, social battery) into relatable designs sold as
{p['label']} and other products on Redbubble. You write like a person, not like a brochure.

ARTICLE TITLE (already decided, do NOT output it): "{plan['title']}"
PRIMARY KEYWORD: "{plan['primary_keyword']}"
SECONDARY KEYWORDS (use naturally where they fit): {sec}
ANIMAL: {animal}
PRODUCT FOCUS: {p['label']}
AUDIENCE: {audience}
ANGLE: {fill(angle['brief'], animal, product, today, idiom)}
TODAY: {today.strftime('%B %d, %Y')}

REAL PRODUCTS FROM THE SHOP (talk about these by name; never invent other designs or products):
{designs_brief(designs)}

RESEARCH NOTES FROM GOOGLE SEARCH (the only source for facts, dates and origins; do not add facts beyond these):
{notes_block}

STORY AND STRUCTURE (HTML body only)
1. Hook: open with a short, vivid scene (2-3 sentences, second person, present tense) that the reader instantly
   recognises; connect it to the {animal}. Use the primary keyword naturally within the first 100 words.
2. The first <h2> section opens with a direct 40-60 word answer to what the title promises (featured-snippet style).
3. 5-7 <h2> sections with descriptive headings that contain natural search phrases (never "Introduction"/"Conclusion").
   Use <h3> for individual items, <ul>/<ol> for lists, at most one small <table> if it truly helps.
4. Keep one narrative thread through the article (the opening scene comes back at the end). Mix short and long sentences,
   use concrete details and light humour. For each shop product you feature, explain the joke (from its title), the real
   {animal} trait behind it and who will feel seen by it; do not describe artwork details you cannot know.
5. Give real, practical {p['label']} advice where it fits (for stickers: placement, applying without bubbles, keeping them
   looking good; for t-shirts and hoodies: fit, sizing, print care, styling, gifting the right size). Speak in general terms
   about materials and finishes; do not claim specific specs, prices, discounts or shipping times.
6. A short wrap-up paragraph, then the exact comment <!--CTA--> on its own line, then
   <h2>Frequently Asked Questions</h2> with 4-5 <h3> questions people really search about this topic, each answered in a
   40-70 word <p> whose first sentence answers directly.
{marker_rule}

RULES
- LENGTH: 1,100-1,600 words. Under 900 words is not acceptable.
- Accurate and honest: no invented statistics, studies, quotes, reviews, customer stories, awards or experts.
  No veterinary, medical or mental-health advice (ADHD/anxiety appear only as light, kind humour, never mocking).
- Mention {BRAND} or Redbubble at most 2 times. Do not name competitors or other brands.
- Use each of these exact phrases at least once in running text (not in headings): "{animal} {p['label']}", "{animal} gift ideas".
- Avoid these clichés completely: {', '.join(CLICHES[:12])}. At most one emoji in the whole article.
- Do NOT output <h1>, <html>, <head>, <body>, <style>, <script>, <img> or <a> tags (images and links are added automatically).
- Output raw HTML only with these tags: p, h2, h3, ul, ol, li, strong, em, table, thead, tbody, tr, th, td, plus the comments
  described above. No markdown, no code fences, no commentary.
"""


def cliche_count(text):
    low = re.sub(r'<[^>]+>', ' ', text).lower()
    return sum(low.count(c) for c in CLICHES)


def generate_article(client, animal, product, angle, plan, designs, notes, today):
    prompt = build_article_prompt(animal, product, angle, plan, designs, notes, today)

    def accept(text):
        c = clean_article_html(text)
        head = re.sub(r'<[^>]+>', ' ', c)[:900].lower()
        kw_words = [w for w in plan["primary_keyword"].split() if len(w) > 3]
        return (count_words(c) >= MIN_WORDS and len(re.findall(r'<h2\b', c, re.I)) >= 4 and cliche_count(c) <= 2
                and (not kw_words or sum(w in head for w in kw_words) >= max(1, len(kw_words) - 1)))

    raw = generate_with_fallback(client, prompt, "članak", temperature=0.85, accept=accept)
    if not raw:
        raise RuntimeError("Nijedan Gemini model nije vratio tekst. Pogledaj greške iznad.")
    cleaned = clean_article_html(raw)
    print(f"Članak: {count_words(cleaned)} reči, {cliche_count(cleaned)} klišea.")
    return cleaned


def auto_link_keywords(content, animal, max_links=4):
    """Linkuje prva pojavljivanja prodajnih fraza na TAČAN proizvod (sticker -> nalepnice, hoodie -> duksevi...)."""
    targets = {}
    for prod, info in PRODUCTS.items():
        url = shop_url(animal, prod)
        for form in {info["label"], info["one"], info["label"].replace("-", " "), info["one"].replace("-", " ")}:
            targets[f"{animal} {form}"] = url
    targets[f"{animal} gift ideas"] = shop_url(animal)
    targets[f"{animal} gifts"] = shop_url(animal)
    pattern = re.compile(r'\b(' + '|'.join(re.escape(k) for k in sorted(targets, key=len, reverse=True)) + r')\b', re.I)
    linked, skip_depth, out = set(), 0, []

    def repl(m):
        key = m.group(1).lower()
        url = targets.get(key) or next((u for k, u in targets.items() if k.lower() == key), None)
        if not url or url in linked or len(linked) >= max_links:
            return m.group(0)
        linked.add(url)
        return f'<a href="{esc(url)}" target="_blank" rel="noopener" class="inline-shop">{m.group(0)}</a>'

    for tok in re.split(r'(<[^>]+>)', content):
        if tok.startswith("<") and tok.endswith(">"):
            m = re.match(r'<(/?)(a|h[1-6])\b', tok, re.I)
            if m:
                skip_depth = max(0, skip_depth - 1) if m.group(1) else skip_depth + 1
            out.append(tok)
            continue
        if skip_depth == 0 and len(linked) < max_links:
            tok = pattern.sub(repl, tok)
        out.append(tok)
    return "".join(out)


def add_toc(content):
    used, headings = set(), []

    def repl(m):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        base = slugify(text) or "section"
        hid, n = base, 2
        while hid in used:
            hid, n = f"{base}-{n}", n + 1
        used.add(hid)
        headings.append((hid, text))
        return f'<h2 id="{hid}">{m.group(1)}</h2>'

    content = re.sub(r'<h2\b[^>]*>(.*?)</h2>', repl, content, flags=re.S | re.I)
    if len(headings) < 4:
        return content
    items = "".join(f'<li><a href="#{hid}">{esc(text)}</a></li>' for hid, text in headings)
    toc = f'<nav class="toc" aria-label="Table of contents"><strong>In this article</strong><ol>{items}</ol></nav>'
    idx = content.find('</p>')
    return toc + content if idx == -1 else content[:idx + 4] + toc + content[idx + 4:]


# ---------------------------------------------------------------------------
# SLIKE: NALEPNICE I MOCKUP ODEĆE OD TVOJIH DIZAJNA
# ---------------------------------------------------------------------------
PASTELS = [((255, 236, 210), (255, 214, 170)), ((214, 236, 255), (178, 214, 250)), ((226, 247, 230), (190, 232, 200)),
           ((240, 230, 255), (214, 200, 250)), ((255, 244, 200), (253, 226, 150)), ((255, 226, 226), (250, 196, 196))]
GARMENTS = {"black": (32, 32, 36), "heather": (186, 188, 194), "navy": (34, 44, 74), "white": (246, 246, 244)}


def bg_gradient(size, colors):
    (top, bottom), (w, h) = colors, size
    g = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g.resize((w, h))


def _fill_holes(mask):
    w, h = mask.size
    pad = Image.new("L", (w + 2, h + 2), 0)
    pad.paste(mask, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    return pad.point(lambda p: 0 if p == 128 else 255).crop((1, 1, w + 1, h + 1))


def sticker(design):
    """Die-cut nalepnica: beli rub oko spoljne konture + blaga senka (kako nalepnica izgleda uživo)."""
    border = max(10, int(max(design.size) * 0.035))
    pad = border * 3
    w, h = design.width + 2 * pad, design.height + 2 * pad
    a = Image.new("L", (w, h), 0)
    a.paste(design.getchannel("A"), (pad, pad))
    a = a.point(lambda p: 255 if p > 60 else 0)
    grown = a.filter(ImageFilter.GaussianBlur(border * 0.9)).point(lambda p: 255 if p > 8 else 0)
    grown = _fill_holes(grown).filter(ImageFilter.GaussianBlur(1.2))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.putalpha(grown.filter(ImageFilter.GaussianBlur(border * 0.7)).point(lambda p: int(p * 0.35)))
    out.alpha_composite(shadow, (int(border * 0.25), int(border * 0.45)))
    white = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    white.putalpha(grown)
    out.alpha_composite(white)
    out.alpha_composite(design, (pad, pad))
    bb = out.getchannel("A").getbbox()
    return out.crop(bb) if bb else out


def sticker_scene(designs, size=1200, seed=0):
    rnd = random.Random(seed)
    canvas = bg_gradient((size, size), PASTELS[seed % len(PASTELS)]).convert("RGBA")
    slots = {1: [(0.5, 0.5, 0.8)], 2: [(0.31, 0.38, 0.52), (0.69, 0.64, 0.52)],
             3: [(0.28, 0.3, 0.47), (0.72, 0.32, 0.44), (0.5, 0.72, 0.47)],
             4: [(0.28, 0.28, 0.43), (0.72, 0.28, 0.43), (0.28, 0.72, 0.43), (0.72, 0.72, 0.43)]}[min(len(designs), 4)]
    for d, (cx, cy, frac) in zip(designs, slots):
        st = sticker(d)
        st.thumbnail((int(size * frac), int(size * frac)), Image.Resampling.LANCZOS)
        st = st.rotate(rnd.uniform(-7, 7), resample=Image.Resampling.BICUBIC, expand=True)
        canvas.alpha_composite(st, (int(cx * size - st.width / 2), int(cy * size - st.height / 2)))
    return canvas.convert("RGB")


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def garment(kind, color, size=1200):
    """Ravni (vektorski) mockup duksa ili majice, crtan u kodu: nema troška i dizajn uvek sedne na grudi.
    Koordinate su u prostoru 1200x1200; slika i zona štampe se na kraju skaliraju na traženu veličinu."""
    S = 3
    final_size, size = size, 1200
    base = GARMENTS[color]
    dark = _shade(base, 0.72) if color != "black" else (18, 18, 20)
    line = _shade(base, 0.55) if color not in ("black", "navy") else _shade(base, 1.6)
    img = Image.new("RGBA", (size * S, size * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lw = 4 * S

    def poly(pts, **kw):
        d.polygon([(x * S, y * S) for x, y in pts], **kw)

    if kind == "hoodie":
        poly([(470, 250), (730, 250), (790, 360), (410, 360)], fill=dark)
        d.ellipse((440 * S, 175 * S, 760 * S, 400 * S), fill=base, outline=line, width=lw)
        poly([(365, 345), (300, 390), (215, 905), (300, 925), (372, 600)], fill=base, outline=line, width=lw)
        poly([(835, 345), (900, 390), (985, 905), (900, 925), (828, 600)], fill=base, outline=line, width=lw)
        poly([(215, 905), (300, 925), (292, 975), (205, 958)], fill=dark, outline=line, width=lw)
        poly([(985, 905), (900, 925), (908, 975), (995, 958)], fill=dark, outline=line, width=lw)
        poly([(365, 345), (835, 345), (850, 990), (350, 990)], fill=base, outline=line, width=lw)
        poly([(350, 990), (850, 990), (848, 1045), (352, 1045)], fill=dark, outline=line, width=lw)
        d.ellipse((505 * S, 300 * S, 695 * S, 420 * S), fill=dark, outline=line, width=lw)
        d.ellipse((530 * S, 330 * S, 670 * S, 425 * S), fill=_shade(dark, 0.7))
        poly([(440, 790), (760, 790), (800, 965), (400, 965)], outline=line, width=lw)
        cord = (235, 235, 235) if color != "white" else (200, 200, 200)
        for x0, x1 in ((560, 548), (640, 652)):
            d.line((x0 * S, 410 * S, x1 * S, 560 * S), fill=cord, width=6 * S)
        area = (600, 455, 390, 315)          # centar x, vrh, max širina, max visina dizajna
    else:
        poly([(390, 300), (250, 400), (318, 515), (395, 465)], fill=base, outline=line, width=lw)
        poly([(810, 300), (950, 400), (882, 515), (805, 465)], fill=base, outline=line, width=lw)
        poly([(390, 300), (520, 285), (600, 320), (680, 285), (810, 300), (805, 1030), (395, 1030)],
             fill=base, outline=line, width=lw)
        d.chord((515 * S, 245 * S, 685 * S, 345 * S), 0, 180, fill=dark, outline=line, width=lw)
        d.chord((532 * S, 252 * S, 668 * S, 328 * S), 0, 180, fill=_shade(dark, 0.75))
        area = (600, 390, 380, 430)
    size = final_size
    k = size / 1200
    area = tuple(int(v * k) for v in area)
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    noise = Image.effect_noise((size, size), 18).convert("L")
    tex = Image.merge("RGBA", [noise.point(lambda p: p // 6)] * 3 + [img.getchannel("A").point(lambda p: int(p * 0.25))])
    img.alpha_composite(tex)
    return img, area


def apparel_scene(design, kind, size=1200, seed=0):
    g = design.convert("L").resize((64, 64))
    a = design.getchannel("A").resize((64, 64))
    vals = [v for v, al in zip(g.getdata(), a.getdata()) if al > 128]
    lum = sum(vals) / max(1, len(vals)) / 255
    color = "black" if lum > 0.42 else "heather"            # svetao dizajn na crnom, taman na sivom
    canvas = bg_gradient((size, size), PASTELS[seed % len(PASTELS)]).convert("RGBA")
    gar, (cx, top, mw, mh) = garment(kind, color, size)
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow.putalpha(gar.getchannel("A").filter(ImageFilter.GaussianBlur(18)).point(lambda p: int(p * 0.28)))
    canvas.alpha_composite(shadow, (int(10 * size / 1200), int(18 * size / 1200)))
    canvas.alpha_composite(gar)
    d = design.copy()
    d.thumbnail((mw, mh), Image.Resampling.LANCZOS)
    canvas.alpha_composite(d, (int(cx - d.width / 2), int(top)))
    return canvas.convert("RGB")


def product_image(designs, product, size=1200, seed=0):
    kind = PRODUCTS[product]["kind"]
    if kind == "sticker":
        return sticker_scene(designs[:3], size, seed)
    return apparel_scene(designs[0], kind, size, seed)


def save_jpg(img, path, quality=86):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    return "/" + path


def store_collage(images, size=1200, seed=0):
    """Slike proizvoda iz shopa (već su fotografije proizvoda) složene na pastelnu pozadinu."""
    canvas = bg_gradient((size, size), PASTELS[seed % len(PASTELS)]).convert("RGBA")
    n = min(len(images), 4)
    cells = {1: [(100, 100, 1000)], 2: [(55, 320, 530), (615, 320, 530)],
             3: [(70, 70, 505), (625, 70, 505), (347, 625, 505)],
             4: [(70, 70, 505), (625, 70, 505), (70, 625, 505), (625, 625, 505)]}[n]
    for im, (x, y, side) in zip(images, cells):
        k = size / 1200
        x, y, side = int(x * k), int(y * k), int(side * k)
        tile = ImageOps.fit(im, (side, side), Image.Resampling.LANCZOS).convert("RGBA")
        mask = Image.new("L", (side, side), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, side - 1, side - 1), int(side * 0.05), fill=255)
        shadow = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(14)).point(lambda p: int(p * 0.3)))
        canvas.alpha_composite(shadow, (x + 8, y + 12))
        tile.putalpha(mask)
        canvas.alpha_composite(tile, (x, y))
    return canvas.convert("RGB")


# ---- Rezerva kad shop nije dostupan: Fal.ai crta NOVU ilustraciju za post ----
def chroma_cutout(img_bytes):
    """Skida jednobojnu magenta pozadinu (povezanu sa ivicom slike); unutrašnjost dizajna ostaje puna."""
    if np is None:
        return None
    rgb = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    a = np.asarray(rgb).astype(np.int32)
    h, w, _ = a.shape
    b = max(2, min(h, w) // 100)
    border = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    spread = float(np.percentile(np.sqrt(((border - bg) ** 2).sum(1)), 90))
    if spread > 60:
        return None
    t1 = min(70.0, max(35.0, spread + 15))
    d = np.sqrt(((a - bg) ** 2).sum(2))
    cand = Image.fromarray(((d < t1) * 255).astype(np.uint8), "L").copy()   # .copy(): Pillow 12 fromarray je samo-za-čitanje
    for x, y in [(x, 0) for x in range(0, w, 4)] + [(x, h - 1) for x in range(0, w, 4)] + \
                [(0, y) for y in range(0, h, 4)] + [(w - 1, y) for y in range(0, h, 4)]:
        if cand.getpixel((x, y)) == 255:
            ImageDraw.floodfill(cand, (x, y), 128)
    bgmask = np.asarray(cand) == 128
    alpha = Image.fromarray(np.where(bgmask, 0, 255).astype(np.uint8), "L").filter(ImageFilter.MinFilter(3))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    bb = alpha.getbbox()
    return out.crop(bb) if bb else out


def fal_design(animal, phrase, scene=""):
    """Nova ilustracija za post (kad shop nije dostupan): polu-realistična životinja, crna kontura, tekst u lenti,
    magenta pozadina koju bot skine, pa od nje napravi nalepnicu ili mockup majice/duksa."""
    if not FAL_KEY:
        return None
    phrase = re.sub(r"[^A-Za-z0-9 '!?]", "", phrase or "").upper()[:32]
    banner = (f"Banner & Text: at the very bottom below the animal, a horizontal ribbon banner filled with solid bright yellow "
              f"with a thick black outline, containing bold black typography reading exactly '{phrase}'. ") if phrase else \
             "There is NO text anywhere. "
    prompt = ("A standalone semi-realistic cartoon illustration graphic for a t-shirt design. "
              f"Subject: a {animal} with true-to-life proportions and natural colors, funny relatable expression"
              + (f": {scene}. " if scene else ". ") +
              "Style: semi-realistic cel-shaded illustration, crisp fur texture strokes, saturated colors, thick solid bold "
              "black outline around everything. " + banner +
              "Composition: centered, fully visible, isolated on a PURE SOLID HOT MAGENTA (#FF00FF) CHROMA KEY BACKGROUND.")
    try:
        r = requests.post("https://fal.run/fal-ai/z-image/turbo",
                          headers={"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"},
                          json={"prompt": prompt, "image_size": "square_hd",
                                "negative_prompt": "magenta, pink, purple, white border, sticker, frame, text outside banner, "
                                                   "photograph, 3d render, ground, shadow"}, timeout=120)
        r.raise_for_status()
        img = requests.get(r.json()["images"][0]["url"], timeout=60).content
        cut = chroma_cutout(img)
        if cut is not None:
            cut.thumbnail((900, 900), Image.Resampling.LANCZOS)
        return cut
    except Exception as e:
        print(f"Fal rezervni dizajn nije uspeo: {e}")
        return None


# ---------------------------------------------------------------------------
# HTML DELOVI
# ---------------------------------------------------------------------------
def design_card_html(item, img_path, product):
    p = PRODUCTS[product]
    url = esc(item["link"])
    name = item["title"].split(" - ")[0]
    rest = item["title"].split(" - ", 1)[1] if " - " in item["title"] else ""
    alt = esc(f"{item['title']} {p['one']}")
    img = (f'<a href="{url}" target="_blank" rel="noopener"><img src="{img_path}" alt="{alt}" width="600" height="600" '
           f'loading="lazy" decoding="async"></a>') if img_path else ""
    return (f'<figure class="design-card">{img}<figcaption><strong>{esc(name)}</strong>'
            + (f'<span>{esc(rest)}</span>' if rest else "")
            + f'<a class="btn" href="{url}" target="_blank" rel="noopener">Get this {esc(p["one"])} ➔</a>'
            '</figcaption></figure>')


def place_design_cards(content, cards):
    """<!--DESIGN:k--> markere menja karticama dizajna; dizajni koje model nije postavio idu u mrežu pre CTA."""
    used = set()

    def repl(m):
        k = int(m.group(1))
        if k in cards and k not in used:
            used.add(k)
            return cards[k]
        return ""
    content = re.sub(r'<!--DESIGN:(\d+)-->', repl, content)
    rest = [c for k, c in sorted(cards.items()) if k not in used]
    if rest:
        grid = f'<div class="design-grid">{"".join(rest)}</div>'
        if "<!--CTA-->" in content:
            content = content.replace("<!--CTA-->", grid + "<!--CTA-->", 1)
        else:
            content += grid
    return content


def cta_html(animal, product):
    p = PRODUCTS[product]
    others = [k for k in PRODUCTS if k != product]
    links = " · ".join(f'<a href="{esc(shop_url(animal, o))}" target="_blank" rel="noopener">{esc(animal.title())} '
                       f'{esc(PRODUCTS[o]["label"])}</a>' for o in others)
    return (f'<div class="cta-box"><p class="cta-title">Find your {esc(animal)} {esc(p["one"])}</p>'
            f'<a class="cta-btn" href="{esc(shop_url(animal, product))}" target="_blank" rel="noopener">'
            f'Shop {esc(animal.title())} {esc(p["label"].title())} 🛍️</a>'
            f'<p class="cta-more">Also: {links} · <a href="{esc(shop_url(animal))}" target="_blank" rel="noopener">'
            f'all {esc(animal)} designs</a></p></div>')


def insert_cta(content, animal, product):
    box = cta_html(animal, product)
    if "<!--CTA-->" in content:
        first, *rest = content.split("<!--CTA-->")
        return first + box + "".join(rest)
    faq = re.search(r'<h2\b[^>]*>\s*(Frequently Asked Questions|FAQ)', content, re.I)
    return content[:faq.start()] + box + content[faq.start():] if faq else content + box


# ---------------------------------------------------------------------------
# SEO HEAD, SCHEMA, POVEZANI ČLANCI
# ---------------------------------------------------------------------------
GA_SNIPPET = """<!-- Google Tag (gtag.js) - Google Analytics -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=__GA_ID__"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', '__GA_ID__');
    </script>""".replace("__GA_ID__", GA_MEASUREMENT_ID)

FONT_LINKS = """<link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">"""


def seo_head_tags(title, description, canonical, image=None, og_type="article", published=None):
    t, d = esc(title), esc(description)
    tags = [
        f'<meta name="description" content="{d}">',
        f'<link rel="canonical" href="{canonical}">',
        '<meta name="robots" content="index, follow, max-image-preview:large">',
        f'<meta property="og:type" content="{og_type}">',
        f'<meta property="og:site_name" content="{BRAND}">',
        f'<meta property="og:title" content="{t}">',
        f'<meta property="og:description" content="{d}">',
        f'<meta property="og:url" content="{canonical}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}">',
        f'<meta name="twitter:title" content="{t}">',
        f'<meta name="twitter:description" content="{d}">',
    ]
    if image:
        tags += [f'<meta property="og:image" content="{image}">', f'<meta name="twitter:image" content="{image}">',
                 f'<meta name="pinterest:description" content="{d}">']
    if published:
        tags += [f'<meta property="article:published_time" content="{published}">',
                 f'<meta property="article:modified_time" content="{published}">']
    tags.append(f'<link rel="alternate" type="application/rss+xml" title="{BRAND} Blog" href="https://{SITE_DOMAIN}/rss.xml">')
    return "\n    ".join(tags)


def build_jsonld(title, description, url, images, date_iso, keywords, animal):
    home = f"https://{SITE_DOMAIN}/"
    article = {
        "@type": "BlogPosting", "@id": f"{url}#article", "headline": title[:110], "description": description,
        "datePublished": date_iso, "dateModified": date_iso, "inLanguage": "en", "about": animal,
        "keywords": ", ".join(keywords), "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "author": {"@type": "Organization", "name": BRAND, "url": home},
        "publisher": {"@type": "Organization", "name": BRAND,
                      "logo": {"@type": "ImageObject", "url": f"https://{SITE_DOMAIN}{LOGO_PATH}"}},
    }
    if images:
        article["image"] = images[:6]
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": home},
        {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"https://{SITE_DOMAIN}/blog.html"},
        {"@type": "ListItem", "position": 3, "name": title, "item": url}]}
    return json.dumps({"@context": "https://schema.org", "@graph": [article, crumbs]}, ensure_ascii=False).replace("</", "<\\/")


def get_related_posts_html(current_slug, animal, posts, max_posts=3):
    others = [p for p in posts if p["slug"] != current_slug]
    if not others:
        return ""
    same = [p for p in others if animal in p["animals"]]
    rest = [p for p in others if animal not in p["animals"]]
    random.shuffle(same)
    random.shuffle(rest)
    selected = (same[:2] + rest + same[2:])[:max_posts]
    cards = "".join(
        f'<a class="related-card" href="{p["clean_url"]}"><img src="{esc(site_img(p["img_url"]))}" alt="" loading="lazy" '
        f'width="80" height="80" onerror="this.style.display=\'none\'"><span>{p["title"]}</span></a>' for p in selected)
    return f'<section class="related"><h3>You Might Also Like 🐾</h3><div class="related-grid">{cards}</div></section>'


# ---------------------------------------------------------------------------
# SITEMAP / RSS / INDEXNOW
# ---------------------------------------------------------------------------
def update_sitemap(posts):
    known = [p["dt_obj"] for p in posts if p["date_known"]]
    latest = max(known).strftime('%Y-%m-%d') if known else None
    blog_lastmod = f"\n    <lastmod>{latest}</lastmod>" if latest else ""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
  <url>
    <loc>https://{SITE_DOMAIN}/</loc>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://{SITE_DOMAIN}/blog.html</loc>{blog_lastmod}
    <priority>0.9</priority>
  </url>
  <url>
    <loc>https://{SITE_DOMAIN}/privacy.html</loc>
    <priority>0.3</priority>
  </url>
"""
    for p in sorted(posts, key=lambda x: x["dt_obj"], reverse=True):
        lastmod = f"\n    <lastmod>{p['dt_obj'].strftime('%Y-%m-%d')}</lastmod>" if p["date_known"] else ""
        img = p["img_url"]
        image_tag = ""
        if img and "logo" not in img.lower() and not img.startswith("http"):
            loc = f"https://{SITE_DOMAIN}/{img.lstrip('/')}"
            image_tag = f"\n    <image:image><image:loc>{esc(loc)}</image:loc></image:image>"
        xml += f"""  <url>
    <loc>https://{SITE_DOMAIN}/blog/{p['slug']}.html</loc>{lastmod}{image_tag}
    <priority>0.8</priority>
  </url>\n"""
    xml += "</urlset>"
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(xml)
    for old in ["sitemap-main.xml", "sitemap-blog.xml"]:
        if os.path.exists(old):
            os.remove(old)
    print("sitemap.xml ažuriran (sa slikama za Google Images).")


def update_rss(title, post_url, content_summary, image_url=None):
    rss_file = "rss.xml"
    pub_date = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    text_only = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', content_summary)).strip()
    if len(text_only) > 350:
        short = text_only[:350]
        dot = short.rfind('.')
        text_only = short[:dot + 1] if dot != -1 else short + "..."
    if not os.path.exists(rss_file):
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "Petzzz Studio Blog"
        ET.SubElement(channel, "link").text = f"https://{SITE_DOMAIN}"
        ET.SubElement(channel, "description").text = "Latest posts and gift guides from Petzzz Studio"
    else:
        try:
            rss = ET.parse(rss_file).getroot()
            channel = rss.find("channel")
        except Exception:
            rss = ET.Element("rss", version="2.0")
            channel = ET.SubElement(rss, "channel")
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = post_url
    ET.SubElement(item, "guid").text = post_url
    ET.SubElement(item, "description").text = text_only
    ET.SubElement(item, "pubDate").text = pub_date
    if image_url:
        ET.SubElement(item, "enclosure", attrib={"url": image_url, "type": "image/jpeg", "length": "0"})
        ET.SubElement(item, "{http://search.yahoo.com/mrss/}content", attrib={"url": image_url, "medium": "image"})
    items = channel.findall("item")
    for old in items[:-60]:                 # RSS drži poslednjih 60 postova (manji fajl, brže čitanje)
        channel.remove(old)
    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write(rss_file, encoding="utf-8", xml_declaration=True)
    print("rss.xml ažuriran.")


def notify_indexnow(post_url):
    try:
        r = requests.post("https://api.indexnow.org/indexnow", timeout=10,
                          headers={"Content-Type": "application/json; charset=utf-8"},
                          json={"host": SITE_DOMAIN, "key": INDEXNOW_KEY,
                                "keyLocation": f"https://{SITE_DOMAIN}/{INDEXNOW_KEY}.txt",
                                "urlList": [post_url, f"https://{SITE_DOMAIN}/blog.html"]})
        print(f"IndexNow: {r.status_code}")
    except Exception as e:
        print(f"IndexNow nije uspeo: {e}")


# ---------------------------------------------------------------------------
# ŠABLONI
# ---------------------------------------------------------------------------
POST_CSS = """
        body { font-family: 'Poppins', sans-serif; background: #f8f9fa; color: #333; margin:0; line-height:1.75; }
        header { background: #fff; border-bottom: 1px solid #eaeaea; padding: 15px 20px; }
        .nav-container { max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
        .logo-box { display: flex; align-items: center; text-decoration: none; gap: 10px; font-weight:700; color:#3a1c5c; }
        .logo-img { width: 40px; height: 40px; border-radius: 50%; }
        .shop-link { color:#7b2cbf; text-decoration:none; font-weight:600; }
        .container { max-width: 800px; margin: 40px auto; background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        h1 { color: #1c1328; font-size: 2.2em; margin-bottom: 10px; line-height: 1.2; }
        h2 { color: #7b2cbf; margin-top: 38px; line-height: 1.3; scroll-margin-top: 20px; }
        h3 { color: #3a1c5c; margin-top: 26px; line-height: 1.3; }
        .meta { color:#888; font-size:0.9em; margin: 0 0 18px 0; }
        .chips { display:flex; gap:8px; flex-wrap:wrap; margin: 0 0 22px 0; }
        .chips a { background:#e7d9fc; color:#7b2cbf; text-decoration:none; padding:4px 12px; border-radius:15px; font-size:0.85em; font-weight:600; }
        .hero { margin: 10px 0 28px 0; text-align:center; }
        .hero img { width:100%; max-width:620px; height:auto; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.08); }
        .hero figcaption { font-size:0.85em; color:#777; margin-top:8px; }
        .inline-shop { color:#7b2cbf; font-weight:600; }
        .toc { background:#f7f2fd; border-left:4px solid #7b2cbf; padding:15px 20px; border-radius:8px; margin:25px 0; }
        .toc strong { color:#3a1c5c; }
        .toc ol { margin:10px 0 0 0; padding-left:20px; }
        .toc a { color:#7b2cbf; text-decoration:none; }
        .design-card { margin: 22px 0; display:flex; gap:18px; align-items:center; background:#fbf9fe; border:1px solid #efe7fb; border-radius:12px; padding:14px; }
        .design-card img { width:190px; height:190px; object-fit:contain; border-radius:10px; background:#fff; flex-shrink:0; }
        .design-card figcaption { display:flex; flex-direction:column; gap:6px; }
        .design-card strong { color:#1c1328; font-size:1.05em; }
        .design-card span { color:#555; font-size:0.92em; line-height:1.5; }
        .design-card .btn { align-self:flex-start; background:#7b2cbf; color:#fff !important; text-decoration:none; padding:8px 16px; border-radius:8px; font-weight:600; font-size:0.9em; }
        .design-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap:14px; margin:25px 0; }
        .design-grid .design-card { flex-direction:column; text-align:center; margin:0; }
        .design-grid .design-card img { width:100%; height:auto; }
        .design-grid .design-card .btn { align-self:center; }
        .cta-box { text-align:center; background: linear-gradient(135deg, #f7f2fd, #e9fbfb); border-radius:14px; padding:24px 18px; margin:34px 0; }
        .cta-title { font-weight:700; color:#1c1328; font-size:1.15em; margin:0 0 12px 0; }
        .cta-btn { display:inline-block; padding:13px 28px; background:#00d2d3; color:#fff !important; text-decoration:none; border-radius:30px; font-weight:700; }
        .cta-more { font-size:0.88em; margin:14px 0 0 0; }
        .cta-more a { color:#7b2cbf; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 0.95em; }
        th, td { border: 1px solid #eaeaea; padding: 10px 12px; text-align: left; vertical-align: top; }
        th { background: #f7f2fd; color: #3a1c5c; }
        .breadcrumb { font-size: 0.85em; margin-bottom: 20px; color: #888; }
        .breadcrumb a { color: #7b2cbf; text-decoration: none; font-weight: 600; }
        .author-box { margin-top: 40px; padding: 18px 20px; background: #f7f2fd; border-radius: 10px; font-size: 0.92em; }
        .author-box p { margin: 6px 0 0 0; }
        .author-box a { color: #7b2cbf; font-weight: 600; }
        .related { margin-top:40px; padding-top:25px; border-top:1px solid #eaeaea; }
        .related-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:12px; }
        .related-card { display:flex; gap:12px; align-items:center; text-decoration:none; color:#1c1328; background:#fdfbfb; border:1px solid #eee; border-radius:10px; padding:10px; font-weight:600; font-size:0.92em; line-height:1.35; }
        .related-card img { width:64px; height:64px; object-fit:cover; border-radius:8px; flex-shrink:0; }
        footer { background: #1c1328; color: #bbb; text-align: center; padding: 30px 20px; margin-top: 50px; font-size: 0.9em; }
        footer a { color: #fff; }
        @media (max-width: 600px) {
            .container { padding: 22px; margin: 20px 12px; }
            h1 { font-size: 1.8em; }
            table { display: block; overflow-x: auto; }
            .design-card { flex-direction:column; text-align:center; }
            .design-card img { width:100%; height:auto; }
            .design-card .btn { align-self:center; }
        }
"""

INDEX_CSS = """
        body { font-family: 'Poppins', sans-serif; background: #f8f9fa; color: #333; margin:0; line-height:1.7; scroll-behavior: smooth; }
        header { background: #fff; border-bottom: 1px solid #eaeaea; padding: 15px 20px; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 10px rgba(0,0,0,0.02); }
        .nav-container { max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }
        .logo-box { display: flex; align-items: center; text-decoration: none; gap: 10px; font-weight:700; color:#3a1c5c; }
        .logo-img { width: 40px; height: 40px; border-radius: 50%; }
        .nav-links a { margin-left: 20px; text-decoration: none; color: #555; font-weight: 600; font-size: 0.9em; transition: color 0.2s; }
        .nav-links a:hover { color: #8e44ad; }
        .container { max-width: 800px; margin: 50px auto; padding: 0 20px; }
        h1 { color: #1c1328; font-size: 2.5em; margin-bottom: 30px; text-align:center; line-height: 1.2; }
        footer { background: #1c1328; color: #bbb; text-align: center; padding: 30px 20px; margin-top: 50px; font-size: 0.9em; }
        footer a { color: #fff; }
        .search-wrapper { max-width: 600px; margin: 0 auto 20px auto; position: relative; }
        .search-box { position: relative; display: flex; align-items: center; }
        .search-icon { position: absolute; left: 18px; width: 20px; height: 20px; color: #7b2cbf; pointer-events: none; }
        .search-input { width: 100%; padding: 14px 20px 14px 50px; font-size: 1em; font-family: 'Poppins', sans-serif; border: 2px solid #eaeaea; border-radius: 30px; outline: none; background: #ffffff; color: #333; box-shadow: 0 4px 12px rgba(0,0,0,0.04); transition: all 0.3s ease; box-sizing: border-box; }
        .search-input:focus { border-color: #7b2cbf; box-shadow: 0 4px 18px rgba(123, 44, 191, 0.18); }
        .filters { display:flex; gap:8px; justify-content:center; flex-wrap:wrap; margin: 0 0 28px 0; }
        .filters button { font-family:'Poppins', sans-serif; border:2px solid #e7d9fc; background:#fff; color:#7b2cbf; padding:6px 14px; border-radius:20px; font-weight:600; cursor:pointer; }
        .filters button.active { background:#7b2cbf; color:#fff; border-color:#7b2cbf; }
        .no-results { display: none; text-align: center; padding: 20px; color: #666; font-size: 1.1em; font-weight: 600; background: #fff; border-radius: 12px; margin-bottom: 20px; }
        .article-card { background: #fff; padding: 20px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); transition: transform 0.2s, box-shadow 0.2s; display: flex; align-items: center; gap: 20px; }
        .article-card:hover { transform: translateY(-3px); box-shadow: 0 6px 20px rgba(0,0,0,0.08); }
        .article-thumb { width: 100px; height: 100px; border-radius: 10px; object-fit: cover; flex-shrink: 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .article-content { flex: 1; }
        #backToTop { display: none; position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%); z-index: 99; border: none; outline: none; background-color: #7b2cbf; color: white; cursor: pointer; width: 50px; height: 50px; border-radius: 50%; font-size: 22px; font-weight: bold; box-shadow: 0 4px 15px rgba(123, 44, 191, 0.4); align-items: center; justify-content: center; }
        @media (max-width: 600px) {
            .nav-container { flex-direction: column; gap: 15px; padding: 5px 0; }
            .nav-links { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }
            .nav-links a { margin-left: 0; background: #f0ecf4; padding: 8px 16px; border-radius: 20px; color: #3a1c5c; }
            h1 { font-size: 2em; }
            .article-card { flex-direction: column; align-items: flex-start; gap: 15px; }
            .article-thumb { width: 100%; height: 180px; }
        }
"""

INDEX_JS = """
        var activeProduct = 'all';
        function applyFilters() {
            var filter = document.getElementById('petSearchInput').value.toLowerCase().trim();
            var visible = 0;
            document.querySelectorAll('.article-card').forEach(function(card) {
                var title = card.querySelector('h3').innerText.toLowerCase();
                var prod = card.getAttribute('data-product') || '';
                var ok = title.indexOf(filter) !== -1 && (activeProduct === 'all' || prod === activeProduct);
                card.style.display = ok ? 'flex' : 'none';
                if (ok) visible++;
            });
            document.getElementById('noResultsMessage').style.display = visible === 0 ? 'block' : 'none';
        }
        document.getElementById('petSearchInput').addEventListener('keyup', applyFilters);
        document.querySelectorAll('.filters button').forEach(function(b) {
            b.addEventListener('click', function() {
                document.querySelectorAll('.filters button').forEach(function(x) { x.classList.remove('active'); });
                b.classList.add('active');
                activeProduct = b.getAttribute('data-product');
                applyFilters();
            });
        });
        var topBtn = document.getElementById('backToTop');
        window.onscroll = function() {
            topBtn.style.display = (document.documentElement.scrollTop > 300 || document.body.scrollTop > 300) ? 'flex' : 'none';
        };
        topBtn.onclick = function() { window.scrollTo({ top: 0, behavior: 'smooth' }); };
"""


def update_blog_index(posts):
    articles = sorted(posts, key=lambda x: x['dt_obj'], reverse=True)
    cards = ""
    for a in articles:
        img = site_img(a['img_url'])
        label = {"stickers": "Stickers", "t-shirts": "T-Shirts", "hoodies": "Hoodies"}.get(a.get("product") or "", "")
        cards += f"""
        <div class="article-card" data-product="{esc(a.get('product') or '')}">
            <a href="{a['clean_url']}">
                <img src="{esc(img)}" alt="{esc(html.unescape(a['title']))}" class="article-thumb" width="100" height="100" loading="lazy" onerror="this.src='{LOGO_PATH}'">
            </a>
            <div class="article-content">
                <h3 style="margin-top:0; font-size:1.3em; line-height:1.3;"><a href="{a['clean_url']}" style="text-decoration:none; color:#1c1328;">{a['title']}</a></h3>
                <p style="font-size:0.85em; color:#888; margin-bottom:12px;">Published on {a['date_str']}{(' · ' + label) if label else ''}</p>
                <a href="{a['clean_url']}" style="display:inline-block; padding:8px 16px; background:#e7d9fc; color:#7b2cbf; text-decoration:none; border-radius:6px; font-weight:600; font-size:0.85em;">Read Article ➔</a>
            </div>
        </div>"""
    page_title = "Funny Animal Gift Guides, Stickers & Hoodies | Petzzz Studio"
    page_desc = ("Relatable animal humor, gift guides and idiom stories: funny stickers, t-shirts and hoodies "
                 "for introverts, overthinkers and animal lovers from Petzzz Studio.")
    head_tags = seo_head_tags(page_title, page_desc, f"https://{SITE_DOMAIN}/blog.html", og_type="website")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc(page_title)}</title>
    {head_tags}
    {GA_SNIPPET}
    <link rel="icon" type="image/png" href="{LOGO_PATH}">
    {FONT_LINKS}
    <style>{INDEX_CSS}</style>
</head>
<body>
    <header>
        <div class="nav-container">
            <a href="/" class="logo-box"><img src="{LOGO_PATH}" alt="Petzzz Logo" class="logo-img"><span>Petzzz Studio</span></a>
            <div class="nav-links">
                <a href="/">Home Store</a>
                <a href="{STORE_HOME_URL}" target="_blank" rel="noopener">Redbubble Shop</a>
            </div>
        </div>
    </header>
    <main class="container">
        <h1>Latest Articles & Gift Guides</h1>
        <div class="search-wrapper">
            <div class="search-box">
                <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                <input type="text" id="petSearchInput" class="search-input" placeholder="Search by animal (e.g. Capybara, Pug)..." aria-label="Search articles by animal">
            </div>
        </div>
        <div class="filters">
            <button class="active" data-product="all">All</button>
            <button data-product="stickers">Stickers</button>
            <button data-product="t-shirts">T-Shirts</button>
            <button data-product="hoodies">Hoodies</button>
        </div>
        <div id="noResultsMessage" class="no-results">No articles found. Try another animal! 🐾</div>
        {cards}
    </main>
    <button id="backToTop" title="Go to top">↑</button>
    <footer><p>&copy; {datetime.date.today().year} Petzzz Studio. | <a href="/privacy.html">Privacy Policy</a></p></footer>
    <script>{INDEX_JS}</script>
</body>
</html>"""
    with open("blog.html", "w", encoding="utf-8") as f:
        f.write(page)


def optimize_blog_images(limit_kb=260, side=1200):
    """Smanjuje velike slike u blog/images (stare Flux slike su ~800 KB) na <= 1200 px i JPEG kvalitet 82.
    Ime fajla ostaje isto, pa se nijedan link ne menja. Posle prvog prolaza nema više šta da radi (brzo)."""
    saved, count = 0, 0
    for path in glob.glob(f"{POST_IMG_DIR}/*"):
        if not path.lower().endswith((".jpg", ".jpeg")) or os.path.getsize(path) <= limit_kb * 1024:
            continue
        try:
            before = os.path.getsize(path)
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((side, side), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=82, optimize=True, progressive=True)
            if buf.tell() < before:
                with open(path, "wb") as f:
                    f.write(buf.getvalue())
                saved += before - buf.tell()
                count += 1
        except Exception as e:
            print(f"Slika {path} nije smanjena: {e}")
    if count:
        print(f"Smanjeno {count} slika bloga, ušteđeno {saved // 1048576} MB.")


def update_home_latest(posts, count=6):
    """Na početnoj stranici (index.html) osvežava deo 'Latest Gift Guides & Stories' između oznaka
    <!--LATEST-POSTS:START--> i <!--LATEST-POSTS:END-->. Ako oznaka nema, ništa ne menja."""
    if not os.path.exists("index.html"):
        return
    with open("index.html", encoding="utf-8") as f:
        page = f.read()
    start, end = "<!--LATEST-POSTS:START-->", "<!--LATEST-POSTS:END-->"
    if start not in page or end not in page:
        return
    latest = sorted(posts, key=lambda x: x["dt_obj"], reverse=True)
    latest = [p for p in latest if not p["img_url"].startswith("http")][:count] or latest[:count]
    cards = "".join(
        f'\n            <a class="latest-card" href="{p["clean_url"]}"><img src="{esc(site_img(p["img_url"]))}" '
        f'alt="{esc(html.unescape(p["title"]))}" width="400" height="400" loading="lazy" decoding="async">'
        f'<span>{p["title"]}</span></a>' for p in latest)
    block = f'{start}\n        <div class="latest-grid">{cards}\n        </div>\n        {end}'
    a, b = page.index(start), page.index(end) + len(end)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(page[:a] + block + page[b:])
    print("Početna stranica: osveženi najnoviji članci.")


# ---------------------------------------------------------------------------
# GLAVNI TOK
# ---------------------------------------------------------------------------
def build_images(animal, product, slug, plan, store_items, today):
    """Slike iz shopa (ako ih ima) ili nova Fal.ai ilustracija. Kartice su numerisane kao proizvodi u promptu (1..n).
    Vraća (hero_path, hero_alt, cards{k: html}, apsolutni URL-ovi slika, from_shop)."""
    p = PRODUCTS[product]
    seed = int(today.strftime("%j"))
    hero_path, hero_alt, abs_images, cards = None, "", [], {}
    shop_imgs = []
    for k, item in enumerate(store_items, 1):
        im = download_store_image(item["img_url"])
        path = None
        if im is not None:
            shop_imgs.append(im)
            card = ImageOps.pad(im, (600, 600), color=(255, 255, 255))
            path = save_jpg(card, f"{POST_IMG_DIR}/{slug}-{k}.jpg", 84)
            abs_images.append(f"https://{SITE_DOMAIN}{path}")
        cards[k] = design_card_html(item, path, product)
    from_shop = bool(shop_imgs)
    if shop_imgs:
        hero = store_collage(shop_imgs, 1200, seed)
        names = [it["title"].split(" - ")[0] for it in store_items[:3]]
        hero_alt = f"{', '.join(names)} {animal} {p['label']}"
    else:
        art = fal_design(animal, plan.get("image_phrase", ""), plan.get("image_scene", ""))
        if art is None:
            return None, "", cards, abs_images, False
        hero = product_image([art], product, 1200, seed)
        name = plan.get("image_phrase", "").title() or f"Funny {animal.title()}"
        hero_alt = (f"{name} {animal} {p['one']} illustration" if p["kind"] == "sticker"
                    else f"{animal.title()} {p['one']} with a {name} illustration")
    hero_path = save_jpg(hero, f"{POST_IMG_DIR}/{slug}.jpg")
    abs_images.insert(0, f"https://{SITE_DOMAIN}{hero_path}")
    return hero_path, hero_alt, cards, abs_images, from_shop


def generate_post():
    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY nije pronađen u environment varijablama!")
    today = datetime.date.today()
    optimize_blog_images()                  # brže stranice: stare slike ~800 KB -> ~150 KB (jednom, pa ništa)
    posts = load_posts()
    today_count = sum(1 for p in posts if p["date_known"] and p["dt_obj"].date() == today)
    if today_count >= MAX_POSTS_PER_DAY:
        print(f"Danas je već objavljeno {today_count} post(a) (limit MAX_POSTS_PER_DAY={MAX_POSTS_PER_DAY}). "
              f"Preskačem: kvalitet je važniji od broja postova.")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    chosen = choose_animal(posts, today)
    repair_old_links(known_shop_animals(load_shop_check()))
    if chosen is None:
        # bez novog posta, ali spisak blogova, početna i sitemap se osvežavaju (npr. ako si obrisao neki post)
        update_blog_index(posts)
        update_home_latest(posts)
        update_sitemap(posts)
        return
    animal, shop_items, source = chosen
    available = {it["ptype"] for it in shop_items if it.get("ptype") in PRODUCTS}
    product = pick_product(animal, posts, today, available)
    angle = pick_angle(animal, product, posts, today, True)
    store_items = [it for it in shop_items if it.get("ptype") == product][:4]
    if source == "shop" and len(store_items) < 2:
        st, more = fetch_store_products(animal, product)
        known = {it["link"] for it in store_items}
        store_items += [it for it in more if it["link"] not in known][:4 - len(store_items)]

    existing_titles = [p["title"] for p in posts if animal in p["animals"]][:15]
    plan = plan_topic(client, animal, product, angle, store_items, existing_titles, today)
    if angle["id"] == "idiom-meaning" and not plan.get("featured_idiom"):
        print("Nema dobrog pravog idioma za ovu životinju: tema prelazi na 'funny-designs'.")
        angle = next(a for a in ANGLES if a["id"] == "funny-designs")
    if plan.get("featured_idiom"):           # proizvod sa tim idiomom ide prvi
        key = plan["featured_idiom"].lower()
        store_items.sort(key=lambda it: 0 if it.get("phrase", "").lower() == key else 1)

    notes = research_notes(client, animal, angle, plan.get("featured_idiom", ""))

    base_slug = "-".join(slugify(plan["primary_keyword"]).split("-")[:8]) or slugify(plan["title"])
    if slugify(animal) not in base_slug:
        base_slug = f"{base_slug}-{slugify(animal)}"
    slug, n = base_slug, 2
    while os.path.exists(f"blog/{slug}.html"):
        slug, n = f"{base_slug}-{n}", n + 1

    # tekst PRE slika: ako Gemini zakaže, ne trošimo Fal i ne ostavljamo slike bez posta
    article = generate_article(client, animal, product, angle, plan, store_items, notes, today)
    hero_path, hero_alt, cards, abs_images, from_shop = build_images(animal, product, slug, plan, store_items, today)
    article = place_design_cards(article, cards)
    article = auto_link_keywords(article, animal)
    article = insert_cta(article, animal, product)
    article = add_toc(article)
    related = get_related_posts_html(slug, animal, posts)

    p = PRODUCTS[product]
    topic = plan["title"]
    post_url = f"https://{SITE_DOMAIN}/blog/{slug}.html"
    suffix = " | Petzzz Studio"
    seo_title = topic + suffix if len(topic) + len(suffix) <= 62 else topic
    description = plan["meta_description"] or trim_meta(f"{topic}: funny, relatable {animal} {p['label']} and ideas.")
    og_image = abs_images[0] if abs_images else f"https://{SITE_DOMAIN}{LOGO_PATH}"
    date_iso = today.isoformat()
    keywords = [plan["primary_keyword"]] + plan["secondary_keywords"]
    head_tags = seo_head_tags(seo_title, description, post_url, image=og_image, published=date_iso)
    jsonld = build_jsonld(topic, description, post_url, abs_images, date_iso, keywords, animal)

    hero_html = ""
    if hero_path:
        hero_html = (f'<figure class="hero"><a href="{esc(shop_url(animal, product))}" target="_blank" rel="noopener">'
                     f'<img src="{hero_path}" alt="{esc(hero_alt)}" width="1200" height="1200" fetchpriority="high" '
                     f'decoding="async"></a><figcaption>{esc(hero_alt)}'
                     f'{" from the " + BRAND + " shop" if from_shop else " (illustration)"}</figcaption></figure>')
    chips = "".join(f'<a href="{esc(shop_url(animal, k))}" target="_blank" rel="noopener">{esc(animal.title())} '
                    f'{esc(v["label"].title())}</a>' for k, v in PRODUCTS.items())
    phrase_meta = plan.get("featured_idiom", "")

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc(seo_title)}</title>
    {head_tags}
    <meta name="petzzz:animal" content="{esc(animal)}">
    <meta name="petzzz:angle" content="{esc(angle['id'])}">
    <meta name="petzzz:product" content="{esc(product)}">
    <meta name="petzzz:keyword" content="{esc(plan['primary_keyword'])}">
    <meta name="petzzz:phrase" content="{esc(phrase_meta)}">
    <script type="application/ld+json">{jsonld}</script>
    {GA_SNIPPET}
    <link rel="icon" type="image/png" href="{LOGO_PATH}">
    {FONT_LINKS}
    <style>{POST_CSS}</style>
</head>
<body>
    <header>
        <div class="nav-container">
            <a href="/" class="logo-box"><img src="{LOGO_PATH}" alt="Petzzz Logo" class="logo-img" width="40" height="40"><span>Petzzz Studio</span></a>
            <a class="shop-link" href="{esc(shop_url(animal, product))}" target="_blank" rel="noopener">Shop {esc(animal.title())} {esc(p['label'].title())} 🛍️</a>
        </div>
    </header>
    <main class="container">
        <article>
        <nav class="breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a> › <a href="/blog.html">Blog</a> › <span>{esc(animal.title())}</span></nav>
        <h1>{esc(topic)}</h1>
        <p class="meta">Published on {today.strftime('%B %d, %Y')} by Petzzz Studio Team</p>
        <div class="chips">{chips}</div>
        {hero_html}
        {article}
        <div class="author-box">
            <strong>About {BRAND}</strong>
            <p>{BRAND} is an independent design studio turning real animal quirks and everyday chaos into funny, relatable art
            for stickers, t-shirts and hoodies, available in our <a href="{STORE_HOME_URL}" target="_blank" rel="noopener">Redbubble shop</a>.</p>
        </div>
        {related}
        </article>
    </main>
    <footer><p>&copy; {today.year} Petzzz Studio. | <a href="/privacy.html">Privacy Policy</a></p></footer>
</body>
</html>"""
    os.makedirs("blog", exist_ok=True)
    with open(f"blog/{slug}.html", "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Blog post kreiran: blog/{slug}.html")

    all_posts = load_posts()
    update_blog_index(all_posts)
    update_home_latest(all_posts)
    update_sitemap(all_posts)
    update_rss(topic, post_url, article, abs_images[0] if abs_images else None)
    notify_indexnow(post_url)


if __name__ == "__main__":
    generate_post()
