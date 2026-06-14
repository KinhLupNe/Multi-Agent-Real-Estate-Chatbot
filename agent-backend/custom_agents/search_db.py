"""
SearchAgent — biến câu hỏi tự nhiên của user thành ES query qua OpenAI function calling.

Có 2 function tools:
  - search_posts        : LOOSE (range ±20%, text-fallback địa điểm) — cho query mơ hồ
  - search_posts_strict : STRICT (range ±10%, terms match) — cho query cụ thể (≥2 filter)

Strategy: ưu tiên strict, fallback sang loose nếu strict trả rỗng.
Gọi SYNC (manager dùng `self.db_agent.run(...)` không await).
"""
from __future__ import annotations

import json
import os
import sys
from typing import List

from dotenv import load_dotenv
from openai import OpenAI

from .elasticsearch_queries import search_posts, search_posts_strict
from .agent_type import Post, Address, ContactInfo, ExtraInfos


load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Thiếu OPENAI_API_KEY trong .env")

client = OpenAI(api_key=api_key)


def map_es_result_to_post(result: dict) -> Post:
    """Convert raw ES doc → Pydantic Post — chuẩn hóa null + ép kiểu cho writer dùng."""
    addr = result.get("address", {}) or {}
    contact = result.get("contact_info", {}) or {}

    raw_post_id = result.get("post_id")
    safe_post_id = str(raw_post_id) if raw_post_id is not None else ""

    raw_id = result.get("id")
    safe_id = str(raw_id) if raw_id is not None else None

    safe_ward = addr.get("ward")
    if safe_ward is None:
        safe_ward = ""

    safe_price = result.get("price") or 0.0
    safe_price_m2 = result.get("price/square") or 0.0
    safe_square = result.get("square") or 0.0

    return Post(
        address=Address(
            district=result.get("district"),
            full_address=addr.get("full_address"),
            province=result.get("province"),
            ward=safe_ward,
        ),
        contact_info=ContactInfo(
            name=contact.get("name"), phone=contact.get("phone", [])
        ),
        description=result.get("description"),
        estate_type=result.get("estate_type"),
        extra_infos=ExtraInfos(
            direction=result.get("direction"),
            front_face=result.get("front_face"),
            front_road=result.get("front_road"),
            no_bathrooms=result.get("no_bathrooms"),
            no_bedrooms=result.get("no_bedrooms"),
            no_floors=result.get("no_floors"),
            ultilization_square=result.get("ultilization_square"),
            yo_construction=result.get("yo_construction"),
            legal=result.get("legal"),
        ),
        id=safe_id,
        link=result.get("link"),
        post_date=result.get("post_date"),
        created_at=result.get("created_at"),
        post_id=safe_post_id,
        price=safe_price,
        price_per_square=safe_price_m2,
        square=safe_square,
        title=result.get("title"),
    )


# JSON schema cho OpenAI tool calling — phải định nghĩa thủ công (Gemini SDK tự
# sinh từ Python function signature; OpenAI thì cần schema explicit).
# Mirror đúng signature của search_posts / search_posts_strict trong elasticsearch_queries.
SEARCH_PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "estate_type": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "nhà mặt phố", "nhà phố",
                    "nhà riêng", "nhà trọ", "phòng trọ",
                    "chung cư", "tập thể", "căn hộ",
                    "biệt thự", "liền kề", "đất biệt thự",
                    "đất", "đất nền", "đất mặt phố", "đất riêng", "đất trang trại",
                    "kho xưởng", "nhà xưởng", "thuê kho",
                    "văn phòng", "cửa hàng", "nhà đất khác",
                ],
            },
            "description": "Danh sách các loại bất động sản (chỉ map khi user nói rõ).",
        },
        "is_latest_posted": {"type": "boolean", "description": "Lấy bài đăng mới nhất."},
        "is_latest_created": {"type": "boolean", "description": "Lấy bài tạo mới nhất."},
        "province": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tỉnh/Thành phố (vd: ['Hà Nội', 'Hồ Chí Minh']).",
        },
        "district": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Quận/Huyện/Thị xã. GIỮ tiền tố 'Quận'/'Huyện' (vd: ['Quận 1', 'Hoài Đức']).",
        },
        "ward": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Phường/Xã/Thị trấn.",
        },
        "front_face": {"type": "number", "description": "Mặt tiền (m)."},
        "front_road": {"type": "number", "description": "Đường trước nhà (m)."},
        "no_bathrooms": {"type": "integer", "description": "Số phòng tắm."},
        "no_bedrooms": {"type": "integer", "description": "Số phòng ngủ."},
        "no_floors": {"type": "integer", "description": "Số tầng."},
        "ultilization_square": {"type": "number", "description": "Diện tích sử dụng (m²)."},
        "price": {"type": "number", "description": "Mức giá khoảng (VNĐ) — dùng khi user nói 'khoảng', 'tầm'."},
        "min_price": {"type": "number", "description": "Giá tối thiểu (VNĐ) — dùng khi user nói 'trên', 'từ'."},
        "max_price": {"type": "number", "description": "Giá tối đa (VNĐ) — dùng khi user nói 'dưới', 'tối đa'."},
        "price_per_square": {"type": "number", "description": "Giá trên mét vuông."},
        "square": {"type": "number", "description": "Diện tích (m²)."},
        "description": {"type": "string", "description": "Từ khóa mô tả tự do (fuzzy match)."},
    },
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_posts",
            "description": (
                "Tìm bài đăng BĐS với tiêu chí LINH HOẠT (range ±20% cho price/square, "
                "text-fallback cho địa điểm). Phù hợp với query MƠ HỒ hoặc chỉ có 1-2 ràng buộc."
            ),
            "parameters": SEARCH_PARAMS_SCHEMA,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_posts_strict",
            "description": (
                "Tìm bài đăng BĐS với tiêu chí NGHIÊM NGẶT (tất cả phải khớp, range ±10% cho price). "
                "Phù hợp với query CỤ THỂ có >= 2 ràng buộc rõ ràng (vd: loại + tỉnh + giá)."
            ),
            "parameters": SEARCH_PARAMS_SCHEMA,
        },
    },
]


class SearchAgent:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name

        self.system_instruction = """
        Bạn là chuyên gia BĐS. Nhiệm vụ: Query dữ liệu chính xác từ Database.

        QUY TẮC TỐI THƯỢNG (BẮT BUỘC):
        0. LUÔN gọi function khi câu hỏi có BẤT KỲ dấu hiệu BĐS:
           - Có tên tỉnh/thành/quận/huyện/phường/đường -> gọi function.
           - Có từ "nhà", "đất", "căn hộ", "chung cư", "biệt thự", "phòng trọ",
             "kho", "văn phòng", "cửa hàng" -> gọi function.
           - Có giá ("tỷ", "tỉ", "triệu", "tr"), diện tích ("m2", "m²") -> gọi function.
           - Có số phòng ngủ, tầng, hướng -> gọi function.
           * KHÔNG được trả lời bằng text khi câu hỏi liên quan BĐS — phải gọi function.
           * Nếu thiếu thông tin, vẫn gọi function với tham số đoán được, để trống phần còn lại.

        1. Xử lý GIÁ TỔNG (price/min_price/max_price):
           - "tỷ", "tỉ" -> nhân 1,000,000,000.
           - "triệu", "tr" -> nhân 1,000,000.
           - "dưới X", "nhỏ hơn X", "tối đa X" -> max_price=X.
           - "trên X", "lớn hơn X", "từ X" -> min_price=X.
           - "từ A đến B" -> min_price=A, max_price=B.
           - "khoảng X", "tầm X", "~X" -> price=X (KHÔNG dùng min/max).
           - Khi user chỉ nói 1 con số ("5 tỷ"), dùng price, KHÔNG dùng min/max.

        2. Xử lý GIÁ TRÊN MÉT VUÔNG (price_per_square) — RẤT QUAN TRỌNG:
           - Bất cứ khi nào user nói "X triệu/m²", "X triệu một mét", "X triệu mỗi m2",
             "giá/m² là X", "đơn giá X triệu" -> BẮT BUỘC pass price_per_square=X*1,000,000.
             VD: "đất 30 triệu/m2" -> price_per_square=30000000.
             VD: "căn hộ 50tr/m²" -> price_per_square=50000000.
           - KHÔNG được nhầm với price (giá tổng). "30 triệu/m²" khác hẳn "30 triệu".
           - Nếu user nói BOTH giá tổng VÀ giá/m² -> pass cả 2.

        3. Xử lý DIỆN TÍCH (square):
           - "50m2", "50 mét vuông" -> square=50.
           - "trên 80m2", "dưới 100m2" -> dùng square và để model range tự nhiên.

        4. Xử lý ĐỊA ĐIỂM:
           - TỈNH/THÀNH -> province (list). VD: "Đất nền ở Đà Nẵng" -> province=["Đà Nẵng"].
           - QUẬN/HUYỆN -> district (list). Giữ NGUYÊN cả tiền tố "Quận"/"Huyện":
             VD: "Nhà ở Quận 1" -> district=["Quận 1"]; "huyện Hoài Đức" -> district=["Hoài Đức"].
           - PHƯỜNG/XÃ -> ward (list). VD: "phường Bến Nghé" -> ward=["Bến Nghé"].

        5. Xử lý SỐ PHÒNG / TẦNG:
           - "một phòng ngủ", "1 phòng ngủ", "1PN" -> no_bedrooms=1.
           - "hai tầng", "2 tầng" -> no_floors=2.
           - "có 2 wc", "2 phòng tắm" -> no_bathrooms=2.

        6. Xử lý LOẠI BĐS (estate_type) — chỉ map khi user nói rõ:
           - Các loại chuẩn: "nhà mặt phố", "nhà phố", "nhà riêng", "nhà trọ",
             "phòng trọ", "chung cư", "tập thể", "căn hộ", "biệt thự", "liền kề",
             "đất biệt thự", "đất", "đất mặt phố", "đất riêng", "đất trang trại",
             "kho xưởng", "thuê kho", "văn phòng", "cửa hàng", "nhà đất khác".
           - "đất mặt phố" -> ["đất mặt phố"] (KHÔNG tách thành ["đất","nhà mặt phố"]).
           - Nếu user KHÔNG nói loại, để trống estate_type (đừng tự đoán).

        7. CHIẾN THUẬT chọn function — ƯU TIÊN STRICT:
           - MẶC ĐỊNH dùng `search_posts_strict` để filter chính xác.
           - Đặc biệt BẮT BUỘC dùng strict khi user nói RÕ:
             * province + giá tổng cụ thể, HOẶC
             * province + price_per_square, HOẶC
             * province + estate_type.
           - CHỈ dùng `search_posts` (loose, range ±20%) khi query QUÁ mơ hồ:
             chỉ có 1 từ khóa duy nhất, không có giá/địa điểm/loại cụ thể.
           - KHÔNG được từ chối gọi function chỉ vì query mơ hồ.

        VÍ DỤ:
        - "Đất Hà Nội khoảng 30 triệu/m2"
          → search_posts_strict(estate_type=["đất"], province=["Hà Nội"], price_per_square=30000000)
        - "Chung cư 3PN ở Cầu Giấy giá 5 tỷ"
          → search_posts_strict(estate_type=["chung cư"], province=["Hà Nội"], district=["Cầu Giấy"], no_bedrooms=3, price=5000000000)
        - "Tìm nhà đất ở Đà Nẵng"
          → search_posts(province=["Đà Nẵng"])  ← chỉ có province, dùng loose
        """

    def run(self, query: str) -> List[Post]:
        print(f"User: {query}")

        try:
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_instruction},
                    {"role": "user", "content": query},
                ],
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
            )
        except Exception as e:
            print(f"Lỗi API: {e}")
            return []

        try:
            msg = response.choices[0].message
            if not msg.tool_calls:
                print("⚠️ Model không gọi function — trả về text:", (msg.content or "")[:200])
                return []

            tc = msg.tool_calls[0]
            fname = tc.function.name
            try:
                fargs = json.loads(tc.function.arguments)
            except Exception as e:
                print(f"❌ Parse arguments lỗi: {e}")
                return []

            print(f"🤖 OpenAI gọi hàm: {fname}")
            print(f"📦 Tham số gốc: {fargs}")

            # Sanitize args: model có thể trả float thay vì int, district có prefix "Quận"...
            clean_args = self._sanitize_args(fargs)
            print(f"✨ Tham số đã xử lý: {clean_args}")

            raw_results = []
            try:
                if fname == "search_posts":
                    raw_results = search_posts(**clean_args)
                elif fname == "search_posts_strict":
                    raw_results = search_posts_strict(**clean_args)
                    # Strict trả rỗng → fallback loose để không bỏ sót khi tiêu chí quá hẹp.
                    if not raw_results:
                        print("Strict rỗng, fallback sang thường...")
                        raw_results = search_posts(**clean_args)
            except Exception as e:
                print(f"Lỗi thực thi hàm search: {e}")
                return []

            print(f"-> DB trả về {len(raw_results)} kết quả.")

            result_posts = []
            for item in raw_results:
                try:
                    result_posts.append(map_es_result_to_post(item))
                except Exception:
                    continue
            return result_posts

        except Exception as e:
            print(f"Lỗi xử lý response: {e}")
            return []

    def _sanitize_args(self, args: dict) -> dict:
        """Chuẩn hóa tham số do LLM trả về cho match được ES schema.

        Cần thiết vì LLM hay trả float cho số đếm, string cho list, và district
        kèm prefix "Quận"/"Huyện" mà ES `.keyword` không match được.
        """
        new_args = dict(args)

        # LLM hay trả "2.0" cho số phòng → ép int để ES term query đúng.
        for field in ("no_bedrooms", "no_bathrooms", "no_floors"):
            if field in new_args and new_args[field] is not None:
                try:
                    new_args[field] = int(new_args[field])
                except Exception:
                    pass

        # Địa điểm + estate_type phải là list (ES `terms` query yêu cầu list).
        for list_field in ("province", "district", "ward", "estate_type"):
            if list_field in new_args:
                raw = new_args[list_field]
                if raw is None:
                    new_args.pop(list_field)
                    continue
                if isinstance(raw, str):
                    new_args[list_field] = [raw]
                else:
                    new_args[list_field] = [str(item) for item in raw]

        # ES `district.keyword` lưu "Hoài Đức" không có prefix → strip để match.
        if "district" in new_args and new_args["district"]:
            new_args["district"] = [
                d.replace("Quận ", "").replace("Huyện ", "").strip()
                for d in new_args["district"]
            ]

        # Ép float cho mọi trường số (LLM có thể trả int khi user nói "5 tỷ" → 5_000_000_000).
        for p_field in (
            "price", "min_price", "max_price",
            "square", "front_face", "front_road",
            "price_per_square", "ultilization_square",
        ):
            if p_field in new_args and new_args[p_field] is not None:
                try:
                    new_args[p_field] = float(new_args[p_field])
                except Exception:
                    pass

        return new_args


# --- MAIN TEST (INTERACTIVE MODE) ---
if __name__ == "__main__":
    try:
        if sys.stdin.encoding and sys.stdin.encoding.lower() != "utf-8":
            sys.stdin.reconfigure(encoding="utf-8")
        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        print("⏳ Đang khởi tạo Search Agent (OpenAI)...")
        agent = SearchAgent()
        print("\n" + "=" * 70)
        print("🤖  OPENAI REAL ESTATE AGENT - CHẾ ĐỘ TƯƠNG TÁC")
        print("=" * 70)

        while True:
            try:
                query = input("\n💬 Nhập câu hỏi: ").strip()
            except UnicodeDecodeError:
                print("❌ Lỗi encoding. Hãy thử: set PYTHONIOENCODING=utf-8")
                continue

            if query.lower() in ["exit", "quit", "q"]:
                print("👋 Tạm biệt!")
                break

            if not query:
                continue

            try:
                query = query.encode("utf-8", "ignore").decode("utf-8")
            except Exception:
                pass

            print(f"🚀 Đang xử lý: '{query}'")

            try:
                posts = agent.run(query)

                print(f"\n✅ TÌM THẤY: {len(posts)} bài đăng.")
                print("-" * 70)

                if not posts:
                    print("📭 Không có kết quả phù hợp.")
                    continue

                for i, p in enumerate(posts, 1):
                    try:
                        bedrooms = p.extra_infos.no_bedrooms if p.extra_infos else "N/A"
                        floors = p.extra_infos.no_floors if p.extra_infos else "N/A"
                    except Exception:
                        bedrooms = "N/A"
                        floors = "N/A"

                    price_str = f"{p.price:,.0f}" if p.price else "Thỏa thuận"

                    print(f"#{i}")
                    print(f"   🏠 {p.title}")
                    print(f"   💰 {price_str} VNĐ")
                    print(f"   📍 {p.address.province} | {p.address.district} | {p.address.ward}")
                    print(f"   🛠️  {bedrooms} ngủ | {floors} tầng | {p.square} m2")
                    print(f"   📂 {p.estate_type}")
                    print(f"   🔗 Link: {p.link}")
                    print("-" * 70)

            except Exception as e:
                print(f"❌ LỖI XỬ LÝ: {e}")

    except KeyboardInterrupt:
        print("\n\n👋 Đã dừng.")
