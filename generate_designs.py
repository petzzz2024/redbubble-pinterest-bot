import os
import json
import requests
import zipfile
import time
from io import BytesIO
from PIL import Image, ImageFilter
from rembg import remove
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)

# LISTA MODELA: Skripta će ići redom. Ako jedan pukne zbog limita, prelazi na sljedeći.
AVAILABLE_MODELS = [
    'gemini-3.8-flash',
    'gemini-3.5-flash-lite',
    'gemini-3.1-flash-lite',
    'gemini-3.7-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash'
]

def generate_with_fallback(prompt_text):
    """
    Pokušava generisati sadržaj prolazeći kroz sve dostupne modele.
    Ako jedan model baci grešku (npr. Rate Limit), automatski prelazi na sljedeći.
    """
    for model_name in AVAILABLE_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_text)
            return response.text
        except Exception as e:
            print(f"    [!] Model {model_name} nije uspio (Greška: {e}). Pokušavam sljedeći...")
            time.sleep(2) # Kratka pauza prije pokušaja sa novim modelom
            
    # Ako su apsolutno svi modeli pukli
    raise Exception("Svi Gemini modeli su preopterećeni ili van funkcije!")

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

def get_unique_trending_animals(used_animals, target_count=5):
    """
    FAZA 1: Traži trendi životinje koristeći fallback sistem modela.
    """
    fresh_animals = []
    banned_words = ['forbidden', 'wait', 'none', 'nema', 'zabranjeno', 'animal', 'unknown', 'here', 'are']
    
    while len(fresh_animals) < target_count:
        needed = target_count - len(fresh_animals)
        forbidden_list = used_animals + fresh_animals
        forbidden_str = ", ".join(forbidden_list) if forbidden_list else "nema zabranjenih"
        
        prompt = f"""
        Ti si stručnjak za Print-on-Demand trendove. Tvoj zadatak je da mi daš tačno {needed} trendi životinja.
        
        CRVENO UPOZORENJE - STROGO ZABRANJENO spominjati ove životinje:
        [{forbidden_str}]
        
        Vrati ISKLJUČIVO validan JSON niz stringova (Array of strings) sa imenima tih životinja na engleskom.
        Nema objašnjenja, nema toka misli, NEMA rečenica. Samo JSON.
        
        Primer ispravnog odgovora:
        ["capybara", "red panda", "axolotl"]
        """
        
        try:
            raw_response_text = generate_with_fallback(prompt)
            clean_text = raw_response_text.replace("```json", "").replace("```", "").strip()
            suggested = json.loads(clean_text)
            
            for animal in suggested:
                clean_animal = animal.strip().lower()
                
                if clean_animal and len(clean_animal) < 20 and not any(bad in clean_animal for bad in banned_words):
                    if clean_animal not in forbidden_list and clean_animal not in fresh_animals:
                        fresh_animals.append(clean_animal)
                        if len(fresh_animals) == target_count:
                            break
                        
            print(f"  -> Trenutno imamo {len(fresh_animals)}/{target_count} sigurnih novih životinja...")
            time.sleep(2) 
            
        except Exception as e:
            print(f"  -> Greška pri traženju životinja (loš JSON ili su svi modeli pukli): {e}. Pokušavam ponovo...")
            time.sleep(5)
            
    return fresh_animals

def get_designs_for_animal(animal):
    """FAZA 2: Generiše 5 dizajna sa kratkom frazom za lentu na dnu."""
    prompt = f"""
    Ti si stručnjak za Print-on-Demand i Redbubble SEO, Google trend expert.
    Osmisli 5 POTPUNO RAZLIČITIH dizajna za životinju: {animal.upper()}.
    
    Vrati ISKLJUČIVO validan JSON NIZ (Array) koji sadrži tačno 5 objekata u ovom formatu:
    [
      {{
        "title": "Kratak SEO naslov na engleskom (min 4-7 reči). Bez reči 'sticker', 'design'.",
        "description": "SEO opis od 150 do 200 znakova na engleskom",
        "tags": "tag1, tag2, tag3... (Točno 15 tagova. Prvi tag je {animal})",
        "visual_scene": "Kratak opis radnje/scene na engleskom, npr. 'wearing retro sunglasses and playing video games'. BEZ spominjanja teksta, pozadine ili kruga.",
        "text": "Samo kratka, spretna fraza NA ENGLESKOM koja ide u lentu/pravougaonik na dnu (npr. 'GAMER VIBES'). STROGO ZABRANJENO je dodavanje instrukcija o boji ili prevoda!"
      }}
    ]
    """
    raw_response_text = generate_with_fallback(prompt)
    clean_text = raw_response_text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

def generate_and_process_image(visual_scene, text, title, animal_name):
    if not FAL_KEY:
        raise Exception("Nedostaje FAL_KEY u GitHub Secrets!")
        
    # PROMPT: Bela pozadina + crni stroke + lenta na dnu sa tekstom
    image_prompt = (
        f"A standalone flat 2D vector illustration graphic design. "
        f"Subject: A cute 2D cartoon {animal_name} {visual_scene}. "
        f"Outline: The entire illustration MUST have a bold black outline (stroke). "
        f"Banner & Text: Positioned strictly at the very bottom below the animal, there is a stylized horizontal rectangle containing bold typography reading exactly '{text}'. "
        f"Style: Flat 2D vector art, clean crisp sharp edges, solid vibrant colors, NO shading, NO drop shadows, NO 3D effects. "
        f"Composition: The artwork MUST be completely isolated on a PURE, SOLID FLAT WHITE BACKGROUND (#FFFFFF)."
    )
    
    # NEGATIVNI PROMPT: Zabranjujemo crnu pozadinu, stiker efekte i sjenke
    negative_prompt = (
        "black background, dark background, sticker peel, die cut, drop shadow, 3d render, "
        "realistic, photograph, glow, blurry edges, brush strokes, gradient background, scenery, border, circular frame, watermark, messy edges, floating text outside banner"
    )
    
    headers = {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}
    
    # 1. Generisanje slike koristeći Z Image Turbo
    url_image_gen = "https://fal.run/fal-ai/z-image/turbo"
    payload_image_gen = {
        "prompt": image_prompt, 
        "negative_prompt": negative_prompt,
        "image_size": "square_hd"
    }
    
    response_image_gen = requests.post(url_image_gen, headers=headers, json=payload_image_gen)
    if response_image_gen.status_code != 200:
        raise Exception(f"Fal.ai Z Image Turbo greška: {response_image_gen.text}")
        
    result_image_gen = response_image_gen.json()
    original_image_url = result_image_gen["images"][0]["url"]
    
    # Preuzimanje generisane slike
    img_response = requests.get(original_image_url)
    input_image = Image.open(BytesIO(img_response.content))
    
    # 2. Skidanje bele pozadine preko REMBG alata sa Alpha Matting
    output_transparent = remove(
        input_image, 
        post_process_mask=True,
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=3
    )
    
    # 3. Skaliranje i čuvanje na platno 8000x8000
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
        
        # Retry mechanism za Telegram
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(zip_filename, 'rb') as f:
                    response = requests.post(url, data=data, files={"document": f}, timeout=120)
                    if response.status_code == 200:
                        print(f"✅ Telegram paket {zip_counter}/{len(all_chunks)} uspješno poslan!")
                        break
                    else:
                        print(f"❌ Greška pri slanju na Telegram: {response.text}")
            except requests.exceptions.RequestException as e:
                print(f"⏳ Attempt {attempt + 1} failed: {e}. Retrying in 5 seconds...")
                time.sleep(5)
        else:
            print(f"🚨 Failed to send package {zip_counter} after {max_retries} attempts.")
                
        zip_counter += 1

if __name__ == "__main__":
    results = []
    used_animals = load_used_animals()
    
    print("🤖 [FAZA 1] Analiziram trendove i prikupljam 5 sigurnih, novih životinja...")
    fresh_animals = get_unique_trending_animals(used_animals, target_count=5)
    print(f"🎯 Konačna lista za danas: {', '.join(fresh_animals).upper()}")
    
    print("\n🎨 [FAZA 2] Započinjem generisanje dizajna i slika...")
    for i, current_animal in enumerate(fresh_animals):
        try:
            print(f"\n--- Životinja {i+1}/5: {current_animal.upper()} ---")
            batch_data = get_designs_for_animal(current_animal)
            
            used_animals.append(current_animal)
            
            for j, data in enumerate(batch_data):
                design_num = (i * 5) + j + 1
                print(f"  -> Kreiram sliku {design_num}/25: {data['title']}")
                
                filepath = generate_and_process_image(data["visual_scene"], data["text"], data["title"], current_animal)
                
                data["file_path"] = filepath
                data["safe_animal_name"] = get_safe_name(current_animal)
                results.append(data)
                
                time.sleep(2)
                
        except Exception as e:
            print(f"❌ Greška na životinji {current_animal}: {e}")
        
        time.sleep(10)

    save_used_animals(used_animals)

    if results:
        print("\n📦 Pakovanje u ZIP i slanje na Telegram...")
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
