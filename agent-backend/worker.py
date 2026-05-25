"""
Wrapper layer giữa FastAPI endpoints (main.py) và logic ES/agent.

Vai trò: cô lập main.py khỏi việc biết tên hàm chi tiết bên trong
elasticsearch_queries / name_chat → đổi tên hàm dưới không vỡ API contract.
"""
from custom_agents.name_chat import get_name
from elasticsearch_queries import (
    get_area_by_district,
    get_price_by_date,
    get_price_by_district,
    get_price_per_square_by_date,
    get_price_per_square_by_district,
    update_all_global_districts,
)


def get_price_district(estate_type_index: str, listing_type: str):
    return get_price_by_district(estate_type_index, listing_type)


def get_price_per_square_district(estate_type_index: str, listing_type: str):
    return get_price_per_square_by_district(estate_type_index, listing_type)


def get_area_district(estate_type_index: str, listing_type: str):
    return get_area_by_district(estate_type_index, listing_type)


def get_price_date(estate_type_index: str, selected_district: str, start_date, end_date, listing_type: str):
    return get_price_by_date(estate_type_index, selected_district, start_date, end_date, listing_type)


def get_price_per_square_date(estate_type_index: str, selected_district: str, start_date, end_date, listing_type: str):
    return get_price_per_square_by_date(estate_type_index, selected_district, start_date, end_date, listing_type)


def update_global_districts(province: str):
    return update_all_global_districts(province)


async def get_name_conversation(query):
    return await get_name(query)
