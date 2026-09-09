import os
import re
import datetime
import urllib.parse
import google.generativeai as genai

# Konfiguracija Gemini API-ja
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Lista SEO tema i ključnih reči
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

def get_store_category(animal_keyword):
    """
    Generiše tačan link za pretragu VAŠEG Redbubble šopa i
    dodeljuje proverenu, 100% besplatnu sliku životinje.
    """
    # NOVI, ISPRAVNI REDBUBBLE LINK: Pretražuje celu bazu ali filtrira SAMO vaš username (Petzzz)
    query_encoded = urllib.parse.quote(animal_keyword)
    shop_search_url = f"https://www.redbubble.com/shop/?query={query_encoded}&artistUserName=Petzzz"
    
    # Proverene slike bez Premium zaštite (100% rade)
    unsplash_images = {
        "corgi": "https://images.unsplash.com/photo-1519098901909-b1553a1190af?w=800&q=80",
        "dog": "https://images.unsplash.com/photo-1537151608828-ea2b11777ee8?w=800&q=80",
        "dachshund": "https://images.unsplash.com/photo-1612222869049-d8ec83637a3c?w=800&q=80",
        "french bulldog": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=800&q=80",
        "cat": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=800&q=80",
        "golden retriever": "https://images.unsplash.com/photo-1552053831-71594a27632d?w=800&q=80"
    }
    
    cover_img = unsplash_images.get(animal_keyword.lower(), "https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=800&q=80")

    return {
        "title": f"Explore Petzzz {animal_keyword.capitalize()} Designs",
        "img_url": cover_img,
        "product_link": shop_search_url
    }

def generate_post():
    day_of_year = datetime.datetime.now().timetuple().tm_yday
    item = TOPICS[day_of_year % len(TOPICS)]
    topic = item["topic"]
    animal = item["animal"]
    slug = slugify(topic)
    
    # 1. Dobijanje tačnih podataka za vaš šop i naslovne slike
    category = get_store_category(animal)
    
    # 2. Generisanje SEO Teksta
    prompt = f"""
    Write an engaging, SEO-optimized blog article about: "{topic}".
    Target audience: Pet lovers, dog/cat owners looking for gifts.
    Word count: 500-600 words.
    
    Format requirements:
    - Output ONLY the HTML body content (h2, p, ul, li, strong). Do NOT include <html> or <body> tags.
    - Naturally mention pet stickers, t-shirts, hoodies, and accessories.
    - Include 1 call-to-action button linking to: {category['product_link']}
      Formatted as:
      <a href="{category['product_link']}" target="_blank" style="display:inline-block; padding:12px 24px; background:#00d2d3; color:#1c1328; text-decoration:none; border-radius:30px; font-weight:bold; margin:20px 0;">See All Our {animal.capitalize()} Products 🛍️</a>
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

    # 3. HTML za naslovnu sliku koja vodi pravo u pretragu (Dodat poseban parametar da slika uvek bude na sredini)
    product_html_banner = f"""
    <div style="text-align:center; margin: 30px 0; background:#f0f0f0; padding:20px; border-radius:12px;">
        <a href="{category['product_link']}" target="_blank">
            <img src="{category['img_url']}" alt="{animal} lovers gift ideas" style="max-width:100%; height:auto; max-height:450px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.1); object-fit:cover; display:inline-block;">
        </a>
        <p style="font-size:1.1em; margin-top:15px; font-weight:700;">
            <a href="{category['product_link']}" target="_blank" style="display:inline-block; padding:10px 25px; background:#7b2cbf; color:white; text-decoration:none; border-radius:8px; transition:0.3s;">
                View Petzzz {animal.capitalize()} Collection ➔
            </a>
        </p>
    </div>
    """

    # 4. Sklapanje kompletnog fajla
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
        a:hover {{ opacity: 0.8; }}
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
