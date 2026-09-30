import os
import json
import requests
import urllib.parse
import smtplib
import zipfile
import time
from email.message import EmailMessage
from io import BytesIO
from PIL import Image
from rembg import remove
import google.generativeai as genai

# API ključevi i Email podaci
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

genai.configure(api_key=GEMINI_API_KEY)

def get_batch_of_designs(batch_index):
    model = genai.GenerativeModel('gemini-3.1-flash-lite')
    
    prompt = f"""
    Ti si stručnjak za Redbubble SEO i dizajn. Ovo je serija broj {batch_index} od 5.
    
    ZADATAK:
    1. Izaberi JEDNU specifičnu, popularnu životinju (svaki put izaberi neku novu, zanimljivu životinjsku nišu).
    2. Osmisli 5 POTPUNO RAZLIČITIH i jedinstvenih ideja za dizajn majice/stikera vezanih ISKLJUČIVO za tu istu životinju (npr. različite situacije, tekstovi, stilovi).
    
    Vrati ISKLJUČIVO validan JSON NIZ (Array) koji sadrži tačno 5 objekata, bez markdown oznaka (bez ```json), tačno u ovom formatu:
    [
      {{
        "title": "Kratak SEO naslov na engleskom (max 5-6 riječi)",
        "description": "SEO opis do 150 znakova na engleskom s ključnim riječima",
        "tags": "tag1, tag2, tag3... (Točno 15 tagova. Prvi tag MORA biti točan naziv te životinje na engleskom). Svi tagovi na engleskom.",
        "image_prompt": "Vector illustration sticker of [opis životinje i specifične situacije], isolated on solid white background. Clean 2D flat style, bold black outlines, Adobe Illustrator style, highly detailed. Circular badge emblem design. Text wrapping perfectly inside the circular frame reading '[Tekst]'."
      }},
      ... (i tako još 4 objekta za istu životinju)
    ]
    """
    response = model.generate_content(prompt)
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

def generate_and_process_image(image_prompt, title):
    if not FAL_KEY:
        raise Exception("Nedostaje FAL_KEY u GitHub Secrets!")
        
    url = "[https://fal.run/fal-ai/recraft-v3](https://fal.run/fal-ai/recraft-v3)"
    headers = {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": image_prompt,
        "image_size": "square_hd"
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Fal.ai greška: {response.text}")
        
    result = response.json()
    image_url = result["images"][0]["url"]
    
    # Preuzimanje gotove slike
    img_response = requests.get(image_url)
    input_image = Image.open(BytesIO(img_response.content))
    
    # Brisanje pozadine pomoću rembg
    output_transparent = remove(input_image)
    
    # Postavljanje na 2000x2000 transparentno platno SKROZ DO IVICA
    canvas = Image.new("RGBA", (2000, 2000), (0, 0, 0, 0))
    output_transparent.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
    
    x = (2000 - output_transparent.width) // 2
    y = (2000 - output_transparent.height) // 2
    canvas.paste(output_transparent, (x, y), output_transparent)
    
    # Čuvanje slike pod imenom iz naslova
    clean_filename = "".join(c for c in title if c.isalnum() or c in (' ', '_')).rstrip()
    os.makedirs("output_images", exist_ok=True)
    filepath = f"output_images/{clean_filename}.png"
    canvas.save(filepath, "PNG")
    
    return filepath

def send_email_with_limit(text_path, image_paths):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("Email podaci nisu uneseni u GitHub Secrets.")
        return

    zip_filename = "redbubble_designs.zip"
    MAX_RAW_SIZE = 18 * 1024 * 1024 
    
    added_images = 0
    current_size = os.path.getsize(text_path)

    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(text_path, arcname=os.path.basename(text_path))
        
        for img_path in image_paths:
            img_size = os.path.getsize(img_path)
            if current_size + img_size > MAX_RAW_SIZE:
                print(f"Dostignut limit za email (do 25MB). Spakovano {added_images} slika.")
                break
            
            zipf.write(img_path, arcname=os.path.basename(img_path))
            current_size += img_size
            added_images += 1

    msg = EmailMessage()
    msg['Subject'] = f'Tvoji Redbubble dizajni (Spakovano: {added_images})'
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg.set_content(f"U privitku se nalazi Notepad fajl s podacima i {added_images} slika (2000x2000 do ivica).\nSlike koje nisu stale zbog limita od 25MB preuzmi sa GitHuba pod 'Artifacts'.")

    with open(zip_filename, 'rb') as f:
        msg.add_attachment(f.read(), maintype='application', subtype='zip', filename=zip_filename)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print("Email je uspješno poslan!")
    except Exception as e:
        print(f"Greška pri slanju emaila: {e}")

if __name__ == "__main__":
    results = []
    generated_images = []
    
    for i in range(5):
        try:
            print(f"Tražim životinju {i+1}/5 i generišem 5 njenih dizajna...")
            batch_data = get_batch_of_designs(i + 1)
            
            for j, data in enumerate(batch_data):
                design_num = (i * 5) + j + 1
                print(f"  -> Generisanje slike {design_num}/25: {data['title']}")
                
                filepath = generate_and_process_image(data["image_prompt"], data["title"])
                
                data["file_path"] = filepath
                results.append(data)
                generated_images.append(filepath)
                
                time.sleep(2)
                
        except Exception as e:
            print(f"❌ Greška na seriji životinje {i+1}: {e}")
        
        time.sleep(10)

    if results:
        txt_path = "redbubble_podaci.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            for index, item in enumerate(results):
                f.write(f"--- DIZAJN {index + 1} ---\n")
                f.write(f"Naslov: {item.get('title', '')}\n")
                f.write(f"Opis: {item.get('description', '')}\n")
                f.write(f"Tagovi: {item.get('tags', '')}\n")
                f.write(f"Slika (Ime fajla): {os.path.basename(item.get('file_path', ''))}\n")
                f.write("\n")
        
        send_email_with_limit(txt_path, generated_images)
