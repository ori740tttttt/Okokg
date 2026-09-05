"""One-off idempotent seed of iconic POIs for Palermo (PA) and Trapani (TP) provinces.
Skips any POI whose name already exists (case-insensitive)."""
import asyncio
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

ICONIC = [
    # --- Palermo (PA) ---
    {"name": "Duomo di Monreale", "category": "art", "lat": 38.0817, "lng": 13.2920, "town": "Monreale", "province": "PA",
     "description": "Capolavoro arabo-normanno con mosaici dorati, patrimonio UNESCO.", "price": "€4 (terrazze €2,50)", "hours": "08:30–12:45 / 14:30–17:00", "duration": "1–2 ore"},
    {"name": "Spiaggia di Mondello", "category": "beach", "lat": 38.2010, "lng": 13.3270, "town": "Mondello", "province": "PA",
     "description": "La spiaggia di Palermo: sabbia bianca e mare turchese tra Monte Pellegrino e Capo Gallo.", "duration": "mezza giornata"},
    {"name": "Cefalù", "category": "art", "lat": 38.0394, "lng": 14.0228, "town": "Cefalù", "province": "PA",
     "description": "Borgo medievale con Duomo normanno UNESCO e spiaggia, ai piedi della Rocca.", "duration": "1 giorno"},
    {"name": "Riserva di Capo Gallo", "category": "nature", "lat": 38.2160, "lng": 13.2870, "town": "Palermo", "province": "PA",
     "description": "Area marina protetta con scogliere, calette e snorkeling vicino a Mondello.", "duration": "mezza giornata"},
    {"name": "Santuario di Santa Rosalia (Monte Pellegrino)", "category": "nature", "lat": 38.1717, "lng": 13.3530, "town": "Palermo", "province": "PA",
     "description": "Santuario rupestre dedicato alla patrona di Palermo, con vista sul golfo.", "price": "Gratis", "duration": "1–2 ore"},
    {"name": "Villa Palagonia (Bagheria)", "category": "art", "lat": 38.0782, "lng": 13.5085, "town": "Bagheria", "province": "PA",
     "description": "La celebre 'villa dei mostri' barocca, famosa per le statue grottesche.", "price": "€6", "duration": "1 ora"},
    # --- Trapani (TP) ---
    {"name": "Erice", "category": "art", "lat": 38.0367, "lng": 12.5870, "town": "Erice", "province": "TP",
     "description": "Borgo medievale in cima al monte: chiese, vicoli acciottolati e dolci di mandorla.", "duration": "mezza giornata"},
    {"name": "Segesta — Tempio e Teatro", "category": "art", "lat": 37.9416, "lng": 12.8350, "town": "Calatafimi-Segesta", "province": "TP",
     "description": "Tempio dorico e teatro greco perfettamente conservati, immersi nella campagna.", "price": "€6", "hours": "09:00–19:30", "duration": "2–3 ore"},
    {"name": "Parco Archeologico di Selinunte", "category": "art", "lat": 37.5836, "lng": 12.8255, "town": "Castelvetrano", "province": "TP",
     "description": "Uno dei parchi archeologici più estesi del Mediterraneo, affacciato sul mare.", "price": "€6", "duration": "mezza giornata"},
    {"name": "Saline di Trapani e Paceco", "category": "nature", "lat": 37.9530, "lng": 12.4870, "town": "Trapani", "province": "TP",
     "description": "Saline con mulini a vento e fenicotteri: spettacolari al tramonto.", "duration": "1–2 ore"},
    {"name": "Favignana (Isole Egadi)", "category": "beach", "lat": 37.9320, "lng": 12.3290, "town": "Favignana", "province": "TP",
     "description": "L'isola 'farfalla' con cale di acqua cristallina: da girare in bici o in barca.", "duration": "1 giorno"},
    {"name": "Marsala", "category": "art", "lat": 37.7990, "lng": 12.4350, "town": "Marsala", "province": "TP",
     "description": "Città del vino e dello Sbarco dei Mille, con cantine storiche e centro barocco.", "duration": "mezza giornata"},
    {"name": "Grotta Mangiapane (Custonaci)", "category": "art", "lat": 38.1140, "lng": 12.6770, "town": "Custonaci", "province": "TP",
     "description": "Borgo-presepe dentro una grotta preistorica, set di film celebri.", "duration": "1 ora"},
    {"name": "Grotta delle Colombe", "category": "nature", "lat": 38.0877, "lng": 13.0801, "town": "Terrasini", "province": "PA",
     "description": "Grotta marina nascosta a Cala Muletti: si raggiunge a piedi dalla spiaggia di San Cataldo, a pochi minuti da Trappeto.",
     "maps_url": "https://www.google.com/maps/search/?api=1&query=Grotta+delle+Colombe+Cala+Muletti+Terrasini"},
]


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    existing = await db.pois.find({}, {"_id": 0, "name": 1}).to_list(2000)
    existing_names = {(p.get("name") or "").strip().lower() for p in existing}

    inserted = 0
    skipped = 0
    for poi in ICONIC:
        if poi["name"].strip().lower() in existing_names:
            skipped += 1
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "name": poi["name"],
            "category": poi["category"],
            "lat": poi["lat"],
            "lng": poi["lng"],
            "town": poi.get("town"),
            "province": poi.get("province"),
            "description": poi.get("description"),
            "price": poi.get("price"),
            "hours": poi.get("hours"),
            "duration": poi.get("duration"),
            "discount": poi.get("discount"),
            "notes": poi.get("notes"),
            "ticket_url": poi.get("ticket_url"),
            "maps_url": poi.get("maps_url"),
            "image_url": poi.get("image_url"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.pois.insert_one(doc)
        inserted += 1
        print(f"  + {poi['name']}")

    total = await db.pois.count_documents({})
    print(f"\nInserted: {inserted} | Skipped (already present): {skipped} | Total POIs now: {total}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
