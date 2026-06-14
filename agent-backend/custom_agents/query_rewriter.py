"""
Query Rewriter — biến câu hỏi cuối của user (có thể là follow-up phụ thuộc ngữ cảnh)
thành câu standalone tự đứng được, để Planner & SearchAgent xử lý chính xác.

Tận dụng CẢ assistant response trong history để resolve các refer:
  - "căn 2", "cái đầu tiên", "ngôi nhà thứ 3" → bám vào item cụ thể assistant đã liệt kê
  - "rẻ hơn thế thì sao" → biết "thế" là giá nào assistant vừa đề cập
  - "tại quận đó" → biết "quận đó" là gì user/assistant nói trước
"""
from __future__ import annotations
import os
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Thiếu OPENAI_API_KEY trong .env")

client = AsyncOpenAI(api_key=api_key)


class RewrittenQuery(BaseModel):
    standalone_query: str


PROMPT = """Bạn là Query Rewriter cho hệ thống tư vấn bất động sản tại Việt Nam.

NHIỆM VỤ: dựa trên lịch sử hội thoại (cả user VÀ assistant) + câu hỏi hiện tại,
viết lại câu hỏi hiện tại thành 1 câu STANDALONE — đầy đủ ngữ cảnh để Search Agent
xử lý được mà không cần đọc lại history.

NGUYÊN TẮC:
1. Giữ NGUYÊN ý định gốc của user, KHÔNG thêm điều kiện mới user chưa nói.
2. Bổ sung các FILTER user đã nói ở turn trước (province, district, loại BĐS, số phòng, diện tích, ngân sách).
3. KHAI THÁC assistant response để resolve các REFER:
   - "căn 2", "cái đầu tiên", "ngôi nhà thứ N" → tra danh sách assistant vừa liệt kê → lấy địa chỉ/giá/diện tích cụ thể.
   - "rẻ hơn thế", "cao hơn", "tương tự" → bám vào giá/diện tích assistant vừa nói.
   - "ở khu đó", "quận đó", "loại đó" → resolve thành tên thực tế trong history.
4. Nếu câu hiện tại ĐÃ standalone (đủ tỉnh + giá/loại, không có từ chỉ định ngữ cảnh) → giữ NGUYÊN, không thêm thừa.
5. Nếu câu hiện tại là chitchat/off-topic/không liên quan câu trước → trả NGUYÊN VĂN.
6. Output là 1 câu tiếng Việt tự nhiên, KHÔNG đánh dấu, KHÔNG giải thích.

VÍ DỤ:

History:
  user: Mua nhà mặt tiền tại Hà Nội quận Hoàn Kiếm
  assistant: Đây là một vài bài đăng phù hợp...
Câu hiện tại: Với ngân sách 50 tỷ thì mua được cái nào?
Standalone: Mua nhà mặt tiền tại Hà Nội quận Hoàn Kiếm với ngân sách 50 tỷ thì mua được cái nào?

History:
  user: Tìm chung cư 2 phòng ngủ ở Cầu Giấy
  assistant: Có các bài: 1. Căn The Pride 6.5 tỷ tại Hà Đông, 2. Căn Vinhomes Smart City 4.2 tỷ tại Nam Từ Liêm...
Câu hiện tại: Căn 2 còn không?
Standalone: Căn hộ Vinhomes Smart City 4.2 tỷ tại Nam Từ Liêm còn không?

History:
  user: Đất nền Hà Nội dưới 5 tỷ
  assistant: Có 10 bài, median 3.2 tỷ, đa phần ở Hoài Đức và Thường Tín...
Câu hiện tại: Rẻ hơn thế nữa thì sao?
Standalone: Đất nền Hà Nội dưới 3.2 tỷ, ưu tiên Hoài Đức và Thường Tín.

History:
  user: Tìm nhà phố Cầu Giấy
  assistant: Có bài 1, bài 2, bài 3...
Câu hiện tại: Còn ở quận đó loại biệt thự thì sao?
Standalone: Tìm biệt thự ở Cầu Giấy.

History:
  user: Xin chào
  assistant: Chào bạn, mình có thể giúp gì?
Câu hiện tại: Bạn làm được gì?
Standalone: Bạn làm được gì?

History: (rỗng)
Câu hiện tại: Mua nhà ở Đà Nẵng giá 3 tỷ
Standalone: Mua nhà ở Đà Nẵng giá 3 tỷ
"""

# Giới hạn truncate per role. User thường ngắn; assistant dài (markdown listings + analysis).
# 2000 chars assistant đủ chứa top 3-5 listings + summary mà không thổi token quá đáng.
MAX_USER_CHARS = 800
MAX_ASSISTANT_CHARS = 2000
# 8 turn = 16 message lịch sử, đủ context cho follow-up dài mà không quá $$ per call.
MAX_HISTORY_MESSAGES = 16


def _format_history(messages: list[dict]) -> str:
    """Lấy tối đa MAX_HISTORY_MESSAGES message gần nhất TRỪ câu hiện tại."""
    if not messages or len(messages) < 2:
        return "(rỗng)"
    history = messages[-(MAX_HISTORY_MESSAGES + 1):-1]
    lines = []
    for m in history:
        role = m.get("role", "")
        content = str(m.get("content", "")).strip()
        if not content or role not in ("user", "assistant"):
            continue
        limit = MAX_USER_CHARS if role == "user" else MAX_ASSISTANT_CHARS
        if len(content) > limit:
            content = content[:limit] + " ...[truncated]"
        lines.append(f"  {role}: {content}")
    return "\n".join(lines) if lines else "(rỗng)"


class QueryRewriter:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name

    async def run(self, messages: list[dict]) -> str:
        """messages = full conversation list, item cuối là câu user hiện tại."""
        if not messages:
            return ""
        current = str(messages[-1].get("content", "")).strip()
        if not current:
            return ""
        # Turn đầu hoặc rất ngắn (vd "ok", "ừ") không cần rewrite.
        if len(messages) < 2:
            return current

        history_text = _format_history(messages)
        # History rỗng (system prompt only) → skip.
        if history_text == "(rỗng)":
            return current

        user_input = f"History:\n{history_text}\n\nCâu hiện tại: {current}\nStandalone:"

        try:
            response = await client.beta.chat.completions.parse(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": user_input},
                ],
                response_format=RewrittenQuery,
                temperature=0.1,  # gần deterministic để rewrite ổn định
            )
            result = response.choices[0].message.parsed
            if result is None or not result.standalone_query.strip():
                return current
            rewritten = result.standalone_query.strip()
            print(f"📝 [REWRITE] '{current}' → '{rewritten}'")
            return rewritten
        except Exception as e:
            print(f"⚠️ Lỗi Query Rewriter: {e} — fallback dùng câu gốc")
            return current


query_rewriter = QueryRewriter()
