"""API tests with FastAPI's TestClient: auth, roles, upload rules, limits and error mapping."""
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import config
from app.api import auth, main
from app.api.rate_limit import limiter
from app.ingest import upload_ingestor

KEYS = {"customer": "test-customer-key", "employee": "test-employee-key", "admin": "test-admin-key"}


@pytest.fixture
def client(monkeypatch, fake_llm):
    """App with known test keys, a fake LLM key and a clean rate limiter."""
    monkeypatch.setattr(config.settings, "api_keys", SecretStr(",".join(f"{k}:{r}" for r, k in KEYS.items())))
    monkeypatch.setattr(config.settings, f"{config.LLM_PROVIDER}_api_key", SecretStr("test-llm-key"))
    auth.api_keys.cache_clear()
    limiter.reset()
    with TestClient(main.app) as test_client:
        yield test_client
    auth.api_keys.cache_clear()


def headers(role: str) -> dict:
    return {"X-API-Key": KEYS[role]}


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ready_requires_key_and_reports_chunks(client):
    assert client.get("/ready").status_code == 401
    body = client.get("/ready", headers=headers("customer")).json()
    assert body["ready"] and body["chunks"] > 0


def test_missing_or_wrong_key_is_401(client):
    assert client.post("/ask", json={"question": "hi"}).status_code == 401
    assert client.post("/ask", json={"question": "hi"}, headers={"X-API-Key": "nope"}).status_code == 401


def test_role_comes_from_key_not_body(client, questions):
    q = questions["Q41"]["question"]  # internal-only migration notes
    resp = client.post("/ask", json={"question": q, "role": "admin"}, headers=headers("customer"))
    assert resp.status_code == 200 and resp.json()["status"] == "refused"


def test_ask_response_matches_contract(client, fake_llm, questions):
    def reply(prompt: str) -> str:
        chunk_id, _ = fake_llm.chunks_in(prompt)[0]
        return json.dumps({"status": "answered", "answer": f"Five [{chunk_id}].", "conflicts": []})
    fake_llm.reply = reply
    body = client.post("/ask", json={"question": questions["Q01"]["question"]}, headers=headers("customer")).json()
    assert set(body) == {"status", "answer", "citations", "confidence", "conflicts",
                         "clarifying_question", "latency_ms"}
    assert set(body["citations"][0]) == {"chunk_id", "doc_id", "title", "section", "page", "excerpt"}


def test_request_id_is_echoed_or_generated(client):
    assert client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"
    assert len(client.get("/health").headers["X-Request-ID"]) == 32


def test_documents_are_filtered_by_role(client):
    customer = {d["doc_id"] for d in client.get("/documents", headers=headers("customer")).json()}
    admin = {d["doc_id"] for d in client.get("/documents", headers=headers("admin")).json()}
    assert not customer & {"D11", "D12", "D14", "D16"} and {"D12", "D16"} <= admin


def test_question_length_is_validated(client):
    too_long = "x" * (config.QUESTION_MAX_CHARS + 1)
    assert client.post("/ask", json={"question": too_long}, headers=headers("customer")).status_code == 422
    assert client.post("/ask", json={"question": ""}, headers=headers("customer")).status_code == 422


def test_rate_limit_per_key(client, monkeypatch):
    monkeypatch.setattr(limiter, "limit", 2)
    codes = [client.get("/documents", headers=headers("customer")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert client.get("/documents", headers=headers("admin")).status_code == 200  # other keys unaffected


def test_oversized_body_is_rejected(client):
    resp = client.post("/ask", content=b"{}", headers={**headers("customer"), "Content-Type": "application/json",
                                                       "Content-Length": str(config.REQUEST_MAX_BYTES + 1)})
    assert resp.status_code == 413


def test_llm_outage_maps_to_503(client, fake_llm, questions):
    def down(prompt: str) -> str:
        raise main.LLMError("provider down")
    fake_llm.reply = down
    resp = client.post("/ask", json={"question": questions["Q01"]["question"]}, headers=headers("customer"))
    assert resp.status_code == 503


# --- upload -----------------------------------------------------------------------------

@pytest.fixture
def isolated_uploads(monkeypatch, tmp_path):
    """Send uploads to a temp dir and record (instead of performing) index writes."""
    added = []
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "UPLOADS_METADATA_PATH", tmp_path / "uploads" / "metadata.json")
    monkeypatch.setattr(config, "CHUNKS_PATH", tmp_path / "chunks.jsonl")
    monkeypatch.setattr(upload_ingestor.index, "add_chunks", lambda chunks: added.extend(chunks))
    monkeypatch.setattr(upload_ingestor.search, "reset_caches", lambda: None)
    monkeypatch.setattr(upload_ingestor.input_guard, "reset_caches", lambda: None)
    return added


def _upload(client, role, name, content, level="public"):
    return client.post("/upload", headers=headers(role), data={"access_level": level},
                       files={"file": (name, content, "application/octet-stream")})


def test_upload_indexes_new_document(client, isolated_uploads):
    resp = _upload(client, "employee", "vpn guide.md", b"# VPN\n\n## Setup\n\nInstall the client.\n", "internal")
    assert resp.status_code == 201
    body = resp.json()
    assert body["doc_id"] == "U001" and body["chunks"] == 1 and body["access_level"] == "internal"
    assert isolated_uploads[0]["section"] == "Setup" and isolated_uploads[0]["source_file"].startswith("data/uploads/")
    assert _upload(client, "employee", "copy.md", b"# VPN\n\n## Setup\n\nInstall the client.\n").status_code == 422


def test_upload_redacts_pii(client, isolated_uploads):
    _upload(client, "admin", "contacts.txt", b"Call +1-555-0100 or mail a.b@corp.example today.")
    assert "555" not in isolated_uploads[0]["text"] and "@" not in isolated_uploads[0]["text"]


@pytest.mark.parametrize("role,name,level,code", [
    ("customer", "a.md", "public", 403),  # customers cannot upload
    ("employee", "a.md", "admin", 403),  # cannot upload above own level
    ("employee", "a.exe", "public", 422),  # unsupported type
    ("employee", "a.md", "secret", 403),  # unknown access level ranks above every role
])
def test_upload_rules(client, isolated_uploads, role, name, level, code):
    assert _upload(client, role, name, b"## A\n\ntext", level).status_code == code


def test_upload_size_limit(client, isolated_uploads, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_MAX_BYTES", 10)
    assert _upload(client, "admin", "big.txt", b"x" * 11).status_code == 413


# --- evaluate ---------------------------------------------------------------------------

def test_evaluate_is_admin_only(client, monkeypatch):
    import eval.run_eval as run_eval
    monkeypatch.setattr(run_eval, "run_evaluation", lambda fast, judge: {"mode": "fast", "rows": [1], "retrieval": {}})
    assert client.post("/evaluate", json={}, headers=headers("employee")).status_code == 403
    body = client.post("/evaluate", json={"fast": True}, headers=headers("admin")).json()
    assert body == {"mode": "fast", "retrieval": {}}
