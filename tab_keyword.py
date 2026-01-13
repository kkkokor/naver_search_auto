import sys
import re
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QTextEdit, QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QMessageBox, QGroupBox, QCheckBox, QSplitter,
    QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from api_client import api

# -------------------------------------------------------------------------
# [작업 스레드] 스마트 키워드 등록 (워터폴 방식)
# -------------------------------------------------------------------------
# [수정] KeywordRegisterWorker 클래스 전체 교체
class KeywordRegisterWorker(QThread):
    progress_signal = pyqtSignal(int, int) 
    log_signal = pyqtSignal(int, str, str)
    result_signal = pyqtSignal(int, int)
    
    def __init__(self, task_list):
        super().__init__()
        self.task_list = task_list
        self.is_running = True

    def run(self):
        try:
            total = len(self.task_list)
            success_cnt = 0
            fail_cnt = 0
            
            # 그룹별로 작업 분류
            grouped_tasks = {}
            for task in self.task_list:
                gid = task['group_id']
                if gid not in grouped_tasks: grouped_tasks[gid] = []
                grouped_tasks[gid].append(task)

            current_progress = 0
            
            for initial_gid, tasks in grouped_tasks.items():
                if not self.is_running: break
                
                keyword_queue = [t['keyword'] for t in tasks]
                
                # 원본 그룹 정보 조회
                original_grp_info = api.get_adgroup(initial_gid)
                
                if not original_grp_info or 'error' in original_grp_info:
                    self.log_batch(tasks, "실패", "그룹 정보 조회 불가")
                    fail_cnt += len(tasks)
                    current_progress += len(tasks)
                    continue

                current_gid = initial_gid
                current_grp_name = original_grp_info['name']
                campaign_id = original_grp_info['nccCampaignId']
                
                base_name = re.sub(r'_\d+$', '', current_grp_name)
                next_group_index = 1
                
                # 번호 파싱
                if current_grp_name != base_name:
                    try: next_group_index = int(current_grp_name.split('_')[-1]) + 1
                    except: next_group_index = 1

                # [등록 루프]
                while len(keyword_queue) > 0 and self.is_running:
                    # 1. 용량 확인
                    existing_kwds = api.get_keywords(current_gid)
                    # 리스트가 아니면(에러면) 꽉 찬 것으로 간주하여 안전하게 다음 단계로
                    current_count = len(existing_kwds) if isinstance(existing_kwds, list) else 1000
                    capacity = 1000 - current_count
                    
                    # 2. 중복 제거
                    if isinstance(existing_kwds, list):
                        exist_set = {k['keyword'].replace(" ", "").upper() for k in existing_kwds}
                        keyword_queue = [k for k in keyword_queue if k.replace(" ", "").upper() not in exist_set]
                    
                    if not keyword_queue: break

                    # 3. 등록 시도
                    if capacity > 0:
                        chunk = keyword_queue[:capacity]
                        res = api.create_keywords_bulk(current_gid, chunk)
                        
                        # [검증] 리스트이고, 내용이 있어야 진짜 성공
                        if isinstance(res, list) and len(res) > 0:
                            created_cnt = len(res)
                            self.log_batch(tasks[:created_cnt], "성공", f"{current_grp_name} 등록완료")
                            success_cnt += created_cnt
                            
                            keyword_queue = keyword_queue[created_cnt:]
                            tasks = tasks[created_cnt:]
                        else:
                            # 실패 시 잠시 대기
                            time.sleep(1.0)

                    # 4. 남은 키워드가 있다면 -> 그룹 확장(워터폴)
                    if len(keyword_queue) > 0:
                        found_next_group = False
                        
                        while not found_next_group and self.is_running:
                            next_name = f"{base_name}_{next_group_index}"
                            self.log_batch(tasks, "확장중", f"{next_name} 확인 중...")
                            
                            # [안전] 1014 방지를 위한 대기
                            time.sleep(1.0) 
                            
                            # A. 먼저 조회 (Find)
                            all_grps = api.get_adgroups(campaign_id)
                            target = next((g for g in all_grps if g['name'].strip() == next_name.strip()), None)
                            
                            if target:
                                current_gid = target['nccAdgroupId']
                                current_grp_name = target['name']
                                found_next_group = True
                                self.log_batch(tasks, "전환", f"기존 그룹({next_name}) 발견")
                            else:
                                # B. 없으면 생성 (Create)
                                new_grp = api.create_adgroup(
                                    campaign_id, next_name,
                                    original_grp_info.get('pcChannelId'),
                                    original_grp_info.get('mobileChannelId'),
                                    original_grp_info.get('adgroupType', 'WEB_SITE')
                                )
                                
                                if new_grp and 'nccAdgroupId' in new_grp:
                                    current_gid = new_grp['nccAdgroupId']
                                    current_grp_name = next_name
                                    found_next_group = True
                                    self.log_batch(tasks, "생성", f"새 그룹({next_name}) 생성됨")
                                    # 자산 복제
                                    self.clone_assets(initial_gid, current_gid)
                                else:
                                    # 실패 시 다음 번호로
                                    next_group_index += 1
                                    if next_group_index > 100:
                                        self.log_batch(tasks, "실패", "그룹 확장 한도 초과")
                                        fail_cnt += len(keyword_queue)
                                        keyword_queue = [] # 종료
                                        break
                        
                        if found_next_group:
                            next_group_index += 1
                
                current_progress += len(tasks) if not keyword_queue else 0
                self.progress_signal.emit(current_progress, total)

            self.result_signal.emit(success_cnt, fail_cnt)
            
        except Exception as e:
            print(f"Worker Error: {e}")
            self.result_signal.emit(success_cnt, fail_cnt)

    def clone_assets(self, src_gid, dst_gid):
        try:
            time.sleep(1.0) # 안전 딜레이
            # 확장소재 복제
            exts = api.get_extensions(src_gid)
            for ext in exts:
                if ext.get("type") in ["IMAGE_SUB_LINKS", "POWER_LINK_IMAGE"]: continue
                api.create_extension(dst_gid, ext['type'], ext.get('extension'), ext.get('pcChannelId'))
                time.sleep(0.2)
            
            # 소재 복제
            ads = api.get_ads(src_gid)
            for ad in ads:
                c = ad['ad']
                api.create_ad(dst_gid, c['headline'], c['description'], c.get('pc', {}).get('final'), c.get('mobile', {}).get('final'))
                time.sleep(0.2)
        except: pass

    def log_batch(self, tasks, status, msg):
        # 작업이 많이 남았을 때 모든 행을 업데이트하면 UI가 멈출 수 있으므로 첫 번째 행만 업데이트하거나 로그용 
        for t in tasks:
            self.log_signal.emit(t['row'], status, msg)

    def stop(self): self.is_running = False

# -------------------------------------------------------------------------
# [메인 UI]
# -------------------------------------------------------------------------
class KeywordExpanderWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.adgroups_map = {} 
        self.generated_list = [] 
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        left = QWidget(); l_vbox = QVBoxLayout(left)
        
        l_vbox.addWidget(QLabel("1. 대상 캠페인"))
        self.combo_camp = QComboBox()
        self.combo_camp.currentIndexChanged.connect(self.on_campaign_changed)
        l_vbox.addWidget(self.combo_camp)
        
        l_vbox.addWidget(QLabel("2. 그룹명(지역명) 매핑"))
        self.txt_mapping = QTextEdit()
        self.txt_mapping.setPlaceholderText("예: 푸른배관_인천(월미도,송도)")
        l_vbox.addWidget(self.txt_mapping)
        
        l_vbox.addWidget(QLabel("3. 메인 키워드"))
        self.txt_kwd = QTextEdit()
        self.txt_kwd.setFixedHeight(80)
        l_vbox.addWidget(self.txt_kwd)
        
        opt = QHBoxLayout()
        self.chk_ab = QCheckBox("지역+키워드"); self.chk_ab.setChecked(True)
        self.chk_ba = QCheckBox("키워드+지역"); self.chk_ba.setChecked(True)
        self.chk_b = QCheckBox("키워드만")
        opt.addWidget(self.chk_ab); opt.addWidget(self.chk_ba); opt.addWidget(self.chk_b)
        l_vbox.addLayout(opt)
        
        btn_gen = QPushButton("미리보기 생성")
        btn_gen.setStyleSheet("background-color: #6610f2; color: white; padding: 10px;")
        btn_gen.clicked.connect(self.generate_preview)
        l_vbox.addWidget(btn_gen)
        
        right = QWidget(); r_vbox = QVBoxLayout(right)
        r_vbox.addWidget(QLabel("<b>생성 결과</b>"))
        self.table = QTableWidget(); self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["그룹", "키워드", "상태", "메시지"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        r_vbox.addWidget(self.table)
        
        bar = QHBoxLayout()
        self.lbl_cnt = QLabel("0개")
        self.progress = QProgressBar()
        self.btn_run = QPushButton("일괄 등록")
        self.btn_run.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        self.btn_run.clicked.connect(self.run_register)
        self.btn_run.setEnabled(False)
        bar.addWidget(self.lbl_cnt); bar.addWidget(self.progress); bar.addWidget(self.btn_run)
        r_vbox.addLayout(bar)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left); splitter.addWidget(right)
        splitter.setSizes([400, 600])
        layout.addWidget(splitter)
        self.load_campaigns()

    def load_campaigns(self):
        self.combo_camp.clear()
        try:
            camps = api.get_campaigns()
            for c in camps: self.combo_camp.addItem(c['name'], c['nccCampaignId'])
        except: pass

    def on_campaign_changed(self):
        self.adgroups_map = {}
        cid = self.combo_camp.currentData()
        if not cid: return
        try:
            grps = api.get_adgroups(cid)
            for g in grps: self.adgroups_map[g['name'].strip()] = g['nccAdgroupId']
        except: pass

    def generate_preview(self):
        self.table.setRowCount(0); self.generated_list = []; self.btn_run.setEnabled(False)
        map_txt = self.txt_mapping.toPlainText().strip()
        kwd_txt = self.txt_kwd.toPlainText().strip()
        if not map_txt or not kwd_txt: return QMessageBox.warning(self, "경고", "입력값 확인")
        
        kwds = [k.strip() for k in re.split(r'[,\n]+', kwd_txt) if k.strip()]
        lines = map_txt.splitlines()
        tasks = []
        for line in lines:
            line = line.strip()
            if not line: continue
            match = re.match(r"^([^(]+)(?:\(([^)]+)\))?$", line)
            if match:
                gname = match.group(1).strip()
                subs = match.group(2)
                gid = self.adgroups_map.get(gname)
                if not gid: 
                    print(f"매칭 실패: {gname}")
                    continue
                geos = [s.strip() for s in subs.split(',') if s.strip()] if subs else [gname]
                for k in kwds:
                    for g in geos:
                        combos = set()
                        if self.chk_ab.isChecked(): combos.add(g+k)
                        if self.chk_ba.isChecked(): combos.add(k+g)
                        if self.chk_b.isChecked(): combos.add(k)
                        for res in combos:
                            tasks.append({'group_name': gname, 'group_id': gid, 'keyword': res})
                            
        self.table.setRowCount(len(tasks))
        for i, t in enumerate(tasks):
            self.table.setItem(i, 0, QTableWidgetItem(t['group_name']))
            self.table.setItem(i, 1, QTableWidgetItem(t['keyword']))
            self.table.setItem(i, 2, QTableWidgetItem("대기"))
            self.table.setItem(i, 3, QTableWidgetItem("-"))
            t['row'] = i
            self.generated_list.append(t)
        self.lbl_cnt.setText(f"총 {len(tasks)}개")
        if tasks: self.btn_run.setEnabled(True)
        else: QMessageBox.warning(self, "알림", "매칭된 그룹 없음")

    def run_register(self):
        if not self.generated_list: return
        if QMessageBox.question(self, "확인", f"{len(self.generated_list)}개 등록?") != QMessageBox.StandardButton.Yes: return
        self.btn_run.setEnabled(False)
        self.worker = KeywordRegisterWorker(self.generated_list)
        self.worker.log_signal.connect(self.update_log)
        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.result_signal.connect(self.on_finished)
        self.worker.start()

    def update_log(self, row, status, msg):
        item = QTableWidgetItem(status)
        color = "green" if "성공" in status else ("orange" if "진행" in status or "전환" in status or "복제" in status else "red")
        item.setForeground(QBrush(QColor(color)))
        self.table.setItem(row, 2, item)
        self.table.setItem(row, 3, QTableWidgetItem(msg))
        self.table.scrollToItem(self.table.item(row, 0))

    def on_finished(self, success, fail):
        QMessageBox.information(self, "완료", f"성공: {success}건\n실패: {fail}건\n\n(실패 0건이 아닐 경우 로그 확인 필요)")
        self.btn_run.setEnabled(True)
        self.worker = None