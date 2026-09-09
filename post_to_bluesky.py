import os
import random
import urllib.parse
import requests
from atproto import Client

BSKY_HANDLE = os.environ.get("BSKY_HANDLE")
BSKY_PASSWORD = os.environ.get("BSKY_APP_PASSWORD")

# Baza životinja sa garantovano ispravnim slikama
ANIMALS_DATA = {
    "corgi": "https://images.unsplash.com/photo-1519098901909-b1553a1190af?w=800&q=80",
    "pug": "https://images.unsplash.com/photo-1517423440428-a5a00ad493e8?w=800&q=80",
    "husky": "https://images.unsplash.com/photo-1605568427561-40dd23c2acea?w=800&q=80",
    "dachshund": "https://images.unsplash.com/photo-1612222869049-d8ec83637a3c?w=800&q=80",
    "french bulldog": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=800&q=80",
    "cat": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=800&q=80",
    "golden retriever": "https://images.unsplash.com/photo-1552053831-71594a27632d?w=800&q=80"
}

def post_to_bluesky():
    if not BSKY_HANDLE or not BSKY_PASSWORD:
        print("Greška: Bluesky kredencijali nisu podešeni u GitHub Secrets!")
        return

    client = Client()
    client.login(BSKY_HANDLE, BSKY_PASSWORD)

    animal, img_src = random.choice(list(ANIMALS_DATA.items()))
    query_encoded = urllib.parse.quote(animal)
    shop_url = f"https://www.redbubble.com/shop/?query={query_encoded}&artistUserName=Petzzz"

    # Učitavanje slike sa interneta ili lokalnog logotipa
    if img_src.startswith("http"):
        img_data = requests.get(img_src).content
    else:
        with open("Logo 2.png", "rb") as f:
            img_data = f.read()

    hashtag_animal = animal.replace(" ", "")
    post_text = (
        f"Love {animal.capitalize()}s? 🐾 Discover unique {animal} stickers, "
        f"t-shirts, and hoodies at Petzzz Studio!\n\n"
        f"Shop collection: {shop_url}\n\n"
        f"#{hashtag_animal} #PetLovers #Redbubble #PetzzzStudio"
    )

    client.send_image(
        text=post_text,
        image=img_data,
        image_alt=f"Cute {animal} artwork preview - Petzzz Studio"
    )
    print(f"Uspešno objavljeno na Bluesky za životinju: {animal}")

if __name__ == "__main__":
    post_to_bluesky()
