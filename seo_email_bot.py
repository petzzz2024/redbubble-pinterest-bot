import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google import genai

GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
EMAIL_SENDER = os.environ.get('EMAIL_SENDER', '').strip()
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '').strip()
EMAIL_RECEIVER = os.environ.get('EMAIL_RECEIVER', '').strip()

# Proširena lista životinja i kategorija
PET_LIST = [
    "Corgi", "Black Cat", "French Bulldog", "Dachshund", "Capybara", 
    "Golden Retriever", "Pomeranian", "Shiba Inu", "German Shepherd", 
    "Maine Coon", "Parrot", "Hamster", "Rescue Dog", "Labrador", 
    "Poodle", "Beagle", "Sphynx Cat", "Cockatiel", "Husky", "Border Collie"
]

def generate_mega_report(selected_animals):
    client = genai.Client(api_key=GEMINI_KEY)
    
    animals_str = ", ".join(selected_animals)
    
    prompt = f"""
    You are a top Print-on-Demand (Redbubble & Pinterest) SEO Expert specializing in the pet niche.
    
    Selected 5 Animals/Pets for today: {animals_str}.
    
    For EACH of these 5 animals, generate 5 DISTINCT trending design ideas/sub-topics (Total 25 design packs).
    
    For EACH idea (1 to 5 per animal), provide:
    1. 💡 **Sub-topic Name & Design Concept** (e.g., "Retro Sunset Corgi Mom")
    2. 📝 **Redbubble SEO Title**: (Max 60 characters)
    3. 🏷️ **15 Redbubble Tags**: (Comma-separated, copy-paste ready)
    4. 📌 **Pinterest SEO Description**: (2-3 sentences + 5 relevant hashtags)
    5. 🎨 **AI Image Prompt**: (Ready-to-use prompt for Midjourney / DALL-E inside <code> tags)
    
    Format the entire output in clean, structured HTML for an email newsletter.
    Use clear headers (<h2> for Animal, <h3> for Idea), distinct content boxes, code blocks for tags and prompts, and elegant inline CSS styling.
    """

    models_to_try = [
        'gemini-3.7-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.1-pro-preview'
    ]

    for model_name in models_to_try:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            print(f"Mega SEO izveštaj uspešno generisan pomoću modela: {model_name}")
            return res.text.strip()
        except Exception as e:
            print(f"Model {model_name} je preopterećen, pokušavam sledeći model...")

    return "<p>Svi AI modeli su trenutno nedostupni.</p>"

def send_email(subject, html_content, selected_animals):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    full_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 750px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h1 style="color: #d32f2f; text-align: center;">🐾 Petzzz Daily Mega SEO Digest</h1>
        <p style="text-align: center; color: #555; font-size: 15px;"><strong>Današnje izabrane životinje:</strong> {', '.join(selected_animals)}</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;" />
        {html_content}
        <hr style="border: 0; border-top: 1px solid #eee; margin-top: 30px;" />
        <p style="font-size: 12px; color: #777; text-align: center;">Automatski generisano putem Redbubble AutoBot sistema.</p>
      </body>
    </html>
    """

    msg.attach(MIMEText(full_html, 'html'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

def main():
    # Nasumičan izbor 5 životinja za današnji izveštaj
    selected_animals = random.sample(PET_LIST, 5)
    print(f"Generišem mega izveštaj za životinje: {selected_animals}")
    
    html_report = generate_mega_report(selected_animals)
    subject = f"🐾 Mega SEO Report: 5 Životinja x 5 Tema ({', '.join(selected_animals[:3])}...)"
    
    send_email(subject, html_report, selected_animals)
    print("Mega SEO izveštaj sa 25 kompletnih priprema uspešno poslat na e-mail!")

if __name__ == "__main__":
    main()
