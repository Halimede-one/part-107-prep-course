"""Lexical retrieval over the knowledge-base chunks.

Standard library only, so no embedding model or third-party package is needed.
The corpus is small and section-structured, so term overlap weighted by rarity
picks the right chunk. If this proves too blunt once the real corpus lands,
that is the point to revisit semantic retrieval as a separate decision.
"""

import math
import os
import re

_TOKEN = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset("""
a an and are as at be but by can do does for from had has have how i if in into is it
its may must my no not of on or shall should so than that the their then there these
they this to under was were what when where which who why will with you your
""".split())


def _tokens(text):
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def parse_chunk(text, name):
    """Split a chunk file into its header metadata and body."""
    meta, body = {}, text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
            body = parts[2].strip()
    return {
        "id": name,
        "source": meta.get("source", name),
        "section": meta.get("section", ""),
        "url": meta.get("url", ""),
        "page": meta.get("page", ""),
        "kind": meta.get("kind", "source"),
        "derived_from": meta.get("derived_from", ""),
        "text": body,
    }


def load_chunks(directory):
    """Load every .md chunk in a directory. Missing directory yields no chunks."""
    if not os.path.isdir(directory):
        return []
    chunks = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".md") or name == "index.md":
            continue
        with open(os.path.join(directory, name), "r", encoding="utf-8") as handle:
            chunks.append(parse_chunk(handle.read(), name))
    return chunks


def search(chunks, query, top_k=3):
    """Return the top_k chunks for a query, most relevant first."""
    query_terms = set(_tokens(query))
    if not query_terms or not chunks:
        return []

    documents = [_tokens(c["section"] + " " + c["text"]) for c in chunks]
    document_count = len(documents)
    containing = {
        term: sum(1 for tokens in documents if term in tokens) for term in query_terms
    }

    scored = []
    for chunk, tokens in zip(chunks, documents):
        if not tokens:
            continue
        score = 0.0
        for term in query_terms:
            occurrences = tokens.count(term)
            if not occurrences:
                continue
            rarity = math.log(1 + document_count / (1 + containing[term]))
            score += (occurrences / len(tokens)) * rarity
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]
