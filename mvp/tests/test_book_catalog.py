from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER_DIR))

import book_catalog


ISBN = "9780141439518"


class BookCatalogTests(unittest.TestCase):
    def test_visual_parser_keeps_only_visible_identifiers(self):
        parsed = book_catalog.parse_visual_identity(
            '```json\n'
            '{"titulo":"Orgulho e Preconceito","autor":"Jane Austen",'
            '"isbn":"978-0-14-143951-8","ano":1813,"sinopse":"texto inventado"}'
            '\n```'
        )
        self.assertEqual(parsed, {
            "titulo": "Orgulho e Preconceito",
            "autor": "Jane Austen",
            "isbn": ISBN,
        })

    def test_google_candidate_uses_catalog_fields_not_generated_metadata(self):
        candidate = book_catalog.google_candidate({
            "id": "volume-1",
            "volumeInfo": {
                "title": "Pride and Prejudice",
                "authors": ["Jane Austen"],
                "publishedDate": "2024-06-11",
                "industryIdentifiers": [{"type": "ISBN_13", "identifier": ISBN}],
                "description": "<p>A publisher-supplied description.</p>",
                "categories": ["Fiction / Classics"],
                "imageLinks": {"thumbnail": "http://books.google.com/books/content?id=1&edge=curl"},
                "canonicalVolumeLink": "https://books.google.com/books?id=volume-1",
            },
        })
        self.assertEqual(candidate["titulo"], "Pride and Prejudice")
        self.assertEqual(candidate["autor"], "Jane Austen")
        self.assertEqual(candidate["ano"], 2024)
        self.assertEqual(candidate["isbn"], ISBN)
        self.assertEqual(candidate["sinopse"], "A publisher-supplied description.")
        self.assertEqual(candidate["genero"], "Clássico")
        self.assertEqual(candidate["capa_url"], "https://books.google.com/books/content?id=1")
        self.assertEqual(candidate["fontes"], [{
            "nome": "Google Books",
            "url": "https://books.google.com/books?id=volume-1",
        }])

    def test_google_candidate_prefers_highest_available_cover_size(self):
        candidate = book_catalog.google_candidate({
            "id": "volume-2",
            "volumeInfo": {
                "title": "Romeo and Juliet",
                "imageLinks": {
                    "thumbnail": "https://books.google.com/books/content?id=2&zoom=1",
                    "large": "https://books.google.com/books/content?id=2&zoom=5",
                    "extraLarge": "http://books.google.com/books/content?id=2&zoom=0&edge=curl",
                },
            },
        })
        self.assertEqual(
            candidate["capa_url"],
            "https://books.google.com/books/content?id=2&zoom=0",
        )

    def test_openlibrary_candidate_reads_description_from_work_record(self):
        candidate = book_catalog.openlibrary_candidate(
            {
                "key": "/works/OL1003040W",
                "title": "Dom Casmurro",
                "author_name": ["Machado de Assis"],
                "first_publish_year": 1899,
                "isbn": [ISBN],
                "cover_i": 647501,
                "subject": ["Brazilian fiction", "Classic literature"],
            },
            {"description": {"type": "/type/text", "value": "Descrição registrada na obra."}},
            requested_isbn=ISBN,
        )
        self.assertEqual(candidate["titulo"], "Dom Casmurro")
        self.assertEqual(candidate["ano"], 1899)
        self.assertEqual(candidate["sinopse"], "Descrição registrada na obra.")
        self.assertEqual(candidate["genero"], "Clássico")
        self.assertEqual(candidate["capa_url"], "https://covers.openlibrary.org/b/id/647501-L.jpg?default=false")
        self.assertEqual(candidate["fontes"][0]["url"], "https://openlibrary.org/works/OL1003040W")

    def test_ocr_isbn_mismatch_never_auto_confirms_another_edition(self):
        candidate = {
            "titulo": "Dom Casmurro",
            "autor": "Machado de Assis",
            "isbn": "9780000000002",
        }
        match = book_catalog.score_candidate(candidate, {
            "titulo": "Dom Casmurro",
            "autor": "Machado de Assis",
            "isbn": ISBN,
        })
        self.assertFalse(match["isbn_confirmado"])
        self.assertFalse(match["confirmado"])

    def test_openlibrary_fallback_survives_google_books_quota(self):
        calls = []

        class FakeResponse:
            def __init__(self, status_code, data):
                self.status_code = status_code
                self._data = data

            def json(self):
                return self._data

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"HTTP {self.status_code}")

        def fake_get(url, **kwargs):
            calls.append(url)
            if "googleapis.com" in url:
                return FakeResponse(429, {})
            if url.endswith("/search.json"):
                return FakeResponse(200, {"docs": [{
                    "key": "/works/OL1003040W",
                    "title": "Dom Casmurro",
                    "author_name": ["Machado de Assis"],
                    "first_publish_year": 1899,
                    "isbn": [ISBN],
                    "cover_i": 647501,
                    "subject": ["Classic literature"],
                    "description": "Sinopse publicada no catálogo.",
                }]})
            return FakeResponse(200, {})

        with patch.object(book_catalog.requests, "get", side_effect=fake_get):
            matches, providers = book_catalog.search_catalogs({
                "titulo": "Dom Casmurro",
                "autor": "Machado de Assis",
                "isbn": "",
            })

        self.assertEqual(providers["google_books"], "quota")
        self.assertEqual(providers["open_library"], "ok")
        self.assertEqual(matches[0]["titulo"], "Dom Casmurro")
        self.assertEqual(matches[0]["sinopse"], "Sinopse publicada no catálogo.")
        self.assertEqual(matches[0]["isbn"], "")  # não escolhe ISBN aleatório de outra edição da obra
        self.assertTrue(matches[0]["confirmado"])
        self.assertTrue(any("openlibrary.org" in url for url in calls))


if __name__ == "__main__":
    unittest.main()
