// Feste e Sagre — provincia di Palermo (PA) e Trapani (TP).
// SOLO ricorrenze ufficiali/consolidate. Le feste patronali usano il giorno
// liturgico fisso; le sagre a data variabile sono marcate `approx` (senza pallino
// sul calendario) e riportano "date da confermare".
export type Festival = {
  id: string;
  name: string;
  place: string;
  province: "PA" | "TP";
  start: string; // ISO 2026
  end: string; // ISO 2026
  dateLabel: string;
  category: "religiosa" | "sagra" | "folklore";
  icon: string;
  description: string;
  curiosity: string;
  approx?: boolean; // data variabile: non marcare il calendario
  note?: string;
};

export const festivals: Festival[] = [
  // ————— Provincia di PALERMO —————
  { id: "corleone-san-leoluca", name: "Festa di San Leoluca", place: "Corleone", province: "PA", start: "2026-03-01", end: "2026-03-01", dateLabel: "1 marzo 2026", category: "religiosa", icon: "⛪", description: "Festa patronale in onore di San Leoluca, monaco basiliano protettore di Corleone.", curiosity: "Le reliquie del santo sono custodite nella Chiesa Madre del paese." },
  { id: "san-giuseppe-salemi", name: "Festa di San Giuseppe · Pani e Tavolate", place: "Salemi", province: "TP", start: "2026-03-19", end: "2026-03-19", dateLabel: "19 marzo 2026", category: "religiosa", icon: "🍞", description: "Tavolate e altari votivi ricoperti di pani artistici modellati a mano in onore di San Giuseppe.", curiosity: "A Salemi i pani di San Giuseppe sono vere opere d'arte in pasta cotta al forno." },
  { id: "misteri-trapani", name: "Processione dei Misteri", place: "Trapani", province: "TP", start: "2026-04-03", end: "2026-04-04", dateLabel: "Venerdì Santo · 3–4 aprile 2026", category: "religiosa", icon: "✝️", description: "I venti Sacri Gruppi scolpiti sfilano per la città in una processione che dura quasi 24 ore.", curiosity: "I gruppi sono portati a spalla con l'antica 'annacata', il tipico dondolio a ritmo delle marce." },
  { id: "ballo-diavoli-prizzi", name: "Ballo dei Diavoli (Abballu di li Diavuli)", place: "Prizzi", province: "PA", start: "2026-04-05", end: "2026-04-05", dateLabel: "Domenica di Pasqua · 5 aprile 2026", category: "folklore", icon: "😈", description: "I Diavoli mascherati e la Morte ostacolano l'incontro tra la Madonna e il Cristo risorto, finché gli Angeli li sconfiggono.", curiosity: "Rito arcaico unico in Sicilia, culmina in Piazza Sant'Anna con la vittoria del bene." },
  { id: "sagra-carciofo-cerda", name: "Sagra del Carciofo · Cynara Festival", place: "Cerda", province: "PA", start: "2026-04-23", end: "2026-04-26", dateLabel: "23–26 aprile 2026 (clou 25 aprile)", category: "sagra", icon: "🌿", description: "Quattro giorni dedicati al carciofo di Cerda con degustazioni, cortei storici e stand gastronomici.", curiosity: "A Cerda sorge il monumento al carciofo: il paese ne è la capitale in Sicilia." },
  { id: "calatafimi-crocifisso", name: "Festa del SS. Crocifisso", place: "Calatafimi-Segesta", province: "TP", start: "2026-05-01", end: "2026-05-03", dateLabel: "1–3 maggio 2026", category: "religiosa", icon: "✝️", description: "Solenne festa del Santissimo Crocifisso, tra le più sentite del trapanese.", curiosity: "La grande festa storica con i 'Ceti' si celebra ogni tre anni con carri e cortei." },
  { id: "monreale-crocifisso", name: "Festa del SS. Crocifisso", place: "Monreale", province: "PA", start: "2026-05-03", end: "2026-05-03", dateLabel: "3 maggio 2026", category: "religiosa", icon: "⛪", description: "Festa del Santissimo Crocifisso, patrono di Monreale, con processione e celebrazioni solenni.", curiosity: "Nel 2026 la festa ha celebrato il suo 400° anniversario." },
  { id: "gangi-san-cataldo", name: "Festa di San Cataldo", place: "Gangi", province: "PA", start: "2026-05-10", end: "2026-05-10", dateLabel: "10 maggio 2026", category: "religiosa", icon: "⛪", description: "Festa patronale nel borgo medievale di Gangi, tra i più belli d'Italia.", curiosity: "Gangi è arroccata sul Monte Marone, con vista sull'Etna nelle giornate limpide." },
  { id: "san-vito-patrono", name: "Festa di San Vito Martire", place: "San Vito Lo Capo", province: "TP", start: "2026-06-15", end: "2026-06-15", dateLabel: "15 giugno 2026", category: "religiosa", icon: "⛪", description: "Festa patronale in onore di San Vito, con processione e festeggiamenti nel borgo.", curiosity: "Il paese e il suo santuario-fortezza devono a San Vito il nome e la storia millenaria." },
  { id: "petralia-sottana-san-calogero", name: "Festa di San Calogero", place: "Petralia Sottana", province: "PA", start: "2026-06-18", end: "2026-06-18", dateLabel: "18 giugno 2026", category: "religiosa", icon: "⛪", description: "Festa patronale sulle Madonie in onore di San Calogero eremita.", curiosity: "Petralia Sottana è porta d'accesso al Parco delle Madonie." },
  { id: "alcamo-madonna-miracoli", name: "Festa della Madonna dei Miracoli", place: "Alcamo", province: "TP", start: "2026-06-19", end: "2026-06-21", dateLabel: "19–21 giugno 2026", category: "religiosa", icon: "⛪", description: "Festa patronale di Alcamo in onore della Madonna dei Miracoli.", curiosity: "Alcamo celebra anche la Madonna dell'Alto l'8 settembre." },
  { id: "marsala-san-giovanni", name: "Festa di San Giovanni Battista", place: "Marsala", province: "TP", start: "2026-06-24", end: "2026-06-24", dateLabel: "24 giugno 2026", category: "religiosa", icon: "⛪", description: "Festa patronale di Marsala in onore di San Giovanni Battista.", curiosity: "Legata alla Grotta della Sibilla presso la chiesa di San Giovanni al Boeo." },
  { id: "petralia-soprana-pietro-paolo", name: "Festa dei SS. Pietro e Paolo", place: "Petralia Soprana", province: "PA", start: "2026-06-29", end: "2026-06-29", dateLabel: "29 giugno 2026", category: "religiosa", icon: "⛪", description: "Festa patronale nel borgo più alto delle Madonie.", curiosity: "Petralia Soprana è tra 'I Borghi più belli d'Italia'." },
  { id: "festino-santa-rosalia", name: "Festino di Santa Rosalia", place: "Palermo", province: "PA", start: "2026-07-14", end: "2026-07-15", dateLabel: "14–15 luglio 2026", category: "religiosa", icon: "👑", description: "Il carro trionfale della 'Santuzza' sfila dal Palazzo Reale al Foro Italico, chiudendo con i fuochi sul mare.", curiosity: "Al culmine risuona il grido 'Viva Palermo e Santa Rosalia!'." },
  { id: "castelbuono-santanna", name: "Festa di Sant'Anna", place: "Castelbuono", province: "PA", start: "2026-07-26", end: "2026-07-26", dateLabel: "26 luglio 2026", category: "religiosa", icon: "⛪", description: "Festa patronale di Castelbuono, in onore di Sant'Anna, con processione fino al Castello dei Ventimiglia.", curiosity: "Castelbuono è la patria della 'manna' e del dolce testa di turco." },
  { id: "trapani-sant-alberto", name: "Festa di Sant'Alberto", place: "Trapani", province: "TP", start: "2026-08-07", end: "2026-08-07", dateLabel: "7 agosto 2026", category: "religiosa", icon: "⛪", description: "Festa patronale di Trapani in onore di Sant'Alberto degli Abati.", curiosity: "Si distribuisce l'acqua benedetta di Sant'Alberto, ritenuta miracolosa." },
  { id: "cefalu-trasfigurazione", name: "Festa del SS. Salvatore (Trasfigurazione)", place: "Cefalù", province: "PA", start: "2026-08-06", end: "2026-08-06", dateLabel: "6 agosto 2026", category: "religiosa", icon: "⛪", description: "Festa patronale di Cefalù con la tradizionale 'ntinna a mare, l'albero della cuccagna sul molo.", curiosity: "I concorrenti sfidano un palo insaponato proteso sul mare per afferrare la bandierina." },
  { id: "bagheria-san-giuseppe", name: "Festa di San Giuseppe", place: "Bagheria", province: "PA", start: "2026-08-02", end: "2026-08-02", dateLabel: "Prima domenica di agosto (2 agosto 2026)", category: "religiosa", icon: "⛪", description: "Festa patronale estiva di Bagheria in onore di San Giuseppe.", curiosity: "Bagheria è celebre per le sue splendide ville barocche settecentesche." },
  { id: "castellammare-madonna-soccorso", name: "Madonna del Soccorso · Rievocazione", place: "Castellammare del Golfo", province: "TP", start: "2026-08-19", end: "2026-08-21", dateLabel: "19–21 agosto 2026", category: "folklore", icon: "⛪", description: "Festa patronale con rievocazione storica dello sbarco e processione a mare.", curiosity: "Il porticciolo si illumina di barche in processione sotto il castello." },
  { id: "mazara-festino-san-vito", name: "Festino di San Vito", place: "Mazara del Vallo", province: "TP", start: "2026-08-16", end: "2026-08-23", dateLabel: "16–23 agosto 2026", category: "religiosa", icon: "⛪", description: "Settimana di festeggiamenti per il patrono San Vito con processioni e la sfilata del carro.", curiosity: "La ricorrenza liturgica cade il 15 giugno, ma il grande festino è ad agosto." },
  { id: "trapani-madonna", name: "Festa della Madonna di Trapani", place: "Trapani", province: "TP", start: "2026-08-16", end: "2026-08-16", dateLabel: "16 agosto 2026", category: "religiosa", icon: "⛪", description: "Solenne festa mariana con processione a mare della venerata effige della Madonna.", curiosity: "La statua marmorea è attribuita a Nino Pisano, nel Santuario dell'Annunziata." },
  { id: "custonaci-madonna", name: "Madonna di Custonaci", place: "Custonaci / Erice", province: "TP", start: "2026-08-26", end: "2026-08-26", dateLabel: "Ultimo mercoledì di agosto (26 agosto 2026)", category: "religiosa", icon: "⛪", description: "Festa patronale con il quadro della Madonna portato in processione tra Custonaci ed Erice.", curiosity: "Ogni tre anni si tiene la 'Peregrinatio' con la solenne processione dei quadri." },
  { id: "misilmeri-san-giusto", name: "Festa di San Giusto", place: "Misilmeri", province: "PA", start: "2026-08-30", end: "2026-08-30", dateLabel: "Ultima domenica di agosto (30 agosto 2026)", category: "religiosa", icon: "⛪", description: "Festa patronale di Misilmeri in onore di San Giusto martire.", curiosity: "Misilmeri fu teatro della storica battaglia risorgimentale di Gorgo Lungo." },
  { id: "acchianata-santa-rosalia", name: "Acchianata a Monte Pellegrino", place: "Palermo", province: "PA", start: "2026-09-03", end: "2026-09-04", dateLabel: "3–4 settembre 2026", category: "religiosa", icon: "🕯️", description: "Migliaia di fedeli salgono di notte al Santuario di Santa Rosalia sul Monte Pellegrino.", curiosity: "È il pellegrinaggio più sentito dell'anno, complementare al Festino di luglio." },
  { id: "altavilla-madonna-milicia", name: "Madonna della Milicia", place: "Altavilla Milicia", province: "PA", start: "2026-09-06", end: "2026-09-06", dateLabel: "6 settembre 2026", category: "religiosa", icon: "⛪", description: "Festa mariana con la venerata immagine di Maria SS. Lauretana, tra fede e folklore.", curiosity: "Il santuario è meta di pellegrinaggio da tutta la Sicilia occidentale." },
  { id: "terrasini-madonna-grazie", name: "Madonna delle Grazie", place: "Terrasini", province: "PA", start: "2026-09-08", end: "2026-09-08", dateLabel: "8 settembre 2026", category: "religiosa", icon: "⛪", description: "Festa patronale di Terrasini in onore della Madonna delle Grazie.", curiosity: "Terrasini è nota anche per la festa dei 'Schietti' a Pasqua." },
  { id: "carini-crocifisso", name: "Festa del SS. Crocifisso", place: "Carini", province: "PA", start: "2026-09-14", end: "2026-09-14", dateLabel: "14 settembre 2026", category: "religiosa", icon: "✝️", description: "Festa patronale di Carini in onore del Santissimo Crocifisso.", curiosity: "Carini è celebre per il suo castello e la leggenda della 'Baronessa di Carini'." },
  { id: "favignana-crocifisso", name: "Festa del SS. Crocifisso", place: "Favignana", province: "TP", start: "2026-09-14", end: "2026-09-14", dateLabel: "14 settembre 2026", category: "religiosa", icon: "✝️", description: "Festa patronale dell'isola di Favignana in onore del Santissimo Crocifisso.", curiosity: "Favignana è la maggiore delle Egadi, terra dell'antica tonnara Florio." },
  { id: "cous-cous-fest", name: "Cous Cous Fest", place: "San Vito Lo Capo", province: "TP", start: "2026-09-18", end: "2026-09-27", dateLabel: "18–27 settembre 2026", category: "sagra", icon: "🍲", description: "Festival internazionale del cous cous, simbolo d'integrazione mediterranea: gare tra chef, degustazioni e concerti.", curiosity: "Il cous cous alla trapanese, di pesce, è l'anima della manifestazione." },
  { id: "pantelleria-san-fortunato", name: "Festa di San Fortunato", place: "Pantelleria", province: "TP", start: "2026-10-16", end: "2026-10-16", dateLabel: "16 ottobre 2026", category: "religiosa", icon: "⛪", description: "Festa patronale dell'isola di Pantelleria in onore di San Fortunato martire.", curiosity: "Pantelleria è la 'perla nera' del Mediterraneo, terra di Zibibbo e capperi." },
  { id: "partinico-san-leonardo", name: "Festa di San Leonardo", place: "Partinico", province: "PA", start: "2026-11-06", end: "2026-11-06", dateLabel: "6 novembre 2026", category: "religiosa", icon: "⛪", description: "Festa patronale di Partinico in onore di San Leonardo abate.", curiosity: "Partinico sorge nella fertile piana tra Palermo e il golfo di Castellammare." },
  { id: "termini-immacolata", name: "Immacolata Concezione", place: "Termini Imerese", province: "PA", start: "2026-12-08", end: "2026-12-08", dateLabel: "8 dicembre 2026", category: "religiosa", icon: "⛪", description: "Festa patronale di Termini Imerese in onore dell'Immacolata Concezione.", curiosity: "Termini è città termale d'origine romana, ricca di storia e archeologia." },
  { id: "santa-lucia-palermo", name: "Festa di Santa Lucia", place: "Palermo", province: "PA", start: "2026-12-13", end: "2026-12-13", dateLabel: "13 dicembre 2026", category: "religiosa", icon: "🕯️", description: "Il 13 dicembre i palermitani rinunciano a pane e pasta e mangiano cuccìa, arancine e panelle.", curiosity: "La cuccìa, grano bollito con ricotta o crema, è il dolce simbolo della giornata." },
  { id: "presepe-vivente-custonaci", name: "Presepe Vivente di Custonaci", place: "Custonaci (Grotta Mangiapane)", province: "TP", start: "2026-12-26", end: "2026-12-31", dateLabel: "Periodo natalizio (dal 26 dicembre)", category: "folklore", icon: "🌟", description: "Nel borgo rupestre della Grotta Mangiapane rivive un villaggio con oltre 160 figuranti e gli antichi mestieri.", curiosity: "La scenografia è una grotta abitata fin dal Paleolitico.", note: "Prosegue nei primi giorni di gennaio: verifica le date ufficiali dell'edizione." },

  // ————— SAGRE a data variabile (da confermare ogni anno) —————
  { id: "sagra-cannolo-dattilo", name: "Sagra del Cannolo", place: "Dattilo (Paceco)", province: "TP", start: "2026-07-15", end: "2026-07-15", dateLabel: "Estate — date da confermare", category: "sagra", icon: "🥠", description: "Sagra dedicata al celebre cannolo di ricotta di pecora, nella frazione di Dattilo.", curiosity: "I cannoli di Dattilo sono famosi per le dimensioni generose.", approx: true },
  { id: "sagra-cassatelle-favignana", name: "Sagra delle Cassatelle", place: "Favignana", province: "TP", start: "2026-08-01", end: "2026-08-01", dateLabel: "Estate — date da confermare", category: "sagra", icon: "🥟", description: "Sagra del dolce fritto ripieno di ricotta, tipico delle Egadi.", curiosity: "Le cassatelle si gustano calde, spolverate di zucchero a velo.", approx: true },
  { id: "sagra-aglio-rosso-paceco", name: "Sagra dell'Aglio Rosso di Nubia", place: "Paceco / Nubia", province: "TP", start: "2026-07-20", end: "2026-07-20", dateLabel: "Estate — date da confermare", category: "sagra", icon: "🧄", description: "Sagra dedicata al pregiato aglio rosso di Nubia, presidio Slow Food.", curiosity: "L'aglio si intreccia a mano nelle caratteristiche 'trizze'.", approx: true },
];

// Ordina per data e restituisce le prossime feste a partire da 'from'.
export function upcomingFestivals(from: Date = new Date()): Festival[] {
  const fromIso = from.toISOString().slice(0, 10);
  const sorted = [...festivals].sort((a, b) => a.start.localeCompare(b.start));
  const future = sorted.filter((f) => f.end >= fromIso);
  return future.length > 0 ? future : sorted;
}

// Date ISO da marcare sul calendario (solo eventi a data certa, non `approx`).
export function festivalDateSet(): Record<string, Festival[]> {
  const map: Record<string, Festival[]> = {};
  for (const f of festivals) {
    if (f.approx) continue;
    const cur = new Date(f.start);
    const end = new Date(f.end);
    while (cur <= end) {
      const iso = cur.toISOString().slice(0, 10);
      if (!map[iso]) map[iso] = [];
      map[iso].push(f);
      cur.setDate(cur.getDate() + 1);
    }
  }
  return map;
}
