"""Book-catalog lookup using source metadata; vision output is search input only."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_FIELDS = (
    "key,title,author_name,first_publish_year,isbn,cover_i,subject,publisher,"
    "description,first_sentence"
)
USER_AGENT = "BibliotecaEscolar/1.0 (https://library.autoava.us)"
REQUEST_TIMEOUT = (3, 8)
MAX_RESULTS = 6


def _clean_text(value: object, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    value = html.unescape(re.sub(r"<[^>]*>", " ", value))
    return " ".join(value.split())[:limit].strip()


def _valid_isbn(digits: str) -> bool:
    if len(digits) == 13 and digits.isdigit():
        total = sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(digits[:12]))
        return (10 - total % 10) % 10 == int(digits[-1])
    if len(digits) == 10 and re.fullmatch(r"\d{9}[\dX]", digits):
        total = sum(int(char) * (10 - index) for index, char in enumerate(digits[:9]))
        check = 10 if digits[-1] == "X" else int(digits[-1])
        return (total + check) % 11 == 0
    return False


def normalize_isbn(value: object) -> str:
    if not isinstance(value, str):
        return ""
    digits = re.sub(r"[^0-9Xx]", "", value).upper()
    return digits if _valid_isbn(digits) else ""


def _decode_json_object(text: object) -> dict:
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        raise ValueError("A resposta visual não contém JSON.")
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("A resposta visual não contém um objeto JSON.")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("A resposta visual não contém um objeto JSON.")
    return value


def parse_visual_identity(text: object) -> dict[str, str]:
    """Whitelist only title, author and ISBN transcribed from the image."""
    value = _decode_json_object(text)
    title = _clean_text(value.get("titulo", value.get("title")), 200)
    author = _clean_text(value.get("autor", value.get("author")), 160)
    isbn = normalize_isbn(value.get("isbn"))
    return {"titulo": title, "autor": author, "isbn": isbn}


def _first_year(value: object) -> int | None:
    match = re.match(r"^\s*(\d{4})", str(value or ""))
    if not match:
        return None
    year = int(match.group(1))
    return year if 1000 <= year <= 2100 else None


def _normalize_name(value: object) -> str:
    text = _clean_text(value, 400).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _similarity(left: object, right: object) -> float:
    a, b = _normalize_name(left), _normalize_name(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _genre(values: object) -> str:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return ""
    text = " ".join(_clean_text(value, 120).casefold() for value in values)
    normalized = _normalize_name(text)
    if any(term in normalized for term in ("juvenile", "young adult", "children", "adolescent")):
        return "Juvenil"
    if any(term in normalized for term in ("mystery", "detective", "thriller", "crime")):
        return "Mistério"
    if "fantasy" in normalized:
        return "Fantasia"
    if "classic" in normalized or "classics" in normalized:
        return "Clássico"
    if "romance" in normalized or "romantic" in normalized:
        return "Romance"
    if "adventure" in normalized:
        return "Aventura"
    if "drama" in normalized:
        return "Drama"
    if any(term in normalized for term in ("fiction", "novel", "literature")):
        return "Ficção"
    return ""


def _safe_url(value: object, allowed_hosts: set[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return ""
    host = (parts.hostname or "").casefold()
    if parts.scheme not in ("http", "https") or host not in allowed_hosts:
        return ""
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True) if key != "edge"]
    return urlunsplit(("https", host, parts.path, urlencode(query), ""))


def _best_isbn(values: object) -> str:
    if not isinstance(values, (list, tuple)):
        return ""
    candidates = [normalize_isbn(value) for value in values if isinstance(value, str)]
    candidates = [value for value in candidates if value]
    return next((value for value in candidates if len(value) == 13), candidates[0] if candidates else "")


def google_candidate(item: object) -> dict:
    if not isinstance(item, dict):
        item = {}
    info = item.get("volumeInfo")
    if not isinstance(info, dict):
        info = {}
    identifiers = info.get("industryIdentifiers") or []
    if not isinstance(identifiers, list):
        identifiers = []
    identifiers = sorted(
        (entry for entry in identifiers if isinstance(entry, dict)),
        key=lambda entry: 0 if entry.get("type") == "ISBN_13" else 1,
    )
    isbn = _best_isbn([entry.get("identifier", "") for entry in identifiers])
    images = info.get("imageLinks") or {}
    if not isinstance(images, dict):
        images = {}
    cover = _safe_url(
        next((images.get(size) for size in ("extraLarge", "large", "medium", "thumbnail", "smallThumbnail") if images.get(size)), ""),
        {"books.google.com"},
    )
    volume_id = item.get("id")
    volume_id = volume_id if isinstance(volume_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", volume_id) else ""
    source_url = _safe_url(info.get("canonicalVolumeLink"), {"books.google.com"})
    if not source_url and volume_id:
        source_url = f"https://books.google.com/books?id={volume_id}"
    authors = info.get("authors") or []
    if not isinstance(authors, list):
        authors = []
    return {
        "titulo": _clean_text(info.get("title"), 200),
        "autor": ", ".join(filter(None, (_clean_text(author, 120) for author in authors)))[:300],
        "ano": _first_year(info.get("publishedDate")),
        "isbn": isbn,
        "genero": _genre(info.get("categories")),
        "sinopse": _clean_text(info.get("description"), 4000),
        "capa_url": cover,
        "fontes": ([{"nome": "Google Books", "url": source_url}] if source_url else []),
    }


def openlibrary_candidate(doc: object, work: object = None, requested_isbn: str = "") -> dict:
    if not isinstance(doc, dict):
        doc = {}
    if not isinstance(work, dict):
        work = {}
    key = doc.get("key")
    safe_key = key if isinstance(key, str) and re.fullmatch(r"/works/OL\d+W", key) else ""
    source_url = f"https://openlibrary.org{safe_key}" if safe_key else ""
    cover_id = doc.get("cover_i")
    cover = ""
    if isinstance(cover_id, int) and cover_id > 0:
        cover = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false"
    authors = doc.get("author_name") or []
    if not isinstance(authors, list):
        authors = []
    description = work.get("description") or doc.get("description")
    if isinstance(description, dict):
        description = description.get("value")
    raw_isbns = doc.get("isbn") or []
    if isinstance(raw_isbns, str):
        raw_isbns = [raw_isbns]
    doc_isbns = [normalize_isbn(value) for value in raw_isbns if isinstance(value, str)]
    requested_isbn = normalize_isbn(requested_isbn)
    isbn = requested_isbn if requested_isbn and requested_isbn in doc_isbns else ""
    subjects = doc.get("subject") or work.get("subjects") or []
    return {
        "titulo": _clean_text(doc.get("title"), 200),
        "autor": ", ".join(filter(None, (_clean_text(author, 120) for author in authors)))[:300],
        "ano": _first_year(doc.get("first_publish_year")),
        "isbn": isbn,
        "genero": _genre(subjects),
        "sinopse": _clean_text(description, 4000),
        "capa_url": cover,
        "fontes": ([{"nome": "Open Library", "url": source_url}] if source_url else []),
    }


def score_candidate(candidate: dict, visual: dict[str, str]) -> dict:
    title_score = _similarity(candidate.get("titulo"), visual.get("titulo"))
    author_score = _similarity(candidate.get("autor"), visual.get("autor"))
    visual_isbn = normalize_isbn(visual.get("isbn"))
    candidate_isbn = normalize_isbn(candidate.get("isbn"))
    isbn_confirmed = bool(visual_isbn and candidate_isbn == visual_isbn)
    if isbn_confirmed:
        score = 100
    elif visual.get("autor"):
        score = round(70 * title_score + 30 * author_score)
    else:
        score = round(100 * title_score)
    if visual_isbn and not isbn_confirmed:
        score = min(score, 49)
    confirmed = isbn_confirmed or (
        not visual_isbn
        and title_score >= 0.92
        and (not visual.get("autor") or author_score >= 0.82)
    )
    confidence = "alta" if score >= 90 else "média" if score >= 70 else "baixa"
    return {
        "score": score,
        "confianca": confidence,
        "isbn_confirmado": isbn_confirmed,
        "confirmado": confirmed,
    }


def _fetch_json(url: str, params: dict) -> tuple[dict | None, str]:
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None, "indisponivel"
    if response.status_code == 429:
        return None, "quota"
    if response.status_code == 403:
        return None, "bloqueado"
    if response.status_code != 200:
        return None, "indisponivel"
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        return None, "resposta_invalida"
    return (payload, "ok") if isinstance(payload, dict) else (None, "resposta_invalida")


def _google_query(visual: dict[str, str]) -> str:
    if visual.get("isbn"):
        return f"isbn:{visual['isbn']}"
    terms = []
    title = re.sub(r'["\r\n]+', " ", visual.get("titulo", "")).strip()
    author = re.sub(r'["\r\n]+', " ", visual.get("autor", "")).strip()
    if title:
        terms.append(f'intitle:"{title}"')
    if author:
        terms.append(f'inauthor:"{author}"')
    return " ".join(terms)


def _merge_candidates(candidates: list[dict]) -> list[dict]:
    merged: dict[tuple, dict] = {}
    for candidate in candidates:
        if not candidate.get("titulo"):
            continue
        isbn = candidate.get("isbn") or ""
        if isbn:
            key = ("isbn", isbn)
        else:
            key = (
                "text",
                _normalize_name(candidate.get("titulo")),
                _normalize_name(candidate.get("autor")),
                candidate.get("ano"),
            )
        current = merged.get(key)
        if current is None:
            merged[key] = dict(candidate)
            continue
        for field in ("autor", "ano", "isbn", "genero", "sinopse", "capa_url"):
            if not current.get(field) and candidate.get(field):
                current[field] = candidate[field]
        seen = {source.get("url") for source in current.get("fontes", [])}
        current.setdefault("fontes", []).extend(
            source for source in candidate.get("fontes", []) if source.get("url") not in seen
        )
    return list(merged.values())


def search_catalogs(visual: dict[str, str]) -> tuple[list[dict], dict[str, str]]:
    """Search public catalogs; return only metadata present in their records."""
    visual = {
        "titulo": _clean_text(visual.get("titulo"), 200),
        "autor": _clean_text(visual.get("autor"), 160),
        "isbn": normalize_isbn(visual.get("isbn")),
    }
    providers = {"google_books": "nao_consultado", "open_library": "nao_consultado"}
    if not visual["titulo"] and not visual["isbn"]:
        return [], providers

    candidates: list[dict] = []
    google_query = _google_query(visual)
    google_data, google_status = _fetch_json(
        GOOGLE_BOOKS_URL,
        {"q": google_query, "maxResults": MAX_RESULTS, "printType": "books"},
    )
    google_items = google_data.get("items", []) if google_data else []
    providers["google_books"] = google_status if google_status != "ok" else ("ok" if google_items else "sem_resultados")
    if isinstance(google_items, list):
        candidates.extend(google_candidate(item) for item in google_items[:MAX_RESULTS])

    params = {"limit": MAX_RESULTS, "fields": OPEN_LIBRARY_FIELDS}
    if visual["isbn"]:
        params["q"] = f"isbn:{visual['isbn']}"
    else:
        params["title"] = visual["titulo"]
        if visual["autor"]:
            params["author"] = visual["autor"]
    library_data, library_status = _fetch_json(OPEN_LIBRARY_URL, params)
    library_docs = library_data.get("docs", []) if library_data else []
    providers["open_library"] = library_status if library_status != "ok" else ("ok" if library_docs else "sem_resultados")
    if isinstance(library_docs, list):
        candidates.extend(openlibrary_candidate(doc, requested_isbn=visual["isbn"]) for doc in library_docs[:MAX_RESULTS])

    results = []
    for candidate in _merge_candidates(candidates):
        match = score_candidate(candidate, visual)
        if match["score"] < 45:
            continue
        results.append({**candidate, **match})
    results.sort(
        key=lambda item: (
            item["score"],
            item["confirmado"],
            bool(item.get("sinopse")),
            bool(item.get("isbn")),
        ),
        reverse=True,
    )
    return results[:MAX_RESULTS], providers
