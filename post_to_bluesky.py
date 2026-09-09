import os
import random
import re
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from atproto import Client, client_utils

BSKY_HANDLE = os.environ.get("BSKY_HANDLE")
BSKY_PASSWORD = os.environ.get("BSKY_APP_PASSWORD")
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

GEMINI_MODELS = [
    'gemini-1.5-flash',
    'gemini-2.0-flash',
    'gemini-3.8-flash',
    'gemini-3.7-flash'
]

def fetch_random_redbubble_design():
    """Skida popis proizvoda sa prve strane Vašeg šopa i bira jedan nasumičan."""
    shop_url = "https://www.redbubble.com/people/Petzzz/shop"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    products = []
    try:
        response = requests.get(shop_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        img_tags = soup.find_all('img', src=re.compile(r'ih\d\.redbubble\.net'))
        
        for img in img_tags:
            alt = img.get('alt', '').strip()
            src = img.get('src')
            parent_a = img.find_parent('a')
            
            if parent_a and parent_a.get('href'):
                href = parent_a.get('href')
                full_link = href if href.startswith('http') else f"https://www.redbubble.com{href}"
                
                if '/i/' in full_link:
                    clean_title = alt.replace(" designed and sold by Petzzz.", "").replace("Item preview, ", "")
                    products.append({
                        "title": clean_title,
                        "img_url": src,
                        "product_link": full_link
                    })
    except Exception as e:
        print(f"Greška pri pretrazi Redbubble prodavnice: {e}")

    if products:
        return random.choice(products) 
    
    return None

def post_to_bluesky():
    if not BSKY_HANDLE or not BSKY_PASSWORD:
        print("Greška: Bluesky kredencijali nisu podešeni!")
        return

    print("Tražim nasumičan dizajn sa Redbubble...")
    design = fetch_random_redbubble_design()
    
    # Ako se dizajn ne pronađe, koristi se rezervni generalni link prodavnice
    if not design:
        design = {
            "title": "Petzzz Studio Apparel & Stickers",
            "img_url": "https://images.unsplash.com/photo-1517423440428-a5a00ad493e8?w=800&q=80",
            "product_link": "https://www.redbubble.com/people/Petzzz/shop"
        }

    print(f"Izabran dizajn: {design['title']}")
    
    # GRAĐENJE OBRAZA SA KLIKABILNIM LINKOVIMA (TextBuilder)
    tb = client_utils.TextBuilder()
    tb.text(f"Discover unique {design['title']} at Petzzz Studio! 🐾\n\nShop collection: ")
    tb.link(design['product_link'], design['product_link'])  # Pravi klikabilan plavi link
    tb.text("\n\n")
    tb.tag("PetLovers", "PetLovers")       # Pravi klikabilan tag
    tb.text(" ")
    tb.tag("Redbubble", "Redbubble")
    tb.text(" ")
    tb.tag("PetzzzStudio", "PetzzzStudio")

    print("Preuzimam sliku dizajna...")
    img_data = requests.get(design['img_url']).content
    
    print("Povezujem se na Bluesky...")
    client = Client()
    client.login(BSKY_HANDLE, BSKY_PASSWORD)
    
    print("Objavljujem post sa klikabilnim linkom...")
    client.send_image(
        text=tb,
        image=img_data,
        image_alt=design['title']
    )
    print("Uspešno objavljeno!")

if __name__ == "__main__":
    post_to_bluesky()
