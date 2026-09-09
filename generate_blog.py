import os
import re
import datetime
import urllib.parse
import glob
import google.generativeai as genai

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

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
    """Pravi Redbubble pretragu za izabranu životinju i daje sliku."""
    clean_animal = animal_keyword.lower().strip()
    query_encoded = urllib.parse.quote(clean_animal)
    shop_search_url = f"https://www.redbubble.com/shop/?query={query_encoded}&artistUserName=Petzzz"
    
    # Lista prelepih sigurnih slika
    unsplash_images = {
        "corgi": "https://images.unsplash.com/photo-1519098901909-b1553a1190af?w=800&q=80",
        "pug": "https://images.unsplash.com/photo-1517423440428-a5a00ad493e8?w=800&q=80",
        "husky": "https://images.unsplash.com/photo-1605568427561-40dd23c2acea?w=800&q=80",
        "dachshund": "https://images.unsplash.com/photo-1612222869049-d8ec83637a3c?w=800&q=80",
        "french bulldog": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=800&q=80",
        "cat": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=800&q=80",
        "golden retriever": "https://images.unsplash.com/photo-1552053831-71594a27632d?w=800&q=80"
    }
    
    # REZERVNA SLIKA JE SADA VAŠ LOGO
    fallback_img = "../Logo 2.png"

    cover_img = unsplash_images.get(clean_animal, fallback_img)

    return {
        "title": f"Explore Petzzz {clean_animal.title()} Designs",
        "img_url": cover_img,
        "product_link": shop_search_url
    }

def update_blog_index():
    """Prolazi kroz sve blogove i pravi glavnu blog.html stranicu (Blog Hub)"""
    html_files = glob.glob("blog/*.html")
    posts_list_html = ""
    
    html_files.sort(key=os.path.getmtime, reverse=True)
    
    for file in html_files:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
            title_match = re.search(r'<h1>(.*?)</h1>', content)
            title = title_match.group(1) if title_match else "Petzzz Article"
            
            date_match = re.search(r'Published on (.*?) by', content)
            date_str = date_match.group(1) if date_match else ""
            
        posts_list_html += f"""
        <div style="background:#fff; padding:25px; border-radius:12px; margin-bottom:20px; box-shadow:0 4px 15px rgba(0,0,0,0.05); transition:transform 0.2s;">
            <h3 style="margin-top:0; font-size:1.4em;"><a href="{file}" style="text-decoration:none; color:#1c1328;">{title}</a></h3>
            <p style="font-size:0.85em; color:#888; margin-bottom:15px;">Published on {date_str}</p>
            <a href="{file}" style="display:inline-block; padding:8px 16px; background:#e7d9fc; color:#7b2cbf; text-decoration:none; border-radius:6px; font-weight:600; font-size:0.9em;">Read Article ➔</a>
        </div>
        """

    index_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Petzzz Studio - Official Blog</title>
    <link rel="icon" type="image/png" href="Logo 2.png">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Poppins', sans-serif; background: #f8f9fa; color: #333; margin:0; line-height:1.7; }}
        header {{ background: #fff; border-bottom: 1px solid #eaeaea; padding: 15px 20px; }}
        .nav-container {{ max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
        .logo-box {{ display: flex; align-items: center; text-decoration: none; gap: 10px; font-weight:700; color:#3a1c5c; }}
        .logo-img {{ width: 40px; height: 40px; border-radius: 50%; }}
        .nav-links a {{ margin-left: 20px; text-decoration: none; color: #555; font-weight: 600; font-size: 0.9em; }}
        .nav-links a:hover {{ color: #8e44ad; }}
        .container {{ max-width: 800px; margin: 50px auto; padding: 0 20px; }}
        h1 {{ color: #1c1328; font-size: 2.5em; margin-bottom: 30px; text-align:center; }}
        footer {{ background: #1c1328; color: #bbb; text-align: center; padding: 30px 20px; margin-top: 50px; font-size: 0.9em; }}
        footer a {{ color: #fff; }}
    </style>
</head>
<body>
    <header>
        <div class="nav-container">
            <a href="index.html" class="logo-box">
                <img src="Logo 2.png" alt="Petzzz Logo" class="logo-img">
                <span>Petzzz Studio</span>
            </a>
            <div class="nav-links">
                <a href="index.html">Home Store</a>
                <a href="https://petzzz.redbubble.com" target="_blank">Redbubble Shop</a>
            </div>
        </div>
    </header>

    <div class="container">
        <h1>Latest Pet Articles & Gift Guides</h1>
        {posts_list_html}
    </div>

    <footer>
        <p>&copy; 2026 Petzzz Studio. | <a href="privacy.html">Privacy Policy</a></p>
    </footer>
</body>
</html>"""

    with open("blog.html", "w", encoding="utf-8") as f:
        f.write(index_page)
    print("Blog Hub (blog.html) uspesno azuriran!")

def generate_post():
    topic_prompt = """
    You are an SEO expert. Pick ONE random pet EXACTLY from this list: Corgi, Pug, Husky, Dachshund, French Bulldog, Cat, Golden Retriever.
    Do NOT use any other words, abbreviations, or nicknames for the animal name.
    Then, write a catchy blog post title about gift ideas or apparel for owners of this pet.
    OUTPUT STRICTLY IN THIS FORMAT AND NOTHING ELSE:
    AnimalName|Catchy Blog Title
    Example: Husky|Top 10 Cozy Hoodies for Husky Lovers
    """
    
    generated_topic = None
    animal = None
    topic = None

    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(topic_prompt)
            if "|" in resp.text:
                animal, topic = resp.text.strip().split('|', 1)
                animal = animal.strip()
                topic = topic.strip()
                break
        except:
            continue

    if not animal or not topic:
        animal = "Pug"
        topic = "Top 10 Amazing Gifts for Pug Lovers"

    slug = slugify(topic)
    category = get_store_category(animal)
    
    # OVDE JE BOJA DUGMETA PROMENJENA U #ffffff (BELA)
    article_prompt = f"""
    Write an engaging, SEO-optimized blog article about: "{topic}".
    Target audience: Owners of {animal} looking for gifts, t-shirts, stickers.
    Word count: 500-600 words.
    
    Format requirements:
    - Output ONLY the HTML body content (h2, p, ul, li, strong). Do NOT include <html> or <body> tags.
    - Naturally mention pet stickers, t-shirts, hoodies.
    - Include 1 call-to-action button linking to: {category['product_link']}
      Formatted as:
      <a href="{category['product_link']}" target="_blank" style="display:inline-block; padding:12px 24px; background:#00d2d3; color:#ffffff; text-decoration:none; border-radius:30px; font-weight:bold; margin:20px 0;">See All Our {animal.capitalize()} Products 🛍️</a>
    """
    
    article_content = None
    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(article_prompt)
            article_content = response.text
            break
        except:
            continue

    if not article_content:
        raise Exception("Nijedan model nije uspeo da generise sadrzaj.")

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
        .back-btn {{ display:inline-block; margin-bottom:20px; color:#7b2cbf; text-decoration:none; font-weight:600; font-size:0.9em; }}
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
        <a href="../blog.html" class="back-btn">← Back to All Articles</a>
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
    
    update_blog_index()

if __name__ == "__main__":
    generate_post()
