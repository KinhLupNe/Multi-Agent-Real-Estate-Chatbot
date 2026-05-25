"""
Vẽ heatmap giá BĐS theo quận/huyện trên folium map.

Coords từ file `district_coords_full.json` (sinh bởi `make_coords.py`) — index
theo `{province: {district: [lat, lon]}}` để tránh trùng tên quận giữa các tỉnh.
"""
import json

import folium
import pandas as pd
from folium import plugins


COORD_DB: dict = {}
try:
    with open("district_coords_full.json", "r", encoding="utf-8") as f:
        COORD_DB = json.load(f)
except Exception:
    print("Cảnh báo: Chưa có file district_coords_full.json — heatmap sẽ trống.")


def get_district_coordinates(district_name: str, province_name: str):
    """Trả về [lat, lon] cho cặp (province, district), hoặc None nếu không có."""
    if province_name in COORD_DB:
        return COORD_DB[province_name].get(district_name)
    return None


def _build_heatmap(price_df: pd.DataFrame, current_province: str, value_col: str, unit_label: str):
    """Builder chung cho cả 2 heatmap (giá tổng và giá/m²) — tránh duplicate logic.

    Sinh map có:
      - HeatMap layer (chuẩn hóa giá về 0-1 cho gradient màu)
      - CircleMarker mỗi quận, tooltip giá thực tế
      - Auto fit_bounds theo các điểm có tọa độ
    """
    DEFAULT_CENTER = (21.0285, 105.8542)  # Hồ Hoàn Kiếm — fallback khi không có coord nào
    if price_df.empty:
        return folium.Map(location=list(DEFAULT_CENTER), zoom_start=10)

    max_price = price_df[value_col].max()
    min_price = price_df[value_col].min()

    lat_list: list[float] = []
    lon_list: list[float] = []
    heat_data: list[list[float]] = []
    marker_data: list[dict] = []

    for _, row in price_df.iterrows():
        dist_name = row["Quận/Huyện"]
        coords = get_district_coordinates(dist_name, current_province)
        if not coords:
            continue
        lat, lon = coords
        val = row[value_col]
        # Chuẩn hóa min-max về [0,1] cho heatmap weight. Cùng giá trị (max=min) → giữa thang.
        normalized = (val - min_price) / (max_price - min_price) if max_price > min_price else 0.5
        lat_list.append(lat)
        lon_list.append(lon)
        heat_data.append([lat, lon, normalized])
        marker_data.append({"coords": coords, "name": dist_name, "value": val})

    # Center map theo trọng tâm các quận có tọa độ, không hardcode HN.
    center_lat = sum(lat_list) / len(lat_list) if lat_list else DEFAULT_CENTER[0]
    center_lon = sum(lon_list) / len(lon_list) if lon_list else DEFAULT_CENTER[1]

    m = folium.Map(location=[center_lat, center_lon], zoom_start=10, zoom_control=False)
    if heat_data:
        plugins.HeatMap(heat_data, radius=25, blur=15).add_to(m)

    for item in marker_data:
        folium.CircleMarker(
            location=item["coords"],
            radius=4,
            color="black",
            weight=1,
            fill=True,
            fill_color="white",
            fill_opacity=0.7,
            tooltip=f"{item['name']}: {item['value']:,.0f} {unit_label}",
        ).add_to(m)

    if lat_list:
        m.fit_bounds([[min(lat_list), min(lon_list)], [max(lat_list), max(lon_list)]])
    return m


def create_price_heatmap(price_df: pd.DataFrame, current_province: str):
    """Heatmap giá trung bình (VNĐ) — dùng cho dashboard tab Chatbot/Người mua."""
    return _build_heatmap(price_df, current_province, "Giá Trung Bình (VNĐ)", "VNĐ")


def create_price_per_square_heatmap(price_per_square_df: pd.DataFrame, current_province: str):
    """Heatmap đơn giá m² (VNĐ/m²) — dùng cho dashboard tab Nhà đầu tư (roadmap)."""
    return _build_heatmap(price_per_square_df, current_province, "Giá Trung Bình/m² (VNĐ)", "VNĐ/m²")
