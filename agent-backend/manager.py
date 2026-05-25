"""
ResearchManager — orchestrator của pipeline multi-agent:
  QueryRewriter → Planner → (SearchDB ↔ Judge | SearchWeb) → Writer → Zep memory

Mỗi turn user gửi câu hỏi đi qua manager.run(), kết quả về frontend dạng
RealEstateAdvice (findings + analysis + follow-up questions).
"""
from __future__ import annotations

import asyncio
import base64
import os
from typing import Any

from dotenv import load_dotenv, find_dotenv
from rich.console import Console

from custom_agents.planner import planner_agent, ToolSelection
from custom_agents.query_rewriter import query_rewriter
from custom_agents.search_db import SearchAgent
from custom_agents.search_web import search_agent
from custom_agents.writer import RealEstateAdvice, WriterAgent
from custom_agents.judge import evaluator
from printer import Printer

from zep_cloud.client import AsyncZep
from zep_cloud.types import Message
from zep_cloud.errors import NotFoundError

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

load_dotenv(dotenv_path=find_dotenv())

API_KEY = os.environ.get("ZEP_API_KEY")
# Fallback user_id cho Zep khi caller không truyền. main.py thường set per-chat
# (= "chat-{chat_id}") để memory isolate, fallback này chỉ là safety net.
DEFAULT_ZEP_USER_ID = os.environ.get("ZEP_USER_ID", "bds-default-user")

# Langfuse observability qua OTLP. Nếu thiếu env key thì exporter fail silent,
# pipeline vẫn chạy bình thường — chỉ mất trace trên dashboard.
langfuse_public = os.getenv("LANGFUSE_PUBLIC_KEY")
langfuse_secret = os.getenv("LANGFUSE_SECRET_KEY")
langfuse_host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
LANGFUSE_AUTH = base64.b64encode(
    f"{langfuse_public}:{langfuse_secret}".encode()
).decode()
otlp_endpoint = f"{langfuse_host}/api/public/otel"
otlp_headers = {"Authorization": f"Basic {LANGFUSE_AUTH}"}

# Guard chỉ setup 1 lần — uvicorn reload có thể import module nhiều lần.
if not trace.get_tracer_provider():
    trace_provider = TracerProvider()
    trace_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(
        otlp_endpoint=otlp_endpoint,
        otlp_headers=otlp_headers,
    )))
    trace.set_tracer_provider(trace_provider)

tracer = trace.get_tracer(__name__)


class ResearchManager:
    def __init__(self, use_judge: bool = True):
        self.console = Console()
        self.printer = Printer(self.console)
        self.client = AsyncZep(api_key=API_KEY)

        # use_judge=True bật vòng self-correction SearchDB ↔ Judge (≤2 vòng),
        # tăng chất lượng kết quả nhưng tốn thêm 1-2 LLM call mỗi turn.
        self.use_judge = use_judge
        self.db_agent = SearchAgent()
        self.writer_agent = WriterAgent()

    async def _ensure_thread(self, chat_id: str, user_id: str | None = None) -> None:
        """Zep Cloud SDK 3.x: thread phải tồn tại trước khi add_messages."""
        uid = user_id or DEFAULT_ZEP_USER_ID
        try:
            await self.client.user.get(user_id=uid)
        except NotFoundError:
            await self.client.user.add(user_id=uid)

        try:
            await self.client.thread.get(thread_id=chat_id)
        except NotFoundError:
            await self.client.thread.create(thread_id=chat_id, user_id=uid)

    async def add_memory(self, messages, chat_id, user_id: str | None = None):
        if not self.client or not chat_id:
            return

        try:
            zep_messages = []
            for m in messages:
                role = m.get("role")
                content = m.get("content")
                if role in ["user", "assistant"] and content:
                    text_content = str(content)
                    if len(text_content) > 4000:
                        text_content = text_content[:4000] + "\n...[Nội dung quá dài đã được cắt bớt để lưu vào bộ nhớ]..."
                    zep_messages.append(Message(role=role, content=text_content))

            if not zep_messages:
                return

            await self._ensure_thread(chat_id, user_id)
            await self.client.thread.add_messages(
                thread_id=chat_id,
                messages=zep_messages,
            )
            print(f"🧠 Đã lưu {len(zep_messages)} tin nhắn vào Zep (Thread: {chat_id})")

        except Exception as e:
            print(f"⚠️ Lỗi khi lưu Memory vào Zep: {e}")


    async def run(
        self,
        query: Any,
        user_id: str | None,
        session_id: str | None,
    ) -> tuple[RealEstateAdvice, str]:
        """Entry point chính: xử lý 1 turn user → trả (report, plaintext answer).

        query: hoặc string (legacy) hoặc list[dict{role, content, chat_id?}] (chuẩn từ main.py).
        """
        user_query = query if isinstance(query, str) else query[-1]["content"]
        with tracer.start_as_current_span("Real estate research trace") as span:
            span.set_attribute("langfuse.user.id", user_id or "")
            span.set_attribute("langfuse.session.id", session_id or "")

            self.printer.update_item(
                "trace_id",
                f"View trace: {langfuse_host}",
                is_done=True,
                hide_checkmark=True,
            )

            self.printer.update_item(
                "starting",
                "Starting research...",
                is_done=True,
                hide_checkmark=True,
            )

            posts = None
            findings = None

            # 0. REWRITE QUERY — kèm context các turn trước thành câu standalone,
            #    giúp planner & search_db không mất filter của câu trước.
            if isinstance(query, list) and len(query) > 1:
                rewritten = await query_rewriter.run(query)
                if rewritten and rewritten != user_query:
                    query = [*query[:-1], {**query[-1], "content": rewritten}]
                    user_query = rewritten
                    span.set_attribute("rewriter.applied", True)
                    span.set_attribute("rewriter.standalone", rewritten)

            # 1. QUYẾT ĐỊNH TOOL + PHÂN LOẠI INTENT (Planner)
            plan = await self._decide_tool(query)
            print(plan)

            # 1b. SHORT-CIRCUIT: chitchat / off_topic → skip search + writer
            if plan.intent in ("chitchat", "off_topic"):
                report = self._build_redirect_report(plan.intent, user_query)
                self.printer.update_item(
                    "redirect",
                    f"Phát hiện intent='{plan.intent}' — bỏ qua search, trả lời trực tiếp.",
                    is_done=True,
                    hide_checkmark=True,
                )
                self.printer.end()
                answer = report.real_estate_findings + "\n\n Phân tích:" + report.analytics_and_advice
                span.set_attribute("input.value", user_query)
                span.set_attribute("output.value", answer)
                span.set_attribute("planner.intent", plan.intent)
                return report, answer

            # 2. THỰC THI TOOL (chỉ chạy khi intent="bds_query")
            if "search_db" in plan.tools:
                posts = await self._perform_search_db(query)
            if "search_web" in plan.tools:
                findings = await self._perform_searches(query)

            # 3. VIẾT BÁO CÁO (Writer)
            report = await self._write_report(query, posts, findings)

            self.printer.end()
            answer = report.real_estate_findings + "\n\n Phân tích:" + report.analytics_and_advice
            span.set_attribute("input.value", user_query)
            span.set_attribute("output.value", answer)
            span.set_attribute("planner.intent", plan.intent)

        return report, answer

    async def _decide_tool(self, query) -> ToolSelection:
        user_query = query if type(query) == str else query[-1]["content"]
        with tracer.start_as_current_span("Decide tool") as span:

            result = await planner_agent.run(user_query)
            print(result)
            span.set_attribute("input.value", user_query)
            span.set_attribute("output.value", result.model_dump_json())
            span.set_attribute("planner.intent", result.intent)
            return result

    def _build_redirect_report(self, intent: str, user_query: str) -> RealEstateAdvice:
        """
        Tạo response cố định cho intent='chitchat' hoặc 'off_topic' — không gọi LLM,
        không tốn quota, không qua Writer/SearchDB.
        """
        sample_questions = [
            "Cho tôi danh sách chung cư dưới 3 tỷ ở quận Cầu Giấy.",
            "Giá đất nền tại huyện Hoài Đức hiện nay khoảng bao nhiêu?",
            "Có nhà phố nào ở Hà Nội diện tích trên 60m² dưới 5 tỷ không?",
        ]

        if intent == "chitchat":
            findings = (
                "Xin chào! Mình là trợ lý ảo chuyên tư vấn **bất động sản tại Việt Nam**.\n\n"
                "Mình có thể giúp bạn:\n"
                "- Tìm bài đăng nhà/đất/chung cư/biệt thự theo khu vực, giá, diện tích, số phòng...\n"
                "- Phân tích giá thị trường, gợi ý đầu tư.\n"
                "- Cập nhật thông tin dự án nổi bật."
            )
            advice = (
                "Bạn thử đặt một câu hỏi liên quan tới bất động sản nhé — "
                "mình có dữ liệu thật từ các sàn rao bán BĐS để tư vấn cụ thể."
            )
        else:  # off_topic
            findings = (
                f"Xin lỗi, câu hỏi **\"{user_query}\"** nằm ngoài phạm vi tư vấn của mình.\n\n"
                "Mình chỉ chuyên về **bất động sản tại Việt Nam** (mua/bán/thuê nhà, đất, "
                "chung cư, biệt thự; giá thị trường; dự án; phân tích đầu tư BĐS)."
            )
            advice = (
                "Bạn vui lòng đặt một câu hỏi liên quan tới bất động sản để mình có thể hỗ trợ. "
                "Tham khảo vài câu mẫu ở phần gợi ý bên dưới."
            )

        return RealEstateAdvice(
            real_estate_findings=findings,
            summary_real_estate_findings=findings[:2000],
            analytics_and_advice=advice,
            follow_up_questions=sample_questions,
        )
    


    async def _perform_search_db(self, query):
        """
        Hàm Search DB thông minh với 2 chế độ:
        1. Fast Mode (No Judge)
        2. Reasoning Mode (With Judge Loop)
        """
        user_query = query if type(query) == str else query[-1]["content"]
        
        with tracer.start_as_current_span("Search the database") as span:
            
            # --- TRƯỜNG HỢP 1: KHÔNG DÙNG JUDGE ---
            if not self.use_judge:
                self.printer.update_item("searching", "Searching DB (Fast Mode)...")
                try:
                    # Gọi trực tiếp Gemini Search Agent
                    posts = self.db_agent.run(user_query)
                    self.printer.mark_item_done("searching")
                    return posts
                except Exception as e:
                    print(f"❌ Search Error: {e}")
                    self.printer.mark_item_done("searching") # Nhớ mark done để tắt spinner
                    return []

            # --- TRƯỜNG HỢP 2: CÓ DÙNG JUDGE (SELF-CORRECTION) ---
            self.printer.update_item("searching", "Searching DB (Smart Mode)...")
            
            current_query = user_query
            final_posts = []
            max_retries = 2
            
            for attempt in range(max_retries):
                # Bước 1: Search
                try:
                    # Nếu là lần 2 trở đi, current_query đã kèm Feedback
                    posts = self.db_agent.run(current_query)
                except Exception as e:
                    print(f"Search Error: {e}")
                    posts = []

                # Bước 2: Judge
                self.printer.update_item("evaluating", f"Judging results (Attempt {attempt+1})...")
                
                # Gọi Evaluator
                try:
                    evaluation = evaluator.run(user_query, posts)
                    print(f"\n👨‍⚖️ JUDGE: {evaluation.score} | Reason: {evaluation.reason}")
                except Exception as e:
                    print(f"❌ Judge Error: {e}. Accepting results automatically.")
                    # Nếu Judge lỗi thì coi như Pass để không kẹt
                    self.printer.mark_item_done("evaluating")
                    self.printer.mark_item_done("searching")
                    return posts

                if evaluation.score == "pass":
                    self.printer.mark_item_done("evaluating")
                    self.printer.mark_item_done("searching")
                    return posts # Thành công -> Return ngay
                
                else: # needs_improvement
                    if attempt < max_retries - 1:
                        # Feedback loop: Sửa query để thử lại
                        self.printer.update_item("searching", f"Retrying with feedback...")
                        # Thêm feedback vào query để Gemini Search hiểu
                        current_query = f"Yêu cầu gốc: {user_query}. \nLƯU Ý ĐIỀU CHỈNH (FEEDBACK): {evaluation.feedback}"
                    else:
                        print("🛑 Hết lượt thử lại. Dùng kết quả hiện tại.")
                        final_posts = posts

            self.printer.mark_item_done("evaluating")
            self.printer.mark_item_done("searching")
        return final_posts
        

    async def _perform_searches(self, query: Any) -> list[str]:
        user_query = query if type(query) == str else query[-1]["content"]
        with tracer.start_as_current_span("Search the web") as span:
            self.printer.update_item("searching", "Searching...")
            num_completed = 0
            tasks = [asyncio.create_task(self._search(query))]
            results = []
            for task in asyncio.as_completed(tasks):
                result = await task
                if result is not None:
                    results.append(result)
                num_completed += 1
                self.printer.update_item(
                    "searching", f"Searching... {num_completed}/{len(tasks)} completed"
                )
            self.printer.mark_item_done("searching")
            span.set_attribute("input.value", user_query)
            span.set_attribute("output.value", str(results))
            return results

    async def _search(self, query: Any) -> str | None:
        input = query
        try:
            result = await search_agent.run(input)
            return str(result)
        except Exception:
            return None

    async def _write_report(
        self,
        query: Any,
        posts: Any = None,
        findings: list[str] | None = None,
    ) -> RealEstateAdvice:
        """Tổng hợp posts (DB) + findings (web) thành báo cáo có cấu trúc qua WriterAgent."""
        self.printer.update_item("writing", "Gemini is analyzing & writing report...")
        user_query = query if isinstance(query, str) else query[-1]["content"]
        
        # Format posts (DB) + findings (web) thành 1 khối text cho Writer prompt.
        # Format gọn để tiết kiệm token thay vì dump JSON thô.
        context_parts: list[str] = []

        if posts:
            posts_clean_str = ""
            if isinstance(posts, list):
                for idx, p in enumerate(posts, 1):
                    p_data = p if isinstance(p, dict) else p.__dict__
                    posts_clean_str += f"\n#{idx}. {p_data.get('title', 'N/A')}\n"
                    posts_clean_str += f"   - Giá: {p_data.get('price', 0):,} VNĐ\n"
                    posts_clean_str += f"   - Đ/C: {p_data.get('address', {})}\n"
                    posts_clean_str += f"   - Link: {p_data.get('link', '')}\n"
            else:
                posts_clean_str = str(posts)
            context_parts.append(f"=== DỮ LIỆU TỪ DATABASE ===\n{posts_clean_str}")
        else:
            context_parts.append("=== DỮ LIỆU TỪ DATABASE ===\n(Không tìm thấy dữ liệu trong DB)")

        if findings:
            findings_str = "\n".join(findings) if isinstance(findings, list) else str(findings)
            context_parts.append(f"=== DỮ LIỆU TỪ INTERNET ===\n{findings_str}")

        full_data_context = "\n\n".join(context_parts)

        try:
            result = await self.writer_agent.run(user_query, full_data_context)
            if result:
                self.printer.mark_item_done("writing")
                return result
            raise ValueError("Gemini trả về kết quả rỗng (None).")

        except Exception as e:
            print(f"❌ Writer Error: {e}")
            self.printer.mark_item_done("writing")


            # Fallback an toàn
            return RealEstateAdvice(
                real_estate_findings="Đã xảy ra lỗi trong quá trình tạo báo cáo.",
                summary_real_estate_findings="Hệ thống gặp sự cố kết nối với mô hình ngôn ngữ.",
                analytics_and_advice="Vui lòng thử lại sau giây lát.",
                follow_up_questions=[]
            )