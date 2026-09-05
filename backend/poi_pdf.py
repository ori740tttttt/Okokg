"""
Generazione e lettura di un PDF MODULO COMPILABILE per le attrazioni della mappa.

- build_poi_pdf(pois): crea un PDF con una "scheda" per ogni attrazione.
  Nome e ubicazione sono già precompilati (sola lettura), gli altri campi
  (descrizione, prezzo, orari, durata, sconti, note, link) sono campi
  editabili che l'utente può compilare direttamente nel PDF.

- parse_poi_pdf(raw): legge i valori compilati e li restituisce raggruppati
  per id attrazione -> { campo: valore }.
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject

# Campi editabili nel modulo (ordine = layout)
EDITABLE_FIELDS = [
    "description", "price", "hours", "duration",
    "discount", "notes", "ticket_url", "image_url",
]

FIELD_LABELS = {
    "description": "Descrizione",
    "price": "Prezzo (es. €6, ridotto €3)",
    "hours": "Orari (es. 09:00–19:30)",
    "duration": "Durata (es. 2–3 ore)",
    "discount": "Sconti (es. under 18 gratis)",
    "notes": "Note utili",
    "ticket_url": "Link biglietti (https://…)",
    "image_url": "Link foto (https://…)",
}

SEP = "~"  # separatore id~campo (gli uuid non contengono '~')

# Palette coerente col sito
TERRACOTTA = HexColor("#C26B4E")
INK = HexColor("#2B2622")
INK_SOFT = HexColor("#6B6259")
SAND_LINE = HexColor("#E7DED2")
SAND_BG = HexColor("#FBF7F1")

PAGE_W, PAGE_H = A4
MARGIN = 40
CONTENT_W = PAGE_W - 2 * MARGIN


def _short_field(c, name, x, y, w, value, label):
    """Disegna un'etichetta + campo testo a riga singola."""
    c.setFont("Helvetica", 7.5)
    c.setFillColor(INK_SOFT)
    c.drawString(x, y + 18, label)
    c.acroForm.textfield(
        name=name, tooltip=label,
        x=x, y=y, width=w, height=15,
        borderStyle="underlined", borderColor=SAND_LINE,
        fillColor=None, textColor=INK, forceBorder=True,
        fontName="Helvetica", fontSize=9,
        value=value or "",
    )
    return 26  # altezza consumata (label + campo + gap)


def _multiline_field(c, name, x, y, w, value, label, height=34):
    c.setFont("Helvetica", 7.5)
    c.setFillColor(INK_SOFT)
    c.drawString(x, y + height + 3, label)
    c.acroForm.textfield(
        name=name, tooltip=label,
        x=x, y=y, width=w, height=height,
        borderStyle="solid", borderColor=SAND_LINE,
        fillColor=None, textColor=INK, forceBorder=True,
        fontName="Helvetica", fontSize=9,
        fieldFlags="multiline",
        value=value or "",
    )
    return height + 16


def _draw_header(c, page_no):
    c.setFillColor(TERRACOTTA)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN, PAGE_H - MARGIN, "Appartamento Matteo — Schede attrazioni")
    c.setFillColor(INK_SOFT)
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN, PAGE_H - MARGIN - 14,
                 "Compila i campi di ogni scheda e reimporta il PDF nell'area gestione › Mappa interattiva.")
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN, f"pag. {page_no}")
    c.setStrokeColor(SAND_LINE)
    c.setLineWidth(1)
    c.line(MARGIN, PAGE_H - MARGIN - 22, PAGE_W - MARGIN, PAGE_H - MARGIN - 22)


CARD_HEIGHT = 232  # altezza stimata di una scheda


def build_poi_pdf(pois) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Schede attrazioni — Appartamento Matteo")

    page_no = 1
    _draw_header(c, page_no)
    top = PAGE_H - MARGIN - 38  # cursore Y (parte alta della prossima scheda)

    for poi in pois:
        if top - CARD_HEIGHT < MARGIN:
            c.showPage()
            page_no += 1
            _draw_header(c, page_no)
            top = PAGE_H - MARGIN - 38

        pid = poi.get("id", "")
        name = poi.get("name", "")
        town = poi.get("town") or ""
        province = poi.get("province") or ""
        category = poi.get("category") or ""
        loc = " · ".join([p for p in [town, f"({province})" if province else "", category] if p])

        # cornice scheda
        card_y = top - CARD_HEIGHT
        c.setFillColor(SAND_BG)
        c.setStrokeColor(SAND_LINE)
        c.roundRect(MARGIN, card_y + 6, CONTENT_W, CARD_HEIGHT - 6, 8, stroke=1, fill=1)

        inner_x = MARGIN + 14
        inner_w = CONTENT_W - 28
        y = top - 18

        # Titolo (nome) + ubicazione — precompilati, sola lettura
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(inner_x, y, name[:60])
        y -= 14
        c.setFillColor(INK_SOFT)
        c.setFont("Helvetica", 8.5)
        c.drawString(inner_x, y, loc)
        # coordinate a destra (riferimento)
        lat = poi.get("lat"); lng = poi.get("lng")
        if lat is not None and lng is not None:
            c.drawRightString(MARGIN + CONTENT_W - 14, y, f"{lat:.4f}, {lng:.4f}")
        y -= 16

        # Descrizione (multiline, prefill)
        used = _multiline_field(c, f"{pid}{SEP}description", inner_x, y - 34, inner_w,
                                poi.get("description"), FIELD_LABELS["description"], height=34)
        y -= used

        # Riga 4 campi brevi: prezzo, orari, durata, sconti
        col_w = (inner_w - 3 * 10) / 4
        xs = [inner_x + i * (col_w + 10) for i in range(4)]
        for key, xi in zip(["price", "hours", "duration", "discount"], xs):
            _short_field(c, f"{pid}{SEP}{key}", xi, y - 15, col_w,
                         poi.get(key), FIELD_LABELS[key])
        y -= 26

        # Note (multiline)
        used = _multiline_field(c, f"{pid}{SEP}notes", inner_x, y - 28, inner_w,
                                poi.get("notes"), FIELD_LABELS["notes"], height=28)
        y -= used

        # Due link su una riga
        half = (inner_w - 10) / 2
        _short_field(c, f"{pid}{SEP}ticket_url", inner_x, y - 15, half,
                     poi.get("ticket_url"), FIELD_LABELS["ticket_url"])
        _short_field(c, f"{pid}{SEP}image_url", inner_x + half + 10, y - 15, half,
                     poi.get("image_url"), FIELD_LABELS["image_url"])
        y -= 26

        top = card_y - 10  # gap fra schede

    c.showPage()
    c.save()
    buf.seek(0)
    return _enable_fillable(buf.getvalue())


def _enable_fillable(pdf_bytes: bytes) -> bytes:
    """Imposta /NeedAppearances true e assicura che i campi siano editabili,
    così tutti i visualizzatori (incluso Apple/iPad) li mostrano compilabili."""
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append(reader)
    try:
        writer.set_need_appearances_writer(True)
    except Exception:
        # fallback manuale sul catalogo AcroForm
        try:
            root = writer._root_object
            if "/AcroForm" in root:
                root["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)
        except Exception:
            pass
    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out.getvalue()


def parse_poi_pdf(raw: bytes) -> dict:
    """Restituisce { poi_id: { campo: valore } } per i campi compilati."""
    reader = PdfReader(BytesIO(raw))
    fields = reader.get_fields() or {}
    result = {}
    for full_name, field in fields.items():
        if not full_name or SEP not in full_name:
            continue
        pid, key = full_name.rsplit(SEP, 1)
        if key not in EDITABLE_FIELDS:
            continue
        val = field.get("/V")
        if val is None:
            val = ""
        val = str(val).strip()
        result.setdefault(pid, {})[key] = val
    return result
