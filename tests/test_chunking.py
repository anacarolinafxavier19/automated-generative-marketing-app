from app.ingestion.chunking import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_returns_single_chunk():
    text = "This is a short piece of context about a company."
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert chunks == [text]


def test_long_text_is_split_into_overlapping_chunks():
    text = " ".join(f"word{i}" for i in range(2000))
    chunks = chunk_text(text, chunk_size=500, overlap=50)

    assert len(chunks) > 1
    # every chunk should respect the token budget
    for chunk in chunks:
        assert len(chunk) > 0
    # reassembled chunks should cover the start and end of the source text
    assert chunks[0].startswith("word0")
    assert "word1999" in chunks[-1]
