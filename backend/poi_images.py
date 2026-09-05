"""
Risoluzione immagini per le attrazioni dell'itinerario.
Strategia:
1. Se il POI ha già image_url -> usalo.
2. Cerca una foto su Wikipedia (IT, poi EN) tramite REST summary.
3. Fallback: immagine curata per categoria (art / beach / nature / village).

Le immagini risolte vengono restituite come URL. Il caller può decidere di
cache-arle nel documento POI (image_url) per non richiamare Wikipedia ogni volta.
"""
import logging

import httpx

logger = logging.getLogger("appmatteo.poi_images")

USER_AGENT = "AppartamentoMatteo/1.0 (https://appartamentomatteo.it; info@appartamentomatteo.it)"

# Immagini di fallback per categoria (Unsplash/Pexels, uso libero)
CATEGORY_IMAGES = {
    "art": [
        "https://images.unsplash.com/photo-1561280618-d4a6f7d04e79?w=800&q=80",
        "https://images.unsplash.com/photo-1598624262720-0d04fa753768?w=800&q=80",
    ],
    "beach": [
        "https://images.unsplash.com/photo-1587648072376-282e37263c11?w=800&q=80",
        "https://images.unsplash.com/photo-1687937171141-0ff553c1d681?w=800&q=80",
    ],
    "nature": [
        "https://images.unsplash.com/photo-1681804528052-03c4d87b4769?w=800&q=80",
        "https://images.unsplash.com/photo-1597606904453-920ac2eb8efb?w=800&q=80",
    ],
    "village": [
        "https://images.unsplash.com/photo-1559139061-28d9de44e40e?w=800&q=80",
    ],
}
DEFAULT_IMAGE = "https://images.unsplash.com/photo-1523365154888-8a758819b722?w=800&q=80"


def category_fallback(category: str, seed: int = 0) -> str:
    imgs = CATEGORY_IMAGES.get((category or "").lower())
    if not imgs:
        return DEFAULT_IMAGE
    return imgs[seed % len(imgs)]


async def _wiki_thumb(client: httpx.AsyncClient, lang: str, title: str):
    """Cerca l'immagine di una pagina Wikipedia via action API (pageimages)."""
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "titles": title,
        "prop": "pageimages",
        "piprop": "original|thumbnail",
        "pithumbsize": 900,
        "redirects": 1,
        "format": "json",
    }
    try:
        r = await client.get(url, params=params, timeout=7.0, follow_redirects=True,
                             headers={"User-Agent": USER_AGENT})
        if r.status_code != 200:
            return None
        pages = (((r.json() or {}).get("query") or {}).get("pages") or {})
        for _pid, page in pages.items():
            orig = (page.get("original") or {}).get("source")
            thumb = (page.get("thumbnail") or {}).get("source")
            img = orig or thumb
            if img:
                return img.split("?")[0]  # rimuove i parametri utm
    except Exception:
        return None
    return None


def _title_variants(name: str):
    """Genera varianti del nome per aumentare le probabilità di match su Wikipedia."""
    n = (name or "").strip()
    variants = [n]
    # rimuove parti tra parentesi: "Villa Palagonia (Bagheria)" -> "Villa Palagonia"
    if "(" in n:
        variants.append(n.split("(")[0].strip())
    # rimuove dopo trattino/– : "Segesta — Tempio e Teatro" -> "Segesta"
    for sep in ["—", "–", " - ", ":"]:
        if sep in n:
            variants.append(n.split(sep)[0].strip())
    # dedup preservando ordine
    seen, out = set(), []
    for v in variants:
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


async def _wiki_search_title(client: httpx.AsyncClient, lang: str, query: str):
    """Trova il titolo di pagina Wikipedia più pertinente per una query."""
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {"action": "query", "list": "search", "srsearch": query,
              "srlimit": 1, "format": "json"}
    try:
        r = await client.get(url, params=params, timeout=7.0, follow_redirects=True,
                             headers={"User-Agent": USER_AGENT})
        if r.status_code != 200:
            return None
        hits = (((r.json() or {}).get("query") or {}).get("search") or [])
        if hits:
            return hits[0].get("title")
    except Exception:
        return None
    return None


async def resolve_image(client: httpx.AsyncClient, name: str, category: str = "",
                        existing: str = None, seed: int = 0) -> str:
    """Restituisce l'URL immagine migliore per un'attrazione."""
    if existing and existing.strip():
        return existing.strip()
    # 1) prova i titoli diretti
    for title in _title_variants(name):
        for lang in ("it", "en"):
            img = await _wiki_thumb(client, lang, title)
            if img:
                return img
    # 2) ricerca Wikipedia -> pagina migliore -> immagine
    for lang in ("it", "en"):
        title = await _wiki_search_title(client, lang, f"{name} Sicilia")
        if title:
            img = await _wiki_thumb(client, lang, title)
            if img:
                return img
    # 3) fallback per categoria
    return category_fallback(category, seed)
