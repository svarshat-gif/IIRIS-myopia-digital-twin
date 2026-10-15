"""Independent onset research API; no patient lookup or progression substitution."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import get_current_user
from app.ml import onset

router = APIRouter(prefix='/research', tags=['research'])


class OnsetInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    age: float = Field(..., ge=5, le=9, description='Years; model population is ages 5-9')
    spheq: float = Field(..., gt=-.75, le=15, description='Baseline SE in D; initially nonmyopic cohort only')
    al: float = Field(..., ge=15, le=35, description='Measured baseline axial length in mm')
    gender: Literal[0, 1] | None = Field(None, description='Original codebook: 0 male, 1 female; null unknown')
    mommy: Literal[0, 1] | None = Field(None, description='Mother myopic: 0 no, 1 yes; null unknown')
    dadmy: Literal[0, 1] | None = Field(None, description='Father myopic: 0 no, 1 yes; null unknown')
    sporthr: float | None = Field(None, ge=0, le=168, description='Sports/outdoor activity hours/week, not pure outdoor exposure')
    readhr: float | None = Field(None, ge=0, le=168, description='Pleasure reading hours/week')
    comphr: float | None = Field(None, ge=0, le=168, description='Computer/games hours/week')
    studyhr: float | None = Field(None, ge=0, le=168, description='School study hours/week')
    tvhr: float | None = Field(None, ge=0, le=168, description='TV hours/week')


@router.post('/onset/predict', summary='Separate five-year incident-myopia research estimate')
def predict_onset(payload: OnsetInput, user=Depends(get_current_user)):
    try:
        return onset.predict(payload.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
