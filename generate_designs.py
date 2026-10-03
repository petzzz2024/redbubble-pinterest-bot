import os
import json
import requests
import urllib.parse
import zipfile
import time
from io import BytesIO
from PIL import Image
from rembg import remove
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)

def get_safe_name(text):
    return "".join(c for c in text if c.isalnum() or c in (' ', '_')).rstrip()

def load_used_animals(filename="used_animals.txt"):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    return []

def save_used_animals(animals, filename="used_animals.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        for animal in sorted(set(animals)):
            if animal: 
                f.write(f"{animal}\n")

def get_batch_of_designs(batch_index, used_animals):
    model = genai.GenerativeModel('gemini-3.1-flash-lite')
    
    forbidden_str = ", ".join(used_animals) if used_animals else "nema zabranjenih"

    prompt = f"""
    Ti si stručnjak za Print-on-Demand (POD) i Redbubble SEO. Prati trenutne internet trendove. Ovo je serija {batch_index} od 5.

    CRVENO UPOZORENJE - STROGO ZABRANJENE ŽIVOTINJE (već smo ih radili i NE SMIJEŠ ih ponoviti):
    [{forbidden_str}]

    ZADATAK:
    1. Izaberi JEDNU specifičnu, popularnu životinju koja ima veliki broj pretraga, ali NIJE na gornjoj listi zabranjenih.
    2. Osmisli 5 POTPUNO RAZLIČITIH dizajna za tu JEDNU novu životinju.
    
    Vrati ISKLJUČIVO validan JSON NIZ (Array) koji sadrži tačno 5 objekata u ovom formatu:
    [
      {{
        "animal_used": "SAMO i isključivo ime životinje na engleskom (npr. 'red panda'). Bez rečenica, objašnjavanja i bez dvotačke!",
        "title": "Kratak SEO naslov na engleskom (max 5-6 riječi). Bez reči 'sticker', 'design'.",
        "description": "SEO opis do 150 znakova na engleskom",
        "tags": "tag1, tag2, tag3... (Točno 15 tagova. Prvi tag je naziv životinje)",
        "visual_scene": "Kratak opis radnje na engleskom, npr. 'wearing sunglasses and playing video games'. BEZ spominjanja pozadine, okvira ili kruga.",
        "text": "Kratak tekst koji ide na stiker, npr. 'GAMER VIBES'"
      }}
    ]
    """
    response = model.generate_content(prompt)
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

def generate_and_process_image(visual_scene, text, title, animal_name):
    if not FAL_KEY:
        raise Exception("Nedostaje FAL_KEY u GitHub Secrets!")
        
    image_prompt = f"A cute 2D vector graphic illustration of a {animal_name} {visual_scene}. The entire artwork AND the text '{text}' MUST be strictly contained INSIDE a perfectly round, thick continuous black circular border. White background outside the circle. No elements, no leaves, and no text can break or extend past the circular border. Clean flat design, sticker art style, striking colors, flawless anatomy."
    
    url = "https://fal.run/fal-ai/flux/schnell"
    headers = {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}
    payload = {"prompt": image_prompt, "image_size": "square_hd"}
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Fal.ai greška: {response.text}")
        
    result = response.json()
    img_response = requests.get(result["images"][0]["url"])
    input_image = Image.open(BytesIO(img_response.content))
    
    # DODATO ALPHA MATTING - Skida "bijeli oreol" i pravi oštru ivicu
    output_transparent = remove(
        input_image, 
        post_process_mask=True,
        alpha_matting=True,
        alpha_matting_erode_size=3  # "Odgrize" 3 piksela sa ivice da ukloni bijelu liniju
    )
    
    bbox = output_transparent.getbbox()
    if bbox:
        output_transparent = output_transparent.crop(bbox)
    
    target_size = 8000
    ratio = min(target_size / output_transparent.width, target_size / output_transparent.height)
    new_w = int(output_transparent.width * ratio)
    new_h = int(output_transparent.height * ratio)
    output_transparent = output_transparent.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    canvas = Image.new("RGBA", (8000, 8000), (0, 0, 0, 0))
    x = (8000 - new_w) // 2
    y = (8000 - new_h) // 2
    canvas.paste(output_transparent, (x, y), output_transparent)
    
    safe_animal = get_safe_name(animal_name)
    safe_title = get_safe_name(title)
    
    folder_path = os.path.join("output_images", safe_animal)
    os.makedirs(folder_path, exist_ok=True)
    
    filepath = os.path.join(folder_path, f"{safe_title}.png")
    canvas.save(filepath, "PNG")
    
    return filepath

def send_telegram_chunks(files_to_zip):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram podaci nedostaju u GitHub Secrets.")
        return

    MAX_ZIP_SIZE = 48 * 1024 * 1024
    zip_counter = 1
    current_zip_files = {}
    current_size = 0
    all_chunks = []

    for local_path, arc_name in files_to_zip.items():
        file_size = os.path.getsize(local_path)
        if current_size + file_size > MAX_ZIP_SIZE and current_zip_files:
            all_chunks.append(current_zip_files)
            current_zip_files = {local_path: arc_name}
            current_size = file_size
        else:
            current_zip_files[local_path] = arc_name
            current_size += file_size
            
    if current_zip_files:
        all_chunks.append(current_zip_files)

    for chunk in all_chunks:
        zip_filename = f"redbubble_part_{zip_counter}.zip"
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for local_path, arc_name in chunk.items():
                zipf.write(local_path, arcname=arc_name)
                
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": f"🚀 Redbubble Dizajni - Dio {zip_counter}/{len(all_chunks)} (8000x8000 px)"
        }
        
        with open(zip_filename, 'rb') as f:
            response = requests.post(url, data=data, files={"document": f})
            if response.status_code == 200:
                print(f"✅ Telegram paket {zip_counter}/{len(all_chunks)} uspješno poslan!")
            else:
                print(f"❌ Greška pri slanju na Telegram: {response.text}")
                
        zip_counter += 1

if __name__ == "__main__":
    results = []
    used_animals = load_used_animals()
    
    for i in range(5):
        try:
            print(f"\nTražim trendi životinju {i+1}/5...")
            batch_data = get_batch_of_designs(i + 1, used_animals)
            
            raw_animal = batch_data[0].get("animal_used", "unknown_animal")
            if ":" in raw_animal:
                raw_animal = raw_animal.split(":")[-1]
            current_animal = raw_animal.strip().lower()
            
            print(f"Gemini je izabrao: {current_animal.upper()}")
            if current_animal not in used_animals:
                used_animals.append(current_animal)
            
            for j, data in enumerate(batch_data):
                design_num = (i * 5) + j + 1
                print(f"  -> Generisanje slike {design_num}/25: {data['title']}")
                
                filepath = generate_and_process_image(data["visual_scene"], data["text"], data["title"], current_animal)
                
                data["file_path"] = filepath
                data["safe_animal_name"] = get_safe_name(current_animal)
                results.append(data)
                
                time.sleep(2)
                
        except Exception as e:
            print(f"❌ Greška na seriji {i+1}: {e}")
        
        time.sleep(10)

    save_used_animals(used_animals)

    if results:
        grouped_results = {}
        files_to_zip = {} 
        
        for item in results:
            animal = item["safe_animal_name"]
            if animal not in grouped_results:
                grouped_results[animal] = []
            grouped_results[animal].append(item)
            
        for animal, items in grouped_results.items():
            folder_path = os.path.join("output_images", animal)
            txt_path = os.path.join(folder_path, f"{animal}_podaci.txt")
            
            with open(txt_path, "w", encoding="utf-8") as f:
                for index, item in enumerate(items):
                    f.write(f"--- DIZAJN {index + 1} ---\n")
                    f.write(f"Naslov: {item.get('title', '')}\n")
                    f.write(f"Opis: {item.get('description', '')}\n")
                    f.write(f"Tagovi: {item.get('tags', '')}\n")
                    f.write(f"Slika (Ime fajla): {os.path.basename(item.get('file_path', ''))}\n")
                    f.write("\n")
            
            files_to_zip[txt_path] = f"{animal}/{os.path.basename(txt_path)}"
            for item in items:
                img_path = item["file_path"]
                files_to_zip[img_path] = f"{animal}/{os.path.basename(img_path)}"
        
        send_telegram_chunks(files_to_zip)
