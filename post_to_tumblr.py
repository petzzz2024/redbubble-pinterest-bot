import os
import random
import re
import requests
from bs4 import BeautifulSoup
import pytumblr

CONSUMER_KEY = os.environ.get("TUMBLR_CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("TUMBLR_CONSUMER_SECRET")
OAUTH_TOKEN = os.environ.get("TUMBLR_OAUTH_TOKEN")
OAUTH_SECRET = os.environ.get("TUMBLR_OAUTH_SECRET")
BLOG_NAME = os.environ.get("TUMBLR_BLOG_NAME")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

STOP_WORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
    'from', 'up', 'about', 'into', 'over', 'after', 'designed', 'sold', 'item', 'preview',
    'petzzz', 'studio', 'art', 'gift', 'gifts', 'v1', 'v2', 'v3'
}

def extract_all_keywords(title):
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

def post_to_tumblr():
    if not all([CONSUMER_KEY, CONSUMER_SECRET, OAUTH_TOKEN, OAUTH_SECRET, BLOG_NAME]):
        print("Greška: Tumblr kredencijali nisu podešeni u GitHub Secrets!")
        return

    design = fetch_random_redbubble_design()
    if not design:
        print("Nije pronađen nijedan dizajn.")
        return

    print(f"Izabran dizajn: {design['title']}")
    keywords = extract_all_keywords(design['title'])
    keywords.extend(["illustration", "digitalart", "redbubble", "petzzzstudio", "stickers"])

    print("Preuzimam sliku dizajna...")
    img_path = "tumblr_temp_img.jpg"
    try:
        img_resp = requests.get(design['img_url'], headers=HEADERS, timeout=10)
        with open(img_path, "wb") as f:
            f.write(img_resp.content)
    except Exception as e:
        print(f"Greška pri preuzimanju slike: {e}")
        return

    caption_html = f"""
    <h2>🐾 {design['title']}</h2>
    <p>Discover unique artwork, stickers, t-shirts, and hoodies at Petzzz Studio!</p>
    <p>🛒 <strong><a href="{design['product_link']}">Shop the collection here</a></strong></p>
    """

    print("Povezujem se na Tumblr API...")
    client = pytumblr.TumblrRestClient(CONSUMER_KEY, CONSUMER_SECRET, OAUTH_TOKEN, OAUTH_SECRET)
    
    print("Objavljujem post na Tumblr-u...")
    response = client.create_photo(
        BLOG_NAME,
        state="published",
        tags=keywords,
        data=img_path,
        caption=caption_html
    )
    
    if 'id' in response:
        print(f"Uspešno objavljeno na Tumblr! Post ID: {response['id']}")
    else:
        print(f"Desila se greška prilikom objave: {response}")

    if os.path.exists(img_path):
        os.remove(img_path)

if __name__ == "__main__":
    post_to_tumblr()
