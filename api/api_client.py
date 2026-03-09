import requests
import time
import hmac
import hashlib
import base64
import urllib.parse
import json
import sys
from datetime import datetime, timedelta
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

    # [수정] 에러 발생 시 상세 정보를 반환하도록 개선
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
                try:
                    err_json = resp.json()
                    # 에러 코드와 메시지를 포함한 딕셔너리 반환
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
    
    def get_keywords_paged(self, adgroup_id, base_search_id=None, record_size=100):
        """
        페이징을 지원하는 키워드 조회
        base_search_id: 이전 페이지의 마지막 키워드 ID (None이면 첫 페이지)
        record_size: 한 번에 가져올 개수 (기본 100개)
        """
        params = {
            "nccAdgroupId": adgroup_id,
            "recordSize": record_size
        }
        
        if base_search_id:
            params["baseSearchId"] = base_search_id
        
        res = self.call_naver("/ncc/keywords", params=params)
        return res if isinstance(res, list) else []

    # [수정] 성공/실패 여부를 리스트/딕셔너리로 명확히 반환
    def create_keywords_bulk(self, adgroup_id, keywords):
        results = []
        
        for i in range(0, len(keywords), 100):
            chunk = keywords[i:i+100]
            # [수정] 3916 오류 해결: useGroupBidAmt=False를 명시하여 bidAmt를 직접 사용하도록 함
            # useGroupBidAmt 필드가 없으면 bidAmt를 보냈음에도 그룹 입찰가를 사용하려고 시도하다가
            # 그룹 입찰가가 설정되지 않은 경우 오류가 날 수 있음.
            # 혹은 bidAmt 필드 자체가 무시될 수 있음.
            body = [{"nccAdgroupId": adgroup_id, "keyword": k, "bidAmt": 70, "useGroupBidAmt": False} for k in chunk]
            
            # [DEBUG] 요청 바디 출력
            print(f"[DEBUG_REQ] Group:{adgroup_id} Keywords({len(chunk)}): {chunk}", flush=True)

            res = self.call_naver("/ncc/keywords", method="POST", params={"nccAdgroupId": adgroup_id}, body=body)
            
            # [DEBUG] 응답 결과 출력
            print(f"[DEBUG_RES] Type:{type(res)} Body:{str(res)[:500]}...", flush=True)

            if isinstance(res, list):
                for item in res:
                    if 'nccKeywordId' in item:
                        results.append(item)
                    else:
                        print(f"[DEBUG_WARN] Item missing ID: {item}", flush=True)
            
            elif isinstance(res, dict) and res.get('error'):
                print(f"[DEBUG_ERR] API Error: {res}", flush=True)
                if not results:
                    return res
                break
            
            time.sleep(0.2)
            
        return results

    def update_bid(self, keyword_id, adgroup_id, bid_amt):
        body = [{"nccKeywordId": keyword_id, "nccAdgroupId": adgroup_id, "bidAmt": bid_amt, "useGroupBidAmt": False}]
        return self.call_naver("/ncc/keywords", method="PUT", params={"fields": "bidAmt"}, body=body)
    
    # [수정] 대량 입찰가 수정 - useGroupBidAmt: False 추가
    def update_keywords_bulk(self, update_list):
        # 각 항목에 useGroupBidAmt: False 추가 (3916 에러 방지)
        for item in update_list:
            if 'useGroupBidAmt' not in item:
                item['useGroupBidAmt'] = False
        return self.call_naver("/ncc/keywords", method="PUT", params={"fields": "bidAmt"}, body=update_list)

    def get_estimate_bid(self, keywords_data, target_position=3, device="PC"):
        """
        순위별 평균 입찰가 조회 (Estimate API)
        keywords_data: [{'key': '키워드명', 'id': 'nkw-xxx'}, ...] 또는 ['키워드명', ...]
        target_position: 목표 순위 (기본값 3위)
        """
        if not keywords_data:
            return {}
        
        # 최대 100개씩 처리 (API 제한)
        result = {}
        for i in range(0, len(keywords_data), 100):
            chunk = keywords_data[i:i+100]
            items = []
            
            for kw in chunk:
                if isinstance(kw, dict):
                    items.append({
                        "key": kw.get('key') or kw.get('keyword'),
                        "position": target_position
                    })
                else:
                    items.append({"key": kw, "position": target_position})
            
            try:
                # average-position-bid API 호출
                res = self.call_naver(
                    "/estimate/average-position-bid/keyword",
                    method="POST",
                    body={
                        "device": device,
                        "items": items
                    }
                )
                
                if res and 'estimate' in res:
                    for est in res['estimate']:
                        keyword = est.get('keyword')
                        bid = est.get('bid', 70)  # 기본값 70원
                        ncc_id = est.get('nccKeywordId')  # ID도 포함될 수 있음
                        
                        # [중요] 70원은 데이터 없음을 의미하는 허수이므로 무시
                        if bid == 70:
                            continue
                        
                        # 키워드명과 ID 모두 매핑
                        if keyword:
                            result[keyword] = bid
                        if ncc_id:
                            result[ncc_id] = bid
                
                print(f"[ESTIMATE] {len(chunk)}개 키워드 입찰가 조회 완료")
                time.sleep(0.5)  # API 속도 제한
                
            except Exception as e:
                print(f"[ESTIMATE_ERROR] 입찰가 조회 실패: {e}")
                continue
        
        return result

    def get_stats(self, id_list, since=None, until=None):
        if not id_list: return {}
        if not since:
            # 최근 7일 데이터 사용 (당일 ~ 7일 전)
            # 당일 데이터도 포함하여 최대한 실시간 반영
            until_date = datetime.now().strftime("%Y-%m-%d")
            since_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            time_range = {"since": since_date, "until": until_date}
        else:
            time_range = {"since": since, "until": until}
        
        print(f"[STATS] 통계 조회 시작: {len(id_list)}개 키워드, 기간: {time_range}")
        sys.stdout.flush()  # 즉시 출력
        stats_map = {}
        
        for i in range(0, len(id_list), 50):
            chunk = id_list[i:i+50]
            ids_str = ",".join(chunk)
            # 기본 필드만 요청 (convCnt, convValue 제외 - 오류 원인 가능성)
            fields = ["impCnt", "clkCnt", "salesAmt", "avgRnk", "ccnt"]
            
            print(f"[STATS] 청크 {i//50 + 1}/{(len(id_list)-1)//50 + 1}: {len(chunk)}개 ID 조회 중...")
            sys.stdout.flush()
            
            # [디버깅] 첫 청크 파라미터 출력
            if i == 0:
                print(f"[STATS_DEBUG] 요청 파라미터:")
                print(f"  - ids: {ids_str[:200]}...")  # 처음 200자만
                print(f"  - fields: {json.dumps(fields)}")
                print(f"  - timeRange: {json.dumps(time_range)}")
                sys.stdout.flush()
            
            res = self.call_naver("/stats", params={
                "ids": ids_str, 
                "fields": json.dumps(fields),
                "timeRange": json.dumps(time_range)
            })

            # [디버깅] 실제 응답 구조 확인
            if i == 0:  # 첫 번째 청크만 출력
                print(f"[STATS_DEBUG] 첫 청크 응답 타입: {type(res)}")
                print(f"[STATS_DEBUG] 응답 키: {res.keys() if isinstance(res, dict) else 'N/A'}")
                if isinstance(res, dict) and 'data' in res:
                    print(f"[STATS_DEBUG] data 타입: {type(res['data'])}, 길이: {len(res['data']) if isinstance(res['data'], list) else 'N/A'}")
                    if isinstance(res['data'], list) and len(res['data']) > 0:
                        print(f"[STATS_DEBUG] 첫 번째 항목: {res['data'][0]}")
                print(f"[STATS_DEBUG] 전체 응답: {res}")
                sys.stdout.flush()

            if res and isinstance(res, dict) and 'data' in res:
                for item in res['data']:
                    # item이 딕셔너리인지 확인
                    if not isinstance(item, dict):
                        print(f"[STATS_WARN] 잘못된 데이터 형식: {type(item)}")
                        continue
                    stats_map[item['id']] = item
                print(f"[STATS] 청크 성공: {len(res['data'])}개 통계 수신")
            elif res and isinstance(res, dict) and res.get('error'):
                error_code = res.get('code', 'unknown')
                error_msg = res.get('message', 'unknown')
                print(f"[STATS_ERROR] API 오류 발생 - 코드: {error_code}, 메시지: {error_msg}")
            else:
                print(f"[STATS_ERROR] 예상치 못한 응답 형식: {type(res)}")
            
            # API 한도 방지를 위해 대기 시간 증가 (0.1 → 0.5초)
            time.sleep(0.5)
        
        print(f"[STATS] 완료: 총 {len(stats_map)}개 통계 수집됨")
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
        
        # [수정] POST 요청 시에는 'adExtension' 필드명을 사용해야 함.
        # 4014(Missing Content) 에러 해결을 위해, 빈 값({})이라도 무조건 adExtension 필드를 전송함.
        # PHONE 타입의 경우 만약 {} 전송 시 1010 에러가 난다면, 이는 상위 로직에서 content_dict를 제대로 전달하지 않은 문제임.
        body["adExtension"] = content_dict if content_dict is not None else {}
        
        if channel_id:
            body["pcChannelId"] = channel_id
            body["mobileChannelId"] = channel_id
            
        # [DEBUG]
        if type_str == "PHONE":
            print(f"[DEBUG_EXT_CREATE] PHONE Body: {json.dumps(body, ensure_ascii=False)}", flush=True)

        # [수정] 단일 객체 전송으로 복구 (API가 Array를 받지 않음)
        return self.call_naver("/ncc/ad-extensions", method="POST", body=body)

    def get_biz_channels(self):
        return self.call_naver("/ncc/channels") or []

    # [수정] adgroupType 파라미터 추가
    def create_adgroup(self, campaign_id, name, pc_cid, mo_cid, adgroup_type="WEB_SITE"):
        body = {
            "nccCampaignId": campaign_id,
            "name": name,
            "pcChannelId": pc_cid,
            "mobileChannelId": mo_cid,
            "adgroupType": adgroup_type 
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

    def approve_user(self, user_id, days=30, months=None):
        # 하위호환성: months 파라미터도 지원
        if months is not None:
            days = months * 30
        if not self.server_token: return False
        try:
            requests.put(f"{self.server_url}/admin/approve/{user_id}?days={days}", headers={"Authorization": f"Bearer {self.server_token}"})
            return True
        except: return False

    def extend_user_license(self, user_id, days=30):
        """회원 라이선스 기간 연장"""
        if not self.server_token: return False
        try:
            requests.put(f"{self.server_url}/admin/extend/{user_id}?days={days}", headers={"Authorization": f"Bearer {self.server_token}"})
            return True
        except: return False

    def suspend_user(self, user_id):
        """회원 사용정지"""
        if not self.server_token: return False
        try:
            requests.put(f"{self.server_url}/admin/suspend/{user_id}", headers={"Authorization": f"Bearer {self.server_token}"})
            return True
        except: return False

    def resume_user(self, user_id):
        """사용정지 회원 복구"""
        if not self.server_token: return False
        try:
            requests.put(f"{self.server_url}/admin/resume/{user_id}", headers={"Authorization": f"Bearer {self.server_token}"})
            return True
        except: return False

api = APIClient("http://3.38.242.254:8000")
