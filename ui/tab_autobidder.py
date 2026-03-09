import time
import json
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTreeWidget, QTreeWidgetItem, QGroupBox, QFormLayout, 
    QSpinBox, QCheckBox, QTableWidget, QTableWidgetItem, 
    QHeaderView, QMessageBox, QSplitter, QProgressBar, QDoubleSpinBox, QComboBox
)
from PyQt6.QtWidgets import QTreeWidgetItemIterator
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont

from api.api_client import api

# -------------------------------------------------------------------------
# [데이터 로더] 안전한 순차 로딩 (1014 에러 방지)
# -------------------------------------------------------------------------
class CampaignLoader(QThread):
    data_signal = pyqtSignal(list)
    
    def run(self):
        try:
            # 1. 캠페인 조회
            camps = api.get_campaigns()
            if not camps:
                self.data_signal.emit([])
                return

            result_tree = []
            # 2. 순차적으로 하나씩 조회 (병렬 처리 제거)
            for c in camps:
                camp_data = {
                    'id': c['nccCampaignId'],
                    'name': c['name'],
                    'groups': []
                }
                groups = api.get_adgroups(c['nccCampaignId'])
                for g in groups:
                    camp_data['groups'].append({
                        'id': g['nccAdgroupId'],
                        'name': g['name']
                    })
                result_tree.append(camp_data)
                # [중요] 0.2초 대기
                time.sleep(0.2)
            
            self.data_signal.emit(result_tree)
        except Exception:
            self.data_signal.emit([])

# -------------------------------------------------------------------------
# [입찰 워커] 벌크 업데이트 + 속도 제한 적용
# -------------------------------------------------------------------------
class BidWorker(QThread):
    log_signal = pyqtSignal(dict)
    status_signal = pyqtSignal(str) 
    row_status_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal()

    COOLDOWN_FILE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bid_cooldown.json'))

    def __init__(self, target_list, is_loop, interval):
        super().__init__()
        self.target_list = target_list
        self.is_loop = is_loop
        self.interval = interval
        self.is_running = True
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.cooldown_map = self._load_cooldown()

    def _load_cooldown(self):
        try:
            if os.path.exists(self.COOLDOWN_FILE):
                with open(self.COOLDOWN_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                now = datetime.now()
                pruned = {}
                for kid, ts_str in data.items():
                    ts = datetime.fromisoformat(ts_str)
                    if (now - ts).total_seconds() < 48 * 3600:
                        pruned[kid] = ts_str
                return pruned
        except Exception as e:
            print(f"[COOLDOWN] 로드 실패: {e}")
        return {}

    def _save_cooldown(self):
        try:
            with open(self.COOLDOWN_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.cooldown_map, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[COOLDOWN] 저장 실패: {e}")

    def _is_adjusted_in_24h(self, keyword_id):
        ts_str = self.cooldown_map.get(keyword_id)
        if not ts_str:
            return False
        try:
            last_adj = datetime.fromisoformat(ts_str)
            return (datetime.now() - last_adj).total_seconds() < 24 * 3600
        except:
            return False

    def _record_adjustment(self, keyword_id):
        self.cooldown_map[keyword_id] = datetime.now().isoformat()

    def run(self):
        while self.is_running:
            total_targets = len(self.target_list)
            if total_targets == 0: break
            
            # 연속 오류가 너무 많으면 중단
            if self.consecutive_errors >= self.max_consecutive_errors:
                self.status_signal.emit(f"⚠️ 연속 {self.consecutive_errors}회 오류 발생. 안전을 위해 자동 중단합니다.")
                time.sleep(2)
                break
            
            bulk_updates = [] 
            logs_buffer = []

            for item in self.target_list:
                if not self.is_running: break
                
                idx = item['row']
                gid = item['gid']
                cfg = item['config']
                
                self.row_status_signal.emit(idx, "Running")
                self.status_signal.emit(f"분석 중: {cfg['name']}")
                
                try:
                    # [핵심 변경] 100개씩 조회하고 처리하는 방식
                    chunk_size = 100
                    processed_count = 0
                    base_search_id = None  # 페이징을 위한 ID
                    
                    while self.is_running:
                        # 100개씩 키워드 조회
                        keywords = api.get_keywords_paged(gid, base_search_id, chunk_size)
                        
                        # API 응답 확인 (밴/한도 초과 감지)
                        if keywords is None or (isinstance(keywords, dict) and keywords.get('error')):
                            error_code = keywords.get('code') if isinstance(keywords, dict) else None
                            
                            # 1014 오류 (한도 초과) - 재시도 전에 충분히 대기
                            if error_code == 1014:
                                self.status_signal.emit(f"⏸️ API 한도 초과 (1014). 30초 대기 후 재시도...")
                                time.sleep(30)
                                self.consecutive_errors = 0  # 한도 초과는 일시적이므로 카운터 리셋
                                continue
                            
                            self.consecutive_errors += 1
                            self.status_signal.emit(f"⚠️ API 오류 ({self.consecutive_errors}/{self.max_consecutive_errors}): {cfg['name']}")
                            time.sleep(2)
                            break
                        
                        # 키워드가 없으면 종료
                        if not keywords or len(keywords) == 0:
                            break
                        
                        # 다음 페이지를 위한 base_search_id 업데이트
                        if len(keywords) == chunk_size:
                            base_search_id = keywords[-1]['nccKeywordId']
                        else:
                            base_search_id = None  # 마지막 페이지
                        
                        # API 속도 제한 - 키워드 조회 후 대기
                        time.sleep(0.5)
                        
                        # 유효한 키워드만 필터링
                        valid_kwds = [k for k in keywords if k['status'] in ['ELIGIBLE', 'ON']]
                        if not valid_kwds:
                            continue
                        
                        kwd_ids = [k['nccKeywordId'] for k in valid_kwds]
                        processed_count += len(valid_kwds)
                        
                        print(f"[AUTOBID] {cfg['name']}: {len(kwd_ids)}개 유효 키워드 (총 {processed_count}개 처리 중)")
                        
                        # 통계 조회
                        stats_map = api.get_stats(kwd_ids)

                        # 에러 응답 처리
                        if isinstance(stats_map, dict) and stats_map.get('error'):
                            error_code = stats_map.get('code')
                            if error_code == 1014:
                                print(f"[AUTOBID] API 한도 초과 (1014) - 30초 대기")
                                self.status_signal.emit(f"⏸️ 통계 API 한도 초과. 30초 대기...")
                                time.sleep(30)
                                self.consecutive_errors = 0
                                continue
                            print(f"[AUTOBID_ERROR] 통계 조회 오류 - 코드: {error_code}")
                            self.consecutive_errors += 1
                            self.status_signal.emit(f"⚠️ 통계 조회 실패 ({self.consecutive_errors}/{self.max_consecutive_errors})")
                            time.sleep(2)
                            continue

                        # 통계 없으면 빈 딕셔너리 (신규 키워드 탐색 모드)
                        if not stats_map:
                            print(f"[AUTOBID] {cfg['name']}: 통계 데이터 없음 (탐색 모드)")
                            stats_map = {}

                        self.consecutive_errors = 0
                        print(f"[AUTOBID] {cfg['name']}: 통계 {len(stats_map)}개 수집")
                        time.sleep(1.0)

                        # 키워드 데이터 수집
                        all_keywords = []
                        keyword_data_map = {}

                        for k in valid_kwds:
                            kid = k['nccKeywordId']
                            cur_bid = k['bidAmt']
                            stat = stats_map.get(kid, {})
                            cur_rank = stat.get('avgRnk', 0.0)
                            imp_cnt = stat.get('impCnt', 0)
                            keyword = k['keyword']

                            keyword_data_map[keyword] = {
                                'kid': kid,
                                'cur_bid': cur_bid,
                                'cur_rank': cur_rank,
                                'imp_cnt': imp_cnt
                            }
                            all_keywords.append(keyword)

                        # estimate API 호출
                        estimate_map = {}
                        if all_keywords:
                            print(f"[AUTOBID] {cfg['name']}: {len(all_keywords)}개 키워드 estimate 조회")
                            target_position = int(cfg['target_rank'])
                            estimate_map = api.get_estimate_bid(all_keywords, target_position=target_position)
                            time.sleep(0.5)

                        # 입찰가 계산
                        for k in valid_kwds:
                            keyword = k['keyword']
                            data = keyword_data_map[keyword]
                            estimated_bid = estimate_map.get(keyword) if estimate_map else None

                            new_bid, reason = self.calculate_bid_with_data(
                                data['cur_bid'], data['cur_rank'], data['imp_cnt'],
                                estimated_bid, cfg, data['kid']
                            )

                            if new_bid != data['cur_bid']:
                                bulk_updates.append({
                                    "nccKeywordId": data['kid'],
                                    "nccAdgroupId": gid,
                                    "bidAmt": new_bid,
                                    "useGroupBidAmt": False
                                })
                                logs_buffer.append({
                                    "time": datetime.now().strftime("%H:%M:%S"),
                                    "group": cfg['name'],
                                    "keyword": keyword,
                                    "old": data['cur_bid'],
                                    "new": new_bid,
                                    "rank": round(data['cur_rank'], 1) if data['cur_rank'] else 0,
                                    "reason": reason
                                })
                        
                        # 이 청크(100개)의 업데이트 실행
                        if bulk_updates:
                            print(f"[AUTOBID] {cfg['name']}: {len(bulk_updates)}개 키워드 업데이트 실행")
                            self.flush_updates(bulk_updates, logs_buffer)
                            bulk_updates = []
                            logs_buffer = []
                        
                        # 다음 청크로 이동 전 대기 (API 한도 방지)
                        time.sleep(2.0)
                        
                        # 마지막 페이지면 종료
                        if base_search_id is None:
                            break

                except Exception as e:
                    print(f"Err {gid}: {e}")
                    self.consecutive_errors += 1
                    if self.consecutive_errors >= self.max_consecutive_errors:
                        self.status_signal.emit(f"⚠️ 연속 오류 한도 초과. 중단합니다.")
                        break
                
                self.row_status_signal.emit(idx, "Waiting")
                self._save_cooldown()

                # [중요] 각 그룹 처리 후 추가 대기 (API 한도 방지) - 3초로 증가
                time.sleep(3.0)

            if not self.is_loop: break
            
            self.status_signal.emit(f"사이클 완료. {self.interval}분 대기...")
            # 대기 시간 (중단 가능하도록 쪼개서 대기)
            for _ in range(self.interval * 60):
                if not self.is_running: break
                time.sleep(1)

        self.finished_signal.emit()

    # [수정] BidWorker의 flush_updates 메서드 수정 (대기 시간 증가)
    def flush_updates(self, updates, logs):
        if not updates: return
        
        self.status_signal.emit(f"{len(updates)}개 키워드 수정 중...")
        try:
            res = api.update_keywords_bulk(updates)
            if isinstance(res, list):
                for log in logs:
                    self.log_signal.emit(log)
                # 성공 시 오류 카운터 리셋
                self.consecutive_errors = 0
            elif isinstance(res, dict) and res.get('error'):
                # API 오류 감지
                error_code = res.get('code', 'unknown')
                
                # 1014 오류 특별 처리
                if error_code == 1014:
                    self.status_signal.emit(f"⏸️ 업데이트 한도 초과 (1014). 30초 대기...")
                    time.sleep(30)
                    self.consecutive_errors = 0
                    return
                
                self.consecutive_errors += 1
                self.status_signal.emit(f"⚠️ 업데이트 실패 ({self.consecutive_errors}/{self.max_consecutive_errors}): 코드 {error_code}")
            else:
                self.status_signal.emit("업데이트 실패 (API 오류)")
                self.consecutive_errors += 1
        except Exception as e:
            self.status_signal.emit(f"전송 오류: {e}")
            self.consecutive_errors += 1
            
        # [수정] API 안정성을 위해 대기 시간 10초로 증가 (한도 초과 방지)
        time.sleep(10.0)

    def calculate_bid_with_data(self, cur_bid, cur_rank, imp_cnt, estimated_bid, cfg, keyword_id=None):
        """
        자동입찰 6규칙 알고리즘:

        Rule 1: [최우선] Estimate 가격 → 그대로 적용 (max_bid 캡)
        Rule 2: 목표보다 높은 순위 → 단위 인하 (신뢰노출 이상, 24h 쿨다운)
        Rule 3: 목표보다 낮은 순위 → 단위 인상 (신뢰노출 이상, 24h 쿨다운, max_bid 캡)
        Rule 4: 모든 입찰가 max_bid 초과 불가
        Rule 5: 순위 미노출(rank=0) → 탐색모드 (probe_limit 한도)
        Rule 6: 목표순위 = 현재순위 → 동결
        """
        target = cfg['target_rank']
        step = cfg['bid_step']
        max_b = cfg['max_bid']
        min_b = cfg['min_bid']
        probe_limit = cfg['probe_limit']
        min_imp = cfg['min_imp']

        # ━━━ [Rule 1] Estimate 가격 (최우선) ━━━
        if estimated_bid:
            # 순위가 목표보다 낮거나 노출 부족 → estimate와 단위인상 중 큰 값 적용
            if cur_rank > target or (cur_rank > 0 and imp_cnt < min_imp):
                new_bid = max(estimated_bid, cur_bid + step)
                new_bid = min(new_bid, max_b)
                if new_bid == cur_bid:
                    return cur_bid, f"✓유지(Est={estimated_bid},{int(cur_rank)}위)"
                return new_bid, f"📊Est+인상({cur_bid}→{new_bid},Est={estimated_bid})"

            new_bid = min(estimated_bid, max_b)
            if new_bid == cur_bid:
                return cur_bid, f"✓유지(Est={estimated_bid})"
            elif new_bid > cur_bid:
                return new_bid, f"📊Est인상({cur_bid}→{new_bid})"
            else:
                return new_bid, f"📊Est인하({cur_bid}→{new_bid})"

        # ━━━ [Rule 5] 순위 미노출 → 탐색 모드 ━━━
        if cur_rank == 0.0:
            if cur_bid < probe_limit:
                new_bid = cur_bid + step
                if new_bid > probe_limit:
                    new_bid = probe_limit
                if new_bid > max_b:
                    new_bid = max_b
                return new_bid, "🔍탐색(미노출)"
            else:
                return cur_bid, "탐색한도도달"

        # ━━━ 노출 부족 (순위 있지만 데이터 불충분) → 동결 ━━━
        if imp_cnt < min_imp:
            return cur_bid, f"유지(노출부족{imp_cnt}<{min_imp})"

        # ━━━ [Rule 6] 목표순위 = 현재순위 → 동결 ━━━
        if cur_rank == target:
            return cur_bid, f"✓유지({int(cur_rank)}위=목표)"

        # ━━━ [Rule 2] 목표보다 높은 순위 → 단위 인하 (24h 쿨다운) ━━━
        if cur_rank < target:
            if keyword_id and self._is_adjusted_in_24h(keyword_id):
                return cur_bid, f"유지(24h쿨다운,{int(cur_rank)}위)"
            new_bid = cur_bid - step
            if new_bid < min_b:
                new_bid = min_b
            if keyword_id:
                self._record_adjustment(keyword_id)
            return new_bid, f"🔻인하({int(cur_rank)}위→목표{target}위)"

        # ━━━ [Rule 3] 목표보다 낮은 순위 → 단위 인상 (24h 쿨다운) ━━━
        if cur_rank > target:
            if keyword_id and self._is_adjusted_in_24h(keyword_id):
                return cur_bid, f"유지(24h쿨다운,{int(cur_rank)}위)"
            new_bid = cur_bid + step
            if new_bid > max_b:
                new_bid = max_b
            if keyword_id:
                self._record_adjustment(keyword_id)
            return new_bid, f"🔺인상({int(cur_rank)}위→목표{target}위)"

        return cur_bid, "유지"

    def stop(self):
        self.is_running = False

# -------------------------------------------------------------------------
# [일괄 입찰가 워커] 모든 키워드를 동일 금액으로 설정
# -------------------------------------------------------------------------
class BulkBidFixWorker(QThread):
    log_signal = pyqtSignal(dict)
    status_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)  # (current, total)
    finished_signal = pyqtSignal()

    def __init__(self, campaign_id, fixed_bid_amt):
        super().__init__()
        self.campaign_id = campaign_id
        self.fixed_bid_amt = fixed_bid_amt
        self.is_running = True

    def run(self):
        try:
            self.status_signal.emit("캠페인 그룹 조회 중...")
            
            # 1. 캠페인의 모든 그룹 조회
            groups = api.get_adgroups(self.campaign_id)
            if not groups:
                self.status_signal.emit("그룹이 없습니다.")
                self.finished_signal.emit()
                return
            
            total_keywords = 0
            processed = 0
            all_updates = []
            
            # 2. 각 그룹의 모든 키워드 조회
            for g in groups:
                if not self.is_running: break
                
                gid = g['nccAdgroupId']
                gname = g['name']
                keywords = api.get_keywords(gid)
                
                if keywords:
                    for k in keywords:
                        if k['status'] in ['ELIGIBLE', 'ON']:
                            kid = k['nccKeywordId']
                            old_bid = k['bidAmt']
                            
                            # 기존 금액과 다를 때만 업데이트 추가
                            if old_bid != self.fixed_bid_amt:
                                all_updates.append({
                                    'nccKeywordId': kid,
                                    'nccAdgroupId': gid,
                                    'bidAmt': self.fixed_bid_amt
                                })
                                
                                # 로그 출력
                                self.log_signal.emit({
                                    'time': datetime.now().strftime("%H:%M:%S"),
                                    'group': gname,
                                    'keyword': k['keyword'],
                                    'old': old_bid,
                                    'new': self.fixed_bid_amt,
                                    'reason': f'일괄 설정'
                                })
                            
                            total_keywords += 1
                            processed += 1
                            self.progress_signal.emit(processed, len(groups))
                
                time.sleep(0.2)  # 속도 제한
            
            # 3. 일괄 업데이트
            if all_updates:
                self.status_signal.emit(f"업데이트 중... ({len(all_updates)}개 키워드)")
                
                # 100개씩 묶어서 업데이트
                for i in range(0, len(all_updates), 100):
                    if not self.is_running: break
                    chunk = all_updates[i:i+100]
                    api.update_keywords_bulk(chunk)
                    time.sleep(0.5)  # 요청 간격
                
                self.status_signal.emit(f"완료! 총 {len(all_updates)}개 키워드 업데이트")
            else:
                self.status_signal.emit("변경할 키워드가 없습니다.")
            
            self.finished_signal.emit()
        except Exception as e:
            self.status_signal.emit(f"오류: {str(e)}")
            self.finished_signal.emit()

    def stop(self):
        self.is_running = False

# -------------------------------------------------------------------------
# [메인 UI]
# -------------------------------------------------------------------------
class AutoBidderWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.loader = None
        self.added_groups_row = {} 
        self.init_ui()
        
    def init_ui(self):
        layout = QHBoxLayout(self)
        
        left_layout = QVBoxLayout()
        h_tree = QHBoxLayout()
        lbl_target = QLabel("<b>1. 대상 선택</b>")
        lbl_target.setMinimumWidth(150)
        h_tree.addWidget(lbl_target)
        h_tree.addStretch()
        btn_refresh = QPushButton("불러오기")
        btn_refresh.setMinimumSize(100, 30)
        btn_refresh.setStyleSheet("font-size: 11pt; padding: 5px;")
        btn_refresh.clicked.connect(self.start_loading)
        h_tree.addWidget(btn_refresh)
        left_layout.addLayout(h_tree)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("캠페인 / 광고그룹")
        left_layout.addWidget(self.tree)
        
        right_layout = QVBoxLayout()
        
        grp_setting = QGroupBox("2. 공통 설정 값")
        grp_setting.setStyleSheet("QGroupBox { font-size: 11pt; font-weight: bold; }")
        grid = QVBoxLayout()
        row1 = QHBoxLayout()
        self.sb_target = QSpinBox(); self.sb_target.setRange(1, 100); self.sb_target.setValue(3); self.sb_target.setPrefix("목표: ")
        self.sb_target.setMinimumWidth(120); self.sb_target.setStyleSheet("font-size: 10pt; padding: 5px;")
        self.sb_max = QSpinBox(); self.sb_max.setRange(70, 300000); self.sb_max.setSingleStep(1000); self.sb_max.setValue(20000); self.sb_max.setPrefix("최대: ")
        self.sb_max.setMinimumWidth(150); self.sb_max.setStyleSheet("font-size: 10pt; padding: 5px;")
        self.sb_step = QSpinBox(); self.sb_step.setRange(10, 10000); self.sb_step.setValue(500); self.sb_step.setPrefix("단위: ")
        self.sb_step.setMinimumWidth(120); self.sb_step.setStyleSheet("font-size: 10pt; padding: 5px;")
        row1.addWidget(self.sb_target); row1.addWidget(self.sb_max); row1.addWidget(self.sb_step)
        
        row2 = QHBoxLayout()
        self.sb_probe = QSpinBox(); self.sb_probe.setRange(70, 50000); self.sb_probe.setValue(5000); self.sb_probe.setPrefix("탐색한도: ")
        self.sb_probe.setMinimumWidth(150); self.sb_probe.setStyleSheet("font-size: 10pt; padding: 5px;")
        self.sb_imp = QSpinBox(); self.sb_imp.setRange(0, 10000); self.sb_imp.setValue(20); self.sb_imp.setPrefix("신뢰노출: ")
        self.sb_imp.setMinimumWidth(140); self.sb_imp.setStyleSheet("font-size: 10pt; padding: 5px;")
        row2.addWidget(self.sb_probe); row2.addWidget(self.sb_imp); row2.addStretch()
        
        grid.addLayout(row1); grid.addLayout(row2)
        
        self.btn_add = QPushButton("▼ 설정 적용하여 대기열 추가")
        self.btn_add.setStyleSheet("background-color: #6610f2; color: white; font-weight: bold; padding: 10px;")
        self.btn_add.clicked.connect(self.add_or_update_groups)
        grid.addWidget(self.btn_add)
        grp_setting.setLayout(grid)
        right_layout.addWidget(grp_setting)
        
        right_layout.addWidget(QLabel("<b>3. 자동입찰 대기열</b>"))
        self.table_target = QTableWidget()
        self.table_target.setColumnCount(8)
        self.table_target.setHorizontalHeaderLabels(["그룹명", "목표순위", "최대입찰", "입찰단위", "탐색한도", "신뢰노출", "상태", "GID"])
        self.table_target.setColumnHidden(7, True)
        self.table_target.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.table_target)
        
        btn_del = QPushButton("선택 삭제")
        btn_del.clicked.connect(self.remove_rows)
        right_layout.addWidget(btn_del)
        
        # [새로운 기능] 일괄 입찰가 설정
        grp_bulk_fix = QGroupBox("4. 일괄 입찰가 설정 (모든 키워드)")
        grp_bulk_fix.setStyleSheet("QGroupBox { font-size: 11pt; font-weight: bold; }")
        bulk_layout = QHBoxLayout(grp_bulk_fix)
        lbl_bulk = QLabel("대상:")
        lbl_bulk.setMinimumWidth(50)
        lbl_bulk.setStyleSheet("font-size: 10pt;")
        self.combo_camp_bulk = QComboBox()
        self.combo_camp_bulk.addItem("캠페인 선택")
        self.combo_camp_bulk.setMinimumWidth(200)
        self.combo_camp_bulk.setStyleSheet("font-size: 10pt; padding: 5px;")
        self.sb_bulk_bid = QSpinBox()
        self.sb_bulk_bid.setRange(70, 300000)
        self.sb_bulk_bid.setSingleStep(1000)
        self.sb_bulk_bid.setValue(500)
        self.sb_bulk_bid.setPrefix("입찰가: ")
        self.sb_bulk_bid.setMinimumWidth(150)
        self.sb_bulk_bid.setStyleSheet("font-size: 10pt; padding: 5px;")
        self.btn_bulk_fix = QPushButton("✓ 일괄 설정 실행")
        self.btn_bulk_fix.setMinimumSize(130, 35)
        self.btn_bulk_fix.setStyleSheet("background-color: #ff9800; color: white; font-weight: bold; font-size: 10pt; padding: 5px;")
        self.btn_bulk_fix.clicked.connect(self.start_bulk_bid_fix)
        bulk_layout.addWidget(lbl_bulk)
        bulk_layout.addWidget(self.combo_camp_bulk, 1)
        bulk_layout.addWidget(self.sb_bulk_bid)
        bulk_layout.addWidget(self.btn_bulk_fix)
        right_layout.addWidget(grp_bulk_fix)
        
        hbox_exec = QHBoxLayout()
        self.chk_loop = QCheckBox("무한반복"); self.chk_loop.setChecked(True)
        self.sb_interval = QSpinBox(); self.sb_interval.setValue(10); self.sb_interval.setSuffix("분")
        self.btn_start = QPushButton("🚀 입찰 시작")
        self.btn_start.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 10px;")
        self.btn_start.clicked.connect(self.toggle_bidding)
        
        hbox_exec.addWidget(self.chk_loop); hbox_exec.addWidget(QLabel("대기:")); hbox_exec.addWidget(self.sb_interval)
        hbox_exec.addStretch(); hbox_exec.addWidget(self.btn_start)
        right_layout.addLayout(hbox_exec)
        
        self.lbl_status = QLabel("준비됨")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.lbl_status)
        
        self.table_log = QTableWidget()
        self.table_log.setColumnCount(6)
        self.table_log.setHorizontalHeaderLabels(["시간", "그룹", "키워드", "기존", "변경", "사유"])
        self.table_log.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.table_log)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        w_left = QWidget(); w_left.setLayout(left_layout)
        w_right = QWidget(); w_right.setLayout(right_layout)
        splitter.addWidget(w_left); splitter.addWidget(w_right)
        splitter.setSizes([350, 600])
        layout.addWidget(splitter)

    def start_loading(self):
        self.tree.clear()
        self.lbl_status.setText("로딩 중...")
        self.loader = CampaignLoader()
        self.loader.data_signal.connect(self.on_loaded)
        self.loader.start()

    def on_loaded(self, data):
        self.lbl_status.setText(f"로딩 완료. (캠페인 {len(data)}개)")
        if not data: return
        
        # 콤보박스에 캠페인 추가
        self.combo_camp_bulk.clear()
        self.combo_camp_bulk.addItem("캠페인 선택", "")
        
        for c in data:
            c_item = QTreeWidgetItem(self.tree)
            c_item.setText(0, c['name'])
            c_item.setFlags(c_item.flags() | Qt.ItemFlag.ItemIsAutoTristate | Qt.ItemFlag.ItemIsUserCheckable)
            c_item.setCheckState(0, Qt.CheckState.Unchecked)
            c_item.setExpanded(True)
            # 콤보박스에 캠페인 ID 추가
            self.combo_camp_bulk.addItem(c['name'], c['id'])
            for g in c['groups']:
                g_item = QTreeWidgetItem(c_item)
                g_item.setText(0, g['name'])
                g_item.setData(0, Qt.ItemDataRole.UserRole, g['id'])
                g_item.setFlags(g_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                g_item.setCheckState(0, Qt.CheckState.Unchecked)

    def add_or_update_groups(self):
        target = self.sb_target.value()
        max_b = self.sb_max.value()
        step = self.sb_step.value()
        probe = self.sb_probe.value()
        min_imp = self.sb_imp.value()
        
        cnt = 0
        iterator = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value()
            gid = item.data(0, Qt.ItemDataRole.UserRole)
            if gid:
                name = item.text(0)
                if gid in self.added_groups_row:
                    row = self.added_groups_row[gid]
                    if row < self.table_target.rowCount():
                        self.table_target.setItem(row, 1, QTableWidgetItem(str(target)))
                        self.table_target.setItem(row, 2, QTableWidgetItem(str(max_b)))
                        self.table_target.setItem(row, 3, QTableWidgetItem(str(step)))
                        self.table_target.setItem(row, 4, QTableWidgetItem(str(probe)))
                        self.table_target.setItem(row, 5, QTableWidgetItem(str(min_imp)))
                else:
                    r = self.table_target.rowCount()
                    self.table_target.insertRow(r)
                    self.table_target.setItem(r, 0, QTableWidgetItem(name))
                    self.table_target.setItem(r, 1, QTableWidgetItem(str(target)))
                    self.table_target.setItem(r, 2, QTableWidgetItem(str(max_b)))
                    self.table_target.setItem(r, 3, QTableWidgetItem(str(step)))
                    self.table_target.setItem(r, 4, QTableWidgetItem(str(probe)))
                    self.table_target.setItem(r, 5, QTableWidgetItem(str(min_imp)))
                    self.table_target.setItem(r, 6, QTableWidgetItem("Ready"))
                    self.table_target.setItem(r, 7, QTableWidgetItem(gid))
                    self.added_groups_row[gid] = r
                cnt += 1
            iterator += 1
        
        if cnt == 0: QMessageBox.warning(self, "알림", "체크된 그룹이 없습니다.")
        else: self.lbl_status.setText(f"{cnt}개 적용 완료")

    def remove_rows(self):
        rows = sorted(set(i.row() for i in self.table_target.selectedIndexes()), reverse=True)
        for r in rows:
            gid = self.table_target.item(r, 7).text()
            if gid in self.added_groups_row: del self.added_groups_row[gid]
            self.table_target.removeRow(r)
        self.added_groups_row = {self.table_target.item(r, 7).text(): r for r in range(self.table_target.rowCount())}

    def toggle_bidding(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop(); self.worker.wait(); self.worker = None
            self.btn_start.setText("🚀 입찰 시작"); self.btn_start.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
            self.lbl_status.setText("중지됨")
            return

        cnt = self.table_target.rowCount()
        if cnt == 0: return QMessageBox.warning(self, "경고", "대기열이 비어있습니다.")

        target_list = []
        try:
            for r in range(cnt):
                gid = self.table_target.item(r, 7).text()
                target_list.append({
                    'row': r, 'gid': gid,
                    'config': {
                        'name': self.table_target.item(r, 0).text(),
                        'target_rank': int(self.table_target.item(r, 1).text()),
                        'max_bid': int(self.table_target.item(r, 2).text()),
                        'bid_step': int(self.table_target.item(r, 3).text()),
                        'probe_limit': int(self.table_target.item(r, 4).text()),
                        'min_imp': int(self.table_target.item(r, 5).text()),
                        'min_bid': 70
                    }
                })
        except: return QMessageBox.warning(self, "오류", "테이블 값 오류")

        self.worker = BidWorker(target_list, self.chk_loop.isChecked(), self.sb_interval.value())
        self.worker.log_signal.connect(self.add_log)
        self.worker.status_signal.connect(self.lbl_status.setText)
        self.worker.row_status_signal.connect(self.update_row_color)
        self.worker.finished_signal.connect(lambda: self.lbl_status.setText("완료"))
        self.worker.start()
        self.btn_start.setText("🛑 중단"); self.btn_start.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")

    def update_row_color(self, row, status):
        if row >= self.table_target.rowCount(): return
        color = QColor("blue") if status == "Running" else QColor("black")
        self.table_target.item(row, 0).setForeground(QBrush(color))
        self.table_target.item(row, 0).setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold if status == "Running" else QFont.Weight.Normal))
        self.table_target.setItem(row, 6, QTableWidgetItem(status))

    def add_log(self, data):
        r = self.table_log.rowCount()
        self.table_log.insertRow(r)
        self.table_log.setItem(r, 0, QTableWidgetItem(data['time']))
        self.table_log.setItem(r, 1, QTableWidgetItem(data['group']))
        self.table_log.setItem(r, 2, QTableWidgetItem(data['keyword']))
        self.table_log.setItem(r, 3, QTableWidgetItem(str(data['old'])))
        new_item = QTableWidgetItem(str(data['new']))
        new_item.setForeground(QBrush(QColor("red" if data['new'] > data['old'] else "blue")))
        self.table_log.setItem(r, 4, new_item)
        self.table_log.setItem(r, 5, QTableWidgetItem(data['reason']))
        self.table_log.scrollToBottom()
        if r > 1000: self.table_log.removeRow(0)

    def start_bulk_bid_fix(self):
        """일괄 입찰가 설정 시작"""
        camp_id = self.combo_camp_bulk.currentData()
        if not camp_id or camp_id == "":
            QMessageBox.warning(self, "경고", "캠페인을 선택해주세요.")
            return
        
        bid_amt = self.sb_bulk_bid.value()
        if bid_amt < 70 or bid_amt > 300000:
            QMessageBox.warning(self, "경고", "입찰가는 70~300,000 사이여야 합니다.")
            return
        
        if QMessageBox.question(self, "확인", 
                                f"캠페인의 모든 키워드 입찰가를 {bid_amt}원으로 설정하시겠습니까?") != QMessageBox.StandardButton.Yes:
            return
        
        # 워커 실행
        self.bulk_bid_worker = BulkBidFixWorker(camp_id, bid_amt)
        self.bulk_bid_worker.log_signal.connect(self.add_log)
        self.bulk_bid_worker.status_signal.connect(self.lbl_status.setText)
        self.bulk_bid_worker.finished_signal.connect(lambda: self.btn_bulk_fix.setEnabled(True))
        self.bulk_bid_worker.start()
        
        self.btn_bulk_fix.setEnabled(False)
        self.lbl_status.setText("일괄 입찰가 설정 중...")