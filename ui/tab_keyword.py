import sys
import re
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QTextEdit, QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QMessageBox, QGroupBox, QCheckBox, QSplitter,
    QProgressBar, QTabWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from api.api_client import api

# -------------------------------------------------------------------------
# [작업 스레드] 스마트 키워드 등록 (워터폴 + 강력한 검증 및 에러 핸들링)
# -------------------------------------------------------------------------
class KeywordRegisterWorker(QThread):
    # Signals must be defined at class level
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
            
            # 1. 초기 그룹 ID 기준 작업 분류 (Classifier)
            grouped_tasks = {}
            for task in self.task_list:
                gid = task['group_id']
                if gid not in grouped_tasks:
                    grouped_tasks[gid] = []
                grouped_tasks[gid].append(task)
            
            current_progress = 0
            
            # 각 초기 그룹별로 처리 시작 (Iterate Tasks)
            for initial_gid, tasks in grouped_tasks.items():
                if not self.is_running: break
                
                # Get Original Group Info
                try:
                    original_grp_info = api.get_adgroup(initial_gid)
                except Exception as e:
                    original_grp_info = None

                if not original_grp_info or 'error' in original_grp_info:
                    self.log_batch(tasks, "실패", "그룹 정보 조회 불가")
                    fail_cnt += len(tasks)
                    current_progress += len(tasks)
                    self.progress_signal.emit(current_progress, total)
                    continue

                # Set Navigation Info
                navigate_gid = initial_gid
                navigate_name = original_grp_info['name']
                campaign_id = original_grp_info['nccCampaignId']
                pc_channel_id = original_grp_info.get('pcChannelId')
                mobile_channel_id = original_grp_info.get('mobileChannelId')
                adgroup_type = original_grp_info.get('adgroupType', 'WEB_SITE')
                
                # Base Name Extraction
                base_name = re.sub(r'_\d+$', '', navigate_name)
                
                # Next Group Index Calculation
                next_group_index = 1
                if navigate_name != base_name:
                    try:
                        next_group_index = int(navigate_name.split('_')[-1]) + 1
                    except:
                        next_group_index = 1

                # [중요] 전체 관련 그룹의 기존 키워드 수집 (중복 방지)
                all_existing_keywords = set()
                try:
                    all_campaign_groups = api.get_adgroups(campaign_id)
                    if isinstance(all_campaign_groups, list):
                        for grp in all_campaign_groups:
                            grp_name = grp.get('name', '')
                            # base_name으로 시작하는 모든 그룹의 키워드 수집
                            if grp_name.startswith(base_name):
                                grp_id = grp['nccAdgroupId']
                                grp_kwds = api.get_keywords(grp_id)
                                if isinstance(grp_kwds, list):
                                    for k in grp_kwds:
                                        all_existing_keywords.add(k['keyword'].replace(" ", "").upper())
                    self.log_batch(tasks, "준비", f"기존 키워드 {len(all_existing_keywords)}개 확인")
                except Exception as e:
                    self.log_batch(tasks, "경고", f"기존 키워드 조회 실패: {e}")

                # Task Queues (전체 중복 제거)
                keyword_queue = [t['keyword'] for t in tasks if t['keyword'].replace(" ", "").upper() not in all_existing_keywords]
                task_queue = [t for t in tasks if t['keyword'].replace(" ", "").upper() not in all_existing_keywords]
                
                # 이미 등록된 키워드들은 스킵으로 처리
                already_exist_count = len(tasks) - len(task_queue)
                if already_exist_count > 0:
                    self.log_batch(tasks[:already_exist_count], "스킵", "이미 등록됨")
                    success_cnt += already_exist_count

                loop_safety_counter = 0

                while len(keyword_queue) > 0 and self.is_running:
                    loop_safety_counter += 1
                    if loop_safety_counter > 50: # Prevent infinite loop of group creations
                         self.log_batch(task_queue, "중단", "그룹 생성 반복 횟수 초과 (50회)")
                         fail_cnt += len(keyword_queue)
                         break

                    # ---------------------------------------------------------
                    # [Step 1] Capacity Check
                    # ---------------------------------------------------------
                    time.sleep(0.5) 
                    existing_kwds = api.get_keywords(navigate_gid)
                    
                    if isinstance(existing_kwds, dict) and existing_kwds.get('error'):
                        self.log_batch(task_queue, "대기", "키워드 수 조회 실패. 재시도...")
                        time.sleep(2.0)
                        continue 
                    elif isinstance(existing_kwds, list):
                        current_count = len(existing_kwds)
                    else:
                        time.sleep(2.0)
                        continue

                    # [중요] 중복 키워드 필터링 (현재 그룹 + 전체 추적 세트)
                    if isinstance(existing_kwds, list):
                        exist_set = {k['keyword'].replace(" ", "").upper() for k in existing_kwds}
                        # 전체 추적 세트와 현재 그룹 키워드를 합쳐서 중복 체크
                        combined_exist_set = all_existing_keywords | exist_set
                        
                        # 큐에서 이미 존재하는 것들은 제거
                        filtered_keyword_queue = []
                        filtered_task_queue = []
                        for i, k in enumerate(keyword_queue):
                            k_upper = k.replace(" ", "").upper()
                            if k_upper not in combined_exist_set:
                                filtered_keyword_queue.append(k)
                                filtered_task_queue.append(task_queue[i])
                        
                        keyword_queue = filtered_keyword_queue
                        task_queue = filtered_task_queue
                    
                    if not keyword_queue:
                         # 현재 그룹에서 할 게 없으면 다음 로직(확장 등)으로 넘어가거나 종료
                         # 하지만 Capacity가 남아있는데 큐가 비었다면? -> 이미 다 등록된 것 -> Loop 종료
                         break

                    current_count = len(existing_kwds) if isinstance(existing_kwds, list) else 0
                    capacity = 1000 - current_count
                    
                    # ---------------------------------------------------------
                    # [Step 2] Register if Capacity > 0
                    # ---------------------------------------------------------
                    if capacity > 0:
                        register_chunk = keyword_queue[:capacity]
                        current_chunk_tasks = task_queue[:capacity]
                        
                        time.sleep(1.0) 
                        
                        res = api.create_keywords_bulk(navigate_gid, register_chunk)
                        
                        # [Result Validation]
                        if isinstance(res, list) and len(res) > 0:
                            n_success = len(res)
                            self.log_batch(current_chunk_tasks[:n_success], "성공", f"{navigate_name} 등록함")
                            success_cnt += n_success
                            
                            # 성공한 키워드를 전체 추적 세트에 추가
                            for kwd in register_chunk[:n_success]:
                                all_existing_keywords.add(kwd.replace(" ", "").upper())
                            
                            keyword_queue = keyword_queue[n_success:]
                            task_queue = task_queue[n_success:]
                            
                            # 키워드가 남아있으면 다시 Step 1로 돌아가서 현재 그룹 capacity 재확인
                            if keyword_queue:
                                continue
                        
                        elif isinstance(res, dict) and res.get('error'):
                            # API Error (Validation or System)
                            err_code = res.get('code')
                            err_msg = res.get('data', {}).get('message', '알 수 없음')
                            self.log_batch(current_chunk_tasks, "실패", f"Err {err_code}: {err_msg}")
                            
                            # CRITICAL: If registration fails for a chunk, we must skip these keywords 
                            # or stop to prevent creating new groups infinitely for the SAME bad keywords.
                            # Here we treat them as failed and remove from queue
                            fail_cnt += len(register_chunk)
                            keyword_queue = keyword_queue[len(register_chunk):]
                            task_queue = task_queue[len(register_chunk):]
                            
                        elif isinstance(res, list) and len(res) == 0:
                             # Returned empty list despite sending -> Validation failed for all
                             self.log_batch(current_chunk_tasks, "실패", "키워드 등록 실패 (검증 미통과)")
                             fail_cnt += len(register_chunk)
                             keyword_queue = keyword_queue[len(register_chunk):]
                             task_queue = task_queue[len(register_chunk):]

                    if not keyword_queue:
                        break

                    # ---------------------------------------------------------
                    # [Step 3] Waterfall Expansion (현재 그룹이 꽉 찬 경우에만)
                    # ---------------------------------------------------------
                    # capacity가 0이면 현재 그룹이 꽉 찼으므로 다음 그룹으로 이동
                    found_next_group = False
                    retry_limit = 0 
                    
                    while not found_next_group and self.is_running and retry_limit < 100:
                        retry_limit += 1
                        target_name = f"{base_name}_{next_group_index}"
                        self.log_batch(task_queue, "이동중", f"{target_name} 탐색...")
                        
                        # [Find]
                        time.sleep(0.5)
                        all_grps = api.get_adgroups(campaign_id)
                        
                        target_grp = None
                        if isinstance(all_grps, list):
                            target_grp = next((g for g in all_grps if g['name'].strip() == target_name), None)
                        
                        if target_grp:
                            # Found existing group
                            navigate_gid = target_grp['nccAdgroupId']
                            navigate_name = target_grp['name']
                            found_next_group = True
                            self.log_batch(task_queue, "전환", f"기존 그룹({navigate_name})로 이동")
                        
                        else:
                            # [Create]
                            time.sleep(1.0)
                            new_grp_res = api.create_adgroup(
                                campaign_id, target_name,
                                pc_channel_id, mobile_channel_id,
                                adgroup_type
                            )
                            
                            if new_grp_res and isinstance(new_grp_res, dict) and 'nccAdgroupId' in new_grp_res:
                                navigate_gid = new_grp_res['nccAdgroupId']
                                navigate_name = new_grp_res['name']
                                found_next_group = True
                                self.log_batch(task_queue, "생성", f"새 그룹({navigate_name}) 생성")
                                
                                # [Asset Clone]
                                self.clone_assets(initial_gid, navigate_gid)
                            
                            elif isinstance(new_grp_res, dict) and new_grp_res.get('error'):
                                code = str(new_grp_res.get('code'))
                                if code == '3710':
                                    self.log_batch(task_queue, "재시도", "이름 중복. 그룹 재검색...")
                                    time.sleep(1.0) 
                                    continue 
                                elif code == '1014':
                                    self.log_batch(task_queue, "대기", "API 1014... 5초 대기")
                                    time.sleep(5.0)
                                    continue
                                else:
                                    self.log_batch(task_queue, "확장오류", f"생성실패 {code}")
                                    next_group_index += 1
                            else:
                                next_group_index += 1
                        
                        if found_next_group:
                            next_group_index += 1
                        
                    if not found_next_group:
                        self.log_batch(task_queue, "실패", "그룹 확장 실패")
                        fail_cnt += len(keyword_queue)
                        keyword_queue = [] 
                        break
                
                current_progress += len(tasks)
                self.progress_signal.emit(current_progress, total)

            self.result_signal.emit(success_cnt, fail_cnt)
            
        except Exception as e:
            print(f"Worker Exception: {e}")
            # Ensure signals work even in error
            try: self.result_signal.emit(success_cnt, fail_cnt)
            except: pass

    def clone_assets(self, src_gid, dst_gid):
        """ 자산(소재, 확장소재) 복제 - 개선된 로직 """
        try:
            # 1. 확장소재 (Refer to tab_extension.py)
            time.sleep(1.0) 
            exts = api.get_extensions(src_gid)
            if isinstance(exts, list):
                for ext in exts:
                    if ext.get("type") in ["IMAGE_SUB_LINKS", "POWER_LINK_IMAGE"]: continue
                    
                    try:
                        # [수정] tab_extension.py 방식 적용: content 및 channel_id 안전하게 추출
                        content = ext.get('extension') or {}
                        
                        # PHONE, SUB_LINKS 등은 content 필수
                        if ext.get("type") in ["PHONE", "SUB_LINKS"] and not content:
                            continue

                        channel_id = ext.get('pcChannelId') or ext.get('mobileChannelId')
                        
                        time.sleep(1.0) # [속도 조절] 0.5s -> 1.0s
                        api.create_extension(dst_gid, ext['type'], content, channel_id)
                    except:
                        pass

            # 2. 소재 (Ads)
            time.sleep(1.0)
            ads = api.get_ads(src_gid)
            if isinstance(ads, list):
                for ad in ads:
                    try:
                        c = ad.get('ad')
                        if not c: continue
                        
                        # [오류 해결 1010] headline 등 필수 필드가 없으면 스킵
                        if not c.get('headline') or not c.get('description'):
                            continue
                            
                        time.sleep(1.0) # [속도 조절] 0.5s -> 1.0s
                        api.create_ad(
                            dst_gid, 
                            c.get('headline'), 
                            c.get('description'), 
                            c.get('pc', {}).get('final'), 
                            c.get('mobile', {}).get('final')
                        )
                    except: pass
        except Exception as e:
            print(f"Asset Clone Error: {e}")

    def log_batch(self, tasks, status, msg):
        for t in tasks:
            self.log_signal.emit(t['row'], status, msg)
    
    def stop(self):
        self.is_running = False

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
        layout = QVBoxLayout(self)
        
        # 탭 위젯 생성
        tabs = QTabWidget()
        
        # [탭 1] 키워드 확장 (기존 기능)
        tab_expand = QWidget()
        self.init_expand_tab(tab_expand)
        tabs.addTab(tab_expand, "🔄 키워드 확장")
        
        # [탭 2] 중복 키워드 삭제 (새 기능)
        tab_cleanup = QWidget()
        self.init_cleanup_tab(tab_cleanup)
        tabs.addTab(tab_cleanup, "🧹 중복 키워드 삭제")
        
        layout.addWidget(tabs)
        
        # 캠페인 목록 로드
        self.load_campaigns()
    
    def init_expand_tab(self, parent):
        """기존 키워드 확장 UI"""
        layout = QHBoxLayout(parent)
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
        btn_gen.setMinimumSize(120, 35)
        btn_gen.setStyleSheet("background-color: #6610f2; color: white; font-size: 11pt; font-weight: bold; padding: 8px;")
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
        self.btn_run.setMinimumSize(100, 35)
        self.btn_run.setStyleSheet("background-color: #28a745; color: white; font-size: 11pt; font-weight: bold; padding: 8px;")
        self.btn_run.clicked.connect(self.run_register)
        self.btn_run.setEnabled(False)
        bar.addWidget(self.lbl_cnt); bar.addWidget(self.progress); bar.addWidget(self.btn_run)
        r_vbox.addLayout(bar)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left); splitter.addWidget(right)
        splitter.setSizes([400, 600])
        layout.addWidget(splitter)
    
    def init_cleanup_tab(self, parent):
        """새로운 중복 키워드 삭제 UI"""
        layout = QVBoxLayout(parent)
        
        # 상단 설명
        desc = QLabel("묶음 그룹(예: 인천, 인천_1, 인천_2) 내에서 중복된 키워드를 찾아 삭제합니다.")
        desc.setStyleSheet("color: #6c757d; font-size: 11px; padding: 10px;")
        layout.addWidget(desc)
        
        # 캠페인 선택
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("대상 캠페인:"))
        self.cleanup_combo_camp = QComboBox()
        self.cleanup_combo_camp.currentIndexChanged.connect(self.on_cleanup_campaign_changed)
        h1.addWidget(self.cleanup_combo_camp)
        h1.addStretch()
        layout.addLayout(h1)
        
        # 그룹 베이스 네임 입력
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("그룹 베이스명:"))
        self.cleanup_txt_basename = QTextEdit()
        self.cleanup_txt_basename.setPlaceholderText("예: 인천\n부천\n서울")
        self.cleanup_txt_basename.setFixedHeight(100)
        h2.addWidget(self.cleanup_txt_basename)
        layout.addLayout(h2)
        
        # 버튼
        h3 = QHBoxLayout()
        btn_scan = QPushButton("🔍 중복 키워드 검색")
        btn_scan.setMinimumSize(150, 35)
        btn_scan.setStyleSheet("background-color: #0d6efd; color: white; font-size: 11pt; font-weight: bold; padding: 8px;")
        btn_scan.clicked.connect(self.scan_duplicates)
        h3.addWidget(btn_scan)
        
        self.btn_cleanup_delete = QPushButton("🗑️ 선택 항목 삭제")
        self.btn_cleanup_delete.setMinimumSize(140, 35)
        self.btn_cleanup_delete.setStyleSheet("background-color: #dc3545; color: white; font-size: 11pt; font-weight: bold; padding: 8px;")
        self.btn_cleanup_delete.clicked.connect(self.delete_duplicates)
        self.btn_cleanup_delete.setEnabled(False)
        h3.addWidget(self.btn_cleanup_delete)
        h3.addStretch()
        layout.addLayout(h3)
        
        # 결과 테이블
        self.cleanup_table = QTableWidget()
        self.cleanup_table.setColumnCount(4)
        self.cleanup_table.setHorizontalHeaderLabels(["선택", "그룹명", "키워드", "키워드 ID"])
        self.cleanup_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.cleanup_table)
        
        # 상태 바
        self.cleanup_status = QLabel("대기 중...")
        self.cleanup_status.setStyleSheet("color: #6c757d; padding: 5px;")
        layout.addWidget(self.cleanup_status)

    def load_campaigns(self):
        self.combo_camp.clear()
        self.cleanup_combo_camp.clear()
        try:
            camps = api.get_campaigns()
            for c in camps:
                self.combo_camp.addItem(c['name'], c['nccCampaignId'])
                self.cleanup_combo_camp.addItem(c['name'], c['nccCampaignId'])
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
                    # 1. 지역+키워드 조합 (체크된 경우에만)
                    if self.chk_ab.isChecked() or self.chk_ba.isChecked():
                        for g in geos:
                            if self.chk_ab.isChecked():
                                tasks.append({'group_name': gname, 'group_id': gid, 'keyword': g+k})
                            if self.chk_ba.isChecked():
                                tasks.append({'group_name': gname, 'group_id': gid, 'keyword': k+g})
                    
                    # 2. 키워드만 (체크된 경우 한 번만 추가)
                    if self.chk_b.isChecked():
                        tasks.append({'group_name': gname, 'group_id': gid, 'keyword': k})
                            
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
    
    # ===== 중복 키워드 삭제 기능 =====
    
    def on_cleanup_campaign_changed(self):
        """클린업 탭 캠페인 변경"""
        self.cleanup_table.setRowCount(0)
        self.cleanup_status.setText("대기 중...")
        self.btn_cleanup_delete.setEnabled(False)
    
    def scan_duplicates(self):
        """중복 키워드 검색"""
        campaign_id = self.cleanup_combo_camp.currentData()
        if not campaign_id:
            return QMessageBox.warning(self, "경고", "캠페인을 선택하세요")
        
        basenames = self.cleanup_txt_basename.toPlainText().strip()
        if not basenames:
            return QMessageBox.warning(self, "경고", "그룹 베이스명을 입력하세요")
        
        basename_list = [b.strip() for b in basenames.split('\n') if b.strip()]
        
        self.cleanup_status.setText("검색 중...")
        self.cleanup_table.setRowCount(0)
        self.btn_cleanup_delete.setEnabled(False)
        
        try:
            # 전체 그룹 조회
            all_groups = api.get_adgroups(campaign_id)
            if not isinstance(all_groups, list):
                self.cleanup_status.setText("그룹 조회 실패")
                return
            
            duplicates = []  # (그룹명, 키워드, 키워드ID, 키워드 정규화)
            
            # 각 베이스명별로 처리
            for basename in basename_list:
                self.cleanup_status.setText(f"검색 중: {basename}...")
                
                # 해당 베이스명으로 시작하는 모든 그룹 찾기
                related_groups = []
                for grp in all_groups:
                    grp_name = grp.get('name', '')
                    # basename 또는 basename_숫자 형태인 그룹들
                    if grp_name == basename or re.match(f"^{re.escape(basename)}_\\d+$", grp_name):
                        related_groups.append(grp)
                
                if len(related_groups) < 2:
                    continue  # 묶음 그룹이 아니면 스킵
                
                # 각 그룹의 키워드 수집
                all_keywords = {}  # {정규화된키워드: [(그룹명, 키워드원본, ID), ...]}
                
                for grp in related_groups:
                    grp_id = grp['nccAdgroupId']
                    grp_name = grp['name']
                    
                    keywords = api.get_keywords(grp_id)
                    if not isinstance(keywords, list):
                        continue
                    
                    for kwd in keywords:
                        kwd_text = kwd['keyword']
                        kwd_id = kwd['nccKeywordId']
                        normalized = kwd_text.replace(" ", "").upper()
                        
                        if normalized not in all_keywords:
                            all_keywords[normalized] = []
                        
                        all_keywords[normalized].append((grp_name, kwd_text, kwd_id))
                    
                    time.sleep(0.3)  # API 부하 방지
                
                # 중복 찾기 (2개 이상 그룹에 존재하는 키워드)
                for normalized, occurrences in all_keywords.items():
                    if len(occurrences) > 1:
                        # 첫 번째 그룹은 유지, 나머지는 중복으로 표시
                        for i, (grp_name, kwd_text, kwd_id) in enumerate(occurrences):
                            if i > 0:  # 첫 번째 제외
                                duplicates.append((grp_name, kwd_text, kwd_id, normalized))
            
            # 테이블에 표시
            self.cleanup_table.setRowCount(len(duplicates))
            for i, (grp_name, kwd_text, kwd_id, normalized) in enumerate(duplicates):
                # 체크박스
                chk = QCheckBox()
                chk.setChecked(True)
                self.cleanup_table.setCellWidget(i, 0, chk)
                
                self.cleanup_table.setItem(i, 1, QTableWidgetItem(grp_name))
                self.cleanup_table.setItem(i, 2, QTableWidgetItem(kwd_text))
                
                # 키워드 ID를 UserRole에 저장
                id_item = QTableWidgetItem(kwd_id)
                id_item.setData(Qt.ItemDataRole.UserRole, kwd_id)
                self.cleanup_table.setItem(i, 3, id_item)
            
            self.cleanup_status.setText(f"검색 완료: {len(duplicates)}개 중복 키워드 발견")
            
            if duplicates:
                self.btn_cleanup_delete.setEnabled(True)
            else:
                QMessageBox.information(self, "결과", "중복 키워드가 없습니다")
                
        except Exception as e:
            self.cleanup_status.setText(f"오류: {e}")
            QMessageBox.critical(self, "오류", f"검색 중 오류 발생:\n{e}")
    
    def delete_duplicates(self):
        """선택된 중복 키워드 삭제"""
        # 체크된 항목 수집
        to_delete = []
        for i in range(self.cleanup_table.rowCount()):
            chk = self.cleanup_table.cellWidget(i, 0)
            if chk and chk.isChecked():
                kwd_id_item = self.cleanup_table.item(i, 3)
                kwd_id = kwd_id_item.data(Qt.ItemDataRole.UserRole)
                kwd_text = self.cleanup_table.item(i, 2).text()
                grp_name = self.cleanup_table.item(i, 1).text()
                to_delete.append((kwd_id, kwd_text, grp_name, i))
        
        if not to_delete:
            return QMessageBox.warning(self, "경고", "삭제할 항목을 선택하세요")
        
        reply = QMessageBox.question(
            self, "확인", 
            f"{len(to_delete)}개의 키워드를 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self.btn_cleanup_delete.setEnabled(False)
        self.cleanup_status.setText("삭제 중...")
        
        success = 0
        fail = 0
        
        for kwd_id, kwd_text, grp_name, row_idx in to_delete:
            try:
                result = api.delete_keyword(kwd_id)
                if result and not isinstance(result, dict) or (isinstance(result, dict) and not result.get('error')):
                    success += 1
                    # 테이블에서 행 삭제 표시
                    for col in range(4):
                        item = self.cleanup_table.item(row_idx, col)
                        if item:
                            item.setBackground(QBrush(QColor("#d4edda")))
                else:
                    fail += 1
                time.sleep(0.5)  # API 부하 방지
            except Exception as e:
                fail += 1
                print(f"삭제 실패: {kwd_text} ({kwd_id}) - {e}")
        
        self.cleanup_status.setText(f"완료: 성공 {success}건, 실패 {fail}건")
        QMessageBox.information(self, "완료", f"삭제 완료\n\n성공: {success}건\n실패: {fail}건")
        
        # 성공한 행 제거
        self.scan_duplicates()  # 재검색