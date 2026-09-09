import os
import smtplib
import glob
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

def count_recent_files(pattern, days=7):
    """Broji generisane objave u poslednjih N dana."""
    count = 0
    now = datetime.now()
    files = glob.glob(pattern)
    for f in files:
        file_mtime = datetime.fromtimestamp(os.path.getmtime(f))
        if now - file_mtime <= timedelta(days=days):
            count += 1
    return count

def generate_report():
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
        print("Greška: Email kredencijali nisu podešeni u GitHub Secrets!")
        return

    # Brojanje generisanih blogova za proteklih 7 dana
    new_blogs = count_recent_files("blog/*.html", days=7)
    
    msg = MIMEMultipart("alternative")
    msg['Subject'] = f"📊 Petzzz Studio - Nedeljni Izveštaj Automatizacije ({datetime.now().strftime('%d.%m.%Y')})"
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f9; padding: 20px; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #7b2cbf; border-bottom: 2px solid #e7d9fc; padding-bottom: 10px;">🐾 Petzzz Studio Nedeljni Pregled</h2>
            <p>Evo sumarnog izveštaja aktivnosti svih radnih tokova za proteklih 7 dana:</p>
            
            <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                <thead>
                    <tr style="background: #7b2cbf; color: #ffffff;">
                        <th style="padding: 10px; text-align: left;">Kanal / Bot Aktivnost</th>
                        <th style="padding: 10px; text-align: center;">Status</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-bottom: 1px solid #ddd;">
                        <td style="padding: 12px;"><strong>Bluesky Auto-Post</strong></td>
                        <td style="padding: 12px; text-align: center; color: #2ecc71; font-weight: bold;">Aktivno (3x Dnevno)</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #ddd;">
                        <td style="padding: 12px;"><strong>Tumblr Auto-Post</strong></td>
                        <td style="padding: 12px; text-align: center; color: #2ecc71; font-weight: bold;">Aktivno (3x Dnevno)</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #ddd;">
                        <td style="padding: 12px;"><strong>Pinterest Auto-Pin</strong></td>
                        <td style="padding: 12px; text-align: center; color: #e67e22; font-weight: bold;">Na čekanju (Pending Access)</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #ddd;">
                        <td style="padding: 12px;"><strong>SEO Blog Članci</strong></td>
                        <td style="padding: 12px; text-align: center; font-weight: bold;">{new_blogs} novih članaka</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #ddd;">
                        <td style="padding: 12px;"><strong>IndexNow (Bing/Yandex)</strong></td>
                        <td style="padding: 12px; text-align: center; color: #2ecc71; font-weight: bold;">Instant Indeksirano</td>
                    </tr>
                </tbody>
            </table>

            <div style="margin-top: 25px; padding: 15px; background: #f8f9fa; border-left: 4px solid #7b2cbf; border-radius: 4px;">
                <p style="margin: 0; font-size: 0.9em;">
                    📌 <strong>Pinterest Status:</strong> Čim Pinterest odobri API pristup, u tabeli promenite status u <code>Aktivno</code> i skripta iz <code>pinterest.yml</code> će početi sa radom.
                </p>
            </div>
            
            <p style="margin-top: 30px; font-size: 0.8em; color: #888; text-align: center;">
                Generisano automatski preko GitHub Actions | Petzzz Studio
            </p>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_content, "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("Nedeljni izveštaj uspešno poslat na e-mail!")
    except Exception as e:
        print(f"Greška pri slanju e-maila: {e}")

if __name__ == "__main__":
    generate_report()
