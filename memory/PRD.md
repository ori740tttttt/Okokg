# PRD — Traap / Appartamento Matteo (App mobile Expo)

## Problem statement
Clonare il progetto GitHub "Traap" (app turistica/affitto casa a Trappeto, Sicilia) e renderlo un'app mobile nativa.
Scelte utente: Ospite + Admin completo, tutte le funzioni, Emergent LLM Key, multilingua, stesso stile mediterraneo.

## Architettura
- Backend: FastAPI + MongoDB riusato dal repo originale (server.py ~250KB, moduli carmelo_ai, marketing_ai, itinerary_pdf, poi_*). Emergent LLM Key per Carmelo AI.
- Frontend: Expo Router (React Native), tema mediterraneo (sand/terracotta/olive) in src/theme.ts.
- i18n: it/en/es/fr/de con expo-localization + react-i18next.

## Implementato (2026-06)
- Home: hero, prezzo, calendario disponibilità, dettagli casa, galleria, CTA mappa/cucina.
- Prenotazione: calcolo preventivo live (/quote) + invio richiesta (/bookings).
- Luoghi/POI: lista filtrabile per categoria + indicazioni stradali; dettaglio POI.
- Carmelo IA: chat streaming (SSE) con Emergent LLM Key.
- Info/FAQ: FAQ, invio domanda ospite, contatti, accesso admin.
- Admin: login JWT, dashboard con statistiche, gestione prenotazioni (approva/rifiuta), prezzi & calendario.
- **Cucina Siciliana** (2026-06): 64 specialità (Palermo & Trapani), indice con filtro per zona, schede dettaglio (descrizione, ingredienti, curiosità), preferiti persistiti sul dispositivo. **Foto reali** dei piatti (LoremFlickr, stabili per piatto) con emoji come badge.
- **Spiagge · Bussola dei venti** (2026-06): meteo live (Open-Meteo: temp/vento/UV/tramonto), consigli dinamici in base al vento (costa Nord/Sud), 40+ spiagge PA/TP con stato IDEALE/MOSSO, filtri (bambini, attrezzate, snorkel, parcheggio, gratis), ricerca, info parcheggio/affluenza/fondale, "Portami lì" (Google Maps). Bilingue IT/EN.
- **Feste & Sagre** (2026-06): eventi ufficiali PA/TP con date 2026 verificate (San Giuseppe 19/3, Misteri Trapani 3-4/4, Ballo dei Diavoli Prizzi 5/4, Sagra Carciofo Cerda 23-26/4, San Vito 15/6, Festino Santa Rosalia 14-15/7, Acchianata 3-4/9, Cous Cous Fest 18-27/9, Santa Lucia 13/12, Presepe Vivente Custonaci). Marcatori sul calendario di prenotazione + prossime feste in Home.

## Credenziali
- Admin: admin / TraapAdmin2026! (vedi test_credentials.md)

## Backlog / Prossimi passi
- P1: Admin foto/gallery manager, POI manager, FAQ manager, itinerari salvati.
- P1: Mappa interattiva nativa (react-native-maps) su build device.
- P2: Marketing AI tools, Google Business, accounting (dal backend esistente).
- P2: Area ospite con sblocco tramite codice di conferma (verify-code) + itinerario PDF.
