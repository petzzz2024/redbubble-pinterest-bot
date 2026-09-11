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

# Proširena lista životinja sa slikama
ANIMALS_DATA = {
    # Psi
    "corgi": "https://images.unsplash.com/photo-1519098901909-b1553a1190af?fit=crop&w=800&h=800&q=80",
    "bernese mountain dog": "https://images.unsplash.com/photo-1584362111166-7b83c78bd90a?fit=crop&w=800&h=800&q=80",
    "golden retriever": "https://images.unsplash.com/photo-1552053831-71594a27632d?fit=crop&w=800&h=800&q=80",
    "border collie": "https://images.unsplash.com/photo-1503256207526-0d5d80fa2f47?fit=crop&w=800&h=800&q=80",
    "english bulldog": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?fit=crop&w=800&h=800&q=80",
    "basset hound": "https://images.unsplash.com/photo-1543466835-00a7907e9de1?fit=crop&w=800&h=800&q=80",
    "belgian malinois": "https://images.unsplash.com/photo-1561037404-61cd46aa615b?fit=crop&w=800&h=800&q=80",
    "shiba inu": "https://images.unsplash.com/photo-1583337130417-3346a1be7dee?fit=crop&w=800&h=800&q=80",
    "red heeler": "https://images.unsplash.com/photo-1537151608828-ea2b11777ee8?fit=crop&w=800&h=800&q=80",
    "pug": "https://images.unsplash.com/photo-1517423440428-a5a00ad493e8?fit=crop&w=800&h=800&q=80",
    "norwegian lundehund": "https://images.unsplash.com/photo-1548199973-03cce0bbc87b?fit=crop&w=800&h=800&q=80",
    "chihuahua": "https://images.unsplash.com/photo-1518717758536-85ae29035b6d?fit=crop&w=800&h=800&q=80",
    "samoyed": "https://images.unsplash.com/photo-1529429612779-c8e40ef2f36d?fit=crop&w=800&h=800&q=80",
    "pitbull": "https://images.unsplash.com/photo-1554456854-55a06977c6f8?fit=crop&w=800&h=800&q=80",
    "husky": "https://images.unsplash.com/photo-1605568427561-40dd23c2acea?fit=crop&w=800&h=800&q=80",
    "dachshund": "https://images.unsplash.com/photo-1612222869049-d8ec83637a3c?fit=crop&w=800&h=800&q=80",

    # Mačke i divlje mačke
    "cat": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?fit=crop&w=800&h=800&q=80",
    "black cat": "https://images.unsplash.com/photo-1543852786-1cf6624b9987?fit=crop&w=800&h=800&q=80",
    "maine coon": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?fit=crop&w=800&h=800&q=80",
    "sphynx cat": "https://images.unsplash.com/photo-1513245543132-31f507417b26?fit=crop&w=800&h=800&q=80",
    "pallas cat": "https://images.unsplash.com/photo-1589656966895-2f33e7653819?fit=crop&w=800&h=800&q=80",
    "snow leopard": "https://images.unsplash.com/photo-1542858178-3011345dcb93?fit=crop&w=800&h=800&q=80",
    "jaguarundi": "https://images.unsplash.com/photo-1534188753412-3e26d0d618d6?fit=crop&w=800&h=800&q=80",

    # Ptice
    "canada goose": "https://images.unsplash.com/photo-1555169062-013468b47731?fit=crop&w=800&h=800&q=80",
    "crow": "https://images.unsplash.com/photo-1522921193457-27ece3c2853f?fit=crop&w=800&h=800&q=80",
    "great potoo": "https://images.unsplash.com/photo-1444464666168-49d633b86797?fit=crop&w=800&h=800&q=80",
    "cassowary": "https://images.unsplash.com/photo-1582220107107-590dc8b0ad3f?fit=crop&w=800&h=800&q=80",
    "green cheeked conure": "https://images.unsplash.com/photo-1552728089-57bdde30beb3?fit=crop&w=800&h=800&q=80",
    "pigeon": "https://images.unsplash.com/photo-1516570161868-f9a88e99990b?fit=crop&w=800&h=800&q=80",
    "silkie chicken": "https://images.unsplash.com/photo-1548550023-2bdb3c5beed7?fit=crop&w=800&h=800&q=80",
    "duck": "https://images.unsplash.com/photo-1459682687441-77722fa5158e?fit=crop&w=800&h=800&q=80",

    # Gmizavci i vodozemci
    "turtle": "https://images.unsplash.com/photo-1437622368342-7a3d73a34c8f?fit=crop&w=800&h=800&q=80",
    "blue pit viper": "https://images.unsplash.com/photo-1531386151447-fd76ad50012f?fit=crop&w=800&h=800&q=80",
    "hognose snake": "https://images.unsplash.com/photo-1504450758481-7338eba7524a?fit=crop&w=800&h=800&q=80",
    "corn snake": "https://images.unsplash.com/photo-1616231016625-728b26e03aeb?fit=crop&w=800&h=800&q=80",
    "argentine tegu": "https://images.unsplash.com/photo-1517457210672-882672722b51?fit=crop&w=800&h=800&q=80",
    "uromastyx": "https://images.unsplash.com/photo-1618698944510-449e798725ee?fit=crop&w=800&h=800&q=80",
    "leachianus gecko": "https://images.unsplash.com/photo-1550081682-16781295240f?fit=crop&w=800&h=800&q=80",
    "crested gecko": "https://images.unsplash.com/photo-1601058265017-eb6368d3ea95?fit=crop&w=800&h=800&q=80",
    "poison dart frog": "https://images.unsplash.com/photo-1558857563-b371033873b8?fit=crop&w=800&h=800&q=80",
    "pacman frog": "https://images.unsplash.com/photo-1582236816027-2e11899a16f2?fit=crop&w=800&h=800&q=80",

    # Morske i vodene životinje
    "sea otter": "https://images.unsplash.com/photo-1551085254-e96b210df58a?fit=crop&w=800&h=800&q=80",
    "harbor seal": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?fit=crop&w=800&h=800&q=80",
    "shark": "https://images.unsplash.com/photo-1560275619-4662e36fa65c?fit=crop&w=800&h=800&q=80",
    "vampire crab": "https://images.unsplash.com/photo-1604555122177-3e117498c407?fit=crop&w=800&h=800&q=80",
    "sea sheep nudibranch": "https://images.unsplash.com/photo-1582967788606-a171c1080cb0?fit=crop&w=800&h=800&q=80",

    # Ostali sisari, insekti i paučnjaci
    "capybara": "https://images.unsplash.com/photo-1589134720177-fba2ba7e1919?fit=crop&w=800&h=800&q=80",
    "wombat": "https://images.unsplash.com/photo-1558239994-46487e4513df?fit=crop&w=800&h=800&q=80",
    "honey badger": "https://images.unsplash.com/photo-1596489379633-85eeb9fb9d67?fit=crop&w=800&h=800&q=80",
    "beaver": "https://images.unsplash.com/photo-1616781702816-c73d9e83ec98?fit=crop&w=800&h=800&q=80",
    "platypus": "https://images.unsplash.com/photo-1521798365611-d5f0e1bc05df?fit=crop&w=800&h=800&q=80",
    "maned wolf": "https://images.unsplash.com/photo-1534188753412-3e26d0d618d6?fit=crop&w=800&h=800&q=80",
    "stoat": "https://images.unsplash.com/photo-1589656966895-2f33e7653819?fit=crop&w=800&h=800&q=80",
    "tibetan fox": "https://images.unsplash.com/photo-1590423789438-e62e105e4cce?fit=crop&w=800&h=800&q=80",
    "binturong": "https://images.unsplash.com/photo-1550974955-f76ea10c4316?fit=crop&w=800&h=800&q=80",
    "jumping spider": "https://images.unsplash.com/photo-1502161254066-6c74afbf07aa?fit=crop&w=800&h=800&q=80"
}

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text).strip('-')

def get_next_animal():
    """Bira nasumičnu životinju koja još nije korišćena u blogu."""
    used_animals = []
    html_files = glob.glob("blog/*.html")
    
    for file in html_files:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read().lower()
            for animal in ANIMALS_DATA.keys():
                if animal in content:
                    used_animals.append(animal)
                    
    unused_animals = [a for a in ANIMALS_DATA.keys() if a not in used_animals]
    
    # Ako ima nekorišćenih životinja, izaberi nasumičnu od njih
    if unused_animals:
        chosen = random.choice(unused_animals)
        print(f"Izabrana nekorišćena životinja: {chosen}")
        return chosen
    
    # Ako su sve već iskorišćene bar jednom, izaberi nasumičnu među onima koje su najmanje puta ponovljene
    min_count = min(used_animals.count(a) for a in ANIMALS_DATA.keys())
    least_used = [a for a in ANIMALS_DATA.keys() if used_animals.count(a) == min_count]
    chosen = random.choice(least_used)
    print(f"Sve životinje su upotrebljene. Izabrana iz grupe najmanje korišćenih: {chosen}")
    return chosen

def get_store_category(animal_keyword):
    clean_animal = animal_keyword.lower().strip()
    query_encoded = urllib.parse.quote(clean_animal)
    shop_search_url = f"https://www.redbubble.com/shop/?query={query_encoded}&artistUserName=Petzzz"
    
    fallback_img = "../Logo 2.png"
    cover_img = ANIMALS_DATA.get(clean_animal, fallback_img)

    return {
        "title": f"Explore Petzzz {clean_animal.title()} Designs",
        "img_url": cover_img,
        "product_link": shop_search_url
    }

def update_sitemap(post_url):
    sitemap_file = "sitemap.xml"
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    if not os.path.exists(sitemap_file):
        root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    else:
        try:
            ET.register_namespace('', "http://www.sitemaps.org/schemas/sitemap/0.9")
            tree = ET.parse(sitemap_file)
            root = tree.getroot()
        except Exception:
            root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    url_elem = ET.SubElement(root, "url")
    loc_elem = ET.SubElement(url_elem, "loc")
    loc_elem.text = post_url
    lastmod_elem = ET.SubElement(url_elem, "lastmod")
    lastmod_elem.text = today

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write(sitemap_file, encoding="utf-8", xml_declaration=True)
    print("Sitemap.xml uspešno ažuriran!")

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
        <div style="background:#fff; padding:25px; border-radius:12px; margin-bottom:20px; box-shadow:0 4px 15px rgba(0,0,0,0.05);">
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
            <img src="{category['img_url']}" alt="{animal} lovers gift ideas" style="max-width:100%; height:auto; max-height:450px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.1); object-fit:cover; display:inline-block;">
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
