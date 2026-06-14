"""JudgeAgent — self-correction loop cho SearchDB: pass/needs_improvement + feedback."""
import json
import os
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Thiếu OPENAI_API_KEY trong .env")

# Sync client — manager.py gọi `evaluator.run(...)` không await để giữ signature cũ.
client = OpenAI(api_key=api_key)


class EvaluationFeedback(BaseModel):
    score: Literal["pass", "needs_improvement"] = Field(
        description="Score 'pass' if at least 30% of listings match criteria (approx ±10%), else 'needs_improvement'."
    )
    feedback: str = Field(
        description="Concise instructions for the search agent to improve results (e.g., 'Search in Hoang Mai district instead')."
    )
    reason: str = Field(
        description="Explanation of why the score was given."
    )


JUDGE_INSTRUCTIONS = (
    "You will evaluate the list of real estate listings retrieved by the real estate search agent to determine if they meet the user's query. "
    "The search agent has searched based on criteria extracted from the user query. "
    "Note: The parameters `price`, `price_per_square`, and `square` are searched approximately within ±10%, meaning a listing is considered satisfactory if these fields are within ±10% of the user's requested values. Other parameters must match exactly (except `description`, which may match fuzzily). "
    "If at least 30% of the listings in the list satisfy the user's criteria (including the ±10% condition for `price`, `price_per_square`, and `square`), return a score of `pass`. Otherwise, return a score of `needs_improvement`. "
    "Provide concise feedback in English to the search agent. Offer brief suggestions based on the parameters above to improve search quality if needed. "
    "You also need to provide the reason why you score `pass` or `needs_improvement`. "
    "\n"
    "When the user's query is expressed in general, non-technical terms (e.g., \"find a home for 5 people,\" \"a house for young couples,\" etc.), first map that description to one or more appropriate filters:\n"
    "- **Occupancy-based** (\"for 5 people\" → `no_bedrooms`: 3–4, `estate_type`: likely \"nhà riêng\" or \"nhà phố\").\n"
    "- **Demographic-based** (\"young couple\" → `no_bedrooms`: 1–2, `price`: 2–3 billion VND, `estate_type`: \"chung cư\" or \"nhà riêng\" depending on the market).\n"
    "- **Budget-based** (\"budget of X to Y\" → `price`: average of X and Y, i.e., (X + Y) / 2; adjust `price_per_square` if needed).\n"
    "- **Lifestyle-based** (e.g., \"near schools\" → include relevant `district` or `ward`, or suggest adding a fuzzy `description` match).\n"
    "Explicitly state the assumed mapping in your feedback before evaluating. Use these mapped values as the criteria to check the returned listings."
)


class JudgeAgent:
    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name

    def run(self, user_query: str, posts_data) -> EvaluationFeedback:
        """Đánh giá kết quả search có khớp query không. Sync để giữ signature cũ."""
        # posts_data có thể là list[Post pydantic] hoặc list[dict] — serialize tất cả.
        if isinstance(posts_data, list):
            try:
                posts_str = json.dumps(
                    [p.__dict__ if hasattr(p, "__dict__") else p for p in posts_data],
                    ensure_ascii=False,
                    default=str,
                )
            except Exception:
                posts_str = str(posts_data)
        else:
            posts_str = str(posts_data)

        input_content = f"""
        USER QUERY: "{user_query}"

        RETRIEVED LISTINGS:
        {posts_str}

        Evaluate now based on the JSON schema.
        """

        try:
            response = client.beta.chat.completions.parse(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": JUDGE_INSTRUCTIONS},
                    {"role": "user", "content": input_content},
                ],
                response_format=EvaluationFeedback,
                temperature=0.1,
            )
            result = response.choices[0].message.parsed
            if result is None:
                raise ValueError("OpenAI trả về parsed=None")
            return result
        except Exception as e:
            print(f"❌ Judge Error: {e}")
            # Fallback "pass" để pipeline không kẹt ở vòng loop khi Judge LLM fail.
            return EvaluationFeedback(score="pass", feedback="Judge Error", reason="System fail")


evaluator = JudgeAgent()
