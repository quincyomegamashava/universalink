from app.core.security import generate_api_key, hash_password, verify_password
from app.services.rag import chunk_text, sanitize_text


def test_password_roundtrip():
    h = hash_password("SecurePass123!")
    assert verify_password("SecurePass123!", h)
    assert not verify_password("wrong", h)


def test_api_key_format():
    key = generate_api_key()
    assert key.startswith("sk-ai-")
    assert len(key) > 40


def test_chunk_text_overlap():
    text = "a" * 1000
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert len(chunks) >= 3
    assert all(len(c) <= 300 for c in chunks)


def test_sanitize_null_bytes():
    assert "\x00" not in sanitize_text("hello\x00world")
