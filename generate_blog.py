import os
import re
import json
import glob
import html
import random
import datetime
import requests
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from google import genai
from google.genai import types

# Registracija media imenskog prostora za Pinterest/RSS kompatibilnost
ET.register_namespace("media", "http://search.yahoo.com/mrss/")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FAL_KEY = os.environ.get("FAL_KEY")
GA_MEASUREMENT_ID = "G-JHTGX1J5HX"

# Zvanični Gemini 3 modeli
GEMINI_MODELS = [
    'gemini-3.5-flash-lite',
    'gemini-3.8-flash',
    'gemini-3.7-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash',
    'gemini-3.1-flash-lite'
]

SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "petzzz.world")
INDEXNOW_KEY = "c8f1e2d3a4b5c6d7e8f9a0b1c2d3e4f5"

BRAND = "Petzzz Studio"
STORE_HOME_URL = "https://petzzz.redbubble.com"
LOGO_PATH = "/Logo%202.png"          # root-relative, radi i iz /blog/ i iz root-a
MIN_WORDS = 1000                     # ispod ovoga članak smatramo "tankim" i probamo sledeći model
SEASONAL_CHANCE = 0.5                # šansa da se u sezonskom prozoru izabere sezonska tema
POST_IMG_DIR = "blog/images"         # slike se čuvaju na SOPSTVENOM domenu (ne na Fal CDN-u)

# Lista životinja koje bot pokriva
ANIMALS_DATA = [
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

    # Gmizavci (Kornjače, zmije, gušteri)
    "turtle", "russian tortoise", "african sulcata tortoise",
    "blue pit viper", "hognose snake", "corn snake",
    "argentine tegu", "uromastyx", "leachianus gecko", "crested gecko",
    "red-eyed crocodile skink",

    # Vodozemci (Žabe)
    "poison dart frog", "pacman frog", "black rain frog", "dumpy tree frog",

    # Morske, vodene životinje i beskičmenjaci
    "sea otter", "harbor seal", "shark", "vampire crab", "sea sheep nudibranch",
    "blobfish", "jumping spider", "weevil",

    # Ostali sisari i egzotične vrste
    "capybara", "wombat", "honey badger", "beaver", "platypus",
    "maned wolf", "stoat", "tibetan fox", "binturong", "hedgehog"
]

# Životinje koje niko (ili skoro niko) ne drži kao ljubimca -> publika su "fanovi", ne "vlasnici".
# Time izbegavamo tekstove tipa "tips for blobfish owners" koji deluju kao loš AI sadržaj.
WILD_ANIMALS = {
    "spotted hyena", "pallas cat", "manul", "snow leopard", "jaguarundi",
    "canada goose", "crow", "great potoo", "cassowary", "pigeon", "emu",
    "bearded vulture", "blue pit viper", "black rain frog", "sea otter",
    "harbor seal", "shark", "vampire crab", "sea sheep nudibranch", "blobfish",
    "weevil", "capybara", "wombat", "honey badger", "beaver", "platypus",
    "maned wolf", "stoat", "tibetan fox", "binturong",
}

# Psi i mačke: jedine za koje pišemo "sympathy gift" članke (osetljiva tema, ima smisla samo za česte kućne ljubimce)
COMPANION_ANIMALS = {
    "corgi", "bernese mountain dog", "golden retriever", "border collie", "english bulldog",
    "basset hound", "belgian malinois", "shiba inu", "red heeler", "pug", "norwegian lundehund",
    "chihuahua", "samoyed", "pitbull", "husky", "dachshund", "afghan hound", "newfoundland dog",
    "cavalier king charles spaniel", "doberman", "cat", "black cat", "maine coon", "sphynx cat",
}

# Najtraženije životinje: dobijaju duplo više članaka u rotaciji
POPULAR_ANIMALS = {
    "cat", "black cat", "corgi", "golden retriever", "husky", "pug", "dachshund",
    "shiba inu", "chihuahua", "pitbull", "border collie", "maine coon",
    "bernese mountain dog", "english bulldog", "samoyed", "capybara", "hedgehog",
}

# ---------------------------------------------------------------------------
# UGLOVI / TEME (content angles)
# Svaki ugao cilja drugu nameru pretrage -> članci za istu životinju se ne takmiče međusobno
# (keyword cannibalization) i pokrivaju ceo "funnel": od "fun facts" do "buy ... gifts".
# ---------------------------------------------------------------------------
ANGLES = [
    # ---- Komercijalni / transakcioni ----
    {"id": "gift-guide", "label": "gift guide",
     "title_hint": "12 Best Gifts for {Animal} Lovers They'll Actually Use",
     "brief": "A gift guide listicle with 10-12 specific, creative gift ideas for people who love {animal}s. Group ideas by type (wearable, stickers and small gifts, home and desk). Each idea gets its own <h3> with a 60-100 word explanation of who it suits and why it works, ending with a 'Best for:' line."},
    {"id": "gifts-by-recipient", "label": "gifts by recipient",
     "title_hint": "Gifts for {Animal} Moms, Dads & Kids: Ideas for Everyone",
     "brief": "Gift ideas organised by recipient: a {animal}-loving mom, dad, teen or kid, coworker or friend, and 'treat yourself'. 2-3 ideas per recipient, each with the reasoning behind it."},
    {"id": "birthday-gifts", "label": "birthday gifts by budget",
     "title_hint": "Birthday Gift Ideas for {Animal} Lovers at Every Budget",
     "brief": "Birthday gift ideas grouped into budget-friendly, mid-range and splurge-worthy tiers (do NOT quote exact prices), plus a short 'how to choose the right gift' section about the person's style, size and taste."},
    {"id": "apparel-guide", "label": "t-shirt and hoodie buyer's guide",
     "title_hint": "{Animal} T-Shirts & Hoodies: How to Pick the Perfect One",
     "brief": "A practical buyer's guide to {animal} t-shirts and hoodies: design styles (cute, funny, minimalist, retro), fit and sizing tips, general fabric considerations, how to care for printed apparel so it lasts, 3 outfit ideas, and tips for gifting the right size."},
    {"id": "sticker-ideas", "label": "sticker ideas",
     "title_hint": "{Animal} Stickers: 15 Fun Ways to Use Them",
     "brief": "15 creative uses and placement ideas for {animal} stickers (laptop, water bottle, planner, journal, phone case, gift wrapping, sticker swaps...), plus practical tips on applying stickers cleanly and making them last."},
    {"id": "home-desk", "label": "home and desk decor",
     "title_hint": "{Animal} Decor & Desk Ideas for Cozy Fans",
     "brief": "Ideas to bring a {animal} theme into a bedroom, desk, reading corner and everyday carry (posters, pillows, mugs, tote bags, phone cases, stickers). Describe product types in general terms; do not promise that every product type exists in a specific shop."},
    {"id": "stocking-stuffers", "label": "stocking stuffers and secret santa",
     "title_hint": "{Animal} Stocking Stuffers & Secret Santa Gift Ideas",
     "brief": "Small, low-cost gift ideas for {animal} lovers that suit stocking stuffers, Secret Santa and office gift swaps. Include how to choose when you barely know the person, and gift wrapping ideas."},
    {"id": "aesthetic", "label": "aesthetic inspiration",
     "title_hint": "{Animal} Aesthetic: Outfit, Room & Desk Inspiration",
     "brief": "A Pinterest-style inspiration article: outfit ideas, room and desk styling, colour palettes and small details that give a cute {animal} aesthetic. Visual and descriptive, with a short mood/colour note for each idea."},
    # ---- Informacioni / "top of funnel" (privlače saobraćaj, vode ka prodavnici) ----
    {"id": "signs-you-are", "label": "relatable list",
     "title_hint": "15 Signs You're Officially a {Animal} Person",
     "brief": "A funny, relatable numbered list of signs you're a true {animal} person. Each item is an <h3> followed by 40-70 words with a specific, believable scenario. End with ways to proudly show it (apparel, stickers, small gifts)."},
    {"id": "fun-facts", "label": "fun facts",
     "title_hint": "Surprising {Animal} Facts You'll Want to Share",
     "brief": "10-12 accurate, widely documented fun facts about the {animal}. Each gets an <h3> and 40-70 words. Avoid precise numbers unless they are well established; if unsure, speak generally. Close with ways fans celebrate their love of the animal."},
    {"id": "captions-puns", "label": "captions and puns",
     "title_hint": "Cute {Animal} Captions & Puns for Instagram",
     "brief": "40+ original captions and puns about {animal}s grouped by mood (cute, funny, sassy, wholesome, seasonal). Do NOT reuse famous quotes or song lyrics. Add a short section with tips for writing your own caption."},
    {"id": "names", "label": "name ideas", "pet_only": True,
     "title_hint": "Cute {Animal} Names: 60+ Ideas by Theme",
     "brief": "60+ name ideas for a {animal}, grouped by theme (food, pop culture, nature, classic, funny, gender-neutral). For each name give a short reason or meaning. Include a short section on how to pick a name your pet will respond to and you will still love in ten years."},
    {"id": "why-we-love", "label": "fan article", "wild_only": True,
     "title_hint": "Why Everyone Is Obsessed With the {Animal}",
     "brief": "A fan-focused article on why people love the {animal}: quirks, genuinely interesting facts, internet and meme culture where applicable, and fun ways fans show their love. Accurate and warm, never written as if readers own the animal."},
    {"id": "memorial-gifts", "label": "sympathy gifts", "companion_only": True,
     "title_hint": "Thoughtful Gifts for Someone Grieving Their {Animal}",
     "brief": "A gentle, empathetic guide to choosing a thoughtful keepsake or gesture for someone who has lost their {animal}: meaningful gift ideas, what to write in the card, and what not to say. No hard selling; the tone is warm and respectful."},
    # ---- Sezonske teme (window = (mesec, dan) početak/kraj; objavljuje se ~6-10 nedelja ranije) ----
    {"id": "christmas", "label": "Christmas gift guide", "window": ((9, 15), (12, 5)),
     "title_hint": "{Animal} Christmas Gifts: 12 Festive Ideas for {year}",
     "brief": "A Christmas and holiday gift guide for {animal} lovers: stocking stuffers, cozy wearables, small gifts and one or two bigger ideas. Include a short 'order early' planning tip without making shipping promises."},
    {"id": "halloween", "label": "Halloween ideas", "window": ((8, 15), (10, 5)),
     "title_hint": "{Animal} Halloween Ideas: Outfits, Decor & Gifts",
     "brief": "Halloween ideas for people who love {animal}s: outfit ideas for people (not for dressing up animals), party and room decor, treat-bag gifts and sticker ideas."},
    {"id": "valentines", "label": "Valentine's gift guide", "window": ((12, 15), (1, 25)),
     "title_hint": "Valentine's Day Gifts for {Animal} Lovers",
     "brief": "Valentine's Day gift ideas for a partner, friend or yourself if you love {animal}s: sweet, funny and low-key options, plus card message ideas."},
    {"id": "mothers-day", "label": "Mother's Day gift guide", "window": ((3, 15), (4, 25)),
     "title_hint": "Mother's Day Gifts for {Animal} Moms: Ideas She'll Love",
     "brief": "Mother's Day gift ideas for moms who love {animal}s: sentimental, funny and practical options, plus short card message ideas."},
    {"id": "fathers-day", "label": "Father's Day gift guide", "window": ((4, 25), (5, 31)),
     "title_hint": "Father's Day Gifts for {Animal} Dads: Ideas He'll Wear",
     "brief": "Father's Day gift ideas for dads who love {animal}s: apparel, small gifts and desk or garage items, plus short card message ideas."},
]


# ---------------------------------------------------------------------------
# POMOĆNE FUNKCIJE
# ---------------------------------------------------------------------------
def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text).strip('-')


def esc(text):
    """HTML escape za atribute i tekst."""
    return html.escape(str(text), quote=True)


def is_pet(animal):
    return animal not in WILD_ANIMALS


def audience_for(animal):
    if is_pet(animal):
        return f"{animal} owners, pet parents and gift shoppers"
    return f"{animal} fans, animal lovers and gift shoppers"


def count_words(html_text):
    return len(re.sub(r'<[^>]+>', ' ', html_text).split())


def in_window(today, start, end):
    """Da li je današnji datum u prozoru (podržava prelazak preko Nove godine)."""
    s = datetime.date(today.year, start[0], start[1])
    e = datetime.date(today.year, end[0], end[1])
    if s <= e:
        return s <= today <= e
    return today >= s or today <= e


def detect_animals(text):
    """Pronalazi životinje u tekstu sa granicama reči (stari kod je koristio 'cat' in content,
    što je tačno u skoro svakom HTML-u: 'category', 'dedicated'...)."""
    text = " " + re.sub(r'[^a-z0-9\s-]', ' ', text.lower()) + " "
    found = []
    for a in sorted(ANIMALS_DATA, key=len, reverse=True):
        pat = rf'(?<![a-z0-9]){re.escape(a)}(?:e?s)?(?![a-z0-9])'
        if re.search(pat, text):
            found.append(a)
            text = re.sub(pat, " ", text)  # "black cat" ne računamo i kao "cat"
    return found


# ---------------------------------------------------------------------------
# UČITAVANJE POSTOJEĆIH ČLANAKA (jednom, koristi se svuda)
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

        date_known = False
        date_match = re.search(r'Published on (.*?) by', content)
        date_str = "Unknown Date"
        dt_obj = datetime.datetime(2020, 1, 1)
        if date_match:
            date_str = date_match.group(1).strip()
            try:
                dt_obj = datetime.datetime.strptime(date_str, '%B %d, %Y')
                date_known = True
            except ValueError:
                pass

        # Pronalaženje prave slike (preskače Logo 2.png iz headera)
        img_url = "Logo 2.png"
        for img in re.findall(r'<img\s+src="([^"]+)"', content):
            if "logo" not in img.lower():
                img_url = img.replace("../", "")
                break

        # Novi članci nose meta tagove; stari se prepoznaju po alt tekstu banera ili naslovu
        meta = {k: html.unescape(v) for k, v in
                re.findall(r'<meta name="petzzz:(\w+)" content="([^"]*)">', content)}
        animals = []
        if meta.get("animal") in ANIMALS_DATA:
            animals = [meta["animal"]]
        else:
            alt_match = re.search(r'alt="([^"]+?) lovers gift ideas"', content)
            if alt_match and alt_match.group(1).lower() in ANIMALS_DATA:
                animals = [alt_match.group(1).lower()]
            else:
                animals = detect_animals(html.unescape(title))

        slug = filename.replace(".html", "")
        posts.append({
            "slug": slug,
            "clean_url": f"/blog/{slug}.html",
            "title": title,
            "date_str": date_str,
            "dt_obj": dt_obj,
            "date_known": date_known,
            "img_url": img_url,
            "animals": animals,
            "angle": meta.get("angle"),
            "keyword": meta.get("keyword"),
        })
    return posts


# ---------------------------------------------------------------------------
# IZBOR ŽIVOTINJE I UGLA (TEME)
# ---------------------------------------------------------------------------
def get_next_animal(posts):
    counts = Counter()
    for p in posts:
        for a in p["animals"]:
            counts[a] += 1

    # Popularne životinje imaju duplo veću "težinu" -> češće se vraćaju na red
    def priority(a):
        return counts[a] / (2 if a in POPULAR_ANIMALS else 1)

    best = min(priority(a) for a in ANIMALS_DATA)
    candidates = [a for a in ANIMALS_DATA if priority(a) == best]
    chosen = random.choice(candidates)
    if counts[chosen] == 0:
        print(f"Izabrana nekorišćena životinja: {chosen}")
    else:
        print(f"Sve životinje su upotrebljene. Izabrana iz grupe najmanje korišćenih: {chosen}")
    return chosen


def pick_angle(animal, posts, today):
    pet = is_pet(animal)
    allowed = [a for a in ANGLES
               if not (a.get("pet_only") and not pet)
               and not (a.get("wild_only") and pet)
               and not (a.get("companion_only") and animal not in COMPANION_ANIMALS)]

    mine = [p for p in posts if animal in p["animals"] and p["angle"]]
    used_ids = {p["angle"] for p in mine}
    used_seasonal = {(p["angle"], p["dt_obj"].year) for p in mine}

    seasonal = [a for a in allowed
                if a.get("window") and in_window(today, *a["window"])
                and (a["id"], today.year) not in used_seasonal]
    evergreen = [a for a in allowed if not a.get("window")]
    fresh = [a for a in evergreen if a["id"] not in used_ids]

    if seasonal and random.random() < SEASONAL_CHANCE:
        chosen = random.choice(seasonal)
    elif fresh:
        chosen = random.choice(fresh)
    elif seasonal:
        chosen = random.choice(seasonal)
    else:
        usage = Counter(p["angle"] for p in mine)
        least = min(usage[a["id"]] for a in evergreen)
        chosen = random.choice([a for a in evergreen if usage[a["id"]] == least])

    print(f"Izabran ugao teme: {chosen['id']} ({chosen['label']})")
    return chosen


def fill(text, animal, today):
    return (text.replace("{animal}", animal)
                .replace("{Animal}", animal.title())
                .replace("{year}", str(today.year)))


# ---------------------------------------------------------------------------
# GEMINI POZIVI
# ---------------------------------------------------------------------------
def generate_with_fallback(client, prompt, label, json_mode=False, temperature=0.8, accept=None):
    """Prolazi kroz modele. accept(text) -> bool kaže da li je rezultat dovoljno dobar.
    Ako nijedan nije dovoljno dobar, vraća najduži dobijeni tekst."""
    best = None
    for model_name in GEMINI_MODELS:
        try:
            print(f"Pokušavam generisanje ({label}) pomoću modela: {model_name}...")
            cfg = types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json" if json_mode else None,
            )
            resp = client.models.generate_content(model=model_name, contents=prompt, config=cfg)
            text = (resp.text or "").strip() if resp else ""
            if not text:
                continue
            if best is None or len(text) > len(best):
                best = text
            if accept is None or accept(text):
                print(f"Uspešno ({label}) sa {model_name}!")
                return text
            print(f"Rezultat sa {model_name} ne zadovoljava kriterijume ({label}), probam sledeći model.")
        except Exception as e:
            print(f"Greška na {model_name} ({label}): {e}")
    return best


def trim_meta(desc, limit=158):
    desc = re.sub(r'\s+', ' ', desc or "").strip()
    if len(desc) <= limit:
        return desc
    cut = desc[:limit - 1]
    cut = cut[:cut.rfind(' ')] if ' ' in cut else cut
    return cut.rstrip(' ,;:-') + "…"


def parse_plan(text):
    """Parsira JSON plan teme; vraća None ako nije upotrebljiv."""
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip(), flags=re.I).strip()
    data = None
    try:
        data = json.loads(t)
    except ValueError:
        m = re.search(r'\{.*\}', t, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
            except ValueError:
                return None
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return None

    title = str(data.get("title", "")).strip().strip('"\'').rstrip('.')
    keyword = str(data.get("primary_keyword", "")).strip().lower()
    if len(title) < 15 or len(title) > 68 or not keyword:
        return None
    secondary = [str(x).strip().lower() for x in (data.get("secondary_keywords") or []) if str(x).strip()][:6]
    return {
        "title": title,
        "primary_keyword": keyword,
        "secondary_keywords": secondary,
        "meta_description": trim_meta(str(data.get("meta_description", ""))),
        "image_alt": re.sub(r'\s+', ' ', str(data.get("image_alt", ""))).strip()[:140],
        "search_intent": str(data.get("search_intent", "commercial")).strip().lower(),
    }


def plan_topic(client, animal, angle, existing_titles, today):
    audience = audience_for(animal)
    existing = "\n".join(f"- {html.unescape(t)}" for t in existing_titles) or "- (none yet)"
    title_hint = fill(angle["title_hint"], animal, today)
    angle_brief = fill(angle["brief"], animal, today)

    prompt = f"""
You are a senior e-commerce SEO strategist for {BRAND}, an independent studio selling original
animal-themed designs on t-shirts, hoodies, stickers and other gift items through Redbubble.

Plan ONE blog post that can realistically rank on Google and attract shoppers.

ANIMAL / NICHE: {animal}
AUDIENCE: {audience}
CONTENT ANGLE: {angle['label']}
ANGLE DESCRIPTION: {angle_brief}
TODAY: {today.strftime('%B %d, %Y')}

EXISTING POSTS ABOUT THIS ANIMAL (do NOT repeat or paraphrase these; target a clearly different keyword):
{existing}

TITLE STYLE EXAMPLE (adapt to the animal, do not copy blindly): "{title_hint}"

RULES FOR THE PLAN
- primary_keyword: ONE natural phrase a real person would type into Google (2-5 words, lowercase), matching the angle.
  Prefer specific long-tail phrases over very generic ones for a small new site.
- secondary_keywords: 4-6 related long-tail phrases people genuinely search for.
- title: max 60 characters (hard limit 66). Put the primary keyword (or a close variant) near the start.
  Include one concrete hook (a number, a recipient, an occasion or a clear benefit). Use the year {today.year}
  only for gift guides and seasonal posts. No clickbait, no ALL CAPS, no quotation marks, no trailing period.
- meta_description: 140-155 characters, includes the primary keyword once, states a concrete benefit,
  ends with a soft call to action. No quotation marks.
- image_alt: 8-14 words, plainly describes a cover photo of a {animal} that fits the topic. No keyword stuffing.
- search_intent: one of "commercial", "informational", "transactional".

Return ONLY a JSON object with exactly these keys:
title, primary_keyword, secondary_keywords (array), meta_description, image_alt, search_intent.
"""
    text = generate_with_fallback(client, prompt, "plan teme", json_mode=True, temperature=0.9,
                                  accept=lambda t: parse_plan(t) is not None)
    plan = parse_plan(text) if text else None
    if plan:
        print(f"Plan teme: '{plan['title']}' | ključna reč: {plan['primary_keyword']}")
        return plan

    print("Plan teme nije uspeo, koristim rezervni plan.")
    kw = f"{animal} gifts"
    return {
        "title": f"{animal.title()} Gifts: {today.year} Ideas for Lovers"[:66],
        "primary_keyword": kw,
        "secondary_keywords": [f"{animal} t-shirts", f"{animal} hoodies", f"{animal} stickers", f"{animal} gift ideas"],
        "meta_description": trim_meta(f"Looking for {kw}? Browse thoughtful, fun gift ideas for {audience}, "
                                      f"from t-shirts and hoodies to stickers."),
        "image_alt": f"Adorable {animal} portrait on a soft pastel background",
        "search_intent": "commercial",
    }


# ---------------------------------------------------------------------------
# ČLANAK
# ---------------------------------------------------------------------------
def clean_article_html(raw):
    """Uklanja ostatke modela: code fence-ove, markdown, html/body/script tagove i dupli H1."""
    text = raw.strip()
    text = re.sub(r'^```(?:html)?\s*', '', text, flags=re.I)
    text = re.sub(r'\s*```$', '', text)
    text = re.sub(r'<!DOCTYPE[^>]*>', '', text, flags=re.I)
    text = re.sub(r'<head\b.*?</head>', '', text, flags=re.I | re.S)
    text = re.sub(r'</?(html|body)\b[^>]*>', '', text, flags=re.I)
    text = re.sub(r'<(script|style|iframe)\b.*?</\1>', '', text, flags=re.I | re.S)
    text = re.sub(r'<h1\b.*?</h1>', '', text, flags=re.I | re.S)
    # ako je model ipak vratio markdown
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'^###\s+(.+)$', r'<h3>\1</h3>', text, flags=re.M)
    text = re.sub(r'^##\s+(.+)$', r'<h2>\1</h2>', text, flags=re.M)
    return text.strip()


def build_article_prompt(animal, angle, plan, today):
    sec = ", ".join(plan["secondary_keywords"]) or "(none)"
    angle_brief = fill(angle["brief"], animal, today)
    audience = audience_for(animal)
    return f"""
You are an experienced content writer and SEO editor for {BRAND}, an independent studio that sells
original animal-themed designs (t-shirts, hoodies, stickers and other gift items) on Redbubble.

Write a genuinely useful, original blog article.

ARTICLE TITLE (already decided, do NOT output it): "{plan['title']}"
PRIMARY KEYWORD: "{plan['primary_keyword']}"
SECONDARY KEYWORDS (use naturally where they fit): {sec}
ANIMAL: {animal}
AUDIENCE: {audience}
ANGLE: {angle_brief}
TODAY: {today.strftime('%B %d, %Y')} (mention the year {today.year} only where it is natural)

LENGTH: 1,300-1,700 words. Anything under 1,100 words is not acceptable.

STRUCTURE (HTML body only)
1. Intro: 2-3 short <p> paragraphs. Open with something concrete (a relatable moment or a surprising fact),
   never a generic statement. Use the primary keyword naturally within the first 100 words.
2. The first <h2> section starts with a direct 40-60 word answer to the main question the title promises
   (so Google can lift it as a featured snippet).
3. 5-7 <h2> sections in total with descriptive headings that contain natural search phrases
   (never "Introduction" or "Conclusion"). Use <h3> for individual items or sub-points, <ul>/<ol> for lists,
   and at most one simple <table> if it really helps compare options.
4. A short wrap-up paragraph, then the exact HTML comment <!--CTA--> on its own line, then the FAQ.
5. FAQ: a final <h2>Frequently Asked Questions</h2> with 4-5 <h3> questions people genuinely search for about this
   topic, each followed by a <p> answer of 40-70 words whose first sentence answers directly.

QUALITY RULES
- Write like a knowledgeable person who loves {animal}s: concrete details, specific scenarios, real traits and quirks.
  No filler openers ("In today's fast-paced world", "Look no further", "Whether you're a... or a..."),
  no repetitive sentence patterns, at most one emoji in the whole article.
- Be accurate. Do NOT invent statistics, studies, quotes, reviews, awards, prices, discounts, shipping promises or
  claims about materials and product quality that you cannot know. When unsure, speak in general terms.
- No veterinary, medical, training or pet-care advice.
- Be helpful first and commercial second. Mention {BRAND} or Redbubble at most 2-3 times. Talk about t-shirts, hoodies
  and stickers (and other gifts) with real buying advice (fit, sizing, print care, sticker placement and durability,
  gift wrapping). Use each of these exact phrases at least once in running text, never in a heading:
  "{animal} t-shirts", "{animal} hoodies", "{animal} stickers", "{animal} gift ideas".
- Do not name or compare competitors or other brands.
- Use the primary keyword naturally (about 4-6 times in total) and vary it with synonyms; never stuff keywords.
- Do NOT include <h1>, <html>, <head>, <body>, <style>, <script>, images or hyperlinks (links are added automatically).
- Output raw HTML only, using these tags: p, h2, h3, ul, ol, li, strong, em, table, thead, tbody, tr, th, td.
  No markdown, no code fences, no commentary before or after.
"""


def generate_article(client, animal, angle, plan, today):
    prompt = build_article_prompt(animal, angle, plan, today)

    def accept(text):
        cleaned = clean_article_html(text)
        return count_words(cleaned) >= MIN_WORDS and len(re.findall(r'<h2\b', cleaned, re.I)) >= 4

    raw = generate_with_fallback(client, prompt, "članak", temperature=0.8, accept=accept)
    if not raw:
        raise Exception("Nijedan Gemini model nije uspeo da vrati tekst. Proverite greške u logu iznad.")
    cleaned = clean_article_html(raw)
    words = count_words(cleaned)
    print(f"Članak ima oko {words} reči.")
    if words < MIN_WORDS:
        print(f"UPOZORENJE: članak je kraći od {MIN_WORDS} reči (nijedan model nije dao duži tekst).")
    return cleaned


def auto_link_keywords(content, animal, store_url, max_links=3):
    """Linkuje prva pojavljivanja prodajnih fraza u običnom tekstu.
    Preskače tekst unutar <a> i <h1-6> (nema ugnježdenih linkova) i ograničava broj linkova."""
    keywords = [
        f"{animal} t-shirts", f"{animal} t-shirt",
        f"{animal} hoodies", f"{animal} hoodie",
        f"{animal} stickers", f"{animal} sticker",
        f"{animal} gift ideas", f"{animal} gifts", f"{animal} apparel"
    ]
    pattern = re.compile(r'\b(' + '|'.join(re.escape(k) for k in sorted(keywords, key=len, reverse=True)) + r')\b',
                         re.IGNORECASE)
    link_open = (f'<a href="{esc(store_url)}" target="_blank" rel="noopener" '
                 f'style="color:#7b2cbf; font-weight:600; text-decoration:underline;">')
    linked = set()
    skip_depth = 0
    out = []

    def repl(m):
        key = m.group(1).lower()
        if key in linked or len(linked) >= max_links:
            return m.group(0)
        linked.add(key)
        return f"{link_open}{m.group(0)}</a>"

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


def cta_button_html(store_url, animal):
    return (f'<p style="text-align:center;"><a href="{esc(store_url)}" target="_blank" rel="noopener" '
            f'style="display:inline-block; padding:12px 24px; background:#00d2d3; color:#ffffff !important; '
            f'text-decoration:none; border-radius:30px; font-weight:bold; margin:20px 0;">'
            f'See All Our {animal.title()} Products 🛍️</a></p>')


def insert_cta(content, store_url, animal):
    button = cta_button_html(store_url, animal)
    if "<!--CTA-->" in content:
        first, *rest = content.split("<!--CTA-->")
        return first + button + "".join(rest)
    faq = re.search(r'<h2\b[^>]*>\s*(Frequently Asked Questions|FAQ)', content, re.I)
    if faq:
        return content[:faq.start()] + button + content[faq.start():]
    return content + button


def add_toc(content):
    """Dodaje id na <h2> i sadržaj (jump linkovi često postanu sitelinkovi u rezultatima pretrage)."""
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

    items = "".join(f'<li><a href="#{hid}" style="color:#7b2cbf; text-decoration:none;">{text}</a></li>'
                    for hid, text in headings)
    toc = ('<nav aria-label="Table of contents" style="background:#f7f2fd; border-left:4px solid #7b2cbf; '
           'padding:15px 20px; border-radius:8px; margin:25px 0;">'
           '<strong style="color:#3a1c5c;">In this article</strong>'
           f'<ol style="margin:10px 0 0 0; padding-left:20px;">{items}</ol></nav>')
    idx = content.find('</p>')
    if idx == -1:
        return toc + content
    return content[:idx + 4] + toc + content[idx + 4:]


# ---------------------------------------------------------------------------
# SLIKE I PRODAVNICA
# ---------------------------------------------------------------------------
IMAGE_SCENES_DEFAULT = [
    "on a soft pastel purple background",
    "in warm natural window light",
    "surrounded by colorful stickers and wrapped gift boxes",
    "in a cozy home setting with soft blankets",
    "on a bright minimalist studio backdrop",
]
IMAGE_SCENES_BY_ANGLE = {
    "christmas": "with festive red and green holiday decorations and warm bokeh lights",
    "halloween": "with small pumpkins and autumn leaves in warm light",
    "valentines": "with soft pink hearts and flowers",
    "mothers-day": "with fresh spring flowers",
    "fathers-day": "in a relaxed outdoor setting",
    "stocking-stuffers": "next to small wrapped gifts",
    "sticker-ideas": "surrounded by colorful stickers",
}


def generate_fal_image(clean_animal, angle_id):
    """Generiše AI sliku preko Fal.ai (Flux Schnell model). Vraća URL ili None."""
    if not FAL_KEY:
        print("FAL_KEY nije pronađen u environment varijablama! Koristim podrazumevani logo.")
        return None

    scene = IMAGE_SCENES_BY_ANGLE.get(angle_id) or random.choice(IMAGE_SCENES_DEFAULT)
    prompt = (f"adorable high quality studio photo of a {clean_animal}, {scene}, "
              f"sharp focus, vibrant colors, soft lighting, no text, no watermark")
    endpoint = "https://fal.run/fal-ai/flux/schnell"
    headers = {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}
    payload = {
        "prompt": prompt,
        "image_size": "square_hd",
        "num_inference_steps": 4,
        "output_format": "jpeg",
        "enable_safety_checker": True
    }

    try:
        print(f"Generišem sliku preko Fal.ai (flux/schnell) za: {clean_animal}...")
        response = requests.post(endpoint, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            data = response.json()
            if "images" in data and len(data["images"]) > 0:
                img_url = data["images"][0]["url"]
                print(f"Fal.ai slika uspešno generisana: {img_url}")
                return img_url
        print(f"Fal.ai API vrati status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Greška pri pozivanju Fal.ai API-ja: {e}")
    return None


def save_image_locally(remote_url, slug):
    """Skida sliku i čuva je na sopstvenom domenu: bolje za Google Images, OG preview i ne zavisi od tuđeg CDN-a."""
    try:
        os.makedirs(POST_IMG_DIR, exist_ok=True)
        resp = requests.get(remote_url, timeout=60)
        resp.raise_for_status()
        local_file = f"{POST_IMG_DIR}/{slug}.jpg"
        with open(local_file, "wb") as f:
            f.write(resp.content)
        print(f"Slika sačuvana lokalno: {local_file}")
        return f"/{local_file}"
    except Exception as e:
        print(f"Slika nije mogla da se sačuva lokalno ({e}); koristim spoljni URL.")
        return None


def get_store_category(animal_keyword, slug, angle_id, image_alt):
    clean_animal = animal_keyword.lower().strip()
    query_encoded = urllib.parse.quote(clean_animal)
    shop_search_url = f"https://www.redbubble.com/shop/?query={query_encoded}&artistUserName=Petzzz"

    remote = generate_fal_image(clean_animal, angle_id)
    local = save_image_locally(remote, slug) if remote else None

    if local:
        img_path, img_abs = local, f"https://{SITE_DOMAIN}{local}"
    elif remote:
        img_path, img_abs = remote, remote
    else:
        img_path, img_abs = LOGO_PATH, None

    return {
        "title": f"Explore Petzzz {clean_animal.title()} Designs",
        "img_url": img_path,
        "img_abs_url": img_abs,
        "has_ai_image": bool(remote),
        "image_alt": image_alt or f"Adorable {clean_animal} portrait",
        "product_link": shop_search_url
    }


# ---------------------------------------------------------------------------
# SEO HEAD, SCHEMA, INTERNO LINKOVANJE
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
        tags += [f'<meta property="og:image" content="{image}">', f'<meta name="twitter:image" content="{image}">']
    if published:
        tags += [f'<meta property="article:published_time" content="{published}">',
                 f'<meta property="article:modified_time" content="{published}">']
    tags.append(f'<link rel="alternate" type="application/rss+xml" title="{BRAND} Blog" '
                f'href="https://{SITE_DOMAIN}/rss.xml">')
    return "\n    ".join(tags)


def build_jsonld(title, description, url, image, date_iso, keywords, animal):
    home = f"https://{SITE_DOMAIN}/"
    article = {
        "@type": "BlogPosting",
        "@id": f"{url}#article",
        "headline": title[:110],
        "description": description,
        "datePublished": date_iso,
        "dateModified": date_iso,
        "inLanguage": "en",
        "about": animal,
        "keywords": ", ".join(keywords),
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "author": {"@type": "Organization", "name": BRAND, "url": home},
        "publisher": {"@type": "Organization", "name": BRAND,
                      "logo": {"@type": "ImageObject", "url": f"https://{SITE_DOMAIN}{LOGO_PATH}"}},
    }
    if image:
        article["image"] = [image]
    crumbs = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": home},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"https://{SITE_DOMAIN}/blog.html"},
            {"@type": "ListItem", "position": 3, "name": title, "item": url},
        ],
    }
    data = {"@context": "https://schema.org", "@graph": [article, crumbs]}
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def get_related_posts_html(current_slug, animal, posts, max_posts=3):
    """Preporučeni članci: prvo isti pojam (tematski klaster), pa nasumični za popunu."""
    others = [p for p in posts if p["slug"] != current_slug]
    if not others:
        return ""
    same = [p for p in others if animal in p["animals"]]
    rest = [p for p in others if animal not in p["animals"]]
    random.shuffle(same)
    random.shuffle(rest)
    selected = (same[:2] + rest + same[2:])[:max_posts]

    cards_html = ""
    for p in selected:
        cards_html += f"""
            <div style="flex:1; min-width:220px; background:#fdfbfb; padding:15px; border-radius:8px; border:1px solid #eee; box-shadow:0 2px 8px rgba(0,0,0,0.03);">
                <h4 style="margin:0 0 10px 0; font-size:1.0em; line-height:1.3;"><a href="{p['clean_url']}" style="color:#1c1328; text-decoration:none;">{p['title']}</a></h4>
                <a href="{p['clean_url']}" style="color:#7b2cbf; font-size:0.85em; font-weight:600; text-decoration:none;">Read Article ➔</a>
            </div>
            """

    return f"""
    <div style="margin-top:40px; padding-top:25px; border-top:1px solid #eaeaea;">
        <h3 style="color:#1c1328; margin-bottom:15px;">You Might Also Like 🐾</h3>
        <div style="display:flex; gap:15px; flex-wrap:wrap;">
            {cards_html}
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# SITEMAP / RSS / INDEXNOW
# ---------------------------------------------------------------------------
def update_sitemap(posts):
    """Jedna sitemap.xml. lastmod je stvarni datum objave, a ne 'danas' za sve URL-ove
    (Google ignoriše lastmod kad se pokaže da je nepouzdan)."""
    known_dates = [p["dt_obj"] for p in posts if p["date_known"]]
    latest = max(known_dates).strftime('%Y-%m-%d') if known_dates else None
    blog_lastmod = f"\n    <lastmod>{latest}</lastmod>" if latest else ""

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <!-- Glavne Stranice -->
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
        xml_content += f"""  <url>
    <loc>https://{SITE_DOMAIN}/blog/{p['slug']}.html</loc>{lastmod}
    <priority>0.8</priority>
  </url>\n"""
    xml_content += "</urlset>"

    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)

    for old_sitemap in ["sitemap-main.xml", "sitemap-blog.xml"]:
        if os.path.exists(old_sitemap):
            os.remove(old_sitemap)

    print("Jedinstvena sitemap.xml uspešno izgenerisana!")


def update_rss(title, post_url, content_summary, image_url=None):
    rss_file = "rss.xml"
    pub_date = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

    # Odstrani HTML tagove i sređivanje razmaka
    text_only = re.sub(r'<[^>]+>', ' ', content_summary)
    text_only = re.sub(r'\s+', ' ', text_only).strip()

    # Pametno skraćivanje na poslednju celu rečenicu (do oko 350 karaktera)
    if len(text_only) > 350:
        short_text = text_only[:350]
        last_dot = short_text.rfind('.')
        if last_dot != -1:
            clean_description = short_text[:last_dot + 1]
        else:
            clean_description = short_text + "..."
    else:
        clean_description = text_only

    if not os.path.exists(rss_file):
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "Petzzz Studio Blog"
        ET.SubElement(channel, "link").text = f"https://{SITE_DOMAIN}"
        ET.SubElement(channel, "description").text = "Latest posts and gift guides from Petzzz Studio"
    else:
        try:
            tree = ET.parse(rss_file)
            rss = tree.getroot()
            channel = rss.find("channel")
        except Exception:
            rss = ET.Element("rss", version="2.0")
            channel = ET.SubElement(rss, "channel")

    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = post_url
    ET.SubElement(item, "description").text = clean_description
    ET.SubElement(item, "pubDate").text = pub_date

    # Dodavanje slika za Pinterest, Make.com i ostale RSS čitače (samo apsolutni URL-ovi)
    if image_url:
        ET.SubElement(item, "enclosure", attrib={"url": image_url, "type": "image/jpeg", "length": "0"})
        ET.SubElement(item, "{http://search.yahoo.com/mrss/}content", attrib={"url": image_url, "medium": "image"})

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write(rss_file, encoding="utf-8", xml_declaration=True)
    print("Rss.xml uspešno ažuriran!")


def notify_indexnow(post_url):
    endpoint = "https://api.indexnow.org/indexnow"
    payload = {
        "host": SITE_DOMAIN,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{SITE_DOMAIN}/{INDEXNOW_KEY}.txt",
        "urlList": [post_url, f"https://{SITE_DOMAIN}/blog.html"]
    }
    headers = {"Content-Type": "application/json; charset=utf-8"}

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 202]:
            print("IndexNow API: Uspešno poslato obaveštenje pretraživačima!")
        else:
            print(f"IndexNow API status ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"IndexNow API zahtev nije uspeo: {e}")


# ---------------------------------------------------------------------------
# ŠABLONI (CSS/JS su obični stringovi, bez dupliranja zagrada)
# ---------------------------------------------------------------------------
POST_CSS = """
        body { font-family: 'Poppins', sans-serif; background: #f8f9fa; color: #333; margin:0; line-height:1.7; }
        header { background: #fff; border-bottom: 1px solid #eaeaea; padding: 15px 20px; }
        .nav-container { max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
        .logo-box { display: flex; align-items: center; text-decoration: none; gap: 10px; font-weight:700; color:#3a1c5c; }
        .logo-img { width: 40px; height: 40px; border-radius: 50%; }
        .container { max-width: 800px; margin: 40px auto; background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        h1 { color: #1c1328; font-size: 2.2em; margin-bottom: 10px; line-height: 1.2; }
        h2 { color: #7b2cbf; margin-top: 35px; line-height: 1.3; scroll-margin-top: 20px; }
        h3 { color: #3a1c5c; margin-top: 25px; line-height: 1.3; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 0.95em; }
        th, td { border: 1px solid #eaeaea; padding: 10px 12px; text-align: left; vertical-align: top; }
        th { background: #f7f2fd; color: #3a1c5c; }
        .breadcrumb { font-size: 0.85em; margin-bottom: 20px; color: #888; }
        .breadcrumb a { color: #7b2cbf; text-decoration: none; font-weight: 600; }
        .author-box { margin-top: 40px; padding: 18px 20px; background: #f7f2fd; border-radius: 10px; font-size: 0.92em; }
        .author-box p { margin: 6px 0 0 0; }
        .author-box a { color: #7b2cbf; font-weight: 600; }
        footer { background: #1c1328; color: #bbb; text-align: center; padding: 30px 20px; margin-top: 50px; font-size: 0.9em; }
        footer a { color: #fff; }
        @media (max-width: 600px) {
            .container { padding: 22px; margin: 20px 12px; }
            h1 { font-size: 1.8em; }
            table { display: block; overflow-x: auto; }
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

        /* Pretraga */
        .search-wrapper { max-width: 600px; margin: 0 auto 35px auto; position: relative; }
        .search-box { position: relative; display: flex; align-items: center; }
        .search-icon { position: absolute; left: 18px; width: 20px; height: 20px; color: #7b2cbf; pointer-events: none; }
        .search-input { width: 100%; padding: 14px 20px 14px 50px; font-size: 1em; font-family: 'Poppins', sans-serif; border: 2px solid #eaeaea; border-radius: 30px; outline: none; background: #ffffff; color: #333; box-shadow: 0 4px 12px rgba(0,0,0,0.04); transition: all 0.3s ease; box-sizing: border-box; }
        .search-input:focus { border-color: #7b2cbf; box-shadow: 0 4px 18px rgba(123, 44, 191, 0.18); }
        .no-results { display: none; text-align: center; padding: 20px; color: #666; font-size: 1.1em; font-weight: 600; background: #fff; border-radius: 12px; margin-bottom: 20px; }

        /* Kartice članaka sa kockastom sličicom */
        .article-card {
            background: #fff;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            transition: transform 0.2s, box-shadow 0.2s;
            display: flex;
            align-items: center;
            gap: 20px;
        }
        .article-card:hover { transform: translateY(-3px); box-shadow: 0 6px 20px rgba(0,0,0,0.08); }
        .article-thumb {
            width: 100px;
            height: 100px;
            border-radius: 10px;
            object-fit: cover;
            flex-shrink: 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .article-content { flex: 1; }

        /* Dugme Back to Top */
        #backToTop {
            display: none; position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
            z-index: 99; border: none; outline: none; background-color: #7b2cbf; color: white;
            cursor: pointer; width: 50px; height: 50px; border-radius: 50%; font-size: 22px; font-weight: bold;
            box-shadow: 0 4px 15px rgba(123, 44, 191, 0.4); transition: background-color 0.3s;
            align-items: center; justify-content: center;
        }
        #backToTop:hover { background-color: #5a189a; }

        /* Mobilni Prikaz */
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
        // Pretraga
        document.getElementById('petSearchInput').addEventListener('keyup', function() {
            let filter = this.value.toLowerCase().trim();
            let cards = document.querySelectorAll('.article-card');
            let visibleCount = 0;

            cards.forEach(function(card) {
                let title = card.querySelector('h3').innerText.toLowerCase();
                if (title.includes(filter)) {
                    card.style.display = "flex";
                    visibleCount++;
                } else {
                    card.style.display = "none";
                }
            });

            let noResults = document.getElementById('noResultsMessage');
            if (visibleCount === 0) {
                noResults.style.display = "block";
            } else {
                noResults.style.display = "none";
            }
        });

        // Back to Top strelica
        let mybutton = document.getElementById("backToTop");
        window.onscroll = function() {
            if (document.body.scrollTop > 300 || document.documentElement.scrollTop > 300) {
                mybutton.style.display = "flex";
            } else {
                mybutton.style.display = "none";
            }
        };

        mybutton.onclick = function() {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        };
"""


def update_blog_index(posts):
    articles = sorted(posts, key=lambda x: x['dt_obj'], reverse=True)

    posts_list_html = ""
    for article in articles:
        posts_list_html += f"""
        <div class="article-card">
            <a href="{article['clean_url']}">
                <img src="{article['img_url']}" alt="{esc(html.unescape(article['title']))}" class="article-thumb" width="100" height="100" loading="lazy" onerror="this.src='{LOGO_PATH}'">
            </a>
            <div class="article-content">
                <h3 style="margin-top:0; font-size:1.3em; line-height:1.3;"><a href="{article['clean_url']}" style="text-decoration:none; color:#1c1328;">{article['title']}</a></h3>
                <p style="font-size:0.85em; color:#888; margin-bottom:12px;">Published on {article['date_str']}</p>
                <a href="{article['clean_url']}" style="display:inline-block; padding:8px 16px; background:#e7d9fc; color:#7b2cbf; text-decoration:none; border-radius:6px; font-weight:600; font-size:0.85em;">Read Article ➔</a>
            </div>
        </div>
        """

    page_title = "Pet Gift Guides & Animal Lover Articles | Petzzz Studio"
    page_desc = ("Gift guides, fun facts and ideas for dog, cat and animal lovers: t-shirts, hoodies, "
                 "stickers and more from Petzzz Studio.")
    head_tags = seo_head_tags(page_title, page_desc, f"https://{SITE_DOMAIN}/blog.html", og_type="website")

    index_page = f"""<!DOCTYPE html>
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
            <a href="/" class="logo-box">
                <img src="{LOGO_PATH}" alt="Petzzz Logo" class="logo-img">
                <span>Petzzz Studio</span>
            </a>
            <div class="nav-links">
                <a href="/">Home Store</a>
                <a href="{STORE_HOME_URL}" target="_blank" rel="noopener">Redbubble Shop</a>
            </div>
        </div>
    </header>

    <main class="container">
        <h1>Latest Pet Articles & Gift Guides</h1>

        <!-- Pretraga -->
        <div class="search-wrapper">
            <div class="search-box">
                <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="11" cy="11" r="8"></circle>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
                <input type="text" id="petSearchInput" class="search-input" placeholder="Search by animal (e.g. Pitbull, Cat)..." aria-label="Search articles by animal">
            </div>
        </div>

        <div id="noResultsMessage" class="no-results">
            No articles found for that search. Try another animal! 🐾
        </div>

        {posts_list_html}
    </main>

    <!-- Back to Top -->
    <button id="backToTop" title="Go to top">↑</button>

    <footer>
        <p>&copy; 2026 Petzzz Studio. | <a href="/privacy.html">Privacy Policy</a></p>
    </footer>

    <script>{INDEX_JS}</script>
</body>
</html>"""

    with open("blog.html", "w", encoding="utf-8") as f:
        f.write(index_page)


# ---------------------------------------------------------------------------
# GLAVNI TOK
# ---------------------------------------------------------------------------
def generate_post():
    if not GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY nije pronađen u environment varijablama!")

    client = genai.Client(api_key=GEMINI_API_KEY)
    today = datetime.date.today()
    posts = load_posts()

    animal = get_next_animal(posts)
    angle = pick_angle(animal, posts, today)
    existing_titles = [p["title"] for p in posts if animal in p["animals"]][:15]

    plan = plan_topic(client, animal, angle, existing_titles, today)
    topic = plan["title"]

    # Kratak slug iz ključne reči (npr. corgi-gifts-for-moms), jedinstven
    base_slug = "-".join(slugify(plan["primary_keyword"]).split("-")[:7]) or slugify(topic)
    if slugify(animal) not in base_slug:
        base_slug = f"{slugify(animal)}-{base_slug}"
    slug, n = base_slug, 2
    while os.path.exists(f"blog/{slug}.html"):
        slug, n = f"{base_slug}-{n}", n + 1

    category = get_store_category(animal, slug, angle["id"], plan["image_alt"])

    article = generate_article(client, animal, angle, plan, today)
    article = auto_link_keywords(article, animal, category['product_link'])
    article = insert_cta(article, category['product_link'], animal)
    article = add_toc(article)

    related_posts_html = get_related_posts_html(slug, animal, posts)

    # --- SEO metapodaci ---
    post_url = f"https://{SITE_DOMAIN}/blog/{slug}.html"
    suffix = " | Petzzz Studio"
    seo_title = topic + suffix if len(topic) + len(suffix) <= 62 else topic
    description = plan["meta_description"] or trim_meta(
        f"{topic}: practical ideas and tips for {audience_for(animal)}.")
    og_image = category["img_abs_url"] or f"https://{SITE_DOMAIN}{LOGO_PATH}"
    date_iso = today.isoformat()
    keywords = [plan["primary_keyword"]] + plan["secondary_keywords"]

    head_tags = seo_head_tags(seo_title, description, post_url, image=og_image, published=date_iso)
    jsonld = build_jsonld(topic, description, post_url, category["img_abs_url"], date_iso, keywords, animal)

    # --- Delovi stranice ---
    dims = ' width="1024" height="1024"' if category["has_ai_image"] else ""
    product_html_banner = f"""
    <div style="text-align:center; margin: 30px 0; background:#f0f0f0; padding:20px; border-radius:12px;">
        <a href="{esc(category['product_link'])}" target="_blank" rel="noopener">
            <img src="{category['img_url']}" alt="{esc(category['image_alt'])}"{dims} fetchpriority="high" decoding="async" style="max-width:100%; height:auto; max-height:450px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.1); object-fit:cover; display:inline-block;" onerror="this.src='{LOGO_PATH}'">
        </a>
        <p style="font-size:1.1em; margin-top:15px; font-weight:700;">
            <a href="{esc(category['product_link'])}" target="_blank" rel="noopener" style="display:inline-block; padding:10px 25px; background:#7b2cbf; color:#ffffff !important; text-decoration:none; border-radius:8px; transition:0.3s;">
                View Petzzz {animal.title()} Collection ➔
            </a>
        </p>
    </div>
    """

    badge_style = "background:#e7d9fc; color:#7b2cbf; text-decoration:none; padding:4px 12px; border-radius:15px; font-size:0.85em; font-weight:600;"
    tag_badges = f"""
    <div style="margin: 15px 0 25px 0; display:flex; gap:8px; flex-wrap:wrap;">
        <a href="{esc(category['product_link'])}" target="_blank" rel="noopener" style="{badge_style}">#{animal.title().replace(' ', '')}</a>
        <a href="{esc(category['product_link'])}" target="_blank" rel="noopener" style="{badge_style}">#PetGifts</a>
        <a href="{esc(category['product_link'])}" target="_blank" rel="noopener" style="{badge_style}">#RedbubbleShop</a>
    </div>
    """

    author_box = f"""
    <div class="author-box">
        <strong>About {BRAND}</strong>
        <p>{BRAND} is an independent design studio creating original animal-themed art for t-shirts, hoodies, stickers and gifts,
        available in our <a href="{STORE_HOME_URL}" target="_blank" rel="noopener">Redbubble shop</a>.</p>
    </div>
    """

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc(seo_title)}</title>
    {head_tags}
    <meta name="petzzz:animal" content="{esc(animal)}">
    <meta name="petzzz:angle" content="{esc(angle['id'])}">
    <meta name="petzzz:keyword" content="{esc(plan['primary_keyword'])}">
    <script type="application/ld+json">{jsonld}</script>
    {GA_SNIPPET}
    <link rel="icon" type="image/png" href="{LOGO_PATH}">
    {FONT_LINKS}
    <style>{POST_CSS}</style>
</head>
<body>
    <header>
        <div class="nav-container">
            <a href="/" class="logo-box">
                <img src="{LOGO_PATH}" alt="Petzzz Logo" class="logo-img" width="40" height="40">
                <span>Petzzz Studio</span>
            </a>
            <a href="{STORE_HOME_URL}" target="_blank" rel="noopener" style="color:#7b2cbf; text-decoration:none; font-weight:600;">Visit Redbubble Shop 🛍️</a>
        </div>
    </header>

    <main class="container">
        <article>
        <nav class="breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a> › <a href="/blog.html">Blog</a> › <span>{esc(animal.title())}</span></nav>
        <h1>{esc(topic)}</h1>
        <p><em>Published on {today.strftime('%B %d, %Y')} by Petzzz Studio Team</em></p>
        {tag_badges}
        {product_html_banner}
        <hr style="border:0; border-top:1px solid #eaeaea; margin:30px 0;">
        {article}
        {author_box}
        {related_posts_html}
        </article>
    </main>

    <footer>
        <p>&copy; 2026 Petzzz Studio. | <a href="/privacy.html">Privacy Policy</a></p>
    </footer>
</body>
</html>"""

    os.makedirs("blog", exist_ok=True)
    file_path = f"blog/{slug}.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Blog post uspešno kreiran: {file_path}")

    # Ponovo učitavamo sve članke (uključujući novi) za indeks i sitemap
    all_posts = load_posts()
    update_blog_index(all_posts)
    update_sitemap(all_posts)
    update_rss(topic, post_url, article, category['img_abs_url'])
    notify_indexnow(post_url)


if __name__ == "__main__":
    generate_post()
