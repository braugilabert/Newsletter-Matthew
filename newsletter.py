"""Matt's Newsletter: weekly TXT quizzes, RSS news, SMTP and a static archive.

Adapted from the original RSS / editable TXT / SMTP / docs newsletter.
Default mode only previews. Sending always requires --send.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import html
import json
import logging
import os
import re
import smtplib
import ssl
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
NAME = "Matt's Newsletter"
NEWS_TITLE = "España: cinco noticias de la semana"
SECTIONS = (
    ("neuropsychology", "Neuropsychology case files", "Symptoms, brain regions and the most likely syndrome."),
    ("mental_health", "Mental health case files", "Fictional diagnostic cases: DSM-5-TR and ICD-11."),
    ("neuroscience", "Neuroscience", "Neurotransmitters, circuits and how the brain works."),
    ("psychotherapy", "Psychotherapy toolkit", "Methods, origins and the language of therapy."),
    ("irish", "A little Gaeilge", "Towards B1: messages, meaning and grammar in context."),
    ("music", "Music theory, finally", "A few minutes of practice count. Start here."),
)
FIELDS = {"ID", "TITLE", "QUESTION", "A", "B", "C", "D", "ANSWER", "EXPLANATION", "EXAMPLE", "SOURCE"}
LOG = logging.getLogger(__name__)


def read_json(path, default):
    # Damaged history must stop a send rather than silently repeat an edition.
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def safe_url(value):
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError(f"Invalid public HTTP(S) URL: {value!r}")
    return value.strip()


def load_bank(path):
    records = []
    for block in re.split(r"(?m)^---\s*$", path.read_text(encoding="utf-8-sig")):
        record = {}
        for line in block.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, sep, value = line.partition(":")
            if not sep or key not in FIELDS or key in record:
                raise ValueError(f"{path.name}: invalid or repeated field {line!r}")
            record[key] = value.strip()
        if not record:
            continue
        missing = FIELDS - record.keys()
        if missing or any(not v for v in record.values()):
            raise ValueError(f"{path.name}: missing or empty fields in {record.get('ID')}: {missing}")
        if record["ANSWER"] not in {"A", "B", "C", "D"}:
            raise ValueError(f"{path.name}: ANSWER must be A, B, C or D")
        if len({record[option].casefold() for option in "ABCD"}) != 4:
            raise ValueError(f"{path.name}: options must be distinct in {record['ID']}")
        safe_url(record["SOURCE"])
        records.append(record)
    ids = [r["ID"] for r in records]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError(f"{path.name}: empty bank or duplicate IDs")
    return records


def load_banks():
    banks = {key: load_bank(ROOT / "content" / f"{key}.txt") for key, *_ in SECTIONS}
    ids = [q["ID"] for bank in banks.values() for q in bank]
    if len(ids) != len(set(ids)):
        raise ValueError("Question IDs must be unique across all banks")
    return banks


def select_questions(banks, history, count):
    used, selected = history.get("questions", {}), {}
    for key, bank in banks.items():
        if not 1 <= count <= len(bank):
            raise ValueError(f"Requested {count} questions but {key} has {len(bank)}")
        selected[key] = sorted(bank, key=lambda q: used.get(q["ID"], ""))[:count]
    return selected


def edition_id(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def plain_text(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value))).strip()


def normal_title(value):
    plain = ''.join(c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9]+", plain)) - {
        "the", "and", "for", "with", "from", "that", "this", "says", "after", "over", "into", "are",
        "el", "la", "los", "las", "un", "una", "de", "del", "en", "y", "a", "por", "para", "con", "que", "se", "al", "su"}


def story_key(item):
    p = urlsplit(safe_url(item["url"]))
    url = urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))
    return hashlib.sha256(url.encode()).hexdigest()


def news_config():
    config = read_json(ROOT / "config" / "news_sources.json", None)
    if not config or not 1 <= int(config["days_back"]) <= 14 or not 1 <= config["max_stories"] <= 10:
        raise ValueError("Invalid news configuration")
    if not config["sources"]:
        raise ValueError("At least one RSS source is required")
    for source in config["sources"]:
        safe_url(source["url"])
    return config


def fetch_feed(source, now, days):
    request = urllib.request.Request(source["url"], headers={"User-Agent": "MattsNewsletter/1.0 RSS reader"})
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read(2_000_001)
    # Embedded article HTML can contain a harmless doctype inside a CDATA value.
    # Actual XML DTD/entity declarations outside CDATA remain unsupported.
    declaration_text = re.sub(br"<!\[CDATA\[.*?\]\]>", b"", body, flags=re.S).upper()
    if len(body) > 2_000_000 or b"<!DOCTYPE" in declaration_text or b"<!ENTITY" in declaration_text:
        raise ValueError("Unsupported or oversized RSS XML")
    root = ET.fromstring(body)
    entries = root.findall(".//item") + root.findall("{http://www.w3.org/2005/Atom}entry")
    items = []
    for entry in entries:
        def text_of(*names):
            for name in names:
                found = entry.find(name)
                if found is not None and found.text:
                    return found.text
            return ""
        title = plain_text(text_of("title", "{http://www.w3.org/2005/Atom}title"))
        link = text_of("link")
        if not link:
            atom = entry.find("{http://www.w3.org/2005/Atom}link[@rel='alternate']")
            if atom is None:
                atom = entry.find("{http://www.w3.org/2005/Atom}link")
            link = atom.get("href", "") if atom is not None else ""
        raw_date = text_of("pubDate", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated")
        try:
            try:
                published = parsedate_to_datetime(raw_date)
            except (ValueError, TypeError):
                published = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            if published.tzinfo is None or not now - timedelta(days=days) <= published <= now:
                continue
            safe_url(link)
        except (ValueError, TypeError):
            continue
        if title:
            if source.get("include_url") and not re.search(source["include_url"], link):
                continue
            if source.get("exclude_url") and re.search(source["exclude_url"], link):
                continue
            items.append({"title": title, "url": link, "source": source["name"],
                          "published": published.isoformat(), "kind": source.get("kind", "Información")})
    return items


def rank_news(items, config, history, now):
    """Prioritise cross-source coverage, then public-interest topics and recency."""
    previous, seen, groups = history.get("news", {}), set(), []
    for item in items:
        published = datetime.fromisoformat(item["published"])
        if published.tzinfo is None or not now - timedelta(days=config["days_back"]) <= published <= now:
            continue
        key = story_key(item)
        if key in seen or key in previous:
            continue
        seen.add(key)
        tokens = normal_title(item["title"])
        for group in groups:
            other = normal_title(group[0]["title"])
            if tokens and len(tokens & other) / max(1, len(tokens | other)) >= .52:
                group.append(item)
                break
        else:
            groups.append([item])
    ranked = []
    for group in groups:
        item = max(group, key=lambda n: n["published"]).copy()
        title = item["title"].lower()
        priority = sum(weight for phrase, weight in config["priority_terms"].items()
                       if re.search(r"\b" + re.escape(phrase) + r"\w*\b", title))
        coverage = len({n["source"] for n in group})
        if config.get("require_priority_match", False) and not priority:
            continue
        item["coverage"] = coverage
        item["score"] = priority + config.get("coverage_weight", 3) * coverage
        ranked.append(item)
    result, outlets = [], Counter()
    ranked.sort(key=lambda n: (n["score"], n["published"]), reverse=True)
    for item in ranked:
        if outlets[item["source"]] < 2:
            result.append(item)
            outlets[item["source"]] += 1
        if len(result) >= config["max_stories"]:
            break
    if config.get("relax_source_limit", False) and len(result) < config["max_stories"]:
        selected_keys = {story_key(item) for item in result}
        for item in ranked:
            if story_key(item) not in selected_keys:
                result.append(item)
                selected_keys.add(story_key(item))
            if len(result) >= config["max_stories"]:
                break
        result.sort(key=lambda n: (n["score"], n["published"]), reverse=True)
    return result


def collect_news(now, history, offline=False, fixture=None):
    config = news_config()
    if fixture:
        return rank_news(read_json(fixture, []), config, history, now), "Previsualización con una muestra fechada de noticias enlazadas a sus fuentes; no es una consulta en directo."
    if offline:
        return [], "Previsualización sin conexión: las noticias de España se consultarán al generar la edición semanal."
    def fetch(source):
        try:
            return fetch_feed(source, now, config["days_back"]), None
        except Exception as exc:
            LOG.warning("RSS unavailable (%s): %s", source["name"], exc)
            return [], source["name"]
    items, failures = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for batch, failed in pool.map(fetch, config["sources"]):
            items.extend(batch)
            if failed:
                failures.append(failed)
    note = ""
    if len(failures) == len(config["sources"]):
        note = "No se han podido consultar las noticias de España esta semana. No se han sustituido por titulares antiguos."
    elif failures:
        note = "Algunas fuentes no estaban disponibles. La selección se basa en los medios que se han podido consultar."
    stories = rank_news(items, config, history, now)
    if not stories and not note:
        note = "No se han encontrado noticias nuevas con fecha verificable de los últimos siete días."
    elif 0 < len(stories) < config["max_stories"]:
        note += (" " if note else "") + f"Se han verificado {len(stories)} noticias nuevas; no se añaden titulares sin verificar para completar cinco."
    return stories, note


def esc(value):
    return html.escape(str(value), quote=True)


def english_date(day):
    return f"{day.day} {calendar.month_name[day.month]} {day.year}"


def spanish_date(day):
    months = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
    return f"{day.day} de {months[day.month]} de {day.year}"


def link(url, label):
    return f'<a href="{esc(url)}" style="color:#000000;text-decoration:underline">{esc(label)}</a>'


def panel(number, title, subtitle, body, language="en"):
    return (f'<tr><td lang="{esc(language)}" style="padding:0 24px 28px"><table role="presentation" width="100%" '
            'cellpadding="0" cellspacing="0" style="border:2px solid #000000;border-collapse:collapse">'
            '<tr><td style="padding:18px;background:#000000;color:#ffffff">'
            f'<div style="font:12px Arial,sans-serif;letter-spacing:2px">{esc(number)}</div>'
            f'<h2 style="font:700 26px Georgia,serif;margin:8px 0">{esc(title)}</h2>'
            f'<p style="font:14px/1.5 Arial,sans-serif;margin:0">{esc(subtitle)}</p></td></tr>'
            f'<tr><td style="padding:20px;background:#ffffff;color:#000000">{body}</td></tr></table></td></tr>')


def page(title, body):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">'
            f'<title>{esc(title)}</title><style>body{{margin:0}}a{{color:#000000}}'
            '@media(max-width:600px){.shell{width:100%!important}.masthead{font-size:40px!important}}'
            '</style></head><body style="margin:0;background:#ffffff;color:#000000;'
            'font:16px/1.65 Arial,sans-serif"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            '<tr><td align="center"><table role="presentation" class="shell" width="680" cellpadding="0" '
            f'cellspacing="0" style="width:100%;max-width:680px;background:#ffffff">{body}'
            '</table></td></tr></table></body></html>')


def render_email(day, selected, stories, news_note, web_url="", archive_url="", demo=False):
    eid, total = edition_id(day), sum(len(selected[k]) for k, *_ in SECTIONS)
    news_number = f"{len(SECTIONS) + 1:02d}"
    overview = ' &nbsp; '.join(f'{i:02d} {esc(title)}' for i, (_, title, _) in enumerate(SECTIONS, 1))
    overview += f' &nbsp; <span lang="es">{news_number} {NEWS_TITLE}</span>'
    banner = ('<p style="border:2px solid #000000;padding:12px;font-size:13px">'
              'PREVIEW / DEMO — sample edition, never sent. Archive dates demonstrate the design.</p>') if demo else ""
    nav = " · ".join(link(url, label) for url, label in [(web_url, "Read online"), (archive_url, "Past editions")] if url)
    rows = [f'<tr><td style="padding:28px 24px 20px">{banner}<p style="font:12px Arial,sans-serif;'
            f'letter-spacing:2px">THE WEEKLY CURIOSITY EDIT · {esc(eid)}</p>'
            f'<h1 class="masthead" style="font:700 54px/1.04 Georgia,serif;letter-spacing:-2px;'
            f'margin:24px 0">{esc(NAME)}</h1><p style="border-top:4px solid #000000;'
            f'border-bottom:1px solid #000000;padding:12px 0;font-size:13px">{english_date(day)}'
            f' · {total} questions · one good week of learning</p><p>{nav}</p>'
            '<p>Hi Matt,</p><p>A few brain teasers, a little Gaeilge and a reason to pick up your instrument. '
            'Try the questions first; the answer key and worked examples are at the end. After you finish all, have a beer. '
            'Or two, my friend.</p>'
            f'<p style="font-size:13px">{overview}</p></td></tr>']
    answers, answer_sections = [], []
    text = [f"{NAME} | {eid} | {english_date(day)}", "Try the questions before the answer key."]
    if demo:
        text.insert(0, "PREVIEW / DEMO — sample edition, never sent.")
    for number, (key, title, subtitle) in enumerate(SECTIONS, 1):
        body, key_body = [], []
        text.append(f"\n{number:02d}. {title}\n{subtitle}")
        for index, q in enumerate(selected[key], 1):
            label, correct = f"{number}.{index}", q["ANSWER"]
            body.append('<div style="padding:10px 0 22px;border-bottom:1px solid #000000">'
                        f'<p style="font:12px Arial,sans-serif;letter-spacing:1px">QUESTION {label}</p>'
                        f'<h3 style="font:700 21px/1.3 Georgia,serif;margin:10px 0">{esc(q["TITLE"])}</h3>'
                        f'<p>{esc(q["QUESTION"])}</p>')
            text.append(f'{label}. {q["TITLE"]}\n{q["QUESTION"]}')
            for option in "ABCD":
                body.append(f'<p style="margin:6px 0"><strong>{option}.</strong> {esc(q[option])}</p>')
                text.append(f'{option}. {q[option]}')
            body.append('</div>')
            key_body.append('<div style="padding:8px 0 18px;border-bottom:1px solid #000000">'
                            f'<p><strong>{label} · {esc(q["TITLE"])}</strong></p>'
                            f'<p>{esc(q["QUESTION"])}</p>'
                            f'<p><strong>Answer: {correct}. {esc(q[correct])}</strong></p>'
                            f'<p>{esc(q["EXPLANATION"])}</p><p><strong>Worked example / practice:</strong> '
                            f'{esc(q["EXAMPLE"])}</p></div>')
            answers.append((label, q))
        rows.append(panel(f"{number:02d}", title, subtitle, "".join(body)))
        answer_sections.append(panel(f"KEY {number:02d}", title, "Answers, explanations and one more small step.", ''.join(key_body)))
    news_body = ('<p style="font-size:13px">Cinco asuntos de actualidad nacional, seleccionados por su cobertura en distintos medios, '
                 'interés público y fecha de publicación. Titulares originales, medio y enlace; la selección automática no es exhaustiva.</p>')
    text.append(f"\n{news_number}. {NEWS_TITLE}")
    if news_note:
        news_body += f'<p style="border:1px solid #000000;padding:12px">{esc(news_note)}</p>'
        text.append(news_note)
    for story in stories:
        published = datetime.fromisoformat(story["published"]).astimezone(ZoneInfo("Europe/Madrid")).date()
        news_body += ('<div style="padding:10px 0;border-bottom:1px solid #000000">'
                      f'<p style="font:12px Arial,sans-serif">{esc(story["source"])} · {spanish_date(published)}'
                      f' · {esc(story.get("kind", "Información"))}</p><h3 style="font:700 21px/1.3 Georgia,serif">'
                      f'{link(story["url"], story["title"])}</h3></div>')
        text.append(f'{story["title"]}\n{story["source"]} | {spanish_date(published)}\n{story["url"]}')
    rows.append(panel(news_number, NEWS_TITLE, "Actualidad de España de los últimos siete días, en español.", news_body, language="es"))
    rows.append('<tr><td style="padding:12px 24px 28px"><p style="border:2px solid #000000;padding:18px">'
                f'<strong>Pencils down?</strong> Your score: ____ / {total}. Read on for the answers, explanations and practice ideas.</p></td></tr>')
    rows.extend(answer_sections)
    text.append("\nANSWER KEY AND WORKED EXAMPLES")
    for label, q in answers:
        text.append(f'{label}. {q["TITLE"]}\n{q["QUESTION"]}\n'
                    f'Answer: {q["ANSWER"]}. {q[q["ANSWER"]]}\n{q["EXPLANATION"]}\n'
                    f'Worked example / practice: {q["EXAMPLE"]}')
    footer = ('Clinical vignettes are fictional educational examples. Brain functions involve networks; '
              'a likely quiz answer is not a clinical assessment. Irish follows broadly standard usage; dialect forms may differ.')
    rows.append('<tr><td style="padding:12px 24px 40px;border-top:4px solid #000000;font-size:12px">'
                f'<p>{footer}</p><p>{esc(NAME)} · Once a week · Made for Matthew by Carta Clara</p>'
                '<p>To stop receiving this newsletter, reply to the sender and ask to be removed.</p></td></tr>')
    text += [footer, "To stop receiving this newsletter, reply to the sender and ask to be removed."]
    if web_url:
        text.append(f"Read online: {web_url}")
    if archive_url:
        text.append(f"Past editions: {archive_url}")
    return page(f"{NAME} · {eid}", "".join(rows)), "\n\n".join(text)


def archive_page(entries, demo=False):
    body = (f'<tr><td style="padding:32px 24px"><p style="font-size:12px;letter-spacing:2px">THE READING ROOM</p>'
            f'<h1 style="font:700 46px Georgia,serif">{esc(NAME)}</h1>'
            '<h2 style="font:28px Georgia,serif">Past editions</h2>'
            '<p>Brain teasers, Gaeilge and music. A fresh edition every week.</p>')
    if demo:
        body += '<p style="border:2px solid #000000;padding:14px">DEMO ARCHIVE — these sample editions have never been sent.</p>'
    if not entries:
        body += '<p>The first edition is on its way. Published editions will appear here.</p>'
    for entry in sorted(entries, key=lambda e: e["date"], reverse=True):
        body += ('<article style="border-top:2px solid #000000;padding:18px 0"><p style="font-size:12px">'
                 f'{esc(entry["id"])} · {english_date(date.fromisoformat(entry["date"]))}'
                 f'{" · DEMO" if entry.get("demo") else ""}</p><h3 style="font:700 25px Georgia,serif">'
                 f'{link(entry["file"], entry["title"])}</h3><p>{entry["questions"]} questions · '
                 f'{entry.get("subjects", 5)} subjects · {esc(entry.get("news_title", "Ireland’s News"))}</p></article>')
    return page(f"Past editions · {NAME}", body + '</td></tr>')


def publish(folder, day, selected, rendered, demo=False):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "editions").mkdir(exist_ok=True)
    eid = edition_id(day)
    path = folder / "editions" / f"{eid}.html"
    path.write_text(rendered[0], encoding="utf-8")
    path.with_suffix(".txt").write_text(rendered[1], encoding="utf-8")
    entries = [e for e in read_json(folder / "editions.json", []) if e["id"] != eid]
    entries.append({"id": eid, "date": day.isoformat(), "title": selected["neuropsychology"][0]["TITLE"],
                    "questions": sum(len(selected[k]) for k, *_ in SECTIONS),
                    "subjects": len(SECTIONS),
                    "news_title": NEWS_TITLE,
                    "file": f"editions/{eid}.html", "demo": demo})
    write_json(folder / "editions.json", entries)
    (folder / "index.html").write_text(archive_page(entries, demo), encoding="utf-8")
    (folder / ".nojekyll").touch()


def record_usage(history, selected, stories, day):
    for key, *_ in SECTIONS:
        for q in selected[key]:
            history.setdefault("questions", {})[q["ID"]] = day.isoformat()
    for story in stories:
        history.setdefault("news", {})[story_key(story)] = day.isoformat()


def send_email(subject, rendered, eid):
    sender = os.environ["EMAIL_REMITENTE"].strip()
    recipients = [v.strip() for v in os.environ["EMAIL_DESTINATARIOS"].split(",") if v.strip()]
    if not sender or not recipients or any("\n" in v or "\r" in v for v in [sender] + recipients):
        raise ValueError("A sender and at least one valid recipient are required")
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, sender, sender
    message["Reply-To"] = sender
    message["Message-ID"] = f"<matt-{eid}@{sender.split('@')[-1]}>"
    message.set_content(rendered[1])
    message.add_alternative(rendered[0], subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30, context=ssl.create_default_context()) as smtp:
        smtp.login(sender, os.environ["EMAIL_PASSWORD"])
        if smtp.send_message(message, from_addr=sender, to_addrs=recipients):
            raise RuntimeError("Some recipients were refused; inspect delivery before retrying")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="Preview without sending (default)")
    mode.add_argument("--demo", action="store_true", help="Generate four labelled demo archive entries")
    mode.add_argument("--send", action="store_true", help="Send and publish this week's edition")
    mode.add_argument("--check", action="store_true", help="Validate all content and configuration")
    parser.add_argument("--offline", action="store_true", help="Preview without network access")
    parser.add_argument("--news-fixture", type=Path, help="Preview using a labelled dated news snapshot")
    parser.add_argument("--date", type=date.fromisoformat, help="Override preview date only")
    parser.add_argument("--questions", type=int, default=3, help="Questions per subject (default: 3)")
    args = parser.parse_args(argv)
    if args.questions < 1:
        parser.error("--questions must be positive")
    if args.send and (args.date or args.offline or args.news_fixture):
        parser.error("Sending requires the current date and live news")
    if args.send and os.getenv("MODO_PRUEBA") == "1":
        parser.error("MODO_PRUEBA=1 forbids sending")
    banks = load_banks()
    news_config()
    if args.check:
        for key, bank in banks.items():
            print(f"{key}: {len(bank)} exercises OK")
        return 0
    now = datetime.now(ZoneInfo("Europe/Dublin"))
    if args.date:
        now = datetime.combine(args.date, datetime.max.time(), tzinfo=ZoneInfo("Europe/Dublin"))
    day, eid = now.date(), edition_id(now.date())
    history_path = ROOT / "state" / "history.json"
    history = read_json(history_path, {}) if not args.demo else {}
    if args.send and eid in history.get("editions", {}):
        print(f"{eid} already sent; no duplicate email.")
        return 0
    selected = select_questions(banks, history, args.questions)
    stories, note = collect_news(now, history, args.offline, args.news_fixture)
    if args.demo:
        demo_history = {}
        for offset in (3, 2, 1, 0):
            sample_day = day - timedelta(weeks=offset)
            chosen = select_questions(banks, demo_history, args.questions)
            snapshot_note = note if offset == 0 else "Ejemplo del archivo: no se han reconstruido noticias de semanas anteriores."
            rendered = render_email(sample_day, chosen, stories if offset == 0 else [], snapshot_note,
                                    archive_url="../index.html", demo=True)
            publish(ROOT / "previews" / "archive", sample_day, chosen, rendered, demo=True)
            record_usage(demo_history, chosen, [], sample_day)
        # Use the latest sample in both the inbox preview and the archive.
        selected = chosen
        rendered = render_email(day, selected, stories, note, web_url=f"previews/archive/editions/{eid}.html",
                                archive_url="previews/archive/index.html", demo=True)
    else:
        base = os.getenv("URL_WEB", "").strip().rstrip("/") if args.send else ""
        if base:
            safe_url(base)
        rendered = render_email(day, selected, stories, note,
                                web_url=f"{base}/editions/{eid}.html" if base else "",
                                archive_url=f"{base}/index.html" if base else "", demo=not args.send)
    if not args.send:
        (ROOT / "vista_previa.html").write_text(rendered[0], encoding="utf-8")
        (ROOT / "vista_previa.txt").write_text(rendered[1], encoding="utf-8")
        print("Saved vista_previa.html and vista_previa.txt. No email sent; production history unchanged.")
        return 0
    # Stage web files before SMTP; a pending marker blocks ambiguous automatic retries.
    pending = ROOT / "state" / "pending.json"
    if pending.exists():
        raise RuntimeError("A pending delivery needs manual reconciliation. See README before retrying.")
    for variable in ("EMAIL_REMITENTE", "EMAIL_PASSWORD", "EMAIL_DESTINATARIOS"):
        if not os.getenv(variable, "").strip():
            raise ValueError(f"Missing required secret: {variable}")
    web_rendered = render_email(day, selected, stories, note, archive_url="../index.html")
    publish(ROOT / "docs", day, selected, web_rendered)
    write_json(pending, {"edition": eid, "date": day.isoformat(), "status": "delivery_uncertain_until_recorded",
                         "question_ids": [q["ID"] for k, *_ in SECTIONS for q in selected[k]],
                         "news_keys": [story_key(s) for s in stories]})
    send_email(f"{NAME} · {eid} · Your weekly curiosity quiz", rendered, eid)
    record_usage(history, selected, stories, day)
    history.setdefault("editions", {})[eid] = {"date": day.isoformat(), "status": "sent"}
    write_json(history_path, history)
    pending.unlink()
    print(f"{eid} sent, archived and recorded.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, smtplib.SMTPException) as exc:
        LOG.error("%s", exc)
        sys.exit(1)
