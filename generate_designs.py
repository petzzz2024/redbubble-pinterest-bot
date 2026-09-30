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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

genai.configure(api_key=GEMINI_API_KEY)

def get_batch_of_designs(batch_index, used_animals):
    model = genai.GenerativeModel('gemini-3.1-flash-lite')
    
    zabrana = ""
    if used_animals:
        zabrana = f"STROGO ZABRANJENO: NE SMEŠ koristiti sledeće životinje: {', '.join(used_animals)}. Izaberi neku potpuno novu i drugačiju!"

    prompt = f"""
    Ti si stručnjak za Redbubble SEO i dizajn. Ovo je serija broj {batch_index} od 5.
    
    ZADATAK:
    1. Izaberi JEDNU specifičnu, popularnu životinju. {zabrana}
    2. Osmisli 5 POTPUNO RAZLIČITIH ideja za dizajn vezanih ISKLJUČIVO za tu životinju.
    
    Vrati ISKLJUČIVO validan JSON NIZ (Array) koji sadrži tačno 5 objekata u ovom formatu:
    [
      {{
        "animal_used": "tačan naziv životinje na engleskom (ovo je važno da znamo koju si izabrao)",
        "title": "Kratak SEO naslov na engleskom (max 5-6 riječi)",
        "description": "SEO opis do 150 znakova na engleskom s ključnim riječima",
        "tags": "tag1, tag2, tag3... (Točno 15 tagova. Prvi tag je naziv životinje)",
        "image_prompt": "Flat 2D vector graphic design, digital artwork of [opis životinje i situacije]. Circular badge emblem. Text reads '[Tekst]'. Solid white background. STRICTLY NO MOCKUPS, NO physical physical stickers, NO hands, NO 3D, NO shadows."
      }}
    ]
    """
    response = model.generate_content(prompt)
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

def generate_and_process_image(image_prompt, title):
    if not FAL_KEY:
        raise Exception("Nedostaje FAL_KEY u GitHub Secrets!")
        
    # Prelazak na flux/schnell model radi drastično niže cijene
    url = "https://fal.run/fal-ai/flux/schnell"
    
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
    
    img_response = requests.get(image_url)
    input_image = Image.open(BytesIO(img_response.content))
    
    # Skidanje pozadine
    output_transparent = remove(input_image)
    
    # KORAK ZA ODSECANJE NEVIDLJIVIH IVICA (CROP)
    bbox = output_transparent.getbbox()
    if bbox:
        output_transparent = output_transparent.crop(bbox)
    
    canvas = Image.new("RGBA", (2000, 2000), (0, 0, 0, 0))
    output_transparent.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
    
    x = (2000 - output_transparent.width) // 2
    y = (2000 - output_transparent.height) // 2
    canvas.paste(output_transparent, (x, y), output_transparent)
    
    clean_filename = "".join(c for c in title if c.isalnum() or c in (' ', '_')).rstrip()
    os.makedirs("output_images", exist_ok=True)
    filepath = f"output_images/{clean_filename}.png"
    canvas.save(filepath, "PNG")
    
    return filepath

def send_chunked_emails(text_path, image_paths):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("Email podaci nedostaju.")
        return

    MAX_ZIP_SIZE = 18 * 1024 * 1024 
    email_counter = 1
    current_zip_images = []
    current_size = os.path.getsize(text_path)
    
    all_chunks = []

    for img in image_paths:
        img_size = os.path.getsize(img)
        if current_size + img_size > MAX_ZIP_SIZE:
            all_chunks.append(current_zip_images)
            current_zip_images = [img]
            current_size = os.path.getsize(text_path) + img_size
        else:
            current_zip_images.append(img)
            current_size += img_size
            
    if current_zip_images:
        all_chunks.append(current_zip_images)

    print(f"Slike su podeljene u {len(all_chunks)} email(ova) zbog veličine.")

    for chunk in all_chunks:
        zip_filename = f"redbubble_part_{email_counter}.zip"
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(text_path, arcname=os.path.basename(text_path))
            for img in chunk:
                zipf.write(img, arcname=os.path.basename(img))
                
        msg = EmailMessage()
        msg['Subject'] = f'Tvoji Redbubble Dizajni - Deo {email_counter}/{len(all_chunks)}'
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        msg.set_content(f"Deo {email_counter} sa {len(chunk)} slika i Notepad podacima je u prilogu.")

        with open(zip_filename, 'rb') as f:
            msg.add_attachment(f.read(), maintype='application', subtype='zip', filename=zip_filename)

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
                smtp.send_message(msg)
            print(f"Email {email_counter}/{len(all_chunks)} je uspešno poslan!")
        except Exception as e:
            print(f"Greška pri slanju emaila {email_counter}: {e}")
            
        email_counter += 1

if __name__ == "__main__":
    results = []
    generated_images = []
    used_animals = []
    
    for i in range(5):
        try:
            print(f"Tražim životinju {i+1}/5 i generišem 5 njenih dizajna...")
            batch_data = get_batch_of_designs(i + 1, used_animals)
            
            current_animal = batch_data[0].get("animal_used", "unknown_animal")
            if current_animal not in used_animals:
                used_animals.append(current_animal)
            
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
                f.write(f"Životinja: {item.get('animal_used', '')}\n")
                f.write(f"Naslov: {item.get('title', '')}\n")
                f.write(f"Opis: {item.get('description', '')}\n")
                f.write(f"Tagovi: {item.get('tags', '')}\n")
                f.write(f"Slika (Ime fajla): {os.path.basename(item.get('file_path', ''))}\n")
                f.write("\n")
        
        send_chunked_emails(txt_path, generated_images)
