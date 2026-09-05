"""
Carmelo IA - Concierge turistico esperto delle province di Palermo e Trapani.

Espone helpers per:
  - Chat multi-turno con memoria (in-memory + persistenza messaggi MongoDB)
  - Generazione itinerari dettagliati (1-15 giorni, formato ora-per-ora o libero)
  - Adattamento di itinerari esterni (file PDF/DOCX/TXT o testo incollato)
  - Scelta modello: Claude / GPT / Gemini (1 o più in parallelo)

Le info su prezzi/orari sono ESPLICITAMENTE marcate come "indicative" perché possono
variare. Il system prompt impone a Carmelo di consigliare di verificare prima della visita.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Dict, List, Optional, Tuple

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

logger = logging.getLogger("carmelo")

# ============================================================
# Modelli disponibili
# ============================================================
MODELS = {
    "claude": ("anthropic", "claude-sonnet-4-5-20250929"),
    "openai": ("openai", "gpt-4o"),
    "gemini": ("gemini", "gemini-2.5-flash"),
}

MODEL_LABELS = {
    "claude": "Claude Sonnet 4.5",
    "openai": "GPT-4o",
    "gemini": "Gemini 2.5 Flash",
}


def resolve_models(selection: Optional[List[str]] | Optional[str]) -> List[str]:
    """Normalizza la selezione modello in lista valida. Default: claude."""
    if not selection:
        return ["claude"]
    if isinstance(selection, str):
        if selection == "all":
            return ["claude", "openai", "gemini"]
        selection = [selection]
    out = [m for m in selection if m in MODELS]
    return out or ["claude"]


# ============================================================
# Knowledge base certificato (Palermo + Trapani)
# Prezzi/orari sono indicativi - Carmelo dirà sempre di verificare.
# ============================================================
KNOWLEDGE_BASE = """
# CONOSCENZE CERTIFICATE — Province di PALERMO e TRAPANI
(Tutti i prezzi/orari sono INDICATIVI e da verificare prima della visita.
Le riduzioni standard in Italia: gratis under 18 nei musei statali e disabile+accompagnatore.
Ridotto 18-25 anni UE nei musei statali. Gratis prima domenica del mese in molti musei statali.)

## ATTRAZIONI PROVINCIA DI PALERMO

### PALERMO CITTÀ
- **Cattedrale di Palermo** — Corso Vittorio Emanuele. Ingresso chiesa GRATIS.
  Percorso completo (Tesoro, Cripta, Tombe Reali, Tetti): ~15 € intero, ~12 € ridotto studenti,
  ~7 € bambini 7-17, gratis under 7. Orari: lun-sab 7:00-19:00, dom 8:00-13:00 e 16:00-19:00.
  Tetti consigliati al tramonto.
- **Palazzo dei Normanni + Cappella Palatina** — Piazza Indipendenza.
  Biglietto A (ven-lun, include Sale Reali): ~19 € intero, ~17 € ridotto 14-25,
  ~12 € studenti, gratis under 14 e disabili+accompagnatore.
  Biglietto B (mar-gio, solo Cappella e Giardini): ~15,50 € intero. Orari ~8:30-16:30.
- **Teatro Massimo** — Piazza Verdi. Visita guidata ~12 € intero, ~7 € ridotto (studenti),
  ~5 € bambini 6-13, gratis under 6. Tour ogni 30 min, 9:30-18:00.
- **Quattro Canti e Piazza Pretoria** — GRATIS, sempre accessibili.
  Fontana Pretoria visibile dalla piazza. Bellissimi al tramonto.
- **Mercato di Ballarò** — Via Ballarò. GRATIS. Mattina 7:00-14:00 lun-sab.
  Street food: panelle, sfincione, arancine, frittola.
- **Mercato della Vucciria** — Piazza Caracciolo. Di giorno è un mercato modesto;
  la sera diventa il cuore della movida (apericena, vino, musica).
- **Catacombe dei Cappuccini** — Piazza Cappuccini. ~5 € intero, ~3 € ridotto.
  Orari: 9:00-13:00 e 15:00-18:00. Chiuse domenica pomeriggio nei mesi invernali.
- **Cattedrale di Monreale** — Piazza Guglielmo II. Chiesa GRATIS. Chiostro: ~6 € intero,
  ~3 € ridotto 18-25, gratis under 18. Terrazze: ~5 €. Orari 8:30-12:45 e 14:30-17:00.
  UNESCO. Imperdibili i mosaici dorati arabo-normanni (oltre 6000 mq).
- **Galleria d'Arte Moderna (GAM)** — Via Sant'Anna 21. ~10 € intero, ~8 € ridotto.
- **Palazzo Abatellis (Galleria Regionale)** — Via Alloro 4. ~9 € intero, ~4,50 € ridotto.
  Ospita "Trionfo della Morte" e l'Annunciata di Antonello da Messina.
- **Orto Botanico di Palermo** — Via Lincoln 2. ~7 € intero, ~5 € ridotto. Aperto 9:00-18:00.

### CEFALÙ
- **Duomo di Cefalù** — Piazza Duomo. Ingresso GRATIS in chiesa.
  Percorso completo (Cripta + Chiostro + tetti): ~10 € intero, ~6 € ridotto. UNESCO.
- **La Rocca** — Salita ~30 min, ~5 € biglietto sentiero. Vista mozzafiato sul borgo e sul mare.
- **Lavatoio Medievale** — GRATIS, in Via Vittorio Emanuele.

### ALTRO (PA)
- **Duomo di Cefalù** (vedi sopra).
- **Castello di Carini** — ~5 € intero. La "Baronessa di Carini".
- **Solunto (area archeologica)** — ~6 € intero. Vista sul Golfo.
- **Villa Palagonia (Bagheria)** — "Villa dei Mostri". ~6 € intero.
- **Madonie — Piano Battaglia** — sentieri, in inverno neve. Borghi: Petralia Soprana, Castelbuono.

## ATTRAZIONI PROVINCIA DI TRAPANI

### SEGESTA (Calatafimi)
- **Parco Archeologico di Segesta** — Tempio dorico + Teatro Greco. ~6 € intero, ~3 € ridotto 18-25,
  gratis under 18 e over 65 UE. Orari estivi 9:00-19:30. Navetta interna per il teatro ~1,50 €.

### SELINUNTE (Castelvetrano)
- **Parco Archeologico di Selinunte** — il più grande d'Europa. ~6 € intero, ~3 € ridotto.
  Orari 9:00-19:00. Trenino elettrico interno consigliato ~6 €.

### ERICE
- **Borgo medievale di Erice** — ingresso libero. Funivia da Trapani ~9 € A/R adulti,
  ~4,50 € bambini 4-12. Apertura: 8:00-23:30 estate (verificare).
- **Castello di Venere** — ~6 € intero, ~3 € ridotto.
- **Pasticceria Maria Grammatico** — fondamentale per dolci di mandorla, genovesi, cannoli.

### TRAPANI
- **Saline di Trapani e Paceco** — Via Chiusa, Nubia. WWF.
  Museo del Sale ~3 € + visita guidata. Tramonto leggendario.
- **Torre di Ligny** — punta della città. Vista 360°. ~3 €.
- **Centro storico** — corso Vittorio Emanuele. GRATIS.
- **Funivia per Erice** — vedi Erice.

### MARSALA
- **Cantine Florio** — degustazione storica. Tour ~15 € (con degustazione 3 vini).
- **Cantine Donnafugata** — Tour da ~20 €.
- **Isola di Mozia / Mothia** — antica città fenicia, "Giovinetto di Mozia".
  Traghetto ~6 € A/R + ingresso ~9 €. Solo bagaglio piccolo.
- **Riserva dello Stagnone** — kitesurf e tramonti.

### SAN VITO LO CAPO
- **Spiaggia di San Vito** — bandiera blu, sabbia bianca, fondale basso. Lidi 20-30 €/giorno.
- **Tempio della Tonnara del Secco** — ingresso libero alla zona.
- **Couscous Fest** — fine settembre, evento gratuito.

### RISERVA DELLO ZINGARO
- **Riserva Naturale Orientata dello Zingaro** — primo parco regionale d'Italia.
  ~5 € intero, ~3 € ridotto (12-17), gratis under 11. Aperta 7:00-19:30 estate.
  3 sentieri: costiero (facile), media costa, alta montagna. 7 calette imperdibili
  (Cala dell'Uzzo, Cala Marinella, Cala Berretta, Cala della Disa, Cala del Varo, Cala Tonnarella, Cala Capreria).

### SCOPELLO / CASTELLAMMARE DEL GOLFO
- **Tonnara e Faraglioni di Scopello** — ~7 € ingresso al cortile della tonnara per accedere alla cala.
- **Baia di Guidaloca** — spiaggetta in ciottoli, libera.
- **Castellammare del Golfo** — centro storico + Castello arabo-normanno (~5 €).

### MAZARA DEL VALLO
- **Museo del Satiro Danzante** — Piazza Plebiscito. ~6 € intero, ~3 € ridotto.
- **Casbah** — quartiere arabo, ingresso libero a piedi.

## SCONTI / RIDUZIONI COMUNI
- **Bambini 0-6 anni**: quasi sempre gratis ai musei.
- **Studenti 18-25 UE**: ~50% di sconto ai musei statali con documento.
- **Over 65 UE**: gratis o ridotto nei musei statali (varia per regione).
- **Disabili + accompagnatore**: gratis nei musei statali (legge 104).
- **Prima domenica del mese**: musei statali GRATIS (es. Cefalù, Monreale chiostro, Selinunte, Segesta).
- **Tessere**: CoopCulture e Sicilypass possono includere ingressi multipli.

## DOVE MANGIARE (locali iconici, da verificare prima della visita)

### TRAPPETO (PA) — vicinissimo alla casa vacanze
- **Da Calogero** — pesce fresco, atmosfera familiare.
- **La Taverna del Pescatore** — terrazza vista mare, primi di mare.
- **Pasticceria Antico Bar Aragona** — colazione con cassatelle e granita.

### BALESTRATE (PA)
- **Ristorante Da Concetta** — pesce.
- **Trattoria Da Filippo** — cucina casareccia.

### CASTELLAMMARE DEL GOLFO (TP)
- **La Cambusa** — porto, pesce.
- **Galà Bistrot** — fine dining su lungomare.

### SCOPELLO (TP)
- **Bar del Cinema** — pane cunzato (panino con tonno, pomodori, formaggio, capperi, olive). Mitico.
- **Trattoria del Borgo** — cucina di mare.

### SAN VITO LO CAPO (TP)
- **Tha'am** — couscous di pesce premiato. Prenotare.
- **Profumi di Cous Cous** — couscous di carne e verdure.

### ERICE (TP)
- **Pasticceria Maria Grammatico** — dolci di mandorla, genovese (cassatina ricotta).
- **Monte San Giuliano** — ristorante tradizionale con vista.

### TRAPANI
- **Calvino** — pizza al taglio storica (rianata, alla trapanese).
- **Osteria La Bettolaccia** — couscous trapanese e busiate al pesto trapanese.
- **Cantina Siciliana** — cucina tipica con storia.

### MARSALA (TP)
- **San Lorenzo** — pesce di alta qualità, vino Marsala in abbinamento.
- **Il Gallo e l'Innamorata** — cucina del territorio.

### PALERMO
- **Antica Focacceria San Francesco** — sfincione, panelle, pane con la milza.
- **Bisso Bistrot** — bistrot economico in pieno centro (Quattro Canti).
- **Trattoria ai Cascinari** — frequentata da Camilleri, cucina palermitana.
- **Ferro di Cavallo** — popolare, economica, fa la lista.
- **Nni Franco u Vastiddaru** — street food.
- **Buatta Cucina Popolana** — moderna ma autentica.
- **Gagini Social Restaurant** — alta cucina contemporanea.

### MONREALE
- **Bricco e Bacco** — vista sul Conca d'Oro, cucina del territorio.

### CEFALÙ
- **Le Chat Noir** — vicino al duomo, busiate.
- **Tinchitè** — trattoria con vista mare.

## ESPERIENZE IMPERDIBILI
- Tramonto alle saline di Trapani / Stagnone di Marsala.
- Trekking sentiero costiero della Riserva dello Zingaro (7 km A/R fattibili in mezza giornata).
- Bagno al faraglione di Scopello.
- Funivia di Erice e dolci da Maria Grammatico al tramonto.
- Tour del centro storico di Palermo + Cattedrale + Cappella Palatina (1 giornata intera).
- Cefalù: Duomo + La Rocca + bagno + cena al porto.
- Segesta al mattino + Erice al pomeriggio (combo classica).
- Monreale al mattino + ritorno a Palermo per pomeriggio nei mercati.
- Couscous Fest a San Vito Lo Capo (fine settembre).

## DISTANZE DA TRAPPETO (auto)
- Balestrate: 4 km / 5 min
- Castellammare del Golfo: 21 km / 25 min
- Scopello: 30 km / 40 min
- Riserva dello Zingaro (ingresso sud): 35 km / 45 min
- San Vito Lo Capo: 60 km / 1h 15
- Erice: 70 km / 1h 30
- Palermo (centro): 40 km / 40 min
- Monreale: 50 km / 1h
- Segesta: 35 km / 35 min
- Cefalù: 110 km / 1h 30
- Trapani: 70 km / 1h 15
- Marsala: 90 km / 1h 30
- Selinunte: 100 km / 1h 30
- Aeroporto Palermo (Punta Raisi): 25 km / 25 min
- Aeroporto Trapani (Birgi): 60 km / 1h
"""

# ============================================================
# Property profile
# ============================================================
PROPERTY_CONTACT = """
Indirizzo: Via Gioacchino Rossini, 40, Trappeto (PA), Sicilia (90040)
Contatti: +39 388 161 1514 — +39 351 302 8126
Email: accetta562@gmail.com
CIR: 19082074C252260 — CIN: IT082074C2NA6HPQMB
Prenotazioni dirette: dal sito ufficiale Appartamento Matteo
"""


# ============================================================
# System prompts
# ============================================================
def build_system_prompt(mode: str = "chat", days: Optional[int] = None,
                        format_style: str = "free", extra: Optional[str] = None) -> str:
    """
    mode: chat | itinerary | adapt
    days: 1-15 (solo per itinerary)
    format_style: hourly | free
    """
    base = (
        "Sei **Carmelo**, concierge turistico siciliano della casa vacanze "
        "*Appartamento Matteo* a Trappeto (PA). Sei nato e cresciuto tra Palermo e Trapani, "
        "conosci ogni vicolo, ogni spiaggia e ogni trattoria del territorio.\n\n"
        "**LINGUA**: rispondi sempre in italiano caldo e ospitale, con qualche espressione "
        "siciliana qua e là (es. 'amunì', 'beddra', 'avete capito') ma mai eccessiva.\n\n"
        "**REGOLE OPERATIVE**:\n"
        "1. Quando dai un prezzo o un orario, premetti SEMPRE *'indicativo'* e suggerisci di "
        "verificare al sito ufficiale o telefonando prima della visita.\n"
        "2. Usa SOLO informazioni della knowledge base sotto; se non sai qualcosa con certezza, "
        "dillo apertamente invece di inventare.\n"
        "3. Per ogni attrazione menziona: nome esatto, indirizzo/ubicazione, prezzo intero indicativo, "
        "RIDUZIONI esplicite per studenti/giovani/anziani/disabili, orari indicativi e cosa rende speciale il luogo.\n"
        "4. Suggerisci SEMPRE ristoranti dalla lista certificata e specifica il piatto tipico da provare.\n"
        "5. Cita le distanze in km e minuti d'auto da Trappeto quando rilevante.\n"
        "6. Usa **markdown**: titoli ##, ###, elenchi puntati, **grassetto** per i nomi delle attrazioni.\n"
        "7. Sii pratico: parcheggi, biglietti online, code (es. Cappella Palatina la mattina presto), stagionalità.\n"
        "8. Se l'ospite chiede consigli social/marketing, sei anche esperto di Instagram, Reels, "
        "Facebook, TikTok per case vacanza in Sicilia.\n"
        "9. Chiudi sempre con un breve invito a contattare la casa vacanze se serve aiuto:\n"
        f"{PROPERTY_CONTACT}\n"
    )

    if mode == "itinerary":
        days_str = f"{days} giorni" if days else "il numero di giorni richiesto"
        if format_style == "hourly":
            fmt = (
                f"**FORMATO RICHIESTO**: itinerario di {days_str} *ora-per-ora*. "
                "Per ogni giorno crea sezioni con orari precisi (es. **09:00 - Cattedrale di Monreale**), "
                "tempi di percorrenza tra una tappa e l'altra, pause pranzo e cena con ristoranti consigliati, "
                "e indicazioni su parcheggi/trasporti. Concludi ogni giorno con un *consiglio del locale*."
            )
        else:
            fmt = (
                f"**FORMATO RICHIESTO**: itinerario di {days_str} *libero*. "
                "Per ogni giorno proponi un tema (es. *Giorno 2: Cultura arabo-normanna*), un elenco di "
                "luoghi da visitare con orari di apertura, prezzi indicativi e riduzioni, ubicazione, e "
                "ristoranti consigliati per pranzo/cena. NO orari rigidi, l'ospite sceglie il ritmo."
            )
        n = days or 0
        last_day = f"## Giorno {n}" if n else "## Giorno finale"
        base += (
            "\n**MODALITÀ ITINERARIO**: stai generando un itinerario completo.\n"
            f"⚠️ **VINCOLO TASSATIVO SUL NUMERO DI GIORNI**: l'itinerario DEVE contenere ESATTAMENTE {days_str}, "
            f"né uno in più né uno in meno. Devi scrivere una sezione `## Giorno X - ...` per OGNI giorno, "
            f"partendo da `## Giorno 1 - ...` fino ad arrivare obbligatoriamente a `{last_day} - ...`. "
            f"Non fermarti prima di aver completato tutti i {days_str}. Non accorpare due giorni in uno. "
            "Prima di concludere, ricontrolla di aver scritto tutte le intestazioni dei giorni richiesti.\n"
            "Inizia con un'introduzione di 2-3 righe, poi le sezioni giorno per giorno. "
            f"{fmt}\n"
            "Dopo l'ULTIMO giorno, termina con: una sezione **'🍝 Ristoranti consigliati'** complessiva, una "
            "**'💡 Consigli pratici'** (parcheggio, ZTL, biglietti, scarpe, orari migliori) e una "
            "**'📞 Bisogno di aiuto?'** con i contatti.\n"
        )
    elif mode == "adapt":
        base += (
            "\n**MODALITÀ ADATTAMENTO**: l'ospite ha caricato/incollato un suo itinerario. "
            "Il tuo compito è:\n"
            "a) Mantenere la struttura originale e l'ordine dei giorni dell'ospite.\n"
            "b) ARRICCHIRLO con: prezzi indicativi, orari, riduzioni, ristoranti consigliati nei pressi, "
            "distanze da Trappeto, e consigli pratici.\n"
            "c) Correggere errori palesi o suggerire alternative se una tappa è chiusa stagionalmente.\n"
            "d) Inserire all'inizio e alla fine i CONTATTI della casa vacanze Appartamento Matteo "
            "come riferimento per assistenza durante il soggiorno.\n"
            "e) Mantenere il tono e la lingua dell'itinerario originale, ma con il tuo tocco siciliano.\n"
        )
    else:  # chat
        base += (
            "\n**MODALITÀ CHAT**: rispondi alle domande dell'ospite in modo conversazionale. "
            "Tieni traccia della conversazione precedente e adatta i consigli al contesto. "
            "Se l'ospite chiede di costruire un itinerario, chiedi prima: giorni a disposizione, "
            "numero/età dei viaggiatori, interessi (cultura, spiagge, cibo, natura, famiglia, romantico), "
            "stile (rilassato vs intenso), eventuali esigenze (mobilità, bambini, vegani, etc.).\n"
        )

    if extra:
        base += f"\n**NOTE AGGIUNTIVE**:\n{extra}\n"

    base += f"\n\n---\n# KNOWLEDGE BASE\n{KNOWLEDGE_BASE}"
    return base


# ============================================================
# In-memory chat session cache
# (key = session_id, value = LlmChat instance)
# I messaggi vengono anche persistiti in MongoDB per la UI.
# ============================================================
_chat_cache: Dict[str, LlmChat] = {}


def get_or_create_chat(session_id: str, model_key: str, api_key: str,
                       system_message: str) -> LlmChat:
    """Restituisce un LlmChat persistente in memoria per la coppia (session_id, model_key)."""
    cache_key = f"{session_id}::{model_key}"
    chat = _chat_cache.get(cache_key)
    if chat is not None:
        return chat
    provider, model_name = MODELS[model_key]
    chat = LlmChat(
        api_key=api_key,
        session_id=cache_key,
        system_message=system_message,
    ).with_model(provider, model_name)
    _chat_cache[cache_key] = chat
    return chat


def clear_chat_cache(session_id: str) -> int:
    """Rimuove tutte le istanze in cache per un session_id. Restituisce # rimosse."""
    removed = 0
    for key in list(_chat_cache.keys()):
        if key.startswith(f"{session_id}::"):
            _chat_cache.pop(key, None)
            removed += 1
    return removed


# ============================================================
# Estrazione testo da file (PDF / DOCX / TXT)
# ============================================================
def extract_text_from_upload(filename: str, content: bytes) -> str:
    """Estrae il testo da un file PDF / DOCX / TXT. Solleva ValueError per formati non supportati."""
    name = (filename or "").lower().strip()
    if name.endswith(".txt") or name.endswith(".md"):
        try:
            return content.decode("utf-8", errors="ignore")
        except Exception:
            return content.decode("latin-1", errors="ignore")
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            logger.exception("PDF extract error: %s", e)
            raise ValueError(f"Impossibile leggere il PDF: {e}")
    if name.endswith(".docx"):
        try:
            from docx import Document
            doc = Document(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            logger.exception("DOCX extract error: %s", e)
            raise ValueError(f"Impossibile leggere il DOCX: {e}")
    raise ValueError("Formato non supportato. Usa PDF, DOCX o TXT.")


# ============================================================
# SSE event formatter
# ============================================================
def sse_event(data: str, event: Optional[str] = None) -> str:
    """Formatta un evento SSE (Server-Sent Events). Newline JSON-encoded per safety."""
    payload = json.dumps({"data": data}) if data is not None else "{}"
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {payload}\n\n"


async def stream_chat_response(chat: LlmChat, user_text: str):
    """Generator: stream eventi SSE da una chat. Gestisce errori."""
    try:
        async for ev in chat.stream_message(UserMessage(text=user_text)):
            if isinstance(ev, TextDelta):
                yield sse_event(ev.content, "delta")
            elif isinstance(ev, StreamDone):
                yield sse_event("", "done")
                break
    except Exception as e:
        logger.exception("Carmelo stream error: %s", e)
        yield sse_event(str(e)[:300], "error")
