from __future__ import annotations
import os
import asyncio
from typing import Literal
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load API Key
load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Thiếu OPENAI_API_KEY trong .env")

client = AsyncOpenAI(api_key=api_key)


# 1. Define the structured output model
Intent = Literal["bds_query", "chitchat", "off_topic"]


class ToolSelection(BaseModel):
    intent: Intent
    tools: list[Literal["search_db", "search_web"]]


# 2. Define the prompt
PROMPT = """You are a helpful real estate assistant. Given a user query in Vietnamese, you must do TWO things:

(A) Classify the user's `intent` into ONE of three labels:
    - "bds_query": Câu hỏi liên quan đến bất động sản (mua/bán/thuê nhà, đất, chung cư, biệt thự; giá BĐS; dự án; khu vực; pháp lý nhà đất; phân tích thị trường BĐS; v.v.). Câu BĐS hơi mơ hồ (vd "tôi muốn mua nhà" không kèm tỉnh/giá) VẪN xếp vào "bds_query" — hệ thống có cơ chế tự hỏi lại sau.
    - "chitchat": Câu xã giao ngắn không phải BĐS nhưng không lạc đề (chào hỏi, cảm ơn, hỏi bot là ai, "bạn làm được gì"). KHÔNG dùng cho câu hỏi kiến thức ngoài BĐS.
    - "off_topic": Câu lạc đề rõ ràng, không liên quan BĐS và không phải chitchat (toán, thời tiết, lịch sử, code, dịch thuật, công thức nấu ăn, hỏi về ngôi sao/phim, v.v.).

(B) Chọn tools (CHỈ áp dụng khi intent="bds_query"; với "chitchat" và "off_topic" → trả tools=[]):
    - search_db: Retrieves real estate listings from the database relevant to the query.
    - search_web: Gathers general real estate information, such as price forecasts or project updates, based on the query.
    Khi intent="bds_query": chọn ít nhất 1 tool. Có thể chọn cả 2.

You cannot and must not use or call the WebSearch tool, only return the structured output.

Examples:

Input: Cho tôi các bài đăng chung cư mới nhất tại quận Thanh Xuân?
Output: {"intent": "bds_query", "tools": ["search_db"]}

Input: Tình hình dự án Vinhomes Smart City như thế nào rồi?
Output: {"intent": "bds_query", "tools": ["search_web"]}

Input: Lấy cho tôi các bài đăng nhà riêng có 2 phòng ngủ tại quận Thanh Xuân. Dự đoán giá nhà riêng tại khu vực Thanh Xuân trong 6 tháng tới.
Output: {"intent": "bds_query", "tools": ["search_db", "search_web"]}

Input: Tôi muốn mua nhà.
Output: {"intent": "bds_query", "tools": ["search_db"]}

Input: Xin chào
Output: {"intent": "chitchat", "tools": []}

Input: Cảm ơn bạn
Output: {"intent": "chitchat", "tools": []}

Input: Bạn làm được gì?
Output: {"intent": "chitchat", "tools": []}

Input: 1 + 1 bằng mấy?
Output: {"intent": "off_topic", "tools": []}

Input: Hôm nay thời tiết Hà Nội thế nào?
Output: {"intent": "off_topic", "tools": []}

Input: Dịch giúp tôi câu "good morning" sang tiếng Pháp.
Output: {"intent": "off_topic", "tools": []}
"""


# 3. CLASS PLANNER (OPENAI NATIVE - dùng structured output qua response_format)
class PlannerAgent:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name

    async def run(self, query: str) -> ToolSelection:
        try:
            response = await client.beta.chat.completions.parse(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": query},
                ],
                response_format=ToolSelection,
            )
            result = response.choices[0].message.parsed
            if result is None:
                raise ValueError("OpenAI trả về parsed=None")
            return result
        except Exception as e:
            print(f"❌ Lỗi Planner Agent: {e}")
            return ToolSelection(intent="bds_query", tools=["search_db"])


# Khởi tạo Agent (để các file khác import - giữ tên `planner_agent` như cũ)
planner_agent = PlannerAgent()


# --- MAIN TEST ---
async def main():
    print("⏳ Testing Planner Agent (OpenAI)")

    query = "Cho tôi các bài đăng nhà phố mới nhất tại quận Hoàn Kiếm có 3 tầng. Cho tôi thông tin về diện tích trung bình của các căn hộ Eco Park"
    print(f"User Query: {query}")

    result = await planner_agent.run(query)

    print("\n✅ Kết quả (JSON):")
    print(result.model_dump_json(indent=2))

    print("\n✅ Truy cập từng tool:")
    if result.tools:
        for tool in result.tools:
            print(f"- {tool}")


if __name__ == "__main__":
    asyncio.run(main())
