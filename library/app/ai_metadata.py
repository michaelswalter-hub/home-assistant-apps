from __future__ import annotations

import json
import re
from typing import Any

import requests

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
TIMEOUT = 75


def _extract_output_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in response.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def _extract_citation_urls(response: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for item in response.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            for annotation in content.get("annotations") or []:
                url = None
                if annotation.get("type") == "url_citation":
                    url = annotation.get("url")
                    if not url and isinstance(annotation.get("url_citation"), dict):
                        url = annotation["url_citation"].get("url")
                if url and url not in urls:
                    urls.append(url)
    return urls


def _parse_json_text(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}


def search_book_with_ai(
    api_key: str,
    title: str | None,
    author: str | None,
    isbn: str | None = None,
    model: str = "gpt-5.4-mini",
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("Kein OpenAI API-Key konfiguriert.")

    prompt = f"""
Recherchiere im Web nach genau diesem Buch und identifiziere die wahrscheinlich passende Ausgabe.

Vorhandene Angaben:
Titel: {title or "unbekannt"}
Autor: {author or "unbekannt"}
ISBN: {isbn or "nicht vorhanden"}

Regeln:
- Erfinde niemals ISBN, Verlag, Erscheinungsdatum oder andere bibliografische Daten.
- Übernimm solche Fakten nur, wenn du sie in einer Webquelle gefunden hast.
- Bevorzuge deutschsprachige Ausgaben, wenn Titel/Autor darauf hindeuten.
- Wenn mehrere Ausgaben existieren, wähle die Ausgabe, die den vorhandenen Angaben am besten entspricht.
- Suche besonders nach einer aussagekräftigen deutschsprachigen Zusammenfassung.
- Wenn keine verlässliche vorhandene Zusammenfassung auffindbar ist, darfst du eine kurze sachliche Zusammenfassung aus verlässlichen Webquellen formulieren und kennzeichne summary_generated dann als true.
- Gib ausschließlich ein JSON-Objekt zurück, ohne Markdown.

JSON-Schema:
{{
  "title": "Titel oder null",
  "subtitle": "Untertitel oder null",
  "author": "Autor oder null",
  "isbn": "ISBN-10/13 oder null",
  "publisher": "Verlag oder null",
  "published_date": "Datum/Jahr oder null",
  "language": "Sprachcode oder null",
  "description": "Zusammenfassung oder null",
  "cover_url": "direkte Cover-URL oder null",
  "summary_generated": false,
  "confidence": "high|medium|low",
  "notes": "kurze Begründung zur Ausgabe oder null",
  "sources": ["https://..."]
}}
""".strip()

    payload = {
        "model": model,
        "reasoning": {"effort": "low"},
        "tools": [{"type": "web_search", "search_context_size": "medium"}],
        "input": prompt,
    }

    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )

    if response.status_code >= 400:
        try:
            detail = (response.json().get("error") or {}).get("message")
        except Exception:
            detail = None
        raise RuntimeError(detail or f"OpenAI API Fehler {response.status_code}")

    raw = response.json()
    text = _extract_output_text(raw)
    result = _parse_json_text(text)
    if not result:
        raise RuntimeError("Die KI-Antwort konnte nicht als Metadaten gelesen werden.")

    citations = _extract_citation_urls(raw)
    sources = result.get("sources")
    if not isinstance(sources, list):
        sources = []
    clean_sources = []
    for url in [*sources, *citations]:
        if isinstance(url, str) and url.startswith(("https://", "http://")) and url not in clean_sources:
            clean_sources.append(url)

    result["sources"] = clean_sources[:10]
    result["metadata_source"] = "KI-Websuche"
    result["description_source"] = (
        "KI aus Webquellen"
        if result.get("summary_generated")
        else "Webrecherche"
    )
    return result
