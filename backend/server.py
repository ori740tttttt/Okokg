from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import secrets
import logging
import string
import random
import asyncio
import json
import base64
import csv
from io import BytesIO, StringIO
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional

import jwt
import bcrypt
import httpx
from urllib.parse import quote as urlquote
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse, Response
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone, ImageContent

# Carmelo IA helpers
from carmelo_ai import (
    MODELS as CARMELO_MODELS,
    MODEL_LABELS as CARMELO_MODEL_LABELS,
    resolve_models as carmelo_resolve_models,
    build_system_prompt as carmelo_build_system_prompt,
    get_or_create_chat as carmelo_get_chat,
    clear_chat_cache as carmelo_clear_cache,
    extract_text_from_upload as carmelo_extract_text,
    sse_event as carmelo_sse,
    stream_chat_response as carmelo_stream_response,
)

from carmelo_content import (
    SUPPORTED_LANGS,
    DEFAULT_LANG,
    FAQ_CATEGORIES,
    FAQ_SEED_STUBS,
    slugify as content_slugify,
    get_text_for_lang,
    translate_faq as content_translate_faq,
    search_faqs as content_search_faqs,
)

from marketing_ai import (
    MODELS as MKT_MODELS,
    MODEL_LABELS as MKT_MODEL_LABELS,
    MODEL_BEST_FOR as MKT_MODEL_BEST_FOR,
    resolve_models as mkt_resolve_models,
    build_chat_system_prompt as mkt_build_chat_prompt,
    build_post_generator_prompt as mkt_build_post_prompt,
    build_audit_prompt as mkt_build_audit_prompt,
    build_calendar_prompt as mkt_build_calendar_prompt,
    get_or_create_chat as mkt_get_chat,
    clear_chat_cache as mkt_clear_cache,
    send_message as mkt_send_message,
    extract_json as mkt_extract_json,
)

from itinerary_pdf import build_itinerary_pdf
import poi_images

# ============================================================
# Setup
# ============================================================
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = "HS256"
ADMIN_USERNAME = os.environ['ADMIN_USERNAME']
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']

app = FastAPI(title="Appartamento Matteo API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("appmatteo")


# ============================================================
# Helpers
# ============================================================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": now_utc() + timedelta(days=7),
        "iat": now_utc(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_admin(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    token = None
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        # fallback per download diretti (es. apertura PDF in nuova scheda su iPad)
        token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("sub") != ADMIN_USERNAME:
            raise HTTPException(status_code=401, detail="Non autorizzato")
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token scaduto")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")


def gen_confirmation_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ============================================================
# WhatsApp notifications (CallMeBot)
# ============================================================
def _normalize_phone(raw: str) -> str:
    """Strip spaces/dashes/parens but keep leading +. CallMeBot accepts both with and without +."""
    if not raw:
        return ""
    s = str(raw).strip()
    has_plus = s.startswith("+")
    digits = "".join(ch for ch in s if ch.isdigit())
    return ("+" + digits) if has_plus else digits


async def _send_whatsapp_raw(phone: str, api_key: str, text: str) -> dict:
    """Low-level call to CallMeBot. Returns {ok, status, body}. Never raises."""
    p = _normalize_phone(phone)
    if not p or not api_key or not text:
        return {"ok": False, "status": 0, "body": "missing config (phone/api_key/text)"}
    url = "https://api.callmebot.com/whatsapp.php"
    params = {"phone": p, "text": text, "apikey": api_key}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, params=params)
            body = (r.text or "")[:300]
            # CallMeBot returns plain text. "Message queued" / "Message Sent" / etc. on success.
            ok = r.status_code == 200 and ("queue" in body.lower() or "sent" in body.lower() or "success" in body.lower())
            return {"ok": ok, "status": r.status_code, "body": body}
    except Exception as e:
        logging.warning(f"WhatsApp send failed: {e}")
        return {"ok": False, "status": 0, "body": str(e)[:200]}


async def send_whatsapp_notification(event: str, text: str) -> None:
    """High-level fire-and-forget notification. event is one of:
       'new_request' | 'approved' | 'rejected' | 'deleted' | 'manual' | 'test'.
       Looks up settings; if disabled or the event toggle is off, silently no-op."""
    cfg = await db.settings.find_one({"_id": "whatsapp"}, {"_id": 0})
    if not cfg or not cfg.get("enabled"):
        return
    if event != "test":
        toggle_map = {
            "new_request": "notify_new_request",
            "approved": "notify_approved",
            "manual": "notify_approved",  # treat manual-approved as an approval
            "rejected": "notify_rejected",
            "deleted": "notify_deleted",
        }
        key = toggle_map.get(event)
        if key and not cfg.get(key, False):
            return
    phone = cfg.get("phone", "")
    api_key = cfg.get("api_key", "")
    if not phone or not api_key:
        return
    await _send_whatsapp_raw(phone, api_key, text)


def _format_booking_message(title: str, b: dict) -> str:
    """Build a WhatsApp-formatted message body for a booking event."""
    name = b.get("guest_name") or "—"
    email = b.get("guest_email") or "—"
    phone = b.get("guest_phone") or "—"
    ci = b.get("check_in") or "—"
    co = b.get("check_out") or "—"
    guests = b.get("guests") or "—"
    total = ((b.get("quote") or {}).get("total")) or 0
    source = b.get("source") or "site"
    src_label = "Booking.com" if source == "booking" else "Sito"
    code = b.get("confirmation_code") or ""
    msg = b.get("message") or ""

    # CallMeBot supports WhatsApp markdown: *bold*, _italic_
    lines = [
        f"*{title}*",
        "🏠 Appartamento Matteo",
        "",
        f"👤 *{name}*",
        f"📅 {ci} → {co}",
        f"👥 {guests} ospiti",
        f"💰 € {total:.2f}",
        f"🌐 Sorgente: {src_label}",
        f"📧 {email}",
        f"📞 {phone}",
    ]
    if code:
        lines.append(f"🔑 Codice: {code}")
    if msg:
        lines.append(f"💬 _{msg[:200]}_")
    return "\n".join(lines)


def daterange(start: date, end: date):
    """Yield dates in [start, end). end is exclusive (checkout day)."""
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


# ============================================================
# Models
# ============================================================
class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    token: str
    username: str


class PhotoIn(BaseModel):
    data_url: str  # base64 data URL
    filename: Optional[str] = None


class PhotoOut(BaseModel):
    id: str
    data_url: str
    filename: Optional[str] = None
    order: int = 0
    created_at: datetime


class PriceBulkIn(BaseModel):
    dates: List[str]  # YYYY-MM-DD
    price: Optional[float] = None  # site price
    booking_price: Optional[float] = None  # Booking.com price


class FeesIn(BaseModel):
    base_price_per_night: float = 80.0
    base_booking_price_per_night: float = 95.0
    base_guests: int = 2
    extra_person_per_night: float = 15.0
    ac_per_night: float = 5.0
    tourist_tax_per_person_per_night: float = 2.0
    cleaning_fee: float = 40.0
    booking_url: str = "https://www.booking.com/hotel/it/appartamento-matteo-trappeto.it.html?chal_t=1781608143459&force_referer=https%3A%2F%2Fwww.google.com%2F"


class CustomFeeIn(BaseModel):
    name: str
    amount: float
    mode: str  # "per_night" | "per_stay"


class PropertyIn(BaseModel):
    name: str
    location: str
    rooms: int
    bathrooms: int
    kitchen: int
    living_room: int
    max_guests: int
    description: str
    amenities: List[str]


class PhotoOrderIn(BaseModel):
    ids: List[str]


class PoiIn(BaseModel):
    name: str
    category: str  # "art" | "beach" | "nature"
    lat: float
    lng: float
    description: Optional[str] = None
    town: Optional[str] = None
    province: Optional[str] = None  # "PA" | "TP"
    # Rich itinerary fields
    price: Optional[str] = None        # es. "€6 (ridotto €3)"
    hours: Optional[str] = None        # es. "09:00–19:30"
    duration: Optional[str] = None     # es. "2–3 ore"
    discount: Optional[str] = None     # es. "Gratis 1ª domenica del mese"
    notes: Optional[str] = None        # info utili: es. "Ingresso gratis, ma tetti a pagamento"
    ticket_url: Optional[str] = None   # sito per i biglietti
    maps_url: Optional[str] = None     # link Google Maps per le indicazioni (se vuoto, generato dalle coordinate)
    image_url: Optional[str] = None    # foto (URL o data URL)


class DiscountCodeIn(BaseModel):
    code: str
    type: str = "discount"  # "discount" | "ai_access"
    percent: Optional[float] = None  # required for discount type
    valid_from: str  # YYYY-MM-DD
    valid_to: str    # YYYY-MM-DD
    active: bool = True


class BookingIn(BaseModel):
    guest_name: str
    guest_email: str
    guest_phone: Optional[str] = None
    check_in: str   # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    guests: int
    extras: Optional[dict] = None  # {"ac": bool}
    discount_code: Optional[str] = None
    message: Optional[str] = None


class ItineraryIn(BaseModel):
    confirmation_code: str
    interests: Optional[str] = None
    travel_style: Optional[str] = None


class VerifyCodeIn(BaseModel):
    code: str


# Marketing assistant
class MarketingGenerateIn(BaseModel):
    platform: str               # instagram_post | instagram_story | instagram_reel | facebook_post | tiktok | x_twitter | pinterest | google_business | linkedin | youtube_short
    topic: str                  # free-form topic / brief
    tone: Optional[str] = None  # emozionale | autorevole | ironico | professionale | familiare | aspirational | promozionale
    languages: List[str] = ["it", "en", "es", "fr", "de"]
    custom_notes: Optional[str] = None


class MarketingImageIn(BaseModel):
    content_id: Optional[str] = None      # if set, the generated image is attached to this library item
    prompt: Optional[str] = None          # explicit custom prompt (overrides the rest)
    visual_concept: Optional[str] = None  # Carmelo's suggested visual
    topic: Optional[str] = None           # fallback brief
    platform: Optional[str] = None
    photo_id: Optional[str] = None        # gallery photo id used as REAL reference (location-accurate)
    reference_image: Optional[str] = None  # base64 data URL used as reference (alternative to photo_id)


class AttachPhotosIn(BaseModel):
    photo_ids: List[str] = []             # ids of gallery photos to attach to a marketing post


class MarketingStrategyIn(BaseModel):
    goal: Optional[str] = None            # es. "riempire settembre", "più prenotazioni dirette"


class VideoScriptIn(BaseModel):
    platform: Optional[str] = "tiktok"    # tiktok | instagram_reel | youtube_short | facebook_reel
    topic: str
    duration: Optional[int] = 20          # seconds
    languages: List[str] = ["it", "en"]
    tone: Optional[str] = None
    custom_notes: Optional[str] = None


class CalendarItemIn(BaseModel):
    title: str
    platform: Optional[str] = "tiktok"
    date: str                              # ISO date (YYYY-MM-DD)
    notes: Optional[str] = ""
    content_id: Optional[str] = None       # optional link to a library item
    status: Optional[str] = "planned"      # planned | done


class CalendarItemUpdate(BaseModel):
    title: Optional[str] = None
    platform: Optional[str] = None
    date: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class GBPostIn(BaseModel):
    post_type: Optional[str] = "update"    # update | offer | event
    topic: str
    languages: List[str] = ["it", "en", "es", "fr", "de"]
    offer_details: Optional[str] = None
    custom_notes: Optional[str] = None


class GBDescriptionIn(BaseModel):
    languages: List[str] = ["it", "en", "es", "fr", "de"]
    focus: Optional[str] = None



class ManualBookingIn(BaseModel):
    guest_name: str
    guest_email: Optional[str] = ""
    guest_phone: Optional[str] = None
    check_in: str   # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    guests: int = 2
    total_amount: float  # gross amount in EUR
    source: str         # "site" or "booking"
    status: Optional[str] = "approved"  # manual bookings are typically already confirmed
    notes: Optional[str] = None


class VisitIn(BaseModel):
    session_id: str
    path: Optional[str] = "/"
    referrer: Optional[str] = None


class CommissionRatesIn(BaseModel):
    state_pct: float = 21.0       # Tassa di Stato
    booking_pct: float = 15.0     # Commissione Booking
    vat_pct: float = 3.7          # IVA
    bank_pct: float = 1.5         # Transazioni bancarie


class WhatsAppSettingsIn(BaseModel):
    enabled: bool = False
    phone: str = "+393881611514"  # default to Matteo's primary number
    api_key: str = ""             # CallMeBot api key
    notify_new_request: bool = True
    notify_approved: bool = True
    notify_rejected: bool = False
    notify_deleted: bool = False


class WhatsAppTestIn(BaseModel):
    text: Optional[str] = None


# ============================================================
# Startup
# ============================================================
@app.on_event("startup")
async def startup_event():
    # Indexes
    await db.photos.create_index("order")
    await db.price_overrides.create_index("date", unique=True)
    await db.discount_codes.create_index("code", unique=True)
    await db.bookings.create_index("confirmation_code")
    await db.bookings.create_index("check_in")
    await db.visits.create_index("session_id")
    await db.visits.create_index("created_at")
    await db.marketing_content.create_index("created_at")

    # Seed admin
    existing = await db.admin.find_one({"username": ADMIN_USERNAME})
    if not existing:
        await db.admin.insert_one({
            "username": ADMIN_USERNAME,
            "password_hash": hash_password(ADMIN_PASSWORD),
            "created_at": now_utc().isoformat(),
        })
        logger.info("Admin seeded: %s", ADMIN_USERNAME)
    else:
        # Keep hash in sync with env (allows password rotation via env)
        if not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
            await db.admin.update_one(
                {"username": ADMIN_USERNAME},
                {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}}
            )
            logger.info("Admin password updated from env")

    # Seed default fees if missing
    fees = await db.settings.find_one({"_id": "fees"})
    if not fees:
        defaults = FeesIn().model_dump()
        defaults["_id"] = "fees"
        await db.settings.insert_one(defaults)

    # Seed default commission rates if missing
    rates = await db.settings.find_one({"_id": "commission_rates"})
    if not rates:
        defaults = CommissionRatesIn().model_dump()
        defaults["_id"] = "commission_rates"
        await db.settings.insert_one(defaults)

    # Seed POIs: inserimento idempotente per nome (case-insensitive).
    # Ad ogni avvio aggiunge solo i POI di DEFAULT_POIS che non esistono ancora,
    # così è facile estendere il catalogo senza dover azzerare il DB.
    existing_names = set()
    async for doc in db.pois.find({}, {"name": 1, "_id": 0}):
        n = (doc.get("name") or "").strip().lower()
        if n:
            existing_names.add(n)
    to_insert = [
        {**p, "id": str(uuid.uuid4())}
        for p in DEFAULT_POIS
        if (p.get("name") or "").strip().lower() not in existing_names
    ]
    if to_insert:
        await db.pois.insert_many(to_insert)
        logger.info("Seeded %d new POIs (total catalog now: %d)",
                    len(to_insert), len(existing_names) + len(to_insert))

    # Seed foto Galleria privata (Dashboard → Galleria) dal batch fornito dall'host.
    # Idempotente e "definitivo": usa un registro persistente delle seed_key
    # già consumate (in db.settings._id="private_photos_seed_log"), così una
    # volta seedata una foto NON viene mai più re-inserita — anche se l'admin
    # la elimina dalla dashboard.
    # Portabilità: se qualcuno copia il codice, al primo avvio le foto vengono
    # aggiunte automaticamente. Ai riavvii successivi (o dopo eliminazione)
    # il seed le salta grazie al log persistente.
    GALLERY_SEED = [
        # Batch fornito dall'host (luglio 2026) — Galleria privata Dashboard
        ("galleria_grotta_madonna_lourdes_belvedere.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/4d2sa8vk_IMG-20260713-WA0009.jpg"),
        ("galleria_vista_porto_palme_cactus_alba.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/d0456eqq_IMG-20260713-WA0014.jpg"),
        ("galleria_balcone_fiorito_petunie_porto.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/dtp3ftb7_IMG-20260713-WA0024.jpg"),
        ("galleria_palma_porticciolo_mare_montagne.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/gxwdwjyx_IMG-20260713-WA0016.jpg"),
        ("galleria_cartello_kiss_me_please_porto.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/f7shyoc9_IMG-20260713-WA0011.jpg"),
        # Batch 2 (luglio 2026) — altre foto iconiche di Trappeto
        ("galleria_belvedere_kiss_me_panchina_rossa.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/9ic3lg9d_IMG-20260713-WA0017.jpg"),
        ("galleria_trappeto_porto_vista_monte_cofano.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/hdq1s83m_IMG-20260713-WA0018.jpg"),
        ("galleria_parco_giochi_bambini_trappeto.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/itw13hbp_Gemini_Generated_Image_mshlchmshlchmshl~2.jpg"),
        ("galleria_murales_madonna_pescatori_trappeto.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/pnc3f12w_IMG-20260713-WA0015.jpg"),
        ("galleria_porticciolo_pescatori_barche_trappeto.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/lycey2sj_IMG-20260713-WA0012.jpg"),
    ]
    # Seed_key "legacy" del repo originale che NON devono più essere seedate né
    # ripristinate (l'host non le ha fornite e non le vuole più).
    LEGACY_PRIVATE_SEED_KEYS_TO_PURGE = [
        "edicola_madonna_trappeto.jpg",
        "cartello_kiss_me_please_trappeto.jpg",
        "panchina_rossa_belvedere_trappeto.jpg",
        "vicolo_fiorito_porto_trappeto.jpg",
        "porticciolo_ficodindia_trappeto.jpg",
    ]
    # Rimuovi da MongoDB le foto legacy (una tantum, se ancora presenti)
    try:
        purge_res = await db.private_photos.delete_many(
            {"seed_key": {"$in": LEGACY_PRIVATE_SEED_KEYS_TO_PURGE}}
        )
        if purge_res.deleted_count:
            logger.info("Purged %d legacy private photos", purge_res.deleted_count)
    except Exception as e:
        logger.warning("Legacy private photos purge error: %s", e)
    # Log persistente delle seed_key già utilizzate per la Galleria privata.
    priv_seed_log_doc = await db.settings.find_one({"_id": "private_photos_seed_log"}, {"_id": 0}) or {}
    consumed_priv_seed_keys = set(priv_seed_log_doc.get("consumed", []))
    # Backfill: se una foto è ancora presente in db.private_photos con quella
    # seed_key ma non è nel log, aggiungila subito al log persistente. Così
    # se l'admin la elimina in seguito, non tornerà al prossimo riavvio.
    existing_priv_seed_keys = set()
    async for d in db.private_photos.find({"seed_key": {"$exists": True}}, {"seed_key": 1, "_id": 0}):
        if d.get("seed_key"):
            existing_priv_seed_keys.add(d["seed_key"])
    if existing_priv_seed_keys - consumed_priv_seed_keys:
        consumed_priv_seed_keys = consumed_priv_seed_keys.union(existing_priv_seed_keys)
        await db.settings.update_one(
            {"_id": "private_photos_seed_log"},
            {"$set": {"consumed": list(consumed_priv_seed_keys), "updated_at": now_utc().isoformat()}},
            upsert=True,
        )

    missing = [(fn, url) for (fn, url) in GALLERY_SEED if fn not in consumed_priv_seed_keys]
    if missing:
        newly_consumed_priv = []
        try:
            # Usa max(order)+1 per evitare collisioni quando ci sono già foto
            # inserite (es. dopo cancellazioni parziali).
            max_priv = await db.private_photos.find_one({}, sort=[("order", -1)])
            base_order = (max_priv.get("order", -1) + 1) if max_priv else 0
            async with httpx.AsyncClient(timeout=20.0) as http_seed:
                for i, (filename, url) in enumerate(missing):
                    try:
                        r = await http_seed.get(url)
                        r.raise_for_status()
                        mime = r.headers.get("content-type", "image/jpeg").split(";")[0]
                        b64 = base64.b64encode(r.content).decode("ascii")
                        data_url = f"data:{mime};base64,{b64}"
                        await db.private_photos.insert_one({
                            "id": str(uuid.uuid4()),
                            "seed_key": filename,
                            "data_url": data_url,
                            "filename": filename,
                            "order": base_order + i,
                            "created_at": now_utc().isoformat(),
                        })
                        newly_consumed_priv.append(filename)
                    except Exception as e:
                        logger.warning("Gallery seed failed for %s: %s", filename, e)
            if newly_consumed_priv:
                all_consumed_priv = list(consumed_priv_seed_keys.union(newly_consumed_priv))
                await db.settings.update_one(
                    {"_id": "private_photos_seed_log"},
                    {"$set": {"consumed": all_consumed_priv, "updated_at": now_utc().isoformat()}},
                    upsert=True,
                )
                logger.info("Seeded %d foto in Galleria privata", len(newly_consumed_priv))
        except Exception as e:
            logger.warning("Gallery seed error: %s", e)

    # Seed foto Sezione Pubblica (visibili sul sito) dal batch fornito dall'host.
    # Idempotente e "definitivo": usa un registro persistente delle seed_key
    # già consumate (in db.settings), così una volta seedata una foto NON
    # viene mai più re-inserita — anche se l'admin la elimina dalla dashboard.
    # Portabilità: se qualcuno copia il codice, al primo avvio le foto vengono
    # aggiunte automaticamente. Ai riavvii successivi (o dopo eliminazione
    # dall'interfaccia) il seed le salta.
    PUBLIC_PHOTOS_SEED = [
        ("appartamento_matteo_soggiorno_orologio.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/16u6y9hw_527793756_24321829234079342_3082813497404339534_n.jpg"),
        ("appartamento_matteo_salotto_relax.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/mil2osc9_528044386_24321829434079322_9099943916039380541_n.jpg"),
        ("appartamento_matteo_camera_matrimoniale.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/ls66idr3_527404663_24321829620745970_6468062849176385990_n.jpg"),
        ("appartamento_matteo_cucina_soggiorno.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/hiw1h756_527190010_24321829830745949_8790051268822359350_n.jpg"),
        ("appartamento_matteo_camera_singola.jpg",
         "https://customer-assets.emergentagent.com/job_aer-preview/artifacts/kqj364rr_527651528_24321830177412581_5290042434970837103_n.jpg"),
    ]
    # Log persistente delle seed_key già utilizzate (una tantum, per sempre).
    seed_log_doc = await db.settings.find_one({"_id": "public_photos_seed_log"}, {"_id": 0}) or {}
    consumed_seed_keys = set(seed_log_doc.get("consumed", []))
    # Compat/backfill: se una foto è ancora presente in db.photos con quella
    # seed_key ma non è nel log, aggiungila subito al log persistente. Così, se
    # l'admin la elimina in seguito, non tornerà al prossimo riavvio.
    existing_seed_keys_in_photos = set()
    async for d in db.photos.find({"seed_key": {"$exists": True}}, {"seed_key": 1, "_id": 0}):
        if d.get("seed_key"):
            existing_seed_keys_in_photos.add(d["seed_key"])
    if existing_seed_keys_in_photos - consumed_seed_keys:
        consumed_seed_keys = consumed_seed_keys.union(existing_seed_keys_in_photos)
        await db.settings.update_one(
            {"_id": "public_photos_seed_log"},
            {"$set": {"consumed": list(consumed_seed_keys), "updated_at": now_utc().isoformat()}},
            upsert=True,
        )

    missing_public = [(fn, url) for (fn, url) in PUBLIC_PHOTOS_SEED if fn not in consumed_seed_keys]
    if missing_public:
        newly_consumed = []
        try:
            # Usa max(order)+1 per evitare collisioni quando ci sono già foto
            # inserite (es. dopo cancellazioni parziali).
            max_pub = await db.photos.find_one({}, sort=[("order", -1)])
            base_order_pub = (max_pub.get("order", -1) + 1) if max_pub else 0
            async with httpx.AsyncClient(timeout=20.0) as http_seed_pub:
                for i, (filename, url) in enumerate(missing_public):
                    try:
                        r = await http_seed_pub.get(url)
                        r.raise_for_status()
                        mime = r.headers.get("content-type", "image/jpeg").split(";")[0]
                        b64 = base64.b64encode(r.content).decode("ascii")
                        data_url = f"data:{mime};base64,{b64}"
                        await db.photos.insert_one({
                            "id": str(uuid.uuid4()),
                            "seed_key": filename,
                            "data_url": data_url,
                            "filename": filename,
                            "order": base_order_pub + i,
                            "created_at": now_utc().isoformat(),
                        })
                        newly_consumed.append(filename)
                    except Exception as e:
                        logger.warning("Public photos seed failed for %s: %s", filename, e)
            if newly_consumed:
                # Aggiorna il registro persistente: queste seed_key non verranno
                # più re-inserite, anche se l'admin le elimina dalla dashboard.
                all_consumed = list(consumed_seed_keys.union(newly_consumed))
                await db.settings.update_one(
                    {"_id": "public_photos_seed_log"},
                    {"$set": {"consumed": all_consumed, "updated_at": now_utc().isoformat()}},
                    upsert=True,
                )
                logger.info("Seeded %d foto in Sezione Pubblica", len(newly_consumed))
        except Exception as e:
            logger.warning("Public photos seed error: %s", e)


# ============================================================
# Auth
# ============================================================
@api.post("/auth/login", response_model=TokenOut)
async def login(body: LoginIn):
    if body.username.strip().lower() != ADMIN_USERNAME.lower():
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    admin = await db.admin.find_one({"username": ADMIN_USERNAME})
    if not admin or not verify_password(body.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    token = create_token(ADMIN_USERNAME)
    return TokenOut(token=token, username=ADMIN_USERNAME)


@api.get("/auth/me")
async def me(user: str = Depends(get_current_admin)):
    return {"username": user}


# ============================================================
# Property info (static for now)
# ============================================================
@api.get("/property")
async def get_property():
    info = await db.settings.find_one({"_id": "property"})
    if not info:
        info = {
            "_id": "property",
            "name": "Appartamento Matteo",
            "location": "Trappeto (PA), Sicilia",
            "rooms": 2,
            "bathrooms": 1,
            "kitchen": 1,
            "living_room": 1,
            "max_guests": 5,
            "description": "Accogliente appartamento immerso nella tranquillità del borgo marinaro di Trappeto, a pochi passi dal mare cristallino della costa nord-occidentale della Sicilia.",
            "amenities": ["Wi-Fi gratuito", "Aria condizionata", "Cucina attrezzata", "TV", "Lavatrice", "Terrazza"],
        }
        await db.settings.insert_one(info)
    info.pop("_id", None)
    return info


@api.put("/property")
async def update_property(body: PropertyIn, _: str = Depends(get_current_admin)):
    data = body.model_dump()
    await db.settings.update_one({"_id": "property"}, {"$set": data}, upsert=True)
    return data


# ============================================================
# Photos
# ============================================================
@api.get("/photos", response_model=List[PhotoOut])
async def list_photos():
    cur = db.photos.find({}, {"_id": 0}).sort("order", 1)
    items = await cur.to_list(200)
    return items


@api.post("/photos", response_model=PhotoOut)
async def upload_photo(body: PhotoIn, _: str = Depends(get_current_admin)):
    count = await db.photos.count_documents({})
    photo = {
        "id": str(uuid.uuid4()),
        "data_url": body.data_url,
        "filename": body.filename,
        "order": count,
        "created_at": now_utc().isoformat(),
    }
    await db.photos.insert_one(photo)
    photo.pop("_id", None)
    return photo


@api.delete("/photos/{photo_id}")
async def delete_photo(photo_id: str, _: str = Depends(get_current_admin)):
    res = await db.photos.delete_one({"id": photo_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Foto non trovata")
    return {"ok": True}


@api.put("/photos/reorder")
async def reorder_photos(body: PhotoOrderIn, _: str = Depends(get_current_admin)):
    for i, pid in enumerate(body.ids):
        await db.photos.update_one({"id": pid}, {"$set": {"order": i}})
    return {"ok": True}


# ============================================================
# Private photos (Galleria — non visibili al pubblico)
# ============================================================
@api.get("/private-photos", response_model=List[PhotoOut])
async def list_private_photos(_: str = Depends(get_current_admin)):
    cur = db.private_photos.find({}, {"_id": 0}).sort("order", 1)
    return await cur.to_list(500)


@api.post("/private-photos", response_model=PhotoOut)
async def upload_private_photo(body: PhotoIn, _: str = Depends(get_current_admin)):
    count = await db.private_photos.count_documents({})
    photo = {
        "id": str(uuid.uuid4()),
        "data_url": body.data_url,
        "filename": body.filename,
        "order": count,
        "created_at": now_utc().isoformat(),
    }
    await db.private_photos.insert_one(photo)
    photo.pop("_id", None)
    return photo


@api.delete("/private-photos/{photo_id}")
async def delete_private_photo(photo_id: str, _: str = Depends(get_current_admin)):
    res = await db.private_photos.delete_one({"id": photo_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Foto non trovata")
    return {"ok": True}


@api.put("/private-photos/reorder")
async def reorder_private_photos(body: PhotoOrderIn, _: str = Depends(get_current_admin)):
    for i, pid in enumerate(body.ids):
        await db.private_photos.update_one({"id": pid}, {"$set": {"order": i}})
    return {"ok": True}


@api.post("/private-photos/{photo_id}/promote", response_model=PhotoOut)
async def promote_private_photo(photo_id: str, _: str = Depends(get_current_admin)):
    """Sposta una foto dalla galleria privata a quelle pubbliche."""
    src = await db.private_photos.find_one({"id": photo_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Foto non trovata")
    count = await db.photos.count_documents({})
    dst = {
        "id": str(uuid.uuid4()),
        "data_url": src.get("data_url"),
        "filename": src.get("filename"),
        "order": count,
        "created_at": now_utc().isoformat(),
    }
    await db.photos.insert_one(dst)
    await db.private_photos.delete_one({"id": photo_id})
    dst.pop("_id", None)
    return dst


@api.post("/photos/{photo_id}/demote", response_model=PhotoOut)
async def demote_public_photo(photo_id: str, _: str = Depends(get_current_admin)):
    """Sposta una foto pubblica nella galleria privata (nasconde dal sito)."""
    src = await db.photos.find_one({"id": photo_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Foto non trovata")
    count = await db.private_photos.count_documents({})
    dst = {
        "id": str(uuid.uuid4()),
        "data_url": src.get("data_url"),
        "filename": src.get("filename"),
        "order": count,
        "created_at": now_utc().isoformat(),
    }
    await db.private_photos.insert_one(dst)
    await db.photos.delete_one({"id": photo_id})
    dst.pop("_id", None)
    return dst


# ============================================================
# Custom fees
# ============================================================
@api.get("/custom-fees")
async def list_custom_fees():
    cur = db.custom_fees.find({}, {"_id": 0}).sort("name", 1)
    return await cur.to_list(100)


@api.post("/custom-fees")
async def create_custom_fee(body: CustomFeeIn, _: str = Depends(get_current_admin)):
    if body.mode not in ("per_night", "per_stay"):
        raise HTTPException(status_code=400, detail="Modalità non valida")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Nome obbligatorio")
    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name.strip(),
        "amount": body.amount,
        "mode": body.mode,
        "created_at": now_utc().isoformat(),
    }
    await db.custom_fees.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/custom-fees/{fee_id}")
async def update_custom_fee(fee_id: str, body: CustomFeeIn, _: str = Depends(get_current_admin)):
    if body.mode not in ("per_night", "per_stay"):
        raise HTTPException(status_code=400, detail="Modalità non valida")
    res = await db.custom_fees.update_one(
        {"id": fee_id},
        {"$set": {"name": body.name.strip(), "amount": body.amount, "mode": body.mode}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Costo non trovato")
    return {"ok": True}


@api.delete("/custom-fees/{fee_id}")
async def delete_custom_fee(fee_id: str, _: str = Depends(get_current_admin)):
    res = await db.custom_fees.delete_one({"id": fee_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Costo non trovato")
    return {"ok": True}


# ============================================================
# Fees / Settings
# ============================================================
@api.get("/fees")
async def get_fees():
    doc = await db.settings.find_one({"_id": "fees"}, {"_id": 0})
    if not doc:
        doc = FeesIn().model_dump()
    return doc


@api.put("/fees")
async def update_fees(body: FeesIn, _: str = Depends(get_current_admin)):
    data = body.model_dump()
    await db.settings.update_one({"_id": "fees"}, {"$set": data}, upsert=True)
    return data


# ============================================================
# Prices
# ============================================================
@api.get("/prices")
async def get_prices():
    cur = db.price_overrides.find({}, {"_id": 0})
    items = await cur.to_list(2000)
    return items


@api.post("/prices/bulk")
async def bulk_set_prices(body: PriceBulkIn, _: str = Depends(get_current_admin)):
    if not body.dates:
        return {"updated": 0}
    if body.price is None and body.booking_price is None:
        raise HTTPException(status_code=400, detail="Specifica almeno un prezzo")
    update_fields = {}
    if body.price is not None:
        update_fields["price"] = body.price
    if body.booking_price is not None:
        update_fields["booking_price"] = body.booking_price
    for d in body.dates:
        await db.price_overrides.update_one(
            {"date": d},
            {"$set": {"date": d, **update_fields}},
            upsert=True,
        )
    return {"updated": len(body.dates)}


@api.delete("/prices/bulk")
async def bulk_delete_prices(body: PriceBulkIn, _: str = Depends(get_current_admin)):
    # Reset: remove the overrides for those dates entirely (both site + booking)
    res = await db.price_overrides.delete_many({"date": {"$in": body.dates}})
    return {"deleted": res.deleted_count}


# ============================================================
# Discount codes
# ============================================================
@api.get("/discount-codes")
async def list_codes(_: str = Depends(get_current_admin)):
    cur = db.discount_codes.find({}, {"_id": 0}).sort("created_at", -1)
    items = await cur.to_list(500)
    # Ensure backward compat: items without type are treated as discount
    for it in items:
        it.setdefault("type", "discount")
    return items


@api.post("/discount-codes")
async def create_code(body: DiscountCodeIn, _: str = Depends(get_current_admin)):
    code = body.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Codice non valido")
    if body.type not in ("discount", "ai_access"):
        raise HTTPException(status_code=400, detail="Tipo non valido")
    if body.type == "discount" and (body.percent is None or body.percent <= 0):
        raise HTTPException(status_code=400, detail="Percentuale obbligatoria per i codici sconto")
    if body.valid_from > body.valid_to:
        raise HTTPException(status_code=400, detail="Date non valide")
    doc = {
        "id": str(uuid.uuid4()),
        "code": code,
        "type": body.type,
        "percent": body.percent if body.type == "discount" else None,
        "valid_from": body.valid_from,
        "valid_to": body.valid_to,
        "active": body.active,
        "created_at": now_utc().isoformat(),
    }
    try:
        await db.discount_codes.insert_one(doc)
    except Exception:
        raise HTTPException(status_code=400, detail="Codice già esistente")
    doc.pop("_id", None)
    return doc


@api.delete("/discount-codes/expired")
async def delete_expired_codes(_: str = Depends(get_current_admin)):
    today = now_utc().date().isoformat()
    res = await db.discount_codes.delete_many({"valid_to": {"$lt": today}})
    return {"deleted": res.deleted_count}


@api.delete("/discount-codes/{code_id}")
async def delete_code(code_id: str, _: str = Depends(get_current_admin)):
    res = await db.discount_codes.delete_one({"id": code_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Codice non trovato")
    return {"ok": True}


@api.get("/discount-codes/validate/{code}")
async def validate_code(code: str):
    today = now_utc().date().isoformat()
    doc = await db.discount_codes.find_one(
        {"code": code.upper(), "active": True, "type": "discount"}, {"_id": 0}
    )
    # Backward compat: also match codes that have no 'type' field
    if not doc:
        doc = await db.discount_codes.find_one(
            {"code": code.upper(), "active": True, "type": {"$exists": False}}, {"_id": 0}
        )
    if not doc:
        raise HTTPException(status_code=404, detail="Codice non valido")
    if doc["valid_from"] > today or doc["valid_to"] < today:
        raise HTTPException(status_code=400, detail="Codice scaduto o non ancora attivo")
    return doc


# ============================================================
# Availability + Pricing calculation
# ============================================================
async def get_blocked_dates(skip_booking_id: Optional[str] = None) -> set:
    """Dates blocked by approved bookings."""
    blocked = set()
    q = {"status": "approved"}
    if skip_booking_id:
        q["id"] = {"$ne": skip_booking_id}
    cur = db.bookings.find(q, {"_id": 0, "check_in": 1, "check_out": 1})
    async for b in cur:
        ci = date.fromisoformat(b["check_in"])
        co = date.fromisoformat(b["check_out"])
        for d in daterange(ci, co):
            blocked.add(d.isoformat())
    return blocked


@api.get("/availability")
async def availability():
    blocked = await get_blocked_dates()
    prices_cur = db.price_overrides.find({}, {"_id": 0})
    rows = await prices_cur.to_list(2000)
    prices = {p["date"]: p["price"] for p in rows if p.get("price") is not None}
    booking_prices = {p["date"]: p["booking_price"] for p in rows if p.get("booking_price") is not None}
    fees = await db.settings.find_one({"_id": "fees"}, {"_id": 0}) or FeesIn().model_dump()
    return {
        "blocked_dates": sorted(blocked),
        "prices": prices,
        "booking_prices": booking_prices,
        "base_price": fees["base_price_per_night"],
        "base_booking_price": fees.get("base_booking_price_per_night", 0),
        "booking_url": fees.get("booking_url", ""),
    }


async def calculate_quote(check_in: str, check_out: str, guests: int,
                          extras: dict, discount_code: Optional[str]) -> dict:
    ci = date.fromisoformat(check_in)
    co = date.fromisoformat(check_out)
    if co <= ci:
        raise HTTPException(status_code=400, detail="Date non valide")
    nights = (co - ci).days

    fees_doc = await db.settings.find_one({"_id": "fees"}, {"_id": 0}) or FeesIn().model_dump()
    rows_cur = db.price_overrides.find({}, {"_id": 0})
    rows = await rows_cur.to_list(2000)
    prices = {p["date"]: p["price"] for p in rows if p.get("price") is not None}
    booking_prices = {p["date"]: p["booking_price"] for p in rows if p.get("booking_price") is not None}

    base = fees_doc["base_price_per_night"]
    base_b = fees_doc.get("base_booking_price_per_night", 0) or 0

    nightly_total = 0.0
    booking_nightly_total = 0.0
    for d in daterange(ci, co):
        iso = d.isoformat()
        nightly_total += prices.get(iso, base)
        booking_nightly_total += booking_prices.get(iso, base_b)

    extra_guests = max(0, guests - fees_doc["base_guests"])
    extra_guest_fees = extra_guests * fees_doc["extra_person_per_night"] * nights
    ac_fee = fees_doc["ac_per_night"] * nights if (extras or {}).get("ac") else 0
    tourist_tax = fees_doc["tourist_tax_per_person_per_night"] * guests * nights
    cleaning = fees_doc["cleaning_fee"]

    # Custom fees
    custom_fees_cur = db.custom_fees.find({}, {"_id": 0})
    custom_fees = await custom_fees_cur.to_list(100)
    custom_fees_breakdown = []
    custom_fees_total = 0.0
    for cf in custom_fees:
        cost = cf["amount"] * nights if cf["mode"] == "per_night" else cf["amount"]
        custom_fees_total += cost
        custom_fees_breakdown.append({
            "name": cf["name"],
            "amount": cf["amount"],
            "mode": cf["mode"],
            "cost": round(cost, 2),
        })

    subtotal = nightly_total + extra_guest_fees + ac_fee + cleaning + custom_fees_total
    discount_amount = 0.0
    discount_info = None
    if discount_code:
        today = now_utc().date().isoformat()
        dc = await db.discount_codes.find_one(
            {"code": discount_code.upper(), "active": True}, {"_id": 0}
        )
        if dc and dc["valid_from"] <= today <= dc["valid_to"]:
            discount_amount = round(subtotal * dc["percent"] / 100.0, 2)
            discount_info = {"code": dc["code"], "percent": dc["percent"]}

    total = subtotal - discount_amount + tourist_tax

    # Booking total mirrors the site total but uses booking nightly prices and no discount code
    booking_subtotal = booking_nightly_total + extra_guest_fees + ac_fee + cleaning + custom_fees_total
    booking_total = booking_subtotal + tourist_tax if booking_nightly_total > 0 else 0
    savings = round(booking_total - total, 2) if booking_total > 0 else 0

    return {
        "nights": nights,
        "nightly_total": round(nightly_total, 2),
        "booking_nightly_total": round(booking_nightly_total, 2),
        "extra_guest_fees": round(extra_guest_fees, 2),
        "ac_fee": round(ac_fee, 2),
        "cleaning_fee": round(cleaning, 2),
        "custom_fees": custom_fees_breakdown,
        "custom_fees_total": round(custom_fees_total, 2),
        "tourist_tax": round(tourist_tax, 2),
        "subtotal": round(subtotal, 2),
        "discount_amount": round(discount_amount, 2),
        "discount_info": discount_info,
        "total": round(total, 2),
        "booking_total": round(booking_total, 2),
        "savings": savings,
    }


@api.post("/quote")
async def quote(body: BookingIn):
    return await calculate_quote(
        body.check_in, body.check_out, body.guests,
        body.extras or {}, body.discount_code,
    )


# ============================================================
# Bookings
# ============================================================
@api.post("/bookings")
async def create_booking(body: BookingIn):
    # Phone number is required to submit a request
    if not body.guest_phone or not body.guest_phone.strip():
        raise HTTPException(status_code=400, detail="Il numero di telefono è obbligatorio")
    # Validate availability
    blocked = await get_blocked_dates()
    ci = date.fromisoformat(body.check_in)
    co = date.fromisoformat(body.check_out)
    if co <= ci:
        raise HTTPException(status_code=400, detail="Date non valide")
    for d in daterange(ci, co):
        if d.isoformat() in blocked:
            raise HTTPException(status_code=400, detail=f"Data {d.isoformat()} non disponibile")

    quote_data = await calculate_quote(
        body.check_in, body.check_out, body.guests,
        body.extras or {}, body.discount_code,
    )

    doc = {
        "id": str(uuid.uuid4()),
        "guest_name": body.guest_name,
        "guest_email": body.guest_email,
        "guest_phone": body.guest_phone,
        "check_in": body.check_in,
        "check_out": body.check_out,
        "guests": body.guests,
        "extras": body.extras or {},
        "discount_code": body.discount_code,
        "message": body.message,
        "quote": quote_data,
        "source": "site",
        "status": "pending",
        "confirmation_code": None,
        "created_at": now_utc().isoformat(),
    }
    await db.bookings.insert_one(doc)
    doc.pop("_id", None)

    # Fire-and-forget WhatsApp notification
    text = _format_booking_message("📩 NUOVA RICHIESTA DI PRENOTAZIONE", doc)
    asyncio.create_task(send_whatsapp_notification("new_request", text))

    return doc


@api.get("/bookings")
async def list_bookings(_: str = Depends(get_current_admin)):
    cur = db.bookings.find({}, {"_id": 0}).sort("created_at", -1)
    return await cur.to_list(1000)


@api.post("/bookings/{booking_id}/approve")
async def approve_booking(booking_id: str, _: str = Depends(get_current_admin)):
    b = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Prenotazione non trovata")

    # Check no conflict with other approved bookings
    blocked = await get_blocked_dates(skip_booking_id=booking_id)
    ci = date.fromisoformat(b["check_in"])
    co = date.fromisoformat(b["check_out"])
    for d in daterange(ci, co):
        if d.isoformat() in blocked:
            raise HTTPException(
                status_code=400,
                detail=f"Conflitto: la data {d.isoformat()} è già occupata da un'altra prenotazione approvata",
            )

    code = b.get("confirmation_code") or gen_confirmation_code()
    await db.bookings.update_one(
        {"id": booking_id},
        {"$set": {"status": "approved", "confirmation_code": code,
                  "approved_at": now_utc().isoformat()}}
    )
    b["status"] = "approved"
    b["confirmation_code"] = code
    text = _format_booking_message("✅ PRENOTAZIONE APPROVATA", b)
    asyncio.create_task(send_whatsapp_notification("approved", text))
    return {"ok": True, "confirmation_code": code}


@api.post("/bookings/{booking_id}/reject")
async def reject_booking(booking_id: str, _: str = Depends(get_current_admin)):
    b = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Prenotazione non trovata")
    await db.bookings.update_one(
        {"id": booking_id},
        {"$set": {"status": "rejected", "rejected_at": now_utc().isoformat()}}
    )
    b["status"] = "rejected"
    text = _format_booking_message("❌ PRENOTAZIONE RIFIUTATA", b)
    asyncio.create_task(send_whatsapp_notification("rejected", text))
    return {"ok": True}


@api.delete("/bookings/{booking_id}")
async def delete_booking(booking_id: str, _: str = Depends(get_current_admin)):
    b = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    res = await db.bookings.delete_one({"id": booking_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prenotazione non trovata")
    if b:
        text = _format_booking_message("🗑️ PRENOTAZIONE ELIMINATA", b)
        asyncio.create_task(send_whatsapp_notification("deleted", text))
    return {"ok": True}


# ============================================================
# AI Itinerary (locked by confirmation_code)
# ============================================================
@api.post("/ai/itinerary")
async def ai_itinerary(body: ItineraryIn):
    code_clean = body.confirmation_code.strip().upper()
    booking = await db.bookings.find_one(
        {"confirmation_code": code_clean, "status": "approved"},
        {"_id": 0},
    )
    guest_name = booking["guest_name"] if booking else "Ospite"
    nights = 0
    check_in = check_out = guests = None

    if booking:
        nights = (date.fromisoformat(booking["check_out"]) - date.fromisoformat(booking["check_in"])).days
        check_in = booking["check_in"]
        check_out = booking["check_out"]
        guests = booking["guests"]
    else:
        # Try AI access code from codes collection
        today = now_utc().date().isoformat()
        ai_code = await db.discount_codes.find_one(
            {"code": code_clean, "active": True, "type": "ai_access"}, {"_id": 0}
        )
        if not ai_code or ai_code["valid_from"] > today or ai_code["valid_to"] < today:
            raise HTTPException(
                status_code=403,
                detail="Codice di conferma non valido o scaduto. L'itinerario IA è disponibile solo dopo l'approvazione della prenotazione da parte dell'host oppure con un codice di accesso valido.",
            )
        nights = 3  # default suggestion
        check_in = "in arrivo"
        check_out = "in arrivo"
        guests = 2

    system_message = (
        "Sei un esperto concierge turistico siciliano. Crei itinerari di viaggio dettagliati, "
        "caldi e personalizzati per gli ospiti di una casa vacanze a Trappeto (PA), in Sicilia. "
        "Conosci a fondo la zona della costa nord-occidentale: Trappeto, Balestrate, Castellammare del Golfo, "
        "Scopello, Riserva dello Zingaro, San Vito Lo Capo, Erice, Segesta, Palermo, Monreale, Cefalù. "
        "Suggerisci spiagge, ristoranti tipici, percorsi naturalistici, esperienze culturali, mercati e tradizioni. "
        "Scrivi sempre in italiano, in tono ospitale e con una struttura chiara giorno per giorno usando markdown."
    )
    prompt = (
        f"Ospite: {guest_name}\n"
        f"Numero ospiti: {guests}\n"
        f"Soggiorno: dal {check_in} al {check_out} ({nights} notti)\n"
        f"Interessi: {body.interests or 'non specificati'}\n"
        f"Stile di viaggio: {body.travel_style or 'non specificato'}\n\n"
        f"Crea un itinerario completo giorno per giorno, con sezioni: 🌅 Mattina, ☀️ Pomeriggio, 🌙 Sera. "
        f"Includi consigli pratici (parcheggi, distanze in auto da Trappeto), ristoranti consigliati, "
        f"e un'esperienza speciale da non perdere. Concludi con una sezione 'Consigli del locale'."
    )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"itinerary-{code_clean}",
        system_message=system_message,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    async def event_generator():
        try:
            async for ev in chat.stream_message(UserMessage(text=prompt)):
                if isinstance(ev, TextDelta):
                    # SSE format
                    chunk = ev.content.replace("\n", "\\n")
                    yield f"data: {chunk}\n\n"
                elif isinstance(ev, StreamDone):
                    yield "data: [DONE]\n\n"
                    break
        except Exception as e:
            logger.exception("AI itinerary error: %s", e)
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# Carmelo IA v2 — Chat multi-turno + Itinerari pro + Adattamento itinerari esterni
# ============================================================
class CarmeloChatIn(BaseModel):
    session_id: str
    message: str
    model: Optional[str] = "claude"  # claude | openai | gemini


class CarmeloItineraryIn(BaseModel):
    session_id: str
    days: int = 3            # 1-15
    format: str = "free"     # hourly | free
    travelers: Optional[str] = None    # es. "2 adulti + 1 bambino"
    interests: Optional[str] = None
    travel_style: Optional[str] = None
    arrival_date: Optional[str] = None  # YYYY-MM-DD
    notes: Optional[str] = None
    model: Optional[str] = "claude"
    confirmation_code: Optional[str] = None  # facoltativo


class CarmeloAdaptIn(BaseModel):
    session_id: str
    original_text: str       # itinerario incollato
    model: Optional[str] = "claude"
    notes: Optional[str] = None


async def _save_message(session_id: str, role: str, content: str, model: Optional[str] = None):
    await db.carmelo_messages.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": role,
        "content": content,
        "model": model,
        "created_at": now_utc().isoformat(),
    })


@api.get("/carmelo/models")
async def carmelo_list_models():
    """Elenco modelli disponibili per Carmelo."""
    return {
        "models": [
            {"key": k, "label": CARMELO_MODEL_LABELS[k]} for k in CARMELO_MODELS.keys()
        ]
    }


@api.get("/carmelo/messages/{session_id}")
async def carmelo_get_messages(session_id: str):
    """Ritorna lo storico messaggi (per la UI)."""
    cur = db.carmelo_messages.find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("created_at", 1)
    return await cur.to_list(500)


@api.delete("/carmelo/messages/{session_id}")
async def carmelo_clear_messages(session_id: str):
    """Cancella lo storico e la cache in memoria."""
    await db.carmelo_messages.delete_many({"session_id": session_id})
    removed = carmelo_clear_cache(session_id)
    return {"ok": True, "cache_removed": removed}


@api.post("/carmelo/chat")
async def carmelo_chat(body: CarmeloChatIn):
    """Chat conversazionale multi-turno con Carmelo. Streaming SSE."""
    models = carmelo_resolve_models(body.model)
    model_key = models[0]
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Messaggio vuoto")

    system_prompt = carmelo_build_system_prompt(mode="chat")
    chat = carmelo_get_chat(body.session_id, model_key, EMERGENT_LLM_KEY, system_prompt)
    user_text = body.message.strip()

    # Save user message immediately
    await _save_message(body.session_id, "user", user_text, model_key)

    async def gen():
        full = ""
        try:
            async for ev in chat.stream_message(UserMessage(text=user_text)):
                if isinstance(ev, TextDelta):
                    full += ev.content
                    yield carmelo_sse(ev.content, "delta")
                elif isinstance(ev, StreamDone):
                    yield carmelo_sse("", "done")
                    break
        except Exception as e:
            logger.exception("Carmelo chat error: %s", e)
            yield carmelo_sse(str(e)[:300], "error")
        finally:
            if full.strip():
                await _save_message(body.session_id, "assistant", full, model_key)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.post("/carmelo/itinerary")
async def carmelo_itinerary(body: CarmeloItineraryIn):
    """Genera un itinerario completo. Streaming SSE."""
    days = max(1, min(15, int(body.days or 3)))
    fmt = body.format if body.format in ("hourly", "free") else "free"
    models = carmelo_resolve_models(body.model)
    model_key = models[0]

    # Personalizzazione dal profilo prenotazione (se code fornito)
    guest_info = ""
    if body.confirmation_code:
        b = await db.bookings.find_one(
            {"confirmation_code": body.confirmation_code.strip().upper(),
             "status": "approved"}, {"_id": 0}
        )
        if b:
            guest_info = (
                f"Nome ospite: {b.get('guest_name')}, soggiorno "
                f"{b.get('check_in')} → {b.get('check_out')}, {b.get('guests')} ospiti."
            )

    system_prompt = carmelo_build_system_prompt(
        mode="itinerary", days=days, format_style=fmt,
        extra=guest_info or None,
    )
    # Per gli itinerari usa una sessione "itin-<session>-<model>" così non interferisce con la chat
    itin_session = f"itin-{body.session_id}"
    chat = carmelo_get_chat(itin_session, model_key, EMERGENT_LLM_KEY, system_prompt)

    # Limite token più generoso per evitare troncamenti a metà frase
    try:
        chat.with_params(max_tokens=4000)
    except Exception:
        pass

    fmt_label = "ORA-PER-ORA (con orari precisi)" if fmt == "hourly" else "LIBERO (senza orari rigidi)"
    profile = (
        f"- Viaggiatori: {body.travelers or 'non specificato'}\n"
        f"- Interessi: {body.interests or 'mix completo (cultura, mare, cibo, natura)'}\n"
        f"- Stile: {body.travel_style or 'equilibrato'}\n"
        f"- Data arrivo: {body.arrival_date or 'flessibile'}\n"
        f"- Note extra: {body.notes or 'nessuna'}\n"
    )

    # Messaggio utente riepilogativo (per la history/UI)
    summary_user = f"Genera un itinerario di {days} giorni (formato {fmt_label}).\n{profile}"
    await _save_message(itin_session, "user", summary_user, model_key)

    async def _stream_step(text: str):
        """Stream di un singolo step; ritorna il testo accumulato dello step."""
        acc = ""
        async for ev in chat.stream_message(UserMessage(text=text)):
            if isinstance(ev, TextDelta):
                acc += ev.content
                yield ("delta", ev.content)
            elif isinstance(ev, StreamDone):
                break
        yield ("acc", acc)

    async def gen():
        full = ""
        try:
            # 1) Introduzione breve
            intro_prompt = (
                f"Stai creando un itinerario di ESATTAMENTE {days} giorni in formato {fmt_label} "
                f"con questo profilo:\n{profile}\n"
                "Scrivi SOLO una breve introduzione di 2-3 righe (niente titolo '#'), calorosa e siciliana. "
                "NON scrivere ancora nessun giorno."
            )
            async for kind, chunk in _stream_step(intro_prompt):
                if kind == "delta":
                    full += chunk
                    yield carmelo_sse(chunk, "delta")

            # 2) Un giorno alla volta -> garantisce ESATTAMENTE N sezioni "## Giorno"
            for d in range(1, days + 1):
                full += "\n\n"
                yield carmelo_sse("\n\n", "delta")
                day_prompt = (
                    f"Ora scrivi ESCLUSIVAMENTE il Giorno {d} di {days}. "
                    f"Inizia con l'intestazione esatta '## Giorno {d} - <tema del giorno>' (usa proprio '## '). "
                    "Poi le tappe con sezioni ### 🌅 Mattina, ### ☀️ Pomeriggio, ### 🌙 Sera: nomi esatti dei luoghi, "
                    "prezzi indicativi, riduzioni, orari, e un ristorante consigliato col piatto tipico. "
                    "Completo ma conciso (max ~250 parole). "
                    f"NON scrivere altri giorni oltre al Giorno {d}, NON scrivere introduzioni o sezioni finali."
                )
                async for kind, chunk in _stream_step(day_prompt):
                    if kind == "delta":
                        full += chunk
                        yield carmelo_sse(chunk, "delta")

            # 3) Sezioni finali
            full += "\n\n"
            yield carmelo_sse("\n\n", "delta")
            final_prompt = (
                "Ora scrivi SOLO le sezioni finali dell'itinerario, senza ripetere i giorni:\n"
                "1) '## 🍝 Ristoranti consigliati' con 4-6 ristoranti del territorio (nome, zona, piatto tipico, prezzo indicativo).\n"
                "2) '## 💡 Consigli pratici' (parcheggi, ZTL, biglietti online, scarpe comode, orari migliori, stagionalità).\n"
                "3) '## 📞 Bisogno di aiuto?' con i contatti della casa vacanze Appartamento Matteo."
            )
            async for kind, chunk in _stream_step(final_prompt):
                if kind == "delta":
                    full += chunk
                    yield carmelo_sse(chunk, "delta")

            yield carmelo_sse("", "done")
        except Exception as e:
            logger.exception("Carmelo itinerary error: %s", e)
            yield carmelo_sse(str(e)[:300], "error")
        finally:
            if full.strip():
                await _save_message(itin_session, "assistant", full, model_key)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ItineraryPdfIn(BaseModel):
    content: str
    title: Optional[str] = None
    days: Optional[int] = None


@api.post("/carmelo/itinerary/pdf")
async def carmelo_itinerary_pdf(body: ItineraryPdfIn):
    """Genera un PDF elegante dell'itinerario (logo + info Appartamento Matteo)."""
    text = (body.content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Contenuto itinerario vuoto")
    try:
        pdf_bytes = build_itinerary_pdf(text, title=body.title, days=body.days)
    except Exception as e:
        logger.exception("Itinerary PDF error: %s", e)
        raise HTTPException(status_code=500, detail=f"Errore generazione PDF: {e}")
    filename = "itinerario-appartamento-matteo.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================
# Itinerario SCHEMATICO (strutturato con immagini)
# ============================================================
class StructuredItineraryIn(BaseModel):
    session_id: str
    model: str = "claude"
    days: int = 3
    format: str = "free"
    travelers: Optional[str] = ""
    interests: Optional[str] = ""
    travel_style: Optional[str] = ""
    arrival_date: Optional[str] = None
    notes: Optional[str] = ""
    confirmation_code: Optional[str] = None


class StructuredPdfIn(BaseModel):
    itinerary: dict
    title: Optional[str] = None


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower().strip() if ch.isalnum() or ch == " ").strip()


async def _enrich_structured(data: dict, days: int) -> dict:
    """Arricchisce l'itinerario strutturato con i dati dei POI e le immagini."""
    pois = await db.pois.find({}, {"_id": 0}).to_list(1000)
    by_name = {}
    for p in pois:
        by_name[_norm(p.get("name"))] = p

    def match_poi(name: str):
        key = _norm(name)
        if key in by_name:
            return by_name[key]
        # match parziale
        for k, p in by_name.items():
            if key and (key in k or k in key):
                return p
        return None

    def gmaps_from_latlng(lat, lng, name=None):
        if lat is None or lng is None:
            return ""
        if name:
            q = urlquote(name)
            return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}&query_place_id=&query_name={q}"
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

    def gmaps_from_query(name: str, address: str = "", town: str = ""):
        """Fallback: costruisce un search Google Maps dal nome + eventuale via/città."""
        parts = [p for p in [name, address, town, "Sicilia"] if p]
        query = ", ".join(parts)
        return f"https://www.google.com/maps/search/?api=1&query={urlquote(query)}"

    days_list = data.get("days") or []
    # Garantisce ESATTAMENTE N giorni
    days_list = days_list[:days]

    # 1) Enrichment SINCRONO dei campi (dati POI) + raccolta job immagini
    all_stops = []
    for day in days_list:
        for stop in (day.get("stops") or []):
            name = stop.get("name") or ""
            poi = match_poi(name)
            if poi:
                town = poi.get("town") or ""
                prov = poi.get("province") or ""
                loc = town + (f" ({prov})" if prov else "")
                stop["location"] = stop.get("location") or loc or "Sicilia nord-occidentale"
                stop["hours"] = poi.get("hours") or stop.get("hours") or "Verifica orari sul sito ufficiale"
                stop["cost"] = poi.get("price") or stop.get("cost") or "Ingresso indicativo — verifica"
                stop["duration"] = poi.get("duration") or stop.get("duration") or "1–2 ore"
                stop["category"] = poi.get("category") or "art"
                if not stop.get("description"):
                    stop["description"] = poi.get("description") or ""
                # Address (via) — se il POI non ce l'ha, lascia quello che ha proposto l'AI
                stop["address"] = stop.get("address") or ""
                # lat/lng dal POI (per mini-mappa e riordino nearest-neighbor)
                if poi.get("lat") is not None and poi.get("lng") is not None:
                    stop["lat"] = poi.get("lat")
                    stop["lng"] = poi.get("lng")
                # Google Maps URL: POI se disponibile, altrimenti genera da lat/lng
                stop["maps_url"] = poi.get("maps_url") or gmaps_from_latlng(poi.get("lat"), poi.get("lng"), poi.get("name")) or stop.get("maps_url") or ""
                # Ticket URL: POI se disponibile, altrimenti l'AI può averlo aggiunto
                stop["ticket_url"] = poi.get("ticket_url") or stop.get("ticket_url") or ""
                stop["_poi"] = poi
            else:
                stop.setdefault("location", "Sicilia nord-occidentale")
                stop.setdefault("hours", "Verifica orari sul sito ufficiale")
                stop.setdefault("cost", "Ingresso indicativo — verifica")
                stop.setdefault("duration", "1–2 ore")
                stop.setdefault("address", "")
                # Fallback maps_url anche per tappe non-catalogo (search query)
                if not stop.get("maps_url"):
                    stop["maps_url"] = gmaps_from_query(stop.get("name") or "", stop.get("address") or "", stop.get("location") or "")
                stop.setdefault("ticket_url", "")
                stop["category"] = stop.get("category") or "art"
                stop["_poi"] = None
            all_stops.append(stop)

    # 1.b) Riordino intelligente delle tappe per giorno (nearest-neighbor)
    # Mantiene la prima tappa come "punto di partenza" e riordina le successive per prossimità
    # (percorso pedonale/logico: A più vicino a B, B più vicino a C, ecc.)
    import math

    def _haversine_km(a_lat, a_lng, b_lat, b_lng):
        R = 6371.0
        p1 = math.radians(a_lat); p2 = math.radians(b_lat)
        dp = math.radians(b_lat - a_lat); dl = math.radians(b_lng - a_lng)
        h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * R * math.asin(math.sqrt(h))

    for day in days_list:
        stops = day.get("stops") or []
        if len(stops) < 3:
            continue  # nessun riordino necessario per 0/1/2 tappe
        geo = [s for s in stops if isinstance(s.get("lat"), (int, float)) and isinstance(s.get("lng"), (int, float))]
        no_geo = [s for s in stops if s not in geo]
        if len(geo) < 3:
            continue
        # Nearest-neighbor: parti dalla prima tappa scelta dall'AI (di solito è la "mattina")
        ordered = [geo[0]]
        remaining = geo[1:]
        while remaining:
            last = ordered[-1]
            nxt = min(remaining, key=lambda s: _haversine_km(last["lat"], last["lng"], s["lat"], s["lng"]))
            ordered.append(nxt)
            remaining.remove(nxt)
        # Ri-etichetta i time slot (Mattina/Pomeriggio/Sera) in base al nuovo ordine
        slots = ["Mattina", "Pomeriggio", "Sera"]
        for i, s in enumerate(ordered):
            if i < len(slots):
                # aggiorna solo se il campo esiste già (rispetta l'AI se ha usato altro)
                if s.get("time"):
                    s["time"] = slots[i]
        # ricompone: tappe geolocalizzate riordinate + eventuali senza coordinate in fondo
        day["stops"] = ordered + no_geo

    # 2) Risoluzione immagini in PARALLELO (dedup per chiave POI/nome)
    sem = asyncio.Semaphore(8)
    cache_updates = {}

    async with httpx.AsyncClient() as client:
        async def resolve_for(idx, stop):
            poi = stop.get("_poi")
            name = (poi.get("name") if poi else stop.get("name")) or ""
            category = (poi.get("category") if poi else stop.get("category")) or "art"
            existing = poi.get("image_url") if poi else None
            async with sem:
                img = await poi_images.resolve_image(client, name, category, existing=existing, seed=idx)
            stop["image"] = img
            if poi and img and not existing and img != poi_images.DEFAULT_IMAGE and "unsplash" not in img:
                cache_updates[poi.get("id")] = img

        await asyncio.gather(*[resolve_for(i, s) for i, s in enumerate(all_stops)])

    # 3) Cache immagini sui POI (best effort)
    for pid, img in cache_updates.items():
        try:
            await db.pois.update_one({"id": pid}, {"$set": {"image_url": img}})
        except Exception:
            pass

    # pulizia campo interno
    for stop in all_stops:
        stop.pop("_poi", None)

    data["days"] = days_list
    return data


def _fresh_chat(session_id: str, model_key: str, system_prompt: str, max_tokens: int = 3000):
    provider, model_name = CARMELO_MODELS[model_key]
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id,
                   system_message=system_prompt).with_model(provider, model_name)
    try:
        chat.with_params(max_tokens=max_tokens)
    except Exception:
        pass
    return chat


@api.post("/carmelo/itinerary/structured")
async def carmelo_itinerary_structured(body: StructuredItineraryIn):
    """Genera un itinerario SCHEMATICO strutturato (JSON) con immagini per ogni attrazione.
    Strategia scalabile: 1 call 'outline' veloce + espansione dei giorni IN PARALLELO."""
    days = max(1, min(15, int(body.days or 3)))
    model_key = carmelo_resolve_models(body.model)[0]

    pois = await db.pois.find({}, {"_id": 0}).to_list(1000)
    catalog_lines = []
    for p in pois:
        loc = (p.get("town") or "")
        if p.get("province"):
            loc += f" ({p['province']})"
        desc = (p.get("description") or "").strip()
        catalog_lines.append(f"- {p.get('name')} [{p.get('category')}, {loc}]")
    catalog = "\n".join(catalog_lines)

    system_prompt = carmelo_build_system_prompt(mode="itinerary", days=days, format_style=body.format)
    session = f"struct-{body.session_id}"

    profile = (
        f"- Viaggiatori: {body.travelers or 'non specificato'}\n"
        f"- Interessi: {body.interests or 'mix (cultura, mare, natura, cibo)'}\n"
        f"- Stile: {body.travel_style or 'equilibrato'}\n"
        f"- Data arrivo: {body.arrival_date or 'flessibile'}\n"
        f"- Note: {body.notes or 'nessuna'}\n"
    )

    # ---- STEP 1: OUTLINE (veloce) ----
    outline_prompt = (
        f"Costruisci lo SCHEMA di un itinerario di ESATTAMENTE {days} giorni intorno a Trappeto (Sicilia NO).\n"
        f"Profilo ospite:\n{profile}\n"
        "SELEZIONA le tappe SOLO da questo catalogo (usa i NOMI ESATTI):\n"
        f"{catalog}\n\n"
        "Rispondi SOLO con JSON valido:\n"
        "{\n"
        '  "title": "titolo accattivante",\n'
        '  "intro": "2-3 righe di introduzione calorosa",\n'
        '  "restaurants": [{"name":"","area":"","dish":"piatto tipico","price":"prezzo indicativo"}],\n'
        '  "tips": ["consiglio 1","consiglio 2","consiglio 3"],\n'
        '  "days": [{"day":1,"theme":"tema del giorno","stops":["Nome esatto 1","Nome esatto 2","Nome esatto 3"]}]\n'
        "}\n\n"
        f"REGOLE: 'days' deve avere ESATTAMENTE {days} oggetti (day 1..{days}). Ogni giorno 2-3 tappe vicine "
        "geograficamente. Usa SOLO nomi del catalogo. In 'stops' metti SOLO i nomi (stringhe)."
    )

    try:
        outline_chat = _fresh_chat(f"{session}-outline", model_key, system_prompt, max_tokens=2500)
        raw = await mkt_send_message(outline_chat, outline_prompt)
        outline = mkt_extract_json(raw)
        if not outline or not isinstance(outline.get("days"), list):
            raise HTTPException(status_code=502, detail="Risposta AI non valida")

        odays = outline["days"][:days]
        # normalizza stops in liste di nomi
        for od in odays:
            stops = od.get("stops") or []
            names = []
            for s in stops:
                if isinstance(s, str):
                    names.append(s)
                elif isinstance(s, dict) and s.get("name"):
                    names.append(s["name"])
            od["_names"] = names[:4]

        # ---- STEP 2: espansione giorni IN PARALLELO ----
        sem = asyncio.Semaphore(4)

        async def expand_day(od):
            day_n = od.get("day")
            theme = od.get("theme") or ""
            names = od.get("_names") or []
            if not names:
                return {"day": day_n, "theme": theme, "stops": []}
            prompt = (
                f"Giorno {day_n} — tema: \"{theme}\". Espandi QUESTE tappe (usa ESATTAMENTE questi nomi, "
                f"stesso ordine geografico sensato): {names}.\n"
                "Rispondi SOLO con JSON: {\"stops\":[{\"name\":\"\",\"time\":\"Mattina|Pomeriggio|Sera\","
                "\"description\":\"conciso, max 40 parole, perché vale la visita + eventuale nota ZTL/parcheggio se rilevante\","
                "\"address\":\"via/piazza precisa se la conosci (es. Piazza del Duomo, Palermo)\","
                "\"hours\":\"orari indicativi\",\"cost\":\"costo biglietto indicativo e conciso (es. \\u20ac7, rid. \\u20ac5; o Gratis)\","
                "\"duration\":\"durata visita (es. 1-2 ore)\","
                "\"ticket_url\":\"URL ufficiale per acquistare biglietti se esiste (es. https://... del sito ufficiale, di Coopculture, TicketOne, del comune, ecc.). Stringa vuota se non esiste un canale ufficiale.\"}]}\n"
                "Usa la tua conoscenza reale (valori INDICATIVI). Per ticket_url NON inventare URL: se non conosci il sito ufficiale, lascia stringa vuota. "
                "NON aggiungere il campo location né maps_url (li aggiungo io)."
            )
            async with sem:
                try:
                    dchat = _fresh_chat(f"{session}-d{day_n}", model_key, system_prompt, max_tokens=1800)
                    dr = await mkt_send_message(dchat, prompt)
                    dj = mkt_extract_json(dr) or {}
                    stops = dj.get("stops") if isinstance(dj.get("stops"), list) else None
                except Exception as e:
                    logger.warning("expand day %s failed: %s", day_n, e)
                    stops = None
            if not stops:
                stops = [{"name": n, "time": "", "description": ""} for n in names]
            return {"day": day_n, "theme": theme, "stops": stops}

        expanded = await asyncio.gather(*[expand_day(od) for od in odays])
        expanded.sort(key=lambda d: d.get("day") or 0)

        data = {
            "title": outline.get("title") or f"Itinerario di {days} giorni in Sicilia",
            "intro": outline.get("intro") or "",
            "restaurants": outline.get("restaurants") or [],
            "tips": outline.get("tips") or [],
            "days": expanded,
        }

        data = await _enrich_structured(data, days)
        data["days_count"] = len(data.get("days") or [])

        await _save_message(session, "assistant", json.dumps(data)[:12000], model_key)
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Structured itinerary error: %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:300])


# ---- Chat-driven itinerary patch ----
class ItineraryPatchIn(BaseModel):
    session_id: str
    model: str = "claude"
    itinerary: dict
    message: str
    history: Optional[List[dict]] = None  # [{role, content}, ...]


def _prune_for_prompt(itin: dict) -> dict:
    """Rimuove i data URL delle immagini (base64) prima di inviare al modello."""
    if not isinstance(itin, dict):
        return {}
    slim = {
        "title": itin.get("title") or "",
        "intro": itin.get("intro") or "",
        "restaurants": itin.get("restaurants") or [],
        "tips": itin.get("tips") or [],
        "days": [],
    }
    for d in (itin.get("days") or []):
        stops = []
        for s in (d.get("stops") or []):
            s_copy = {k: v for k, v in s.items() if k != "image" or (isinstance(v, str) and not v.startswith("data:"))}
            # se image è data URL, indica che c'è ma non passarla al modello
            if isinstance(s.get("image"), str) and s["image"].startswith("data:"):
                s_copy["image"] = "<uploaded>"
            stops.append(s_copy)
        slim["days"].append({
            "day": d.get("day"),
            "theme": d.get("theme") or "",
            "stops": stops,
        })
    return slim


@api.post("/carmelo/itinerary/patch")
async def carmelo_itinerary_patch(body: ItineraryPatchIn):
    """Modifica un itinerario esistente in base a una richiesta in linguaggio naturale.

    Il modello riceve l'itinerario attuale + la richiesta dell'utente e restituisce:
    - itinerary: la NUOVA versione completa dell'itinerario
    - reply: una breve frase conversazionale che descrive la modifica
    """
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Messaggio vuoto")
    if not body.itinerary or not isinstance(body.itinerary, dict):
        raise HTTPException(status_code=400, detail="Itinerario mancante")

    model_key = carmelo_resolve_models(body.model)[0]
    session = f"patch-{body.session_id}"

    slim = _prune_for_prompt(body.itinerary)

    history_txt = ""
    if body.history:
        last = body.history[-6:]  # ultimi 6 turni
        for m in last:
            r = "Utente" if m.get("role") == "user" else "Carmelo"
            c = (m.get("content") or "").strip()[:400]
            if c:
                history_txt += f"{r}: {c}\n"

    system = (
        "Sei Carmelo, un concierge digitale esperto della Sicilia nord-occidentale (Palermo/Trapani). "
        "Modifichi un itinerario JSON esistente in base alle richieste dell'utente. "
        "Puoi: cambiare foto (imposta 'image' a un URL affidabile), aggiungere/rimuovere/riordinare tappe e giorni, "
        "aggiornare qualsiasi campo (name, description, address, hours, cost, duration, ticket_url, maps_url, time), "
        "aggiungere info su ZTL, parcheggi, orari speciali, sconti, note pratiche nella 'description', "
        "aggiungere link ufficiali per i biglietti (ticket_url) e Google Maps (maps_url). "
        "REGOLE FONDAMENTALI:\n"
        "1) Ritorna SOLO JSON valido (nessun testo prima/dopo).\n"
        "2) L'oggetto deve avere questa forma: { \"itinerary\": {...}, \"reply\": \"breve frase in italiano che descrive le modifiche fatte\" }\n"
        "3) In 'itinerary' preserva TUTTI i campi esistenti e modifica SOLO ciò che l'utente chiede.\n"
        "4) Non toccare le foto già presenti (image) a meno che non venga chiesto esplicitamente.\n"
        "5) Se l'utente chiede una modifica ambigua, fai la migliore interpretazione e spiega in 'reply'.\n"
        "6) Se aggiungi una tappa nuova: inserisci name, time, description, address, hours, cost, duration, "
        "ticket_url (se conosci il sito ufficiale, altrimenti \"\"), maps_url (URL google maps con la query del luogo).\n"
        "7) NON inventare ticket_url o maps_url se non sei sicuro: usa stringa vuota.\n"
        "8) 'reply' deve essere breve (max 200 caratteri), in italiano, tono cordiale."
    )

    prompt = (
        (f"CONTESTO CONVERSAZIONE PRECEDENTE:\n{history_txt}\n" if history_txt else "")
        + "ITINERARIO ATTUALE (JSON):\n"
        + json.dumps(slim, ensure_ascii=False)
        + "\n\nRICHIESTA UTENTE:\n"
        + body.message.strip()
        + "\n\nRispondi SOLO con l'oggetto JSON { itinerary, reply } come descritto."
    )

    try:
        chat = _fresh_chat(session, model_key, system, max_tokens=5000)
        raw = await mkt_send_message(chat, prompt)
        parsed = mkt_extract_json(raw)
        if not parsed or not isinstance(parsed, dict) or not parsed.get("itinerary"):
            raise HTTPException(status_code=502, detail="Risposta AI non valida — riprova con una richiesta più specifica")

        new_itin = parsed["itinerary"]
        reply = (parsed.get("reply") or "").strip()[:300] or "Fatto."

        # Post-processing: preserva immagini utente e arricchisce le tappe nuove
        try:
            orig_days = body.itinerary.get("days") or []
            new_days = new_itin.get("days") or []

            # Set di (dayIdx, name.lower()) delle tappe originali per identificare le nuove
            orig_stop_names = set()
            for i, od in enumerate(orig_days):
                for os_ in (od.get("stops") or []):
                    n = (os_.get("name") or "").strip().lower()
                    if n:
                        orig_stop_names.add((i, n))

            # Carica POI e prepara matcher (solo se ci sono nuove tappe potenziali)
            pois_cache = None

            def match_poi(name_txt: str, pois_list):
                key = _norm(name_txt)
                by_name = {_norm(p.get("name")): p for p in pois_list}
                if key in by_name:
                    return by_name[key]
                for k, p in by_name.items():
                    if key and (key in k or k in key):
                        return p
                return None

            def gmaps_from_query(name_txt: str, address: str = "", town: str = ""):
                parts = [p for p in [name_txt, address, town, "Sicilia"] if p]
                query = ", ".join(parts)
                return f"https://www.google.com/maps/search/?api=1&query={urlquote(query)}"

            # Raccolta tappe nuove/senza immagine da arricchire
            new_stops_to_enrich = []
            for i, day in enumerate(new_days):
                orig_day = orig_days[i] if i < len(orig_days) else {}
                orig_stops = orig_day.get("stops") or []
                for j, stop in enumerate(day.get("stops") or []):
                    stop_name_lc = (stop.get("name") or "").strip().lower()

                    # Preserva image se il modello l'ha "dimenticata"
                    if isinstance(stop.get("image"), str) and stop["image"].strip() in ("<uploaded>", ""):
                        orig_stop = orig_stops[j] if j < len(orig_stops) else None
                        if orig_stop and orig_stop.get("image") and (orig_stop.get("name") or "").strip().lower() == stop_name_lc:
                            stop["image"] = orig_stop["image"]

                    # Tappa nuova? (nome non presente in nessun giorno originale con stesso indice)
                    is_new = (i, stop_name_lc) not in orig_stop_names

                    if is_new:
                        # Match con POI catalogo per arricchimento sincrono
                        if pois_cache is None:
                            pois_cache = await db.pois.find({}, {"_id": 0}).to_list(1000)
                        poi = match_poi(stop.get("name") or "", pois_cache) if pois_cache else None
                        if poi:
                            town = poi.get("town") or ""
                            prov = poi.get("province") or ""
                            loc = town + (f" ({prov})" if prov else "")
                            if not stop.get("location"): stop["location"] = loc or "Sicilia nord-occidentale"
                            if not stop.get("hours"): stop["hours"] = poi.get("hours") or "Verifica orari sul sito ufficiale"
                            if not stop.get("cost"): stop["cost"] = poi.get("price") or "Ingresso indicativo — verifica"
                            if not stop.get("duration"): stop["duration"] = poi.get("duration") or "1–2 ore"
                            if not stop.get("description"): stop["description"] = poi.get("description") or ""
                            if not stop.get("ticket_url"): stop["ticket_url"] = poi.get("ticket_url") or ""
                            if not stop.get("maps_url"):
                                if poi.get("maps_url"):
                                    stop["maps_url"] = poi["maps_url"]
                                elif poi.get("lat") is not None and poi.get("lng") is not None:
                                    stop["maps_url"] = f"https://www.google.com/maps/search/?api=1&query={poi.get('lat')},{poi.get('lng')}"
                            stop["category"] = poi.get("category") or stop.get("category") or "art"
                            # Se non ha ancora un'immagine, marca per arricchimento
                            if not stop.get("image"):
                                new_stops_to_enrich.append((stop, poi))
                        else:
                            # Default fallback per campi mancanti
                            stop.setdefault("hours", "Verifica orari sul sito ufficiale")
                            stop.setdefault("cost", "Ingresso indicativo — verifica")
                            stop.setdefault("duration", "1–2 ore")
                            stop.setdefault("category", "art")
                            if not stop.get("image"):
                                new_stops_to_enrich.append((stop, None))

                    # Auto-genera maps_url se ancora mancante
                    if not (stop.get("maps_url") or "").strip():
                        stop["maps_url"] = gmaps_from_query(stop.get("name") or "", stop.get("address") or "", stop.get("location") or "")

            # Enrichment immagini in parallelo per le tappe nuove
            if new_stops_to_enrich:
                sem = asyncio.Semaphore(4)
                async with httpx.AsyncClient() as http_client:
                    async def resolve_image_for(stop, poi):
                        name = (poi.get("name") if poi else stop.get("name")) or ""
                        category = (poi.get("category") if poi else stop.get("category")) or "art"
                        existing = poi.get("image_url") if poi else None
                        async with sem:
                            try:
                                img = await poi_images.resolve_image(http_client, name, category, existing=existing, seed=0)
                                stop["image"] = img or ""
                            except Exception as e:
                                logger.warning("resolve image failed for %s: %s", name, e)
                    await asyncio.gather(*[resolve_image_for(s, p) for s, p in new_stops_to_enrich])
        except Exception as e:
            logger.warning("patch post-processing error: %s", e)

        # Aggiorna days_count
        new_itin["days_count"] = len(new_itin.get("days") or [])

        await _save_message(session, "user", body.message.strip()[:2000], model_key)
        await _save_message(session, "assistant", reply[:1000], model_key)

        return {"itinerary": new_itin, "reply": reply}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Itinerary patch error: %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:300])




@api.post("/carmelo/itinerary/structured/pdf")
async def carmelo_itinerary_structured_pdf(body: StructuredPdfIn):
    """PDF schematico dall'itinerario strutturato (con immagini)."""
    itin = body.itinerary or {}
    if not itin.get("days"):
        raise HTTPException(status_code=400, detail="Itinerario vuoto")
    try:
        from itinerary_pdf import build_structured_pdf
        pdf_bytes = build_structured_pdf(itin, title=body.title)
    except Exception as e:
        logger.exception("Structured PDF error: %s", e)
        raise HTTPException(status_code=500, detail=f"Errore PDF: {e}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="itinerario-appartamento-matteo.pdf"'},
    )




@api.post("/carmelo/adapt-itinerary")
async def carmelo_adapt_itinerary(body: CarmeloAdaptIn):
    """Adatta un itinerario esterno (testo già estratto), arricchendolo coi contatti e info locali."""
    text = (body.original_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Itinerario originale vuoto")
    if len(text) > 60000:
        text = text[:60000]

    model_key = carmelo_resolve_models(body.model)[0]
    system_prompt = carmelo_build_system_prompt(mode="adapt", extra=body.notes)
    adapt_session = f"adapt-{body.session_id}"
    chat = carmelo_get_chat(adapt_session, model_key, EMERGENT_LLM_KEY, system_prompt)

    user_prompt = (
        "Ecco l'itinerario originale dell'ospite. Adattalo arricchendolo con prezzi indicativi, "
        "orari, riduzioni, ristoranti, distanze da Trappeto e i contatti della casa vacanze.\n\n"
        "=== INIZIO ITINERARIO ORIGINALE ===\n"
        f"{text}\n"
        "=== FINE ITINERARIO ORIGINALE ==="
    )

    await _save_message(adapt_session, "user", "[ITINERARIO ESTERNO CARICATO]", model_key)

    async def gen():
        full = ""
        try:
            async for ev in chat.stream_message(UserMessage(text=user_prompt)):
                if isinstance(ev, TextDelta):
                    full += ev.content
                    yield carmelo_sse(ev.content, "delta")
                elif isinstance(ev, StreamDone):
                    yield carmelo_sse("", "done")
                    break
        except Exception as e:
            logger.exception("Carmelo adapt error: %s", e)
            yield carmelo_sse(str(e)[:300], "error")
        finally:
            if full.strip():
                await _save_message(adapt_session, "assistant", full, model_key)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.post("/carmelo/extract-file")
async def carmelo_extract_file(file: UploadFile = File(...)):
    """Estrae testo da un file PDF/DOCX/TXT caricato. Ritorna { text }."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Nessun file ricevuto")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File troppo grande (max 10 MB)")
    try:
        text = carmelo_extract_text(file.filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Impossibile estrarre testo dal file")
    return {"filename": file.filename, "text": text[:60000], "chars": len(text)}



# ============================================================
# Verify code (public) — shared validation for map + itinerary
# ============================================================
@api.post("/verify-code")
async def verify_code(body: VerifyCodeIn):
    """Validate a confirmation code. Accepts either:
       - a confirmation_code of an approved booking, OR
       - an active 'ai_access' code from discount_codes (valid for today).
       Returns booking info on success, 403 otherwise.
    """
    code_clean = (body.code or "").strip().upper()
    if not code_clean:
        raise HTTPException(status_code=400, detail="Codice mancante")

    booking = await db.bookings.find_one(
        {"confirmation_code": code_clean, "status": "approved"},
        {"_id": 0},
    )
    if booking:
        return {
            "valid": True,
            "kind": "booking",
            "guest_name": booking.get("guest_name"),
            "check_in": booking.get("check_in"),
            "check_out": booking.get("check_out"),
        }

    # Master / AI-access unlock code (from discount_codes, type "ai_access")
    today = now_utc().date().isoformat()
    ai = await db.discount_codes.find_one(
        {"code": code_clean, "active": True, "type": "ai_access"}, {"_id": 0}
    )
    if ai and ai.get("valid_from", "") <= today <= ai.get("valid_to", ""):
        return {"valid": True, "kind": "ai_access"}

    raise HTTPException(status_code=403, detail="Codice non valido o scaduto.")



# ============================================================
# Carmelo Content — FAQ + Itinerari PDF + Domande ospiti
# Storage PDF locali in /app/backend/uploads/itineraries
# ============================================================
UPLOAD_DIR_ITINERARIES = ROOT_DIR / "uploads" / "itineraries"
UPLOAD_DIR_ITINERARIES.mkdir(parents=True, exist_ok=True)


def _faq_for_public(doc: dict, lang: str) -> dict:
    """Serializza FAQ per il pubblico nella lingua richiesta."""
    translations = doc.get("translations") or {}
    txt = get_text_for_lang(translations, lang, doc.get("question_it", ""), doc.get("answer_it", ""))
    return {
        "id": doc.get("id"),
        "category": doc.get("category"),
        "question": txt["question"],
        "answer": txt["answer"],
        "language": lang if (lang == "it" or translations.get(lang)) else "it",
        "translation_fallback": lang != "it" and not translations.get(lang),
        "keywords": doc.get("keywords", []),
        "priority": doc.get("priority", 0),
        "published": doc.get("published", False),
        "updated_at": doc.get("updated_at"),
    }


def _itin_for_public(doc: dict, full: bool = False) -> dict:
    """Serializza un itinerario per il pubblico."""
    return {
        "id": doc.get("id"),
        "slug": doc.get("slug"),
        "title": doc.get("title"),
        "subtitle": doc.get("subtitle"),
        "days": doc.get("days", 1),
        "theme": doc.get("theme"),
        "hero_image": doc.get("hero_image"),
        "preview_text": doc.get("preview_text"),
        "tags": doc.get("tags", []),
        "visibility": doc.get("visibility", "code_only"),
        "has_pdf": bool(doc.get("pdf_filename")),
        "published": doc.get("published", False),
        "highlights": doc.get("highlights", []) if full else None,
        "updated_at": doc.get("updated_at"),
    }


async def _is_valid_unlock_code(code: str) -> bool:
    """True se code è una booking confermata o un ai_access code attivo."""
    if not code:
        return False
    c = code.strip().upper()
    if not c:
        return False
    if await db.bookings.find_one({"confirmation_code": c, "status": "approved"}):
        return True
    today = now_utc().date().isoformat()
    ai = await db.discount_codes.find_one(
        {"code": c, "active": True, "type": "ai_access"}, {"_id": 0}
    )
    if ai and ai.get("valid_from", "") <= today <= ai.get("valid_to", ""):
        return True
    return False


# ============================================================
# Models
# ============================================================
class FaqIn(BaseModel):
    category: str
    question_it: str
    answer_it: Optional[str] = ""
    keywords: Optional[List[str]] = []
    priority: Optional[int] = 0
    published: Optional[bool] = False


class FaqTranslateIn(BaseModel):
    target_lang: str


class GuestQuestionIn(BaseModel):
    name: str
    contact: str
    contact_kind: Optional[str] = "email"
    message: str
    language: Optional[str] = "it"


class GuestQuestionAdminUpdate(BaseModel):
    status: Optional[str] = None
    answer: Optional[str] = None


class GuestQuestionPromoteIn(BaseModel):
    category: str
    question_it: str
    answer_it: str
    publish: Optional[bool] = True


class ItineraryIn(BaseModel):
    title: str
    subtitle: Optional[str] = ""
    days: int = 3
    theme: Optional[str] = ""
    hero_image: Optional[str] = ""
    preview_text: Optional[str] = ""
    highlights: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    visibility: str = "code_only"
    published: Optional[bool] = False


# ============================================================
# PUBLIC: FAQ categories list
# ============================================================
@api.get("/faqs/categories")
async def list_faq_categories():
    return {"categories": FAQ_CATEGORIES}


# ============================================================
# PUBLIC: FAQ list with search and language filter
# ============================================================
@api.get("/faqs")
async def list_public_faqs(
    lang: str = "it",
    category: Optional[str] = None,
    q: Optional[str] = None,
):
    lang = lang if lang in SUPPORTED_LANGS else "it"
    flt: dict = {"published": True}
    if category:
        flt["category"] = category
    cur = db.carmelo_faqs.find(flt, {"_id": 0}).sort([("priority", -1), ("category", 1)])
    docs = await cur.to_list(500)
    if q:
        docs = content_search_faqs(docs, q, lang)
    return {"faqs": [_faq_for_public(d, lang) for d in docs], "count": len(docs)}


# ============================================================
# PUBLIC: guest question submit
# ============================================================
@api.post("/guest-questions")
async def submit_guest_question(body: GuestQuestionIn):
    if not body.name.strip() or not body.message.strip() or not body.contact.strip():
        raise HTTPException(status_code=400, detail="Campi obbligatori mancanti")
    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name.strip()[:120],
        "contact": body.contact.strip()[:200],
        "contact_kind": (body.contact_kind or "email").lower(),
        "message": body.message.strip()[:4000],
        "language": body.language or "it",
        "status": "open",
        "answer": None,
        "created_at": now_utc().isoformat(),
        "answered_at": None,
        "promoted_to_faq_id": None,
    }
    await db.carmelo_guest_questions.insert_one(doc)
    return {"ok": True, "id": doc["id"]}


# ============================================================
# PUBLIC: itineraries library
# ============================================================
@api.get("/itineraries")
async def list_public_itineraries(lang: str = "it"):
    cur = db.carmelo_itineraries.find(
        {"published": True}, {"_id": 0}
    ).sort([("days", 1), ("created_at", -1)])
    docs = await cur.to_list(200)
    return {"itineraries": [_itin_for_public(d) for d in docs]}


@api.get("/sitemap.xml")
async def sitemap(request: Request):
    """Dynamic XML sitemap: home, places, itineraries listings + one URL per POI and
    per published itinerary, each with hreflang alternates for the 5 languages."""
    proto = request.headers.get("x-forwarded-proto", "https")
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    base = f"{proto}://{host}".rstrip("/")
    langs = ["it", "en", "es", "fr", "de"]

    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    def url_entry(path: str, priority: str = "0.7", changefreq: str = "weekly") -> str:
        loc = f"{base}{path}"
        alts = "".join(
            f'<xhtml:link rel="alternate" hreflang="{l}" href="{esc(loc)}?lang={l}"/>' for l in langs
        )
        alts += f'<xhtml:link rel="alternate" hreflang="x-default" href="{esc(loc)}"/>'
        return (
            f"<url><loc>{esc(loc)}</loc>"
            f"<changefreq>{changefreq}</changefreq><priority>{priority}</priority>"
            f"{alts}</url>"
        )

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">',
        url_entry("/", "1.0", "weekly"),
        url_entry("/luoghi", "0.9", "weekly"),
        url_entry("/itinerari", "0.8", "weekly"),
        url_entry("/mappa", "0.7", "monthly"),
    ]

    pois = await db.pois.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
    for p in pois:
        slug = f"{content_slugify(p.get('name', 'luogo'))}-{(p.get('id') or '')[:8]}"
        parts.append(url_entry(f"/luoghi/{slug}", "0.6", "monthly"))

    itins = await db.carmelo_itineraries.find({"published": True}, {"_id": 0, "slug": 1}).to_list(500)
    for it in itins:
        if it.get("slug"):
            parts.append(url_entry(f"/itinerari/{it['slug']}", "0.7", "monthly"))

    parts.append("</urlset>")
    return Response(content="".join(parts), media_type="application/xml")


@api.get("/itineraries/{slug}")
async def get_public_itinerary(slug: str, code: Optional[str] = None):
    doc = await db.carmelo_itineraries.find_one(
        {"slug": slug, "published": True}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Itinerario non trovato")
    out = _itin_for_public(doc, full=True)
    visibility = doc.get("visibility", "code_only")
    code_ok = await _is_valid_unlock_code(code or "")
    out["can_download"] = bool(doc.get("pdf_filename")) and (visibility == "public" or code_ok)
    out["requires_code"] = visibility == "code_only" and not code_ok
    out["is_preview_only"] = visibility == "preview" and not code_ok
    return out


@api.get("/itineraries/{slug}/pdf")
async def download_itinerary_pdf(slug: str, code: Optional[str] = None):
    doc = await db.carmelo_itineraries.find_one(
        {"slug": slug, "published": True}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Itinerario non trovato")
    if not doc.get("pdf_filename"):
        raise HTTPException(status_code=404, detail="PDF non disponibile")
    visibility = doc.get("visibility", "code_only")
    if visibility != "public":
        if not await _is_valid_unlock_code(code or ""):
            raise HTTPException(status_code=403, detail="Codice prenotazione richiesto")
    pdf_path = UPLOAD_DIR_ITINERARIES / doc["pdf_filename"]
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File PDF mancante sul server")
    safe_title = content_slugify(doc.get("title", "itinerario"))
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{safe_title}.pdf",
    )


# ============================================================
# ADMIN: FAQ CRUD
# ============================================================
@api.get("/admin/faqs")
async def admin_list_faqs(_: str = Depends(get_current_admin)):
    cur = db.carmelo_faqs.find({}, {"_id": 0}).sort(
        [("category", 1), ("priority", -1)]
    )
    docs = await cur.to_list(1000)
    return {"faqs": docs, "categories": FAQ_CATEGORIES}


@api.post("/admin/faqs")
async def admin_create_faq(body: FaqIn, _: str = Depends(get_current_admin)):
    doc = {
        "id": str(uuid.uuid4()),
        "category": body.category,
        "question_it": body.question_it.strip(),
        "answer_it": (body.answer_it or "").strip(),
        "keywords": [k.strip().lower() for k in (body.keywords or []) if k.strip()],
        "priority": int(body.priority or 0),
        "published": bool(body.published),
        "translations": {},
        "asked_count": 0,
        "created_at": now_utc().isoformat(),
        "updated_at": now_utc().isoformat(),
    }
    await db.carmelo_faqs.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/admin/faqs/{faq_id}")
async def admin_update_faq(faq_id: str, body: FaqIn,
                            _: str = Depends(get_current_admin)):
    existing = await db.carmelo_faqs.find_one({"id": faq_id})
    if not existing:
        raise HTTPException(404, "FAQ non trovata")

    update = {
        "category": body.category,
        "question_it": body.question_it.strip(),
        "answer_it": (body.answer_it or "").strip(),
        "keywords": [k.strip().lower() for k in (body.keywords or []) if k.strip()],
        "priority": int(body.priority or 0),
        "published": bool(body.published),
        "updated_at": now_utc().isoformat(),
    }
    if (existing.get("question_it") != update["question_it"]
            or existing.get("answer_it") != update["answer_it"]):
        update["translations"] = {}
    await db.carmelo_faqs.update_one({"id": faq_id}, {"$set": update})
    doc = await db.carmelo_faqs.find_one({"id": faq_id}, {"_id": 0})
    return doc


@api.delete("/admin/faqs/{faq_id}")
async def admin_delete_faq(faq_id: str, _: str = Depends(get_current_admin)):
    res = await db.carmelo_faqs.delete_one({"id": faq_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "FAQ non trovata")
    return {"ok": True}


@api.post("/admin/faqs/seed")
async def admin_seed_faqs(_: str = Depends(get_current_admin)):
    """Crea le FAQ stub iniziali (solo quelle non già presenti)."""
    created = 0
    skipped = 0
    for stub in FAQ_SEED_STUBS:
        existing = await db.carmelo_faqs.find_one({"question_it": stub["question_it"]})
        if existing:
            skipped += 1
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "category": stub["category"],
            "question_it": stub["question_it"],
            "answer_it": "",
            "keywords": [],
            "priority": stub.get("priority", 0),
            "published": False,
            "translations": {},
            "asked_count": 0,
            "created_at": now_utc().isoformat(),
            "updated_at": now_utc().isoformat(),
        }
        await db.carmelo_faqs.insert_one(doc)
        created += 1
    return {"ok": True, "created": created, "skipped": skipped}


@api.post("/admin/faqs/{faq_id}/translate")
async def admin_translate_faq(faq_id: str, body: FaqTranslateIn,
                                _: str = Depends(get_current_admin)):
    """Traduce la FAQ in target_lang usando LLM e memorizza in translations."""
    if body.target_lang not in SUPPORTED_LANGS or body.target_lang == "it":
        raise HTTPException(400, f"Lingua non supportata: {body.target_lang}")
    doc = await db.carmelo_faqs.find_one({"id": faq_id})
    if not doc:
        raise HTTPException(404, "FAQ non trovata")
    if not doc.get("answer_it", "").strip():
        raise HTTPException(400, "Rispondi alla FAQ in italiano prima di tradurla")
    try:
        result = await content_translate_faq(
            EMERGENT_LLM_KEY,
            doc["question_it"],
            doc["answer_it"],
            body.target_lang,
        )
    except Exception as e:
        logger.exception("Translate error: %s", e)
        raise HTTPException(500, f"Errore traduzione: {e}")
    translations = doc.get("translations") or {}
    translations[body.target_lang] = {
        "question": result["question"],
        "answer": result["answer"],
        "translated_at": now_utc().isoformat(),
    }
    await db.carmelo_faqs.update_one(
        {"id": faq_id},
        {"$set": {"translations": translations, "updated_at": now_utc().isoformat()}},
    )
    return {"ok": True, "translation": translations[body.target_lang]}


# ============================================================
# ADMIN: Guest Questions Inbox
# ============================================================
@api.get("/admin/guest-questions")
async def admin_list_guest_questions(_: str = Depends(get_current_admin)):
    cur = db.carmelo_guest_questions.find({}, {"_id": 0}).sort("created_at", -1)
    docs = await cur.to_list(500)
    counts = {
        "open": sum(1 for d in docs if d.get("status") == "open"),
        "answered": sum(1 for d in docs if d.get("status") == "answered"),
        "closed": sum(1 for d in docs if d.get("status") == "closed"),
    }
    return {"questions": docs, "counts": counts}


@api.patch("/admin/guest-questions/{qid}")
async def admin_update_guest_question(qid: str, body: GuestQuestionAdminUpdate,
                                       _: str = Depends(get_current_admin)):
    update: dict = {}
    if body.status:
        if body.status not in ("open", "answered", "closed"):
            raise HTTPException(400, "Status non valido")
        update["status"] = body.status
        if body.status == "answered":
            update["answered_at"] = now_utc().isoformat()
    if body.answer is not None:
        update["answer"] = body.answer
    if not update:
        raise HTTPException(400, "Niente da aggiornare")
    res = await db.carmelo_guest_questions.update_one({"id": qid}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Domanda non trovata")
    return {"ok": True}


@api.delete("/admin/guest-questions/{qid}")
async def admin_delete_guest_question(qid: str, _: str = Depends(get_current_admin)):
    res = await db.carmelo_guest_questions.delete_one({"id": qid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Domanda non trovata")
    return {"ok": True}


@api.post("/admin/guest-questions/{qid}/promote-to-faq")
async def admin_promote_to_faq(qid: str, body: GuestQuestionPromoteIn,
                                _: str = Depends(get_current_admin)):
    q = await db.carmelo_guest_questions.find_one({"id": qid})
    if not q:
        raise HTTPException(404, "Domanda non trovata")
    doc = {
        "id": str(uuid.uuid4()),
        "category": body.category,
        "question_it": body.question_it.strip(),
        "answer_it": body.answer_it.strip(),
        "keywords": [],
        "priority": 50,
        "published": bool(body.publish),
        "translations": {},
        "asked_count": 1,
        "created_at": now_utc().isoformat(),
        "updated_at": now_utc().isoformat(),
    }
    await db.carmelo_faqs.insert_one(doc)
    await db.carmelo_guest_questions.update_one(
        {"id": qid},
        {"$set": {"status": "closed", "promoted_to_faq_id": doc["id"],
                  "answered_at": now_utc().isoformat()}},
    )
    return {"ok": True, "faq_id": doc["id"]}


# ============================================================
# ADMIN: Itineraries CRUD + PDF upload
# ============================================================
@api.get("/admin/itineraries")
async def admin_list_itineraries(_: str = Depends(get_current_admin)):
    cur = db.carmelo_itineraries.find({}, {"_id": 0}).sort("created_at", -1)
    docs = await cur.to_list(200)
    return {"itineraries": docs}


async def _unique_slug(base: str, exclude_id: Optional[str] = None) -> str:
    slug = content_slugify(base)
    i = 1
    candidate = slug
    while True:
        flt = {"slug": candidate}
        if exclude_id:
            flt["id"] = {"$ne": exclude_id}
        if not await db.carmelo_itineraries.find_one(flt):
            return candidate
        i += 1
        candidate = f"{slug}-{i}"
        if i > 200:
            return f"{slug}-{uuid.uuid4().hex[:6]}"


@api.post("/admin/itineraries")
async def admin_create_itinerary(body: ItineraryIn,
                                  _: str = Depends(get_current_admin)):
    if body.visibility not in ("public", "preview", "code_only"):
        raise HTTPException(400, "Visibility non valida")
    days = max(1, min(30, int(body.days or 1)))
    slug = await _unique_slug(body.title)
    doc = {
        "id": str(uuid.uuid4()),
        "slug": slug,
        "title": body.title.strip(),
        "subtitle": (body.subtitle or "").strip(),
        "days": days,
        "theme": (body.theme or "").strip(),
        "hero_image": (body.hero_image or "").strip(),
        "preview_text": (body.preview_text or "").strip(),
        "highlights": [h.strip() for h in (body.highlights or []) if h.strip()],
        "tags": [t.strip().lower() for t in (body.tags or []) if t.strip()],
        "visibility": body.visibility,
        "published": bool(body.published),
        "pdf_filename": None,
        "pdf_size": 0,
        "pdf_uploaded_at": None,
        "created_at": now_utc().isoformat(),
        "updated_at": now_utc().isoformat(),
    }
    await db.carmelo_itineraries.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/admin/itineraries/{itin_id}")
async def admin_update_itinerary(itin_id: str, body: ItineraryIn,
                                  _: str = Depends(get_current_admin)):
    existing = await db.carmelo_itineraries.find_one({"id": itin_id})
    if not existing:
        raise HTTPException(404, "Itinerario non trovato")
    if body.visibility not in ("public", "preview", "code_only"):
        raise HTTPException(400, "Visibility non valida")
    days = max(1, min(30, int(body.days or 1)))
    new_slug = existing.get("slug")
    if (existing.get("title") or "") != body.title.strip():
        new_slug = await _unique_slug(body.title, exclude_id=itin_id)
    update = {
        "slug": new_slug,
        "title": body.title.strip(),
        "subtitle": (body.subtitle or "").strip(),
        "days": days,
        "theme": (body.theme or "").strip(),
        "hero_image": (body.hero_image or "").strip(),
        "preview_text": (body.preview_text or "").strip(),
        "highlights": [h.strip() for h in (body.highlights or []) if h.strip()],
        "tags": [t.strip().lower() for t in (body.tags or []) if t.strip()],
        "visibility": body.visibility,
        "published": bool(body.published),
        "updated_at": now_utc().isoformat(),
    }
    await db.carmelo_itineraries.update_one({"id": itin_id}, {"$set": update})
    return await db.carmelo_itineraries.find_one({"id": itin_id}, {"_id": 0})


@api.delete("/admin/itineraries/{itin_id}")
async def admin_delete_itinerary(itin_id: str, _: str = Depends(get_current_admin)):
    doc = await db.carmelo_itineraries.find_one({"id": itin_id})
    if not doc:
        raise HTTPException(404, "Itinerario non trovato")
    if doc.get("pdf_filename"):
        p = UPLOAD_DIR_ITINERARIES / doc["pdf_filename"]
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
    await db.carmelo_itineraries.delete_one({"id": itin_id})
    return {"ok": True}


@api.post("/admin/itineraries/{itin_id}/upload-pdf")
async def admin_upload_itinerary_pdf(itin_id: str,
                                      file: UploadFile = File(...),
                                      _: str = Depends(get_current_admin)):
    doc = await db.carmelo_itineraries.find_one({"id": itin_id})
    if not doc:
        raise HTTPException(404, "Itinerario non trovato")
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Carica un file PDF")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 25 MB)")
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "File non riconosciuto come PDF valido")

    if doc.get("pdf_filename"):
        old = UPLOAD_DIR_ITINERARIES / doc["pdf_filename"]
        if old.exists():
            try:
                old.unlink()
            except Exception:
                pass

    new_filename = f"{itin_id}.pdf"
    target = UPLOAD_DIR_ITINERARIES / new_filename
    with open(target, "wb") as f:
        f.write(content)

    await db.carmelo_itineraries.update_one(
        {"id": itin_id},
        {"$set": {
            "pdf_filename": new_filename,
            "pdf_size": len(content),
            "pdf_uploaded_at": now_utc().isoformat(),
            "updated_at": now_utc().isoformat(),
        }},
    )
    return {"ok": True, "filename": new_filename, "size": len(content)}


@api.delete("/admin/itineraries/{itin_id}/pdf")
async def admin_delete_itinerary_pdf(itin_id: str,
                                      _: str = Depends(get_current_admin)):
    doc = await db.carmelo_itineraries.find_one({"id": itin_id})
    if not doc:
        raise HTTPException(404, "Itinerario non trovato")
    if doc.get("pdf_filename"):
        p = UPLOAD_DIR_ITINERARIES / doc["pdf_filename"]
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
    await db.carmelo_itineraries.update_one(
        {"id": itin_id},
        {"$set": {"pdf_filename": None, "pdf_size": 0, "pdf_uploaded_at": None,
                  "updated_at": now_utc().isoformat()}},
    )
    return {"ok": True}


@api.get("/admin/itineraries/{itin_id}/pdf")
async def admin_get_itinerary_pdf(itin_id: str, _: str = Depends(get_current_admin)):
    doc = await db.carmelo_itineraries.find_one({"id": itin_id})
    if not doc:
        raise HTTPException(404, "Itinerario non trovato")
    if not doc.get("pdf_filename"):
        raise HTTPException(404, "PDF non disponibile")
    p = UPLOAD_DIR_ITINERARIES / doc["pdf_filename"]
    if not p.exists():
        raise HTTPException(404, "File PDF mancante")
    return FileResponse(path=str(p), media_type="application/pdf",
                         filename=f"{content_slugify(doc.get('title', 'itinerario'))}.pdf")


    today = now_utc().date().isoformat()
    ai_code = await db.discount_codes.find_one(
        {"code": code_clean, "active": True, "type": "ai_access"}, {"_id": 0}
    )
    if ai_code and ai_code.get("valid_from", "") <= today <= ai_code.get("valid_to", ""):
        return {"valid": True, "kind": "ai_access"}

    raise HTTPException(
        status_code=403,
        detail="Codice non valido o scaduto. Verrà generato automaticamente quando l'host approverà la tua prenotazione.",
    )


# ============================================================
# Default POIs (Provincia Palermo & Trapani)
# ============================================================
DEFAULT_POIS = [
    # ===== ARTE & CULTURA (Provincia Palermo) =====
    {"name": "Cattedrale di Palermo", "category": "art", "lat": 38.1145, "lng": 13.3556, "description": "Capolavoro arabo-normanno, patrimonio UNESCO.", "town": "Palermo", "province": "PA"},
    {"name": "Palazzo dei Normanni e Cappella Palatina", "category": "art", "lat": 38.1110, "lng": 13.3520, "description": "Cappella con mosaici bizantini straordinari.", "town": "Palermo", "province": "PA"},
    {"name": "Teatro Massimo", "category": "art", "lat": 38.1206, "lng": 13.3567, "description": "Il più grande teatro lirico d'Italia.", "town": "Palermo", "province": "PA"},
    {"name": "Teatro Politeama Garibaldi", "category": "art", "lat": 38.1245, "lng": 13.3567, "description": "Teatro ottocentesco affacciato su Piazza Ruggero Settimo, sede dell'Orchestra Sinfonica Siciliana.", "town": "Palermo", "province": "PA"},
    {"name": "Quattro Canti e Piazza Pretoria", "category": "art", "lat": 38.1153, "lng": 13.3617, "description": "Cuore barocco di Palermo.", "town": "Palermo", "province": "PA"},
    {"name": "Mercato di Ballarò", "category": "art", "lat": 38.1117, "lng": 13.3589, "description": "Storico mercato popolare di Palermo, profumi e voci.", "town": "Palermo", "province": "PA"},
    {"name": "Mercato della Vucciria", "category": "art", "lat": 38.1198, "lng": 13.3653, "description": "Mercato leggendario reso famoso da Guttuso.", "town": "Palermo", "province": "PA"},
    {"name": "Catacombe dei Cappuccini", "category": "art", "lat": 38.1108, "lng": 13.3406, "description": "Affascinante e inquietante cripta con migliaia di mummie.", "town": "Palermo", "province": "PA"},
    {"name": "Duomo di Monreale", "category": "art", "lat": 38.0820, "lng": 13.2925, "description": "Mosaici dorati arabo-normanni, patrimonio UNESCO.", "town": "Monreale", "province": "PA"},
    {"name": "Duomo di Cefalù", "category": "art", "lat": 38.0386, "lng": 14.0227, "description": "Cattedrale arabo-normanna affacciata sul mare.", "town": "Cefalù", "province": "PA"},
    {"name": "Centro storico di Cefalù", "category": "art", "lat": 38.0365, "lng": 14.0240, "description": "Vicoli medievali tra mare e Rocca.", "town": "Cefalù", "province": "PA"},
    {"name": "Villa Palagonia", "category": "art", "lat": 38.0789, "lng": 13.5092, "description": "Villa barocca dei mostri a Bagheria.", "town": "Bagheria", "province": "PA"},
    {"name": "Castello di Carini", "category": "art", "lat": 38.1352, "lng": 13.1797, "description": "Maniero medievale con la leggenda della Baronessa.", "town": "Carini", "province": "PA"},
    {"name": "Castello a Mare", "category": "art", "lat": 38.1361, "lng": 13.3702, "description": "Fortezza del porto di Palermo.", "town": "Palermo", "province": "PA"},

    # ===== ARTE & CULTURA (Provincia Trapani) =====
    {"name": "Tempio di Segesta", "category": "art", "lat": 37.9415, "lng": 12.8336, "description": "Tempio dorico del V sec. a.C. perfettamente conservato.", "town": "Calatafimi-Segesta", "province": "TP"},
    {"name": "Teatro greco di Segesta", "category": "art", "lat": 37.9445, "lng": 12.8395, "description": "Teatro antico con vista mozzafiato sulle colline.", "town": "Calatafimi-Segesta", "province": "TP"},
    {"name": "Parco archeologico di Selinunte", "category": "art", "lat": 37.5839, "lng": 12.8252, "description": "Il più grande parco archeologico d'Europa.", "town": "Castelvetrano", "province": "TP"},
    {"name": "Borgo medievale di Erice", "category": "art", "lat": 38.0382, "lng": 12.5887, "description": "Borgo storico in cima al monte, panorami infiniti.", "town": "Erice", "province": "TP"},
    {"name": "Castello di Venere (Erice)", "category": "art", "lat": 38.0364, "lng": 12.5919, "description": "Castello normanno sulla vetta del Monte San Giuliano.", "town": "Erice", "province": "TP"},
    {"name": "Saline e Mulini di Trapani", "category": "art", "lat": 37.9544, "lng": 12.5070, "description": "Saline storiche con mulini a vento, sito Ramsar.", "town": "Trapani", "province": "TP"},
    {"name": "Centro storico di Trapani", "category": "art", "lat": 38.0176, "lng": 12.5365, "description": "Vicoli barocchi e Torre di Ligny sulla punta.", "town": "Trapani", "province": "TP"},
    {"name": "Cattedrale di Marsala", "category": "art", "lat": 37.7993, "lng": 12.4368, "description": "Cattedrale barocca dedicata a San Tommaso.", "town": "Marsala", "province": "TP"},
    {"name": "Cantine storiche di Marsala", "category": "art", "lat": 37.7959, "lng": 12.4378, "description": "Florio, Pellegrino, Donnafugata: tradizione vinicola.", "town": "Marsala", "province": "TP"},
    {"name": "Isola di Mozia (Mothia)", "category": "art", "lat": 37.8703, "lng": 12.4717, "description": "Antica città fenicia con il Giovinetto di Mozia.", "town": "Marsala", "province": "TP"},
    {"name": "Casbah di Mazara del Vallo", "category": "art", "lat": 37.6519, "lng": 12.5897, "description": "Quartiere arabo nel cuore del centro storico.", "town": "Mazara del Vallo", "province": "TP"},
    {"name": "Museo del Satiro Danzante", "category": "art", "lat": 37.6531, "lng": 12.5916, "description": "Il celebre bronzo greco recuperato dal mare.", "town": "Mazara del Vallo", "province": "TP"},
    {"name": "Castello arabo-normanno di Salemi", "category": "art", "lat": 37.8156, "lng": 12.8050, "description": "Borgo arroccato con castello del XII secolo.", "town": "Salemi", "province": "TP"},

    # ===== SPIAGGE (Provincia Palermo) =====
    {"name": "Spiaggia di Mondello", "category": "beach", "lat": 38.2049, "lng": 13.3252, "description": "Sabbia bianca a mezzaluna a 11 km da Palermo.", "town": "Palermo", "province": "PA"},
    {"name": "Spiaggia di Cefalù", "category": "beach", "lat": 38.0405, "lng": 14.0177, "description": "Sabbia dorata sotto la Rocca, ideale per famiglie.", "town": "Cefalù", "province": "PA"},
    {"name": "Spiaggia di Trappeto", "category": "beach", "lat": 38.0815, "lng": 13.0431, "description": "Sabbia fine e mare turchese, perfetta a due passi da casa.", "town": "Trappeto", "province": "PA"},
    {"name": "Spiaggia di Balestrate", "category": "beach", "lat": 38.0506, "lng": 13.0024, "description": "Lunga spiaggia di sabbia, ottimi stabilimenti.", "town": "Balestrate", "province": "PA"},
    {"name": "Spiaggia di Aspra", "category": "beach", "lat": 38.0935, "lng": 13.5283, "description": "Borgo marinaro autentico e calette caratteristiche.", "town": "Bagheria", "province": "PA"},
    {"name": "Capo Gallo - Cala Rossa", "category": "beach", "lat": 38.2163, "lng": 13.2835, "description": "Cale rocciose nella riserva di Capo Gallo.", "town": "Palermo", "province": "PA"},
    {"name": "Pollina - Finale", "category": "beach", "lat": 38.0220, "lng": 14.1660, "description": "Lunghe spiagge di sabbia a est di Cefalù.", "town": "Pollina", "province": "PA"},

    # ===== SPIAGGE (Provincia Trapani) =====
    {"name": "San Vito Lo Capo", "category": "beach", "lat": 38.1832, "lng": 12.7320, "description": "Iconica spiaggia bianca tra mare caraibico e Monte Monaco.", "town": "San Vito Lo Capo", "province": "TP"},
    {"name": "Macari - Baia Santa Margherita", "category": "beach", "lat": 38.1648, "lng": 12.7137, "description": "Caletta selvaggia con scogli e fondali cristallini.", "town": "San Vito Lo Capo", "province": "TP"},
    {"name": "Cala dell'Uzzo (Zingaro)", "category": "beach", "lat": 38.1085, "lng": 12.7902, "description": "Caletta della Riserva dello Zingaro, accesso a piedi.", "town": "San Vito Lo Capo", "province": "TP"},
    {"name": "Cala Bianca (Zingaro)", "category": "beach", "lat": 38.1011, "lng": 12.7929, "description": "Acque turchesi nel cuore della riserva.", "town": "Custonaci", "province": "TP"},
    {"name": "Spiaggia di Scopello e Faraglioni", "category": "beach", "lat": 38.0689, "lng": 12.8281, "description": "La cartolina della Sicilia: tonnara e faraglioni.", "town": "Castellammare del Golfo", "province": "TP"},
    {"name": "Spiaggia di Cornino", "category": "beach", "lat": 38.1187, "lng": 12.6649, "description": "Sabbia chiara ai piedi di Monte Cofano.", "town": "Custonaci", "province": "TP"},
    {"name": "Lido Marausa", "category": "beach", "lat": 37.8866, "lng": 12.4775, "description": "Sabbia bianca a sud di Trapani, fondale basso.", "town": "Misiliscemi", "province": "TP"},
    {"name": "Spiaggia di Tre Fontane", "category": "beach", "lat": 37.5660, "lng": 12.7224, "description": "Lunga spiaggia di sabbia dorata, ideale per surf.", "town": "Campobello di Mazara", "province": "TP"},
    {"name": "Spiaggia delle Saline (Marsala)", "category": "beach", "lat": 37.8780, "lng": 12.4540, "description": "Spiaggia con vista sulle saline e Mozia.", "town": "Marsala", "province": "TP"},

    # ===== NATURA & PANORAMI (Provincia Palermo) =====
    {"name": "Riserva di Capo Gallo", "category": "nature", "lat": 38.2228, "lng": 13.2900, "description": "Sentieri panoramici sul mare a nord di Palermo.", "town": "Palermo", "province": "PA"},
    {"name": "Monte Pellegrino e Santuario di Santa Rosalia", "category": "nature", "lat": 38.1700, "lng": 13.3550, "description": "Panorama spettacolare sul golfo di Palermo.", "town": "Palermo", "province": "PA"},
    {"name": "Madonie - Piano Battaglia", "category": "nature", "lat": 37.8689, "lng": 14.0119, "description": "Parco delle Madonie, sentieri e d'inverno neve.", "town": "Petralia Sottana", "province": "PA"},
    {"name": "La Rocca di Cefalù", "category": "nature", "lat": 38.0444, "lng": 14.0294, "description": "Salita panoramica con rovine medievali in cima.", "town": "Cefalù", "province": "PA"},
    {"name": "Riserva di Monte Catalfano", "category": "nature", "lat": 38.0686, "lng": 13.5519, "description": "Vista a 360° sul Golfo di Palermo, antica Solunto.", "town": "Bagheria", "province": "PA"},
    {"name": "Gole del Pollina", "category": "nature", "lat": 37.9967, "lng": 14.1581, "description": "Trekking tra canyon nei pressi dei Nebrodi.", "town": "Pollina", "province": "PA"},

    # ===== NATURA & PANORAMI (Provincia Trapani) =====
    {"name": "Riserva dello Zingaro", "category": "nature", "lat": 38.0856, "lng": 12.7916, "description": "Prima riserva naturale della Sicilia, sentiero costiero.", "town": "San Vito Lo Capo", "province": "TP"},
    {"name": "Riserva di Monte Cofano", "category": "nature", "lat": 38.1322, "lng": 12.6739, "description": "Promontorio calcareo a picco sul mare turchese.", "town": "Custonaci", "province": "TP"},
    {"name": "Stagnone di Marsala", "category": "nature", "lat": 37.8800, "lng": 12.4650, "description": "Laguna salata con tramonti leggendari e kitesurf.", "town": "Marsala", "province": "TP"},
    {"name": "Belvedere di Erice", "category": "nature", "lat": 38.0395, "lng": 12.5905, "description": "Vista che spazia dalle Egadi fino a Cofano.", "town": "Erice", "province": "TP"},
    {"name": "Lago Rubino", "category": "nature", "lat": 37.9275, "lng": 12.6694, "description": "Lago artificiale immerso nella campagna trapanese.", "town": "Trapani", "province": "TP"},
    {"name": "Riserva Bosco di Scorace", "category": "nature", "lat": 37.9750, "lng": 12.8350, "description": "Sughereta secolare, ideale per passeggiate.", "town": "Buseto Palizzolo", "province": "TP"},
    {"name": "Isole Egadi - Favignana", "category": "nature", "lat": 37.9325, "lng": 12.3267, "description": "Calette turchesi raggiungibili in traghetto da Trapani.", "town": "Favignana", "province": "TP"},
    {"name": "Isole Egadi - Levanzo", "category": "nature", "lat": 38.0029, "lng": 12.3358, "description": "Piccola isola con la Grotta del Genovese.", "town": "Favignana", "province": "TP"},

    # ===== NUOVI POI · ARTE (Palermo città + provincia) =====
    {"name": "Palazzo della Zisa", "category": "art", "lat": 38.1188, "lng": 13.3399, "description": "Palazzo d'estate arabo-normanno, gioiello UNESCO immerso nel Genoardo.", "town": "Palermo", "province": "PA"},
    {"name": "Chiesa della Martorana", "category": "art", "lat": 38.1155, "lng": 13.3625, "description": "Chiesa medievale con mosaici bizantini a fondo oro, UNESCO.", "town": "Palermo", "province": "PA"},
    {"name": "Museo Archeologico Salinas", "category": "art", "lat": 38.1215, "lng": 13.3603, "description": "Il più importante museo archeologico della Sicilia, tra fenici, greci e romani.", "town": "Palermo", "province": "PA"},
    {"name": "San Giovanni degli Eremiti", "category": "art", "lat": 38.1123, "lng": 13.3488, "description": "Cupole rosse arabo-normanne e chiostro con giardino profumato di agrumi.", "town": "Palermo", "province": "PA"},
    {"name": "Palazzo Abatellis (Galleria Regionale)", "category": "art", "lat": 38.1150, "lng": 13.3710, "description": "Pinacoteca con il Trionfo della Morte e l'Annunciata di Antonello.", "town": "Palermo", "province": "PA"},
    {"name": "Palazzo Chiaramonte-Steri", "category": "art", "lat": 38.1147, "lng": 13.3728, "description": "Sede dell'Inquisizione: soffitto ligneo trecentesco e graffiti dei prigionieri.", "town": "Palermo", "province": "PA"},
    {"name": "Mercato del Capo", "category": "art", "lat": 38.1179, "lng": 13.3536, "description": "Il più antico mercato di Palermo tra grida, panelle e sfincione.", "town": "Palermo", "province": "PA"},
    {"name": "Foro Italico Umberto I", "category": "art", "lat": 38.1141, "lng": 13.3762, "description": "Passeggiata sul mare con vista su Monte Pellegrino, cuore serale di Palermo.", "town": "Palermo", "province": "PA"},
    {"name": "Orto Botanico di Palermo", "category": "nature", "lat": 38.1116, "lng": 13.3729, "description": "Uno dei più antichi orti botanici d'Europa (1789), con piante tropicali secolari e un immenso ficus.", "town": "Palermo", "province": "PA"},
    {"name": "Molo Trapezoidale (Porto di Palermo)", "category": "art", "lat": 38.1288, "lng": 13.3714, "description": "Nuovo waterfront del porto di Palermo con passeggiata panoramica, ormeggio yacht e area eventi.", "town": "Palermo", "province": "PA"},
    {"name": "Murales Falcone e Borsellino (Palermo)", "category": "art", "lat": 38.1140, "lng": 13.3728, "description": "Grande murale dedicato ai giudici antimafia, uno dei simboli della Palermo che resiste (zona Kalsa/Magione).", "town": "Palermo", "province": "PA"},
    {"name": "Piazza Marina e Giardino Garibaldi", "category": "art", "lat": 38.1147, "lng": 13.3720, "description": "Piazza storica della Kalsa con l'enorme ficus magnolioides ottocentesco, accanto a Palazzo Steri.", "town": "Palermo", "province": "PA"},
    {"name": "Villa Malfitano Whitaker", "category": "art", "lat": 38.1252, "lng": 13.3405, "description": "Villa neoclassica della famiglia Whitaker con parco esotico, salone estivo e mobili originali di fine '800.", "town": "Palermo", "province": "PA"},
    {"name": "Palazzina Cinese e Museo Pitrè", "category": "art", "lat": 38.1721, "lng": 13.3435, "description": "Residenza reale in stile cinoiserie nel Parco della Favorita, adiacente al museo etnografico Pitrè.", "town": "Palermo", "province": "PA"},
    {"name": "Parco della Favorita", "category": "nature", "lat": 38.1730, "lng": 13.3450, "description": "Grande parco reale borbonico ai piedi di Monte Pellegrino: sentieri, agrumeti e ville storiche.", "town": "Palermo", "province": "PA"},
    {"name": "Quartiere della Kalsa (Piazza Magione)", "category": "art", "lat": 38.1128, "lng": 13.3708, "description": "Cuore antico di Palermo: la chiesa normanna della Magione, piazza spaziosa, locali e street art.", "town": "Palermo", "province": "PA"},
    {"name": "Stand Florio all'Arenella", "category": "art", "lat": 38.1655, "lng": 13.3722, "description": "Padiglione neogotico voluto dalla famiglia Florio sul mare dell'Arenella, oggi sede di eventi.", "town": "Palermo", "province": "PA"},
    {"name": "Cantieri Culturali alla Zisa", "category": "art", "lat": 38.1214, "lng": 13.3418, "description": "Ex fabbrica Ducrot riconvertita a polo culturale: mostre, teatro, cinema d'autore e concerti.", "town": "Palermo", "province": "PA"},
    {"name": "Antico Mercato del Borgo Vecchio", "category": "art", "lat": 38.1272, "lng": 13.3591, "description": "Mercato notturno tra Via Villafranca e Piazza Ucciardone: brace, panelle e vita popolare fino a tarda notte.", "town": "Palermo", "province": "PA"},
    {"name": "Museo del Mare (Arsenale)", "category": "art", "lat": 38.1278, "lng": 13.3695, "description": "Storia marinara di Palermo nell'Arsenale settecentesco, accanto al Molo Trapezoidale.", "town": "Palermo", "province": "PA"},
    {"name": "Area archeologica di Solunto", "category": "art", "lat": 38.0928, "lng": 13.5406, "description": "Antica città punica-romana con vista mozzafiato sul Golfo di Palermo.", "town": "Santa Flavia", "province": "PA"},
    {"name": "Centro storico di Castelbuono", "category": "art", "lat": 37.9358, "lng": 14.0879, "description": "Borgo delle Madonie con castello dei Ventimiglia e tradizione della manna.", "town": "Castelbuono", "province": "PA"},
    {"name": "Petralia Soprana (borgo)", "category": "art", "lat": 37.7960, "lng": 14.1050, "description": "Tra i borghi più belli d'Italia, arroccato a 1147 m nelle Madonie.", "town": "Petralia Soprana", "province": "PA"},
    {"name": "Gangi (borgo)", "category": "art", "lat": 37.7960, "lng": 14.2062, "description": "Borgo medievale abbarbicato sul Monte Marone, 'borgo dei borghi'.", "town": "Gangi", "province": "PA"},
    {"name": "Polizzi Generosa", "category": "art", "lat": 37.8127, "lng": 14.0195, "description": "Cittadina delle Madonie con chiese barocche e la nocciola gentile.", "town": "Polizzi Generosa", "province": "PA"},
    {"name": "Piana degli Albanesi", "category": "art", "lat": 37.9947, "lng": 13.2820, "description": "Comunità arbëreshë con rito bizantino, celebre la Pasqua in costume.", "town": "Piana degli Albanesi", "province": "PA"},
    {"name": "Real Casina di Caccia (Ficuzza)", "category": "art", "lat": 37.8720, "lng": 13.4093, "description": "Palazzina borbonica ai margini del bosco, mercatini nel weekend.", "town": "Corleone", "province": "PA"},
    {"name": "Centro storico di Corleone", "category": "art", "lat": 37.8107, "lng": 13.3021, "description": "Chiese, torri saracene e il museo dell'antimafia in un borgo dell'entroterra.", "town": "Corleone", "province": "PA"},
    {"name": "Museo del Carretto Siciliano (Terrasini)", "category": "art", "lat": 38.1531, "lng": 13.0788, "description": "Palazzo D'Aumale con la più ricca collezione di carretti siciliani.", "town": "Terrasini", "province": "PA"},
    {"name": "Centro storico di Cinisi", "category": "art", "lat": 38.1585, "lng": 13.1051, "description": "Borgo di Peppino Impastato, chiesa madre e strade in pietra.", "town": "Cinisi", "province": "PA"},
    {"name": "Duomo di Termini Imerese", "category": "art", "lat": 37.9860, "lng": 13.6970, "description": "Cattedrale barocca affacciata sul mare, centro termale sin dall'antichità.", "town": "Termini Imerese", "province": "PA"},
    {"name": "Himera - Parco archeologico", "category": "art", "lat": 37.9660, "lng": 13.8422, "description": "Colonia greca del 648 a.C. con Tempio della Vittoria.", "town": "Termini Imerese", "province": "PA"},
    {"name": "Santuario di Gibilmanna", "category": "art", "lat": 37.9830, "lng": 14.0293, "description": "Santuario francescano sul Pizzo Sant'Angelo, vista su Cefalù e Madonie.", "town": "Cefalù", "province": "PA"},

    # ===== NUOVI POI · ARTE (Trapani città + provincia) =====
    {"name": "Torre di Ligny", "category": "art", "lat": 38.0193, "lng": 12.4986, "description": "Fortezza spagnola sulla punta estrema di Trapani, tramonti sul mare.", "town": "Trapani", "province": "TP"},
    {"name": "Cattedrale di San Lorenzo (Trapani)", "category": "art", "lat": 38.0170, "lng": 12.5138, "description": "Cattedrale barocca nel cuore del centro storico trapanese.", "town": "Trapani", "province": "TP"},
    {"name": "Santuario dell'Annunziata (Trapani)", "category": "art", "lat": 38.0225, "lng": 12.5296, "description": "Custodisce la Madonna di Trapani e il Museo Pepoli.", "town": "Trapani", "province": "TP"},
    {"name": "Castello arabo-normanno di Castellammare", "category": "art", "lat": 38.0263, "lng": 12.8863, "description": "Fortezza sul porto turistico, tra torri arabe e bastioni.", "town": "Castellammare del Golfo", "province": "TP"},
    {"name": "Castello dei Conti di Modica (Alcamo)", "category": "art", "lat": 37.9773, "lng": 12.9660, "description": "Castello quattrocentesco nel centro storico di Alcamo.", "town": "Alcamo", "province": "TP"},
    {"name": "Cretto di Burri (Gibellina)", "category": "art", "lat": 37.7844, "lng": 12.9068, "description": "Immensa opera di land art di Alberto Burri sui ruderi della vecchia Gibellina.", "town": "Gibellina", "province": "TP"},
    {"name": "Ruderi di Poggioreale antica", "category": "art", "lat": 37.7325, "lng": 13.0393, "description": "Città fantasma abbandonata dopo il terremoto del Belice del 1968.", "town": "Poggioreale", "province": "TP"},
    {"name": "Cave di Cusa", "category": "art", "lat": 37.5807, "lng": 12.7180, "description": "Antiche cave di tufo dei Selinunti, colonne interrotte dal 409 a.C.", "town": "Campobello di Mazara", "province": "TP"},
    {"name": "Grotta Mangiapane (Custonaci)", "category": "art", "lat": 38.1140, "lng": 12.6772, "description": "Villaggio-presepe dentro una grotta preistorica, set di film celebri.", "town": "Custonaci", "province": "TP"},

    # ===== NUOVI POI · SPIAGGE (Palermo) =====
    {"name": "Spiaggia di Isola delle Femmine", "category": "beach", "lat": 38.2101, "lng": 13.2427, "description": "Sabbia dorata di fronte all'isolotto riserva naturale.", "town": "Isola delle Femmine", "province": "PA"},
    {"name": "Baia dell'Olivella", "category": "beach", "lat": 38.1010, "lng": 13.5237, "description": "Caletta selvaggia ai piedi di Solunto, mare cristallino.", "town": "Santa Flavia", "province": "PA"},
    {"name": "Spiaggia dell'Arenella", "category": "beach", "lat": 38.1739, "lng": 13.3808, "description": "Borgo di pescatori con arenile sabbioso, vista su Monte Pellegrino.", "town": "Palermo", "province": "PA"},
    {"name": "Spiaggia di Sferracavallo", "category": "beach", "lat": 38.2098, "lng": 13.2653, "description": "Borgata marinara a nord di Palermo, ricci di mare e pasta con le sarde.", "town": "Palermo", "province": "PA"},
    {"name": "Spiaggia di Terrasini (Praia)", "category": "beach", "lat": 38.1520, "lng": 13.0800, "description": "Cala Rossa e Praiola, scogli e piccole calette a pochi km da Trappeto.", "town": "Terrasini", "province": "PA"},

    # ===== NUOVI POI · SPIAGGE (Trapani) =====
    {"name": "Marettimo (Isole Egadi)", "category": "beach", "lat": 37.9636, "lng": 12.0728, "description": "L'isola più selvaggia delle Egadi, grotte marine e sentieri montani.", "town": "Favignana", "province": "TP"},
    {"name": "Alcamo Marina", "category": "beach", "lat": 38.0430, "lng": 12.9412, "description": "Lunga spiaggia di sabbia sul Golfo di Castellammare.", "town": "Alcamo", "province": "TP"},
    {"name": "Spiaggia di Bonagia (Valderice)", "category": "beach", "lat": 38.0640, "lng": 12.5665, "description": "Borgo di pescatori con tonnara storica e mare turchese.", "town": "Valderice", "province": "TP"},
    {"name": "Spiaggia di Selinunte (Marinella)", "category": "beach", "lat": 37.5822, "lng": 12.8228, "description": "Ampia spiaggia accanto al parco archeologico, sabbia dorata.", "town": "Castelvetrano", "province": "TP"},

    # ===== NUOVI POI · NATURA & PANORAMI =====
    {"name": "Riserva marina di Ustica", "category": "nature", "lat": 38.7060, "lng": 13.1830, "description": "Prima riserva marina d'Italia, paradiso per snorkeling e diving.", "town": "Ustica", "province": "PA"},
    {"name": "Bosco della Ficuzza", "category": "nature", "lat": 37.8595, "lng": 13.4030, "description": "Uno dei boschi più estesi della Sicilia occidentale, sentieri e cascate.", "town": "Corleone", "province": "PA"},
    {"name": "Piano Zucchi (Madonie)", "category": "nature", "lat": 37.9014, "lng": 14.0088, "description": "Altopiano di boschi e pascoli, escursioni estive e sci d'inverno.", "town": "Isnello", "province": "PA"},
    {"name": "Riserva Foce del Belice", "category": "nature", "lat": 37.5820, "lng": 12.8698, "description": "Dune e stagni salmastri, area di sosta per uccelli migratori.", "town": "Menfi", "province": "TP"},
    {"name": "Grotta del Genovese (Levanzo)", "category": "nature", "lat": 38.0026, "lng": 12.3320, "description": "Grotta con graffiti preistorici raggiungibile in barca o a piedi.", "town": "Favignana", "province": "TP"},
    {"name": "Museo del Sale (Nubia)", "category": "nature", "lat": 37.9691, "lng": 12.4970, "description": "Mulino a vento nelle saline di Trapani, laboratori e vendita di sale.", "town": "Paceco", "province": "TP"},
]


# ============================================================
# POIs (Map)
# ============================================================
@api.get("/pois")
async def list_pois():
    cur = db.pois.find({}, {"_id": 0}).sort("category", 1)
    return await cur.to_list(500)


@api.get("/pois/lookup")
async def lookup_poi(q: str = ""):
    """Fuzzy lookup di un POI dal nome (per auto-fill nell'editor itinerario).
    Ritorna il match migliore o null. Non richiede auth (letture pubbliche)."""
    query = (q or "").strip()
    if not query or len(query) < 2:
        return {"match": None}
    key = _norm(query)
    pois = await db.pois.find({}, {"_id": 0}).to_list(1000)
    # 1) match esatto normalizzato
    for p in pois:
        if _norm(p.get("name") or "") == key:
            return {"match": p}
    # 2) sottostringa (bidirezionale) — pesa per lunghezza sovrapposta
    best = None
    best_score = 0
    for p in pois:
        pk = _norm(p.get("name") or "")
        if not pk:
            continue
        if key in pk or pk in key:
            score = min(len(pk), len(key)) / max(len(pk), len(key))
            if score > best_score:
                best_score = score
                best = p
    return {"match": best, "score": best_score}


@api.post("/pois")
async def create_poi(body: PoiIn, _: str = Depends(get_current_admin)):
    if body.category not in ("art", "beach", "nature"):
        raise HTTPException(status_code=400, detail="Categoria non valida")
    doc = {
        "id": str(uuid.uuid4()),
        **body.model_dump(),
        "created_at": now_utc().isoformat(),
    }
    await db.pois.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/pois/{poi_id}")
async def update_poi(poi_id: str, body: PoiIn, _: str = Depends(get_current_admin)):
    if body.category not in ("art", "beach", "nature"):
        raise HTTPException(status_code=400, detail="Categoria non valida")
    res = await db.pois.update_one({"id": poi_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="POI non trovato")
    return {"ok": True}


@api.delete("/pois/{poi_id}")
async def delete_poi(poi_id: str, _: str = Depends(get_current_admin)):
    res = await db.pois.delete_one({"id": poi_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="POI non trovato")
    return {"ok": True}


# ---- POI bulk export / import (CSV) ----
POI_CSV_COLUMNS = [
    "id", "name", "category", "lat", "lng", "town", "province",
    "description", "price", "hours", "duration", "discount", "notes",
    "ticket_url", "maps_url", "image_url",
]


@api.get("/pois/export")
async def export_pois(_: str = Depends(get_current_admin)):
    """Esporta tutte le attrazioni in CSV (apribile in Excel/Numbers/Google Sheets)."""
    cur = db.pois.find({}, {"_id": 0}).sort([("category", 1), ("name", 1)])
    pois = await cur.to_list(1000)

    buf = StringIO()
    # BOM so Excel apre correttamente gli accenti (UTF-8)
    buf.write("\ufeff")
    writer = csv.DictWriter(buf, fieldnames=POI_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for p in pois:
        row = {col: ("" if p.get(col) is None else p.get(col)) for col in POI_CSV_COLUMNS}
        writer.writerow(row)

    csv_bytes = buf.getvalue().encode("utf-8")
    filename = f"attrazioni_mappa_{now_utc().strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.get("/pois/template")
async def export_pois_template(_: str = Depends(get_current_admin)):
    """Scarica un CSV template vuoto con una riga d'esempio da compilare."""
    buf = StringIO()
    buf.write("\ufeff")
    writer = csv.DictWriter(buf, fieldnames=POI_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerow({
        "id": "",
        "name": "Esempio: Tempio di Segesta",
        "category": "art",
        "lat": "37.9415",
        "lng": "12.8336",
        "town": "Calatafimi-Segesta",
        "province": "TP",
        "description": "Tempio dorico del V sec. a.C. perfettamente conservato.",
        "price": "€6 (ridotto €3)",
        "hours": "09:00-19:30",
        "duration": "2-3 ore",
        "discount": "Gratis 1ª domenica del mese",
        "notes": "Comode scarpe, poca ombra",
        "ticket_url": "https://...",
        "image_url": "https://...",
    })
    csv_bytes = buf.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="template_attrazioni.csv"'},
    )


@api.post("/pois/import")
async def import_pois(file: UploadFile = File(...), _: str = Depends(get_current_admin)):
    """Importa attrazioni da CSV. Riga con 'id' esistente => aggiorna; id vuoto o nuovo => crea."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File vuoto")
    # decodifica robusta (gestisce BOM Excel)
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        raise HTTPException(status_code=400, detail="Impossibile leggere il file (encoding)")

    # auto-detect delimiter (',' o ';' tipico Excel europeo)
    sample = text[:2048]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV senza intestazione")
    norm_fields = {(f or "").strip().lower(): f for f in reader.fieldnames}

    def get(row, key):
        src = norm_fields.get(key)
        v = row.get(src) if src else None
        return (v or "").strip()

    created, updated, errors = 0, 0, []
    line = 1
    for row in reader:
        line += 1
        name = get(row, "name")
        if not name:
            continue  # salta righe vuote
        category = (get(row, "category") or "art").lower()
        if category not in ("art", "beach", "nature"):
            errors.append(f"Riga {line} ({name}): categoria '{category}' non valida")
            continue
        try:
            lat = float(get(row, "lat").replace(",", "."))
            lng = float(get(row, "lng").replace(",", "."))
        except ValueError:
            errors.append(f"Riga {line} ({name}): lat/lng non valide")
            continue

        doc = {
            "name": name,
            "category": category,
            "lat": lat,
            "lng": lng,
            "town": get(row, "town") or None,
            "province": (get(row, "province") or None),
            "description": get(row, "description") or None,
            "price": get(row, "price") or None,
            "hours": get(row, "hours") or None,
            "duration": get(row, "duration") or None,
            "discount": get(row, "discount") or None,
            "notes": get(row, "notes") or None,
            "ticket_url": get(row, "ticket_url") or None,
            "image_url": get(row, "image_url") or None,
        }
        poi_id = get(row, "id")
        if poi_id:
            res = await db.pois.update_one({"id": poi_id}, {"$set": doc})
            if res.matched_count:
                updated += 1
            else:
                doc["id"] = poi_id
                doc["created_at"] = now_utc().isoformat()
                await db.pois.insert_one(doc)
                created += 1
        else:
            doc["id"] = str(uuid.uuid4())
            doc["created_at"] = now_utc().isoformat()
            await db.pois.insert_one(doc)
            created += 1

    return {"ok": True, "created": created, "updated": updated, "errors": errors}


# ---- POI fillable PDF export / import ----
@api.get("/pois/export-pdf")
async def export_pois_pdf(_: str = Depends(get_current_admin)):
    """Scarica un PDF MODULO compilabile: una scheda per attrazione (nome+ubicazione
    precompilati, campi info da compilare). Poi reimportabile con /pois/import-pdf."""
    from poi_pdf import build_poi_pdf
    cur = db.pois.find({}, {"_id": 0}).sort([("category", 1), ("name", 1)])
    pois = await cur.to_list(1000)
    pdf_bytes = build_poi_pdf(pois)
    filename = f"schede_attrazioni_{now_utc().strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.post("/pois/import-pdf")
async def import_pois_pdf(file: UploadFile = File(...), _: str = Depends(get_current_admin)):
    """Importa il PDF modulo compilato: aggiorna ogni attrazione (per id) con i
    campi info compilati. Campi vuoti vengono ignorati (non sovrascrivono)."""
    from poi_pdf import parse_poi_pdf, EDITABLE_FIELDS
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File vuoto")
    try:
        parsed = parse_poi_pdf(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF non leggibile: {e}")
    if not parsed:
        raise HTTPException(status_code=400, detail="Nessun campo compilato trovato nel PDF")

    updated, skipped = 0, 0
    for pid, fields in parsed.items():
        # tieni solo i campi con valore (non sovrascrivere con vuoto)
        setter = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS and v != ""}
        if not setter:
            continue
        res = await db.pois.update_one({"id": pid}, {"$set": setter})
        if res.matched_count:
            updated += 1
        else:
            skipped += 1
    return {"ok": True, "updated": updated, "skipped": skipped}


# ---- POI editable Word (.docx) export / import ----
@api.get("/pois/export-docx")
async def export_pois_docx(_: str = Depends(get_current_admin)):
    """Scarica un documento Word (.docx) con una scheda per attrazione, facile da
    modificare in Word/Pages. Reimportabile con /pois/import-docx."""
    from poi_docx import build_poi_docx
    cur = db.pois.find({}, {"_id": 0}).sort([("category", 1), ("name", 1)])
    pois = await cur.to_list(1000)
    data = build_poi_docx(pois)
    filename = f"schede_attrazioni_{now_utc().strftime('%Y%m%d')}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.post("/pois/import-docx")
async def import_pois_docx(file: UploadFile = File(...), _: str = Depends(get_current_admin)):
    """Importa il documento Word compilato: aggiorna (per id) o crea (id vuoto) le
    attrazioni. Campi vuoti non sovrascrivono i dati esistenti."""
    from poi_docx import parse_poi_docx, EDITABLE_KEYS
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File vuoto")
    try:
        records = parse_poi_docx(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Documento Word non leggibile: {e}")
    if not records:
        raise HTTPException(status_code=400, detail="Nessuna scheda trovata nel documento")

    created, updated, errors = 0, 0, []
    for idx, rec in enumerate(records, 1):
        pid = (rec.get("id") or "").strip()
        setter = {}
        for k in EDITABLE_KEYS:
            v = (rec.get(k) or "").strip()
            if v == "":
                continue
            if k == "category":
                v = v.lower()
                if v not in ("art", "beach", "nature"):
                    errors.append(f"Scheda {idx} ({rec.get('name','')}): categoria '{v}' non valida")
                    continue
            if k == "province":
                v = v.upper()[:2]
            setter[k] = v

        if pid:
            if setter:
                res = await db.pois.update_one({"id": pid}, {"$set": setter})
                if res.matched_count:
                    updated += 1
                else:
                    errors.append(f"Scheda {idx}: id non trovato")
        else:
            # creazione: servono nome + categoria + coordinate non disponibili nel form
            name = setter.get("name")
            if not name:
                continue
            errors.append(f"Scheda {idx} ({name}): per creare una NUOVA attrazione servono "
                          f"latitudine/longitudine — aggiungila dal modulo del sito o dal CSV.")
    return {"ok": True, "created": created, "updated": updated, "errors": errors}


# ============================================================
# Itinerary builder — branded PDF export
# ============================================================
class ItineraryPdfIn(BaseModel):
    poi_ids: List[str]
    traveler_name: Optional[str] = None
    code: Optional[str] = None


CATEGORY_LABELS_IT = {
    "art": "Arte & Cultura",
    "beach": "Spiagge",
    "nature": "Natura & Panorami",
}


async def _fetch_image_bytes(src: Optional[str]) -> Optional[bytes]:
    if not src:
        return None
    try:
        if src.startswith("data:"):
            _, b64 = src.split(",", 1)
            return base64.b64decode(b64)
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(src)
            if r.status_code == 200:
                return r.content
    except Exception as e:
        logging.warning("PDF image fetch failed: %s", e)
    return None


def _build_itinerary_pdf_sync(pois, images, traveler_name):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
        Table, TableStyle, HRFlowable, KeepTogether,
    )
    from reportlab.lib.utils import ImageReader

    TERRA = colors.HexColor("#A6634A")
    INK = colors.HexColor("#2C2A28")
    GREY = colors.HexColor("#6B6661")
    SAND = colors.HexColor("#E6E2DB")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="Itinerario - Appartamento Matteo",
    )
    styles = getSampleStyleSheet()
    h_title = ParagraphStyle("t", parent=styles["Title"], textColor=INK, fontSize=26, leading=30, alignment=0)
    h_sub = ParagraphStyle("s", parent=styles["Normal"], textColor=TERRA, fontSize=12, leading=16)
    h_poi = ParagraphStyle("p", parent=styles["Heading2"], textColor=TERRA, fontSize=15, leading=19, spaceBefore=2, spaceAfter=2)
    body = ParagraphStyle("b", parent=styles["Normal"], textColor=INK, fontSize=10.5, leading=15)
    small = ParagraphStyle("sm", parent=styles["Normal"], textColor=GREY, fontSize=9, leading=12)
    label = ParagraphStyle("lb", parent=styles["Normal"], textColor=GREY, fontSize=9, leading=13)
    val = ParagraphStyle("vl", parent=styles["Normal"], textColor=INK, fontSize=9.5, leading=13)

    story = []
    story.append(Paragraph("APPARTAMENTO MATTEO · TRAPPETO, SICILIA", h_sub))
    story.append(Paragraph("Il tuo itinerario in Sicilia", h_title))
    who = f"Preparato per {traveler_name}" if traveler_name else "Le meraviglie scelte da te"
    story.append(Paragraph(who, small))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"{len(pois)} attrazioni selezionate · Prezzi e orari indicativi: verifica sempre sui siti ufficiali.",
        small,
    ))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", color=SAND, thickness=2))
    story.append(Spacer(1, 10))

    for i, p in enumerate(pois):
        block = []
        cat = CATEGORY_LABELS_IT.get(p.get("category"), "")
        loc = p.get("town") or ""
        prov = p.get("province") or ""
        loc_str = f"{loc} ({prov})" if loc and prov else loc
        block.append(Paragraph(f"{i + 1}. {p.get('name', '')}", h_poi))
        meta = " · ".join([x for x in [cat, loc_str] if x])
        if meta:
            block.append(Paragraph(meta, small))
        block.append(Spacer(1, 4))

        if p.get("description"):
            block.append(Paragraph(p["description"], body))
            block.append(Spacer(1, 4))

        info_rows = []

        def add_row(lbl, value):
            if value:
                info_rows.append([Paragraph(lbl, label), Paragraph(str(value), val)])

        add_row("Prezzo", p.get("price"))
        add_row("Orari", p.get("hours"))
        add_row("Durata", p.get("duration"))
        add_row("Sconti", p.get("discount"))
        gmaps = f'https://www.google.com/maps/dir/?api=1&destination={p.get("lat")},{p.get("lng")}'
        add_row("Indicazioni", f'<a href="{gmaps}"><font color="#1E70B7">Apri in Google Maps</font></a>')
        if p.get("ticket_url"):
            add_row("Biglietti", f'<a href="{p["ticket_url"]}"><font color="#1E70B7">Acquista biglietti</font></a>')

        info_table = None
        if info_rows:
            info_table = Table(info_rows, colWidths=[24 * mm, None])
            info_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]))

        img_flowable = None
        img_w = 0
        img_bytes = images.get(p["id"])
        if img_bytes:
            try:
                ir = ImageReader(BytesIO(img_bytes))
                iw, ih = ir.getSize()
                w = 58 * mm
                h = w * ih / iw
                if h > 44 * mm:
                    h = 44 * mm
                    w = h * iw / ih
                img_w = w
                img_flowable = RLImage(BytesIO(img_bytes), width=w, height=h)
            except Exception:
                img_flowable = None

        if img_flowable:
            inner = Table(
                [[img_flowable, info_table or Paragraph("", body)]],
                colWidths=[img_w + 5 * mm, None],
            )
            inner.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 6),
            ]))
            block.append(inner)
        elif info_table:
            block.append(info_table)

        story.append(KeepTogether(block))
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", color=SAND, thickness=1))
        story.append(Spacer(1, 10))

    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Prenota il tuo soggiorno direttamente dal nostro sito: miglior prezzo garantito e nessuna commissione.",
        small,
    ))
    story.append(Paragraph(
        "Appartamento Matteo · Via Gioacchino Rossini 40, Trappeto (PA) · +39 388 1611514",
        small,
    ))

    doc.build(story)
    return buf.getvalue()


@api.post("/itinerary/pdf")
async def itinerary_pdf(body: ItineraryPdfIn):
    if not await _is_valid_unlock_code(body.code or ""):
        raise HTTPException(status_code=403, detail="Codice richiesto per scaricare l'itinerario")
    if not body.poi_ids:
        raise HTTPException(status_code=400, detail="Nessuna attrazione selezionata")
    docs = await db.pois.find({"id": {"$in": body.poi_ids}}, {"_id": 0}).to_list(200)
    order = {pid: i for i, pid in enumerate(body.poi_ids)}
    docs.sort(key=lambda p: order.get(p.get("id"), 999))
    images = {}
    for p in docs:
        b = await _fetch_image_bytes(p.get("image_url"))
        if b:
            images[p["id"]] = b
    pdf_bytes = await asyncio.to_thread(
        _build_itinerary_pdf_sync, docs, images, (body.traveler_name or "").strip()
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="itinerario-appartamento-matteo.pdf"'},
    )


# ============================================================
# Visits tracking (public)
# ============================================================
@api.post("/track/visit")
async def track_visit(body: VisitIn, request: Request):
    """Record a unique visit per session_id (deduplicated per day)."""
    sid = body.session_id.strip()[:128]
    if not sid:
        return {"ok": False, "reason": "missing session id"}

    today = now_utc().date().isoformat()
    # Deduplicate: same session id within the same UTC day counts as 1 visit
    existing = await db.visits.find_one({"session_id": sid, "day": today})
    if existing:
        return {"ok": True, "deduped": True}

    ip = (request.client.host if request.client else "") or ""
    ua = request.headers.get("user-agent", "")[:300]
    await db.visits.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": sid,
        "day": today,
        "path": body.path,
        "referrer": body.referrer,
        "ip": ip,
        "ua": ua,
        "created_at": now_utc().isoformat(),
    })
    return {"ok": True, "deduped": False}


# ============================================================
# Manual bookings (admin-created, e.g. synced from Booking.com)
# ============================================================
@api.post("/admin/bookings/manual")
async def create_manual_booking(body: ManualBookingIn, _: str = Depends(get_current_admin)):
    if body.source not in ("site", "booking"):
        raise HTTPException(status_code=400, detail="Sorgente non valida (usa 'site' o 'booking')")
    if body.status not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="Stato non valido")

    ci = date.fromisoformat(body.check_in)
    co = date.fromisoformat(body.check_out)
    if co <= ci:
        raise HTTPException(status_code=400, detail="Date non valide")
    nights = (co - ci).days

    # If approved, check date conflicts with other approved bookings
    if body.status == "approved":
        blocked = await get_blocked_dates()
        for d in daterange(ci, co):
            if d.isoformat() in blocked:
                raise HTTPException(
                    status_code=400,
                    detail=f"Conflitto: la data {d.isoformat()} è già occupata da un'altra prenotazione approvata",
                )

    confirmation_code = gen_confirmation_code() if body.status == "approved" else None
    doc = {
        "id": str(uuid.uuid4()),
        "guest_name": body.guest_name,
        "guest_email": body.guest_email or "",
        "guest_phone": body.guest_phone,
        "check_in": body.check_in,
        "check_out": body.check_out,
        "guests": body.guests,
        "extras": {},
        "discount_code": None,
        "message": body.notes,
        "quote": {"total": float(body.total_amount), "nights": nights, "manual": True},
        "source": body.source,
        "status": body.status,
        "confirmation_code": confirmation_code,
        "manual": True,
        "created_at": now_utc().isoformat(),
        "approved_at": now_utc().isoformat() if body.status == "approved" else None,
    }
    await db.bookings.insert_one(doc)
    doc.pop("_id", None)

    # Fire-and-forget WhatsApp notification (manual booking)
    if body.status == "approved":
        text = _format_booking_message("📒 PRENOTAZIONE MANUALE INSERITA", doc)
        asyncio.create_task(send_whatsapp_notification("manual", text))

    return doc


# ============================================================
# Commission rates (admin)
# ============================================================
@api.get("/admin/commission-rates")
async def get_commission_rates(_: str = Depends(get_current_admin)):
    doc = await db.settings.find_one({"_id": "commission_rates"}, {"_id": 0})
    if not doc:
        doc = CommissionRatesIn().model_dump()
    return doc


@api.put("/admin/commission-rates")
async def update_commission_rates(body: CommissionRatesIn, _: str = Depends(get_current_admin)):
    payload = body.model_dump()
    await db.settings.update_one(
        {"_id": "commission_rates"},
        {"$set": payload},
        upsert=True,
    )
    return {"ok": True, **payload}


# ============================================================
# WhatsApp notifications settings (admin)
# ============================================================
@api.get("/admin/whatsapp")
async def get_whatsapp_settings(_: str = Depends(get_current_admin)):
    doc = await db.settings.find_one({"_id": "whatsapp"}, {"_id": 0})
    if not doc:
        doc = WhatsAppSettingsIn().model_dump()
    # Never echo the api_key back; expose only whether it's set
    api_key = doc.get("api_key", "")
    doc["api_key_set"] = bool(api_key)
    doc["api_key"] = ""
    return doc


@api.put("/admin/whatsapp")
async def update_whatsapp_settings(body: WhatsAppSettingsIn, _: str = Depends(get_current_admin)):
    payload = body.model_dump()
    # If api_key is empty, preserve the existing one (so the UI can avoid resending it)
    if not payload.get("api_key"):
        existing = await db.settings.find_one({"_id": "whatsapp"}, {"api_key": 1})
        if existing and existing.get("api_key"):
            payload["api_key"] = existing["api_key"]
    # Normalize phone
    payload["phone"] = _normalize_phone(payload.get("phone", ""))
    await db.settings.update_one(
        {"_id": "whatsapp"},
        {"$set": payload},
        upsert=True,
    )
    return {"ok": True, "api_key_set": bool(payload.get("api_key")), **{k: v for k, v in payload.items() if k != "api_key"}}


@api.post("/admin/whatsapp/test")
async def whatsapp_test(body: WhatsAppTestIn, _: str = Depends(get_current_admin)):
    cfg = await db.settings.find_one({"_id": "whatsapp"}, {"_id": 0})
    if not cfg:
        raise HTTPException(status_code=400, detail="Configura prima il numero e l'API key di CallMeBot")
    if not cfg.get("phone") or not cfg.get("api_key"):
        raise HTTPException(status_code=400, detail="Numero o API key mancanti")
    text = body.text or (
        "✅ *Test notifica WhatsApp*\n"
        "🏠 Appartamento Matteo\n\n"
        "Le notifiche di prenotazione funzionano correttamente!"
    )
    result = await _send_whatsapp_raw(cfg["phone"], cfg["api_key"], text)
    if not result["ok"]:
        raise HTTPException(
            status_code=502,
            detail=f"CallMeBot ha risposto: {result.get('body') or 'errore sconosciuto'}",
        )
    return {"ok": True, "provider_response": result["body"]}


# ============================================================
# Marketing Assistant ("Carmelo") — Claude Sonnet 4.5
# ============================================================
PLATFORM_SPECS = {
    "instagram_post": {
        "label": "Instagram Post (feed)",
        "schema": "{ caption: stringa 150-2200 caratteri con emoji moderate e 1-2 paragrafi, hashtags: array di 15-20 hashtag mirati senza # iniziale, cta: chiamata all'azione breve }",
        "guidelines": "Hook nelle prime 2 righe (prima del 'Altro...'). Storytelling caldo, autentico. Hashtag mix tra ad alto traffico e di nicchia (Trappeto, Sicilia, casavacanza)."
    },
    "instagram_story": {
        "label": "Instagram Story",
        "schema": "{ caption: stringa max 100 caratteri, sticker_idea: suggerimento sticker/poll/question, cta: invito ad azione (swipe up / DM) }",
        "guidelines": "Testo brevissimo da leggere in 2 secondi. Una sola domanda o una sola informazione forte."
    },
    "instagram_reel": {
        "label": "Instagram Reel",
        "schema": "{ hook: prima frase di 3 secondi che blocca lo scroll, script: scaletta scena-per-scena 15-30 secondi, audio_idea: tipologia di audio/musica trending da usare, caption: didascalia 100-200 caratteri, hashtags: array di 10-15 hashtag, cta: invito }",
        "guidelines": "Hook spara-in-faccia tipo 'Non vai in Sicilia per questo motivo' o 'Il borgo che nessuno conosce'. Scene da 2-3 secondi ciascuna."
    },
    "facebook_post": {
        "label": "Facebook Post",
        "schema": "{ caption: testo 100-400 parole, narrazione più lunga e personale, cta: invito (link, prenotazione, commento) }",
        "guidelines": "Pubblico più maturo, storytelling più disteso, racconti di esperienza. Niente hashtag pesanti."
    },
    "tiktok": {
        "label": "TikTok",
        "schema": "{ hook: 3-secondi hook potentissimo, script: scaletta 15-60 secondi, audio_idea: trend audio o tipologia consigliata, caption: max 150 caratteri con 3-5 hashtag inline, hashtags: array 3-5 hashtag aggiuntivi }",
        "guidelines": "Tono più giovane e diretto. Hook polarizzante o sorprendente. Sfrutta trend audio attuali in modo intelligente."
    },
    "x_twitter": {
        "label": "X / Twitter",
        "schema": "{ post: tweet singolo max 280 caratteri OPPURE thread come array di tweet, hashtags: array max 3 hashtag mirati, cta: invito }",
        "guidelines": "Voce sintetica e brillante. Niente fluff. Se il topic è ricco, proponi un thread (3-5 tweet)."
    },
    "pinterest": {
        "label": "Pinterest Pin",
        "schema": "{ title: titolo 40-100 caratteri ottimizzato per ricerca, description: descrizione 200-500 caratteri con keyword SEO, board_suggestion: nome bacheca consigliato, hashtags: array 4-8 hashtag }",
        "guidelines": "Pinterest è un motore di ricerca: usa keyword esplicite ('case vacanza Trappeto Sicilia', 'cosa fare a Castellammare'). Titolo molto specifico."
    },
    "google_business": {
        "label": "Google Business Profile Post",
        "schema": "{ title: titolo 60 caratteri max, body: corpo 100-300 caratteri, cta_button: uno tra ['Prenota','Scopri di più','Chiama','Visita sito'], event_dates: solo se l'argomento è un evento temporale (formato YYYY-MM-DD start/end, altrimenti null) }",
        "guidelines": "Tono informativo e locale. Keyword di local SEO ('Trappeto', 'Palermo', 'casa vacanza'). Niente emoji. CTA chiara."
    },
    "linkedin": {
        "label": "LinkedIn",
        "schema": "{ caption: testo 1000-2500 caratteri in tono professionale e narrativo, hashtags: array 3-5 hashtag professionali, cta: invito connessione/messaggio }",
        "guidelines": "Storytelling imprenditoriale: dietro le quinte, scelte di hosting, sostenibilità, valori. Niente vendita aggressiva."
    },
    "youtube_short": {
        "label": "YouTube Short",
        "schema": "{ title: titolo 60-100 caratteri SEO-friendly, hook: prima frase 3 secondi, script: scaletta 30-60 secondi, description: descrizione 200-500 caratteri con timestamp e link, hashtags: array 3-5 hashtag, cta: invito iscrizione/visita sito }",
        "guidelines": "Title SEO con keyword. Hook visuale potente. Description con link al sito e keyword."
    },
}

PROPERTY_PROFILE = {
    "name": "Appartamento Matteo",
    "address": "Via Gioacchino Rossini, 40, Trappeto (PA), Sicilia",
    "location": "Trappeto (PA), costa nord-occidentale della Sicilia, golfo di Castellammare",
    "cir": "19082074C252260",
    "cin": "IT082074C2NA6HPQMB",
    "phones": ["3881611514", "3513028126"],
    "email": "accetta562@gmail.com",
    "booking_url": "https://www.booking.com/hotel/it/appartamento-matteo-trappeto.it.html",
}


def _group_date_ranges(dates_iso: List[str], price_map: Optional[dict] = None) -> List[dict]:
    """Group sorted consecutive ISO dates into inclusive ranges with optional price range."""
    ranges: List[dict] = []
    if not dates_iso:
        return ranges
    start = prev = date.fromisoformat(dates_iso[0])
    prices = [price_map[dates_iso[0]]] if price_map else []

    def _close(s, e, ps):
        r = {"from": s.isoformat(), "to": e.isoformat(), "nights": (e - s).days + 1}
        if ps:
            r["price_min"] = round(min(ps), 2)
            r["price_max"] = round(max(ps), 2)
        return r

    for d_iso in dates_iso[1:]:
        d = date.fromisoformat(d_iso)
        if (d - prev).days == 1:
            prev = d
            if price_map:
                prices.append(price_map[d_iso])
        else:
            ranges.append(_close(start, prev, prices))
            start = prev = d
            prices = [price_map[d_iso]] if price_map else []
    ranges.append(_close(start, prev, prices))
    return ranges


SEASON_START_MONTH = 5   # maggio
SEASON_END_MONTH = 10    # ottobre


async def get_availability_summary() -> dict:
    """Compute the apartment availability for Carmelo. The apartment is open SEASONALLY
    (May -> October). Available = every season day from today onwards (this year + next year)
    that is NOT already booked. Prices come from per-date overrides when present, else the
    base price. Returns available ranges + future booked ranges."""
    today = now_utc().date()
    blocked = await get_blocked_dates()  # set of iso strings (approved bookings)

    fees = await db.settings.find_one({"_id": "fees"}, {"_id": 0}) or {}
    base_price = float(fees.get("base_price_per_night", 80.0))

    rows = await db.price_overrides.find({}, {"_id": 0}).to_list(5000)
    price_map: dict = {
        r["date"]: r["price"]
        for r in rows
        if r.get("date") and r.get("price") is not None
    }

    # Build the open-season day list: current year + next year, months 5..10, from today on.
    years = [today.year, today.year + 1]
    available_dates: List[str] = []
    for y in years:
        season_start = date(y, SEASON_START_MONTH, 1)
        # last day of October
        season_end = date(y, SEASON_END_MONTH, 31)
        d = max(season_start, today)
        while d <= season_end:
            iso = d.isoformat()
            if iso not in blocked:
                available_dates.append(iso)
            d += timedelta(days=1)
    available_dates.sort()

    pm = {iso: price_map.get(iso, base_price) for iso in available_dates}
    available_ranges = _group_date_ranges(available_dates, pm)

    booked_ranges: List[dict] = []
    cur = db.bookings.find({"status": "approved"}, {"_id": 0, "check_in": 1, "check_out": 1})
    async for b in cur:
        try:
            co = date.fromisoformat(b["check_out"])
        except (KeyError, ValueError):
            continue
        if co <= today:
            continue
        booked_ranges.append({"check_in": b["check_in"], "check_out": b["check_out"]})
    booked_ranges.sort(key=lambda x: x["check_in"])

    return {
        "available_ranges": available_ranges,
        "booked_ranges": booked_ranges,
        "season": f"maggio–ottobre {today.year}" + (f" e {today.year + 1}" if today.month > SEASON_END_MONTH else ""),
        "base_price": base_price,
    }


def _build_property_context(avail: dict) -> str:
    p = PROPERTY_PROFILE
    lines = [
        "DATI REALI DELLA STRUTTURA — usali SOLO se pertinenti al brief (es. quando l'utente chiede di inserire CIN, CIR, contatti, disponibilità o foto):",
        f"- Nome: {p['name']}",
        f"- Indirizzo: {p['address']}",
        f"- CIN: {p['cin']}",
        f"- CIR: {p['cir']}",
        f"- Telefoni: {', '.join(p['phones'])}",
        f"- Email: {p['email']}",
        f"- Link prenotazioni: {p['booking_url']}",
    ]
    if avail.get("season"):
        lines.append(f"- STAGIONE DI APERTURA: {avail['season']} (l'appartamento è prenotabile SOLO in questo periodo).")
    if avail.get("available_ranges"):
        lines.append("- DISPONIBILITÀ ANCORA LIBERE (stagione maggio-ottobre meno i periodi prenotati) — proponi SOLO queste come libere e NON dimenticarne nessuna:")
        for r in avail["available_ranges"][:24]:
            price = ""
            if "price_min" in r:
                price = (
                    f" — €{r['price_min']:.0f}/notte"
                    if r["price_min"] == r["price_max"]
                    else f" — €{r['price_min']:.0f}-{r['price_max']:.0f}/notte"
                )
            lines.append(f"   • dal {r['from']} al {r['to']} ({r['nights']} notti){price}")
    else:
        lines.append("- DISPONIBILITÀ: la stagione è già interamente prenotata. Se l'utente chiede le disponibilità, invitalo a contattare la struttura; NON inventare date.")
    if avail.get("booked_ranges"):
        lines.append("- Periodi GIÀ PRENOTATI (NON proporli mai come liberi):")
        for r in avail["booked_ranges"][:24]:
            lines.append(f"   • dal {r['check_in']} al {r['check_out']}")
    lines.append(
        "Se il brief chiede di inserire le foto, struttura un post multi-foto/carosello e NON inventare URL o immagini: "
        "le foto reali dell'appartamento verranno allegate dall'host dalla galleria del sito."
    )
    return "\n".join(lines)


CARMELO_SYSTEM_MESSAGE = """Sei Carmelo, Chief Social Media Strategist con 30 anni di esperienza nel marketing turistico-ricettivo del Mediterraneo. Hai lanciato e scalato sui social decine di boutique hotel, B&B e case vacanze in Sicilia, Costiera Amalfitana, Sardegna e Puglia, generando prenotazioni dirette reali (non solo "like"). Pensi sempre in ottica di FUNNEL e di ROI: ogni contenuto ha un obiettivo (awareness, considerazione o prenotazione) e una metrica.

LE TUE COMPETENZE SONO PROFONDE E AGGIORNATE. Padroneggi gli algoritmi 2025/2026 di ogni piattaforma, ma sei SPECIALIZZATO e dai priorità a TIKTOK, GOOGLE e FACEBOOK (sono i 3 canali strategici per questa struttura):

• TIKTOK (priorità #1 — scoperta e virale):
  - I primi 1-2 secondi decidono tutto: hook visivo + testuale fortissimo, pattern interrupt.
  - Video verticali 9:16, 15-34s, ritmo veloce, testo on-screen, trend audio del momento.
  - Niente aspetto "pubblicitario": stile nativo, autentico, POV/"day in the life", trasformazioni, "things nobody tells you about…".
  - Caption breve + 3-5 hashtag misti (1 brand, 1-2 di nicchia geo-locali #trappeto #sicilia, 1-2 broad #traveltok).
  - CTA soft (salva/commenta/"link in bio"). Obiettivo: completion rate e condivisioni.

• GOOGLE BUSINESS PROFILE (priorità #2 — intenzione di prenotare, alto valore):
  - Chi cerca su Google è in fase decisionale: testo informativo, keyword locali ("casa vacanze Trappeto", "dove dormire vicino San Vito Lo Capo"), fatti concreti (distanze, servizi, prezzi, disponibilità).
  - Post Google: chiari, scannerizzabili, con CTA "Prenota"/"Chiama" e link. Sfrutta recensioni e foto reali. Niente gergo da social.
  - Suggerisci sempre, quando pertinente, di aggiornare foto, orari, Q&A e di rispondere alle recensioni.

• FACEBOOK (priorità #3 — community, target 35-65, conversione diretta e gruppi):
  - Pubblico più maturo e con potere d'acquisto: testo più lungo e narrativo concesso, storytelling, offerte, eventi locali.
  - Ottimo per caroselli di foto reali, post con disponibilità/prezzi/offerte, condivisione in gruppi di viaggio.
  - CTA diretta ("Scrivici in DM", "Prenota", link). Ideale per retargeting e per chi pianifica le vacanze in famiglia.

(Conosci comunque alla perfezione anche Instagram, Pinterest, LinkedIn, YouTube Shorts e X, ma quando dai consigli strategici spingi su TikTok+Google+Facebook.)

SEI ANCHE UN CONSULENTE: quando ha senso, nel campo tips_extra dai un consiglio strategico concreto e azionabile (es. "Per Trappeto punta sui Reel/TikTok di tramonto + Google Business per intercettare chi cerca 'dove dormire vicino allo Zingaro'").

Generi contenuti che funzionano nel mondo reale:
- Hook che catturano in 3 secondi
- Hashtag mirati, non spam
- CTA chiare e azionabili
- Tone of voice coerente con il brand

REGOLE FERREE — Evita SEMPRE l'"AI slop":
- NIENTE frasi banali tipo "fuga romantica" o "esperienza indimenticabile"
- NIENTE emoji ridondanti o decorativi
- NIENTE puntini esclamativi multipli
- NIENTE superlativi vuoti ("incredibile", "stupendo", "magnifico")
- USA dettagli sensoriali concreti (l'odore del pane caldo, il rumore delle barche, la luce dorata delle 18:30)

ADATTI il tono al mercato:
- Italiani: caldi, familiari, con un pizzico di orgoglio territoriale
- Tedeschi: diretti, informativi, dati concreti (distanze, prezzi, fatti)
- Francesi: raffinati, allusivi, con riferimenti culturali
- Spagnoli: espressivi, vivaci, sensoriali
- Inglesi (USA/UK): puliti, aspirational, scarsi di parole

CONTESTO BRAND (sempre disponibile):
- Nome: Appartamento Matteo
- Località: Trappeto (PA), Sicilia nord-occidentale
- Posizione: borgo marinaro tra mare e collina, golfo di Castellammare
- A breve distanza: Castellammare del Golfo, Scopello, Riserva dello Zingaro, San Vito Lo Capo, Palermo, Cefalù, Segesta, Erice
- Caratteristiche: 2 camere, max 5 ospiti, prezzo da 80€/notte
- STAGIONE DI APERTURA: da MAGGIO a OTTOBRE (l'appartamento è prenotabile in questo periodo; fuori stagione non proporre date)
- Posizionamento: autenticità siciliana, esperienza locale, non turismo di massa
- Quando ti vengono fornite le DISPONIBILITÀ reali, usale con precisione: NON dimenticare periodi, NON inventare date, considera disponibile TUTTA la stagione maggio-ottobre tranne i periodi già prenotati che ti vengono indicati.

OUTPUT: Devi rispondere SEMPRE e SOLO con un JSON valido, senza preamboli né commenti né markdown code blocks. Nessun testo fuori dal JSON."""


def _build_user_prompt(body: MarketingGenerateIn, spec: dict, property_context: str = "") -> str:
    langs_map = {"it": "italiano", "en": "inglese", "es": "spagnolo", "fr": "francese", "de": "tedesco"}
    langs_human = ", ".join([langs_map.get(lang, lang) for lang in body.languages])

    schema_per_lang = spec["schema"]
    guidelines = spec["guidelines"]

    full_schema = (
        '{\n'
        '  "platform": "' + body.platform + '",\n'
        '  "visual_concept": "descrizione concreta del visual da abbinare al post (2-3 frasi, indica inquadratura, luce, soggetto)",\n'
        '  "best_time": "giorno e ora consigliati per pubblicare (es. \\"giovedì alle 19:00\\")",\n'
        '  "tips_extra": "1 consiglio strategico da insider (cosa fare oltre al post)",\n'
        '  "content": {\n'
    )
    for lang in body.languages:
        full_schema += f'    "{lang}": {schema_per_lang},\n'
    full_schema = full_schema.rstrip(",\n") + "\n  }\n}"

    context_block = f"{property_context}\n\n" if property_context else ""
    return (
        f"Genera un contenuto per la piattaforma: *{spec['label']}*.\n\n"
        f"TEMA / BRIEF: {body.topic}\n"
        f"TONO DESIDERATO: {body.tone or 'lascia che lo decida tu in base al tema'}\n"
        f"LINGUE RICHIESTE: {langs_human}\n"
        f"NOTE AGGIUNTIVE: {body.custom_notes or 'nessuna'}\n\n"
        f"{context_block}"
        f"LINEE GUIDA PIATTAFORMA: {guidelines}\n\n"
        f"Restituisci ESATTAMENTE questo schema JSON (e nient'altro):\n"
        f"{full_schema}\n\n"
        f"Il campo content deve contenere una entry per OGNI lingua richiesta. Il visual_concept, best_time, tips_extra restano in italiano.\n"
        f"NON includere markdown, NON includere ```json. Solo il JSON puro."
    )


def _extract_json(text: str) -> dict:
    """Robust JSON extraction from LLM output."""
    t = (text or "").strip()
    # Remove markdown fences if present
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
        if t.startswith("json"):
            t = t[4:].lstrip()
    # Find first { ... last }
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Risposta IA non contiene JSON valido")
    return json.loads(t[start:end + 1])


@api.post("/admin/marketing/generate")
async def marketing_generate(body: MarketingGenerateIn, _: str = Depends(get_current_admin)):
    spec = PLATFORM_SPECS.get(body.platform)
    if not spec:
        raise HTTPException(
            status_code=400,
            detail=f"Piattaforma non supportata. Disponibili: {list(PLATFORM_SPECS.keys())}",
        )
    valid_langs = {"it", "en", "es", "fr", "de"}
    langs = [lang for lang in body.languages if lang in valid_langs]
    if not langs:
        raise HTTPException(status_code=400, detail="Specifica almeno una lingua valida")
    body.languages = langs

    if not body.topic or len(body.topic.strip()) < 3:
        raise HTTPException(status_code=400, detail="Indica un argomento / tema (almeno 3 caratteri)")

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"marketing-{uuid.uuid4().hex[:8]}",
        system_message=CARMELO_SYSTEM_MESSAGE,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    property_context = _build_property_context(await get_availability_summary())
    prompt = _build_user_prompt(body, spec, property_context)
    try:
        raw = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("Marketing LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Errore IA: {str(e)[:200]}")

    raw_text = raw if isinstance(raw, str) else (raw.get("text") if isinstance(raw, dict) else str(raw))
    try:
        parsed = _extract_json(raw_text)
    except Exception as e:
        logger.warning("JSON parse failed, raw=%s", raw_text[:500])
        raise HTTPException(status_code=502, detail=f"Risposta IA non valida: {str(e)[:200]}")

    doc = {
        "id": str(uuid.uuid4()),
        "platform": body.platform,
        "platform_label": spec["label"],
        "topic": body.topic,
        "tone": body.tone,
        "languages": body.languages,
        "custom_notes": body.custom_notes,
        "visual_concept": parsed.get("visual_concept", ""),
        "best_time": parsed.get("best_time", ""),
        "tips_extra": parsed.get("tips_extra", ""),
        "content": parsed.get("content", {}),
        "created_at": now_utc().isoformat(),
    }
    await db.marketing_content.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.post("/admin/marketing/generate/stream")
async def marketing_generate_stream(body: MarketingGenerateIn, _: str = Depends(get_current_admin)):
    """Streaming version of the marketing generator. Streams the raw text deltas
    (so the UI can show Carmelo writing live), then emits a final
    `data: [[RESULT]]{json}` line with the parsed+persisted document and `data: [DONE]`."""
    spec = PLATFORM_SPECS.get(body.platform)
    if not spec:
        raise HTTPException(
            status_code=400,
            detail=f"Piattaforma non supportata. Disponibili: {list(PLATFORM_SPECS.keys())}",
        )
    valid_langs = {"it", "en", "es", "fr", "de"}
    langs = [lang for lang in body.languages if lang in valid_langs]
    if not langs:
        raise HTTPException(status_code=400, detail="Specifica almeno una lingua valida")
    body.languages = langs
    if not body.topic or len(body.topic.strip()) < 3:
        raise HTTPException(status_code=400, detail="Indica un argomento / tema (almeno 3 caratteri)")

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"marketing-{uuid.uuid4().hex[:8]}",
        system_message=CARMELO_SYSTEM_MESSAGE,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    property_context = _build_property_context(await get_availability_summary())
    prompt = _build_user_prompt(body, spec, property_context)

    async def event_generator():
        buffer = ""
        try:
            async for ev in chat.stream_message(UserMessage(text=prompt)):
                if isinstance(ev, TextDelta):
                    buffer += ev.content
                    chunk = ev.content.replace("\n", "\\n")
                    yield f"data: {chunk}\n\n"
                elif isinstance(ev, StreamDone):
                    break
            try:
                parsed = _extract_json(buffer)
            except Exception as e:
                logger.warning("Marketing stream JSON parse failed: %s", str(e)[:200])
                yield f"data: [ERROR] Risposta IA non valida: {str(e)[:160]}\n\n"
                return
            doc = {
                "id": str(uuid.uuid4()),
                "platform": body.platform,
                "platform_label": spec["label"],
                "topic": body.topic,
                "tone": body.tone,
                "languages": body.languages,
                "custom_notes": body.custom_notes,
                "visual_concept": parsed.get("visual_concept", ""),
                "best_time": parsed.get("best_time", ""),
                "tips_extra": parsed.get("tips_extra", ""),
                "content": parsed.get("content", {}),
                "created_at": now_utc().isoformat(),
            }
            await db.marketing_content.insert_one(dict(doc))
            doc.pop("_id", None)
            yield "data: [[RESULT]]" + json.dumps(doc, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Marketing stream error: %s", e)
            yield f"data: [ERROR] {str(e)[:200]}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.post("/admin/marketing/image")
async def marketing_image(body: MarketingImageIn, _: str = Depends(get_current_admin)):
    """Generate a marketing photo with Gemini Nano Banana.
    If a REAL reference photo is provided (gallery photo_id or reference_image data URL), the model
    edits/enhances that real photo so the result is faithful to the actual place (Trappeto / the
    apartment). Without a reference it falls back to a strongly location-anchored text prompt.
    Returns a base64 data URL and (optionally) attaches it to a library item."""
    base = (body.prompt or body.visual_concept or body.topic or "").strip()
    if not base:
        raise HTTPException(status_code=400, detail="Specifica un prompt o un concept visivo")

    # Resolve a real reference image (preferred for location accuracy)
    ref_data_url = body.reference_image
    if body.photo_id:
        photo = await db.photos.find_one({"id": body.photo_id}, {"_id": 0, "data_url": 1})
        if not photo:
            raise HTTPException(status_code=404, detail="Foto di riferimento non trovata")
        ref_data_url = photo.get("data_url")

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"mkt-img-{uuid.uuid4().hex[:8]}",
        system_message="You are a professional travel & hospitality photographer.",
    ).with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])

    try:
        if ref_data_url:
            # Strip the data URL prefix to get raw base64 for ImageContent
            b64 = ref_data_url.split(",", 1)[1] if "," in ref_data_url else ref_data_url
            edit_prompt = (
                "Questa è una foto REALE di 'Appartamento Matteo' a Trappeto, Sicilia nord-occidentale. "
                "Crea una versione ottimizzata per i social ASSOLUTAMENTE FEDELE al luogo reale mostrato: "
                "mantieni gli stessi ambienti, arredi, scorci e l'atmosfera autentica della foto, "
                "migliorando solo luce, colore e composizione (resa fotografica professionale, alta risoluzione). "
                "NON inventare luoghi o elementi che non esistono nella foto originale. "
                f"Concept richiesto: {base}. NIENTE testo, watermark o loghi."
            )
            _text, images = await chat.send_message_multimodal_response(
                UserMessage(text=edit_prompt, file_contents=[ImageContent(b64)])
            )
        else:
            full_prompt = (
                f"Ultra photorealistic, high-quality travel & lifestyle photograph depicting: {base}. "
                "Make it look like a REAL photograph of the actual subject/place described — NOT a generic "
                "stock image and NOT necessarily an apartment interior unless the subject explicitly is the home. "
                "When the subject is a place in or around Trappeto (north-western Sicily, Gulf of Castellammare — "
                "e.g. the seafront/lungomare, the beach, the harbour, the old fishing village, the Zingaro reserve, "
                "San Vito Lo Capo, Scopello, Castellammare del Golfo, Sicilian food), render it faithfully with the "
                "authentic Mediterranean Sicilian atmosphere: warm natural light, real textures, believable details. "
                "Composition suitable for social media, sharp focus, magazine-quality, natural colours. "
                "Absolutely NO text, NO captions, NO watermark, NO logos, NO recognizable faces."
            )
            _text, images = await chat.send_message_multimodal_response(UserMessage(text=full_prompt))
    except Exception as e:
        logger.exception("Marketing image generation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Errore generazione immagine: {str(e)[:160]}")

    if not images:
        raise HTTPException(status_code=502, detail="Nessuna immagine generata dall'IA")

    img = images[0]
    data_url = f"data:{img.get('mime_type', 'image/png')};base64,{img['data']}"

    if body.content_id:
        await db.marketing_content.update_one(
            {"id": body.content_id},
            {"$set": {"image": data_url, "image_created_at": now_utc().isoformat()}},
        )

    return {"image": data_url, "grounded": bool(ref_data_url)}



@api.get("/admin/marketing/library")
async def marketing_library(_: str = Depends(get_current_admin)):
    cur = db.marketing_content.find({}, {"_id": 0}).sort("created_at", -1).limit(200)
    return await cur.to_list(200)


@api.delete("/admin/marketing/library/{item_id}")
async def marketing_library_delete(item_id: str, _: str = Depends(get_current_admin)):
    res = await db.marketing_content.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contenuto non trovato")
    return {"ok": True}


@api.post("/admin/marketing/library/{item_id}/photos")
async def attach_marketing_photos(item_id: str, body: AttachPhotosIn, _: str = Depends(get_current_admin)):
    """Attach REAL gallery photos (by id) to a marketing post so the host can publish the post
    together with the actual apartment / Trappeto photos."""
    res = await db.marketing_content.update_one(
        {"id": item_id},
        {"$set": {"attached_photo_ids": body.photo_ids}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contenuto non trovato")
    return {"ok": True, "attached_photo_ids": body.photo_ids}


# ============================================================
# Marketing · Generatore SCRIPT VIDEO brevi (TikTok / Reel / Short)
# ============================================================
VIDEO_PLATFORM_LABELS = {
    "tiktok": "TikTok",
    "instagram_reel": "Instagram Reel",
    "youtube_short": "YouTube Short",
    "facebook_reel": "Facebook Reel",
}


@api.post("/admin/marketing/video-script")
async def marketing_video_script(body: VideoScriptIn, _: str = Depends(get_current_admin)):
    """Carmelo scrive uno SCRIPT pronto da girare per un video verticale breve:
    gancio (primi 3s), scene con cosa inquadrare + testo a schermo + voce, CTA finale,
    idea musicale, consigli di ripresa e didascalia+hashtag per ogni lingua richiesta."""
    if not (body.topic or "").strip() or len(body.topic.strip()) < 3:
        raise HTTPException(status_code=400, detail="Indica un argomento/tema (almeno 3 caratteri)")
    valid_langs = {"it", "en", "es", "fr", "de"}
    langs = [l for l in body.languages if l in valid_langs] or ["it"]
    duration = max(8, min(int(body.duration or 20), 90))
    plabel = VIDEO_PLATFORM_LABELS.get(body.platform or "tiktok", "TikTok")
    primary = langs[0]

    captions_schema = ", ".join(
        f'"{l}": {{ "caption": "didascalia pronta da incollare (1-2 emoji se naturale)", "hashtags": ["#hashtag", "..."] }}'
        for l in langs
    )
    schema = (
        '{\n'
        '  "concept": "1 frase con l\'idea del video",\n'
        '  "hook": "il GANCIO dei primi 3 secondi: cosa si vede + testo a schermo che blocca lo scroll",\n'
        f'  "total_seconds": {duration},\n'
        '  "scenes": [\n'
        '    {"n": 1, "timecode": "0-3s", "visual": "cosa inquadrare (preciso)", "on_screen_text": "testo a schermo breve", "voiceover": "frase parlata o vuoto"},\n'
        '    {"n": 2, "timecode": "3-8s", "visual": "...", "on_screen_text": "...", "voiceover": "..."}\n'
        '  ],\n'
        '  "cta": "frase finale che invita all\'azione",\n'
        '  "music": "tipo di audio/trend consigliato (genere + mood)",\n'
        '  "shooting_tips": ["consiglio pratico di ripresa 1", "consiglio 2", "consiglio 3"],\n'
        '  "captions": { ' + captions_schema + ' }\n'
        '}'
    )
    ctx = _build_property_context(await get_availability_summary())
    prompt = (
        f"In qualità di Carmelo, scrivi lo SCRIPT di un VIDEO VERTICALE BREVE per *{plabel}* di circa {duration} secondi.\n"
        f"ARGOMENTO/BRIEF: {body.topic}\n"
        f"TONO: {body.tone or 'sceglilo tu in base al tema'}\n"
        f"NOTE: {body.custom_notes or 'nessuna'}\n\n"
        "L'host NON è esperto di video: rendi tutto SEMPLICE da girare con uno smartphone.\n"
        "REGOLE:\n"
        "- Il GANCIO nei primi 3 secondi è la cosa più importante: deve fermare lo scroll.\n"
        "- Le scene coprono l'intera durata; ogni scena dice ESATTAMENTE cosa inquadrare e quale testo mettere a schermo.\n"
        "- Punta sui LUOGHI desiderabili (mare, Zingaro, San Vito Lo Capo, borgo, cibo) più che sull'appartamento, per attirare sconosciuti.\n"
        "- 'on_screen_text' breve e leggibile; 'voiceover' opzionale.\n"
        f"- Storyboard (scene, hook, cta, music, shooting_tips) in {'italiano' if primary == 'it' else primary}. Le 'captions' una per ogni lingua: {', '.join(langs)}.\n"
        "- Hashtag: mix locali (Sicilia/Trappeto/San Vito/Zingaro) e di viaggio, 8-12 per lingua.\n\n"
        f"{ctx}\n\n"
        f"Restituisci ESATTAMENTE questo JSON (senza markdown, nessun testo fuori dal JSON):\n{schema}"
    )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"vscript-{uuid.uuid4().hex[:8]}",
        system_message=CARMELO_SYSTEM_MESSAGE,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929").with_params(max_tokens=4000)
    try:
        raw = await chat.send_message(UserMessage(text=prompt))
        data = _extract_json(raw)
    except Exception as e:
        logger.exception("Video script error: %s", e)
        raise HTTPException(status_code=502, detail=f"Errore generazione script: {str(e)[:160]}")

    doc = {
        "id": str(uuid.uuid4()),
        "platform": body.platform or "tiktok",
        "platform_label": plabel,
        "topic": body.topic,
        "duration": duration,
        "languages": langs,
        "script": data,
        "created_at": now_utc().isoformat(),
    }
    await db.video_scripts.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.get("/admin/marketing/video-scripts")
async def marketing_video_scripts(_: str = Depends(get_current_admin)):
    cur = db.video_scripts.find({}, {"_id": 0}).sort("created_at", -1).limit(100)
    return await cur.to_list(100)


@api.delete("/admin/marketing/video-scripts/{item_id}")
async def marketing_video_script_delete(item_id: str, _: str = Depends(get_current_admin)):
    res = await db.video_scripts.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Script non trovato")
    return {"ok": True}


# ============================================================
# Marketing · Calendario editoriale
# ============================================================
@api.get("/admin/marketing/calendar")
async def marketing_calendar_list(_: str = Depends(get_current_admin)):
    cur = db.marketing_calendar.find({}, {"_id": 0}).sort("date", 1)
    return await cur.to_list(500)


@api.post("/admin/marketing/calendar")
async def marketing_calendar_create(body: CalendarItemIn, _: str = Depends(get_current_admin)):
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="Indica un titolo")
    if not (body.date or "").strip():
        raise HTTPException(status_code=400, detail="Indica una data")
    doc = {
        "id": str(uuid.uuid4()),
        "title": body.title.strip(),
        "platform": body.platform or "tiktok",
        "date": body.date,
        "notes": (body.notes or "").strip(),
        "content_id": body.content_id,
        "status": body.status or "planned",
        "created_at": now_utc().isoformat(),
    }
    await db.marketing_calendar.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.put("/admin/marketing/calendar/{item_id}")
async def marketing_calendar_update(item_id: str, body: CalendarItemUpdate, _: str = Depends(get_current_admin)):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Niente da aggiornare")
    res = await db.marketing_calendar.update_one({"id": item_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Voce non trovata")
    return await db.marketing_calendar.find_one({"id": item_id}, {"_id": 0})


@api.delete("/admin/marketing/calendar/{item_id}")
async def marketing_calendar_delete(item_id: str, _: str = Depends(get_current_admin)):
    res = await db.marketing_calendar.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Voce non trovata")
    return {"ok": True}


@api.post("/admin/marketing/strategy")
async def marketing_strategy(body: MarketingStrategyIn, _: str = Depends(get_current_admin)):
    """Carmelo generates a personalized social marketing PLAN (focused on TikTok, Google Business
    and Facebook), aware of the real property data and seasonal availability."""
    avail = await get_availability_summary()
    ctx = _build_property_context(avail)

    schema = (
        '{\n'
        '  "summary": "2-3 frasi: dove concentrare gli sforzi e perché, per QUESTA struttura",\n'
        '  "priority_platforms": [\n'
        '    {"platform": "TikTok", "priority": 1, "why": "...", "cadence": "es. 3-4 video/sett", "best_times": "...", "content_ideas": ["idea concreta 1", "idea 2", "idea 3"]},\n'
        '    {"platform": "Google Business Profile", "priority": 2, "why": "...", "cadence": "...", "best_times": "...", "content_ideas": ["...", "...", "..."]},\n'
        '    {"platform": "Facebook", "priority": 3, "why": "...", "cadence": "...", "best_times": "...", "content_ideas": ["...", "...", "..."]}\n'
        '  ],\n'
        '  "content_pillars": ["pilastro 1", "pilastro 2", "pilastro 3", "pilastro 4"],\n'
        '  "weekly_plan": [\n'
        '    {"day": "Lunedì", "platform": "TikTok", "idea": "..."},\n'
        '    {"day": "Mercoledì", "platform": "Facebook", "idea": "..."},\n'
        '    {"day": "Venerdì", "platform": "Google", "idea": "..."},\n'
        '    {"day": "Domenica", "platform": "TikTok", "idea": "..."}\n'
        '  ],\n'
        '  "kpis": ["metrica 1 da monitorare", "metrica 2", "metrica 3"],\n'
        '  "quick_wins": ["azione rapida ad alto impatto 1", "azione 2", "azione 3"]\n'
        '}'
    )

    prompt = (
        "In qualità di Carmelo, crea un PIANO DI MARKETING SOCIAL personalizzato e concreto per 'Appartamento Matteo' a Trappeto.\n"
        f"OBIETTIVO DELL'HOST: {body.goal or 'massimizzare le prenotazioni dirette nella stagione maggio-ottobre'}.\n"
        "Dai PRIORITÀ a TikTok (1), Google Business Profile (2) e Facebook (3), spiegando perché proprio questi canali per QUESTA struttura e per il pubblico dei viaggiatori che cercano la Sicilia autentica.\n"
        "Sii specifico, azionabile e realistico (no consigli generici). Usa le disponibilità reali quando proponi idee a tema 'date libere/offerte'.\n\n"
        f"{ctx}\n\n"
        "Restituisci ESATTAMENTE questo schema JSON (e nient'altro, senza markdown):\n"
        f"{schema}"
    )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"strategy-{uuid.uuid4().hex[:8]}",
        system_message=CARMELO_SYSTEM_MESSAGE,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    try:
        raw = await chat.send_message(UserMessage(text=prompt))
        data = _extract_json(raw)
    except Exception as e:
        logger.exception("Marketing strategy error: %s", e)
        raise HTTPException(status_code=502, detail=f"Errore generazione strategia: {str(e)[:160]}")

    data["season"] = avail.get("season")
    data["generated_at"] = now_utc().isoformat()
    return data


@api.post("/admin/marketing/strategy/stream")
async def marketing_strategy_stream(body: MarketingStrategyIn, _: str = Depends(get_current_admin)):
    """Streaming version of the strategy generator: streams Carmelo's text live
    (avoids proxy/ingress timeouts on long generations), then emits the final
    `data: [[RESULT]]{json}` and `data: [DONE]`."""
    avail = await get_availability_summary()
    ctx = _build_property_context(avail)

    schema = (
        '{\n'
        '  "objective": "l\'obiettivo riformulato in 1 frase chiara e misurabile",\n'
        '  "summary": "executive summary in 2-3 frasi: la strategia in sintesi per QUESTA struttura",\n'
        '  "target_audience": "in 1 frase: chi è il viaggiatore ideale da intercettare (età, provenienza, interessi)",\n'
        '  "priority_platforms": [\n'
        '    {"platform": "TikTok", "priority": 1, "role": "ruolo nel funnel (es. Awareness)", "why": "perché per QUESTA struttura", "cadence": "es. 3-4 video/sett", "best_times": "...", "content_ideas": ["idea concreta 1", "idea 2", "idea 3"]},\n'
        '    {"platform": "Google Business Profile", "priority": 2, "role": "...", "why": "...", "cadence": "...", "best_times": "...", "content_ideas": ["...", "...", "..."]},\n'
        '    {"platform": "Facebook", "priority": 3, "role": "...", "why": "...", "cadence": "...", "best_times": "...", "content_ideas": ["...", "...", "..."]}\n'
        '  ],\n'
        '  "content_pillars": ["pilastro 1", "pilastro 2", "pilastro 3", "pilastro 4"],\n'
        '  "weekly_plan": [\n'
        '    {"day": "Lunedì", "platform": "TikTok", "idea": "azione concreta", "format": "es. Reel 20s"},\n'
        '    {"day": "Martedì", "platform": "...", "idea": "...", "format": "..."},\n'
        '    {"day": "Mercoledì", "platform": "...", "idea": "...", "format": "..."},\n'
        '    {"day": "Giovedì", "platform": "...", "idea": "...", "format": "..."},\n'
        '    {"day": "Venerdì", "platform": "...", "idea": "...", "format": "..."},\n'
        '    {"day": "Sabato", "platform": "...", "idea": "...", "format": "..."},\n'
        '    {"day": "Domenica", "platform": "...", "idea": "...", "format": "..."}\n'
        '  ],\n'
        '  "first_week_actions": ["azione da fare SUBITO 1 (concreta)", "azione 2", "azione 3", "azione 4"],\n'
        '  "quick_wins": ["azione rapida ad alto impatto 1", "azione 2", "azione 3"],\n'
        '  "kpis": ["metrica 1 da monitorare con valore-obiettivo", "metrica 2", "metrica 3"],\n'
        '  "expected_results": "risultati realistici attesi a 30/60/90 giorni, in 1-2 frasi (no promesse gonfiate)"\n'
        '}'
    )
    prompt = (
        "In qualità di Carmelo, Chief Social Media Strategist, crea un PIANO DI MARKETING professionale, "
        "SCHEMATICO e azionabile per 'Appartamento Matteo' a Trappeto (Sicilia).\n"
        f"OBIETTIVO DELL'HOST: {body.goal or 'massimizzare le prenotazioni dirette nella stagione maggio-ottobre'}.\n\n"
        "REGOLE DI QUALITÀ (sei un professionista vero):\n"
        "- Ragiona per FUNNEL: assegna a ogni piattaforma un ruolo (Awareness / Considerazione / Prenotazione).\n"
        "- Dai PRIORITÀ a TikTok (1), Google Business Profile (2), Facebook (3) e spiega il perché per QUESTA struttura.\n"
        "- Frasi brevi e concrete, niente fuffa, niente consigli generici. Ogni voce deve essere 'fai questo'.\n"
        "- Il piano settimanale deve coprire 7 giorni con formato consigliato per ogni contenuto.\n"
        "- Usa le disponibilità reali per le idee a tema 'date libere/offerte'.\n"
        "- 'expected_results' deve essere realistico e onesto.\n\n"
        f"{ctx}\n\n"
        "Restituisci ESATTAMENTE questo schema JSON (e nient'altro, senza markdown, senza testo prima o dopo):\n"
        f"{schema}"
    )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"strategy-{uuid.uuid4().hex[:8]}",
        system_message=CARMELO_SYSTEM_MESSAGE,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929").with_params(max_tokens=8000)

    async def event_generator():
        buffer = ""
        try:
            async for ev in chat.stream_message(UserMessage(text=prompt)):
                if isinstance(ev, TextDelta):
                    buffer += ev.content
                    chunk = ev.content.replace("\n", "\\n")
                    yield f"data: {chunk}\n\n"
                elif isinstance(ev, StreamDone):
                    break
            try:
                data = _extract_json(buffer)
            except Exception as e:
                logger.warning("Strategy stream JSON parse failed: %s", str(e)[:200])
                yield f"data: [ERROR] Risposta IA non valida: {str(e)[:160]}\n\n"
                return
            data["season"] = avail.get("season")
            data["generated_at"] = now_utc().isoformat()
            yield "data: [[RESULT]]" + json.dumps(data, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Strategy stream error: %s", e)
            yield f"data: [ERROR] {str(e)[:200]}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_strategy_prompt(goal: Optional[str], ctx: str) -> str:
    schema = (
        '{\n'
        '  "objective": "l\'obiettivo riformulato in 1 frase chiara e misurabile",\n'
        '  "summary": "executive summary in 2-3 frasi: la strategia in sintesi per QUESTA struttura",\n'
        '  "target_audience": "in 1 frase: chi è il viaggiatore ideale da intercettare (età, provenienza, interessi)",\n'
        '  "priority_platforms": [\n'
        '    {"platform": "TikTok", "priority": 1, "role": "ruolo nel funnel (es. Awareness)", "why": "perché per QUESTA struttura", "cadence": "es. 3-4 video/sett", "best_times": "...", "content_ideas": ["idea concreta 1", "idea 2", "idea 3"]},\n'
        '    {"platform": "Google Business Profile", "priority": 2, "role": "...", "why": "...", "cadence": "...", "best_times": "...", "content_ideas": ["...", "...", "..."]},\n'
        '    {"platform": "Facebook", "priority": 3, "role": "...", "why": "...", "cadence": "...", "best_times": "...", "content_ideas": ["...", "...", "..."]}\n'
        '  ],\n'
        '  "content_pillars": ["pilastro 1", "pilastro 2", "pilastro 3", "pilastro 4"],\n'
        '  "weekly_plan": [\n'
        '    {"day": "Lunedì", "platform": "TikTok", "idea": "azione concreta", "format": "es. Reel 20s"},\n'
        '    {"day": "Martedì", "platform": "...", "idea": "...", "format": "..."},\n'
        '    {"day": "Mercoledì", "platform": "...", "idea": "...", "format": "..."},\n'
        '    {"day": "Giovedì", "platform": "...", "idea": "...", "format": "..."},\n'
        '    {"day": "Venerdì", "platform": "...", "idea": "...", "format": "..."},\n'
        '    {"day": "Sabato", "platform": "...", "idea": "...", "format": "..."},\n'
        '    {"day": "Domenica", "platform": "...", "idea": "...", "format": "..."}\n'
        '  ],\n'
        '  "first_week_actions": ["azione da fare SUBITO 1 (concreta)", "azione 2", "azione 3", "azione 4"],\n'
        '  "quick_wins": ["azione rapida ad alto impatto 1", "azione 2", "azione 3"],\n'
        '  "kpis": ["metrica 1 da monitorare con valore-obiettivo", "metrica 2", "metrica 3"],\n'
        '  "expected_results": "risultati realistici attesi a 30/60/90 giorni, in 1-2 frasi (no promesse gonfiate)"\n'
        '}'
    )
    return (
        "In qualità di Carmelo, Chief Social Media Strategist, crea un PIANO DI MARKETING professionale, "
        "SCHEMATICO e azionabile per 'Appartamento Matteo' a Trappeto (Sicilia).\n"
        f"OBIETTIVO DELL'HOST: {goal or 'massimizzare le prenotazioni dirette nella stagione maggio-ottobre'}.\n\n"
        "REGOLE DI QUALITÀ (sei un professionista vero):\n"
        "- Ragiona per FUNNEL: assegna a ogni piattaforma un ruolo (Awareness / Considerazione / Prenotazione).\n"
        "- Dai PRIORITÀ a TikTok (1), Google Business Profile (2), Facebook (3) e spiega il perché per QUESTA struttura.\n"
        "- Frasi brevi e concrete, niente fuffa. Ogni voce deve essere 'fai questo'.\n"
        "- Il piano settimanale deve coprire 7 giorni con formato consigliato per ogni contenuto.\n"
        "- Usa le disponibilità reali per le idee a tema 'date libere/offerte'.\n"
        "- 'expected_results' deve essere realistico e onesto.\n\n"
        f"{ctx}\n\n"
        "Restituisci ESATTAMENTE questo schema JSON (e nient'altro, senza markdown, senza testo prima o dopo):\n"
        f"{schema}"
    )


async def _run_strategy_job(job_id: str, goal: Optional[str]):
    """Background worker: generates the strategy and saves it to db.strategy_jobs."""
    try:
        avail = await get_availability_summary()
        ctx = _build_property_context(avail)
        prompt = _build_strategy_prompt(goal, ctx)
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"strategy-{uuid.uuid4().hex[:8]}",
            system_message=CARMELO_SYSTEM_MESSAGE,
        ).with_model("gemini", "gemini-2.5-flash").with_params(max_tokens=8000)
        raw = await chat.send_message(UserMessage(text=prompt))
        data = _extract_json(raw)
        data["season"] = avail.get("season")
        data["generated_at"] = now_utc().isoformat()
        await db.strategy_jobs.update_one(
            {"id": job_id}, {"$set": {"status": "done", "plan": data, "finished_at": now_utc().isoformat()}}
        )
    except Exception as e:
        logger.exception("Strategy job error: %s", e)
        await db.strategy_jobs.update_one(
            {"id": job_id}, {"$set": {"status": "error", "error": str(e)[:200], "finished_at": now_utc().isoformat()}}
        )


@api.post("/admin/marketing/strategy/start")
async def marketing_strategy_start(body: MarketingStrategyIn, _: str = Depends(get_current_admin)):
    """Start background generation of the strategy. Returns a job_id to poll.
    Avoids the proxy's ~60s request timeout entirely."""
    job_id = uuid.uuid4().hex
    await db.strategy_jobs.insert_one({
        "id": job_id,
        "status": "running",
        "goal": body.goal,
        "created_at": now_utc().isoformat(),
    })
    asyncio.create_task(_run_strategy_job(job_id, body.goal))
    return {"job_id": job_id, "status": "running"}


@api.get("/admin/marketing/strategy/status/{job_id}")
async def marketing_strategy_status(job_id: str, _: str = Depends(get_current_admin)):
    doc = await db.strategy_jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Job non trovato")
    return doc




@api.get("/admin/marketing/platforms")
async def marketing_platforms(_: str = Depends(get_current_admin)):
    return [{"id": k, "label": v["label"]} for k, v in PLATFORM_SPECS.items()]


# ============================================================
# Carmelo · Google Business Profile tools (admin)
# ============================================================
class GBSettingsIn(BaseModel):
    review_link: Optional[str] = ""
    business_name: Optional[str] = "Appartamento Matteo"
    maps_url: Optional[str] = ""


class GBReviewReplyIn(BaseModel):
    review_text: str
    rating: Optional[int] = None          # 1-5
    guest_name: Optional[str] = ""


class GBReviewRequestIn(BaseModel):
    tone: Optional[str] = ""              # optional tone hint
    languages: Optional[List[str]] = None  # default all 5


class GBQAIn(BaseModel):
    languages: Optional[List[str]] = None  # default all 5
    focus: Optional[str] = ""             # optional theme


GB_LANGS = ["it", "en", "es", "fr", "de"]
GB_LANG_LABELS = {"it": "Italiano", "en": "English", "es": "Español", "fr": "Français", "de": "Deutsch"}


async def _get_gb_settings() -> dict:
    doc = await db.settings.find_one({"_id": "google_business"}, {"_id": 0})
    return doc or {"review_link": "", "business_name": "Appartamento Matteo", "maps_url": ""}


def _carmelo_chat(tag: str) -> LlmChat:
    return LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"{tag}-{uuid.uuid4().hex[:8]}",
        system_message=CARMELO_SYSTEM_MESSAGE,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")


@api.get("/admin/google-business/settings")
async def gb_get_settings(_: str = Depends(get_current_admin)):
    return await _get_gb_settings()


@api.put("/admin/google-business/settings")
async def gb_save_settings(body: GBSettingsIn, _: str = Depends(get_current_admin)):
    doc = {
        "review_link": (body.review_link or "").strip(),
        "business_name": (body.business_name or "Appartamento Matteo").strip(),
        "maps_url": (body.maps_url or "").strip(),
        "updated_at": now_utc().isoformat(),
    }
    await db.settings.update_one({"_id": "google_business"}, {"$set": doc}, upsert=True)
    return {"ok": True, **doc}


@api.post("/admin/google-business/review-reply")
async def gb_review_reply(body: GBReviewReplyIn, _: str = Depends(get_current_admin)):
    """Carmelo writes a perfect public reply to a Google review, in the SAME language."""
    if not (body.review_text or "").strip():
        raise HTTPException(status_code=400, detail="Inserisci il testo della recensione")

    rating_line = f"Valutazione data dall'ospite: {body.rating}/5.\n" if body.rating else ""
    guest_line = f"Nome ospite: {body.guest_name}.\n" if (body.guest_name or "").strip() else ""

    schema = '{ "detected_language": "codice ISO (it/en/es/fr/de/altro)", "reply": "testo della risposta pubblica" }'
    prompt = (
        "Un ospite ha lasciato questa RECENSIONE su Google per 'Appartamento Matteo' (Trappeto, Sicilia).\n"
        "Scrivi UNA risposta pubblica perfetta, da pubblicare come proprietario.\n"
        "REGOLE FERREE:\n"
        "1) RILEVA la lingua della recensione e RISPONDI NELLA STESSA IDENTICA LINGUA.\n"
        "2) Tono caloroso, umano e personale (mai robotico o generico).\n"
        "3) Personalizza: cita un dettaglio concreto della recensione.\n"
        "4) Se positiva: ringrazia con sincerità e invita a tornare (es. la stagione, la Riserva dello Zingaro, San Vito Lo Capo).\n"
        "5) Se critica o negativa: scusati con garbo, mostra che ti importa davvero, offri di rimediare; MAI difensivo o polemico.\n"
        "6) Lunghezza 50-90 parole. Niente hashtag, niente emoji eccessive (max 1 se naturale).\n"
        "7) Firma con 'Matteo'.\n\n"
        f"{rating_line}{guest_line}"
        f"RECENSIONE:\n\"\"\"{body.review_text.strip()}\"\"\"\n\n"
        f"Restituisci ESATTAMENTE questo JSON (senza markdown):\n{schema}"
    )

    try:
        raw = await _carmelo_chat("gb-reply").send_message(UserMessage(text=prompt))
        data = _extract_json(raw)
    except Exception as e:
        logger.exception("GB review reply error: %s", e)
        raise HTTPException(status_code=502, detail=f"Errore generazione risposta: {str(e)[:160]}")
    data["generated_at"] = now_utc().isoformat()
    return data


@api.post("/admin/google-business/review-request")
async def gb_review_request(body: GBReviewRequestIn, _: str = Depends(get_current_admin)):
    """Carmelo writes post-stay messages (WhatsApp + email) asking for a Google review, in 5 languages."""
    langs = [l for l in (body.languages or GB_LANGS) if l in GB_LANGS] or GB_LANGS
    gb = await _get_gb_settings()
    link = gb.get("review_link") or "[INSERISCI IL LINK RECENSIONI NELLE IMPOSTAZIONI]"
    tone_line = f"Tono richiesto: {body.tone}.\n" if (body.tone or "").strip() else ""

    lang_obj = ", ".join(
        f'"{l}": {{ "whatsapp": "messaggio WhatsApp breve e caloroso, max 50 parole, con il link", '
        f'"email_subject": "oggetto email", "email_body": "corpo email cordiale con il link" }}'
        for l in langs
    )
    schema = "{ " + lang_obj + " }"

    prompt = (
        "Scrivi i messaggi post-soggiorno per chiedere gentilmente una RECENSIONE su Google a un ospite "
        "di 'Appartamento Matteo' (Trappeto, Sicilia).\n"
        "REGOLE:\n"
        "1) Ogni lingua DEVE essere scritta in modo naturale e nativo (non tradotto male).\n"
        "2) Caloroso, breve, mai insistente. Ringrazia per il soggiorno e spiega che una recensione aiuta tanto una piccola struttura familiare.\n"
        f"3) Inserisci SEMPRE, letteralmente, questo link recensioni: {link}\n"
        "4) Firma con 'Matteo'.\n"
        f"{tone_line}\n"
        f"Lingue richieste: {', '.join(langs)}.\n"
        f"Restituisci ESATTAMENTE questo JSON (senza markdown):\n{schema}"
    )

    try:
        raw = await _carmelo_chat("gb-reqrev").send_message(UserMessage(text=prompt))
        data = _extract_json(raw)
    except Exception as e:
        logger.exception("GB review request error: %s", e)
        raise HTTPException(status_code=502, detail=f"Errore generazione messaggi: {str(e)[:160]}")
    return {"review_link": link, "languages": langs, "messages": data, "generated_at": now_utc().isoformat()}


@api.post("/admin/google-business/qa")
async def gb_qa(body: GBQAIn, _: str = Depends(get_current_admin)):
    """Carmelo generates the most useful Q&A to pre-populate the Google Business profile, per language."""
    langs = [l for l in (body.languages or GB_LANGS) if l in GB_LANGS] or GB_LANGS
    focus_line = f"Tema da privilegiare: {body.focus}.\n" if (body.focus or "").strip() else ""

    lang_obj = ", ".join(
        f'"{l}": [ {{ "question": "domanda frequente di un viaggiatore", "answer": "risposta chiara e utile, 1-3 frasi" }} ]'
        for l in langs
    )
    schema = "{ " + lang_obj + " }"

    prompt = (
        "Genera le DOMANDE & RISPOSTE (Q&A) più utili da pre-caricare nella sezione 'Domande e risposte' "
        "del profilo Google Business di 'Appartamento Matteo' (casa vacanze a Trappeto, Sicilia nord-occidentale).\n"
        "Pensa a cosa chiede davvero un viaggiatore (anche straniero): parcheggio, distanza dal mare/spiaggia, "
        "check-in/out, Wi-Fi, aria condizionata, animali ammessi, capienza, distanze da San Vito Lo Capo / Riserva dello Zingaro / "
        "aeroporto di Palermo, supermercati/ristoranti vicini, è adatto a famiglie, lingua parlata dall'host.\n"
        "REGOLE:\n"
        "1) 10-12 coppie domanda/risposta per lingua.\n"
        "2) Ogni lingua scritta in modo nativo e naturale.\n"
        "3) Risposte concrete e oneste; se un dato esatto non è noto, formula la risposta in modo utile senza inventare numeri precisi.\n"
        f"{focus_line}"
        f"Lingue richieste: {', '.join(langs)}.\n"
        f"Restituisci ESATTAMENTE questo JSON (senza markdown):\n{schema}"
    )

    try:
        raw = await _carmelo_chat("gb-qa").send_message(UserMessage(text=prompt))
        data = _extract_json(raw)
    except Exception as e:
        logger.exception("GB QA error: %s", e)
        raise HTTPException(status_code=502, detail=f"Errore generazione Q&A: {str(e)[:160]}")
    return {"languages": langs, "qa": data, "generated_at": now_utc().isoformat()}


class GBGuideIn(BaseModel):
    progress: dict = {}


@api.get("/admin/google-business/guide")
async def gb_get_guide(_: str = Depends(get_current_admin)):
    doc = await db.settings.find_one({"_id": "gb_guide"}, {"_id": 0})
    return doc or {"progress": {}}


@api.put("/admin/google-business/guide")
async def gb_save_guide(body: GBGuideIn, _: str = Depends(get_current_admin)):
    await db.settings.update_one(
        {"_id": "gb_guide"},
        {"$set": {"progress": body.progress or {}, "updated_at": now_utc().isoformat()}},
        upsert=True,
    )
    return {"ok": True, "progress": body.progress or {}}


# ============================================================
# Carmelo · Google Business — Post nativi & Descrizione attività
# ============================================================
GB_POST_TYPE_LABELS = {"update": "Novità", "offer": "Offerta", "event": "Evento"}


@api.post("/admin/google-business/post")
async def gb_generate_post(body: GBPostIn, _: str = Depends(get_current_admin)):
    """Carmelo scrive un POST NATIVO per Google Business (Novità / Offerta / Evento)
    pronto da incollare, nelle lingue richieste, con titolo, testo, pulsante CTA e
    (per offerte/eventi) date di validità e codice sconto."""
    if not (body.topic or "").strip():
        raise HTTPException(status_code=400, detail="Indica l'argomento del post")
    langs = [l for l in (body.languages or GB_LANGS) if l in GB_LANGS] or GB_LANGS
    ptype = body.post_type if body.post_type in GB_POST_TYPE_LABELS else "update"

    extra_fields = ""
    if ptype == "offer":
        extra_fields = (
            '"offer_title": "titolo offerta breve (max 58 caratteri)", '
            '"coupon_code": "codice sconto se sensato (o vuoto)", '
            '"terms": "condizioni brevi", '
        )
    elif ptype == "event":
        extra_fields = '"event_title": "titolo evento (max 58 caratteri)", '

    per_lang = ", ".join(
        f'"{l}": {{ {extra_fields}"summary": "testo del post (punta a 150-300 caratteri), nativo e naturale", '
        f'"cta_button": "una tra: Prenota / Scopri di più / Chiama / Acquista", '
        f'"cta_note": "dove deve puntare il pulsante (es. link sito)" }}'
        for l in langs
    )
    schema = (
        '{\n'
        f'  "post_type": "{ptype}",\n'
        '  "suggested_dates": "suggerimento date validità/evento (es. \\"dal 1 al 30 settembre\\") o vuoto",\n'
        '  "image_idea": "1 frase: che foto abbinare",\n'
        '  "content": { ' + per_lang + ' }\n'
        '}'
    )
    offer_line = f"DETTAGLI OFFERTA/EVENTO: {body.offer_details}\n" if (body.offer_details or "").strip() else ""
    ctx = _build_property_context(await get_availability_summary())
    prompt = (
        f"In qualità di Carmelo, scrivi un POST NATIVO per Google Business Profile di tipo '{GB_POST_TYPE_LABELS[ptype]}'.\n"
        f"ARGOMENTO: {body.topic}\n"
        f"{offer_line}"
        f"NOTE: {body.custom_notes or 'nessuna'}\n\n"
        "REGOLE:\n"
        "- Ogni lingua scritta in modo nativo e naturale (non tradotto male).\n"
        "- I post Google scadono dopo 7 giorni: rendi il testo attuale e con una CTA chiara.\n"
        "- Usa keyword locali (Trappeto, Zingaro, San Vito Lo Capo) in modo naturale.\n"
        "- Se è un'Offerta, proponi qualcosa di concreto e onesto; usa le disponibilità reali.\n"
        f"- Lingue richieste: {', '.join(langs)}.\n\n"
        f"{ctx}\n\n"
        f"Restituisci ESATTAMENTE questo JSON (senza markdown):\n{schema}"
    )
    try:
        raw = await _carmelo_chat("gb-post").send_message(UserMessage(text=prompt))
        data = _extract_json(raw)
    except Exception as e:
        logger.exception("GB post error: %s", e)
        raise HTTPException(status_code=502, detail=f"Errore generazione post: {str(e)[:160]}")
    return {"languages": langs, "post_type": ptype, **data, "generated_at": now_utc().isoformat()}


@api.post("/admin/google-business/description")
async def gb_generate_description(body: GBDescriptionIn, _: str = Depends(get_current_admin)):
    """Carmelo scrive la DESCRIZIONE ATTIVITÀ ottimizzata (max 750 caratteri) con keyword
    locali, per ogni lingua richiesta."""
    langs = [l for l in (body.languages or GB_LANGS) if l in GB_LANGS] or GB_LANGS
    focus_line = f"Tema/angolo da privilegiare: {body.focus}.\n" if (body.focus or "").strip() else ""
    per_lang = ", ".join(
        f'"{l}": {{ "description": "descrizione max 750 caratteri", "char_count": 0 }}'
        for l in langs
    )
    schema = "{ " + per_lang + " }"
    ctx = _build_property_context(await get_availability_summary())
    prompt = (
        "Scrivi la DESCRIZIONE ATTIVITÀ ottimizzata per il profilo Google Business di 'Appartamento Matteo' "
        "(casa vacanze a Trappeto, Sicilia nord-occidentale).\n"
        "REGOLE:\n"
        "1) Massimo 750 caratteri per lingua (limite di Google). Conta i caratteri e mettili in 'char_count'.\n"
        "2) Inserisci in modo NATURALE le keyword locali: Trappeto, golfo di Castellammare, Riserva dello Zingaro, "
        "San Vito Lo Capo, Scopello, Palermo, mare, casa vacanze.\n"
        "3) Inizia forte con il beneficio principale; niente elenco di parole chiave forzato.\n"
        "4) Ogni lingua scritta in modo nativo.\n"
        f"{focus_line}"
        f"Lingue richieste: {', '.join(langs)}.\n\n"
        f"{ctx}\n\n"
        f"Restituisci ESATTAMENTE questo JSON (senza markdown):\n{schema}"
    )
    try:
        raw = await _carmelo_chat("gb-desc").send_message(UserMessage(text=prompt))
        data = _extract_json(raw)
    except Exception as e:
        logger.exception("GB description error: %s", e)
        raise HTTPException(status_code=502, detail=f"Errore generazione descrizione: {str(e)[:160]}")
    return {"languages": langs, "descriptions": data, "generated_at": now_utc().isoformat()}


# ============================================================
# Stats (admin)
# ============================================================
@api.get("/admin/stats")
async def get_stats(_: str = Depends(get_current_admin)):
    # Total unique visits (deduplicated by session/day already at insert time)
    total_visits = await db.visits.count_documents({})

    # Total bookings
    total_bookings = await db.bookings.count_documents({})
    approved_bookings = await db.bookings.count_documents({"status": "approved"})
    pending_bookings = await db.bookings.count_documents({"status": "pending"})
    rejected_bookings = await db.bookings.count_documents({"status": "rejected"})

    # By source
    site_bookings = await db.bookings.count_documents({"source": "site"})
    booking_com_bookings = await db.bookings.count_documents({"source": "booking"})

    # Conversion rate (only counts approved over unique visits)
    conversion_rate = (approved_bookings / total_visits * 100.0) if total_visits > 0 else 0.0

    # Visits in last 30 days (daily breakdown)
    from collections import defaultdict
    cur = db.visits.find({}, {"_id": 0, "day": 1})
    by_day = defaultdict(int)
    async for v in cur:
        by_day[v["day"]] = by_day[v["day"]] + 1
    daily = sorted([{"day": d, "count": c} for d, c in by_day.items()], key=lambda x: x["day"])[-30:]

    return {
        "total_visits": total_visits,
        "total_bookings": total_bookings,
        "approved_bookings": approved_bookings,
        "pending_bookings": pending_bookings,
        "rejected_bookings": rejected_bookings,
        "site_bookings": site_bookings,
        "booking_com_bookings": booking_com_bookings,
        "conversion_rate": round(conversion_rate, 2),
        "daily_visits": daily,
    }


# ============================================================
# Accounting (admin)
# ============================================================
def compute_net(total: float, source: str, rates: dict) -> dict:
    """Apply cascade commissions for Booking.com sales. Site sales keep full revenue."""
    gross = float(total or 0.0)
    breakdown = {
        "gross": round(gross, 2),
        "state": 0.0,
        "booking": 0.0,
        "vat": 0.0,
        "bank": 0.0,
        "total_commissions": 0.0,
        "net": round(gross, 2),
    }
    if source != "booking":
        return breakdown

    state_pct = float(rates.get("state_pct", 21.0))
    booking_pct = float(rates.get("booking_pct", 15.0))
    vat_pct = float(rates.get("vat_pct", 3.7))
    bank_pct = float(rates.get("bank_pct", 1.5))

    # All percentages are applied to gross
    state = gross * state_pct / 100.0
    booking_fee = gross * booking_pct / 100.0
    vat = gross * vat_pct / 100.0
    bank = gross * bank_pct / 100.0
    total_comm = state + booking_fee + vat + bank
    net = gross - total_comm
    breakdown.update({
        "state": round(state, 2),
        "booking": round(booking_fee, 2),
        "vat": round(vat, 2),
        "bank": round(bank, 2),
        "total_commissions": round(total_comm, 2),
        "net": round(net, 2),
        "rates": {
            "state_pct": state_pct,
            "booking_pct": booking_pct,
            "vat_pct": vat_pct,
            "bank_pct": bank_pct,
        },
    })
    return breakdown


@api.get("/admin/accounting")
async def get_accounting(_: str = Depends(get_current_admin)):
    rates_doc = await db.settings.find_one({"_id": "commission_rates"}, {"_id": 0})
    rates = rates_doc or CommissionRatesIn().model_dump()

    # Only approved bookings contribute to accounting
    cur = db.bookings.find({"status": "approved"}, {"_id": 0}).sort("check_in", 1)
    bookings = await cur.to_list(2000)

    items = []
    totals = {
        "gross_total": 0.0,
        "net_total": 0.0,
        "commissions_total": 0.0,
        "site_gross": 0.0,
        "site_net": 0.0,
        "booking_gross": 0.0,
        "booking_net": 0.0,
        "by_commission": {"state": 0.0, "booking": 0.0, "vat": 0.0, "bank": 0.0},
    }

    for b in bookings:
        total = float(((b.get("quote") or {}).get("total")) or 0.0)
        source = b.get("source") or "site"
        bd = compute_net(total, source, rates)
        item = {
            "id": b.get("id"),
            "guest_name": b.get("guest_name"),
            "check_in": b.get("check_in"),
            "check_out": b.get("check_out"),
            "source": source,
            "status": b.get("status"),
            "confirmation_code": b.get("confirmation_code"),
            "breakdown": bd,
        }
        items.append(item)

        totals["gross_total"] += bd["gross"]
        totals["net_total"] += bd["net"]
        totals["commissions_total"] += bd["total_commissions"]
        if source == "booking":
            totals["booking_gross"] += bd["gross"]
            totals["booking_net"] += bd["net"]
            totals["by_commission"]["state"] += bd["state"]
            totals["by_commission"]["booking"] += bd["booking"]
            totals["by_commission"]["vat"] += bd["vat"]
            totals["by_commission"]["bank"] += bd["bank"]
        else:
            totals["site_gross"] += bd["gross"]
            totals["site_net"] += bd["net"]

    # Round totals
    for k, v in totals.items():
        if isinstance(v, dict):
            for kk in v:
                v[kk] = round(v[kk], 2)
        else:
            totals[k] = round(v, 2)

    return {"rates": rates, "items": items, "totals": totals}


# ============================================================
# MARKETING AI — Google Business Profile Coach (admin only)
# ============================================================
class MktChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: Optional[str] = "claude"  # claude | gpt5 | gemini | all
    images: Optional[List[str]] = None  # base64 (data URL o grezzo) di immagini allegate (vision)


class MktGeneratePostIn(BaseModel):
    brief: str  # descrizione del post che l'utente vuole
    post_type: Optional[str] = "NOVITA"  # NOVITA|OFFERTA|EVENTO|PRODOTTO
    language: Optional[str] = "it"
    model: Optional[str] = "claude"


class MktAuditIn(BaseModel):
    current_description: str
    extra_context: Optional[str] = None
    model: Optional[str] = "gpt5"


class MktCalendarIn(BaseModel):
    month_focus: Optional[str] = None  # es: "Promuovere la mappa interattiva"
    start_date: Optional[str] = None  # YYYY-MM-DD
    model: Optional[str] = "gpt5"


@api.get("/admin/marketing/models")
async def mkt_list_models(_: str = Depends(get_current_admin)):
    return {
        "models": [
            {"key": k, "label": MKT_MODEL_LABELS[k], "best_for": MKT_MODEL_BEST_FOR[k]}
            for k in MKT_MODELS.keys()
        ]
    }


@api.post("/admin/marketing/chat")
async def mkt_chat(body: MktChatIn, _: str = Depends(get_current_admin)):
    """Chat libera con il coach esperto GBP. Multi-modello supportato (chiamate in parallelo)."""
    session_id = body.session_id or str(uuid.uuid4())
    models = mkt_resolve_models(body.model)
    system_prompt = mkt_build_chat_prompt()

    async def _call_one(mk: str):
        try:
            chat = mkt_get_chat(session_id, mk, EMERGENT_LLM_KEY, system_prompt, mode="chat")
            answer = await mkt_send_message(chat, body.message, images=body.images)
            return {"model": mk, "label": MKT_MODEL_LABELS[mk], "answer": answer, "error": None}
        except Exception as e:
            logger.exception("mkt_chat error model=%s", mk)
            return {"model": mk, "label": MKT_MODEL_LABELS.get(mk, mk),
                    "answer": "", "error": str(e)[:300]}

    results = await asyncio.gather(*[_call_one(mk) for mk in models])
    # persiste minimal log conversazione
    try:
        await db.marketing_chat_log.insert_one({
            "session_id": session_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "user_message": body.message[:2000],
            "models": models,
            "results": [{"model": r["model"], "answer": r["answer"][:5000]} for r in results],
        })
    except Exception:
        pass
    return {"session_id": session_id, "results": list(results)}


@api.delete("/admin/marketing/chat/{session_id}")
async def mkt_clear_chat(session_id: str, _: str = Depends(get_current_admin)):
    removed = mkt_clear_cache(session_id)
    return {"cleared": removed}


@api.get("/admin/marketing/chat/{session_id}/history")
async def mkt_chat_history(session_id: str, _: str = Depends(get_current_admin)):
    cur = db.marketing_chat_log.find({"session_id": session_id}).sort("ts", 1)
    items = []
    async for d in cur:
        items.append({
            "ts": d.get("ts"),
            "user_message": d.get("user_message"),
            "results": d.get("results", []),
        })
    return {"session_id": session_id, "items": items}


@api.post("/admin/marketing/generate-post")
async def mkt_generate_post(body: MktGeneratePostIn, _: str = Depends(get_current_admin)):
    """Genera un post GBP strutturato (chiamate modelli in parallelo)."""
    models = mkt_resolve_models(body.model)
    system_prompt = mkt_build_post_prompt()
    user_msg = (
        f"Genera un post GBP di tipo {body.post_type} in lingua {body.language}.\n\n"
        f"BRIEF DEL CLIENTE:\n{body.brief}\n\n"
        f"Rispetta lo schema JSON richiesto, nessun testo prima o dopo."
    )

    async def _call_one(mk: str):
        try:
            session_id = f"post-{uuid.uuid4().hex[:8]}"
            chat = mkt_get_chat(session_id, mk, EMERGENT_LLM_KEY, system_prompt, mode="post")
            raw = await mkt_send_message(chat, user_msg)
            parsed = mkt_extract_json(raw)
            return {
                "model": mk, "label": MKT_MODEL_LABELS[mk],
                "raw": raw, "post": parsed,
                "error": None if parsed else "JSON non valido"
            }
        except Exception as e:
            logger.exception("mkt_generate_post error model=%s", mk)
            return {"model": mk, "label": MKT_MODEL_LABELS.get(mk, mk),
                    "raw": "", "post": None, "error": str(e)[:300]}

    results = list(await asyncio.gather(*[_call_one(mk) for mk in models]))
    try:
        await db.marketing_posts_log.insert_one({
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "post_type": body.post_type,
            "brief": body.brief[:2000],
            "models": models,
            "results": [{"model": r["model"], "post": r["post"]} for r in results],
        })
    except Exception:
        pass
    return {"results": results}


@api.post("/admin/marketing/audit")
async def mkt_audit(body: MktAuditIn, _: str = Depends(get_current_admin)):
    """Esegue un audit del profilo GBP (chiamate modelli in parallelo)."""
    models = mkt_resolve_models(body.model)
    system_prompt = mkt_build_audit_prompt()
    user_msg = (
        "Esegui un audit completo del profilo GBP di Appartamento Matteo. "
        "Rispondi SOLO in JSON come da schema.\n\n"
        f"DESCRIZIONE GBP ATTUALE:\n{body.current_description}\n\n"
    )
    if body.extra_context:
        user_msg += f"\nCONTESTO EXTRA:\n{body.extra_context}\n"

    async def _call_one(mk: str):
        try:
            session_id = f"audit-{uuid.uuid4().hex[:8]}"
            chat = mkt_get_chat(session_id, mk, EMERGENT_LLM_KEY, system_prompt, mode="audit")
            raw = await mkt_send_message(chat, user_msg)
            parsed = mkt_extract_json(raw)
            return {
                "model": mk, "label": MKT_MODEL_LABELS[mk],
                "raw": raw, "audit": parsed,
                "error": None if parsed else "JSON non valido"
            }
        except Exception as e:
            logger.exception("mkt_audit error model=%s", mk)
            return {"model": mk, "label": MKT_MODEL_LABELS.get(mk, mk),
                    "raw": "", "audit": None, "error": str(e)[:300]}

    results = list(await asyncio.gather(*[_call_one(mk) for mk in models]))
    return {"results": results}


@api.post("/admin/marketing/generate-calendar")
async def mkt_calendar(body: MktCalendarIn, _: str = Depends(get_current_admin)):
    """Genera un calendario editoriale 30 giorni (chiamate modelli in parallelo)."""
    models = mkt_resolve_models(body.model)
    system_prompt = mkt_build_calendar_prompt()
    user_msg = "Crea un calendario editoriale di 30 giorni per Appartamento Matteo. Rispondi SOLO in JSON come da schema.\n"
    if body.month_focus:
        user_msg += f"\nFOCUS DEL MESE: {body.month_focus}\n"
    if body.start_date:
        user_msg += f"\nDATA DI INIZIO: {body.start_date}\n"

    async def _call_one(mk: str):
        try:
            session_id = f"cal-{uuid.uuid4().hex[:8]}"
            chat = mkt_get_chat(session_id, mk, EMERGENT_LLM_KEY, system_prompt, mode="calendar")
            raw = await mkt_send_message(chat, user_msg)
            parsed = mkt_extract_json(raw)
            return {
                "model": mk, "label": MKT_MODEL_LABELS[mk],
                "raw": raw, "calendar": parsed,
                "error": None if parsed else "JSON non valido"
            }
        except Exception as e:
            logger.exception("mkt_calendar error model=%s", mk)
            return {"model": mk, "label": MKT_MODEL_LABELS.get(mk, mk),
                    "raw": "", "calendar": None, "error": str(e)[:300]}

    results = list(await asyncio.gather(*[_call_one(mk) for mk in models]))
    return {"results": results}




# ============================================================
# Cucina Siciliana — override piatti (admin)
# I default statici vivono nel frontend; qui salviamo solo le modifiche
# dell'admin (per id) e gli eventuali piatti custom aggiunti.
# ============================================================
class DishIn(BaseModel):
    name: Optional[str] = None
    region: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    ingredients: Optional[List[str]] = None
    funFact: Optional[str] = None
    image: Optional[str] = None
    hidden: Optional[bool] = None
    custom: Optional[bool] = None


@api.get("/dishes/overrides")
async def list_dish_overrides():
    docs = await db.dish_overrides.find({}, {"_id": 0}).to_list(1000)
    return docs


@api.put("/dishes/{dish_id}")
async def upsert_dish(dish_id: str, body: DishIn, _: str = Depends(get_current_admin)):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    payload["id"] = dish_id
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.dish_overrides.update_one({"id": dish_id}, {"$set": payload}, upsert=True)
    doc = await db.dish_overrides.find_one({"id": dish_id}, {"_id": 0})
    return doc


@api.post("/dishes")
async def create_dish(body: DishIn, _: str = Depends(get_current_admin)):
    dish_id = "custom-" + uuid.uuid4().hex[:10]
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    payload["id"] = dish_id
    payload["custom"] = True
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.dish_overrides.insert_one(dict(payload))
    return {"id": dish_id}


@api.delete("/dishes/{dish_id}")
async def reset_dish(dish_id: str, _: str = Depends(get_current_admin)):
    await db.dish_overrides.delete_one({"id": dish_id})
    return {"ok": True}



# ============================================================
# Mount router + CORS
# ============================================================
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
