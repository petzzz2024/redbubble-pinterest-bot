import os
import csv
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
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

genai.configure(api_key=GEMINI_API_KEY)

def get_design_data():
    model = genai.GenerativeModel('gemini-3.1-flash-lite')
    
    prompt = """
    Ti si stručnjak za Redbubble SEO i dizajn. Istraži internet sa životinjskim nišama koje ljudi pretražuju i smisli 1 jedinstvenu ideju za dizajn majice/stikera vezanu za životinje.
    Vrati ISKLJUČIVO validan JSON format, bez ikakvog dodatnog teksta ili markdown oznaka, u ovom formatu:
    {
      "title": "Kratak SEO naslov na engleskom (max 5-6 riječi)",
      "description": "SEO opis do 150 znakova na engleskom s ključnim riječima",
      "tags": "tag1, tag2, tag3... (Točno 15 tagova. Prvi tag MORA biti točan naziv te životinje na engleskom). Svi tagovi trebaju da budu na engleskom",
      "image_prompt": "Prompt za sliku na engleskom. OBAVEZNO uključi ove fraze: circular badge layout, emblem design, isolated on solid white background, vector style sticker design of [opis životinje], text wrapping inside the circular frame reading '[Tekst]', high contrast, clean lines, flat colors."
    }
    """
    response = model.generate_content(prompt)
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

def generate_and_process_image(image_prompt, title):
    encoded_prompt = urllib.parse.quote(image_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&model=flux&nologo=true"
    
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Pollinations API greška: {response.status_code}")
        
    input_image = Image.open(BytesIO(response.content))
    output_transparent = remove(input_image)
    
    canvas = Image.new("RGBA", (2000, 2000), (0, 0, 0, 0))
    output_transparent.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
    
    x = (2000 - output_transparent.width) // 2
    y = (2000 - output_transparent.height) // 2
    canvas.paste(output_transparent, (x, y), output_transparent)
    
    clean_filename = "".join(c for c in title if c.isalnum() or c in (' ', '_')).rstrip()
    os.makedirs("output_images", exist_ok=True)
    filepath = f"output_images/{clean_filename}.png"
    canvas.save(filepath, "PNG")
    
    return filepath

def send_email_with_limit(csv_path, image_paths):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("Email podaci nisu uneseni u GitHub Secrets.")
        return

    zip_filename = "redbubble_designs.zip"
    # Maksimalna veličina sirovih datoteka prije nego što Base64 "napuše" fajl (cca 18 MB)
    MAX_RAW_SIZE = 18 * 1024 * 1024 
    
    added_images = 0
    current_size = os.path.getsize(csv_path)

    # Pakiranje u ZIP pazeći na limit
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(csv_path, arcname=os.path.basename(csv_path))
        
        for img_path in image_paths:
            img_size = os.path.getsize(img_path)
            # Ako dodavanjem ove slike prelazimo limit od 18MB, zaustavi pakiranje
            if current_size + img_size > MAX_RAW_SIZE:
                print(f"Dostignut limit za email (do 25MB). Spakovano {added_images} slika.")
                break
            
            zipf.write(img_path, arcname=os.path.basename(img_path))
            current_size += img_size
            added_images += 1

    # Slanje Emaila
    msg = EmailMessage()
    msg['Subject'] = f'Tvoji Redbubble dizajni (Spakovano: {added_images})'
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg.set_content(f"U privitku se nalazi tablica i {added_images} slika.\nSlike koje nisu stale zbog limita od 25MB možeš preuzeti sa GitHuba pod 'Artifacts'.")

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
    
    for i in range(25):
        try:
            print(f"Generiranje {i+1}/25...")
            data = get_design_data()
            
            # --- NOVI SIGURNOSNI KORAK ---
            # Ako Gemini vrati podatke unutar liste (niza), uzimamo prvi element
            if isinstance(data, list):
                data = data[0]
            # -----------------------------
            
            filepath = generate_and_process_image(data["image_prompt"], data["title"])
            
            data["file_path"] = filepath
            results.append(data)
            generated_images.append(filepath)
            print(f"✅ Uspješno: {data['title']}")
        except Exception as e:
            print(f"❌ Greška na {i+1}: {e}")
        
        # Pauza od 15 sekundi da se izbegne Error 429 (Quota Exceeded) i Error 402
        print("Pauza od 15 sekundi radi limita API-ja...")
        time.sleep(15)

    if results:
        csv_path = "redbubble_metadata.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "description", "tags", "image_prompt", "file_path"])
            writer.writeheader()
            writer.writerows(results)
        
        # Pozivamo pametno slanje emaila na kraju
        send_email_with_limit(csv_path, generated_images)
