# PRD — Appartamento Matteo (Okok clone)

## Problem statement
Clonare esattamente il repo GitHub accetta091/Okok (app turistica siciliana, vacation rental "Appartamento Matteo" a Trappeto) e completare le funzioni mancanti richieste dall'utente.

## Architecture
- Backend: FastAPI + MongoDB (motor). AI "Carmelo" via emergentintegrations (EMERGENT_LLM_KEY).
- Frontend: Expo Router (React Native). Tabs ospite: Home, Luoghi, Itinerario, Info. Admin: dashboard + moduli.
- Auth: JWT admin (Matteo / D5230).

## Implemented
- Clone completo funzionante (114 POI seed, gallerie, prezzi, prenotazioni, Carmelo IA).
- Admin dashboard raggruppata: Prenotazioni, Prenotazione manuale, Statistiche, Contabilità, Prezzi, Costi&tariffe, Codici sconto, Foto, Mappa Interattiva, Cucina, Domande ospiti, FAQ, Marketing AI, Google Business, WhatsApp.
- Tab pubblico "Itinerario IA" (Carmelo) rimosso dal pubblico (accessibile solo admin) per risparmiare chiavi LLM.
- Guest: mappa/itinerario con sblocco codice, POI cliccabili con scheda (prezzo/orari/durata/sconti/note/coordinate) + Indicazioni (Google Maps) + Aggiungi all'itinerario + PDF. Store itinerario condiviso + widget flottante "Il mio itinerario". Spiagge incluse nei POI.
- Admin "Mappa Interattiva": CRUD POI completo (nome, coordinate, comune, categoria, descrizione, prezzo, orari, durata, sconti, link biglietti/maps/foto) + Import/Export Word, PDF compilabile, CSV, Template.
- Sezione omaggio in prenotazione (portachiavi souvenir + itinerario digitale).
- Calendario Home: popup festa al tocco con nome, durata e curiosità verificata.
- Feste & Sagre: elenco verificato PA/TP con durata + curiosità.
- Info: telefono +39 388 161 1514 (+ WhatsApp), CIN IT082074C2NA6HPQMB, CIR 19082074C252260.

## Credentials
- Admin: Matteo / D5230
- Codice sblocco itinerario di test (ai_access): MATTEO26

## Backlog / next
- P1: schede POI con foto reali (upload immagini POI da admin).
- P2: rispondere alle domande ospiti in-app (thread).
