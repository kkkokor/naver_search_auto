import requests
import time
import hmac
import hashlib
import base64
import urllib.parse
import json
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List

class APIClient:
    def __init__(self, server_url: str = "http://3.38.242.254:8000"):
        self.server_url = server_url
        self.server_token: Optional[str] = None
        
        self.naver_api_key: Optional[str] = None
        self.naver_secret_key: Optional[str] = None
        self.naver_customer_id: Optional[str] = None
        self.naver_base_url = "https://api.searchad.naver.com"
        
        self.is_superuser = False

    def log(self, type_str, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{type_str}] {msg}", flush=True)

    # -------------------------------------------------------------------------
    # 1. [관제 서버] 통신
    # -------------------------------------------------------------------------
    def login(self, username, password) -> bool:
        self.log("SERVER", f"로그인 시도: {username}")
        try:
            resp = requests.post(f"{self.server_url}/auth/token", data={"username": username, "password": password}, timeout=5)
            if resp.status_code == 200:
                self.server_token = resp.json()["access_token"]
                self.log("SERVER", "로그인 성공")
                return True
            self.log("SERVER", f"로그인 실패: {resp.status_code}")
            return False
        except Exception as e:
            self.log("SERVER", f"연결 오류: {e}")
            return False

    def fetch_user_info(self) -> bool:
        if not self.server_token: return False
        try:
            resp = requests.get(f"{self.server_url}/users/me", headers={"Authorization": f"Bearer {self.server_token}"}, timeout=5)
            if resp.status_code == 200:
                user = resp.json()
                self.naver_api_key = user.get("naver_access_key")
                self.naver_secret_key = user.get("naver_secret_key")
                self.naver_customer_id = user.get("naver_customer_id")
                self.is_superuser = user.get("is_superuser", False)
                self.log("INFO", "유저 정보 로드 완료")
                return True
            return False
        except: return False

    def send_heartbeat(self, status_message: str):
        if not self.server_token: return
        try:
            requests.post(f"{self.server_url}/api/monitor/heartbeat", json={"status": status_message}, headers={"Authorization": f"Bearer {self.server_token}"}, timeout=2)
        except: pass

    # -------------------------------------------------------------------------
    # 2. [네이버 API] 핵심 로직
    # -------------------------------------------------------------------------
    def _generate_signature(self, timestamp, method, uri):
        clean_uri = uri.split('?')[0]
        message = f"{timestamp}.{method}.{clean_uri}"
        hash = hmac.new(bytes(self.naver_secret_key, "utf-8"), bytes(message, "utf-8"), hashlib.sha256)
        return base64.b64encode(hash.digest()).decode()

    def _get_header(self, method, uri):
        if not self.naver_api_key or not self.naver_secret_key or not self.naver_customer_id:
            raise Exception("API 키 설정 필요")
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, uri)
        return {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Timestamp": timestamp,
            "X-API-KEY": self.naver_api_key,
            "X-Customer": str(self.naver_customer_id),
            "X-Signature": signature
        }

    # [수정] 에러 발생 시 상세 정보를 반환하도록 개선 (키워드 탭에서 사용)
    def call_naver(self, uri: str, method: str = "GET", params: Dict = None, body: Any = None):
        if not self.naver_api_key: return None
        clean_uri = uri.split('?')[0]
        try:
            headers = self._get_header(method, clean_uri)
            url = self.naver_base_url + clean_uri
            
            if method == "GET": resp = requests.get(url, headers=headers, params=params)
            elif method == "POST": resp = requests.post(url, headers=headers, params=params, json=body)
            elif method == "PUT": resp = requests.put(url, headers=headers, params=params, json=body)
            elif method == "DELETE": resp = requests.delete(url, headers=headers, params=params)
            else: return None

            if resp.status_code == 200:
                return resp.json()
            else:
                self.log("NAVER_ERR", f"실패({resp.status_code}): {resp.text}")
                # 에러 핸들링을 위해 에러 객체 반환
                try:
                    err_json = resp.json()
                    return {"error": True, "code": err_json.get('code', resp.status_code), "data": err_json}
                except:
                    return {"error": True, "code": resp.status_code, "data": resp.text}
        except Exception as e:
            self.log("NAVER_EX", f"통신 예외: {e}")
            return {"error": True, "code": 999, "data": str(e)}

    # -------------------------------------------------------------------------
    # 3. [비즈니스 로직]
    # -------------------------------------------------------------------------
    def get_campaigns(self):
        res = self.call_naver("/ncc/campaigns")
        return res if isinstance(res, list) else []

    def get_adgroups(self, campaign_id):
        res = self.call_naver("/ncc/adgroups", params={"nccCampaignId": campaign_id})
        return res if isinstance(res, list) else []

    # [NEW] 특정 그룹 상세 조회 (복제 시 필요)
    def get_adgroup(self, adgroup_id):
        return self.call_naver(f"/ncc/adgroups/{adgroup_id}")

    def get_keywords(self, adgroup_id):
        res = self.call_naver("/ncc/keywords", params={"nccAdgroupId": adgroup_id})
        return res if isinstance(res, list) else []

    # [수정] 성공/실패 여부를 리스트/딕셔너리로 명확히 반환
    def create_keywords_bulk(self, adgroup_id, keywords):
        results = []
        for i in range(0, len(keywords), 100):
            chunk = keywords[i:i+100]
            body = [{"nccAdgroupId": adgroup_id, "keyword": k, "bidAmt": 70} for k in chunk]
            
            res = self.call_naver("/ncc/keywords", method="POST", params={"nccAdgroupId": adgroup_id}, body=body)
            
            if isinstance(res, dict) and res.get('error'):
                return res # 에러 객체 반환
            
            if res: results.extend(res)
            time.sleep(0.1)
        return results

    def update_bid(self, keyword_id, adgroup_id, bid_amt):
        body = [{"nccKeywordId": keyword_id, "nccAdgroupId": adgroup_id, "bidAmt": bid_amt, "useGroupBidAmt": False}]
        return self.call_naver("/ncc/keywords", method="PUT", params={"fields": "bidAmt"}, body=body)
    
    # [NEW] 대량 입찰가 수정 (속도 향상)
    def update_keywords_bulk(self, update_list):
        return self.call_naver("/ncc/keywords", method="PUT", params={"fields": "bidAmt"}, body=update_list)

    def get_stats(self, id_list, since=None, until=None):
        if not id_list: return {}
        if not since:
            today = datetime.now().strftime("%Y-%m-%d")
            time_range = {"since": today, "until": today}
        else:
            time_range = {"since": since, "until": until}
        stats_map = {}
        for i in range(0, len(id_list), 50):
            chunk = id_list[i:i+50]
            ids_str = ",".join(chunk)
            res = self.call_naver("/stats", params={"ids": ids_str, "fields": '["impCnt","clkCnt","salesAmt","avgRnk","ccnt"]', "timeRange": json.dumps(time_range)})
            if res and isinstance(res, dict) and 'data' in res:
                for item in res['data']: stats_map[item['id']] = item
            time.sleep(0.05)
        return stats_map

    def get_ads(self, adgroup_id):
        res = self.call_naver("/ncc/ads", params={"nccAdgroupId": adgroup_id})
        return res if isinstance(res, list) else []

    def create_ad(self, adgroup_id, headline, description, pc_url, mobile_url):
        body = {"type": "TEXT_45", "nccAdgroupId": adgroup_id, "ad": {"headline": headline, "description": description, "pc": {"final": pc_url}, "mobile": {"final": mobile_url}}}
        return self.call_naver("/ncc/ads", method="POST", body=body)

    def get_extensions(self, owner_id):
        res = self.call_naver("/ncc/ad-extensions", params={"ownerId": owner_id})
        return res if isinstance(res, list) else []

    def create_extension(self, owner_id, type_str, content_dict, channel_id=None):
        body = {"ownerId": owner_id, "type": type_str}
        if content_dict: body["adExtension"] = content_dict
        if channel_id:
            body["pcChannelId"] = channel_id
            body["mobileChannelId"] = channel_id
        return self.call_naver("/ncc/ad-extensions", method="POST", body=body)

    def get_biz_channels(self):
        return self.call_naver("/ncc/channels") or []

    # [수정] adgroupType 파라미터 추가 (기존엔 없어서 3734 에러 유발 가능성 있었음)
    def create_adgroup(self, campaign_id, name, pc_cid, mo_cid, adgroup_type="WEB_SITE"):
        body = {
            "nccCampaignId": campaign_id,
            "name": name,
            "pcChannelId": pc_cid,
            "mobileChannelId": mo_cid,
            "adgroupType": adgroup_type # <--- 핵심 추가
        }
        return self.call_naver("/ncc/adgroups", method="POST", body=body)

    # -------------------------------------------------------------------------
    # [관리자 기능] (유지)
    # -------------------------------------------------------------------------
    def get_admin_live_status(self):
        if not self.server_token: return []
        try:
            resp = requests.get(f"{self.server_url}/admin/monitor/live", headers={"Authorization": f"Bearer {self.server_token}"}, timeout=5)
            return resp.json() if resp.status_code == 200 else []
        except: return []

    def get_all_users(self):
        if not self.server_token: return []
        try:
            resp = requests.get(f"{self.server_url}/admin/users", headers={"Authorization": f"Bearer {self.server_token}"}, timeout=5)
            return resp.json() if resp.status_code == 200 else []
        except: return []

    def approve_user(self, user_id, months=1):
        if not self.server_token: return False
        try:
            requests.put(f"{self.server_url}/admin/approve/{user_id}?months={months}", headers={"Authorization": f"Bearer {self.server_token}"})
            return True
        except: return False

api = APIClient("http://3.38.242.254:8000")