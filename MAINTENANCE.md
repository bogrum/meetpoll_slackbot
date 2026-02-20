# Bakım Kılavuzu

## Slack Invite Link Yenileme (Her Ay)

Slack ücretsiz planda invite link'ler 30 günde expire olur. Aşağıdaki adımları takip et.

### 1. Yeni link al

1. Slack'te sol üstten workspace adına tıkla
2. **Invite people** → **Copy invite link**
3. Linki kopyala

### 2. Sunucuya bağlan

```bash
ssh raspbog@100.69.111.79
```

### 3. .env dosyasını güncelle

```bash
nano /home/raspbog/slackbot/slackbot/.env
```

`SLACK_INVITE_LINK=` satırını bulup yeni linkle değiştir:

```
SLACK_INVITE_LINK=https://join.slack.com/t/...yeni-link...
```

Kaydet: `Ctrl+O` → `Enter` → `Ctrl+X`

### 4. Botu restart et

```bash
sudo restart-bot
```

### 5. Kontrol et

```bash
systemctl status slackbot
```

`active (running)` görünüyorsa tamam.

---

## Diğer Bakım İşlemleri

### Bot'u manuel restart etme

```bash
ssh raspbog@100.69.111.79
sudo restart-bot
```

### Logları izleme

```bash
ssh raspbog@100.69.111.79
journalctl -u slackbot -f
```

### Son 50 log satırı

```bash
journalctl -u slackbot -n 50
```

### Güncelleme deploy etme

Lokal makineden dosyaları kopyala:

```bash
scp bot.py database.py blocks.py sheets.py mailer.py google_groups.py rss_feed.py raspbog@100.69.111.79:/home/raspbog/slackbot/slackbot/
```

Sonra restart:

```bash
ssh raspbog@100.69.111.79
sudo restart-bot
```
