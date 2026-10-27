"""Busqueda lexica local (BM25) con normalizacion de tildes. Sin modelos ni servicios externos."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

_STOP = set(
    "a al algo ante con como cual cuando de del desde donde el ella en entre era es esa ese eso esta este esto ha hay "
    "la las le lo los mas me mi muy no nos o para pero por que se si sin sobre son su sus tambien te tiene tu un una "
    "uno y ya p101 p-101 bomba".split()
)


# Terminos en ingles que el modelo a veces usa al buscar -> su equivalente en los documentos (sin tildes).
_EN_ES = {
    "vibration": "vibracion", "vibrations": "vibracion", "temperature": "temperatura", "temp": "temperatura", "bearing": "rodamiento",
    "bearings": "rodamiento", "lubrication": "lubricacion", "grease": "grasa", "alignment": "alineamiento", "misalignment": "alineamiento",
    "flow": "caudal", "pressure": "presion", "discharge": "descarga", "suction": "succion", "strainer": "filtro", "filter": "filtro",
    "clogging": "obstruido", "clogged": "obstruido", "current": "corriente", "overheating": "temperatura", "cavitation": "cavitacion",
    "pump": "bomba", "motor": "motor", "cooling": "enfriamiento", "fan": "ventilador", "seal": "sello", "leak": "fuga",
    "lockout": "bloqueo", "maintenance": "mantenimiento", "procedure": "procedimiento", "manual": "manual", "alarm": "alarma",
    "inspection": "inspeccion", "checklist": "checklist", "manufacturer": "fabricante", "low": "bajo", "high": "alta",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[a-z0-9][a-z0-9\-]*", normalize(text)):
        token = _EN_ES.get(token, token)
        if token in _STOP or len(token) < 2:
            continue
        # raiz muy simple: plurales y terminaciones frecuentes, para que "rodamientos" encuentre "rodamiento"
        for suffix in ("es", "s"):
            if len(token) > 5 and token.endswith(suffix):
                token = token[: -len(suffix)]
                break
        tokens.append(token)
    return tokens


class Bm25Index:
    def __init__(self, texts: list[str], k1: float = 1.4, b: float = 0.7) -> None:
        self._docs = [Counter(tokenize(t)) for t in texts]
        self._lengths = [sum(d.values()) or 1 for d in self._docs]
        self._avg = (sum(self._lengths) / len(self._lengths)) if self._docs else 1.0
        self._k1, self._b = k1, b
        df: Counter = Counter()
        for doc in self._docs:
            df.update(doc.keys())
        n = len(self._docs)
        self._idf = {term: math.log(1 + (n - count + 0.5) / (count + 0.5)) for term, count in df.items()}

    def search(self, query: str, limit: int) -> list[tuple[int, float]]:
        terms = tokenize(query)
        scored = []
        for i, doc in enumerate(self._docs):
            score = 0.0
            for term in terms:
                tf = doc.get(term, 0)
                if tf:
                    norm = tf + self._k1 * (1 - self._b + self._b * self._lengths[i] / self._avg)
                    score += self._idf.get(term, 0.0) * tf * (self._k1 + 1) / norm
            if score > 0:
                scored.append((i, round(score, 3)))
        scored.sort(key=lambda item: -item[1])
        return scored[:limit]
