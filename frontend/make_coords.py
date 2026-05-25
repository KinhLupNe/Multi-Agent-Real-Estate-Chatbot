import json
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
import random

# --- CẤU HÌNH ---
OUTPUT_FILE = "district_coords.json"
# Load danh sách địa chính của bạn
try:
    with open("../agent-backend/province_district_ward_prefix.json", "r", encoding="utf-8") as f:
        locations = json.load(f)
except FileNotFoundError:
    print("❌ Lỗi: Không tìm thấy file vietnam_locations.json")
    exit()

# Khởi tạo Geolocator với timeout lớn hơn (10 giây)
geolocator = Nominatim(user_agent="vn_real_estate_app_v2", timeout=10)

coord_db = {}

def get_lat_lon_with_retry(query, max_retries=3):
    """Hàm lấy tọa độ có cơ chế thử lại nếu mạng lỗi"""
    for attempt in range(max_retries):
        try:
            location = geolocator.geocode(query)
            return location
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            wait_time = (attempt + 1) * 2  # Lần 1 chờ 2s, lần 2 chờ 4s...
            print(f"⚠️ Mạng lỗi '{query}'. Thử lại lần {attempt + 1} sau {wait_time}s...")
            time.sleep(wait_time)
        except Exception as e:
            print(f"❌ Lỗi lạ: {e}")
            return None
    return None

print(f"🚀 Bắt đầu quét tọa độ cho {len(locations)} tỉnh thành...")

total_districts = sum(len(p) for p in locations.values()) - len(locations) # Trừ key 'prefix'
processed_count = 0

for province, p_data in locations.items():
    coord_db[province] = {}
    districts = [k for k in p_data.keys() if k != "prefix"]
    
    print(f"\n--- Đang xử lý: {province} ({len(districts)} quận/huyện) ---")
    
    for dist in districts:
        # Tạo query cụ thể để tránh nhầm lẫn (VD: Huyện Gia Lâm vs Phường Gia Lâm)
        # Thêm "District" hoặc "Town" vào tiếng Anh giúp Nominatim hiểu rõ hơn
        query = f"{dist}, {province}, Vietnam"
        
        location = get_lat_lon_with_retry(query)
        
        if location:
            coord_db[province][dist] = [location.latitude, location.longitude]
            print(f"✅ [{processed_count}/{total_districts}] Found: {dist}")
        else:
            print(f"❌ [{processed_count}/{total_districts}] Not Found: {dist}")
            coord_db[province][dist] = None # Vẫn lưu key nhưng value là None
            
        processed_count += 1
        
        # QUAN TRỌNG: Ngủ ngẫu nhiên từ 1.5 đến 3 giây để không bị server chặn
        time.sleep(random.uniform(1.5, 3.0))

    # Cứ xong 1 tỉnh thì lưu file 1 lần (Checkpoint)
    # Để lỡ có mất mạng thì không phải chạy lại từ đầu
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(coord_db, f, ensure_ascii=False, indent=4)
    print(f"💾 Đã lưu tiến độ của {province}")

print(f"\n🎉 HOÀN TẤT! Dữ liệu đã lưu tại {OUTPUT_FILE}")