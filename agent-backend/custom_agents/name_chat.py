from __future__ import annotations
import os
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load API Key
load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Thiếu OPENAI_API_KEY trong .env")

client = AsyncOpenAI(api_key=api_key)

INSTRUCTIONS = """
You are a conversation title generator.
Given a full conversation between a user and an assistant, generate a clear, concise, and relevant title that summarizes the main topic or purpose of the conversation.
The title should be short (3 to 8 words), descriptive, and specific enough to distinguish the conversation from others. Avoid generic titles like "Chat" or "Help Request." Focus on what the conversation is truly about.
Return only the title—no explanation, no punctuation beyond what's necessary.
"""


class NameAgent:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name

    async def run(self, conversation_input):
        """
        conversation_input: Có thể là String hoặc List các tin nhắn
        """
        # 1. Xử lý input đầu vào thành chuỗi văn bản
        input_text = ""
        if isinstance(conversation_input, list):
            for msg in conversation_input:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                input_text += f"{role}: {content}\n"
        else:
            input_text = str(conversation_input)

        # 2. Gọi OpenAI
        try:
            response = await client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": INSTRUCTIONS},
                    {"role": "user", "content": input_text},
                ],
            )
            title = (response.choices[0].message.content or "").strip()
            return title.replace('"', "").replace("'", "")
        except Exception as e:
            print(f"❌ Lỗi đặt tên chat: {e}")
            return "New Conversation"


# Khởi tạo Agent
name_agent = NameAgent()


# --- HÀM WRAPPER (Để giữ tương thích với code cũ gọi vào) ---
async def get_name(query):
    result = await name_agent.run(query)
    return result


# --- MAIN TEST ---
async def main():
    test_input = [
        {"role": "user", "content": "Cho tôi các bài đăng nhà phố mới nhất tại quận Hoàn Kiếm có 3 tầng"},
        {"role": "assistant", "content": "Dưới đây là danh sách nhà phố tại Hoàn Kiếm..."},
    ]

    print("⏳ Đang tạo tiêu đề...")
    result = await get_name(test_input)
    print(f"🏷️ Tiêu đề: {result}")


if __name__ == "__main__":
    asyncio.run(main())
