"""
Pydantic models cho Post object — output của SearchAgent, input của WriterAgent.

Cấu trúc nested theo ES doc schema: Post chứa Address + ContactInfo + ExtraInfos.
"""
from typing import List, Optional

from pydantic import BaseModel


class Address(BaseModel):
    district: str
    full_address: str
    province: str
    ward: str


class ContactInfo(BaseModel):
    name: str
    phone: List[str]


class ExtraInfos(BaseModel):
    direction: Optional[str] = None
    front_face: Optional[float] = None
    front_road: Optional[float] = None
    no_bathrooms: Optional[int] = None
    no_bedrooms: Optional[int] = None
    no_floors: Optional[int] = None
    ultilization_square: Optional[float] = None
    yo_construction: Optional[int] = None
    legal: Optional[str] = None


class Post(BaseModel):
    address: Address
    contact_info: ContactInfo
    description: str
    estate_type: str
    extra_infos: ExtraInfos
    id: Optional[str | int] = None
    link: str
    post_date: str
    created_at: str
    post_id: str
    price: float
    price_per_square: float
    square: float
    title: str

    class Config:
        populate_by_name = True
