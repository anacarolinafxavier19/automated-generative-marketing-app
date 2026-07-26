"""Token-based sliding-window chunking for retrieval."""

import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    text = text.strip()
    if not text:
        return []

    tokens = _ENCODING.encode(text)
    if len(tokens) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap
    while start < len(tokens):
        window = tokens[start : start + chunk_size]
        chunks.append(_ENCODING.decode(window))
        if start + chunk_size >= len(tokens):
            break
        start += step
    return chunks
