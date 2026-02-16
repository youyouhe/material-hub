"""Pydantic request/response schemas for MaterialHub API."""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: int
    filename: str
    upload_time: Optional[str] = None
    section_count: int
    image_count: int


class MaterialResponse(BaseModel):
    id: int
    document_id: int
    source_filename: Optional[str] = None
    section: str
    title: str
    heading_level: int
    image_filename: str
    image_url: str
    file_size: int
    expiry_date: Optional[str] = None
    is_expired: Optional[bool] = None
    created_at: Optional[str] = None


class MaterialUpdate(BaseModel):
    title: Optional[str] = None
    section: Optional[str] = None
    expiry_date: Optional[date] = None


class ExtractionResult(BaseModel):
    document_id: int
    filename: str
    section_count: int
    image_count: int
    materials: list[MaterialResponse]


class SearchParams(BaseModel):
    q: Optional[str] = None
    document_id: Optional[int] = None
    status: str = "valid"  # valid | expired | all
