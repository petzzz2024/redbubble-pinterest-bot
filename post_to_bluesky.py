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

def get_animal_hashtags_via_gemini(title):
    """Koristi Gemini veštačku inteligenciju da precizno pronađe životinju iz naslova i napravi heštegove."""
    prompt = f"""
    Analyze this product title: "{title}".
    Identify the main animal/creature and return 2-3 clean, single-word hashtags related to that animal or breed.
    Do NOT include spaces, punctuation, or special characters in the tags.
    Output ONLY the words separated by commas, nothing else.
    Example input: Modern Day Dinosaur Cassowary Prehistoric Art
    Example output: Cassowary, Dinosaur, Bird
    """
    
    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt, request_options={"timeout": 10})
            if resp.text:
                tags = [re.sub(r'[^a-zA-Z0-9]', '', t.strip()).capitalize() for t in resp.text.split(',') if t.strip()]
                clean_tags = [t for t in tags if t]
                if clean_tags:
                    return clean_tags[:3]
        except Exception:
            continue
            
    return ["PetLovers"]

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
    
    # Gemini AI pronalazi tačne heštegove životinje
    animal_tags = get_animal_hashtags_via_gemini(design['title'])
    if "PetLovers" not in animal_tags:
        animal_tags.append("PetLovers")
    print(f"Generisani heštegovi: {animal_tags}")

    # Građenje teksta sa simvolom '#' i klikabilnim linkom
    tb = client_utils.TextBuilder()
    tb.text(f"Discover unique {design['title']} at Petzzz Studio! 🐾\n\nShop collection: ")
    tb.link(design['product_link'], design['product_link'])
    tb.text("\n\n")
    
    # Dodavanje heštegova sa pravim '#' znakom
    for tag in animal_tags:
        tb.tag(f"#{tag}", tag)
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
