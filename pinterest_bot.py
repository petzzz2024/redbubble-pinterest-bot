import os
import json
import random
import requests
import feedparser
from bs4 import BeautifulSoup
from google import genai

RB_USERNAME = os.environ.get('REDBUBBLE_USERNAME', '').strip()
PINTEREST_BOARD_ID = os.environ.get('PINTEREST_BOARD_ID', '').strip()
PINTEREST_TOKEN = os.environ.get('PINTEREST_ACCESS_TOKEN', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

HISTORY_FILE = "posted_history.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

def get_redbubble_products():
    products = []
    
    # Metoda 1: RSS Feed
    rss_url = f"https://www.redbubble.com/people/{RB_USERNAME}/shop.rss"
    try:
        response = requests.get(rss_url, headers=HEADERS, timeout=15)
        print(f"Status RSS HTTP zahteva: {response.status_code}")
        if response.status_code == 200 and len(response.content) > 500:
            feed = feedparser.parse(response.content)
            for entry in feed.entries:
                title = entry.title
                link = entry.link
                summary_text = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
                soup = BeautifulSoup(summary_text, 'html.parser')
                img_tag = soup.find('img')
                img_url = img_tag['src'] if img_tag else None
                if img_url:
                    products.append({'title': title, 'link': link, 'image_url': img_url})
    except Exception as e:
        print(f"RSS mehanizam nije uspeo: {e}")

    # Metoda 2: Direktno čitanje Shop stranice ako je RSS prazan
    if not products:
        print("RSS feed nije vratio artikle. Pokreće se rezervno čitanje Shop stranice...")
        shop_url = f"https://www.redbubble.com/people/{RB_USERNAME}/shop"
        try:
            response = requests.get(shop_url, headers=HEADERS, timeout=15)
            print(f"Status Shop HTTP zahteva: {response.status_code}")
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                img_tags = soup.find_all('img')
                for img in img_tags:
                    src = img.get('src', '')
                    alt = img.get('alt', '')
                    parent_a = img.find_parent('a')
                    if parent_a and parent_a.get('href') and ('ih1.redbubble.net' in src or 'ih0.redbubble.net' in src):
                        href = parent_a['href']
                        full_link = href if href.startswith('http') else f"https://www.redbubble.com{href}"
                        title = alt.strip() if alt else f"Redbubble Design by {RB_USERNAME}"
                        if not any(p['link'] == full_link for p in products):
                            products.append({'title': title, 'link': full_link, 'image_url': src})
        except Exception as e:
            print(f"Greška pri čitanju Shop stranice: {e}")

    return products

def generate_ai_description(title):
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = f"""
    Napiši privlačan Pinterest opis na engleskom jeziku za proizvod sa nazivom '{title}'.
    Opis treba da bude optimizovan za pretragu (SEO), dužine 2 do 3 rečenice i sa 5 relevantnih hashtagova na kraju.
    Nemoj dodavati naslov, vrati samo čist tekst opisa.
    """
    
    # Lista 3 nova modela koja se pokušavaju redom u slučaju opterećenja
    models_to_try = [
        'gemini-3.7-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.1-pro-preview'
    ]
    
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            print(f"Uspešno generisan opis pomoću modela: {model_name}")
            return response.text.strip()
        except Exception as e:
            print(f"Model {model_name} je trenutno nedostupan ili preopterećen. Pokušavam sledeći model...")

    # Rezervni tekst ukoliko su sva 3 AI modela preopterećena
    print("Sva 3 AI modela su trenutno preopterećena. Koristi se rezervni opis.")
    return f"Discover unique products featuring the '{title}' design on Redbubble. Perfect for gifts, personal style, and unique decor. Shop the full collection now! #redbubble #{RB_USERNAME.lower()} #giftideas #design #shopping"

def post_to_pinterest(title, description, link, image_url):
    url = "https://api.pinterest.com/v5/pins"
    headers = {
        "Authorization": f"Bearer {PINTEREST_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "board_id": PINTEREST_BOARD_ID,
        "title": title[:100],
        "description": description[:500],
        "link": link,
        "media_source": {
            "source_type": "image_url",
            "url": image_url
        }
    }
    
    res = requests.post(url, json=payload, headers=headers)
    return res.status_code == 201, res.json()

def main():
    posted = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            try:
                posted = json.load(f)
            except json.JSONDecodeError:
                posted = []

    products = get_redbubble_products()
    print(f"Broj pronađenih proizvoda u prodavnici: {len(products)}")

    unposted_products = [p for p in products if p['link'] not in posted]
    print(f"Broj neobjavljenih proizvoda: {len(unposted_products)}")

    if not unposted_products:
        print("Nema novih proizvoda za objavu.")
        return

    target_product = random.choice(unposted_products)
    print(f"Izabran proizvod: {target_product['title']}")

    description = generate_ai_description(target_product['title'])
    success, response = post_to_pinterest(
        target_product['title'], 
        description, 
        target_product['link'], 
        target_product['image_url']
    )

    if success:
        print("Uspešno kreiran Pin na Pinterestu!")
        posted.append(target_product['link'])
        with open(HISTORY_FILE, 'w') as f:
            json.dump(posted, f, indent=2)
    else:
        print(f"Pinterest API odziv: {response}")

if __name__ == "__main__":
    main()
