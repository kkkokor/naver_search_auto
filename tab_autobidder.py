import time
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

from api_client import api

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

    def __init__(self, target_list, is_loop, interval):
        super().__init__()
        self.target_list = target_list
        self.is_loop = is_loop
        self.interval = interval
        self.is_running = True

    def run(self):
        while self.is_running:
            total_targets = len(self.target_list)
            if total_targets == 0: break
            
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
                    keywords = api.get_keywords(gid)
                    if keywords:
                        valid_kwds = [k for k in keywords if k['status'] in ['ELIGIBLE', 'ON']]
                        kwd_ids = [k['nccKeywordId'] for k in valid_kwds]
                        
                        if kwd_ids:
                            # 통계 조회
                            stats_map = api.get_stats(kwd_ids)
                            
                            for k in valid_kwds:
                                kid = k['nccKeywordId']
                                cur_bid = k['bidAmt']
                                stat = stats_map.get(kid, {})
                                cur_rank = stat.get('avgRnk', 0.0)
                                imp_cnt = stat.get('impCnt', 0)
                                
                                new_bid, reason = self.calculate_bid(cur_bid, cur_rank, imp_cnt, cfg)
                                
                                if new_bid != cur_bid:
                                    bulk_updates.append({
                                        "nccKeywordId": kid,
                                        "nccAdgroupId": gid,
                                        "bidAmt": new_bid,
                                        "useGroupBidAmt": False
                                    })
                                    logs_buffer.append({
                                        "time": datetime.now().strftime("%H:%M:%S"),
                                        "group": cfg['name'],
                                        "keyword": k['keyword'],
                                        "old": cur_bid,
                                        "new": new_bid,
                                        "rank": round(cur_rank, 1),
                                        "reason": reason
                                    })

                except Exception as e:
                    print(f"Err {gid}: {e}")
                
                self.row_status_signal.emit(idx, "Waiting")
                
                # [중요] 100개 모이면 전송 (API 과부하 방지)
                if len(bulk_updates) >= 100:
                    self.flush_updates(bulk_updates, logs_buffer)
                    bulk_updates = []
                    logs_buffer = []

            # 남은 것 전송
            if bulk_updates:
                self.flush_updates(bulk_updates, logs_buffer)

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
            else:
                self.status_signal.emit("업데이트 실패 (API 오류)")
        except Exception as e:
            self.status_signal.emit(f"전송 오류: {e}")
            
        # [중요] 1014 방지를 위해 전송 후 2초간 휴식
        time.sleep(2.0)

    def calculate_bid(self, cur_bid, cur_rank, imp_cnt, cfg):
        target = cfg['target_rank']
        step = cfg['bid_step']
        max_b = cfg['max_bid']
        min_b = cfg['min_bid']
        probe_limit = cfg['probe_limit']
        min_imp = cfg['min_imp']
        
        if imp_cnt < min_imp and cur_rank > 0: return cur_bid, "데이터부족"
        
        new_bid = cur_bid
        reason = "유지"

        if cur_rank == 0.0:
            if cur_bid < probe_limit:
                new_bid = cur_bid + step
                reason = "🔍탐색"
            else: return cur_bid, "탐색한도"
        elif cur_rank > target:
            new_bid = cur_bid + step
            reason = f"🔺인상({cur_rank})"
        elif cur_rank < target:
            new_bid = cur_bid - step
            reason = f"🔻인하({cur_rank})"
            
        if new_bid > max_b: new_bid = max_b; reason += "(MAX)"
        if new_bid < min_b: new_bid = min_b; reason += "(MIN)"
        
        return new_bid, reason

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
        h_tree.addWidget(QLabel("<b>1. 대상 선택</b>"))
        btn_refresh = QPushButton("불러오기")
        btn_refresh.setFixedSize(70, 25)
        btn_refresh.clicked.connect(self.start_loading)
        h_tree.addWidget(btn_refresh)
        left_layout.addLayout(h_tree)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("캠페인 / 광고그룹")
        left_layout.addWidget(self.tree)
        
        right_layout = QVBoxLayout()
        
        grp_setting = QGroupBox("2. 공통 설정 값")
        grid = QVBoxLayout()
        row1 = QHBoxLayout()
        self.sb_target = QSpinBox(); self.sb_target.setRange(1, 100); self.sb_target.setValue(3); self.sb_target.setPrefix("목표: ")
        self.sb_max = QSpinBox(); self.sb_max.setRange(70, 300000); self.sb_max.setSingleStep(1000); self.sb_max.setValue(20000); self.sb_max.setPrefix("최대: ")
        self.sb_step = QSpinBox(); self.sb_step.setRange(10, 10000); self.sb_step.setValue(500); self.sb_step.setPrefix("단위: ")
        row1.addWidget(self.sb_target); row1.addWidget(self.sb_max); row1.addWidget(self.sb_step)
        
        row2 = QHBoxLayout()
        self.sb_probe = QSpinBox(); self.sb_probe.setRange(70, 50000); self.sb_probe.setValue(5000); self.sb_probe.setPrefix("탐색한도: ")
        self.sb_imp = QSpinBox(); self.sb_imp.setRange(0, 10000); self.sb_imp.setValue(20); self.sb_imp.setPrefix("신뢰노출: ")
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
        bulk_layout = QHBoxLayout(grp_bulk_fix)
        self.combo_camp_bulk = QComboBox()
        self.combo_camp_bulk.addItem("캠페인 선택")
        self.sb_bulk_bid = QSpinBox()
        self.sb_bulk_bid.setRange(70, 300000)
        self.sb_bulk_bid.setSingleStep(1000)
        self.sb_bulk_bid.setValue(500)
        self.sb_bulk_bid.setPrefix("입찰가: ")
        self.btn_bulk_fix = QPushButton("✓ 일괄 설정 실행")
        self.btn_bulk_fix.setStyleSheet("background-color: #ff9800; color: white; font-weight: bold;")
        self.btn_bulk_fix.clicked.connect(self.start_bulk_bid_fix)
        bulk_layout.addWidget(QLabel("대상:"))
        bulk_layout.addWidget(self.combo_camp_bulk)
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