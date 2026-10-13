"""Prescription photos and scan reports attached to a user's record."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from urllib.parse import quote
from typing import Any

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.uploads import ALLOWED_LABEL, MAX_BYTES, human_size, save, sniff
from app.core import uploads
from app.core import storage
from app.db.database import get_db
from app.db.models import Attachment, Observation, User
from app.routers.auth import own_patient

router = APIRouter(prefix="/me/attachments", tags=["attachments"])

KINDS = {"prescription", "scan", "report", "other"}


def _out(a: Attachment) -> dict[str, Any]:
    return {
        "attachment_id": a.attachment_id,
        "filename": a.filename,
        "content_type": a.content_type,
        "kind": a.kind,
        "size_bytes": a.size_bytes,
        "size_label": human_size(a.size_bytes),
        "note": a.note,
        "taken_on": a.taken_on.isoformat() if a.taken_on else None,
        "observation_id": a.observation_id,
        "is_image": a.content_type.startswith("image/"),
        "created_at": a.created_at.isoformat(),
    }


@router.get("", summary="List my uploaded files")
def list_attachments(user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(
        select(Attachment).where(Attachment.user_id == user.user_id)
        .order_by(Attachment.created_at.desc())).all()
    return {"attachments": [_out(a) for a in rows], "count": len(rows)}


@router.post("", status_code=status.HTTP_201_CREATED,
             summary="Upload a prescription photo or scan report")
async def upload(
    file: UploadFile = File(..., description="Image or PDF, up to 10 MB."),
    kind: str = Form("prescription"),
    note: str | None = Form(None),
    taken_on: str | None = Form(None),
    observation_id: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if kind not in KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"kind must be one of {sorted(KINDS)}.")

    data = await file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "That file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"That file is {human_size(len(data))}. The limit is "
            f"{human_size(MAX_BYTES)} — try a smaller photo.")

    # The declared content type is ignored; the real one comes from the bytes.
    detected = sniff(data[:32])
    if detected is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"That does not look like a supported file. Please upload a "
            f"{ALLOWED_LABEL}.")
    content_type, extension, _label = detected

    if observation_id:
        patient = own_patient(db, user)
        obs = db.get(Observation, observation_id)
        if obs is None or patient is None or obs.patient_id != patient.patient_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "That eye test result was not found.")

    parsed_date = None
    if taken_on:
        try:
            parsed_date = date.fromisoformat(taken_on)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "taken_on must be a date like 2026-09-08.") from None

    attachment_id, path = save(user.user_id, data, extension)
    patient = own_patient(db, user)
    row = Attachment(
        attachment_id=attachment_id,
        user_id=user.user_id,
        patient_id=patient.patient_id if patient else None,
        observation_id=observation_id or None,
        filename=re.sub(r"[\x00-\x1f\x7f]", "", (file.filename or f"upload{extension}").replace("\\", "/").split("/")[-1])[:255] or f"upload{extension}",
        content_type=content_type,
        kind=kind,
        size_bytes=len(data),
        stored_path=str(path),
        note=note or None,
        taken_on=parsed_date,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("/{attachment_id}/file", summary="Download one of my files")
def get_file(attachment_id: str, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(Attachment, attachment_id)
    if row is None or row.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    if row.stored_path.startswith("s3://"):
        def chunks():
            with storage.read(row.stored_path) as stream:
                while chunk := stream.read(65536):
                    yield chunk
        return StreamingResponse(chunks(), media_type=row.content_type, headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(row.filename),
            "Content-Security-Policy": "default-src 'none'; sandbox"})
    path = storage.local_path(row.stored_path)
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE,
                            "That file is no longer on the server.")
    return FileResponse(
        path,
        media_type=row.content_type,
        filename=row.filename,
        headers={
            # The stored type was derived from the bytes, but tell the browser
            # not to sniff anyway, and forbid it from executing anything.
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; "
                                       "object-src 'none'; sandbox",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.patch("/{attachment_id}", summary="Rename a file or change its note")
def update_attachment(attachment_id: str, note: str | None = Form(None),
                      kind: str | None = Form(None),
                      observation_id: str | None = Form(None),
                      user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(Attachment, attachment_id)
    if row is None or row.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    if note is not None:
        row.note = note or None
    if kind is not None:
        if kind not in KINDS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"kind must be one of {sorted(KINDS)}.")
        row.kind = kind
    if observation_id is not None:
        if observation_id:
            patient = own_patient(db, user)
            obs = db.get(Observation, observation_id)
            if not obs or not patient or obs.patient_id != patient.patient_id:
                raise HTTPException(404, "That eye test result was not found")
        row.observation_id = observation_id or None
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response, summary="Delete one of my files")
def delete_attachment(attachment_id: str, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    row = db.get(Attachment, attachment_id)
    if row is None or row.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    uploads.delete(row.stored_path)
    db.delete(row)
    db.commit()
