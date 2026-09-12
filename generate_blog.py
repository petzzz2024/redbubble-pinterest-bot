import os
import re
import glob
import random
import datetime
import requests
import urllib.parse
import xml.etree.ElementTree as ET
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GA_MEASUREMENT_ID = "G-JHTGX1J5HX"

# Zvanični Gemini 3 modeli
GEMINI_MODELS = [
    'gemini-3.8-flash',
    'gemini-3.7-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash',
    'gemini-3.5-flash-lite',
    'gemini-3.1-flash-lite'
]

SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "petzzz2024.github.io/redbubble-pinterest-bot")
INDEXNOW_KEY = "c8f1e2d3a4b5c6d7e8f9a0b1c2d3e4f5"

# Lista životinja koje bot pokriva
ANIMALS_DATA = [
    # Psi
    "corgi", "bernese mountain dog", "golden retriever", "border collie", 
    "english bulldog", "basset hound", "belgian malinois", "shiba inu", 
    "red heeler", "pug", "norwegian lundehund", "chihuahua", 
    "samoyed", "pitbull", "husky", "dachshund",

    # Mačke i divlje mačke
    "cat", "black cat", "maine coon", "sphynx cat", 
    "pallas cat", "snow leopard", "jaguarundi",

    # Ptice
    "canada goose", "crow", "great potoo", "cassowary", 
    "green cheeked conure", "pigeon", "silkie chicken", "duck",

    # Gmizavci i vodozemci
    "turtle", "blue pit viper", "hognose snake", "corn snake", 
    "argentine tegu", "uromastyx", "leachianus gecko", "crested gecko", 
    "poison dart frog", "pacman frog",

    # Morske i vodene životinje
    "sea otter", "harbor seal", "shark", "vampire crab", "sea sheep nudibranch",

    # Ostali sisari, insekti i paučnjaci
    "capybara", "wombat", "honey badger", "beaver", "platypus", 
    "maned wolf", "stoat", "tibetan fox", "binturong", "jumping spider"
]

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text).strip('-')

def get_next_animal():
    used_animals = []
    html_files = glob.glob("blog/*.html")
    
    for file in html_files:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read().lower()
            for animal in ANIMALS_DATA:
                if animal in content:
                    used_animals.append(animal)
                    
    unused_animals = [a for a in ANIMALS_DATA if a not in used_animals]
    
    if unused_animals:
        chosen = random.choice(unused_animals)
        print(f"Izabrana nekorišćena životinja: {chosen}")
        return chosen
    
    min_count = min(used_animals.count(a) for a in ANIMALS_DATA)
    least_used = [a for a in ANIMALS_DATA if used_animals.count(a) == min_count]
    chosen = random.choice(least_used)
    print(f"Sve životinje su upotrebljene. Izabrana iz grupe najmanje korišćenih: {chosen}")
    return chosen

def get_store_category(animal_keyword):
    clean_animal = animal_keyword.lower().strip()
    query_encoded = urllib.parse.quote(clean_animal)
    shop_search_url = f"https://www.redbubble.com/shop/?query={query_encoded}&artistUserName=Petzzz"
    
    # Pollinations.ai besplatan API za generisanje slike životinje
    prompt = urllib.parse.quote(f"cute high quality studio photo portrait of a {clean_animal}, detailed, vibrant colors, 8k")
    seed = random.randint(1000, 99999)
    ai_cover_img = f"https://image.pollinations.ai/prompt/{prompt}?width=800&height=800&nologo=true&seed={seed}"

    return {
        "title": f"Explore Petzzz {clean_animal.title()} Designs",
        "img_url": ai_cover_img,
        "product_link": shop_search_url
    }

def update_sitemap(post_url):
    sitemap_file = "sitemap.xml"
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    main_urls = [
        f"https://{SITE_DOMAIN}/index.html",
        f"https://{SITE_DOMAIN}/blog.html"
    ]
    
    if not os.path.exists(sitemap_file):
        root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    else:
        try:
            ET.register_namespace('', "http://www.sitemaps.org/schemas/sitemap/0.9")
            tree = ET.parse(sitemap_file)
            root = tree.getroot()
        except Exception:
            root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    existing_locs = [loc.text for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]

    for url in main_urls:
        if url not in existing_locs:
            url_elem = ET.SubElement(root, "url")
            ET.SubElement(url_elem, "loc").text = url
            ET.SubElement(url_elem, "lastmod").text = today

    if post_url not in existing_locs:
        url_elem = ET.SubElement(root, "url")
        ET.SubElement(url_elem, "loc").text = post_url
        ET.SubElement(url_elem, "lastmod").text = today

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write(sitemap_file, encoding="utf-8", xml_declaration=True)
    print("Sitemap.xml uspešno ažuriran sa glavnim stranicama i novim člankom!")

def update_rss(title, post_url, content_summary):
    rss_file = "rss.xml"
    pub_date = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
    clean_description = re.sub(r'<[^>]+>', '', content_summary)[:200] + "..."
    
    if not os.path.exists(rss_file):
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "Petzzz Studio Blog"
        ET.SubElement(channel, "link").text = f"https://{SITE_DOMAIN}"
        ET.SubElement(channel, "description").text = "Latest posts and gift guides from Petzzz Studio"
    else:
        try:
            tree = ET.parse(rss_file)
            rss = tree.getroot()
            channel = rss.find("channel")
        except Exception:
            rss = ET.Element("rss", version="2.0")
            channel = ET.SubElement(rss, "channel")

    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = post_url
    ET.SubElement(item, "description").text = clean_description
    ET.SubElement(item, "pubDate").text = pub_date

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write(rss_file, encoding="utf-8", xml_declaration=True)
    print("Rss.xml uspešno ažuriran!")

def notify_indexnow(post_url):
    endpoint = "https://api.indexnow.org/indexnow"
    payload = {
        "host": SITE_DOMAIN,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{SITE_DOMAIN}/{INDEXNOW_KEY}.txt",
        "urlList": [post_url]
    }
    headers = {"Content-Type": "application/json; charset=utf-8"}
    
    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 202]:
            print("IndexNow API: Uspešno poslato obaveštenje pretraživačima!")
        else:
            print(f"IndexNow API status ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"IndexNow API zahtev nije uspeo: {e}")

def update_blog_index():
    html_files = glob.glob("blog/*.html")
    articles_data = []
    
    for file in html_files:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
            
            title_match = re.search(r'<h1>(.*?)</h1>', content)
            title = title_match.group(1) if title_match else "Petzzz Article"
            
            date_match = re.search(r'Published on (.*?) by', content)
            if date_match:
                date_str = date_match.group(1).strip()
                try:
                    dt_obj = datetime.datetime.strptime(date_str, '%B %d, %Y')
                except ValueError:
                    dt_obj = datetime.datetime(2020, 1, 1)
            else:
                date_str = "Unknown Date"
                dt_obj = datetime.datetime(2020, 1, 1)
                
            articles_data.append({
                'file': file,
                'title': title,
                'date_str': date_str,
                'dt_obj': dt_obj
            })
            
    # Hronološko sortiranje svih sačuvanih članaka od najnovijeg ka najstarijem
    articles_data.sort(key=lambda x: x['dt_obj'], reverse=True)
    
    posts_list_html = ""
    for article in articles_data:
        posts_list_html += f"""
        <div style="background:#fff; padding:25px; border-radius:12px; margin-bottom:20px; box-shadow:0 4px 15px rgba(0,0,0,0.05);">
            <h3 style="margin-top:0; font-size:1.4em;"><a href="{article['file']}" style="text-decoration:none; color:#1c1328;">{article['title']}</a></h3>
            <p style="font-size:0.85em; color:#888; margin-bottom:15px;">Published on {article['date_str']}</p>
            <a href="{article['file']}" style="display:inline-block; padding:8px 16px; background:#e7d9fc; color:#7b2cbf; text-decoration:none; border-radius:6px; font-weight:600; font-size:0.9em;">Read Article ➔</a>
        </div>
        """

    index_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Petzzz Studio - Official Blog</title>
    <!-- Google Tag (gtag.js) - Google Analytics -->
    <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{GA_MEASUREMENT_ID}');
    </script>
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

def generate_post():
    if not GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY nije pronađen u environment varijablama!")

    client = genai.Client(api_key=GEMINI_API_KEY)
    animal = get_next_animal()
    
    topic_prompt = f"""
    You are an SEO expert. Write a catchy, viral blog post title about gift ideas or apparel for owners of a {animal.upper()}.
    OUTPUT STRICTLY THE TITLE AND NOTHING ELSE.
    Example: Top 10 Cozy Hoodies for {animal.capitalize()} Lovers
    """
    
    topic = None
    for model_name in GEMINI_MODELS:
        try:
            print(f"Pokušavam generisanje naslova pomoću modela: {model_name}...")
            resp = client.models.generate_content(
                model=model_name,
                contents=topic_prompt
            )
            if resp and resp.text:
                topic = resp.text.strip().replace('"', '')
                print(f"Naslov uspešno generisan sa {model_name}: {topic}")
                break
        except Exception as e:
            print(f"Greška na {model_name} (naslov): {e}")

    if not topic:
        topic = f"Top 10 Gift Ideas for {animal.capitalize()} Lovers"

    slug = slugify(topic)
    category = get_store_category(animal)
    
    article_prompt = f"""
    Write an engaging, SEO-optimized blog article about: "{topic}".
    Target audience: Owners of {animal} looking for gifts, t-shirts, stickers.
    Word count: 500-600 words.
    
    Format requirements:
    - Output ONLY the HTML body content (h2, p, ul, li, strong). Do NOT include <html> or <body> tags.
    - Naturally mention pet stickers, t-shirts, hoodies.
    - Include 1 call-to-action button linking to: {category['product_link']}
      Formatted exactly as:
      <a href="{category['product_link']}" target="_blank" style="display:inline-block; padding:12px 24px; background:#00d2d3; color:#ffffff !important; text-decoration:none; border-radius:30px; font-weight:bold; margin:20px 0;">See All Our {animal.capitalize()} Products 🛍️</a>
    """
    
    article_content = None
    for model_name in GEMINI_MODELS:
        try:
            print(f"Pokušavam generisanje članka pomoću modela: {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=article_prompt
            )
            if response and response.text:
                article_content = response.text
                print(f"Članak uspešno generisan sa {model_name}!")
                break
        except Exception as e:
            print(f"Greška na {model_name} (članak): {e}")

    if not article_content:
        raise Exception("Nijedan Gemini 3 model nije uspeo da vrati tekst. Proverite greške u logu iznad.")

    product_html_banner = f"""
    <div style="text-align:center; margin: 30px 0; background:#f0f0f0; padding:20px; border-radius:12px;">
        <a href="{category['product_link']}" target="_blank">
            <img src="{category['img_url']}" alt="{animal} lovers gift ideas" style="max-width:100%; height:auto; max-height:450px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.1); object-fit:cover; display:inline-block;" onerror="this.src='https://images.unsplash.com/photo-1543466835-00a7907e9de1?fit=crop&w=800&h=800&q=80'">
        </a>
        <p style="font-size:1.1em; margin-top:15px; font-weight:700;">
            <a href="{category['product_link']}" target="_blank" style="display:inline-block; padding:10px 25px; background:#7b2cbf; color:#ffffff !important; text-decoration:none; border-radius:8px; transition:0.3s;">
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
    <!-- Google Tag (gtag.js) - Google Analytics -->
    <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{GA_MEASUREMENT_ID}');
    </script>
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
        
    print(f"Blog post uspešno kreiran: {file_path}")
    
    update_blog_index()

    full_post_url = f"https://{SITE_DOMAIN}/{file_path}"
    update_sitemap(full_post_url)
    update_rss(topic, full_post_url, article_content)
    notify_indexnow(full_post_url)

if __name__ == "__main__":
    generate_post()
