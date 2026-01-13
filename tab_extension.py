import sys
import json
import time
import concurrent.futures
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QScrollArea, QFrame, QMessageBox, QGroupBox, 
    QCheckBox, QProgressBar, QSplitter, QTabWidget, QGridLayout,
    QApplication, QDialog
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QFont, QColor

from api_client import api

# -------------------------------------------------------------------------
# [커스텀 위젯] 확장 소재 그룹 카드
# -------------------------------------------------------------------------
class ExtensionGroupCard(QFrame):
    def __init__(self, ext_group_data, all_adgroups, parent_widget):
        super().__init__()
        self.data = ext_group_data
        self.all_groups = all_adgroups 
        self.parent_widget = parent_widget
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            ExtensionGroupCard {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                margin-bottom: 10px;
            }
            ExtensionGroupCard:hover {
                border: 1px solid #6610f2;
            }
        """)
        
        # 사용 중인 그룹 ID 집합
        self.used_group_ids = set(self.data['ownerIds'])
        
        # [수정됨] nccAdGroupId -> nccAdgroupId (소문자 g)
        self.unused_groups = [g for g in self.all_groups if g['nccAdgroupId'] not in self.used_group_ids]
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. 헤더
        header = QHBoxLayout()
        type_lbl = QLabel(self.data['type'])
        type_lbl.setStyleSheet("background-color: #e2e6ea; color: #495057; padding: 3px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;")
        header.addWidget(type_lbl)
        
        usage_percent = int(len(self.used_group_ids) / len(self.all_groups) * 100) if self.all_groups else 0
        usage_color = "#28a745" if not self.unused_groups else "#dc3545"
        usage_text = "✅ 모든 그룹 적용됨" if not self.unused_groups else f"⚠️ {len(self.unused_groups)}개 그룹 미사용"
        
        status_lbl = QLabel(usage_text)
        status_lbl.setStyleSheet(f"color: {usage_color}; font-weight: bold; font-size: 12px;")
        header.addWidget(status_lbl)
        header.addStretch()
        layout.addLayout(header)
        
        # 2. 본문 미리보기
        content_frame = QFrame()
        content_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 5px; padding: 10px;")
        c_layout = QVBoxLayout(content_frame)
        self.render_preview(c_layout)
        layout.addWidget(content_frame)
        
        # 3. 배포 관리
        if self.unused_groups:
            exp_box = QGroupBox(f"배포 관리 (미사용 그룹 {len(self.unused_groups)}개)")
            exp_box.setStyleSheet("QGroupBox { font-weight: bold; color: #666; border: 1px solid #eee; margin-top: 10px; }")
            exp_layout = QVBoxLayout(exp_box)
            
            scroll = QScrollArea()
            scroll.setFixedHeight(100)
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("border: none;")
            
            chk_widget = QWidget()
            self.chk_layout = QVBoxLayout(chk_widget)
            self.chk_layout.setContentsMargins(0,0,0,0)
            self.check_boxes = []
            
            self.btn_check_all = QCheckBox("전체 선택")
            self.btn_check_all.clicked.connect(self.toggle_all)
            self.chk_layout.addWidget(self.btn_check_all)
            
            for grp in self.unused_groups:
                chk = QCheckBox(grp['name'])
                # [수정됨] nccAdGroupId -> nccAdgroupId
                chk.setProperty('groupId', grp['nccAdgroupId'])
                self.check_boxes.append(chk)
                self.chk_layout.addWidget(chk)
                
            scroll.setWidget(chk_widget)
            exp_layout.addWidget(scroll)
            
            btn_copy = QPushButton("선택한 그룹에 복사하기")
            btn_copy.setStyleSheet("background-color: #6610f2; color: white; font-weight: bold;")
            btn_copy.clicked.connect(self.copy_extension)
            exp_layout.addWidget(btn_copy)
            
            layout.addWidget(exp_box)

    def render_preview(self, layout):
        data = self.data['content']
        ext_type = self.data['type']
        
        # [디버깅] 실제 데이터 구조 확인용
        # layout.addWidget(QLabel(f"Type: {ext_type}"))
        # layout.addWidget(QLabel(f"Raw: {str(data)}"))

        if self.data.get('businessChannelId'):
            layout.addWidget(QLabel(f"🏢 비즈채널: {self.data.get('channelName') or self.data.get('businessChannelId')}"))
            if ext_type == 'WEBSITE_INFO':
                layout.addWidget(QLabel(f"🔗 URL: {self.data.get('channelUrl', '-') }"))
                
            # [수정] PHONE 타입이라도 실제 phoneNumber는 extension 딕셔너리 안에 있음
            if ext_type == 'PHONE':
                ph = data.get('phoneNumber') or "번호 없음 (채널 정보만 있음)"
                layout.addWidget(QLabel(f"📞 전화번호: {ph}"))
        
        elif ext_type == 'PHONE':
            # 채널 ID가 없을 수도 있음 (순수 텍스트?) -> PHONE은 채널 필수임
            layout.addWidget(QLabel(f"📞 전화번호: {data.get('phoneNumber', '번호 없음')}"))
            
        elif ext_type == 'SUB_LINKS':
            layout.addWidget(QLabel(f"🔗 서브링크 ({len(data.get('links', []))}개)"))
            for link in data.get('links', [])[:5]:
                # linkName이 네이버 API 표준임
                layout.addWidget(QLabel(f" - {link.get('linkName', '제목없음')}: {link.get('subLink', '')}"))
                
        elif ext_type in ['POWER_LINK_IMAGE', 'IMAGE_SUB_LINKS']:
            layout.addWidget(QLabel("🖼️ 이미지 확장소재"))
            # 이미지 파일 경로나 URL 표시 시도
            # API 구조에 따라 'images' 배열 안에 있을 수 있음
            imgs = data.get('images', [])
            if imgs:
                url = imgs[0].get('imageUrl', 'URL 없음')
                layout.addWidget(QLabel(f"URL: {url}"))
            else:
                path = data.get('imagePath', '-')
                layout.addWidget(QLabel(f"Path: {path}"))
            
        else:
            # 기타 타입 (ADDITIONAL_LINK 등)
            # 일단 전체 덤프해서 보여주기
            lbl = QLabel(f"Content: {str(data)}")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

    def toggle_all(self):
        state = self.btn_check_all.isChecked()
        for chk in self.check_boxes:
            chk.setChecked(state)

    def copy_extension(self):
        targets = [chk.property('groupId') for chk in self.check_boxes if chk.isChecked()]
        if not targets:
            QMessageBox.warning(self, "경고", "복사할 대상을 선택해주세요.")
            return
            
        if QMessageBox.question(self, "확인", f"{len(targets)}개 그룹에 복사하시겠습니까?") == QMessageBox.StandardButton.Yes:
            self.parent_widget.run_bulk_copy(targets, self.data)

# -------------------------------------------------------------------------
# [메인 위젯] 확장 소재 관리 탭
# -------------------------------------------------------------------------
class ExtensionManagerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.grouped_extensions = [] 
        self.all_adgroups = []
        self.channels = []
        self.init_ui()
        QTimer.singleShot(100, self.load_channels)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 컨트롤 영역
        ctrl_layout = QHBoxLayout()
        self.combo_camp = QComboBox()
        self.combo_camp.setPlaceholderText("분석할 캠페인 선택")
        self.combo_camp.currentIndexChanged.connect(self.on_campaign_changed)
        
        btn_refresh = QPushButton("새로고침 / 분석 시작")
        btn_refresh.clicked.connect(self.load_campaigns)
        
        ctrl_layout.addWidget(QLabel("대상 캠페인:"))
        ctrl_layout.addWidget(self.combo_camp, 1)
        ctrl_layout.addWidget(btn_refresh)
        layout.addLayout(ctrl_layout)
        
        # 탭 필터
        self.tabs = QTabWidget()
        self.tabs.addTab(QWidget(), "전체 (ALL)")
        self.tabs.addTab(QWidget(), "전화번호 (PHONE)")
        self.tabs.addTab(QWidget(), "위치/플레이스 (PLACE)")
        self.tabs.addTab(QWidget(), "서브링크 (SUB_LINKS)")
        self.tabs.addTab(QWidget(), "이미지 (IMAGES)")
        self.tabs.currentChanged.connect(self.render_list)
        layout.addWidget(self.tabs)
        
        # 리스트 영역
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #f1f3f5; border: 1px solid #ddd;")
        
        self.scroll_content = QWidget()
        self.scroll_vbox = QVBoxLayout(self.scroll_content)
        self.scroll_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.load_campaigns()

    def load_channels(self):
        try: self.channels = api.get_biz_channels()
        except: pass

    def load_campaigns(self):
        self.combo_camp.clear()
        try:
            camps = api.get_campaigns()
            for c in camps:
                self.combo_camp.addItem(c['name'], c['nccCampaignId'])
        except Exception as e:
            QMessageBox.warning(self, "오류", f"데이터 로드 실패: {e}")

    def on_campaign_changed(self):
        camp_id = self.combo_camp.currentData()
        if not camp_id: return
        self.analyze_extensions(camp_id)

    def analyze_extensions(self, camp_id):
        self.clear_list()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        try:
            # 1. 광고그룹 가져오기
            self.all_adgroups = api.get_adgroups(camp_id)
            if not self.all_adgroups:
                self.progress_bar.setVisible(False)
                return

            raw_exts = []
            
            # 2. [수정됨] 멀티스레딩으로 속도 개선 (기존 순차처리 -> 병렬처리)
            total = len(self.all_adgroups)
            
            # 캠페인 레벨 확장소재도 포함 (1회 호출)
            camp_exts = api.get_extensions(camp_id)
            if camp_exts: raw_exts.extend(camp_exts)
            
            # 헬퍼 함수
            def fetch_ext(grp):
                # [안전장치] 너무 빠른 동시 호출 방지 (랜덤 딜레이 미세 추가 가능하지만, requests pool이 처리함)
                # 필요시 time.sleep(0.1) 추가
                return api.get_extensions(grp['nccAdgroupId'])

            # 병렬 실행 (최대 10개 스레드)
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(fetch_ext, grp): grp for grp in self.all_adgroups}
                
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    try:
                        exts = future.result()
                        if exts: raw_exts.extend(exts)
                    except Exception as e:
                        print(f"Extension fetch failed: {e}")
                    
                    # 진행률 업데이트
                    self.progress_bar.setValue(int((i+1)/total * 100))
                    QApplication.processEvents() # UI 응답성 유지

            self.progress_bar.setVisible(False)
            
            # 3. 그룹핑 로직
            # [디버깅] 발견된 확장소재 타입 로깅
            seen_types = set()
            
            groups = {}
            for ext in raw_exts:
                t = ext['type']
                if t not in seen_types:
                    # [DEBUG] 처음 보는 타입이면 샘플 데이터 출력
                    print(f"[DEBUG_EXT] Type Found: {t}, ID: {ext.get('adExtensionId')}", flush=True)
                    # VIEW 타입 등은 헤드라인 관련 이슈가 있을 수 있어 구조 확인 필요
                    if t in ['VIEW', 'BLOG', 'CAFE', 'POST', 'POWER_CONTENT']:
                        print(f"[DEBUG_EXT_DANGER] {t} Content: {ext.get('extension')}", flush=True)
                seen_types.add(t)
                
                content_key = json.dumps(ext.get('extension') or {}, sort_keys=True)
                channel_id = ext.get('pcChannelId') or ext.get('mobileChannelId') or ''
                unique_key = f"{t}|{content_key}|{channel_id}"
                
                if unique_key not in groups:
                    ch_name = channel_id
                    ch_url = ''
                    if channel_id:
                        found_ch = next((c for c in self.channels if c['nccBusinessChannelId'] == channel_id), None)
                        if found_ch:
                            ch_name = found_ch['name']
                            ch_url = found_ch.get('channelKey', '')

                    groups[unique_key] = {
                        'type': ext['type'],
                        'content': ext.get('extension') or {},
                        'businessChannelId': channel_id,
                        'channelName': ch_name,
                        'channelUrl': ch_url,
                        'ownerIds': [],
                        'items': []
                    }
                
                groups[unique_key]['ownerIds'].append(ext['ownerId'])
                groups[unique_key]['items'].append(ext)
            
            self.progress_bar.setVisible(False)
            print(f"[DEBUG] Found Extension Types in Campaign {camp_id}: {seen_types}")
            
            self.grouped_extensions = list(groups.values())
            self.render_list()
            
        except Exception as e:
            self.progress_bar.setVisible(False)
            QMessageBox.critical(self, "오류", f"분석 중 오류 발생: {e}")

    def render_list(self):
        self.clear_list()
        
        current_tab_idx = self.tabs.currentIndex()
        target_types = []
        if current_tab_idx == 1: target_types = ['PHONE']
        elif current_tab_idx == 2: target_types = ['PLACE', 'LOCATION']
        elif current_tab_idx == 3: target_types = ['SUB_LINKS']
        elif current_tab_idx == 4: target_types = ['POWER_LINK_IMAGE', 'IMAGE_SUB_LINKS']
        
        cnt = 0
        for group in self.grouped_extensions:
            if target_types and group['type'] not in target_types:
                continue
            
            card = ExtensionGroupCard(group, self.all_adgroups, self)
            self.scroll_vbox.addWidget(card)
            cnt += 1
            
        if cnt == 0:
            lbl = QLabel("해당하는 확장소재가 없습니다.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.scroll_vbox.addWidget(lbl)

    def clear_list(self):
        while self.scroll_vbox.count():
            item = self.scroll_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def run_bulk_copy(self, target_group_ids, ext_data):
        success_cnt = 0
        fail_cnt = 0
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        total = len(target_group_ids)
        
        for i, gid in enumerate(target_group_ids):
            try:
                # [속도 조절] 네이버 API 1010/1014 에러 방지 (1.0초 대기)
                time.sleep(1.0)
                
                res = api.create_extension(
                    owner_id=gid,
                    type_str=ext_data['type'],
                    content_dict=ext_data['content'],
                    channel_id=ext_data['businessChannelId']
                )
                
                # [응답 검증] adExtensionId가 있어야 성공
                if isinstance(res, dict) and 'adExtensionId' in res:
                    success_cnt += 1
                else:
                    # 실패 로그 출력 (에러 메시지 확인용)
                    print(f"[EXT_COPY_FAIL] Type:{ext_data['type']} Group:{gid} Res:{res}", flush=True)
                    fail_cnt += 1

            except Exception as e:
                print(f"[EXT_COPY_ERR] Group:{gid} Type:{ext_data['type']} Exception:{e}", flush=True)
                fail_cnt += 1
            
            self.progress_bar.setValue(int((i+1)/total * 100))
            QApplication.processEvents()
                
        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "완료", f"작업이 완료되었습니다.\n성공: {success_cnt}건\n실패: {fail_cnt}건\n(실패 사유는 로그를 확인하세요)")
        self.on_campaign_changed()