import glob
import json
import os
import subprocess
import re
from multiprocessing import Pool
from tqdm import tqdm

# ===============================
# Cấu hình Crawler chạy nhiều spider
# ===============================
MIN_PAGE = 1
MAX_PAGE = 50

# Skip mọi bài đăng có post_date < MIN_DATE. Đặt "" hoặc None để không filter.
MIN_DATE = "2025-01-01"

# Tự động truy vấn cổng NodePort của Kafka external listener từ K8s
def get_kafka_bootstrap_servers():
    env_val = os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
    if env_val:
        return env_val

    try:
        # Chạy kubectl để lấy nodePort của service bootstrap ngoài
        res = subprocess.run(
            ["kubectl", "get", "svc", "my-cluster-kafka-external-bootstrap", "-n", "kafka", "-o", "jsonpath={.spec.ports[0].nodePort}"],
            capture_output=True, text=True, check=True, shell=(os.name == "nt")
        )
        port = res.stdout.strip()
        if port.isdigit():
            return f"127.0.0.1:{port}"
    except Exception as e:
        print(f"⚠️ Không truy vấn được cổng Kafka từ K8s, dùng fallback: {e}")
        pass

    return "127.0.0.1:31608"  # Cổng mặc định của Kafka external bootstrap nodeport


KAFKA_BOOTSTRAP_SERVERS = get_kafka_bootstrap_servers()

# REVERSE=True: chạy ngược thứ tự task — ưu tiên bds68_spider trước bds_spider,
# trong mỗi spider chạy estate_type idx LỚN trước (khác → đất → biệt thự → ... → nhà mặt phố).
# Dùng khi crawl trước đó dừng giữa chừng — bắt đầu từ phần CHƯA crawl (idx cao = dat/khac).
# CLI: `python run_new.py --reverse` cũng bật được flag này.
REVERSE = True

# Mỗi spider tự khai báo các estate_type idx nó hỗ trợ + topic Kafka tương ứng.
# Comment dòng nào không muốn crawl để skip.
SPIDER_CONFIGS = [
    {
        "name": "bds_spider",  # site bds.com.vn — chỉ 4 loại
        "estate_type_to_topic": {
            0: "nhamatpho",
            1: "nharieng",
            2: "chungcu",
            3: "bietthu",
        },
    },
    {
        "name": "bds68_spider",  # site bds68.com.vn — 10 loại (mua bán)
        "estate_type_to_topic": {
            0: "nhamatpho",
            1: "nharieng",
            2: "chungcu",
            3: "bietthu",
            4: "dat",  # đất biệt thự
            5: "dat",  # đất mặt phố
            6: "dat",  # đất nền
            7: "dat",  # đất trang trại
            8: "khac",  # kho xưởng
            9: "khac",  # nhà đất khác
        },
    },
]

PROVINCES_FILE = os.path.join(os.path.dirname(__file__), "provinces.json")
OUTPUT_ROOT_DIR = "crawled_data"
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)


def clear_old_logs():
    """Xoá toàn bộ file .log trong LOGS_DIR trước mỗi lần crawl."""
    old_logs = glob.glob(os.path.join(LOGS_DIR, "*.log"))
    for f in old_logs:
        try:
            os.remove(f)
        except OSError:
            pass
    if old_logs:
        print(f"🧹 Đã xoá {len(old_logs)} file log cũ trong {LOGS_DIR}")


# Các pattern lỗi cần nhận diện (regex, case-insensitive)
ERROR_PATTERNS = {
    "kafka_connect": [
        r"FAIL\|rdkafka",
        r"Connection refused",
        r"Broker: No nodes available",
        r"Failed to send message to Kafka",
        r"kafka\.errors\.NoBrokersAvailable",
    ],
    "http_block": [
        r"\b403 Forbidden\b",
        r"\b429 Too Many Requests\b",
        r"Just a moment\.\.\.",  # Cloudflare challenge page title
        r"cf-chl-bypass",  # Cloudflare challenge cookie
        r"captcha required",
    ],
    "site_changed": [
        r"AttributeError.*'NoneType' object has no attribute",
        r"IndexError: list index out of range",
    ],
    "deps_missing": [
        r"^\s*ModuleNotFoundError",
        r"^\s*ImportError",
    ],
    "spider_not_found": [
        r"Spider not found",
        r"KeyError.*spider",
    ],
}


def detect_error(stderr_text):
    """Trả về (error_type, matched_pattern) hoặc (None, None) nếu không match.

    Ưu tiên check deps_missing trước http_block để tránh tên module
    (vd: scrapy_cloudflare_middleware) bị match nhầm là HTTP block.
    """
    priority = [
        "deps_missing",
        "spider_not_found",
        "kafka_connect",
        "site_changed",
        "http_block",
    ]
    for err_type in priority:
        for pat in ERROR_PATTERNS.get(err_type, []):
            m = re.search(pat, stderr_text, re.IGNORECASE | re.MULTILINE)
            if m:
                return err_type, m.group(0)
    return None, None


def save_log(spider_name, slug, kafka_topic, stderr_text, stdout_text):
    """Lưu full log vào file để debug sau."""
    fname = f"{spider_name}_{slug}_{kafka_topic}.log"
    fpath = os.path.join(LOGS_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("=== STDERR ===\n")
        f.write(stderr_text or "")
        f.write("\n\n=== STDOUT ===\n")
        f.write(stdout_text or "")
    return fpath


def run_crawl_task(task_args):
    province_name = task_args["name"]
    slug = task_args["slug"]
    spider_name = task_args["spider_name"]
    estate_type_idx = task_args["estate_type_idx"]
    kafka_topic = task_args["kafka_topic"]
    tag = f"{spider_name} | {province_name} | idx={estate_type_idx} -> {kafka_topic}"

    output_dir = os.path.join(OUTPUT_ROOT_DIR, slug)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{spider_name}_{slug}_{kafka_topic}.json")

    cmd = [
        "scrapy",
        "crawl",
        spider_name,
        "-a",
        f"min_page={MIN_PAGE}",
        "-a",
        f"max_page={MAX_PAGE}",
        "-a",
        f"province={slug}",
        "-a",
        f"estate_type={estate_type_idx}",
    ]
    if MIN_DATE:
        cmd.extend(["-a", f"min_date={MIN_DATE}"])
    cmd.extend(
        [
            "-O",
            output_path,
            "-s",
            "DOWNLOAD_DELAY=1",
            "-s",
            f"KAFKA_BOOTSTRAP_SERVERS={KAFKA_BOOTSTRAP_SERVERS}",
            "-s",
            f"KAFKA_TOPIC={kafka_topic}",
        ]
    )

    try:
        # shell=False để chạy được cả Windows lẫn Linux (container Airflow).
        # Với shell=True, Linux chỉ chạy mỗi "scrapy" và bỏ hết args → vỡ.
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=os.environ.copy()
        )

        # 1. Đếm số message Kafka đã delivered thực tế (từ callback _delivery_report).
        #    Đây là số chính xác — item_scraped_count chỉ là số item produce vào queue,
        #    không đảm bảo broker đã nhận.
        m_ok = re.search(r"'kafka/delivery_success': (\d+)", result.stderr)
        m_fail = re.search(r"'kafka/delivery_failed': (\d+)", result.stderr)
        m_scraped = re.search(r"'item_scraped_count': (\d+)", result.stderr)
        delivered = int(m_ok.group(1)) if m_ok else 0
        failed = int(m_fail.group(1)) if m_fail else 0
        scraped = int(m_scraped.group(1)) if m_scraped else 0

        if delivered > 0:
            extra = f" | scraped={scraped}" if scraped != delivered else ""
            warn = f" ⚠️ {failed} delivery FAILED" if failed > 0 else ""
            return {
                "status": "success",
                "count": delivered,
                "msg": f"✅ {tag} | {delivered} mess Kafka{extra}{warn}",
            }

        # Spider scrape ra tin nhưng 0 message delivered → Kafka lỗi delivery
        if scraped > 0:
            log_path = save_log(
                spider_name, slug, kafka_topic, result.stderr, result.stdout
            )
            return {
                "status": "kafka_delivery_failed",
                "count": 0,
                "msg": f"❌ Scrape {scraped} tin nhưng 0 message vào Kafka (failed={failed})\n   ↳ {tag}\n   ↳ Log: {log_path}",
            }

        # 2. Scrape 0 tin → check error pattern để biết lý do
        err_type, err_match = detect_error(result.stderr)
        if err_type:
            log_path = save_log(
                spider_name, slug, kafka_topic, result.stderr, result.stdout
            )
            msg_map = {
                "kafka_connect": f"❌ KAFKA không kết nối ({KAFKA_BOOTSTRAP_SERVERS})",
                "http_block": "❌ HTTP bị chặn (403/429/Cloudflare/Captcha)",
                "site_changed": "❌ Site đổi cấu trúc HTML (selector fail)",
                "deps_missing": "❌ Thiếu Python package",
                "spider_not_found": f"❌ Spider '{spider_name}' không tồn tại",
            }
            return {
                "status": err_type,
                "count": 0,
                "msg": f"{msg_map[err_type]}\n   ↳ {tag}\n   ↳ Match: {err_match}\n   ↳ Log: {log_path}",
            }

        # 3. Returncode != 0 nhưng không match pattern → lỗi không xác định
        if result.returncode != 0:
            log_path = save_log(
                spider_name, slug, kafka_topic, result.stderr, result.stdout
            )
            tail = (
                "\n      ".join(result.stderr.splitlines()[-5:])
                if result.stderr
                else "(empty stderr)"
            )
            return {
                "status": "unknown_error",
                "count": 0,
                "msg": f"❌ Scrapy exit code {result.returncode}\n   ↳ {tag}\n   ↳ Log: {log_path}\n   ↳ Tail stderr:\n      {tail}",
            }

        # 4. Returncode 0 + scraped_count 0 → redirect/hết tin (province không có data)
        return {
            "status": "warning",
            "count": 0,
            "msg": f"⚠️ Không có tin (redirect/hết tin)\n   ↳ {tag}",
        }

    except FileNotFoundError:
        return {
            "status": "scrapy_not_installed",
            "count": 0,
            "msg": f"❌ Không tìm thấy lệnh 'scrapy' — cần `pip install scrapy` hoặc activate venv\n   ↳ {tag}",
        }
    except Exception as e:
        return {
            "status": "error",
            "count": 0,
            "msg": f"❌ Lỗi hệ thống: {type(e).__name__}: {e}\n   ↳ {tag}",
        }


def build_tasks(provinces, reverse=False):
    """Tạo full task list từ tất cả SPIDER_CONFIGS.

    reverse=True: đảo thứ tự spider (bds68 trước bds_spider) và đảo thứ tự
    estate_type idx (idx cao trước → khác/đất chạy trước nhà mặt phố/nhà riêng).
    """
    spider_configs = list(reversed(SPIDER_CONFIGS)) if reverse else SPIDER_CONFIGS
    tasks = []
    for spider_cfg in spider_configs:
        spider_name = spider_cfg["name"]
        items = list(spider_cfg["estate_type_to_topic"].items())
        if reverse:
            items = list(reversed(items))
        for idx, topic in items:
            for p in provinces:
                tasks.append(
                    {
                        "spider_name": spider_name,
                        "name": p["name"],
                        "slug": p["slug"],
                        "estate_type_idx": idx,
                        "kafka_topic": topic,
                    }
                )
    return tasks


def main():
    # CLI override: cho phép `python run_new.py --reverse` hoặc `--no-reverse`.
    import argparse

    parser = argparse.ArgumentParser(description="Crawler BĐS multi-spider")
    parser.add_argument(
        "--reverse",
        action="store_true",
        default=REVERSE,
        help="Đảo thứ tự: chạy khac/dat trước, nhà mặt phố/nhà riêng sau (bù lại lần crawl trước dừng giữa chừng)",
    )
    parser.add_argument(
        "--no-reverse",
        dest="reverse",
        action="store_false",
        help="Chạy theo thứ tự mặc định (override REVERSE=True trong file)",
    )
    args = parser.parse_args()

    if not os.path.exists(PROVINCES_FILE):
        print(f"❌ Lỗi: Không tìm thấy file '{PROVINCES_FILE}'")
        return

    clear_old_logs()

    with open(PROVINCES_FILE, "r", encoding="utf-8") as f:
        provinces = json.load(f)

    tasks = build_tasks(provinces, reverse=args.reverse)
    if args.reverse:
        print(
            "🔁 REVERSE mode: bắt đầu từ bds68_spider idx cao (khac/dat) → idx thấp → bds_spider"
        )

    spider_summary = {
        cfg["name"]: len(cfg["estate_type_to_topic"]) for cfg in SPIDER_CONFIGS
    }
    print(f"📊 Spiders: {spider_summary}")
    print(f"📊 Số tỉnh: {len(provinces)} | Tổng task: {len(tasks)}")

    NUMBER_OF_WORKERS = 3
    total_messages = 0
    status_counter = {}  # đếm số task theo status

    with Pool(processes=NUMBER_OF_WORKERS) as pool:
        with tqdm(total=len(tasks), desc="🚀 Crawler", unit="task") as pbar:
            for result in pool.imap_unordered(run_crawl_task, tasks):
                total_messages += result["count"]
                status = result["status"]
                status_counter[status] = status_counter.get(status, 0) + 1
                if status != "success":
                    tqdm.write(result["msg"])
                pbar.set_postfix(
                    {"Kafka": total_messages, "OK": status_counter.get("success", 0)}
                )
                pbar.update(1)

    print(f"\n🏁 Hoàn tất! {total_messages} message thực sự được Kafka broker nhận.")
    print(f"📊 Thống kê task theo status:")
    for status, count in sorted(status_counter.items(), key=lambda x: -x[1]):
        print(f"   {status:25s} : {count}")
    print(f"📁 Log lỗi chi tiết tại: {LOGS_DIR}")


if __name__ == "__main__":
    main()
