"""WebSearchAgent — search DuckDuckGo + tóm tắt cho query về thị trường / dự án BĐS."""
from __future__ import annotations
import asyncio
import json
import os

from ddgs import DDGS  # free search, không cần API key
from dotenv import load_dotenv
from openai import AsyncOpenAI


load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Thiếu OPENAI_API_KEY trong .env")

client = AsyncOpenAI(api_key=api_key)

INSTRUCTIONS = (
    "You are a real estate research assistant. Given a search term about real estate, you search the web "
    "for that term and produce a concise summary of results. Focus on real estate info like real estate posts, market trends, "
    "price forecasts, project updates, amenities around the property. Summary must be 2-3 paragraphs, under 300 words. Capture main points. "
    "Write succinctly, no complete sentences or good grammar needed. For someone synthesizing a real estate "
    "report, so focus on essence, ignore fluff. No extra commentary beyond summary. Just write about the query that you have the information about and ignore the query that you don't have the information about. You must response in Vietnamese."
)


def perform_web_search(query: str) -> str:
    """Search DDG top 5 → format `- Title / Link / Snippet` blocks cho LLM tóm tắt."""
    print(f"🌍 Đang tìm kiếm trên web: '{query}'...")
    try:
        results = DDGS().text(query, max_results=5)
        if not results:
            return "Không tìm thấy kết quả nào."
        formatted_results = ""
        for res in results:
            formatted_results += f"- Title: {res['title']}\n  Link: {res['href']}\n  Snippet: {res['body']}\n\n"
        return formatted_results
    except Exception as e:
        return f"Lỗi khi tìm kiếm: {str(e)}"


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "perform_web_search",
            "description": "Tìm kiếm thông tin trên internet về bất động sản, thị trường, giá cả, dự án.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Từ khóa hoặc câu hỏi tiếng Việt cần tìm kiếm.",
                    }
                },
                "required": ["query"],
            },
        },
    }
]


class WebSearchAgent:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name

    async def run(self, query) -> str:
        """Search web (DDG) + tóm tắt qua OpenAI 2-pass (tool call → summarize)."""
        # Caller có thể truyền string thuần, dict message, hoặc list messages → unwrap về text.
        input_text = ""
        if isinstance(query, str):
            input_text = query
        elif isinstance(query, dict):
            input_text = query.get("content", str(query))
        elif isinstance(query, list):
            if len(query) > 0 and isinstance(query[-1], dict):
                input_text = query[-1].get("content", "")
            else:
                input_text = str(query[-1]) if query else ""

        print(f"🔎 Web Agent nhận input: {input_text}")

        messages = [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": input_text},
        ]

        try:
            # Pass 1: model quyết định gọi tool hay trả thẳng.
            response = await client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            if not msg.tool_calls:
                return msg.content or ""

            # Thực thi tool calls và feed kết quả lại cho model.
            messages.append(msg.model_dump(exclude_none=True))
            for tc in msg.tool_calls:
                fname = tc.function.name
                try:
                    fargs = json.loads(tc.function.arguments)
                except Exception:
                    fargs = {}
                tool_result = perform_web_search(**fargs) if fname == "perform_web_search" else f"Unknown tool: {fname}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(tool_result),
                })

            # Pass 2: model tóm tắt search results thành câu trả lời cho user.
            response2 = await client.chat.completions.create(
                model=self.model_name,
                messages=messages,
            )
            return response2.choices[0].message.content or ""

        except Exception as e:
            print(f"❌ Lỗi Web Search Agent: {e}")
            return f"Không thể thực hiện tìm kiếm. Lỗi: {e}"


# Khởi tạo instance (giữ tên `search_agent`)
search_agent = WebSearchAgent()


# --- MAIN TEST ---
async def main():
    print("⏳ Đang test Web Search Agent (OpenAI)...")

    query = "Giá đất nền tại Đông Anh hiện nay biến động thế nào? Có nên đầu tư không?"
    result = await search_agent.run(query)

    print("\n✅ KẾT QUẢ TỔNG HỢP TỪ OPENAI:")
    print("-" * 60)
    print(result)
    print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
