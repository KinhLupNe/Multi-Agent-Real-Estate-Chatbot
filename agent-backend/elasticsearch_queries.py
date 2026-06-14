from elasticsearch import Elasticsearch
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
import time
from datetime import date
import os
from dotenv import load_dotenv

load_dotenv(override=True)

es = Elasticsearch(
    [f"http://{os.getenv('ES_HOST', '127.0.0.1')}:{os.getenv('ES_PORT', '9200')}"],
    basic_auth=(os.getenv("ES_USER", "elastic"), os.getenv("ES_PASS", "")),
)

# Danh sách quận/huyện hợp lệ — set lại theo tỉnh user chọn qua /set_active_province.
# Mọi dashboard query đều filter theo list này để không lẫn data tỉnh khác.
valid_districts: list[str] = []

# --- Ngưỡng loại outlier khi tính trung bình dashboard ---
# Lý do: data crawl đôi khi parse sai (vd 1 record giá 7.5×10^18 VNĐ kéo avg cả quận lên).
# Cap reasonable cho BĐS dân dụng VN. Nếu cần đổi → sửa ở đây 1 chỗ duy nhất.
PRICE_MIN = 1                       # > 0 VNĐ (loại record giá = 0 / liên hệ)
PRICE_MAX = 1_000_000_000_000       # 1.000 tỷ VNĐ
PRICE_PER_SQ_MIN = 1                # > 0 VNĐ/m²
PRICE_PER_SQ_MAX = 5_000_000_000    # 5 tỷ/m² (đất vàng HN cũng chỉ ~1 tỷ/m²)
SQUARE_MIN = 10                     # ≥ 10 m² (nhà mặt phố không thể nhỏ hơn; <10 thường do crawler parse nhầm "5 tầng" thành 5m²)
SQUARE_MAX = 10_000                 # 10.000 m²


def _price_range_filter():
    return {"range": {"price": {"gte": PRICE_MIN, "lte": PRICE_MAX}}}


def _price_per_sq_range_filter():
    return {"range": {"price/square": {"gte": PRICE_PER_SQ_MIN, "lte": PRICE_PER_SQ_MAX}}}


def _square_range_filter():
    return {"range": {"square": {"gte": SQUARE_MIN, "lte": SQUARE_MAX}}}


LOCATIONS_DB = {}
try:
    with open("province_district_ward_prefix.json", "r", encoding="utf-8") as f:
        LOCATIONS_DB = json.load(f)
except Exception as e:
    print(f"Lỗi load file json: {e}")


def update_all_global_districts(province_name):
    """
    Hàm này sẽ thay đổi giá trị của biến toàn cục 'valid_districts'
    dựa trên tên tỉnh được truyền vào.
    """
    global valid_districts 
    
    if province_name in LOCATIONS_DB:
        province_data = LOCATIONS_DB[province_name]
        # Lấy danh sách key (tên huyện), trừ key "prefix" ra
        new_districts = [k for k in province_data.keys() if k != "prefix"]
        
        # Cập nhật biến global
        valid_districts = new_districts
        print(f"-> Đã chuyển context sang: {province_name} với {len(valid_districts)} quận/huyện.")
        return True
    else:
        print(f"-> Cảnh báo: Không tìm thấy tỉnh {province_name}")
        valid_districts = [] # Hoặc giữ nguyên tùy logic
        return False

def get_price_by_district(estate_type="nhamatpho", listing_type="buy"):
    """
    Lấy dữ liệu giá trung bình theo quận/huyện có lọc theo loại hình Bán/Thuê.
    
    Args:
        estate_type (str): Loại nhà ('nhamatpho', 'nharieng', 'chungcu', 'bietthu')
        listing_type (str): 'buy' (Nhà bán) hoặc 'rent' (Cho thuê)
        
    Returns:
        DataFrame: DataFrame chứa thông tin quận/huyện và giá trung bình
    """
    index_mapping = {
        "nhamatpho": "nhamatpho_index",
        "nharieng": "nharieng_index",
        "chungcu": "chungcu_index",
        "bietthu": "bietthu_index",
        "dat": "dat_index"
    }
    
    if not valid_districts:
        return [], [], []

    index_name = index_mapping.get(estate_type, "nhamatpho_index")

    # 1. Định nghĩa bộ lọc từ khóa "Thuê"
    rent_filter_conditions = [
        { "wildcard": { "estate_type": "*thuê*" } }, 
        { "wildcard": { "estate_type": "*thue*" } }
    ]

    # 2. Khởi tạo cấu trúc query cơ bản (Lọc theo Quận + loại outlier giá)
    bool_query = {
        "must": [
            { "terms": { "district.keyword": valid_districts } },
            _price_range_filter(),
        ]
    }

    # 3. Logic phân loại Bán (Buy) vs Thuê (Rent)
    if listing_type == "rent":
        # === TRƯỜNG HỢP CHO THUÊ ===
        # Logic: Phải chứa "thuê" HOẶC "thue"
        # Ta nhúng một câu lệnh bool/should vào trong must để đảm bảo tính chất OR
        bool_query["must"].append({
            "bool": {
                "should": rent_filter_conditions,
                "minimum_should_match": 1 # Chỉ cần khớp 1 trong các điều kiện là lấy
            }
        })
    else:
        # === TRƯỜNG HỢP NHÀ BÁN (Mặc định) ===
        # Logic: KHÔNG ĐƯỢC chứa "thuê" VÀ KHÔNG ĐƯỢC chứa "thue"
        bool_query["must_not"] = rent_filter_conditions

    # 4. Ghép vào query hoàn chỉnh
    query = {
        "size": 0,
        "query": {
            "bool": bool_query
        },
        "aggs": {
            "group_by_district": {
                "terms": {
                    "field": "district.keyword",
                    "size": len(valid_districts)
                },
                "aggs": {
                    "avg_price": {"avg": {"field": "price"}},
                    "median_price": {"percentiles": {"field": "price", "percents": [50]}},
                }
            }
        }
    }

    # Thực hiện truy vấn
    response = es.search(index=index_name, body=query)

    districts = valid_districts
    avg_prices = []
    median_prices = []
    avg_by_district = {d: 0 for d in valid_districts}
    median_by_district = {d: 0 for d in valid_districts}

    if 'aggregations' in response:
        for bucket in response['aggregations']['group_by_district']['buckets']:
            district = bucket['key']
            avg_v = bucket['avg_price']['value']
            med_v = (bucket.get('median_price', {}).get('values') or {}).get('50.0')
            if avg_v is not None:
                avg_by_district[district] = avg_v
            if med_v is not None:
                median_by_district[district] = med_v

    for district in districts:
        avg_prices.append(avg_by_district[district])
        median_prices.append(median_by_district[district])

    return districts, avg_prices, median_prices


def get_price_per_square_by_district(estate_type="nhamatpho", listing_type="buy"):
    """
    Lấy dữ liệu giá trung bình trên mét vuông theo quận/huyện, lọc theo Bán/Thuê.
    
    Args:
        estate_type (str): Loại nhà ('nhamatpho', 'nharieng', 'chungcu', 'bietthu')
        listing_type (str): 'buy' (Nhà bán) hoặc 'rent' (Cho thuê)
        
    Returns:
        tuple: (districts, avg_prices_per_square) chứa danh sách quận/huyện và giá trung bình/m2
    """

    index_mapping = {
        "nhamatpho": "nhamatpho_index",
        "nharieng": "nharieng_index",
        "chungcu": "chungcu_index",
        "bietthu": "bietthu_index",
        "dat": "dat_index"
    }

    if not valid_districts:
        return [], [], []

    index_name = index_mapping.get(estate_type, "nhamatpho_index")

    # 1. Định nghĩa bộ lọc từ khóa "Thuê"
    rent_filter_conditions = [
        { "wildcard": { "estate_type": "*thuê*" } }, 
        { "wildcard": { "estate_type": "*thue*" } }
    ]

    # 2. Khởi tạo query cơ bản (Lọc theo Quận + loại outlier giá/m²)
    bool_query = {
        "must": [
            { "terms": { "district.keyword": valid_districts } },
            _price_per_sq_range_filter(),
        ]
    }

    # 3. Logic phân loại Bán (Buy) vs Thuê (Rent)
    if listing_type == "rent":
        # === CHO THUÊ ===
        # Lấy bản ghi có chứa chữ "thuê" HOẶC "thue"
        bool_query["must"].append({
            "bool": {
                "should": rent_filter_conditions,
                "minimum_should_match": 1
            }
        })
    else:
        # === NHÀ BÁN (Mặc định) ===
        # Loại bỏ bản ghi chứa chữ "thuê" VÀ "thue"
        bool_query["must_not"] = rent_filter_conditions

    # 4. Ghép vào query hoàn chỉnh
    query = {
        "size": 0,
        "query": {
            "bool": bool_query
        },
        "aggs": {
            "group_by_district": {
                "terms": {
                    "field": "district.keyword",
                    "size": len(valid_districts)
                },
                "aggs": {
                    "avg_price_per_square": {"avg": {"field": "price/square"}},
                    "median_price_per_square": {"percentiles": {"field": "price/square", "percents": [50]}},
                }
            }
        }
    }

    # Thực hiện truy vấn
    response = es.search(index=index_name, body=query)

    districts = valid_districts
    avg_prices_per_square = []
    median_prices_per_square = []
    avg_by_district = {d: 0 for d in valid_districts}
    median_by_district = {d: 0 for d in valid_districts}

    if 'aggregations' in response:
        for bucket in response['aggregations']['group_by_district']['buckets']:
            district = bucket['key']
            avg_v = bucket['avg_price_per_square']['value']
            med_v = (bucket.get('median_price_per_square', {}).get('values') or {}).get('50.0')
            if avg_v is not None:
                avg_by_district[district] = avg_v
            if med_v is not None:
                median_by_district[district] = med_v

    for district in districts:
        avg_prices_per_square.append(avg_by_district[district])
        median_prices_per_square.append(median_by_district[district])

    return districts, avg_prices_per_square, median_prices_per_square



def get_area_by_district(estate_type="nhamatpho", listing_type="buy"):
    """
    Lấy dữ liệu diện tích trung bình theo quận/huyện
    Args:
        estate_type (str): Loại nhà ('nhamatpho', 'nharieng', 'chungcu' hoặc 'bietthu')
        listing_type (str): 'buy' (Nhà bán) hoặc 'rent' (Cho thuê)
    Returns:
        tuple: (districts, avg_areas) chứa danh sách quận/huyện và diện tích trung bình
    """

    index_mapping = {
        "nhamatpho": "nhamatpho_index",
        "nharieng": "nharieng_index",
        "chungcu": "chungcu_index",
        "bietthu": "bietthu_index",
        "dat": "dat_index",
    }

    if not valid_districts:
        return [], [], []

    index_name = index_mapping.get(estate_type, "nhamatpho_index")

    # 1. Định nghĩa điều kiện lọc từ khóa "Thuê"
    rent_conditions = [
        { "wildcard": { "estate_type": "*thuê*" } }, 
        { "wildcard": { "estate_type": "*thue*" } }
    ]

    # 2. Tạo phần khung query cơ bản (Lọc theo quận + loại outlier diện tích)
    bool_query = {
        "must": [
            { "terms": { "district.keyword": valid_districts } },
            _square_range_filter(),
        ]
    }

    # 3. Logic: Nếu là 'rent' thì phải chứa từ khóa thuê, nếu là 'buy' thì cấm chứa
    if listing_type == "rent":
        # Thêm điều kiện: Phải khớp ít nhất 1 trong các từ khóa thuê
        bool_query["must"].append({
            "bool": {
                "should": rent_conditions,
                "minimum_should_match": 1
            }
        })
    else:
        # Mặc định là 'buy': Loại bỏ các bản ghi chứa từ khóa thuê
        bool_query["must_not"] = rent_conditions

    # 4. Ghép vào query hoàn chỉnh
    query = {
        "size": 0,
        "query": {
            "bool": bool_query
        },
        "aggs": {
            "group_by_district": {
                "terms": {
                    "field": "district.keyword",
                    "size": len(valid_districts)
                },
                "aggs": {
                    "avg_area": {"avg": {"field": "square"}},
                    "median_area": {"percentiles": {"field": "square", "percents": [50]}},
                }
            }
        }
    }

    response = es.search(index=index_name, body=query)

    districts = valid_districts
    avg_areas = []
    median_areas = []
    avg_by_district = {d: 0 for d in valid_districts}
    median_by_district = {d: 0 for d in valid_districts}

    if 'aggregations' in response:
        for bucket in response['aggregations']['group_by_district']['buckets']:
            district = bucket['key']
            avg_v = bucket['avg_area']['value']
            med_v = (bucket.get('median_area', {}).get('values') or {}).get('50.0')
            if avg_v is not None:
                avg_by_district[district] = avg_v
            if med_v is not None:
                median_by_district[district] = med_v

    # Tạo danh sách diện tích trung bình theo thứ tự của valid_districts
    for district in districts:
        avg_areas.append(avg_by_district[district])
        median_areas.append(median_by_district[district])

    return districts, avg_areas, median_areas



def get_price_by_date(estate_type, district, s_date, e_date, listing_type="buy"):
    """
    Lấy giá trung bình theo từng ngày trong khoảng thời gian cụ thể, lọc theo Bán/Thuê.

    Args:
        estate_type (str): Loại nhà ('nhamatpho', 'nharieng', 'chungcu' hoặc 'bietthu')
        district (str): Tên quận/huyện
        s_date (str/date): Ngày bắt đầu
        e_date (str/date): Ngày kết thúc
        listing_type (str): 'buy' (Nhà bán) hoặc 'rent' (Cho thuê)

    Returns:
        tuple: (dates, avg_prices)
    """
    index_mapping = {
        "nhamatpho": "nhamatpho_index",
        "nharieng": "nharieng_index",
        "chungcu": "chungcu_index",
        "bietthu": "bietthu_index",
        "dat": "dat_index"
    }

    index_name = index_mapping.get(estate_type, "nhamatpho_index")

    # Xử lý ngày tháng
    try:
        start_date = pd.to_datetime(s_date).strftime("%Y/%m/%d")
        end_date = pd.to_datetime(e_date).strftime("%Y/%m/%d")
    except Exception:
        return [], []

    # 1. Định nghĩa điều kiện lọc từ khóa "Thuê"
    rent_conditions = [
        { "wildcard": { "estate_type": "*thuê*" } },
        { "wildcard": { "estate_type": "*thue*" } }
    ]

    # 2. Tạo phần khung query cơ bản (Quận + Khoảng thời gian + loại outlier giá)
    bool_query = {
        "must": [
            { "term": { "district.keyword": district } },
            {
                "range": {
                    "post_date": {
                        "gte": start_date,
                        "lte": end_date,
                        "format": "yyyy/MM/dd"
                    }
                }
            },
            _price_range_filter(),
        ]
    }

    # 3. Logic: Phân loại Bán vs Thuê
    if listing_type == "rent":
        # === CHO THUÊ ===
        # Thêm điều kiện: Phải khớp ít nhất 1 trong các từ khóa thuê
        bool_query["must"].append({
            "bool": {
                "should": rent_conditions,
                "minimum_should_match": 1
            }
        })
    else:
        # === NHÀ BÁN (Mặc định) ===
        # Loại bỏ các bản ghi chứa từ khóa thuê
        bool_query["must_not"] = rent_conditions

    # 4. Ghép vào query hoàn chỉnh
    query = {
        "size": 0,
        "query": {
            "bool": bool_query
        },
        "aggs": {
            "price_by_date": {
                "date_histogram": {
                    "field": "post_date",
                    "calendar_interval": "day"
                },
                "aggs": {
                    "avg_price": {
                        "avg": {
                            "field": "price"
                        }
                    }
                }
            }
        }
    }

    response = es.search(index=index_name, body=query)

    if "aggregations" not in response:
        return [], [] # Trả về list rỗng thay vì DataFrame để đồng bộ kiểu dữ liệu return

    dates = []
    avg_prices = []

    for bucket in response["aggregations"]["price_by_date"]["buckets"]:
        dates.append(bucket["key_as_string"])
        avg_prices.append(bucket["avg_price"]["value"] or 0)

    return dates, avg_prices




def get_price_per_square_by_date(estate_type, district, s_date, e_date, listing_type="buy"):
    """
    Lấy giá trung bình/m² theo từng ngày, lọc theo Bán/Thuê.

    Args:
        estate_type (str): Loại nhà ('nhamatpho', 'nharieng', 'chungcu' hoặc 'bietthu')
        district (str): Tên quận/huyện
        s_date (str/date): Ngày bắt đầu
        e_date (str/date): Ngày kết thúc
        listing_type (str): 'buy' (Nhà bán) hoặc 'rent' (Cho thuê)

    Returns:
        tuple: (dates, avg_prices_per_square)
    """
    index_mapping = {
        "nhamatpho": "nhamatpho_index",
        "nharieng": "nharieng_index",
        "chungcu": "chungcu_index",
        "bietthu": "bietthu_index",
        "dat": "dat_index"
    }

    index_name = index_mapping.get(estate_type, "nhamatpho_index")

    # Xử lý ngày tháng
    try:
        start_date = pd.to_datetime(s_date).strftime("%Y/%m/%d")
        end_date = pd.to_datetime(e_date).strftime("%Y/%m/%d")
    except Exception:
        return [], []

    # 1. Định nghĩa điều kiện lọc từ khóa "Thuê"
    rent_conditions = [
        { "wildcard": { "estate_type": "*thuê*" } },
        { "wildcard": { "estate_type": "*thue*" } }
    ]

    # 2. Tạo khung query cơ bản (+ loại outlier giá/m²)
    bool_query = {
        "must": [
            { "term": { "district.keyword": district } },
            {
                "range": {
                    "post_date": {
                        "gte": start_date,
                        "lte": end_date,
                        "format": "yyyy/MM/dd"
                    }
                }
            },
            _price_per_sq_range_filter(),
        ]
    }

    # 3. Logic: Phân loại Bán vs Thuê
    if listing_type == "rent":
        # === CHO THUÊ ===
        # Phải khớp ít nhất 1 trong các từ khóa thuê
        bool_query["must"].append({
            "bool": {
                "should": rent_conditions,
                "minimum_should_match": 1
            }
        })
    else:
        # === NHÀ BÁN (Mặc định) ===
        # Loại bỏ các bản ghi chứa từ khóa thuê
        bool_query["must_not"] = rent_conditions

    # 4. Ghép query hoàn chỉnh
    query = {
        "size": 0,
        "query": {
            "bool": bool_query
        },
        "aggs": {
            "price_by_date": {
                "date_histogram": {
                    "field": "post_date",
                    "calendar_interval": "day"
                },
                "aggs": {
                    "avg_price_per_square": {
                        "avg": {
                            "field": "price/square" # Aggregation trên trường giá/m2
                        }
                    }
                }
            }
        }
    }

    response = es.search(index=index_name, body=query)

    if "aggregations" not in response:
        return [], []

    dates = []
    avg_prices_per_square = []

    for bucket in response["aggregations"]["price_by_date"]["buckets"]:
        dates.append(bucket["key_as_string"])
        avg_prices_per_square.append(bucket["avg_price_per_square"]["value"] or 0)

    return dates, avg_prices_per_square


# ============================================================
#  DASHBOARD V2 — chỉ số tổng quan + phân phối + thanh khoản
# ============================================================

_ESTATE_INDEX_MAP = {
    "nhamatpho": "nhamatpho_index",
    "nharieng": "nharieng_index",
    "chungcu": "chungcu_index",
    "bietthu": "bietthu_index",
    "dat": "dat_index",
    "khac": "khac_index",
}


def _resolve_index(estate_type):
    return _ESTATE_INDEX_MAP.get(estate_type, "nhamatpho_index")


def _build_dashboard_bool_query(listing_type, extra_must=None):
    """Bool query chung cho dashboard widgets: filter districts + buy/rent. extra_must=list[clause]."""
    rent_filter_conditions = [
        {"wildcard": {"estate_type": "*thuê*"}},
        {"wildcard": {"estate_type": "*thue*"}},
    ]
    must_clauses = [{"terms": {"district.keyword": valid_districts}}]
    if extra_must:
        must_clauses.extend(extra_must)
    bool_query = {"must": must_clauses}
    if listing_type == "rent":
        bool_query["must"].append({
            "bool": {"should": rent_filter_conditions, "minimum_should_match": 1}
        })
    else:
        bool_query["must_not"] = rent_filter_conditions
    return bool_query


def get_market_kpi(estate_type="nhamatpho", listing_type="buy"):
    """4 KPI tổng quan: total listings, median price, median price/m², tin mới 7 ngày + % change vs 7 ngày trước."""
    if not valid_districts:
        return {
            "total_listings": 0,
            "median_price": 0,
            "median_price_per_sq": 0,
            "new_7d": 0,
            "prev_7d": 0,
            "pct_change_7d": 0.0,
        }
    from datetime import datetime, timedelta
    today = datetime.now().date()
    d7 = (today - timedelta(days=7)).strftime("%Y/%m/%d")
    d14 = (today - timedelta(days=14)).strftime("%Y/%m/%d")

    bq = _build_dashboard_bool_query(listing_type, extra_must=[_price_range_filter()])
    query = {
        "size": 0,
        "query": {"bool": bq},
        "aggs": {
            "total": {"value_count": {"field": "price"}},
            "median_price": {"percentiles": {"field": "price", "percents": [50]}},
            "median_pps": {"percentiles": {"field": "price/square", "percents": [50]}},
            "new_7d": {"filter": {"range": {"post_date": {"gte": d7, "format": "yyyy/MM/dd"}}}},
            "prev_7d": {"filter": {"range": {"post_date": {"gte": d14, "lt": d7, "format": "yyyy/MM/dd"}}}},
        },
    }
    r = es.search(index=_resolve_index(estate_type), body=query)
    agg = r["aggregations"]
    new_7d = agg["new_7d"]["doc_count"]
    prev_7d = agg["prev_7d"]["doc_count"]
    pct = ((new_7d - prev_7d) / prev_7d * 100) if prev_7d > 0 else 0.0
    return {
        "total_listings": agg["total"]["value"],
        "median_price": (agg["median_price"].get("values") or {}).get("50.0") or 0,
        "median_price_per_sq": (agg["median_pps"].get("values") or {}).get("50.0") or 0,
        "new_7d": new_7d,
        "prev_7d": prev_7d,
        "pct_change_7d": pct,
    }


def get_price_segments(estate_type="nhamatpho", listing_type="buy"):
    """Histogram phân khúc giá: dưới 2 tỷ / 2-5 / 5-10 / 10-30 / >30 tỷ. Trả list[{label, count}]."""
    if not valid_districts:
        return []
    bq = _build_dashboard_bool_query(listing_type, extra_must=[_price_range_filter()])
    query = {
        "size": 0,
        "query": {"bool": bq},
        "aggs": {
            "segments": {
                "range": {
                    "field": "price",
                    "ranges": [
                        {"key": "Dưới 2 tỷ", "to": 2_000_000_000},
                        {"key": "2-5 tỷ", "from": 2_000_000_000, "to": 5_000_000_000},
                        {"key": "5-10 tỷ", "from": 5_000_000_000, "to": 10_000_000_000},
                        {"key": "10-30 tỷ", "from": 10_000_000_000, "to": 30_000_000_000},
                        {"key": "Trên 30 tỷ", "from": 30_000_000_000},
                    ],
                }
            }
        },
    }
    r = es.search(index=_resolve_index(estate_type), body=query)
    return [
        {"label": b["key"], "count": b["doc_count"]}
        for b in r["aggregations"]["segments"]["buckets"]
    ]


def get_price_per_sq_quartiles_by_district(estate_type="nhamatpho", listing_type="buy"):
    """Quartiles giá/m² theo quận → box plot. Trả list[{district, count, p5, p25, p50, p75, p95}]."""
    if not valid_districts:
        return []
    bq = _build_dashboard_bool_query(listing_type, extra_must=[_price_per_sq_range_filter()])
    query = {
        "size": 0,
        "query": {"bool": bq},
        "aggs": {
            "by_district": {
                "terms": {"field": "district.keyword", "size": max(len(valid_districts), 1)},
                "aggs": {
                    "stats": {"percentiles": {"field": "price/square", "percents": [5, 25, 50, 75, 95]}}
                },
            }
        },
    }
    r = es.search(index=_resolve_index(estate_type), body=query)
    out = []
    for b in r["aggregations"]["by_district"]["buckets"]:
        v = b["stats"]["values"]
        out.append({
            "district": b["key"],
            "count": b["doc_count"],
            "p5": v.get("5.0") or 0,
            "p25": v.get("25.0") or 0,
            "p50": v.get("50.0") or 0,
            "p75": v.get("75.0") or 0,
            "p95": v.get("95.0") or 0,
        })
    return sorted(out, key=lambda x: -x["p50"])


def get_listing_count_by_district(estate_type="nhamatpho", listing_type="buy"):
    """Số tin đăng mỗi quận → thanh khoản. Trả {districts, counts}."""
    if not valid_districts:
        return {"districts": [], "counts": []}
    bq = _build_dashboard_bool_query(listing_type)
    query = {
        "size": 0,
        "query": {"bool": bq},
        "aggs": {
            "by_district": {
                "terms": {"field": "district.keyword", "size": max(len(valid_districts), 1)}
            }
        },
    }
    r = es.search(index=_resolve_index(estate_type), body=query)
    counts_map = {b["key"]: b["doc_count"] for b in r["aggregations"]["by_district"]["buckets"]}
    counts = [counts_map.get(d, 0) for d in valid_districts]
    # Sort theo count desc
    pairs = sorted(zip(valid_districts, counts), key=lambda x: -x[1])
    return {"districts": [p[0] for p in pairs], "counts": [p[1] for p in pairs]}


# Field path thực tế trong ES (chỉ address được flatten ra root, các field còn lại vẫn trong extra_infos.*)
_FIELD_PATH = {
    "no_bedrooms": "extra_infos.no_bedrooms",
    "no_bathrooms": "extra_infos.no_bathrooms",
    "no_floors": "extra_infos.no_floors",
    "direction": "extra_infos.direction.keyword",
    "front_face": "extra_infos.front_face",
    "front_road": "extra_infos.front_road",
}


def get_field_distribution(field, estate_type="nhamatpho", listing_type="buy", top_n=10):
    """Top N giá trị + count cho 1 field, KÈM slice 'Chưa rõ' cho doc thiếu field."""
    if not valid_districts:
        return []
    bq = _build_dashboard_bool_query(listing_type)
    es_field = _FIELD_PATH.get(field, field)
    query = {
        "size": 0,
        "query": {"bool": bq},
        "aggs": {
            "by_value": {"terms": {"field": es_field, "size": top_n}},
            "missing_count": {"missing": {"field": es_field}},
        },
    }
    r = es.search(index=_resolve_index(estate_type), body=query)
    out = [
        {"value": str(b["key"]), "count": b["doc_count"]}
        for b in r["aggregations"]["by_value"]["buckets"]
    ]
    mc = r["aggregations"]["missing_count"]["doc_count"]
    if mc > 0:
        out.append({"value": "Chưa rõ", "count": mc})
    return out


# Preset bins cho continuous fields (đơn vị: m / m²)
_RANGE_PRESETS = {
    "front_face": [
        {"key": "Dưới 3m", "to": 3},
        {"key": "3-5m", "from": 3, "to": 5},
        {"key": "5-8m", "from": 5, "to": 8},
        {"key": "8-12m", "from": 8, "to": 12},
        {"key": "Trên 12m", "from": 12},
    ],
    "front_road": [
        {"key": "Dưới 3m (hẻm)", "to": 3},
        {"key": "3-5m", "from": 3, "to": 5},
        {"key": "5-10m", "from": 5, "to": 10},
        {"key": "10-20m", "from": 10, "to": 20},
        {"key": "Trên 20m (đại lộ)", "from": 20},
    ],
    "square": [
        {"key": "Dưới 50m²", "to": 50},
        {"key": "50-100m²", "from": 50, "to": 100},
        {"key": "100-300m²", "from": 100, "to": 300},
        {"key": "300-1000m²", "from": 300, "to": 1000},
        {"key": "Trên 1000m²", "from": 1000},
    ],
}


def get_range_distribution(field, estate_type="nhamatpho", listing_type="buy"):
    """Histogram cho continuous field (front_face, front_road, square). Trả list + slice 'Chưa rõ'."""
    if not valid_districts:
        return []
    ranges = _RANGE_PRESETS.get(field)
    if not ranges:
        return []
    bq = _build_dashboard_bool_query(listing_type)
    es_field = _FIELD_PATH.get(field, field)
    query = {
        "size": 0,
        "query": {"bool": bq},
        "aggs": {
            "ranges": {"range": {"field": es_field, "ranges": ranges}},
            "missing_count": {"missing": {"field": es_field}},
        },
    }
    r = es.search(index=_resolve_index(estate_type), body=query)
    out = [
        {"value": b["key"], "count": b["doc_count"]}
        for b in r["aggregations"]["ranges"]["buckets"]
    ]
    mc = r["aggregations"]["missing_count"]["doc_count"]
    if mc > 0:
        out.append({"value": "Chưa rõ", "count": mc})
    return out


def get_price_trend_monthly(estate_type="nhamatpho", listing_type="buy", district=None):
    """Median giá + count theo tháng. Nếu district truyền vào → lọc cho quận đó."""
    if not valid_districts:
        return {"months": [], "medians": [], "counts": []}
    extra_must = [_price_range_filter()]
    bq = _build_dashboard_bool_query(listing_type, extra_must=extra_must)
    if district:
        # Replace lọc districts list bằng 1 district cụ thể
        bq["must"] = [
            m for m in bq["must"]
            if not (isinstance(m, dict) and "terms" in m and "district.keyword" in m.get("terms", {}))
        ]
        bq["must"].append({"term": {"district.keyword": district}})

    query = {
        "size": 0,
        "query": {"bool": bq},
        "aggs": {
            "trend": {
                "date_histogram": {
                    "field": "post_date",
                    "calendar_interval": "month",
                    "min_doc_count": 1,
                },
                "aggs": {
                    "median": {"percentiles": {"field": "price", "percents": [50]}}
                },
            }
        },
    }
    r = es.search(index=_resolve_index(estate_type), body=query)
    months, medians, counts = [], [], []
    for b in r["aggregations"]["trend"]["buckets"]:
        months.append(b["key_as_string"])
        medians.append((b["median"].get("values") or {}).get("50.0") or 0)
        counts.append(b["doc_count"])
    return {"months": months, "medians": medians, "counts": counts}


# ============================================================
#  END DASHBOARD V2
# ============================================================


def search_posts(
    estate_type: List[str],
    is_latest_posted: bool = None,
    is_latest_created: bool = None,
    province: List[str] = None,
    district: List[str] = None,
    ward: List[str] = None,
    front_face: float = None,
    front_road: float = None,
    no_bathrooms: int = None,
    no_bedrooms: int = None,
    no_floors: int = None,
    ultilization_square: float = None,
    price: float = None,
    min_price: float = None,  # <--- THÊM MỚI
    max_price: float = None,  # <--- THÊM MỚI
    price_per_square: float = None,
    square: float = None,
    description: str = None
) -> List[Dict[str, Any]]:
    """
    Truy vấn bài đăng bất động sản với các tiêu chí linh hoạt, trả về kết quả ngẫu nhiên.
    - estate_type: Danh sách các loại bất động sản.
    - district: Danh sách các quận/huyện.
    - is_latest_posted: Sắp xếp theo post_date giảm dần nếu True.
    - is_latest_created: Sắp xếp theo created_at giảm dần nếu True.
    - Mỗi nhóm tiêu chí trả về tối đa 3 bài, tổng tối đa 12 bài.
    """
    # index_mapping = {
    #     "nhà phố": "nhamatpho_index",
    #     "nhà riêng": "nharieng_index",
    #     "chung cư": "chungcu_index",
    #     "biệt thự": "bietthu_index"
    # }
       # 1. MAPPING ĐẦY ĐỦ (Theo danh sách bạn cung cấp)
    index_mapping = {
        # Nhóm Nhà Phố
        "nhà mặt phố": "nhamatpho_index", "nhà phố": "nhamatpho_index",
        # Nhóm Nhà Riêng
        "nhà riêng": "nharieng_index", "nhà trọ": "nharieng_index", 
        "phòng trọ": "nharieng_index",
        # Nhóm Chung Cư
        "chung cư": "chungcu_index", "tập thể": "chungcu_index", "căn hộ": "chungcu_index",
        # Nhóm Biệt Thự & Đất Biệt Thự
        "biệt thự": "bietthu_index", "liền kề": "bietthu_index",
        "đất biệt thự": "dat_index", # Mapping đặc biệt theo yêu cầu của bạn
        # Nhóm Đất
        "đất": "dat_index", "đất nền": "dat_index", 
        "đất mặt phố": "dat_index", "đất riêng": "dat_index", "đất trang trại": "dat_index",
        # Nhóm Khác
        "kho xưởng": "khac_index", "nhà xưởng": "khac_index", "thuê kho": "khac_index",
        "văn phòng": "khac_index", "cửa hàng": "khac_index", "nhà đất khác": "khac_index"
    }

    target_indices = []
    if estate_type:
        for et in estate_type:
            key = et.lower().strip()
            if key in index_mapping:
                target_indices.append(index_mapping[key])
    target_indices = list(set(target_indices))

    INDEX_NAME = ",".join(target_indices) if target_indices else "nhamatpho_index,nharieng_index,chungcu_index,bietthu_index"
    results = []

    sort = []
    if is_latest_posted:
        sort.append({"post_date": {"order": "desc"}})
    if is_latest_created:
        sort.append({"created_at": {"order": "desc"}})

    def wrap_with_random_score(query: dict) -> dict:
        return {
            "query": {
                "function_score": {
                    "query": query["query"],
                    "random_score": {
                        # "field": "_seq_no"
                    }
                }
            },
            "size": query.get("size", 3)
        }
 
    if max_price:
        price = max_price
    if min_price:
        price = min_price
        
    if province:
        query = {
            "query": {
                "terms": {
                    "province": province  
                }
            },
            "size": 3
        }
        if sort: query["sort"] = sort
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying province: {e}")

    if province and not is_latest_created:
        query = {
            "query": {
                "terms": {
                    "province": province
                }
            },
            "size": 3
        }
        if is_latest_posted:
            query["sort"] = [{"post_date": {"order": "desc"}}]
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying district for post_date: {e}")


    if district:
        query = {
            "query": {
                "terms": {
                    "district": district
                }
            },
            "size": 3
        }
        if sort:
            query["sort"] = sort
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying district: {e}")

    if district and not is_latest_created:
        query = {
            "query": {
                "terms": {
                    "district": district
                }
            },
            "size": 3
        }
        if is_latest_posted:
            query["sort"] = [{"post_date": {"order": "desc"}}]
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying district for post_date: {e}")

    if ward:
        query = {
            "query": {
                "terms": {
                    "address.ward.keyword": ward
                }
            },
            "size": 3
        }
        if sort:
            query["sort"] = sort
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying district: {e}")

    if ward and not is_latest_created:
        query = {
            "query": {
                "terms": {
                    "address.ward.keyword": ward
                }
            },
            "size": 3
        }
        if is_latest_posted:
            query["sort"] = [{"post_date": {"order": "desc"}}]
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying district for post_date: {e}")

    # Nhóm 1: Các trường số nguyên/thực nằm ở root
    root_attrs = {
        "no_bedrooms": no_bedrooms,
        "no_bathrooms": no_bathrooms,
        "no_floors": no_floors,
        "front_face": front_face,  
        "front_road": front_road,
        "ultilization_square": ultilization_square
    }
    
    should_clauses = []
    for k, v in root_attrs.items():
        if v is not None:
            should_clauses.append({"term": {k: v}}) # Truy cập trực tiếp, không qua extra_infos

    if should_clauses:
        query = {
            "query": {
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1
                }
            },
            "size": 3
        }
        if sort: query["sort"] = sort
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying attributes: {e}")
            


    range_params = {
        "price": price,
        "price/square": price_per_square,
        "square": square
    }
    range_clauses = []
    for field, val in range_params.items():
        if val is not None:
            delta = val * 0.2
            range_clauses.append({
                "range": {
                    field: {
                        "gte": val - delta,
                        "lte": val + delta
                    }
                }
            })
    if range_clauses:
        query = {
            "query": {
                "bool": {
                    "should": range_clauses,
                    "minimum_should_match": 1
                }
            },
            "size": 3
        }
        if sort:
            query["sort"] = sort
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"]])
        except Exception as e:
            print(f"Error querying price-related fields: {e}")

    if description:
        query = {
            "query": {
                "match": {
                    "description": {
                        "query": description,
                        "fuzziness": "AUTO"
                    }
                }
            },
            "size": 3
        }
        if is_latest_posted:
            query["sort"] = [{"post_date": {"order": "desc"}}]
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying description: {e}")

    # Khử trùng lặp kết quả (Dựa trên _id của ES hoặc post_id)
    seen_ids = set()
    unique_results = []
    for result in results:
        # Ưu tiên lấy post_id, nếu không có thì lấy link làm định danh
        uid = result.get("post_id") or result.get("link")
        if uid and uid not in seen_ids:
            seen_ids.add(uid)
            unique_results.append(result)
            if len(unique_results) >= 12:
                break
    
    return unique_results

def search_posts_strict(
    estate_type: List[str],
    is_latest_posted: bool = None,
    is_latest_created: bool = None,
    province: List[str] = None,
    district: List[str] = None,
    ward: List[str] = None,
    front_face: float = None,
    front_road: float = None,
    no_bathrooms: int = None,
    no_bedrooms: int = None,
    no_floors: int = None,
    ultilization_square: float = None,
    price: float = None,
    min_price: float = None,  # <--- THÊM MỚI
    max_price: float = None,  # <--- THÊM MỚI
    price_per_square: float = None,
    square: float = None,
    description: str = None
) -> List[Dict[str, Any]]:
    """
    Truy vấn bài đăng bất động sản với các tiêu chí nghiêm ngặt, trả về kết quả ngẫu nhiên.
    - Tất cả tiêu chí phải được thỏa mãn.
    - Hỗ trợ nhiều estate_type và district.
    """
    # index_mapping = {
    #     "nhà phố": "nhamatpho_index",
    #     "nhà riêng": "nharieng_index",
    #     "chung cư": "chungcu_index",
    #     "biệt thự": "bietthu_index"
    # }
    # 1. MAPPING ĐẦY ĐỦ (Theo danh sách bạn cung cấp)
    index_mapping = {
        # Nhóm Nhà Phố
        "nhà mặt phố": "nhamatpho_index", "nhà phố": "nhamatpho_index",
        # Nhóm Nhà Riêng
        "nhà riêng": "nharieng_index", "nhà trọ": "nharieng_index", 
        "phòng trọ": "nharieng_index",
        # Nhóm Chung Cư
        "chung cư": "chungcu_index", "tập thể": "chungcu_index", "căn hộ": "chungcu_index",
        # Nhóm Biệt Thự & Đất Biệt Thự
        "biệt thự": "bietthu_index", "liền kề": "bietthu_index",
        "đất biệt thự": "dat_index", # Mapping đặc biệt theo yêu cầu của bạn
        # Nhóm Đất
        "đất": "dat_index", "đất nền": "dat_index", 
        "đất mặt phố": "dat_index", "đất riêng": "dat_index", "đất trang trại": "dat_index",
        # Nhóm Khác
        "kho xưởng": "khac_index", "nhà xưởng": "khac_index", "thuê kho": "khac_index",
        "văn phòng": "khac_index", "cửa hàng": "khac_index", "nhà đất khác": "khac_index"
    }
    target_indices = []
    if estate_type:
        for et in estate_type:
            # 2. Chuẩn hóa input từ LLM: Viết thường + Xóa khoảng trắng thừa
            key = et.lower().strip()
            if key in index_mapping:
                target_indices.append(index_mapping[key])
    target_indices = list(set(target_indices))

    INDEX_NAME = ",".join(target_indices) if target_indices else "nhamatpho_index,nharieng_index,chungcu_index,bietthu_index"
    print(INDEX_NAME)
    must_clauses = []

    # --- THÊM LOGIC LỌC TỈNH/THÀNH PHỐ ---

    if province:
        safe_province = list(province) if isinstance(province, (list, tuple)) else [str(province)]
        must_clauses.append({"terms": {"province": safe_province}})

    if district:
        safe_district = list(district) if isinstance(district, (list, tuple)) else [str(district)]
        must_clauses.append({"terms": {"district": safe_district}})
    
    if ward:
        safe_ward = list(ward) if isinstance(ward, (list, tuple)) else [str(ward)]
        must_clauses.append({"terms": {"address.ward.keyword": safe_ward}})

    root_attrs = {
        "front_face": front_face,
        "front_road": front_road,
        "no_bathrooms": no_bathrooms,
        "no_bedrooms": no_bedrooms,
        "no_floors": no_floors,
        "ultilization_square": ultilization_square
    }
    for k, v in root_attrs.items():
        if v is not None:
            v = float(v) if isinstance(v, float) else int(v)
            must_clauses.append({"term": {k: v}})




# --- ĐOẠN CODE SỬA (BẮT ĐẦU) ---
    
    # 1. Xử lý PRICE riêng (Hỗ trợ min/max)
    price_range_query = {}
    
    # Ưu tiên logic min/max (cho các câu hỏi "nhỏ hơn", "lớn hơn")
    if min_price is not None:
        price_range_query["gte"] = float(min_price)
    if max_price is not None:
        price_range_query["lte"] = float(max_price)
        
    # Nếu không có min/max mà có price (cho câu hỏi "khoảng 3 tỷ") -> Dùng logic cũ (+- 10%)
    if not price_range_query and price is not None:
        price = float(price)
        delta = price * 0.1
        price_range_query["gte"] = price - delta
        price_range_query["lte"] = price + delta
        
    if price_range_query:
        must_clauses.append({"range": {"price": price_range_query}})

    # 2. Xử lý các range còn lại (Diện tích, Giá m2) - Giữ nguyên logic cũ
    other_range_fields = {
        "price/square": price_per_square,
        "square": square
    }
    for field, val in other_range_fields.items():
        if val is not None:
            val = float(val)
            delta = val * 0.1
            must_clauses.append({
                "range": {
                    field: {
                        "gte": val - delta,
                        "lte": val + delta
                    }
                }
            })
            
    # --- ĐOẠN CODE SỬA (KẾT THÚC) ---



    if description:
        must_clauses.append({
            "match": {
                "description": {
                    "query": description,
                    "fuzziness": "AUTO"
                }
            }
        })

    sort = []
    if is_latest_posted:
        sort.append({"post_date": {"order": "desc"}})
    if is_latest_created:
        sort.append({"created_at": {"order": "desc"}})

    query_body = {
        "query": {
            "function_score": {
                "query": {
                    "bool": {
                        "must": must_clauses
                    }
                },
                "random_score": {
                    # "field": "_seq_no"
                }
            }
        },
        "size": 12
    }
    if sort:
        query_body["sort"] = sort

    try:
        response = es.search(index=INDEX_NAME, body=query_body)
        return [hit["_source"] for hit in response["hits"]["hits"]]
    except Exception as e:
        print(f"Error querying Elasticsearch: {e}")
        return []

if __name__ == "__main__":
    result = search_posts_strict(estate_type=["nhà riêng"], is_latest_posted=True, district=["Ngô Quyền"], province=["Hải Phòng"], no_bedrooms=3, price=7000000000.0)
    print(json.dumps(result, indent=4, ensure_ascii=False))
