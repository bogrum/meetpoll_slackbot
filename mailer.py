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
    calendar_link = os.getenv("CALENDAR_LINK", "")

    subject = "RSG-Türkiye'ye Hoş Geldiniz! / Welcome to RSG-Türkiye!"

    # Calendar section (only if link is configured)
    calendar_html_tr = ""
    calendar_html_en = ""
    calendar_text_tr = ""
    calendar_text_en = ""
    if calendar_link:
        calendar_html_tr = f"""
    <p>Dilerseniz etkinlik takvimimizi kendi takviminize de buradan entegre edebilirsiniz:</p>
    <p style="text-align: center; margin: 20px 0;">
        <a href="{calendar_link}"
           style="background-color: #0B8043; color: white; padding: 10px 22px;
                  text-decoration: none; border-radius: 6px; font-size: 14px;
                  font-weight: bold; display: inline-block;">
            &#128197; RSG-T&uuml;rkiye Etkinlik Takvimi
        </a>
    </p>"""
        calendar_html_en = f"""
    <p>You can also integrate our event calendar into your own calendar:</p>
    <p style="text-align: center; margin: 20px 0;">
        <a href="{calendar_link}"
           style="background-color: #0B8043; color: white; padding: 10px 22px;
                  text-decoration: none; border-radius: 6px; font-size: 14px;
                  font-weight: bold; display: inline-block;">
            &#128197; RSG-T&uuml;rkiye Event Calendar
        </a>
    </p>"""
        calendar_text_tr = f"\nEtkinlik takvimimizi kendi takviminize entegre edebilirsiniz:\n{calendar_link}\n"
        calendar_text_en = f"\nIntegrate our event calendar into yours:\n{calendar_link}\n"

    html_body = f"""\
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2>Merhabalar! &#10024;</h2>

    <p>ISCB-SC RSG-T&uuml;rkiye'ye g&ouml;sterdiğin ilgi i&ccedil;in teşekk&uuml;r ederiz. Hesaplamalı biyoloji alanında T&uuml;rkiye'deki en k&ouml;kl&uuml; &ouml;ğrenci topluluklarından biri olarak, seni de aramızda g&ouml;rmekten mutluluk duyuyoruz!</p>

    <p>RSG-T&uuml;rkiye, International Society for Computational Biology (ISCB) Student Council'e bağlı, &ouml;ğrenci ve erken kariyer araştırmacılarını bir araya getiren g&ouml;n&uuml;ll&uuml; bir platformdur. Amacımız, bu alandaki bilgi birikimini paylaşmak ve camiamızı g&uuml;&ccedil;lendirmektir. &#129309;</p>

    <h3>RSG-T&uuml;rkiye'de seni neler bekliyor? &#128640;</h3>

    <p>Biz, 2011 yılından beri hiyerarşiden uzak, tamamen g&ouml;n&uuml;ll&uuml;l&uuml;k esasıyla &uuml;reten ve birbirini destekleyen bir &ouml;ğrenci topluluğuyuz. Burada sadece etkinlik izlemez, aynı zamanda:</p>

    <ul>
        <li>&Ouml;ğrenci Sempozyumları ve Webinar'larda yer alabilir,</li>
        <li>&Ouml;ğrenci Sunumları ile akademik becerilerini geliştirebilir,</li>
        <li>T&uuml;rkiye ve d&uuml;nyadan bilim insanlarıyla tanışma fırsatı yakalayabilir,</li>
        <li>Biyoenformatik d&uuml;nyasındaki g&uuml;ncel ilanlardan (MSc/PhD/PostDoc) anında haberdar olabilirsin.</li>
    </ul>

    <h3>İletişim ve Takip &#128241;</h3>

    <p>Genel iletişim, etkinlik duyuruları ve toplantı bilgilerimizi paylaştığımız Slack kanalımıza seni de bekliyoruz. Katıldığında, formda se&ccedil;miş olduğun komite kanallarına otomatik olarak ekleneceksin.</p>

    <p style="text-align: center; margin: 30px 0;">
        <a href="{invite_link}"
           style="background-color: #4A154B; color: white; padding: 14px 28px;
                  text-decoration: none; border-radius: 6px; font-size: 16px;
                  font-weight: bold; display: inline-block;">
            &#128172; Slack Kanalına Katıl / Join Slack
        </a>
    </p>
{calendar_html_tr}
    <p>Bizi sosyal medya &uuml;zerinden takip ederek g&uuml;ncel ilan ve duyurulardan haberdar olabilirsin:</p>

    <p style="text-align: center; margin: 20px 0;">
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

    <p>Herhangi bir sorunuz olursa l&uuml;tfen &ccedil;ekinmeden bizimle iletişime ge&ccedil;in. Sizlerle birlikte &ccedil;alışmak ve daha g&uuml;zel etkinlikler &uuml;retmek i&ccedil;in &ccedil;ok heyecanlıyız! &#127775;</p>

    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">

    <h2>Hello! &#10024;</h2>

    <p>Thank you for your interest in ISCB-SC RSG-T&uuml;rkiye. As one of the most established student communities in computational biology in Turkey, we are delighted to have you among us!</p>

    <p>RSG-T&uuml;rkiye is a volunteer platform affiliated with the International Society for Computational Biology (ISCB) Student Council, bringing together students and early-career researchers. Our goal is to share knowledge in this field and strengthen our community. &#129309;</p>

    <h3>What awaits you at RSG-T&uuml;rkiye? &#128640;</h3>

    <p>Since 2011, we have been a non-hierarchical student community built entirely on volunteerism, creating and supporting one another. Here, you don't just attend events &mdash; you can also:</p>

    <ul>
        <li>Participate in Student Symposiums and Webinars,</li>
        <li>Develop your academic skills through Student Presentations,</li>
        <li>Meet scientists from Turkey and around the world,</li>
        <li>Stay instantly informed about current positions (MSc/PhD/PostDoc) in bioinformatics.</li>
    </ul>

    <h3>Communication &amp; Updates &#128241;</h3>

    <p>We use Slack for general communication, event announcements, and meeting schedules. Once you join, you'll be automatically added to the committee channels you selected in the registration form.</p>

    <p style="text-align: center; margin: 30px 0;">
        <a href="{invite_link}"
           style="background-color: #4A154B; color: white; padding: 14px 28px;
                  text-decoration: none; border-radius: 6px; font-size: 16px;
                  font-weight: bold; display: inline-block;">
            &#128172; Join Slack Workspace
        </a>
    </p>
{calendar_html_en}
    <p>Follow us on social media to stay up to date with announcements and opportunities:</p>

    <p style="text-align: center; margin: 20px 0;">
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

    <p>If you have any questions, please don't hesitate to reach out. We are very excited to work with you and create great events together! &#127775;</p>

    <p>İyi &ccedil;alışmalar dileriz. / Best regards.</p>

    <p>ISCB-SC RSG-T&uuml;rkiye Ekibi adına / On behalf of the ISCB-SC RSG-T&uuml;rkiye Team</p>
</body>
</html>"""

    text_body = f"""\
Merhabalar!

ISCB-SC RSG-Türkiye'ye gösterdiğin ilgi için teşekkür ederiz. Hesaplamalı biyoloji alanında Türkiye'deki en köklü öğrenci topluluklarından biri olarak, seni de aramızda görmekten mutluluk duyuyoruz!

RSG-Türkiye, International Society for Computational Biology (ISCB) Student Council'e bağlı, öğrenci ve erken kariyer araştırmacılarını bir araya getiren gönüllü bir platformdur. Amacımız, bu alandaki bilgi birikimini paylaşmak ve camiamızı güçlendirmektir.

RSG-Türkiye'de seni neler bekliyor?

Biz, 2011 yılından beri hiyerarşiden uzak, tamamen gönüllülük esasıyla üreten ve birbirini destekleyen bir öğrenci topluluğuyuz. Burada sadece etkinlik izlemez, aynı zamanda:

- Öğrenci Sempozyumları ve Webinar'larda yer alabilir,
- Öğrenci Sunumları ile akademik becerilerini geliştirebilir,
- Türkiye ve dünyadan bilim insanlarıyla tanışma fırsatı yakalayabilir,
- Biyoenformatik dünyasındaki güncel ilanlardan (MSc/PhD/PostDoc) anında haberdar olabilirsin.

İletişim ve Takip

Genel iletişim, etkinlik duyuruları ve toplantı bilgilerimizi paylaştığımız Slack kanalımıza seni de bekliyoruz. Katıldığında, formda seçmiş olduğun komite kanallarına otomatik olarak ekleneceksin.

Slack Kanalına Katıl: {invite_link}
{calendar_text_tr}
Bizi sosyal medyadan takip edin:
LinkedIn: https://www.linkedin.com/company/rsgturkey/posts/?feedView=all
Instagram: https://www.instagram.com/rsgturkey/
X (Twitter): https://x.com/RSGTurkey
YouTube: https://www.youtube.com/channel/UCRM_72rELTgtWK_zKlDGxxQ

Herhangi bir sorunuz olursa lütfen çekinmeden bizimle iletişime geçin. Sizlerle birlikte çalışmak ve daha güzel etkinlikler üretmek için çok heyecanlıyız!

---

Hello!

Thank you for your interest in ISCB-SC RSG-Türkiye. As one of the most established student communities in computational biology in Turkey, we are delighted to have you among us!

RSG-Türkiye is a volunteer platform affiliated with the International Society for Computational Biology (ISCB) Student Council, bringing together students and early-career researchers. Our goal is to share knowledge in this field and strengthen our community.

What awaits you at RSG-Türkiye?

Since 2011, we have been a non-hierarchical student community built entirely on volunteerism, creating and supporting one another. Here, you don't just attend events — you can also:

- Participate in Student Symposiums and Webinars,
- Develop your academic skills through Student Presentations,
- Meet scientists from Turkey and around the world,
- Stay instantly informed about current positions (MSc/PhD/PostDoc) in bioinformatics.

Communication & Updates

We use Slack for general communication, event announcements, and meeting schedules. Once you join, you'll be automatically added to the committee channels you selected in the registration form.

Join Slack: {invite_link}
{calendar_text_en}
Follow us on social media:
LinkedIn: https://www.linkedin.com/company/rsgturkey/posts/?feedView=all
Instagram: https://www.instagram.com/rsgturkey/
X (Twitter): https://x.com/RSGTurkey
YouTube: https://www.youtube.com/channel/UCRM_72rELTgtWK_zKlDGxxQ

If you have any questions, please don't hesitate to reach out. We are very excited to work with you and create great events together!

Best regards,

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
