"""
Gmail SMTP email sender for welcome/onboarding emails.
Uses Python built-in smtplib with Gmail app password authentication.
"""

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def send_welcome_email(to_email: str, first_name: str, last_name: str,
                        invite_link: str) -> bool:
    """
    Send a welcome email with Slack workspace invite link.
    Returns True if sent successfully.
    """
    sender = os.getenv("GMAIL_SENDER_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")

    if not sender or not password:
        logger.error("Gmail credentials not configured (GMAIL_SENDER_ADDRESS / GMAIL_APP_PASSWORD)")
        return False

    if not to_email or not invite_link:
        logger.error("Missing to_email or invite_link")
        return False

    name = f"{first_name} {last_name}".strip() or "Member"
    display_first = first_name or "there"

    subject = "RSG-Türkiye'ye Hoş Geldiniz! / Welcome to RSG-Türkiye!"

    html_body = f"""\
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2>Merhabalar!</h2>

    <p>Sizlere yakın zamanda ISCB-SC RSG-T&uuml;rkiye katılım formunu doldurduğunuz i&ccedil;in yazıyoruz.</p>

    <p>Kısaca grubumuzu tanıtmak istiyoruz ve ayrıca varsa sorularınızı yanıtlamak bizleri mutlu eder.</p>

    <p>ISCB-SC'ye (International Society for Computational Biology, Uluslararası Hesaplamalı Biyoloji Derneği; Student Council, &Ouml;ğrenci Konseyi) bağlı b&ouml;lgesel &ouml;ğrenci grubuyuz (Regional Student Group, RSG) ve RSG-T&uuml;rkiye olarak 2011 yılında kurulduk. Başlıca aktivitelerimiz d&uuml;zenlediğimiz &ouml;ğrenci sempozyumlarımız ve hem T&uuml;rkiye'den hem de yurtdışında tanınmış bilim insanlarını &uuml;cretsiz olarak T&uuml;rkiye hesaplamalı biyoloji camiası ile buluşturduğumuz webinar'larımızdır.</p>

    <p>Genel haberleşme, etkinlik ve organizasyon duyuruları ile birlikte toplantı g&uuml;nlerimizi paylaştığımız ve aktif bir şekilde kullandığımız Slack kanalımıza sizi bekliyoruz:</p>

    <p style="text-align: center; margin: 30px 0;">
        <a href="{invite_link}"
           style="background-color: #4A154B; color: white; padding: 14px 28px;
                  text-decoration: none; border-radius: 6px; font-size: 16px;
                  font-weight: bold; display: inline-block;">
            Slack Kanalına Katıl / Join Slack
        </a>
    </p>

    <p>Katıldığınızda se&ccedil;tiğiniz komite kanallarına otomatik olarak ekleneceksiniz. Eğer link ile ilgili bir sorun yaşarsanız bu e-postaya geri d&ouml;n&uuml;ş yapabilirsiniz.</p>

    <p style="text-align: center; margin: 20px 0;">
        Bizi sosyal medyadan takip edin:<br><br>
        <a href="https://www.linkedin.com/company/rsgturkey/posts/?feedView=all" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/3536/3536505.png" alt="LinkedIn" width="32" height="32" style="vertical-align: middle;">
        </a>
        <a href="https://www.instagram.com/rsgturkey/" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/2111/2111463.png" alt="Instagram" width="32" height="32" style="vertical-align: middle;">
        </a>
        <a href="https://x.com/RSGTurkey" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/5968/5968830.png" alt="X" width="32" height="32" style="vertical-align: middle;">
        </a>
        <a href="https://www.youtube.com/channel/UCRM_72rELTgtWK_zKlDGxxQ" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/1384/1384060.png" alt="YouTube" width="32" height="32" style="vertical-align: middle;">
        </a>
    </p>

    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">

    <h2>Hello!</h2>

    <p>We are writing to you because you recently filled out the ISCB-SC RSG-T&uuml;rkiye registration form.</p>

    <p>We are a regional student group (RSG) affiliated with ISCB-SC (International Society for Computational Biology, Student Council) and were established in 2011. Our main activities are student symposiums and webinars where we bring well-known scientists from Turkey and abroad to the Turkish computational biology community, free of charge.</p>

    <p>We use Slack for general communication, event announcements, and meeting schedules. We would love to have you join us:</p>

    <p style="text-align: center; margin: 30px 0;">
        <a href="{invite_link}"
           style="background-color: #4A154B; color: white; padding: 14px 28px;
                  text-decoration: none; border-radius: 6px; font-size: 16px;
                  font-weight: bold; display: inline-block;">
            Join Slack Workspace
        </a>
    </p>

    <p>Once you join, you'll be automatically added to your selected committee channels. If you have any issues with the link, feel free to reply to this email.</p>

    <p style="text-align: center; margin: 20px 0;">
        Follow us on social media:<br><br>
        <a href="https://www.linkedin.com/company/rsgturkey/posts/?feedView=all" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/3536/3536505.png" alt="LinkedIn" width="32" height="32" style="vertical-align: middle;">
        </a>
        <a href="https://www.instagram.com/rsgturkey/" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/2111/2111463.png" alt="Instagram" width="32" height="32" style="vertical-align: middle;">
        </a>
        <a href="https://x.com/RSGTurkey" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/5968/5968830.png" alt="X" width="32" height="32" style="vertical-align: middle;">
        </a>
        <a href="https://www.youtube.com/channel/UCRM_72rELTgtWK_zKlDGxxQ" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/1384/1384060.png" alt="YouTube" width="32" height="32" style="vertical-align: middle;">
        </a>
    </p>

    <p>İyi g&uuml;nler diliyoruz! / Have a nice day! 🌟</p>

    <p>ISCB-SC RSG-T&uuml;rkiye Ekibi adına / On behalf of the ISCB-SC RSG-T&uuml;rkiye Team</p>
</body>
</html>"""

    text_body = f"""\
Merhabalar!

Sizlere yakın zamanda ISCB-SC RSG-Türkiye katılım formunu doldurduğunuz için yazıyoruz.

Kısaca grubumuzu tanıtmak istiyoruz ve ayrıca varsa sorularınızı yanıtlamak bizleri mutlu eder.

ISCB-SC'ye (International Society for Computational Biology, Uluslararası Hesaplamalı Biyoloji Derneği; Student Council, Öğrenci Konseyi) bağlı bölgesel öğrenci grubuyuz (Regional Student Group, RSG) ve RSG-Türkiye olarak 2011 yılında kurulduk. Başlıca aktivitelerimiz düzenlediğimiz öğrenci sempozyumlarımız ve hem Türkiye'den hem de yurtdışında tanınmış bilim insanlarını ücretsiz olarak Türkiye hesaplamalı biyoloji camiası ile buluşturduğumuz webinar'larımızdır.

Genel haberleşme, etkinlik ve organizasyon duyuruları ile birlikte toplantı günlerimizi paylaştığımız Slack kanalımıza sizi bekliyoruz:

{invite_link}

Katıldığınızda seçtiğiniz komite kanallarına otomatik olarak ekleneceksiniz. Eğer link ile ilgili bir sorun yaşarsanız bu e-postaya geri dönüş yapabilirsiniz.

Bizi sosyal medyadan takip edin:
LinkedIn: https://www.linkedin.com/company/rsgturkey/posts/?feedView=all
Instagram: https://www.instagram.com/rsgturkey/
X (Twitter): https://x.com/RSGTurkey
YouTube: https://www.youtube.com/channel/UCRM_72rELTgtWK_zKlDGxxQ

---

Hello!

We are writing to you because you recently filled out the ISCB-SC RSG-Türkiye registration form.

We are a regional student group (RSG) affiliated with ISCB-SC and were established in 2011. Our main activities are student symposiums and webinars where we bring well-known scientists from Turkey and abroad to the Turkish computational biology community, free of charge.

We use Slack for general communication, event announcements, and meeting schedules. Please join us:

{invite_link}

Once you join, you'll be automatically added to your selected committee channels. If you have any issues with the link, feel free to reply to this email.

Bizi sosyal medyadan takip edin / Follow us on social media:
LinkedIn: https://www.linkedin.com/company/rsgturkey/posts/?feedView=all
Instagram: https://www.instagram.com/rsgturkey/
X (Twitter): https://x.com/RSGTurkey
YouTube: https://www.youtube.com/channel/UCRM_72rELTgtWK_zKlDGxxQ

Iyi gunler diliyoruz! / Have a nice day!

ISCB-SC RSG-Türkiye Ekibi adına / On behalf of the ISCB-SC RSG-Türkiye Team"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())

        logger.info(f"Welcome email sent to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_outreach_email(to_email: str, subject: str, greeting: str,
                         body: str) -> bool:
    """
    Send a personalized outreach email.
    greeting: full greeting line, e.g. "Sayın Prof. Dr. Tunahan Hocam,"
    body: admin-composed text (plain text with newlines)
    Returns True if sent successfully.
    """
    sender = os.getenv("GMAIL_SENDER_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")

    if not sender or not password:
        logger.error("Gmail credentials not configured")
        return False

    if not to_email:
        logger.error("Missing to_email for outreach")
        return False

    # Convert newlines to <br> for HTML body
    body_html = body.replace("\n", "<br>")

    html_body = f"""\
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <p style="font-size: 16px;"><strong>{greeting}</strong></p>

    <p>{body_html}</p>

    <p style="text-align: center; margin: 20px 0;">
        Bizi sosyal medyadan takip edin / Follow us on social media:<br><br>
        <a href="https://www.linkedin.com/company/rsgturkey/posts/?feedView=all" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/3536/3536505.png" alt="LinkedIn" width="32" height="32" style="vertical-align: middle;">
        </a>
        <a href="https://www.instagram.com/rsgturkey/" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/2111/2111463.png" alt="Instagram" width="32" height="32" style="vertical-align: middle;">
        </a>
        <a href="https://x.com/RSGTurkey" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/5968/5968830.png" alt="X" width="32" height="32" style="vertical-align: middle;">
        </a>
        <a href="https://www.youtube.com/channel/UCRM_72rELTgtWK_zKlDGxxQ" style="text-decoration: none; display: inline-block; margin: 4px;">
            <img src="https://cdn-icons-png.flaticon.com/32/1384/1384060.png" alt="YouTube" width="32" height="32" style="vertical-align: middle;">
        </a>
    </p>

    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
    <p style="color: #666; font-size: 12px;">ISCB-SC RSG-T&uuml;rkiye</p>
</body>
</html>"""

    text_body = f"""{greeting}

{body}

---
Bizi sosyal medyadan takip edin / Follow us on social media:
LinkedIn: https://www.linkedin.com/company/rsgturkey/posts/?feedView=all
Instagram: https://www.instagram.com/rsgturkey/
X (Twitter): https://x.com/RSGTurkey
YouTube: https://www.youtube.com/channel/UCRM_72rELTgtWK_zKlDGxxQ

ISCB-SC RSG-Türkiye"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())

        logger.info(f"Outreach email sent to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send outreach email to {to_email}: {e}")
        return False
