"""
IP -> geo enrichment with a fallback chain.

Tries provider A first, then provider B if A fails or is disabled.
If both fail, returns (None, None, None) -- the submission must still
be stored without geo data. Enrichment failure must never fail the request.
"""
import httpx

from app.config import settings


async def _try_provider_a(ip: str) -> tuple[str | None, str | None]:
    if settings.disable_geo_provider_a:
        return None, None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.geo_provider_a_url}/{ip}")
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "success":
                return data.get("country"), data.get("city")
    except Exception:
        pass
    return None, None


async def _try_provider_b(ip: str) -> tuple[str | None, str | None]:
    if settings.disable_geo_provider_b:
        return None, None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.geo_provider_b_url}/{ip}/json/")
            resp.raise_for_status()
            data = resp.json()
            if not data.get("error"):
                return data.get("country_name"), data.get("city")
    except Exception:
        pass
    return None, None


async def enrich_ip(ip: str) -> dict:
    """
    Returns {country, city, provider_used} where provider_used is
    'provider_a', 'provider_b', or None if both failed / were disabled.
    Never raises -- callers can always store the submission.
    """
    if ip in ("127.0.0.1", "testclient", "localhost"):
        # local dev / test requests won't resolve on any real geo provider
        return {"country": None, "city": None, "provider_used": None}

    country, city = await _try_provider_a(ip)
    if country:
        return {"country": country, "city": city, "provider_used": "provider_a"}

    country, city = await _try_provider_b(ip)
    if country:
        return {"country": country, "city": city, "provider_used": "provider_b"}

    return {"country": None, "city": None, "provider_used": None}
