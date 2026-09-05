"""Backend regression tests for Appartamento Matteo (admin + guest itinerary flows).

Covers:
- Auth (POST /auth/login) 
- Admin: stats, accounting, manual booking, discount codes,
  commission rates, whatsapp, guest questions, faqs, photos, marketing library,
  google-business settings.
- Guest: verify-code (MATTEO26), itinerary PDF (POST /itinerary/pdf)
"""
import time
import uuid
import requests

# ---------------------- AUTH ----------------------

def test_login_success(api_url):
    r = requests.post(f"{api_url}/auth/login", json={"username": "Matteo", "password": "D5230"}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("username") == "Matteo"
    assert isinstance(body.get("token"), str) and len(body["token"]) > 20


def test_login_wrong_password(api_url):
    r = requests.post(f"{api_url}/auth/login", json={"username": "Matteo", "password": "WRONG"}, timeout=15)
    assert r.status_code in (400, 401, 403)


def test_admin_endpoint_requires_auth(api_url):
    r = requests.get(f"{api_url}/admin/stats", timeout=15)
    assert r.status_code in (401, 403)


# ---------------------- ADMIN STATS ----------------------

def test_admin_stats(api_url, admin_headers):
    r = requests.get(f"{api_url}/admin/stats", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, dict) and len(data) > 0


# ---------------------- ADMIN ACCOUNTING ----------------------

def test_admin_accounting(api_url, admin_headers):
    r = requests.get(f"{api_url}/admin/accounting", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, dict)
    # Some numeric-ish totals should be present
    keys_lc = " ".join(data.keys()).lower()
    assert any(k in keys_lc for k in ["gross", "net", "lord", "netto", "total", "commission"])


# ---------------------- MANUAL BOOKING ----------------------

def test_admin_manual_booking_create(api_url, admin_headers):
    payload = {
        "guest_name": f"TEST_Guest_{uuid.uuid4().hex[:6]}",
        "guest_email": "test@example.com",
        "check_in": "2026-04-10",
        "check_out": "2026-04-13",
        "guests": 2,
        "total_amount": 300.0,
        "source": "site",
        "status": "approved",
    }
    r = requests.post(f"{api_url}/admin/bookings/manual", headers=admin_headers, json=payload, timeout=20)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert isinstance(body, dict)
    assert body.get("guest_name") == payload["guest_name"] or body.get("id")


# ---------------------- DISCOUNT CODES ----------------------

def test_discount_code_crud(api_url, admin_headers):
    # LIST
    r = requests.get(f"{api_url}/discount-codes", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    items_before = r.json()
    assert isinstance(items_before, list)

    # CREATE regular discount
    code_val = f"TESTCODE{uuid.uuid4().hex[:5].upper()}"
    payload = {"code": code_val, "type": "discount", "percent": 10, "valid_from": "2026-01-01", "valid_to": "2026-12-31"}
    r = requests.post(f"{api_url}/discount-codes", headers=admin_headers, json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    created = r.json()
    code_id = created.get("id")
    assert code_id, f"no id in response: {created}"

    # Verify persisted
    r2 = requests.get(f"{api_url}/discount-codes", headers=admin_headers, timeout=15)
    assert r2.status_code == 200
    assert any((c.get("code") == code_val) for c in r2.json())

    # DELETE
    r3 = requests.delete(f"{api_url}/discount-codes/{code_id}", headers=admin_headers, timeout=15)
    assert r3.status_code in (200, 204)


def test_matteo26_unlock_code_present(api_url, admin_headers):
    """MATTEO26 ai_access code must exist (spec says preseeded)."""
    r = requests.get(f"{api_url}/discount-codes", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    codes = r.json()
    assert any(c.get("code") == "MATTEO26" for c in codes), "MATTEO26 ai_access code not found"


# ---------------------- COMMISSION RATES ----------------------

def test_admin_commission_rates_get_and_update(api_url, admin_headers):
    r = requests.get(f"{api_url}/admin/commission-rates", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    original = r.json()
    assert isinstance(original, dict)

    # Update (set booking_pct=17.5 to test persistence)
    payload = dict(original)
    payload["booking_pct"] = 17.5
    r2 = requests.put(f"{api_url}/admin/commission-rates", headers=admin_headers, json=payload, timeout=15)
    assert r2.status_code in (200, 201), r2.text

    # Verify persistence
    r3 = requests.get(f"{api_url}/admin/commission-rates", headers=admin_headers, timeout=15)
    assert r3.status_code == 200
    assert float(r3.json().get("booking_pct", 0)) == 17.5


# ---------------------- WHATSAPP ----------------------

def test_admin_whatsapp_get_put(api_url, admin_headers):
    r = requests.get(f"{api_url}/admin/whatsapp", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)

    payload = dict(body)
    payload["phone"] = "+390000000000"
    r2 = requests.put(f"{api_url}/admin/whatsapp", headers=admin_headers, json=payload, timeout=15)
    assert r2.status_code in (200, 201), r2.text

    r3 = requests.get(f"{api_url}/admin/whatsapp", headers=admin_headers, timeout=15)
    assert r3.status_code == 200
    assert r3.json().get("phone") == "+390000000000"


# ---------------------- GUEST QUESTIONS ----------------------

def test_admin_guest_questions_list(api_url, admin_headers):
    r = requests.get(f"{api_url}/admin/guest-questions", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    # backend returns {"questions": [...], "counts": {...}}
    assert isinstance(body, dict)
    assert "questions" in body
    assert isinstance(body["questions"], list)


# ---------------------- FAQS ----------------------

def test_admin_faqs_crud(api_url, admin_headers):
    r = requests.get(f"{api_url}/admin/faqs", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    # backend returns {"faqs":[], "categories":[...]}
    assert isinstance(body, dict) and "faqs" in body
    assert isinstance(body["faqs"], list)

    q = f"TEST_Q_{uuid.uuid4().hex[:5]}"
    payload = {"question_it": q, "answer_it": "TEST answer", "category": "casa"}
    r2 = requests.post(f"{api_url}/admin/faqs", headers=admin_headers, json=payload, timeout=15)
    assert r2.status_code in (200, 201), r2.text
    created = r2.json()
    fid = created.get("id")
    assert fid

    # Update
    r3 = requests.put(f"{api_url}/admin/faqs/{fid}", headers=admin_headers,
                      json={"question_it": q, "answer_it": "TEST updated", "category": "casa"}, timeout=15)
    assert r3.status_code in (200, 201), r3.text

    # Delete
    r4 = requests.delete(f"{api_url}/admin/faqs/{fid}", headers=admin_headers, timeout=15)
    assert r4.status_code in (200, 204)


# ---------------------- PHOTOS ----------------------

def test_photos_list(api_url):
    r = requests.get(f"{api_url}/photos", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------------------- MARKETING ----------------------

def test_admin_marketing_library(api_url, admin_headers):
    r = requests.get(f"{api_url}/admin/marketing/library", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_marketing_generate(api_url, admin_headers):
    """LLM call — slow. Run only once."""
    payload = {
        "platform": "instagram_post",
        "topic": "Test marketing per Appartamento Matteo a Cefalù",
        "tone": "familiare",
        "languages": ["it"],
    }
    r = requests.post(f"{api_url}/admin/marketing/generate", headers=admin_headers, json=payload, timeout=90)
    # LLM may return various status codes; accept success
    assert r.status_code in (200, 201), f"{r.status_code}: {r.text[:400]}"
    body = r.json()
    assert isinstance(body, dict)


# ---------------------- GOOGLE BUSINESS ----------------------

def test_admin_google_business_settings(api_url, admin_headers):
    r = requests.get(f"{api_url}/admin/google-business/settings", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)

    payload = dict(body)
    payload["business_name"] = "TEST Appartamento Matteo"
    r2 = requests.put(f"{api_url}/admin/google-business/settings", headers=admin_headers, json=payload, timeout=15)
    assert r2.status_code in (200, 201), r2.text


# ---------------------- GUEST ITINERARY ----------------------

def test_verify_code_matteo26(api_url):
    r = requests.post(f"{api_url}/verify-code", json={"code": "MATTEO26"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    # valid=true, or presence of ok/type field
    assert body.get("valid", True) is not False


def test_verify_code_invalid(api_url):
    r = requests.post(f"{api_url}/verify-code", json={"code": "NOPE_INVALID_XYZ"}, timeout=15)
    assert r.status_code in (400, 401, 403, 404, 200)
    if r.status_code == 200:
        assert r.json().get("valid") is False


def test_itinerary_pdf(api_url):
    # First get some poi ids
    r = requests.get(f"{api_url}/pois", timeout=15)
    if r.status_code != 200:
        # fallback endpoint name
        r = requests.get(f"{api_url}/places", timeout=15)
    assert r.status_code == 200, r.text
    pois = r.json()
    if not isinstance(pois, list) or len(pois) == 0:
        import pytest as _p
        _p.skip("No POIs available to build itinerary")
    poi_ids = [p.get("id") for p in pois[:2] if p.get("id")]

    payload = {"code": "MATTEO26", "poi_ids": poi_ids, "traveler_name": "TEST User"}
    r2 = requests.post(f"{api_url}/itinerary/pdf", json=payload, timeout=60)
    assert r2.status_code == 200, f"{r2.status_code}: {r2.text[:300]}"
    # Response could be pdf bytes or a URL
    ctype = r2.headers.get("content-type", "")
    assert "pdf" in ctype.lower() or "json" in ctype.lower(), f"unexpected content-type: {ctype}"
    if "pdf" in ctype.lower():
        assert len(r2.content) > 500
