import os
import random
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google import genai

GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
EMAIL_SENDER = os.environ.get('EMAIL_SENDER', '').strip()
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '').strip()
EMAIL_RECEIVER = os.environ.get('EMAIL_RECEIVER', '').strip()

PET_TOPICS = [
    "dog mom shirt", "funny cat sticker", "corgi gift", "french bulldog design",
    "rescue dog tote bag", "golden retriever mug", "pet loss memorial",
    "cute cat phone case", "dachshund merch", "capybara sticker", "pomeranian tshirt",
    "cat dad hoodie", "shiba inu sticker", "german shepherd art", "funny pet quotes"
]

def get_google_trends(query):
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={query}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data[1][:6]
    except Exception as e:
        print(f"Greška pri preuzimanju Google trendova: {e}")
    return []

def generate_report(topic, keywords):
    client = genai.Client(api_key=GEMINI_KEY)
    
    prompt = f"""
    Ti si vodeći SEO i Print-on-Demand stručnjak za Redbubble i Pinterest u niši kućnih ljubimaca.
    Analiziraj zadatu temu '{topic}' i sledeće trenutno popularne Google pretrage kupaca: {keywords}.

    Generiši struktuiran izveštaj na engleskom jeziku koji sadrži sledeće sekcije:
    
    1. 💡 **DESIGN CONCEPT & NICHE ANGLE**: Kratak predlog kakav tačno grafički dizajn napraviti na osnovu ovih trendova.
    2. 📝 **REDBUBBLE OPTIMIZED TITLE**: Glavni SEO naslov na engleskom (do 60 karaktera).
    3. 🏷️ **15 REDBUBBLE TAGS (COPY-PASTE READY)**: Tačno 15 razdvojenih zarezom, spremnih za direktno lepljenje u Redbubble.
    4. 📌 **PINTEREST DESCRIPTION**: Privlačan SEO opis za Pinterest sa 5 relevantnih hashtagova.

    Formatiraj ceo odgovor u čistom HTML formatu pogodnom za e-mail (koristi <h2>, <p>, <ul>, <li>, <strong>, <code> elemente sa lepim stilizovanjem).
    """

    models_to_try = [
        'gemini-3.7-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.1-pro-preview'
    ]

    for model_name in models_to_try:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            print(f"SEO izveštaj izgenerisan pomoću modela: {model_name}")
            return res.text.strip()
        except Exception as e:
            print(f"Model {model_name} nedostupan, pokušavam sledeći...")

    return "<p>Svi AI modeli su trenutno nedostupni.</p>"

def send_email(subject, html_content):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    # Obloga e-mail poruke
    full_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h1 style="color: #d32f2f; text-align: center;">🐾 Petzzz Daily SEO Digest</h1>
        <hr style="border: 0; border-top: 1px solid #eee;" />
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
    topic = random.choice(PET_TOPICS)
    keywords = get_google_trends(topic)
    print(f"Analiziram SEO trendove za: {topic}")
    
    html_report = generate_report(topic, keywords)
    subject = f"🐾 Dnevni Redbubble SEO Izveštaj: {topic.title()}"
    
    send_email(subject, html_report)
    print("Dnevni SEO izveštaj je uspešno poslat na e-mail!")

if __name__ == "__main__":
    main()
