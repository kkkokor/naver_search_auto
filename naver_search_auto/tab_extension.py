import sys
import json
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
        
        if self.data.get('businessChannelId'):
            layout.addWidget(QLabel(f"🏢 비즈채널: {self.data.get('channelName') or self.data.get('businessChannelId')}"))
            if ext_type == 'WEBSITE_INFO':
                layout.addWidget(QLabel(f"🔗 URL: {self.data.get('channelUrl', '-') }"))
        
        elif ext_type == 'PHONE':
            layout.addWidget(QLabel(f"📞 전화번호: {data.get('phoneNumber', '번호 없음')}"))
            
        elif ext_type == 'SUB_LINKS':
            layout.addWidget(QLabel(f"🔗 서브링크 ({len(data.get('links', []))}개)"))
            for link in data.get('links', [])[:3]:
                layout.addWidget(QLabel(f" - {link.get('linkName')}"))
                
        elif ext_type in ['POWER_LINK_IMAGE', 'IMAGE_SUB_LINKS']:
            layout.addWidget(QLabel("🖼️ 이미지 확장소재 (미리보기 미지원)"))
            path = data.get('imagePath') or (data.get('images')[0]['imageUrl'] if data.get('images') else '-')
            layout.addWidget(QLabel(f"Path: {path}"))
            
        else:
            lbl = QLabel(str(data))
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
            
            # 2. [수정됨] 모든 광고그룹 순회하며 확장소재 수집
            total = len(self.all_adgroups)
            # 캠페인 레벨 확장소재도 포함
            camp_exts = api.get_extensions(camp_id)
            if camp_exts: raw_exts.extend(camp_exts)
            
            for i, grp in enumerate(self.all_adgroups):
                # [수정됨] nccAdgroupId (소문자 g)
                gid = grp['nccAdgroupId'] 
                exts = api.get_extensions(gid)
                if exts: raw_exts.extend(exts)
                
                # 진행률 업데이트 & UI 프리징 방지
                self.progress_bar.setValue(int((i+1)/total * 100))
                QApplication.processEvents()

            self.progress_bar.setVisible(False)
            
            # 3. 그룹핑 로직
            groups = {}
            for ext in raw_exts:
                content_key = json.dumps(ext.get('extension') or {}, sort_keys=True)
                channel_id = ext.get('pcChannelId') or ext.get('mobileChannelId') or ''
                unique_key = f"{ext['type']}|{content_key}|{channel_id}"
                
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
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        total = len(target_group_ids)
        
        for i, gid in enumerate(target_group_ids):
            try:
                api.create_extension(
                    owner_id=gid,
                    type_str=ext_data['type'],
                    content_dict=ext_data['content'],
                    channel_id=ext_data['businessChannelId']
                )
                success_cnt += 1
            except Exception as e:
                print(f"복사 실패 ({gid}): {e}")
            
            self.progress_bar.setValue(int((i+1)/total * 100))
            QApplication.processEvents()
                
        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "완료", f"총 {success_cnt}개 그룹에 복사되었습니다.\n(새로고침을 눌러 확인하세요)")
        self.on_campaign_changed()