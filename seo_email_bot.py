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

def get_trending_animals(client):
    """Pita AI da sam istraži i predloži 5 najprofitabilnijih životinja za današnji dan."""
    prompt = """
    You are an expert Print-on-Demand market researcher.
    Identify 5 highly profitable, trending, or high-demand animal/pet niches for Redbubble right now.
    Include a mix of specific pet breeds (like 'Cavalier King Charles', 'Sphynx Cat') and internet-popular/meme animals (like 'Capybara', 'Opossum', 'Highland Cow', 'Raccoon', 'Red Panda', 'Axolotl', 'Goose').
    Return ONLY a single line with a comma-separated list of exactly 5 animals. Do not include any other text, bullet points, or explanations.
    """
    
    models_to_try = ['gemini-3.7-flash', 'gemini-3.5-flash-lite', 'gemini-3.1-pro-preview']
    for model_name in models_to_try:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            raw_text = res.text.strip().replace('\n', '')
            animals = [a.strip().strip('.') for a in raw_text.split(',') if a.strip()]
            if len(animals) >= 5:
                print(f"🤖 AI trendovi uspešno izvučeni pomoću modela: {model_name}")
                return animals[:5]
        except Exception as e:
            print(f"Model {model_name} nedostupan za pretragu trendova, pokušavam sledeći...")
            
    print("Svi AI modeli nedostupni. Koristim rezervnu profitabilnu listu.")
    backup_list = ["Capybara", "Opossum", "Raccoon", "Highland Cow", "Red Panda", "Axolotl", "Silly Goose", "Frog", "Corgi", "Black Cat"]
    return random.sample(backup_list, 5)

def generate_mega_report(client, selected_animals):
    animals_str = ", ".join(selected_animals)
    
    prompt = f"""
    You are a top Print-on-Demand (Redbubble & Pinterest) SEO Expert specializing in the pet and animal niche.
    
    The market research algorithm has selected these 5 highly profitable Animals/Pets for today: {animals_str}.
    
    For EACH of these 5 animals, generate 5 DISTINCT trending design ideas/sub-topics (Total 25 design packs).
    Focus on funny quotes, vintage retro styles, cute aesthetics, or internet humor.
    
    For EACH idea (1 to 5 per animal), provide:
    1. 💡 **Sub-topic Name & Design Concept** (e.g., "Retro Sunset Corgi Mom")
    2. 📝 **Redbubble SEO Title**: (Max 60 characters)
    3. 🏷️ **15 Redbubble Tags**: (Comma-separated, copy-paste ready)
    4. 🛒 **Redbubble Description**: (Engaging 2-3 sentence product description optimized for Redbubble and Google SEO. Make it ready to copy-paste into the Redbubble description box).
    5. 📌 **Pinterest SEO Description**: (2-3 sentences + 5 relevant hashtags)
    6. 🎨 **AI Image Prompt**: (Ready-to-use prompt for Midjourney / DALL-E inside <code> tags)
    
    Format the entire output in clean, structured HTML for an email newsletter.
    Use clear headers (<h2> for Animal, <h3> for Idea), distinct content boxes, code blocks for tags and prompts, and elegant inline CSS styling.
    """

    models_to_try = ['gemini-3.7-flash', 'gemini-3.5-flash-lite', 'gemini-3.1-pro-preview']

    for model_name in models_to_try:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            print(f"✅ Mega SEO izveštaj uspešno generisan pomoću modela: {model_name}")
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
        <h1 style="color: #d32f2f; text-align: center;">📈 Petzzz AI Trend & SEO Digest</h1>
        <p style="text-align: center; color: #555; font-size: 15px;"><strong>Današnje najprofitabilnije životinje po AI proceni:</strong><br> {', '.join(selected_animals)}</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;" />
        {html_content}
        <hr style="border: 0; border-top: 1px solid #eee; margin-top: 30px;" />
        <p style="font-size: 12px; color: #777; text-align: center;">Automatski generisano putem AI Market Research Bota.</p>
      </body>
    </html>
    """

    msg.attach(MIMEText(full_html, 'html'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

def main():
    client = genai.Client(api_key=GEMINI_KEY)
    
    print("Započinjem istraživanje tržišta...")
    selected_animals = get_trending_animals(client)
    print(f"Pronađeni današnji trendovi: {selected_animals}")
    
    print("Generišem 25 SEO priprema za dobijene trendove...")
    html_report = generate_mega_report(client, selected_animals)
    
    subject = f"🔥 Top Trendovi: {', '.join(selected_animals[:3])}... (25 Ideja)"
    
    send_email(subject, html_report, selected_animals)
    print("Mega SEO izveštaj zasnovan na AI trendovima je uspešno poslat na e-mail!")

if __name__ == "__main__":
    main()
