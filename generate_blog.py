import os
import re
import datetime
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# Konfiguracija Gemini API-ja
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Lista SEO tema o ljubimcima sa pripadajućim ključnim rečima
TOPICS = [
    {"topic": "Top 10 Cute Gift Ideas for Corgi Lovers", "animal": "corgi"},
    {"topic": "Best Vinyl Stickers for Dog Moms in 2026", "animal": "dog"},
    {"topic": "Funny Dachshund Apparel and Hoodie Ideas", "animal": "dachshund"},
    {"topic": "Why Every French Bulldog Owner Needs Unique Accessories", "animal": "french bulldog"},
    {"topic": "Unique Gift Ideas for Black Cat Owners", "animal": "cat"},
    {"topic": "Best Pet Bandanas and T-Shirts for Golden Retrievers", "animal": "golden retriever"}
]

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text).strip('-')

def fetch_redbubble_product(animal_keyword):
    """Pretražuje Petzzz Redbubble prodavnicu za zadatu životinju i vraća sliku i link."""
    search_url = f"https://www.redbubble.com/people/Petzzz/shop?query={animal_keyword}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            img_tags = soup.find_all('img', src=re.compile(r'ih\d\.redbubble\.net'))
            
            for img in img_tags:
                src = img.get('src')
                alt = img.get('alt', f'Petzzz {animal_keyword.capitalize()} Design')
                parent_a = img.find_parent('a')
                
                if parent_a and parent_a.get('href'):
                    href = parent_a.get('href')
                    full_link = href if href.startswith('http') else f"https://www.redbubble.com{href}"
                    return {
                        "title": alt,
                        "img_url": src,
                        "product_link": full_link
                    }
    except Exception as e:
        print(f"Greška pri pretrazi Redbubble prodavnice: {e}")

    # Fallback opcija u slučaju blokade
    return {
        "title": f"Petzzz {animal_keyword.capitalize()} Collection",
        "img_url": "https://images.unsplash.com/photo-1543466835-00a7907e9de1?w=800&q=80",
        "product_link": "https://petzzz.redbubble.com"
    }

def generate_post():
    day_of_year = datetime.datetime.now().timetuple().tm_yday
    item = TOPICS[day_of_year % len(TOPICS)]
    topic = item["topic"]
    animal = item["animal"]
    slug = slugify(topic)
    
    product = fetch_redbubble_product(animal)
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    Write an engaging, SEO-optimized blog article about: "{topic}".
    Target audience: Pet lovers, dog/cat owners looking for gifts.
    Word count: 500-600 words.
    
    Format requirements:
    - Output ONLY the HTML body content (h2, p, ul, li, strong). Do NOT include <html> or <body> tags.
    - Naturally mention pet stickers, t-shirts, hoodies, and accessories.
    - Include 1 call-to-action button linking to: {product['product_link']}
      Formatted as:
      <a href="{product['product_link']}" target="_blank" style="display:inline-block; padding:12px 24px; background:#00d2d3; color:#fff; text-decoration:none; border-radius:30px; font-weight:bold; margin:20px 0;">Check Out Our {animal.capitalize()} Collection 🛍️</a>
    """
    
    response = model.generate_content(prompt)
    article_content = response.text

    product_html_banner = f"""
    <div style="text-align:center; margin: 30px 0; background:#f0f0f0; padding:20px; border-radius:12px;">
        <a href="{product['product_link']}" target="_blank">
            <img src="{product['img_url']}" alt="{product['title']}" style="max-width:100%; max-height:400px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.1);">
        </a>
        <p style="font-size:0.95em; color:#555; margin-top:12px; font-weight:600;">
            Featured Store Item: <a href="{product['product_link']}" target="_blank" style="color:#7b2cbf;">{product['title']}</a>
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
        h1 {{ color: #1c1328; font-size: 2em; margin-bottom: 10px; }}
        h2 {{ color: #7b2cbf; margin-top: 30px; }}
        footer {{ background: #1c1328; color: #bbb; text-align: center; padding: 25px; margin-top: 50px; font-size: 0.9em; }}
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
        <hr style="border:0; border-top:1px solid #eee; margin:20px 0;">
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
