"""
Carmelo Content - Gestione contenuti curati da Matteo:
  - FAQ (multilingua via traduzione on-demand con LLM)
  - Itinerari PDF caricati dal gestionale (con 3 livelli visibilità)
  - Inbox domande aperte degli ospiti

Le risposte sono scritte da Matteo (IT). Le traduzioni in EN/ES/FR/DE vengono
generate on-demand dall'LLM e memorizzate per riuso.
"""

from __future__ import annotations
import logging
import re
from typing import Optional, List, Dict, Any
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("carmelo.content")

SUPPORTED_LANGS = ["it", "en", "es", "fr", "de"]
DEFAULT_LANG = "it"

LANG_NAMES = {
    "it": "Italian",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}

# ============================================================
# Categorie FAQ predefinite (UI usa queste come filtro)
# ============================================================
FAQ_CATEGORIES = [
    {"key": "casa", "label_it": "La casa", "label_en": "The house",
     "label_es": "La casa", "label_fr": "La maison", "label_de": "Das Haus", "icon": "House"},
    {"key": "arrivo", "label_it": "Arrivo e check-in", "label_en": "Arrival & check-in",
     "label_es": "Llegada y check-in", "label_fr": "Arrivée et check-in",
     "label_de": "Ankunft & Check-in", "icon": "Key"},
    {"key": "servizi", "label_it": "Servizi inclusi", "label_en": "Included services",
     "label_es": "Servicios incluidos", "label_fr": "Services inclus",
     "label_de": "Inbegriffene Services", "icon": "Sparkle"},
    {"key": "extra", "label_it": "Servizi extra", "label_en": "Extra services",
     "label_es": "Servicios extra", "label_fr": "Services extra",
     "label_de": "Extra-Services", "icon": "PlusCircle"},
    {"key": "vicinato", "label_it": "Vicinato e spesa", "label_en": "Neighbourhood & shopping",
     "label_es": "Barrio y compras", "label_fr": "Quartier et courses",
     "label_de": "Umgebung & Einkaufen", "icon": "MapPin"},
    {"key": "spiaggia", "label_it": "Spiaggia e mare", "label_en": "Beach & sea",
     "label_es": "Playa y mar", "label_fr": "Plage et mer",
     "label_de": "Strand und Meer", "icon": "UmbrellaSimple"},
    {"key": "trasporti", "label_it": "Trasporti", "label_en": "Transport",
     "label_es": "Transporte", "label_fr": "Transport",
     "label_de": "Transport", "icon": "Car"},
    {"key": "pratico", "label_it": "Info pratiche", "label_en": "Practical info",
     "label_es": "Info práctica", "label_fr": "Infos pratiques",
     "label_de": "Praktische Infos", "icon": "Info"},
    {"key": "emergenze", "label_it": "Emergenze", "label_en": "Emergencies",
     "label_es": "Emergencias", "label_fr": "Urgences",
     "label_de": "Notfälle", "icon": "Phone"},
]


# ============================================================
# FAQ stub iniziali — Matteo li trova già pronti da rispondere
# ============================================================
FAQ_SEED_STUBS = [
    # CASA (la casa)
    {"category": "casa", "question_it": "Quante persone può ospitare l'appartamento?", "priority": 100},
    {"category": "casa", "question_it": "Quante camere da letto e bagni ci sono?", "priority": 99},
    {"category": "casa", "question_it": "A che piano si trova l'appartamento? C'è l'ascensore?", "priority": 98},
    {"category": "casa", "question_it": "L'appartamento ha la terrazza o il balcone?", "priority": 97},
    {"category": "casa", "question_it": "C'è l'aria condizionata in tutte le stanze?", "priority": 96},
    {"category": "casa", "question_it": "C'è il riscaldamento? Funziona in inverno?", "priority": 95},
    {"category": "casa", "question_it": "La TV è presente? Ha canali satellitari o piattaforme di streaming?", "priority": 94},
    {"category": "casa", "question_it": "L'appartamento ha la lavatrice?", "priority": 93},
    {"category": "casa", "question_it": "La cucina è attrezzata? Cosa contiene esattamente?", "priority": 92},
    {"category": "casa", "question_it": "Sono ammessi animali domestici?", "priority": 91},
    {"category": "casa", "question_it": "Si può fumare nell'appartamento o in terrazza?", "priority": 90},
    # ARRIVO
    {"category": "arrivo", "question_it": "A che ora è il check-in e a che ora il check-out?", "priority": 100},
    {"category": "arrivo", "question_it": "Posso fare il check-in autonomo (self check-in)?", "priority": 99},
    {"category": "arrivo", "question_it": "Come ritiro le chiavi all'arrivo?", "priority": 98},
    {"category": "arrivo", "question_it": "È possibile fare un check-in anticipato o un check-out tardivo?", "priority": 97},
    {"category": "arrivo", "question_it": "Qual è l'indirizzo esatto dell'appartamento?", "priority": 96},
    {"category": "arrivo", "question_it": "Come raggiungo l'appartamento dall'aeroporto di Palermo?", "priority": 95},
    {"category": "arrivo", "question_it": "Come raggiungo l'appartamento dall'aeroporto di Trapani?", "priority": 94},
    {"category": "arrivo", "question_it": "Devo confermare l'orario di arrivo? Come?", "priority": 93},
    # SERVIZI INCLUSI
    {"category": "servizi", "question_it": "Il WiFi è incluso? Qual è la velocità?", "priority": 100},
    {"category": "servizi", "question_it": "Lenzuola e asciugamani sono inclusi?", "priority": 99},
    {"category": "servizi", "question_it": "La pulizia finale è inclusa nel prezzo?", "priority": 98},
    {"category": "servizi", "question_it": "Sono inclusi sapone, shampoo o prodotti di cortesia?", "priority": 97},
    {"category": "servizi", "question_it": "C'è un kit di benvenuto (caffè, tè, prodotti tipici)?", "priority": 96},
    {"category": "servizi", "question_it": "L'elettricità e l'acqua sono incluse nel prezzo?", "priority": 95},
    # EXTRA
    {"category": "extra", "question_it": "Posso richiedere una culla o un lettino per bambini?", "priority": 100},
    {"category": "extra", "question_it": "È disponibile un seggiolone per bambini?", "priority": 99},
    {"category": "extra", "question_it": "Posso noleggiare biciclette o scooter?", "priority": 98},
    {"category": "extra", "question_it": "È disponibile un servizio di transfer dall'aeroporto?", "priority": 97},
    {"category": "extra", "question_it": "Posso richiedere ombrelloni e sdraio per la spiaggia?", "priority": 96},
    {"category": "extra", "question_it": "Si possono richiedere pulizie extra durante il soggiorno?", "priority": 95},
    {"category": "extra", "question_it": "C'è la possibilità di parcheggio? È custodito?", "priority": 94},
    # VICINATO
    {"category": "vicinato", "question_it": "Dov'è il supermercato più vicino?", "priority": 100},
    {"category": "vicinato", "question_it": "C'è un panificio o una pasticceria vicino?", "priority": 99},
    {"category": "vicinato", "question_it": "Dov'è la farmacia più vicina?", "priority": 98},
    {"category": "vicinato", "question_it": "Dov'è il bancomat più vicino?", "priority": 97},
    {"category": "vicinato", "question_it": "L'edicola, il tabaccaio e l'ufficio postale dove si trovano?", "priority": 96},
    {"category": "vicinato", "question_it": "Quali sono i giorni del mercato a Trappeto e dintorni?", "priority": 95},
    # SPIAGGIA
    {"category": "spiaggia", "question_it": "Quanto dista la spiaggia dall'appartamento?", "priority": 100},
    {"category": "spiaggia", "question_it": "La spiaggia è libera o ci sono lidi attrezzati?", "priority": 99},
    {"category": "spiaggia", "question_it": "Il fondale è sabbioso o roccioso? È adatto ai bambini?", "priority": 98},
    {"category": "spiaggia", "question_it": "Posso noleggiare ombrelloni e lettini in spiaggia?", "priority": 97},
    {"category": "spiaggia", "question_it": "Quali altre spiagge belle ci sono nei dintorni?", "priority": 96},
    {"category": "spiaggia", "question_it": "Si possono fare sport acquatici (kayak, snorkeling, surf)?", "priority": 95},
    # TRASPORTI
    {"category": "trasporti", "question_it": "È necessario noleggiare un'auto?", "priority": 100},
    {"category": "trasporti", "question_it": "Ci sono autobus o treni da Trappeto verso Palermo o Trapani?", "priority": 99},
    {"category": "trasporti", "question_it": "Quanto costa un taxi da Trappeto a Palermo?", "priority": 98},
    {"category": "trasporti", "question_it": "Quali compagnie di noleggio auto consigliate?", "priority": 97},
    # PRATICO
    {"category": "pratico", "question_it": "Bisogna pagare la tassa di soggiorno? Quanto?", "priority": 100},
    {"category": "pratico", "question_it": "È richiesta una cauzione? Quanto e quando viene restituita?", "priority": 99},
    {"category": "pratico", "question_it": "Quali sono le politiche di cancellazione?", "priority": 98},
    {"category": "pratico", "question_it": "Quali metodi di pagamento sono accettati?", "priority": 97},
    {"category": "pratico", "question_it": "Posso modificare le date della mia prenotazione?", "priority": 96},
    {"category": "pratico", "question_it": "Mi viene rilasciata fattura o ricevuta?", "priority": 95},
    # EMERGENZE
    {"category": "emergenze", "question_it": "Chi posso contattare in caso di guasti o problemi?", "priority": 100},
    {"category": "emergenze", "question_it": "Cosa faccio se perdo le chiavi?", "priority": 99},
    {"category": "emergenze", "question_it": "Dov'è il pronto soccorso o l'ospedale più vicino?", "priority": 98},
    {"category": "emergenze", "question_it": "Numeri utili in caso di emergenza", "priority": 97},
]


# ============================================================
# Helpers utility
# ============================================================
def slugify(text: str) -> str:
    """Converte titolo in slug URL-friendly."""
    text = (text or "").strip().lower()
    text = re.sub(r"[àáâã]", "a", text)
    text = re.sub(r"[èéêë]", "e", text)
    text = re.sub(r"[ìíîï]", "i", text)
    text = re.sub(r"[òóôõö]", "o", text)
    text = re.sub(r"[ùúûü]", "u", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "itinerario"


def get_text_for_lang(translations: Dict[str, Any], lang: str,
                     base_question: str, base_answer: str) -> Dict[str, str]:
    """Restituisce question/answer nella lingua richiesta o IT come fallback."""
    if lang == "it" or not translations:
        return {"question": base_question, "answer": base_answer}
    t = translations.get(lang)
    if t and t.get("question") and t.get("answer"):
        return {"question": t["question"], "answer": t["answer"]}
    return {"question": base_question, "answer": base_answer}


# ============================================================
# Traduzione FAQ via LLM (admin-only feature)
# ============================================================
async def translate_faq(api_key: str, question_it: str, answer_it: str,
                         target_lang: str) -> Dict[str, str]:
    """
    Traduce question/answer da IT a target_lang usando Claude.
    Restituisce { question: "...", answer: "..." }.
    """
    if target_lang not in LANG_NAMES or target_lang == "it":
        raise ValueError(f"Lingua non supportata: {target_lang}")

    lang_name = LANG_NAMES[target_lang]
    system = (
        f"You are a professional translator for a Sicilian vacation rental. "
        f"Translate Italian text to {lang_name} naturally and warmly. "
        f"Keep the same tone (friendly, professional, hospitable). "
        f"Do NOT translate proper nouns (Trappeto, Palermo, Erice, etc.) or phone numbers. "
        f"Respond ONLY with the translation, NO preamble, NO explanations, NO quotes."
    )
    chat = LlmChat(
        api_key=api_key,
        session_id=f"translate-{target_lang}",
        system_message=system,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    # Translate question
    q_text = ""
    try:
        resp_q = await chat.send_message(UserMessage(text=f"Translate this question:\n\n{question_it}"))
        q_text = (resp_q or "").strip().strip('"').strip("'")
    except Exception as e:
        logger.exception("Translate question failed: %s", e)
        raise

    # Re-init chat for answer (avoid context contamination)
    chat2 = LlmChat(
        api_key=api_key,
        session_id=f"translate-{target_lang}-a",
        system_message=system,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    a_text = ""
    try:
        resp_a = await chat2.send_message(UserMessage(text=f"Translate this answer:\n\n{answer_it}"))
        a_text = (resp_a or "").strip().strip('"').strip("'")
    except Exception as e:
        logger.exception("Translate answer failed: %s", e)
        raise

    return {"question": q_text, "answer": a_text}


# ============================================================
# Public FAQ search helper
# ============================================================
def search_faqs(faqs: List[Dict[str, Any]], query: str, lang: str = "it") -> List[Dict[str, Any]]:
    """Ricerca semplice case-insensitive su question + answer + keywords nella lingua richiesta."""
    if not query or not query.strip():
        return faqs
    q = query.strip().lower()
    out = []
    for f in faqs:
        text_to_search = ""
        if lang != "it" and f.get("translations", {}).get(lang):
            t = f["translations"][lang]
            text_to_search = f"{t.get('question', '')} {t.get('answer', '')}"
        if not text_to_search.strip():
            text_to_search = f"{f.get('question_it', '')} {f.get('answer_it', '')}"
        text_to_search += " " + " ".join(f.get("keywords", []))
        if q in text_to_search.lower():
            out.append(f)
    return out
