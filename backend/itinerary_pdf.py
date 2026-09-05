"""
Genera un PDF elegante dell'itinerario di Carmelo, con:
- copertina/testata con il LOGO dell'Appartamento Matteo
- contenuto markdown reso in modo grafico (giorni, sezioni, liste)
- piè di pagina con i contatti della casa vacanze su ogni pagina
"""
import io
import os
import re

import requests
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, Image, HRFlowable, KeepTogether,
)

# Palette coerente col sito
TERRACOTTA = HexColor("#C26B4E")
TERRACOTTA_DARK = HexColor("#A85539")
TERRACOTTA_SOFT = HexColor("#F3E3DA")
INK = HexColor("#2B2620")
MUTED = HexColor("#6B6255")
SAND = HexColor("#F7F2EA")
LINE = HexColor("#E7DED0")

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "matteo-logo.jpg")

PROPERTY = {
    "name": "Appartamento Matteo",
    "place": "Trappeto · Sicilia",
    "address": "Via Gioacchino Rossini, 40 — Trappeto (PA), 90040",
    "phones": "+39 388 161 1514  ·  +39 351 302 8126",
    "email": "accetta562@gmail.com",
    "codes": "CIR 19082074C252260  ·  CIN IT082074C2NA6HPQMB",
}

# Rimozione emoji/simboli non renderizzabili dai font standard PDF
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U000025A0-\U000025FF]",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text or "").strip()


def _inline(text: str) -> str:
    """Converte markdown inline (bold/italic/link) in mini-HTML per reportlab."""
    t = _strip_emoji(text)
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # link [testo](url)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)",
               r'<link href="\2" color="#A85539">\1</link>', t)
    # bold **testo**
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    # italic *testo* (evita i ** già gestiti)
    t = re.sub(r"(?<!\*)\*(?!\*)([^*]+?)\*(?!\*)", r"<i>\1</i>", t)
    return t.strip()


# Stili paragrafo
_ST = {
    "intro": ParagraphStyle("intro", fontName="Helvetica-Oblique", fontSize=11,
                            leading=16, textColor=MUTED, spaceAfter=6),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10.5,
                           leading=15, textColor=INK, spaceAfter=4),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=10.5,
                             leading=15, textColor=INK, leftIndent=14,
                             bulletIndent=4, spaceAfter=2),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11,
                         leading=15, textColor=TERRACOTTA_DARK, spaceBefore=6, spaceAfter=2),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=13.5,
                              leading=17, textColor=TERRACOTTA_DARK, spaceBefore=4, spaceAfter=2),
    "daynum": ParagraphStyle("daynum", fontName="Helvetica-Bold", fontSize=9,
                             leading=11, textColor=white, alignment=TA_CENTER),
    "dayn": ParagraphStyle("dayn", fontName="Helvetica-Bold", fontSize=17,
                           leading=18, textColor=white, alignment=TA_CENTER),
    "daytitle": ParagraphStyle("daytitle", fontName="Helvetica-Bold", fontSize=14,
                               leading=17, textColor=white),
    "cover_title": ParagraphStyle("cover_title", fontName="Helvetica-Bold", fontSize=26,
                                  leading=30, textColor=TERRACOTTA_DARK, alignment=TA_CENTER),
    "cover_sub": ParagraphStyle("cover_sub", fontName="Helvetica", fontSize=11,
                                leading=15, textColor=MUTED, alignment=TA_CENTER),
    "kicker": ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=9,
                             leading=12, textColor=TERRACOTTA, alignment=TA_CENTER),
}


def _day_banner(n: str, title: str, width: float):
    """Banner colorato per l'intestazione di un giorno."""
    num_cell = Table(
        [[Paragraph("GIORNO", _ST["daynum"])], [Paragraph(str(n), _ST["dayn"])]],
        colWidths=[24 * mm], rowHeights=[6 * mm, 8 * mm],
    )
    num_cell.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    title_para = Paragraph(_inline(title) or f"Giorno {n}", _ST["daytitle"])
    banner = Table([[num_cell, title_para]], colWidths=[26 * mm, width - 26 * mm])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TERRACOTTA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 6),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("RIGHTPADDING", (1, 0), (1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEAFTER", (0, 0), (0, 0), 0.6, white),
    ]))
    return banner


def _parse_markdown(md: str, width: float):
    """Trasforma il markdown in una lista di flowables."""
    flow = []
    lines = (md or "").replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1
        if not line:
            continue

        # H1 -> titolo intro
        if line.startswith("# ") and not line.startswith("## "):
            flow.append(Paragraph(_inline(line[2:]), _ST["section"]))
            continue

        # H2
        if line.startswith("## "):
            text = line[3:].strip()
            m = re.match(r"Giorno\s*(\d+)\s*[-–—:·|]?\s*(.*)", text, re.IGNORECASE)
            if m:
                flow.append(Spacer(1, 8))
                flow.append(_day_banner(m.group(1), m.group(2), width))
                flow.append(Spacer(1, 4))
            else:
                flow.append(Spacer(1, 6))
                flow.append(Paragraph(_inline(text), _ST["section"]))
                flow.append(HRFlowable(width="100%", thickness=0.8, color=LINE,
                                       spaceBefore=1, spaceAfter=4))
            continue

        # H3 / H4
        if line.startswith("### ") or line.startswith("#### "):
            flow.append(Paragraph(_inline(line.lstrip("#").strip()), _ST["h3"]))
            continue

        # Bullet
        if line.startswith(("- ", "* ", "• ")):
            flow.append(Paragraph(_inline(line[2:]), _ST["bullet"], bulletText="•"))
            continue
        m = re.match(r"^\d+\.\s+(.*)", line)
        if m:
            flow.append(Paragraph(_inline(m.group(1)), _ST["bullet"], bulletText="•"))
            continue

        # Separatore
        if re.match(r"^(-{3,}|_{3,}|\*{3,})$", line):
            flow.append(HRFlowable(width="100%", thickness=0.6, color=LINE,
                                   spaceBefore=4, spaceAfter=4))
            continue

        # Paragrafo normale
        flow.append(Paragraph(_inline(line), _ST["body"]))
    return flow


def _cover(width: float, title: str, days):
    """Testata con logo e titolo dell'itinerario."""
    els = []
    if os.path.exists(LOGO_PATH):
        try:
            img = Image(LOGO_PATH, width=52 * mm, height=52 * mm, kind="proportional")
            img.hAlign = "CENTER"
            els.append(img)
            els.append(Spacer(1, 6))
        except Exception:
            pass
    els.append(Paragraph("APPARTAMENTO MATTEO", _ST["kicker"]))
    els.append(Spacer(1, 2))
    heading = title or "Il tuo itinerario in Sicilia"
    els.append(Paragraph(_inline(heading), _ST["cover_title"]))
    sub = PROPERTY["place"]
    if days:
        sub = f"{days} {'giorno' if int(days) == 1 else 'giorni'}  ·  {sub}"
    els.append(Spacer(1, 2))
    els.append(Paragraph(sub, _ST["cover_sub"]))
    els.append(Spacer(1, 8))
    els.append(HRFlowable(width="60%", thickness=1.2, color=TERRACOTTA, hAlign="CENTER"))
    els.append(Spacer(1, 12))
    return KeepTogether(els)


def _footer(canvas, doc):
    canvas.saveState()
    w, _h = A4
    y = 16 * mm
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(18 * mm, y + 9 * mm, w - 18 * mm, y + 9 * mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(TERRACOTTA_DARK)
    canvas.drawCentredString(w / 2, y + 4.5 * mm,
                             f"{PROPERTY['name']}  —  {PROPERTY['address']}")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(w / 2, y + 1 * mm,
                             f"{PROPERTY['phones']}  ·  {PROPERTY['email']}")
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(w / 2, y - 2.5 * mm, PROPERTY["codes"])
    # numero pagina
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(w - 18 * mm, _h - 12 * mm, f"pag. {doc.page}")
    canvas.restoreState()


def build_itinerary_pdf(markdown_text: str, title: str = None, days=None) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=30 * mm,
        title=(title or "Itinerario Appartamento Matteo"),
        author="Appartamento Matteo",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_footer)])

    story = [_cover(doc.width, title, days)]
    story += _parse_markdown(markdown_text, doc.width)
    doc.build(story)
    return buf.getvalue()



# ============================================================
# PDF SCHEMATICO (con immagini per attrazione)
# ============================================================
_ST["stopname"] = ParagraphStyle("stopname", fontName="Helvetica-Bold", fontSize=12,
                                 leading=15, textColor=TERRACOTTA_DARK, spaceAfter=1)
_ST["stopdesc"] = ParagraphStyle("stopdesc", fontName="Helvetica", fontSize=9.5,
                                 leading=13, textColor=INK, spaceAfter=2)
_ST["infolabel"] = ParagraphStyle("infolabel", fontName="Helvetica-Bold", fontSize=7,
                                  leading=9, textColor=MUTED)
_ST["infoval"] = ParagraphStyle("infoval", fontName="Helvetica", fontSize=8.5,
                                leading=11, textColor=INK)
_ST["timebadge"] = ParagraphStyle("timebadge", fontName="Helvetica-Bold", fontSize=7.5,
                                  leading=10, textColor=white, alignment=TA_CENTER)
_ST["theme"] = ParagraphStyle("theme", fontName="Helvetica-Oblique", fontSize=10,
                             leading=13, textColor=MUTED, spaceAfter=2)

_IMG_CACHE = {}


def _fetch_image(url: str):
    if not url:
        return None
    if url in _IMG_CACHE:
        return _IMG_CACHE[url]
    # Supporto data: URLs (immagini caricate come base64)
    if url.startswith("data:"):
        try:
            import base64
            _, b64 = url.split(",", 1)
            data = io.BytesIO(base64.b64decode(b64))
            _IMG_CACHE[url] = data
            return data
        except Exception as e:
            print(f"[itinerary_pdf] data URL decode failed: {e}")
            _IMG_CACHE[url] = None
            return None
    # HTTP(S) URLs
    try:
        r = requests.get(
            url, timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AppartamentoMatteo/1.0)",
                "Accept": "image/*,*/*;q=0.8",
            },
            allow_redirects=True,
        )
        if r.status_code == 200 and r.content:
            data = io.BytesIO(r.content)
            _IMG_CACHE[url] = data
            return data
        print(f"[itinerary_pdf] image fetch {url[:80]} => HTTP {r.status_code}")
    except Exception as e:
        print(f"[itinerary_pdf] image fetch failed for {url[:80]}: {e}")
    _IMG_CACHE[url] = None
    return None


def _info_row(label: str, value: str):
    return [Paragraph(label.upper(), _ST["infolabel"]),
            Paragraph(_inline(value or "—"), _ST["infoval"])]


def _location_row(location: str, address: str, maps_url: str):
    """Riga Ubicazione con via + link Google Maps."""
    lines = []
    if location:
        lines.append(_inline(location))
    if address:
        lines.append(f'<font color="#6B6255">{_inline(address)}</font>')
    if maps_url:
        lines.append(
            f'<link href="{maps_url}"><font color="#3B82F6">Apri in Google Maps</font></link>'
        )
    val = "<br/>".join(lines) if lines else "—"
    return [Paragraph("UBICAZIONE", _ST["infolabel"]),
            Paragraph(val, _ST["infoval"])]


def _tickets_row(cost: str, ticket_url: str):
    """Riga Biglietti con prezzo + link sito ufficiale."""
    lines = []
    if cost:
        lines.append(_inline(cost))
    if ticket_url:
        lines.append(
            f'<link href="{ticket_url}"><font color="#C26B4E">Sito ufficiale biglietti</font></link>'
        )
    val = "<br/>".join(lines) if lines else "—"
    return [Paragraph("BIGLIETTI", _ST["infolabel"]),
            Paragraph(val, _ST["infoval"])]


def _stop_card(stop: dict, width: float):
    img_w, img_h = 44 * mm, 34 * mm
    # colonna immagine
    img_bytes = _fetch_image(stop.get("image"))
    if img_bytes:
        try:
            img_flow = Image(img_bytes, width=img_w, height=img_h, kind="proportional")
        except Exception as e:
            print(f"[itinerary_pdf] Image widget failed: {e}")
            img_flow = Spacer(img_w, img_h)
    else:
        # placeholder testuale se la foto non è disponibile
        img_flow = Table(
            [[Paragraph('<font color="#B39985">Foto non disponibile</font>',
                        ParagraphStyle("noimg", fontSize=7.5, leading=9, alignment=TA_CENTER))]],
            colWidths=[img_w], rowHeights=[img_h],
        )
        img_flow.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, -1), SAND),
            ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ]))

    # colonna testo
    right = []
    time = (stop.get("time") or "").strip()
    header_bits = []
    header_bits.append(Paragraph(_inline(stop.get("name") or "Tappa"), _ST["stopname"]))
    right.extend(header_bits)
    if time:
        tb = Table([[Paragraph(f'<font color="#A85539"><b>{_strip_emoji(time).upper()}</b></font>',
                               ParagraphStyle("tb", fontSize=7.5, leading=10, alignment=TA_CENTER))]],
                   colWidths=[24 * mm])
        tb.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), TERRACOTTA_SOFT),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        right.append(tb)
        right.append(Spacer(1, 2))
    if stop.get("description"):
        right.append(Paragraph(_inline(stop["description"]), _ST["stopdesc"]))

    # griglia info
    text_w = width - img_w - 14
    info = Table([
        _location_row(stop.get("location"), stop.get("address"), stop.get("maps_url")),
        _info_row("Orari", stop.get("hours")),
        _tickets_row(stop.get("cost"), stop.get("ticket_url")),
        _info_row("Durata", stop.get("duration")),
    ], colWidths=[20 * mm, text_w - 20 * mm])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
    ]))
    right.append(Spacer(1, 3))
    right.append(info)

    card = Table([[img_flow, right]], colWidths=[img_w + 4, width - img_w - 4])
    card.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#FBF8F2")),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LEFTPADDING", (0, 0), (0, 0), 3), ("RIGHTPADDING", (0, 0), (0, 0), 6),
        ("LEFTPADDING", (1, 0), (1, 0), 4), ("RIGHTPADDING", (1, 0), (1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return card


def build_structured_pdf(itin: dict, title: str = None) -> bytes:
    buf = io.BytesIO()
    days_list = itin.get("days") or []
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=16 * mm, bottomMargin=30 * mm,
        title=(title or itin.get("title") or "Itinerario Appartamento Matteo"),
        author="Appartamento Matteo",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_footer)])

    story = [_cover(doc.width, title or itin.get("title"), len(days_list))]
    if itin.get("intro"):
        story.append(Paragraph(_inline(itin["intro"]), _ST["intro"]))
        story.append(Spacer(1, 4))

    for day in days_list:
        n = day.get("day") or ""
        story.append(Spacer(1, 8))
        story.append(_day_banner(str(n), day.get("theme") or "", doc.width))
        story.append(Spacer(1, 5))
        for stop in (day.get("stops") or []):
            story.append(_stop_card(stop, doc.width))
            story.append(Spacer(1, 6))

    # Ristoranti
    restaurants = itin.get("restaurants") or []
    if restaurants:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Ristoranti consigliati", _ST["section"]))
        story.append(HRFlowable(width="100%", thickness=0.8, color=LINE, spaceBefore=1, spaceAfter=4))
        for r in restaurants:
            bits = [b for b in [r.get("name"), r.get("area"), r.get("dish"), r.get("price")] if b]
            if r.get("name"):
                line = f"<b>{_inline(r['name'])}</b>"
                extra = " · ".join(_inline(x) for x in [r.get("area"), r.get("dish"), r.get("price")] if x)
                if extra:
                    line += f" — {extra}"
                story.append(Paragraph(line, _ST["bullet"], bulletText="•"))

    # Consigli
    tips = itin.get("tips") or []
    if tips:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Consigli pratici", _ST["section"]))
        story.append(HRFlowable(width="100%", thickness=0.8, color=LINE, spaceBefore=1, spaceAfter=4))
        for tip in tips:
            story.append(Paragraph(_inline(str(tip)), _ST["bullet"], bulletText="•"))

    doc.build(story)
    return buf.getvalue()
