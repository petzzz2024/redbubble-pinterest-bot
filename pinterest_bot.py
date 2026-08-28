import os
import json
import random
import requests
import feedparser
from bs4 import BeautifulSoup
import google.generativeai as genai

RB_USERNAME = os.environ.get('REDBUBBLE_USERNAME')
PINTEREST_BOARD_ID = os.environ.get('PINTEREST_BOARD_ID')
PINTEREST_TOKEN = os.environ.get('PINTEREST_ACCESS_TOKEN')
GEMINI_KEY = os.environ.get('GEMINI_API_KEY')

RSS_URL = f"https://www.redbubble.com/people/{RB_USERNAME}/shop.rss"
HISTORY_FILE = "posted_history.json"

def get_redbubble_products():
    feed = feedparser.parse(RSS_URL)
    products = []
    
    for entry in feed.entries:
        title = entry.title
        link = entry.link
        soup = BeautifulSoup(entry.summary, 'html.parser')
        img_tag = soup.find('img')
        img_url = img_tag['src'] if img_tag else None
        
        if img_url:
            products.append({
                'title': title,
                'link': link,
                'image_url': img_url
            })
    return products

def generate_ai_description(title):
    genai.configure(api_key=GEMINI_KEY)
    # Korišćenje Gemini 3.7 Flash modela
    model = genai.GenerativeModel('gemini-3.7-flash')
    
    prompt = f"""
    Napiši privlačan Pinterest opis na engleskom jeziku za proizvod sa nazivom '{title}'.
    Opis treba da bude optimizovan za pretragu (SEO), dužine 2 do 3 rečenice i sa 5 relevantnih hashtagova na kraju.
    Nemoj dodavati naslov, vrati samo čist tekst opisa.
    """
    response = model.generate_content(prompt)
    return response.text.strip()

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
            posted = json.load(f)

    products = get_redbubble_products()
    unposted_products = [p for p in products if p['link'] not in posted]

    if not unposted_products:
        print("Svi preuzeti proizvodi iz feed-a su već objavljeni.")
        return

    # NASUMIČAN (RANDOM) IZBOR PROIZVODA
    target_product = random.choice(unposted_products)
    print(f"Nasumično izabran proizvod: {target_product['title']}")

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
        print(f"Greška pri objavljivanju: {response}")

if __name__ == "__main__":
    main()
