import os
import re
import datetime
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# Konfiguracija Gemini API-ja
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Lista SEO tema
TOPICS = [
    {"topic": "Top 10 Cute Gift Ideas for Corgi Lovers", "animal": "corgi"},
    {"topic": "Best Vinyl Stickers for Dog Moms in 2026", "animal": "dog"},
    {"topic": "Funny Dachshund Apparel and Hoodie Ideas", "animal": "dachshund"},
    {"topic": "Why Every French Bulldog Owner Needs Unique Accessories", "animal": "french bulldog"},
    {"topic": "Unique Gift Ideas for Black Cat Owners", "animal": "cat"},
    {"topic": "Best Pet Bandanas and T-Shirts for Golden Retrievers", "animal": "golden retriever"}
]

GEMINI_MODELS = [
    'gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.6-flash',
    'gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite',
    'gemini-2.0-flash', 'gemini-1.5-flash'
]

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text).strip('-')

def fetch_redbubble_product(animal_keyword):
    """Pretražuje prodavnicu, uz strogu proveru imena životinje u naslovu dizajna."""
    search_url = f"https://www.redbubble.com/people/Petzzz/shop?query={animal_keyword}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            img_tags = soup.find_all('img', src=re.compile(r'ih\d\.redbubble\.net'))
            
            for img in img_tags:
                alt_text = img.get('alt', '').lower()
                
                # STROGA PROVERA: Slika mora sadržati ime životinje u opisu
                if animal_keyword.lower() in alt_text:
                    src = img.get('src')
                    parent_a = img.find_parent('a')
                    
                    if parent_a and parent_a.get('href'):
                        href = parent_a.get('href')
                        full_link = href if href.startswith('http') else f"https://www.redbubble.com{href}"
                        return {
                            "title": img.get('alt', f'Petzzz {animal_keyword.capitalize()} Design').title(),
                            "img_url": src,
                            "product_link": full_link
                        }
    except Exception as e:
        print(f"Greška pri pretrazi: {e}")

    # REZERVNA OPCIJA: Ako Redbubble blokira bota ili dizajn nije nađen
    # Ubacuje prelepu sliku te životinje, a link vodi na tačnu pretragu u vašem šopu!
    unsplash_images = {
        "corgi": "https://images.unsplash.com/photo-1543466835-00a7907e9de1?w=800&q=80",
        "dog": "https://images.unsplash.com/photo-1537151608828-ea2b11777ee8?w=800&q=80",
        "dachshund": "https://images.unsplash.com/photo-1517849845537-4d257902454a?w=800&q=80",
        "french bulldog": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=800&q=80",
        "cat": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=800&q=80",
        "golden retriever": "https://images.unsplash.com/photo-1552053831-71594a27632d?w=800&q=80"
    }
    
    fallback_img = unsplash_images.get(animal_keyword.lower(), "https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=800&q=80")

    return {
        "title": f"Explore Our {animal_keyword.capitalize()} Collection",
        "img_url": fallback_img,
        "product_link": search_url
    }

def generate_post():
    day_of_year = datetime.datetime.now().timetuple().tm_yday
    item = TOPICS[day_of_year % len(TOPICS)]
    topic = item["topic"]
    animal = item["animal"]
    slug = slugify(topic)
    
    product = fetch_redbubble_product(animal)
    
    prompt = f"""
    Write an engaging, SEO-optimized blog article about: "{topic}".
    Target audience: Pet lovers, dog/cat owners looking for gifts.
    Word count: 500-600 words.
    
    Format requirements:
    - Output ONLY the HTML body content (h2, p, ul, li, strong). Do NOT include <html> or <body> tags.
    - Naturally mention pet stickers, t-shirts, hoodies, and accessories.
    - Include 1 call-to-action button linking to: {product['product_link']}
      Formatted as:
      <a href="{product['product_link']}" target="_blank" style="display:inline-block; padding:12px 24px; background:#00d2d3; color:#1c1328; text-decoration:none; border-radius:30px; font-weight:bold; margin:20px 0;">Check Out Our {animal.capitalize()} Collection 🛍️</a>
    """
    
    article_content = None
    for model_name in GEMINI_MODELS:
        try:
            print(f"Pokušavam generisanje preko modela: {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            article_content = response.text
            print(f"Uspešno generisano preko modela: {model_name}")
            break
        except Exception as e:
            print(f"Model {model_name} nije uspeo: {e}. Prelazim na sledeći...")

    if not article_content:
        raise Exception("Nijedan Gemini model s liste nije uspeo da generiše sadržaj.")

    product_html_banner = f"""
    <div style="text-align:center; margin: 30px 0; background:#f0f0f0; padding:20px; border-radius:12px;">
        <a href="{product['product_link']}" target="_blank">
            <img src="{product['img_url']}" alt="{product['title']}" style="max-width:100%; max-height:400px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.1); object-fit:cover;">
        </a>
        <p style="font-size:1.05em; color:#333; margin-top:15px; font-weight:700;">
            <a href="{product['product_link']}" target="_blank" style="color:#7b2cbf; text-decoration:none;">{product['title']} ➔</a>
        </p>
    </div>
    """

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{topic} - Petzzz Studio Blog</title>
    <link rel="icon" type="image/png" href="../Logo 2.png">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Poppins', sans-serif; background: #f8f9fa; color: #333; margin:0; line-height:1.7; }}
        header {{ background: #fff; border-bottom: 1px solid #eaeaea; padding: 15px 20px; }}
        .nav-container {{ max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
        .logo-box {{ display: flex; align-items: center; text-decoration: none; gap: 10px; font-weight:700; color:#3a1c5c; }}
        .logo-img {{ width: 40px; height: 40px; border-radius: 50%; }}
        .container {{ max-width: 800px; margin: 40px auto; background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }}
        h1 {{ color: #1c1328; font-size: 2.2em; margin-bottom: 10px; line-height: 1.2; }}
        h2 {{ color: #7b2cbf; margin-top: 35px; }}
        footer {{ background: #1c1328; color: #bbb; text-align: center; padding: 30px 20px; margin-top: 50px; font-size: 0.9em; }}
        footer a {{ color: #fff; }}
    </style>
</head>
<body>
    <header>
        <div class="nav-container">
            <a href="../index.html" class="logo-box">
                <img src="../Logo 2.png" alt="Petzzz Logo" class="logo-img">
                <span>Petzzz Studio</span>
            </a>
            <a href="https://petzzz.redbubble.com" target="_blank" style="color:#7b2cbf; text-decoration:none; font-weight:600;">Visit Redbubble Shop 🛍️</a>
        </div>
    </header>

    <div class="container">
        <h1>{topic}</h1>
        <p><em>Published on {datetime.date.today().strftime('%B %d, %Y')} by Petzzz Studio Team</em></p>
        
        {product_html_banner}
        
        <hr style="border:0; border-top:1px solid #eaeaea; margin:30px 0;">
        {article_content}
    </div>

    <footer>
        <p>&copy; 2026 Petzzz Studio. | <a href="../privacy.html">Privacy Policy</a></p>
    </footer>
</body>
</html>"""

    os.makedirs("blog", exist_ok=True)
    file_path = f"blog/{slug}.html"
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_html)
        
    print(f"Blog post uspesno kreiran: {file_path}")

if __name__ == "__main__":
    generate_post()
