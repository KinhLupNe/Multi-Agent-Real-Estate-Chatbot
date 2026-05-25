from elasticsearch import Elasticsearch
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
import time
import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

es = Elasticsearch(
    [f"http://{os.getenv('ES_HOST', '127.0.0.1')}:{os.getenv('ES_PORT', '9200')}"],
    basic_auth=(os.getenv("ES_USER", "elastic"), os.getenv("ES_PASS", "")),
)


def _location_filter_clause(values, root_field: str, nested_field: str):
    # Crawler có thể miss province/district ở root, fallback match trên
    # `address.full_address` (chính xác hơn title/description vì người đăng
    # thường spam tên tỉnh khác trong description để SEO).
    # KHÔNG match title/description nữa — gây false positive (bài Bắc Ninh
    # có "Hà Nội" trong description bị match khi user search Hà Nội).
    if not values:
        return None

    should = [
        {"terms": {f"{root_field}.keyword": values}},
        {"terms": {nested_field: values}},
    ]
    for v in values:
        should.append({"match_phrase": {"address.full_address": v}})

    return {"bool": {"should": should, "minimum_should_match": 1}}

valid_districts = [
        "Ba Đình", "Bắc Từ Liêm", "Cầu Giấy", "Đống Đa", "Hà Đông", "Hai Bà Trưng",
        "Hoàn Kiếm", "Hoàng Mai", "Long Biên", "Nam Từ Liêm", "Tây Hồ", "Thanh Xuân",
        "Ba Vì", "Chương Mỹ", "Đan Phượng", "Đông Anh", "Gia Lâm", "Hoài Đức",
        "Mê Linh", "Mỹ Đức", "Phú Xuyên", "Phúc Thọ", "Quốc Oai", "Sóc Sơn",
        "Thạch Thất", "Thanh Oai", "Thanh Trì", "Thường Tín", "Ứng Hòa", "Sơn Tây"
    ]
def get_price_by_district(estate_type="nhamatpho"):
    """
    Lấy dữ liệu giá trung bình theo quận/huyện
    Args:
        estate_type (str): Loại nhà ('nhamatpho', 'nharieng', 'chungcu' hoặc 'bietthu')
    Returns:
        DataFrame: DataFrame chứa thông tin quận/huyện và giá trung bình
    """
    index_mapping = {
        "nhamatpho": "nhamatpho_index",
        "nharieng": "nharieng_index",
        "chungcu": "chungcu_index",
        "bietthu": "bietthu_index"
    }
    
    index_name = index_mapping.get(estate_type, "nhamatpho_index")

    query = {
        "size": 0,
        "query": {
            "terms": {
                "district": valid_districts
            }
        },
        "aggs": {
            "group_by_district": {
                "terms": {
                    "field": "district",
                    "size": len(valid_districts)
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
    
    districts = valid_districts
    avg_prices = []

    avg_price_by_district = {district: 0 for district in valid_districts}

    # Cập nhật giá trị trung bình từ kết quả truy vấn
    for bucket in response['aggregations']['group_by_district']['buckets']:
        district = bucket['key']
        avg_price = bucket['avg_price']['value']
        if avg_price is not None:
            avg_price_by_district[district] = avg_price

    for district in districts:
        avg_prices.append(avg_price_by_district[district])

    return districts, avg_prices


def get_price_per_square_by_district(estate_type="nhamatpho"):
    """
    Lấy dữ liệu giá trung bình trên mét vuông theo quận/huyện
    Args:
        estate_type (str): Loại nhà ('nhamatpho', 'nharieng', 'chungcu' hoặc 'bietthu')
    Returns:
        tuple: (districts, avg_prices_per_square) chứa danh sách quận/huyện và giá trung bình trên mét vuông
    """

    index_mapping = {
        "nhamatpho": "nhamatpho_index",
        "nharieng": "nharieng_index",
        "chungcu": "chungcu_index",
        "bietthu": "bietthu_index"
    }

    index_name = index_mapping.get(estate_type, "nhamatpho_index")

    query = {
        "size": 0,
        "query": {
            "terms": {
                "district": valid_districts
            }
        },
        "aggs": {
            "group_by_district": {
                "terms": {
                    "field": "district",
                    "size": len(valid_districts)
                },
                "aggs": {
                    "avg_price_per_square": {
                        "avg": {
                            "field": "price/square"
                        }
                    }
                }
            }
        }
    }

    response = es.search(index=index_name, body=query)

    districts = valid_districts
    avg_prices_per_square = []

    # Tạo dictionary để lưu giá trung bình theo quận/huyện, mặc định là 0
    avg_price_per_square_by_district = {district: 0 for district in valid_districts}

    # Cập nhật giá trị trung bình từ kết quả truy vấn
    for bucket in response['aggregations']['group_by_district']['buckets']:
        district = bucket['key']
        avg_price = bucket['avg_price_per_square']['value']
        if avg_price is not None:
            avg_price_per_square_by_district[district] = avg_price

    # Tạo danh sách giá trung bình theo thứ tự của valid_districts
    for district in districts:
        avg_prices_per_square.append(avg_price_per_square_by_district[district])

    return districts, avg_prices_per_square


def get_area_by_district(estate_type="nhamatpho"):
    """
    Lấy dữ liệu diện tích trung bình theo quận/huyện
    Args:
        estate_type (str): Loại nhà ('nhamatpho', 'nharieng', 'chungcu' hoặc 'bietthu')
    Returns:
        tuple: (districts, avg_areas) chứa danh sách quận/huyện và diện tích trung bình
    """

    index_mapping = {
        "nhamatpho": "nhamatpho_index",
        "nharieng": "nharieng_index",
        "chungcu": "chungcu_index",
        "bietthu": "bietthu_index"
    }

    index_name = index_mapping.get(estate_type, "nhamatpho_index")

    query = {
        "size": 0,
        "query": {
            "terms": {
                "district": valid_districts
            }
        },
        "aggs": {
            "group_by_district": {
                "terms": {
                    "field": "district",
                    "size": len(valid_districts)
                },
                "aggs": {
                    "avg_area": {
                        "avg": {
                            "field": "square"
                        }
                    }
                }
            }
        }
    }

    response = es.search(index=index_name, body=query)

    districts = valid_districts
    avg_areas = []

    # Tạo dictionary để lưu diện tích trung bình theo quận/huyện, mặc định là 0
    avg_area_by_district = {district: 0 for district in valid_districts}

    # Cập nhật diện tích trung bình từ kết quả truy vấn
    for bucket in response['aggregations']['group_by_district']['buckets']:
        district = bucket['key']
        avg_area = bucket['avg_area']['value']
        if avg_area is not None:
            avg_area_by_district[district] = avg_area

    # Tạo danh sách diện tích trung bình theo thứ tự của valid_districts
    for district in districts:
        avg_areas.append(avg_area_by_district[district])

    return districts, avg_areas


def get_price_by_date(estate_type, district, s_date, e_date):
    """
    Lấy giá trung bình theo từng ngày trong 10 ngày gần nhất cho một quận/huyện cụ thể.

    Args:
        estate_type (str): Loại nhà ('nhamatpho', 'nharieng', 'chungcu' hoặc 'bietthu')
        district (str): Tên quận/huyện

    Returns:
        DataFrame: DataFrame chứa thông tin ngày và giá trung bình
    """
    index_mapping = {
        "nhamatpho": "nhamatpho_index",
        "nharieng": "nharieng_index",
        "chungcu": "chungcu_index",
        "bietthu": "bietthu_index"
    }

    index_name = index_mapping.get(estate_type, "nhamatpho_index")

    start_date = pd.to_datetime(s_date).strftime("%Y/%m/%d")
    end_date = pd.to_datetime(e_date).strftime("%Y/%m/%d")

    query = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {
                        "term": {
                            "district": district
                        }
                    },
                    {
                        "range": {
                            "price": {"gt": 0}  # Chỉ lấy bài đăng có giá trị hợp lệ
                        }
                    },
                    {
                        "range": {
                            "post_date": {
                                "gte": start_date,
                                "lte": end_date,
                                "format": "yyyy/MM/dd"
                            }
                        }
                    }
                ],
                "must_not": [
                    { "wildcard": { "estate_type": "*Thuê*" } },
                    { "wildcard": { "estate_type": "*thue*" } } # Đề phòng không dấu
                ]
            }
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
        return pd.DataFrame(columns=["Ngày", "Giá Trung Bình (VNĐ)"])

    dates = []
    avg_prices = []

    for bucket in response["aggregations"]["price_by_date"]["buckets"]:
        dates.append(bucket["key_as_string"])
        avg_prices.append(bucket["avg_price"]["value"] or 0)

    return dates, avg_prices

def get_price_per_square_by_date(estate_type, district, s_date, e_date):
    """
    Lấy giá trung bình/m² theo từng ngày trong 10 ngày gần nhất cho một quận/huyện cụ thể.

    Args:
        estate_type (str): Loại nhà ('nhamatpho', 'nharieng', 'chungcu' hoặc 'bietthu')
        district (str): Tên quận/huyện

    Returns:
        DataFrame: DataFrame chứa thông tin ngày và giá trung bình/m²
    """
    index_mapping = {
        "nhamatpho": "nhamatpho_index",
        "nharieng": "nharieng_index",
        "chungcu": "chungcu_index",
        "bietthu": "bietthu_index"
    }

    index_name = index_mapping.get(estate_type, "nhamatpho_index")

    start_date = pd.to_datetime(s_date).strftime("%Y/%m/%d")
    end_date = pd.to_datetime(e_date).strftime("%Y/%m/%d")

    query = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {
                        "term": {
                            "district": district
                        }
                    },
                    {
                        "range": {
                            "price": {"gt": 0}  # Chỉ lấy bài đăng có giá trị hợp lệ
                        }
                    },
                    {
                        "range": {
                            "post_date": {
                                "gte": start_date,
                                "lte": end_date,
                                "format": "yyyy/MM/dd"
                            }
                        }
                    }
                ]
            }
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
                            "field": "price/square"
                        }
                    }
                }
            }
        }
    }

    response = es.search(index=index_name, body=query)

    if "aggregations" not in response:
        return pd.DataFrame(columns=["Ngày", "Giá Trung Bình/m² (VNĐ)"])

    dates = []
    avg_prices_per_square = []

    for bucket in response["aggregations"]["price_by_date"]["buckets"]:
        dates.append(bucket["key_as_string"])
        avg_prices_per_square.append(bucket["avg_price_per_square"]["value"] or 0)

    return  dates, avg_prices_per_square


def search_posts(
    estate_type: List[str] = None,
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
        province_clause = _location_filter_clause(province, "province", "address.province.keyword")
        query = {"query": province_clause, "size": 3}
        if sort:
            query["sort"] = sort
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying province: {e}")

    if province and not is_latest_created:
        province_clause = _location_filter_clause(province, "province", "address.province.keyword")
        query = {"query": province_clause, "size": 3}
        if is_latest_posted:
            query["sort"] = [{"post_date": {"order": "desc"}}]
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying province for post_date: {e}")


    if district:
        district_clause = _location_filter_clause(district, "district", "address.district.keyword")
        query = {"query": district_clause, "size": 3}
        if sort:
            query["sort"] = sort
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying district: {e}")

    if district and not is_latest_created:
        district_clause = _location_filter_clause(district, "district", "address.district.keyword")
        query = {"query": district_clause, "size": 3}
        if is_latest_posted:
            query["sort"] = [{"post_date": {"order": "desc"}}]
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying district for post_date: {e}")

    if ward:
        ward_clause = _location_filter_clause(ward, "ward", "address.ward.keyword")
        query = {"query": ward_clause, "size": 3}
        if sort:
            query["sort"] = sort
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying ward: {e}")

    if ward and not is_latest_created:
        ward_clause = _location_filter_clause(ward, "ward", "address.ward.keyword")
        query = {"query": ward_clause, "size": 3}
        if is_latest_posted:
            query["sort"] = [{"post_date": {"order": "desc"}}]
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"][:3]])
        except Exception as e:
            print(f"Error querying ward for post_date: {e}")

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

    # Fallback: nếu user chỉ truyền estate_type (hoặc không có filter nào),
    # trả random sample từ INDEX_NAME thay vì rỗng — giúp query mơ hồ
    # ("Đất", "Chung cư"...) vẫn có data cho Writer/Judge dùng.
    if not results and target_indices:
        query = {"query": {"match_all": {}}, "size": 12}
        if sort:
            query["sort"] = sort
        try:
            response = es.search(index=INDEX_NAME, body=wrap_with_random_score(query))
            results.extend([hit["_source"] for hit in response["hits"]["hits"]])
        except Exception as e:
            print(f"Error querying fallback match_all: {e}")

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
    estate_type: List[str] = None,
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
        clause = _location_filter_clause(safe_province, "province", "address.province.keyword")
        if clause:
            must_clauses.append(clause)

    if district:
        safe_district = list(district) if isinstance(district, (list, tuple)) else [str(district)]
        clause = _location_filter_clause(safe_district, "district", "address.district.keyword")
        if clause:
            must_clauses.append(clause)

    if ward:
        safe_ward = list(ward) if isinstance(ward, (list, tuple)) else [str(ward)]
        clause = _location_filter_clause(safe_ward, "ward", "address.ward.keyword")
        if clause:
            must_clauses.append(clause)

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
