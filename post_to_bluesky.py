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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def extract_animal_hashtags(title):
    """Izvlači reči vezane za životinju iz naslova i pretvara ih u prilagođene heštegove."""
    ignore_words = {
        'designed', 'sold', 'by', 'petzzz', 'item', 'preview', 'sticker', 'stickers', 
        't-shirt', 'shirt', 'hoodie', 'apparel', 'gift', 'gifts', 'art', 'cute', 'funny', 
        'vector', 'vintage', 'retro', 'lovers', 'lover', 'and', 'the', 'for', 'with', 'studio'
    }
    
    # Pronalazak svih reči iz naslova
    words = re.findall(r'[a-zA-Z0-9]+', title)
    relevant_words = [w.capitalize() for w in words if w.lower() not in ignore_words and len(w) > 2]
    
    unique_tags = []
    for w in relevant_words:
        if w not in unique_tags:
            unique_tags.append(w)
        if len(unique_tags) >= 2:
            break
            
    title_lower = title.lower()
    
    # Dodavanje opštijeg taga za pse ili mačke u zavisnosti od izabrane životinje
    if any(cat in title_lower for cat in ['cat', 'kitten', 'kitty', 'meow']):
        if "CatLovers" not in unique_tags:
            unique_tags.append("CatLovers")
    elif any(dog in title_lower for dog in ['dog', 'puppy', 'corgi', 'pug', 'husky', 'dachshund', 'bulldog', 'retriever', 'doxie', 'frenchie']):
        if "DogLovers" not in unique_tags:
            unique_tags.append("DogLovers")
    else:
        if "PetLovers" not in unique_tags:
            unique_tags.append("PetLovers")
            
    return unique_tags

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
    
    # Dinamičko generisanje heštegova na osnovu izabrane životinje
    animal_tags = extract_animal_hashtags(design['title'])
    print(f"Generisani heštegovi za životinju: {animal_tags}")

    # Građenje teksta sa klikabilnim linkom i prilagođenim heštegovima
    tb = client_utils.TextBuilder()
    tb.text(f"Discover unique {design['title']} at Petzzz Studio! 🐾\n\nShop collection: ")
    tb.link(design['product_link'], design['product_link'])
    tb.text("\n\n")
    
    # Dodavanje tagova vezanih za konkretnu životinju
    for tag in animal_tags:
        tb.tag(tag, tag)
        tb.text(" ")
        
    tb.tag("Redbubble", "Redbubble")
    tb.text(" ")
    tb.tag("PetzzzStudio", "PetzzzStudio")

    print("Preuzimam sliku dizajna...")
    img_data = None
    try:
        img_resp = requests.get(design['img_url'], headers=HEADERS, timeout=10)
        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
            img_data = img_resp.content
    except Exception as e:
        print(f"Greška pri preuzimanju slike: {e}")

    # Fallback na lokalni logo ako preuzimanje slike sa sajta ne uspe
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
