"""
Research coverage % của mỗi field trong 5 ES index BĐS (nhamatpho/nharieng/chungcu/bietthu/dat).

Khi nào chạy: sau khi crawler import data mới → check field nào coverage tăng/giảm
→ điều chỉnh DISTRIBUTION_LAYOUT trong frontend/app.py (Tier 1/2/3).

Chạy: `python scripts/research_common_fields.py` (từ root project).
"""
import os
import sys
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

# Windows cp1252 chết với tiếng Việt → ép utf-8 cho print
sys.stdout.reconfigure(encoding="utf-8")

# .env nằm ở agent-backend/, dùng path tuyệt đối để chạy được từ mọi CWD
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT / "agent-backend" / ".env")

es = Elasticsearch(
    [f"http://{os.getenv('ES_HOST', '127.0.0.1')}:{os.getenv('ES_PORT', '9200')}"],
    basic_auth=(os.getenv("ES_USER", "elastic"), os.getenv("ES_PASS", "")),
    request_timeout=30,
)

INDICES = {
    "Nhà mặt phố": "nhamatpho_index",
    "Nhà riêng":   "nharieng_index",
    "Chung cư":    "chungcu_index",
    "Biệt thự":    "bietthu_index",
    "Đất":         "dat_index",
}

# Bỏ skip để thấy TẤT CẢ field — chỉ loại các field hoàn toàn vô nghĩa
SKIP_FIELDS: set[str] = set()


def get_leaf_fields(mapping: dict, prefix: str = "") -> list[str]:
    """Đi qua mapping ES, trả về list dotted field name của các leaf fields."""
    out = []
    for name, body in mapping.items():
        full = f"{prefix}{name}"
        if "properties" in body:
            out.extend(get_leaf_fields(body["properties"], full + "."))
        else:
            out.append(full)
    return out


def field_coverage(index: str, field: str, total: int) -> tuple[int, float]:
    """Đếm số doc có field này (exists) → coverage % trên total."""
    try:
        r = es.count(index=index, query={"exists": {"field": field}})
        cnt = r["count"]
        return cnt, (cnt / total * 100 if total else 0)
    except Exception:
        return 0, 0.0


def main() -> None:
    print(f"Connecting to {os.getenv('ES_HOST')}:{os.getenv('ES_PORT')} ...")

    # 1. Lấy total docs & leaf fields per index
    all_fields_by_idx = {}
    totals = {}
    for label, idx in INDICES.items():
        try:
            c = es.count(index=idx)["count"]
            totals[idx] = c
            mp = es.indices.get_mapping(index=idx)
            # mapping body: {idx: {mappings: {properties: {...}}}}
            real_idx = next(iter(mp))
            props = mp[real_idx]["mappings"].get("properties", {})
            fields = [f for f in get_leaf_fields(props)
                      if not any(f.startswith(s) or f == s for s in SKIP_FIELDS)
                      and not f.endswith(".keyword")]
            all_fields_by_idx[idx] = fields
            print(f"  [{label}] {idx}: {c:,} docs, {len(fields)} leaf fields")
        except Exception as e:
            print(f"  [{label}] {idx} — LỖI: {e}")

    # 2. Union of all fields
    union_fields = set()
    for fs in all_fields_by_idx.values():
        union_fields.update(fs)
    print(f"\nTổng số field (union 5 index): {len(union_fields)}\n")

    # 3. Coverage matrix: field x index → %
    cov: dict[str, dict[str, float]] = defaultdict(dict)
    for label, idx in INDICES.items():
        if idx not in totals:
            continue
        total = totals[idx]
        for f in sorted(union_fields):
            _, pct = field_coverage(idx, f, total)
            cov[f][label] = pct

    # 4. Sort fields theo avg coverage giảm dần
    field_avg = []
    labels = list(INDICES.keys())
    for f, c in cov.items():
        avg = sum(c.get(l, 0) for l in labels) / len(labels)
        # số index có coverage >= 50%
        n_high = sum(1 for l in labels if c.get(l, 0) >= 50)
        field_avg.append((f, avg, n_high, c))
    field_avg.sort(key=lambda x: (-x[2], -x[1]))

    # 5. Print ALL fields
    print(f"{'Field':<38} {'Avg%':>6} {'>=50%':>6}  " + "  ".join(f"{l[:9]:>9}" for l in labels))
    print("-" * 120)
    for f, avg, n_high, c in field_avg:
        cells = "  ".join(f"{c.get(l, 0):>8.1f}%" for l in labels)
        print(f"{f:<38} {avg:>6.1f} {n_high:>6}  {cells}")


if __name__ == "__main__":
    main()
