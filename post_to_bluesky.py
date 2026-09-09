import os
import random
import re
import requests
from bs4 import BeautifulSoup
from atproto import Client, client_utils

BSKY_HANDLE = os.environ.get("BSKY_HANDLE")
BSKY_PASSWORD = os.environ.get("BSKY_APP_PASSWORD")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Reči koje ne treba pretvarati u heštegove
STOP_WORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
    'from', 'up', 'about', 'into', 'over', 'after', 'designed', 'sold', 'item', 'preview',
    'petzzz', 'studio', 'art', 'gift', 'gifts', 'v1', 'v2', 'v3'
}

def extract_all_keywords(title):
    """Izvlači sve ključne reči iz naslova proizvoda i pravi heštegove od njih."""
    words = re.findall(r'[a-zA-Z0-9]+', title)
    keywords = []
    
    for w in words:
        clean_w = w.strip()
        if clean_w.lower() not in STOP_WORDS and len(clean_w) > 1:
            cap_w = clean_w.capitalize()
            if cap_w not in keywords:
                keywords.append(cap_w)
                
    if "PetLovers" not in keywords:
        keywords.append("PetLovers")
        
    return keywords

def fetch_random_redbubble_design():
    """Očitava ukupan broj stranica šopa, bira nasumičnu stranicu i sa nje uzima nasumičan dizajn."""
    base_shop_url = "https://www.redbubble.com/people/Petzzz/shop"
    
    try:
        response = requests.get(base_shop_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        page_numbers = [1]
        page_links = soup.find_all('a', href=re.compile(r'page=\d+'))
        for link in page_links:
            match = re.search(r'page=(\d+)', link.get('href', ''))
            if match:
                page_numbers.append(int(match.group(1)))
        
        max_page = max(page_numbers) if page_numbers else 1
        chosen_page = random.randint(1, max_page)
        print(f"Pronađeno ukupno stranica: {max_page}. Nasumično izabrana stranica: {chosen_page}")
        
        if chosen_page > 1:
            page_url = f"{base_shop_url}?page={chosen_page}"
            response = requests.get(page_url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
        products = []
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
                    
        if products:
            return random.choice(products)
            
    except Exception as e:
        print(f"Greška pri pretrazi Redbubble prodavnice: {e}")

    return None

def post_to_bluesky():
    if not BSKY_HANDLE or not BSKY_PASSWORD:
        print("Greška: Bluesky kredencijali nisu podešeni!")
        return

    print("Tražim nasumičan dizajn sa celog Redbubble šopa...")
    design = fetch_random_redbubble_design()
    
    if not design:
        design = {
            "title": "Petzzz Studio Apparel & Stickers",
            "img_url": "https://images.unsplash.com/photo-1517423440428-a5a00ad493e8?w=800&q=80",
            "product_link": "https://www.redbubble.com/people/Petzzz/shop"
        }

    print(f"Izabran dizajn: {design['title']}")
    
    # Automatsko izvlačenje svih ključnih reči iz naslova
    keywords = extract_all_keywords(design['title'])
    print(f"Izvučene ključne reči za heštegove: {keywords}")

    # Građenje teksta objave sa klikabilnim linkom i heštegovima
    tb = client_utils.TextBuilder()
    tb.text(f"Discover unique {design['title']} at Petzzz Studio! 🐾\n\nShop collection: ")
    tb.link(design['product_link'], design['product_link'])
    tb.text("\n\n")
    
    # Dodavanje svih ključnih reči kao klikabilnih heštegova
    for word in keywords:
        tb.tag(f"#{word}", word)
        tb.text(" ")
        
    tb.tag("#Redbubble", "Redbubble")
    tb.text(" ")
    tb.tag("#PetzzzStudio", "PetzzzStudio")

    print("Preuzimam sliku dizajna...")
    img_data = None
    try:
        img_resp = requests.get(design['img_url'], headers=HEADERS, timeout=10)
        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
            img_data = img_resp.content
    except Exception as e:
        print(f"Greška pri preuzimanju slike: {e}")

    if not img_data:
        print("Korišćenje rezervne slike (Logo 2.png)...")
        if os.path.exists("Logo 2.png"):
            with open("Logo 2.png", "rb") as f:
                img_data = f.read()
        else:
            img_data = requests.get("https://images.unsplash.com/photo-1517423440428-a5a00ad493e8?w=800&q=80").content

    print("Povezujem se na Bluesky...")
    client = Client()
    client.login(BSKY_HANDLE, BSKY_PASSWORD)
    
    print("Objavljujem post...")
    client.send_image(
        text=tb,
        image=img_data,
        image_alt=design['title']
    )
    print("Uspešno objavljeno!")

if __name__ == "__main__":
    post_to_bluesky()
