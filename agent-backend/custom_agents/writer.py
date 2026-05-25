"""WriterAgent — tổng hợp posts (DB) + findings (web) thành báo cáo có cấu trúc."""
import asyncio
import os
import re

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field


load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Thiếu OPENAI_API_KEY trong .env")

client = AsyncOpenAI(api_key=api_key)


class RealEstateAdvice(BaseModel):
    real_estate_findings: str = Field(description="A markdown-formatted summary of listings and web-sourced information.")
    summary_real_estate_findings: str = Field(description="A concise summary of real_estate_findings, excluding links, with a maximum of 2000 characters.")
    analytics_and_advice: str = Field(description="Detailed analysis and investment recommendations provided by the advisor.")
    follow_up_questions: list[str] = Field(description="Suggested follow-up research topics or questions.")


PROMPT = (
    "Bạn là một cố vấn đầu tư chuyên nghiệp chuyên về thị trường bất động sản. "
    "Bạn sẽ nhận được một câu hỏi đầu tư ban đầu cùng với dữ liệu sơ bộ.\n\n"
    "🚫 QUY TẮC TỐI THƯỢNG — KHÔNG ĐƯỢC BỊA SỐ LIỆU:\n"
    "- TUYỆT ĐỐI KHÔNG được bịa, đoán, làm tròn hay thay đổi: diện tích (square), giá (price), giá/m² (price_per_m2), "
    "địa chỉ (province/district/ward/full_address), link, số phòng ngủ/tầng/tắm, ngày đăng.\n"
    "- CHỈ được dùng EXACT số liệu xuất hiện trong DỮ LIỆU ĐẦU VÀO. Nếu data ghi `square=78` thì viết '78m²', "
    "KHÔNG được viết '100m²' dù số 100 trông tròn đẹp hơn.\n"
    "- Nếu một trường không có trong data → ghi 'Chưa có thông tin' hoặc bỏ qua, KHÔNG tự điền.\n"
    "- Nếu data có vẻ vô lý (vd: giá 10 tỷ cho 78m² = 128 triệu/m²) — VẪN ghi đúng số đó, không 'sửa lại cho hợp lý'. "
    "Đó là việc của user đánh giá, không phải của bạn.\n\n"
    "🎯 KIỂM TRA LOGIC TRƯỚC KHI KHUYÊN:\n"
    "- Nếu data trả về KHÔNG khớp yêu cầu user (sai tỉnh, vượt budget, sai loại) — phải NÊU RÕ trong "
    "'analytics_and_advice' rằng kết quả không phù hợp và GIẢI THÍCH tại sao, KHÔNG khuyên user mua.\n"
    "- Vd: user hỏi 'Hà Nội 30 triệu/m²' mà data có bài Bắc Ninh 128 triệu/m² → phải nói "
    "'Kết quả không khớp yêu cầu (sai tỉnh + giá cao gấp 4 lần). Đề nghị tìm lại với từ khóa chính xác hơn.'\n\n"
    "Nhiệm vụ của bạn là phân tích dữ liệu này, cung cấp một bản tóm tắt có cấu trúc, và đưa ra "
    "lời khuyên đầu tư dựa trên câu hỏi. Sử dụng chuyên môn để đánh giá cơ hội, so sánh, đánh giá rủi ro. "
    "Nếu có danh sách bất động sản, trích dẫn link và tóm tắt thông số ở định dạng markdown.\n\n"
    "Kết quả đầu ra BẮT BUỘC bao gồm các key:\n"
    "1. 'real_estate_findings': markdown tóm tắt tất cả phát hiện (danh sách + thông tin bên ngoài)\n"
    "2. 'summary_real_estate_findings': tóm tắt ngắn (không link), tối đa 2000 characters\n"
    "3. 'analytics_and_advice': phân tích chi tiết + lời khuyên cá nhân hóa\n"
    "4. 'follow_up_questions': danh sách câu hỏi tiếp theo\n\n"
    "Chỉ trả lời bằng tiếng Việt."
)


def clean_markdown_formatting(text: str) -> str:
    """Loại bỏ `**bold**` và đổi `* item` thành `- item` cho hợp Streamlit render."""
    if not isinstance(text, str):
        return text
    text = text.replace("**", "")
    text = re.sub(r"(^|\n)\s*\*\s+", r"\1- ", text)
    return text


class WriterAgent:
    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name

    async def run(self, query: str, data_context: str):
        print(f"✍️ Writer đang viết báo cáo với {self.model_name}...")

        user_content = f"CÂU HỎI: {query}\n\nDỮ LIỆU ĐẦU VÀO:\n{data_context}"

        try:
            response = await client.beta.chat.completions.parse(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format=RealEstateAdvice,
                temperature=0.3,
                max_tokens=8192,
            )

            result = response.choices[0].message.parsed
            if result is None:
                # Fallback: lấy raw text nếu parse fail
                raw_text = response.choices[0].message.content or ""
                print(f"❌ Parse fail. Raw head: {raw_text[:100]}...")
                return RealEstateAdvice(
                    real_estate_findings="Lỗi phân tích dữ liệu.",
                    summary_real_estate_findings="Error Parsing JSON",
                    analytics_and_advice=f"Raw Data: {raw_text[:2000]}...",
                    follow_up_questions=[],
                )

            # Làm sạch markdown (xóa **)
            return RealEstateAdvice(
                real_estate_findings=clean_markdown_formatting(result.real_estate_findings),
                summary_real_estate_findings=clean_markdown_formatting(result.summary_real_estate_findings),
                analytics_and_advice=clean_markdown_formatting(result.analytics_and_advice),
                follow_up_questions=result.follow_up_questions,
            )

        except Exception as e:
            print(f"❌ Lỗi API/System: {e}")
            return None


# --- CHẠY THỬ ---
async def main():
    mock_query = "tìm cho tôi nhà riêng 2 tầng 2 phòng ngủ ở huyện hoài đức giá dưới 5 tỷ. tư vấn cho tôi các căn phù hợp nếu như tôi có ô tô "

    mock_data = """
            #1
            🏠 Nhà 2 tầng dân xây an trai vân canh giá 4,5 tỷ về ở được ngay , dt 30 m2 gần đường ô tô ngã tư canh
            💰 4,500,000,000 VNĐ
            📍 Hoài Đức | Vân Canh
            🛠️  2 ngủ | 2 tầng | 30.0 m2
            📂 Nhà riêng
            🔗 Link: https://bds68.com.vn/ban-nha-rieng/ha-noi/hoai-duc/duong-an-trai/nha-2-tang-dan-xay-an-trai-van-canh-gia-45-ty-ve-o-duoc-ngay-dt-30m2-gan-duong-o-to-nga-tu-canh-pr28442765
            ----------------------------------------------------------------------
            #2
            🏠 Chỉ 4.5 tỷ sở hữu ngôi nhà 2 t , 2 pn , kiên cố , vân canh
            💰 4,500,000,000 VNĐ
            📍 Hoài Đức | Vân Canh
            🛠️  2 ngủ | 2 tầng | 31.0 m2
            📂 Nhà riêng
            🔗 Link: https://bds68.com.vn/ban-nha-rieng/ha-noi/hoai-duc/duong-an-trai/chi-45-ty-pr28879757
        """

    print(f"🚀 Đang chạy với model: gpt-4o-mini")
    agent = WriterAgent(model_name="gpt-4o-mini")

    result = await agent.run(mock_query, mock_data)

    if result:
        print("\n✅ KẾT QUẢ PHÂN TÍCH:")
        print("=" * 60)
        print("📝 TÓM TẮT DỮ LIỆU TÌM ĐƯỢC:")
        print(result.summary_real_estate_findings)
        print("-" * 60)
        print(f"💡 LỜI KHUYÊN (Độ dài: {len(result.analytics_and_advice)} ký tự):")
        print(result.analytics_and_advice)
        print("-" * 60)
        print("❓ CÂU HỎI TIẾP THEO:")
        for q in result.follow_up_questions:
            print(f"  - {q}")


if __name__ == "__main__":
    asyncio.run(main())
