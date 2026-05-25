import requests
import pandas as pd
import streamlit as st
BASE_URL = "http://localhost:8000"

def set_active_province(province_name: str):
    try:
        # Lưu ý: Cần encode URL nếu tên tỉnh có dấu, requests thường tự xử lý
        endpoint = f"{BASE_URL}/set_active_province/{province_name}"
        response = requests.post(endpoint)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"Lỗi kết nối Server: {e}")
        return False
 


def price_by_date(estate_type_index: str, district: str, start_date, end_date, listing_type):
    endpoint = f"{BASE_URL}/get_price_by_date/{listing_type}/{estate_type_index}/{district}/{start_date}/{end_date}"
    response = requests.get(endpoint)
    response.raise_for_status()
    data = response.json()
    dates, avg_prices = data["dates"], data["avg_prices"]
    df = pd.DataFrame({
        "Ngày": dates,
        "Giá Trung Bình (VNĐ)": avg_prices
    })
    return df.sort_values("Ngày", ascending=True)


def price_per_square_by_date(estate_type_index: str, district: str, start_date, end_date, listing_type):
    endpoint = f"{BASE_URL}/get_price_per_square_by_date/{listing_type}/{estate_type_index}/{district}/{start_date}/{end_date}"
    response = requests.get(endpoint)
    response.raise_for_status()
    data = response.json()
    dates, avg_prices_per_square = data["dates"], data["avg_prices_per_square"]
    df = pd.DataFrame({
        "Ngày": dates,
        "Giá Trung Bình/m² (VNĐ)": avg_prices_per_square
    })
    return df.sort_values("Ngày", ascending=True)


def price_by_district(estate_type_index: str, listing_type):
    endpoint = f"{BASE_URL}/get_price_by_district/{listing_type}/{estate_type_index}"
    response = requests.get(endpoint)
    response.raise_for_status()
    data = response.json()
    df = pd.DataFrame({
        'Quận/Huyện': data["districts"],
        'Giá Trung Bình (VNĐ)': data["avg_prices"],
        'Giá Median (VNĐ)': data.get("median_prices") or [0] * len(data["districts"]),
    })
    return df.sort_values('Giá Trung Bình (VNĐ)', ascending=False)


def price_per_square_by_district(estate_type_index: str, listing_type):
    endpoint = f"{BASE_URL}/get_price_per_square_by_district/{listing_type}/{estate_type_index}"
    response = requests.get(endpoint)
    response.raise_for_status()
    data = response.json()
    df = pd.DataFrame({
        'Quận/Huyện': data["districts"],
        'Giá Trung Bình/m² (VNĐ)': data["avg_prices_per_square"],
        'Giá Median/m² (VNĐ)': data.get("median_prices_per_square") or [0] * len(data["districts"]),
    })
    return df.sort_values('Giá Trung Bình/m² (VNĐ)', ascending=False)


def area_by_district(estate_type_index: str, listing_type):
    endpoint = f"{BASE_URL}/get_area_by_district/{listing_type}/{estate_type_index}"
    response = requests.get(endpoint)
    response.raise_for_status()
    data = response.json()
    df = pd.DataFrame({
        'Quận/Huyện': data["districts"],
        'Diện tích trung bình (m²)': data["avg_areas"],
        'Diện tích Median (m²)': data.get("median_areas") or [0] * len(data["districts"]),
    })
    return df.sort_values('Diện tích trung bình (m²)', ascending=False)


# ============================================================
#  DASHBOARD V2 — fetch helpers
# ============================================================

def fetch_kpi(estate_type_index: str, listing_type: str):
    r = requests.get(f"{BASE_URL}/dashboard/kpi/{listing_type}/{estate_type_index}")
    r.raise_for_status()
    return r.json()


def fetch_price_segments(estate_type_index: str, listing_type: str) -> pd.DataFrame:
    r = requests.get(f"{BASE_URL}/dashboard/price_segments/{listing_type}/{estate_type_index}")
    r.raise_for_status()
    items = r.json()["segments"]
    return pd.DataFrame(items)


def fetch_pps_quartiles(estate_type_index: str, listing_type: str) -> pd.DataFrame:
    r = requests.get(f"{BASE_URL}/dashboard/pps_quartiles/{listing_type}/{estate_type_index}")
    r.raise_for_status()
    items = r.json()["districts"]
    return pd.DataFrame(items)


def fetch_listing_count(estate_type_index: str, listing_type: str) -> pd.DataFrame:
    r = requests.get(f"{BASE_URL}/dashboard/listing_count/{listing_type}/{estate_type_index}")
    r.raise_for_status()
    data = r.json()
    return pd.DataFrame({"Quận/Huyện": data["districts"], "Số tin": data["counts"]})


def fetch_field_distribution(estate_type_index: str, listing_type: str, field: str) -> pd.DataFrame:
    r = requests.get(f"{BASE_URL}/dashboard/field_dist/{listing_type}/{estate_type_index}/{field}")
    r.raise_for_status()
    return pd.DataFrame(r.json()["items"])


def fetch_range_distribution(estate_type_index: str, listing_type: str, field: str) -> pd.DataFrame:
    r = requests.get(f"{BASE_URL}/dashboard/range_dist/{listing_type}/{estate_type_index}/{field}")
    r.raise_for_status()
    return pd.DataFrame(r.json()["items"])


def fetch_trend_monthly(estate_type_index: str, listing_type: str, district: str = "") -> pd.DataFrame:
    params = {"district": district} if district else {}
    r = requests.get(
        f"{BASE_URL}/dashboard/trend_monthly/{listing_type}/{estate_type_index}",
        params=params,
    )
    r.raise_for_status()
    data = r.json()
    return pd.DataFrame({
        "Tháng": pd.to_datetime(data["months"]),
        "Median giá": data["medians"],
        "Số tin": data["counts"],
    })