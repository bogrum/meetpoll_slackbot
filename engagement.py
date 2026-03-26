"""
engagement.py — Member re-engagement scoring, candidate selection, and message drafting.
No Slack API calls here — pure data logic.
"""

import random
from datetime import datetime

import database as db

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

EDUCATION_SCORES = {
    "postdoc": 5, "post-doc": 5, "faculty": 5, "öğretim": 5,
    "phd": 4, "doktora": 4, "ph.d": 4,
    "master": 3, "yüksek lisans": 3, "msc": 3, "m.sc": 3,
    "lisans": 1, "undergraduate": 1, "bachelor": 1,
}

COMMITTEE_TR = {
    "Journal Club": "Makale Kulübü",
    "Membership": "Üyelik",
    "Outreach": "Dış İlişkiler",
    "Social Media": "Sosyal Medya",
    "Sponsorship": "Sponsorluk",
    "Symposium": "Sempozyum",
    "Translation": "Çeviri",
    "Webinar": "Webinar",
    "Website": "Website",
    "Graphic Design": "Grafik Tasarım",
}


def _education_score(raw: str) -> int:
    raw = (raw or "").lower()
    best = 1
    for keyword, score in EDUCATION_SCORES.items():
        if keyword in raw:
            best = max(best, score)
    return best


def _normalize_education(raw: str) -> str:
    raw = (raw or "").lower()
    if any(k in raw for k in ("postdoc", "post-doc", "faculty", "öğretim")):
        return "postdoc"
    if any(k in raw for k in ("phd", "doktora", "ph.d")):
        return "phd"
    if any(k in raw for k in ("master", "yüksek lisans", "msc", "m.sc")):
        return "masters"
    if any(k in raw for k in ("mezun", "graduate", "alumni")):
        return "graduate"
    return "undergrad"


def compute_score(member: dict, check_cooldown: bool = True) -> float:
    """Score a member candidate for nudge prioritization (higher = more valuable)."""
    user_id = member.get("user_id") or member.get("slack_user_id", "")

    if check_cooldown:
        if db.is_nudge_dismissed(user_id):
            return -999.0
        if db.was_nudge_sent_recently(user_id, "reengagement", days=30):
            return -10.0

    edu = _education_score(member.get("education_level") or member.get("education") or "")

    choice = (member.get("membership_choice") or "").lower()
    membership = 2 if ("active" in choice or "aktif" in choice) else 1

    committees = [c.strip() for c in (member.get("committees") or "").split(",") if c.strip()]
    committee_score = 1.0 if committees else 0.0
    if len(committees) >= 3:
        committee_score += 0.5

    recency = 0.0
    try:
        created = datetime.fromisoformat(member.get("created_at") or "")
        days_since = (datetime.now() - created).days
        recency = max(0.0, 2.0 - (days_since / 180))
    except Exception:
        pass

    return edu + membership + committee_score + recency


def build_candidates(limit: int = 5) -> list[dict]:
    """Return top-N inactive Slack members ranked by engagement score."""
    inactive = db.get_inactive_users(days=30)

    scored = []
    for user in inactive:
        user_id = user.get("user_id") or user.get("slack_user_id", "")
        full = db.get_member_by_slack_user(user_id)
        if full:
            user.update(full)
        score = compute_score(user)
        if score < 0:
            continue
        user["_score"] = round(score, 2)
        scored.append(user)

    # Add jitter only for tie-breaking in the ranked list
    for m in scored:
        m["_score"] = round(m["_score"] + random.uniform(0, 0.5), 2)
    scored.sort(key=lambda m: m["_score"], reverse=True)
    return scored[:limit]


# ---------------------------------------------------------------------------
# Message drafting
# ---------------------------------------------------------------------------

_EDU_LINES_TR = {
    "graduate": [
        "Mezuniyet sonrasında kazandığın deneyim ve bakış açın topluluğumuz için değerli.",
        "Mezuniyet sonrasında edindiğin birikim topluluğumuza gerçekten katkı sağlayabilir.",
    ],
    "undergrad": [
        "Lisans eğitimini sürdürürken böyle bir topluluğun parçası olmanın değerli deneyimler kazandıracağını düşünüyoruz.",
        "Lisans sürecinde topluluğumuzla birlikte çalışmak hem gelişimine katkı sağlar hem de yeni bağlantılar kurmanı kolaylaştırır.",
    ],
    "masters": [
        "Yüksek lisans çalışmaların sürerken topluluğumuza katkılarının oldukça değerli olacağını düşünüyoruz.",
        "Yüksek lisans sürecindeki bakış açın ve deneyimin topluluğumuz için çok kıymetli.",
    ],
    "phd": [
        "Doktora çalışmalarındaki deneyim ve bakış açının topluluğumuza büyük katkı sağlayacağına inanıyoruz.",
        "Doktora sürecindeki araştırma deneyiminin topluluğumuz için değerli olduğunu düşünüyoruz.",
    ],
    "postdoc": [
        "Akademik deneyimin ve uzmanlığının topluluğumuza çok değerli katkılar sağlayacağını düşünüyoruz.",
        "Alandaki deneyiminle topluluğumuza önemli katkılar sağlayabileceğini düşünüyoruz.",
    ],
}

_EDU_LINES_EN = {
    "graduate": [
        "The experience and perspective you've gained since graduating would be genuinely valuable to our community.",
        "Your background and insights as a graduate would be a great addition to the community.",
    ],
    "undergrad": [
        "We believe being part of our community during your undergraduate studies would be a valuable experience.",
        "Working with us during your undergrad program can open up new connections and learning opportunities.",
    ],
    "masters": [
        "We think your perspective and work during your master's program would be a great addition to our community.",
        "Your experience as a master's student would be genuinely valuable to the community.",
    ],
    "phd": [
        "We believe your research experience and perspective as a PhD student would greatly benefit our community.",
        "Your work and insights from your PhD journey would be a meaningful contribution to the group.",
    ],
    "postdoc": [
        "We believe your academic expertise and experience would be incredibly valuable to our community.",
        "Your depth of experience in the field would be a real asset to the community.",
    ],
}


def draft_nudge_message(member: dict, upcoming_events: list = None) -> str:
    """Generate a warm, personalized bilingual nudge DM."""
    if upcoming_events is None:
        upcoming_events = []

    first_name = (member.get("first_name") or "").strip()
    greeting_tr = f"Merhaba{' ' + first_name if first_name else ''},"
    greeting_en = f"Hi{' ' + first_name if first_name else ''},"

    edu_level = _normalize_education(member.get("education_level") or member.get("education") or "")
    edu_tr = random.choice(_EDU_LINES_TR.get(edu_level, _EDU_LINES_TR["undergrad"]))
    edu_en = random.choice(_EDU_LINES_EN.get(edu_level, _EDU_LINES_EN["undergrad"]))

    # Committee info
    committees = [c.strip() for c in (member.get("committees") or "").split(",") if c.strip()]
    primary = committees[0] if committees else None
    primary_tr = COMMITTEE_TR.get(primary, primary) if primary else None

    if committees:
        # Build per-committee lines with leader mentions
        committee_lines_tr = []
        committee_lines_en = []
        for c in committees:
            c_tr = COMMITTEE_TR.get(c, c)
            leader_id = db.get_committee_leader(c)
            leader = f"<@{leader_id}>" if leader_id else None
            if leader:
                committee_lines_tr.append(
                    f"• {c_tr} — komite liderimiz {leader} yakında seninle iletişime geçecektir, "
                    f"dilersen sen de doğrudan ona yazabilirsin."
                )
                committee_lines_en.append(
                    f"• {c} — our committee lead {leader} will be in touch with you soon; "
                    f"feel free to reach out to them directly as well."
                )
            else:
                committee_lines_tr.append(f"• {c_tr}")
                committee_lines_en.append(f"• {c}")

        committees_list_tr = "\n".join(committee_lines_tr)
        committees_list_en = "\n".join(committee_lines_en)

        multi_note_tr = (
            "\nGenellikle tek bir komiteye odaklanmanın daha verimli olduğunu görüyoruz. "
            "Başlamakta zorlanırsan bir komiteye odaklanmanı öneririz."
        ) if len(committees) > 1 else ""
        multi_note_en = (
            "\nWe generally find it more effective to focus on one committee at a time. "
            "If you find it overwhelming, we'd suggest starting with just one."
        ) if len(committees) > 1 else ""

        committee_tr = (
            f"İlgi duyduğun komiteleri gördük; seni aramızda görmekten memnuniyet duyarız.\n"
            f"{committees_list_tr}{multi_note_tr}"
        )
        committee_en = (
            f"We noticed the committees you're interested in and would love to have you on board.\n"
            f"{committees_list_en}{multi_note_en}"
        )
    else:
        committee_tr = "Topluluğumuzdaki çalışmalara katılmana seviniriz."
        committee_en = "We would be glad to have you join the work happening in our community."

    # Event mention
    event_tr = ""
    event_en = ""
    if upcoming_events:
        ev = upcoming_events[0]
        title = ev.get("title", "")
        dt = (ev.get("event_datetime") or ev.get("start_datetime") or "")[:10]
        event_tr = f"Ayrıca yaklaşan etkinliğimiz '{title}' ({dt}) ilgini çekebilir."
        event_en = f"You might also be interested in our upcoming event '{title}' ({dt})."

    # Admin contact line — dynamic from DB
    admin_ids = db.get_all_onboard_admins()
    if admin_ids:
        mentions = " veya ".join(f"<@{uid}>" for uid in admin_ids[:2])
        contact_tr = f"Herhangi bir sorunuz veya fikriniz için {mentions} ile iletişime geçebilirsiniz."
        mentions_en = " or ".join(f"<@{uid}>" for uid in admin_ids[:2])
        contact_en = f"For any questions or ideas, feel free to reach out to {mentions_en}."
    else:
        contact_tr = "Herhangi bir sorunuz için bu mesajı iletebilirsiniz."
        contact_en = "For any questions, please forward this message."

    intro_tr = "RSG-Türkiye Slack topluluğuna katıldığını gördük ancak henüz aramızda seni göremedik, bu yüzden merhaba demek istedik."
    intro_en = "We noticed you joined the RSG-Türkiye Slack community but haven't seen you around yet, so we wanted to say hello."

    # Build Turkish block
    parts_tr = [greeting_tr, "", intro_tr, "", edu_tr, "", committee_tr]
    if event_tr:
        parts_tr.append("")
        parts_tr.append(event_tr)
    parts_tr += ["", contact_tr]

    # Build English block
    parts_en = [greeting_en, "", intro_en, "", edu_en, "", committee_en]
    if event_en:
        parts_en.append("")
        parts_en.append(event_en)
    parts_en += ["", contact_en, "", "RSG-Türkiye"]

    return "\n".join(parts_tr) + "\n\n\n" + "\n".join(parts_en)
