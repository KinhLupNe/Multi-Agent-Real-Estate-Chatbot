"""Helpers gọi API chat của backend FastAPI."""
from typing import Dict, Any
import requests

BASE_URL = "http://localhost:8000"


def get_response(messages: Any) -> Dict:
    """Gọi POST /chat/ — body là list messages, item cuối phải có chat_id."""
    endpoint = f"{BASE_URL}/chat/"
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(endpoint, json=messages, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        raise ValueError(f"HTTP error: {http_err} - Status: {response.status_code}")
    except requests.exceptions.ConnectionError:
        raise ValueError("Không kết nối được backend FastAPI (port 8000).")
    except requests.exceptions.Timeout:
        raise ValueError("Backend phản hồi quá lâu, thử lại sau.")
    except requests.exceptions.JSONDecodeError:
        raise ValueError("Response không phải JSON hợp lệ.")
    except requests.exceptions.RequestException as req_err:
        raise ValueError(f"Lỗi request: {req_err}")


def get_conversation_name(messages: Any) -> str:
    """Gọi POST /chat/name_conversation để backend tự đặt tên cuộc chat."""
    endpoint = f"{BASE_URL}/chat/name_conversation"
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(endpoint, json=messages, headers=headers)
        response.raise_for_status()
        return str(response.json())
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Lỗi đặt tên chat: {e}")
