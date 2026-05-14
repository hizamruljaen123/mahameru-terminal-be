"""
Internal helper functions for Mahameru Copilot.
Includes API handlers, route builders, and area-to-bbox mapping.
"""

import json
import logging
import re
import urllib.parse
from typing import Dict, Any, Optional

import httpx

from copilot.config import API_BASE, logger
from copilot.api_catalog import API_CATALOG, MICROSERVICE_ROUTES, MICROSERVICE_ROUTE_TEMPLATES
from copilot.tools import TOOL_DEFINITIONS

# ---------------------------------------------------------------------------
# Area → Bounding Box mapping (for /vessel command)
# ---------------------------------------------------------------------------

_AREA_BBOX_MAP: Dict[str, str] = {
    "singapore": "1.0,103.5,1.5,104.2",
    "malacca strait": "1.0,98.0,6.0,104.0",
    "south china sea": "1.0,105.0,20.0,120.0",
    "java sea": "-8.0,105.0,-3.0,118.0",
    "sunda strait": "-7.0,104.0,-5.0,106.5",
    "lombok strait": "-9.0,115.0,-8.0,117.0",
    "jakarta bay": "-6.2,106.5,-5.9,107.0",
    "surabaya": "-7.5,112.5,-7.0,113.0",
    "batam": "0.5,103.5,1.5,104.5",
    "dubai": "24.5,54.5,25.5,55.5",
    "rotterdam": "51.5,3.5,52.5,5.0",
    "shanghai": "30.5,121.0,32.0,122.5",
    "hong kong": "22.0,113.5,22.5,114.5",
    "panama canal": "8.5,-80.0,9.5,-79.0",
    "suez canal": "29.5,32.0,31.0,33.0",
    "strait of gibraltar": "35.5,-6.5,36.5,-5.0",
    "bab el-mandeb": "12.0,42.5,13.5,44.0",
    "bosphorus": "40.5,28.5,41.5,29.5",
}


def _area_to_bbox(area: str) -> str:
    """Convert a named area to a bounding box string."""
    area_lower = area.lower().strip()
    if area_lower in _AREA_BBOX_MAP:
        return _AREA_BBOX_MAP[area_lower]
    # Default to Singapore area
    return "1.0,103.5,1.5,104.2"


# ---------------------------------------------------------------------------
# Vessel Location Extractor — AI-powered: uses LLM to detect location from
# natural language, translates to English, then passes to Nominatim.
# ---------------------------------------------------------------------------

_LOCATION_EXTRACTION_PROMPT = """You are a maritime location extraction AI. Your ONLY job is to identify the port, strait, sea, or geographic area mentioned in the user's message.

Rules:
1. Extract ONLY the location name — nothing else.
2. If the location is in another language (e.g. Indonesian "pelabuhan singapore", "selat malaka"), translate it to English: "Singapore", "Malacca Strait".
3. If multiple locations are mentioned, pick the most specific one.
4. If no location is found, respond with "Singapore".
5. Respond with ONLY the location name — no explanations, no extra text, no punctuation.

Examples:
  User: "kamu tampilkan vessel yang ada di wilayah pelabuhan singapore"
  Response: Singapore

  User: "cek vessel radar selat malaka"
  Response: Malacca Strait

  User: "tampilkan kapal di sekitar dubai"
  Response: Dubai

  User: "lihat vessel di hong kong"
  Response: Hong Kong

  User: "vessel di perairan batam"
  Response: Batam

  User: "saya ingin melihat kapal di tanjung priok jakarta"
  Response: Jakarta

  User: "show me vessels in the south china sea"
  Response: South China Sea"""


async def _ai_extract_vessel_location(client: httpx.AsyncClient, text: str) -> str:
    """Use a lightweight LLM call to extract a maritime location from natural language.

    The LLM:
      1. Understands the user's command in any language (Indonesian, English, etc.)
      2. Detects the location (port, strait, sea area)
      3. Translates to English if needed
      4. Returns just the clean location name for Nominatim geocoding
    """
    from copilot.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

    if not text:
        return "Singapore"

    try:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": _LOCATION_EXTRACTION_PROMPT},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.1,
                "max_tokens": 64,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        location = data["choices"][0]["message"]["content"].strip()
        # Sanity check: must be a real location name, not a sentence
        if len(location) > 100 or not location:
            return "Singapore"
        return location
    except Exception as e:
        logger.warning(f"[AI Location] LLM extraction failed: {e}, falling back to raw text")
        # Fallback: use raw text as-is for Nominatim
        return text


async def _extract_vessel_location(client: httpx.AsyncClient, text: str) -> str:
    """Extract maritime location using AI, with non-AI fallback.

    Priority:
      1. Try AI-powered extraction (LLM understands any language)
      2. Fallback: pass raw text to Nominatim (may still work for simple cases)
      3. Ultimate fallback: "Singapore"
    """
    result = await _ai_extract_vessel_location(client, text)
    if result:
        return result
    # Final fallback
    return "Singapore"


# ---------------------------------------------------------------------------
# API Handlers
# ---------------------------------------------------------------------------

async def _discover_services_handler(client: httpx.AsyncClient, fn_args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle discover_services tool — search/filter API_CATALOG."""
    service_filter = fn_args.get("service", "").strip().lower()
    search_keyword = fn_args.get("search", "").strip().lower()

    if service_filter and service_filter in API_CATALOG:
        svc = API_CATALOG[service_filter]
        endpoints_info = {}
        for ep_key, ep_val in svc["endpoints"].items():
            params_info = ep_val.get("params", {})
            endpoints_info[ep_key] = {
                "method": ep_val["method"],
                "url": f"{svc['base']}{ep_val['path']}",
                "description": ep_val["desc"],
                "params": params_info if params_info else "No params required",
            }
        return {
            "success": True,
            "tool": "discover_services",
            "data": {
                "service": service_filter,
                "description": svc["description"],
                "base_url": svc["base"],
                "endpoints": endpoints_info,
            }
        }

    # List all services (optionally filtered by keyword)
    result = {}
    for svc_name, svc in API_CATALOG.items():
        if search_keyword and search_keyword not in svc_name and search_keyword not in svc["description"].lower():
            # Check endpoint descriptions too
            found = False
            for ep in svc["endpoints"].values():
                if search_keyword in ep["desc"].lower():
                    found = True
                    break
            if not found:
                continue
        result[svc_name] = {
            "description": svc["description"],
            "base_url": svc["base"],
            "endpoint_count": len(svc["endpoints"]),
            "endpoints": {k: {"method": v["method"], "description": v["desc"]} for k, v in svc["endpoints"].items()},
        }

    return {
        "success": True,
        "tool": "discover_services",
        "data": {
            "total_services": len(result),
            "services": result,
            "note": "Use call_api(service='<name>', endpoint='<key>', params={...}) to access any endpoint.",
        }
    }


async def _call_api_handler(client: httpx.AsyncClient, fn_args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle call_api tool — dynamically call any endpoint from API_CATALOG."""
    service_name = fn_args.get("service", "").strip().lower()
    endpoint_key = fn_args.get("endpoint", "").strip().lower()
    params = fn_args.get("params", {}) or {}

    if service_name not in API_CATALOG:
        return {"success": False, "tool": "call_api", "error": f"Service '{service_name}' not found. Use discover_services to list available services."}

    svc = API_CATALOG[service_name]
    if endpoint_key not in svc["endpoints"]:
        available = list(svc["endpoints"].keys())
        return {"success": False, "tool": "call_api", "error": f"Endpoint '{endpoint_key}' not found in '{service_name}'. Available: {', '.join(available)}"}

    ep = svc["endpoints"][endpoint_key]
    path = ep["path"]
    method = ep.get("method", "GET").upper()

    # Substitute path parameters (e.g. {symbol} → params['symbol'])
    for key in list(params.keys()):
        placeholder = "{" + key + "}"
        if placeholder in path:
            path = path.replace(placeholder, str(params[key]))
            del params[key]

    url = f"{svc['base']}{path}"

    try:
        logger.info(f"[call_api] {method} {url} params={params}")
        if method == "GET":
            resp = await client.get(url, params=params, timeout=30.0)
        elif method == "POST":
            resp = await client.post(url, json=params, timeout=30.0)
        else:
            resp = await client.request(method, url, json=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"[call_api] {service_name}/{endpoint_key} OK")
        return {"success": True, "tool": "call_api", "service": service_name, "endpoint": endpoint_key, "data": data}
    except httpx.TimeoutException:
        return {"success": False, "tool": "call_api", "error": f"Timeout calling {url}"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "tool": "call_api", "error": f"HTTP {e.response.status_code}", "detail": str(e)}
    except Exception as e:
        return {"success": False, "tool": "call_api", "error": str(e)}


def _build_route(tool_name: str, args: Dict[str, Any]) -> str:
    """Build a parameterized URL for the given tool and arguments."""
    template = MICROSERVICE_ROUTE_TEMPLATES.get(tool_name)
    if not template:
        base = MICROSERVICE_ROUTES.get(tool_name, "")
        return base

    # Prepare defaults for missing optional args
    defaults = {}
    for td in TOOL_DEFINITIONS:
        if td["function"]["name"] == tool_name:
            props = td["function"]["parameters"].get("properties", {})
            for pname, pinfo in props.items():
                if "default" in pinfo:
                    defaults[pname] = pinfo["default"]
            break

    merged = {**defaults, **args}
    
    # Alias Mapping: If template expects 'symbol' but it's missing, try aliases
    placeholders = re.findall(r'\{([a-zA-Z0-9_]+)\}', template)
    if 'symbol' in placeholders and 'symbol' not in merged:
        for alias in ['ticker', 'entity_name', 'stock']:
            if alias in merged:
                merged['symbol'] = merged[alias]
                break

    formatted_args = {}
    for k, v in merged.items():
        if isinstance(v, bool):
            formatted_args[k] = str(v).lower()
        elif v is None:
            formatted_args[k] = ""
        else:
            formatted_args[k] = str(v)

    final_args = {"base": API_BASE}
    used_keys = set()
    for p in placeholders:
        if p == "base": continue
        val = formatted_args.get(p, "")
        final_args[p] = val
        if p in formatted_args:
            used_keys.add(p)

    try:
        url = template.format(**final_args)
        
        # Append unused args as extra query params for maximum robustness
        unused_args = {k: v for k, v in formatted_args.items() if k not in used_keys and k != "base"}
        if unused_args:
            sep = "&" if "?" in url else "?"
            query_str = urllib.parse.urlencode(unused_args)
            url = f"{url}{sep}{query_str}"
            
        return url
    except Exception as e:
        logger.warning(f"Formatting failed for {tool_name}: {e}, using base route")
        return MICROSERVICE_ROUTES.get(tool_name, "")


async def _call_microservice(client: httpx.AsyncClient, url: str, tool_name: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Call an internal microservice and return parsed JSON."""
    try:
        logger.info(f"[API] Calling {tool_name}: {url}")
        request_headers = headers or {}
        resp = await client.get(url, headers=request_headers, timeout=25.0)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"[API] {tool_name} responded successfully")
        return {"success": True, "tool": tool_name, "data": data}
    except httpx.TimeoutException:
        logger.error(f"[API] Timeout calling {tool_name}")
        return {"success": False, "tool": tool_name, "error": "Microservice timeout"}
    except httpx.HTTPStatusError as e:
        logger.error(f"[API] HTTP {e.response.status_code} from {tool_name}")
        return {"success": False, "tool": tool_name, "error": f"HTTP {e.response.status_code}", "detail": str(e)}
    except Exception as e:
        logger.error(f"[API] Error calling {tool_name}: {e}")
        return {"success": False, "tool": tool_name, "error": str(e)}
