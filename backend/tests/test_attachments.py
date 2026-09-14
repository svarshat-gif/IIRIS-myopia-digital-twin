"""Uploads: type sniffing, size limits, ownership."""
from __future__ import annotations

import struct
import zlib

from tests.conftest import API
from tests.test_auth import PW, auth, register


def png_bytes(w: int = 8, h: int = 8) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes([200, 180, 150]) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def test_upload_and_list(client):
    tok = register(client, "up1@example.com")["access_token"]
    h = auth(tok)
    r = client.post(f"{API}/me/attachments", headers=h,
                    files={"file": ("rx.png", png_bytes(), "image/png")},
                    data={"kind": "prescription", "note": "Sept prescription"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["content_type"] == "image/png"
    assert body["is_image"] is True
    assert body["note"] == "Sept prescription"

    listed = client.get(f"{API}/me/attachments", headers=h).json()
    assert listed["count"] == 1


def test_file_type_comes_from_the_bytes_not_the_claim(client):
    """An HTML file renamed .png and declared image/png must be refused."""
    tok = register(client, "up2@example.com")["access_token"]
    h = auth(tok)
    r = client.post(f"{API}/me/attachments", headers=h, files={
        "file": ("innocent.png", b"<html><script>alert(1)</script></html>", "image/png")})
    assert r.status_code == 422
    assert "supported file" in r.json()["detail"]


def test_empty_file_rejected(client):
    tok = register(client, "up3@example.com")["access_token"]
    r = client.post(f"{API}/me/attachments", headers=auth(tok),
                    files={"file": ("empty.png", b"", "image/png")})
    assert r.status_code == 422


def test_oversized_file_rejected(client):
    tok = register(client, "up4@example.com")["access_token"]
    big = png_bytes() + b"\x00" * (10 * 1024 * 1024 + 10)
    r = client.post(f"{API}/me/attachments", headers=auth(tok),
                    files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413
    assert "limit" in r.json()["detail"]


def test_pdf_is_accepted(client):
    tok = register(client, "up5@example.com")["access_token"]
    r = client.post(f"{API}/me/attachments", headers=auth(tok),
                    files={"file": ("report.pdf", b"%PDF-1.7\n%stuff\n", "application/pdf")})
    assert r.status_code == 201
    assert r.json()["content_type"] == "application/pdf"
    assert r.json()["is_image"] is False


def test_files_are_private_to_their_owner(client):
    a = register(client, "owner@example.com")["access_token"]
    b = register(client, "stranger@example.com")["access_token"]
    ha, hb = auth(a), auth(b)

    created = client.post(f"{API}/me/attachments", headers=ha,
                          files={"file": ("rx.png", png_bytes(), "image/png")}).json()
    aid = created["attachment_id"]

    assert client.get(f"{API}/me/attachments/{aid}/file", headers=ha).status_code == 200
    assert client.get(f"{API}/me/attachments/{aid}/file", headers=hb).status_code == 404
    assert client.get(f"{API}/me/attachments/{aid}/file").status_code == 401
    assert client.get(f"{API}/me/attachments", headers=hb).json()["count"] == 0
    assert client.delete(f"{API}/me/attachments/{aid}", headers=hb).status_code == 404
    assert client.delete(f"{API}/me/attachments/{aid}", headers=ha).status_code == 204


def test_download_sets_hardening_headers(client):
    tok = register(client, "hdr@example.com")["access_token"]
    h = auth(tok)
    aid = client.post(f"{API}/me/attachments", headers=h,
                      files={"file": ("rx.png", png_bytes(), "image/png")}
                      ).json()["attachment_id"]
    r = client.get(f"{API}/me/attachments/{aid}/file", headers=h)
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]


def test_attaching_to_someone_elses_result_fails(client):
    from datetime import date
    a = register(client, "own2@example.com")["access_token"]
    b = register(client, "other2@example.com")["access_token"]
    ha, hb = auth(a), auth(b)
    obs = client.post(f"{API}/me/records", headers=ha, json={
        "visit_date": date.today().isoformat(),
        "spherical_equivalent": -2.0, "axial_length": 24.0}).json()["observation_id"]

    ok = client.post(f"{API}/me/attachments", headers=ha,
                     files={"file": ("rx.png", png_bytes(), "image/png")},
                     data={"observation_id": obs})
    assert ok.status_code == 201
    assert ok.json()["observation_id"] == obs

    bad = client.post(f"{API}/me/attachments", headers=hb,
                      files={"file": ("rx.png", png_bytes(), "image/png")},
                      data={"observation_id": obs})
    assert bad.status_code == 404


def test_simulator_bounds_match_published_ranges(client):
    """A value the published /simulator/inputs contract allows must be accepted,
    and one it forbids must be refused -- so the form and the API cannot disagree."""
    spec = client.get(f"{API}/simulator/inputs").json()
    ranges = {f["name"]: f for group in ("clinical", "behaviour", "ergonomics")
              for f in spec[group]}

    for name, f in ranges.items():
        if name == "parental_myopia":
            continue
        payload = {"age": 10, "spherical_equivalent": -1.5, "years": 1,
                   name: f["max"]}
        assert client.post(f"{API}/simulator/project",
                           json=payload).status_code == 200, name
        payload[name] = f["max"] + 1000
        assert client.post(f"{API}/simulator/project",
                           json=payload).status_code == 422, name


def test_axial_length_error_names_the_field(client):
    r = client.post(f"{API}/simulator/project", json={
        "age": 10, "spherical_equivalent": -1.5, "axial_length": -0.01})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any("axial_length" in str(d.get("loc", "")) for d in detail)
