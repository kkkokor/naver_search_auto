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

from api.api_client import api

import requests
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

class ImageLoaderWorker(QThread):
    """워커 스레드에서 QImage로 다운로드 후 메인 스레드에서 QPixmap 변환"""
    image_loaded = pyqtSignal(QImage)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            resp = requests.get(self.url, timeout=10)
            if resp.status_code == 200:
                img = QImage()
                if img.loadFromData(resp.content):
                    self.image_loaded.emit(img)
                else:
                    print(f"[IMG_WORKER] QImage loadFromData failed for: {self.url}")
            else:
                print(f"[IMG_WORKER] HTTP {resp.status_code} for: {self.url}")
        except Exception as e:
            print(f"[IMG_WORKER] Image load failed: {e}")

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
        
        # [버그 패치] 그룹이 전부 할당되어 배포관리 영역이 그려지지 않아도 hasattr 에러 방지용 초기화
        self.check_boxes = []
        self.workers = []
        
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

        # 전체 끄기/켜기 버튼
        btn_toggle_all = QPushButton("⏸ 전체끄기")
        btn_toggle_all.setStyleSheet("background-color: #fd7e14; color: white; font-weight: bold; padding: 3px 10px; font-size: 11px;")
        btn_toggle_all.setFixedHeight(28)
        btn_toggle_all.clicked.connect(lambda: self.toggle_all_items(True))
        header.addWidget(btn_toggle_all)

        btn_enable_all = QPushButton("▶ 전체켜기")
        btn_enable_all.setStyleSheet("background-color: #20c997; color: white; font-weight: bold; padding: 3px 10px; font-size: 11px;")
        btn_enable_all.setFixedHeight(28)
        btn_enable_all.clicked.connect(lambda: self.toggle_all_items(False))
        header.addWidget(btn_enable_all)

        # 전체 삭제 버튼
        btn_delete_all = QPushButton("🗑 전체삭제")
        btn_delete_all.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; padding: 3px 10px; font-size: 11px;")
        btn_delete_all.setFixedHeight(28)
        btn_delete_all.clicked.connect(self.delete_all_items)
        header.addWidget(btn_delete_all)

        layout.addLayout(header)

        # 2. 본문 미리보기
        content_frame = QFrame()
        content_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 5px; padding: 10px;")
        c_layout = QVBoxLayout(content_frame)
        self.render_preview(c_layout)
        layout.addWidget(content_frame)

        # 3. 적용 관리 (사용 중인 그룹)
        used_groups = [g for g in self.all_groups if g['nccAdgroupId'] in self.used_group_ids]
        if used_groups:
            mgmt_box = QGroupBox(f"적용 관리 (사용 중 그룹 {len(used_groups)}개)")
            mgmt_box.setStyleSheet("QGroupBox { font-weight: bold; color: #666; border: 1px solid #eee; margin-top: 10px; }")
            mgmt_layout = QVBoxLayout(mgmt_box)

            mgmt_scroll = QScrollArea()
            mgmt_scroll.setFixedHeight(100)
            mgmt_scroll.setWidgetResizable(True)
            mgmt_scroll.setStyleSheet("border: none;")

            mgmt_chk_widget = QWidget()
            mgmt_chk_layout = QVBoxLayout(mgmt_chk_widget)
            mgmt_chk_layout.setContentsMargins(0,0,0,0)

            self.mgmt_check_all = QCheckBox("전체 선택")
            self.mgmt_check_all.clicked.connect(self.toggle_mgmt_all)
            mgmt_chk_layout.addWidget(self.mgmt_check_all)

            self.mgmt_check_boxes = []
            for grp in used_groups:
                chk = QCheckBox(grp['name'])
                chk.setProperty('groupId', grp['nccAdgroupId'])
                self.mgmt_check_boxes.append(chk)
                mgmt_chk_layout.addWidget(chk)

            mgmt_scroll.setWidget(mgmt_chk_widget)
            mgmt_layout.addWidget(mgmt_scroll)

            btn_row = QHBoxLayout()
            btn_sel_toggle = QPushButton("⏸ 선택 끄기")
            btn_sel_toggle.setStyleSheet("background-color: #fd7e14; color: white; font-weight: bold;")
            btn_sel_toggle.clicked.connect(lambda: self.toggle_selected_items(True))
            btn_row.addWidget(btn_sel_toggle)

            btn_sel_enable = QPushButton("▶ 선택 켜기")
            btn_sel_enable.setStyleSheet("background-color: #20c997; color: white; font-weight: bold;")
            btn_sel_enable.clicked.connect(lambda: self.toggle_selected_items(False))
            btn_row.addWidget(btn_sel_enable)

            btn_sel_delete = QPushButton("🗑 선택 삭제")
            btn_sel_delete.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")
            btn_sel_delete.clicked.connect(self.delete_selected_items)
            btn_row.addWidget(btn_sel_delete)

            mgmt_layout.addLayout(btn_row)
            layout.addWidget(mgmt_box)

        # 4. 배포 관리
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
        
        # [수정] HEADLINE, DESCRIPTION 우선 처리
        if ext_type == 'HEADLINE':
            hl = data.get('headline', '제목 없음')
            layout.addWidget(QLabel(f"📝 헤드라인: {hl}"))
            if self.data.get('businessChannelId'):
                layout.addWidget(QLabel(f"🏢 비즈채널: {self.data.get('channelName', '-')}"))
            return
            
        elif ext_type == 'DESCRIPTION':
            desc = data.get('description', '설명 없음')
            layout.addWidget(QLabel(f"📄 설명: {desc}"))
            if self.data.get('businessChannelId'):
                layout.addWidget(QLabel(f"🏢 비즈채널: {self.data.get('channelName', '-')}"))
            return

        elif ext_type in ['POWER_LINK_IMAGE', 'IMAGE_SUB_LINKS']:
            layout.addWidget(QLabel("🖼️ 이미지 확장소재"))

            NAVER_CDN_BASE = "https://searchad-phinf.pstatic.net"

            # 1단계: 이미지 관련 키에서 직접 추출
            IMAGE_KEYS = {'imagePath', 'imageUrl', 'image_url', 'filePath',
                          'thumbnailUrl', 'thumbnail', 'iconPath', 'iconUrl'}

            def extract_image_values(obj, collected=None):
                """이미지 관련 키의 값을 직접 추출 + 모든 문자열 URL도 수집"""
                if collected is None:
                    collected = {'keyed': [], 'urls': []}
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in IMAGE_KEYS and isinstance(v, str) and v:
                            collected['keyed'].append(v)
                        else:
                            extract_image_values(v, collected)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_image_values(item, collected)
                elif isinstance(obj, str) and obj.startswith("http"):
                    collected['urls'].append(obj)
                return collected

            extracted = extract_image_values(data)

            # 이미지 URL 조합: keyed 값 우선, 그 다음 일반 URL
            image_urls = []
            for val in extracted['keyed']:
                if val.startswith("http"):
                    image_urls.append(val)
                elif val.startswith("/"):
                    # 상대경로 -> CDN 베이스 URL 붙이기
                    image_urls.append(NAVER_CDN_BASE + val)
                else:
                    # 그 외 경로도 CDN 시도
                    image_urls.append(NAVER_CDN_BASE + "/" + val)

            # 일반 URL에서도 이미지 추가 (중복 제거)
            for u in extracted['urls']:
                if u not in image_urls:
                    image_urls.append(u)

            print(f"[DEBUG_IMG] type={ext_type} keyed={extracted['keyed']} urls={extracted['urls']} final={image_urls}", flush=True)

            if image_urls:
                for img_url in image_urls[:3]:
                    img_lbl = QLabel("이미지 로딩 중...")
                    img_lbl.setFixedSize(260, 260)
                    img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    img_lbl.setStyleSheet("border: 1px solid #ccc; background-color: #fff; padding: 4px;")
                    layout.addWidget(img_lbl)

                    def on_image_loaded(qimage, lbl=img_lbl):
                        if not qimage.isNull():
                            px = QPixmap.fromImage(qimage)
                            lbl.setPixmap(px.scaled(
                                250, 250,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation
                            ))
                        else:
                            lbl.setText("이미지 로드 실패")

                    worker = ImageLoaderWorker(img_url)
                    worker.image_loaded.connect(on_image_loaded)
                    self.workers.append(worker)
                    worker.start()

            # 항상 raw data 표시 (디버깅용)
            debug_lbl = QLabel(f"[raw] {json.dumps(data, ensure_ascii=False)}")
            debug_lbl.setWordWrap(True)
            debug_lbl.setStyleSheet("color: #999; font-size: 9px; margin-top: 4px;")
            layout.addWidget(debug_lbl)
            
        elif self.data.get('businessChannelId'):
            layout.addWidget(QLabel(f"🏢 비즈채널: {self.data.get('channelName') or self.data.get('businessChannelId')}"))
            if ext_type == 'WEBSITE_INFO':
                layout.addWidget(QLabel(f"🔗 URL: {self.data.get('channelUrl', '-') }"))
            elif ext_type == 'PHONE':
                ph = data.get('phoneNumber') or "번호 없음 (채널 정보만 있음)"
                layout.addWidget(QLabel(f"📞 전화번호: {ph}"))

        elif ext_type == 'PHONE':
            layout.addWidget(QLabel(f"📞 전화번호: {data.get('phoneNumber', '번호 없음')}"))

        elif ext_type == 'SUB_LINKS':
            links = data if isinstance(data, list) else data.get('links', [])
            layout.addWidget(QLabel(f"🔗 서브링크 ({len(links)}개)"))
            for link in links[:5]:
                name = link.get('name') or link.get('linkName', '제목없음')
                url = link.get('final') or link.get('subLink', '')
                layout.addWidget(QLabel(f" - {name}: {url}"))

        else:
            lbl = QLabel(f"Content: {str(data)}")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

    def toggle_all(self):
        state = self.btn_check_all.isChecked()
        for chk in self.check_boxes:
            chk.setChecked(state)

    def toggle_mgmt_all(self):
        state = self.mgmt_check_all.isChecked()
        for chk in self.mgmt_check_boxes:
            chk.setChecked(state)

    def _get_ext_ids_for_groups(self, group_ids):
        """특정 그룹들에 해당하는 nccAdExtensionId 리스트 반환"""
        gid_set = set(group_ids)
        return [item['nccAdExtensionId'] for item in self.data['items'] if item['ownerId'] in gid_set]

    def delete_all_items(self):
        ext_ids = [item['nccAdExtensionId'] for item in self.data['items']]
        if not ext_ids:
            return
        if QMessageBox.question(self, "확인", f"이 확장소재를 모든 그룹({len(ext_ids)}건)에서 삭제하시겠습니까?") == QMessageBox.StandardButton.Yes:
            self.parent_widget.run_bulk_delete(ext_ids)

    def toggle_all_items(self, user_lock):
        ext_ids = [item['nccAdExtensionId'] for item in self.data['items']]
        if not ext_ids:
            return
        action = "끄기" if user_lock else "켜기"
        if QMessageBox.question(self, "확인", f"이 확장소재를 모든 그룹({len(ext_ids)}건) {action} 하시겠습니까?") == QMessageBox.StandardButton.Yes:
            self.parent_widget.run_bulk_toggle(ext_ids, user_lock)

    def delete_selected_items(self):
        if not hasattr(self, 'mgmt_check_boxes'):
            return
        selected_gids = [chk.property('groupId') for chk in self.mgmt_check_boxes if chk.isChecked()]
        if not selected_gids:
            QMessageBox.warning(self, "경고", "삭제할 그룹을 선택해주세요.")
            return
        ext_ids = self._get_ext_ids_for_groups(selected_gids)
        if ext_ids and QMessageBox.question(self, "확인", f"선택한 {len(ext_ids)}건을 삭제하시겠습니까?") == QMessageBox.StandardButton.Yes:
            self.parent_widget.run_bulk_delete(ext_ids)

    def toggle_selected_items(self, user_lock):
        if not hasattr(self, 'mgmt_check_boxes'):
            return
        selected_gids = [chk.property('groupId') for chk in self.mgmt_check_boxes if chk.isChecked()]
        if not selected_gids:
            QMessageBox.warning(self, "경고", "대상 그룹을 선택해주세요.")
            return
        ext_ids = self._get_ext_ids_for_groups(selected_gids)
        action = "끄기" if user_lock else "켜기"
        if ext_ids and QMessageBox.question(self, "확인", f"선택한 {len(ext_ids)}건을 {action} 하시겠습니까?") == QMessageBox.StandardButton.Yes:
            self.parent_widget.run_bulk_toggle(ext_ids, user_lock)

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
        
        # 일괄 등록 버튼 (NEW)
        self.btn_bulk_register_multi = QPushButton("✅ 선택한 항목 모두 일괄 등록하기")
        self.btn_bulk_register_multi.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; font-size: 14px; padding: 12px; margin-bottom: 5px; border-radius: 6px;")
        self.btn_bulk_register_multi.clicked.connect(self.on_bulk_register_multi_clicked)
        self.btn_bulk_register_multi.setVisible(False)
        layout.addWidget(self.btn_bulk_register_multi)

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
                    print(f"[DEBUG_EXT] Type Found: {t}, ID: {ext.get('nccAdExtensionId')}", flush=True)
                    # HEADLINE, DESCRIPTION 등 문제 타입 상세 출력
                if t in ['HEADLINE', 'DESCRIPTION', 'VIEW', 'BLOG', 'CAFE', 'POST', 'POWER_CONTENT', 'POWER_LINK_IMAGE', 'IMAGE_SUB_LINKS']:
                    print(f"[DEBUG_EXT_CONTENT] {t} -> extension: {ext.get('extension')} / adExtension: {ext.get('adExtension')}", flush=True)
                    print(f"[DEBUG_EXT_FULL] {t} -> full data: {json.dumps(ext, ensure_ascii=False)}", flush=True)
                seen_types.add(t)
                
                # [수정] GET 응답에서는 'adExtension' 필드에 실제 데이터가 들어있음 ('extension' 아님)
                content_key = json.dumps(ext.get('adExtension') or {}, sort_keys=True)
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
                        'content': ext.get('adExtension') or {},
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
            self.btn_bulk_register_multi.setVisible(False)
        else:
            self.btn_bulk_register_multi.setVisible(True)

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
                
                # [수정] 응답 검증 - 'nccAdExtensionId'가 있어야 성공
                if isinstance(res, dict) and 'nccAdExtensionId' in res:
                    success_cnt += 1
                elif isinstance(res, dict) and res.get('error'):
                    # 실제 에러인 경우만 로그 출력
                    print(f"[EXT_COPY_FAIL] Type:{ext_data['type']} Group:{gid} Res:{res}", flush=True)
                    fail_cnt += 1
                else:
                    # 성공이지만 예상치 못한 응답 구조
                    print(f"[EXT_COPY_WARN] Type:{ext_data['type']} Group:{gid} Unexpected Res:{res}", flush=True)
                    success_cnt += 1
                    fail_cnt += 1

            except Exception as e:
                print(f"[EXT_COPY_ERR] Group:{gid} Type:{ext_data['type']} Exception:{e}", flush=True)
                fail_cnt += 1
            
            self.progress_bar.setValue(int((i+1)/total * 100))
            QApplication.processEvents()
                
        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "완료", f"작업이 완료되었습니다.\n성공: {success_cnt}건\n실패: {fail_cnt}건\n(실패 사유는 로그를 확인하세요)")
        self.on_campaign_changed()

    def run_bulk_delete(self, ext_ids):
        success_cnt = 0
        fail_cnt = 0
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        total = len(ext_ids)

        for i, eid in enumerate(ext_ids):
            try:
                time.sleep(1.0)
                res = api.delete_extension(eid)
                if res is not None and not (isinstance(res, dict) and res.get('error')):
                    success_cnt += 1
                else:
                    print(f"[EXT_DEL_FAIL] ID:{eid} Res:{res}", flush=True)
                    fail_cnt += 1
            except Exception as e:
                print(f"[EXT_DEL_ERR] ID:{eid} Exception:{e}", flush=True)
                fail_cnt += 1

            self.progress_bar.setValue(int((i+1)/total * 100))
            QApplication.processEvents()

        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "삭제 완료", f"삭제 완료\n성공: {success_cnt}건\n실패: {fail_cnt}건")
        self.on_campaign_changed()

    def run_bulk_toggle(self, ext_ids, user_lock):
        action = "끄기" if user_lock else "켜기"
        success_cnt = 0
        fail_cnt = 0
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        total = len(ext_ids)

        for i, eid in enumerate(ext_ids):
            try:
                time.sleep(1.0)
                res = api.toggle_extension(eid, user_lock)
                if res is not None and not (isinstance(res, dict) and res.get('error')):
                    success_cnt += 1
                else:
                    print(f"[EXT_TOGGLE_FAIL] ID:{eid} Lock:{user_lock} Res:{res}", flush=True)
                    fail_cnt += 1
            except Exception as e:
                print(f"[EXT_TOGGLE_ERR] ID:{eid} Exception:{e}", flush=True)
                fail_cnt += 1

            self.progress_bar.setValue(int((i+1)/total * 100))
            QApplication.processEvents()

        self.progress_bar.setVisible(False)
        QMessageBox.information(self, f"{action} 완료", f"{action} 완료\n성공: {success_cnt}건\n실패: {fail_cnt}건")
        self.on_campaign_changed()

    def on_bulk_register_multi_clicked(self):
        from PyQt6.QtWidgets import QMessageBox
        tasks = []
        for i in range(self.scroll_vbox.count()):
            widget = self.scroll_vbox.itemAt(i).widget()
            if isinstance(widget, ExtensionGroupCard):
                for chk in widget.check_boxes:
                    if chk.isChecked():
                        gid = chk.property('groupId')
                        tasks.append({"groupId": gid, "ext_data": widget.data})
                        
        if not tasks:
            QMessageBox.warning(self, "경고", "선택된 확장소재-그룹 항목이 없습니다.")
            return

        if QMessageBox.question(self, "진행 확인", f"총 {len(tasks)}건의 확장소재 복사 작업을 일괄 진행하시겠습니까?") != QMessageBox.StandardButton.Yes:
            return

        self.run_bulk_copy_multi(tasks)

    def run_bulk_copy_multi(self, tasks):
        from PyQt6.QtWidgets import QApplication, QMessageBox
        import time
        success_cnt = 0
        fail_cnt = 0
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        total = len(tasks)
        
        for i, task in enumerate(tasks):
            gid = task["groupId"]
            ext_data = task["ext_data"]
            try:
                time.sleep(1.0)
                
                res = api.create_extension(
                    owner_id=gid,
                    type_str=ext_data['type'],
                    content_dict=ext_data['content'],
                    channel_id=ext_data.get('businessChannelId')
                )
                
                if isinstance(res, dict) and 'nccAdExtensionId' in res:
                    success_cnt += 1
                elif isinstance(res, dict) and res.get('error'):
                    print(f"[EXT_COPY_FAIL] Type:{ext_data['type']} Group:{gid} Res:{res}", flush=True)
                    fail_cnt += 1
                else:
                    success_cnt += 1
                    fail_cnt += 1
            except Exception as e:
                print(f"[EXT_COPY_ERR] Group:{gid} Type:{ext_data['type']} Exception:{e}", flush=True)
                fail_cnt += 1
            
            self.progress_bar.setValue(int((i+1)/total * 100))
            QApplication.processEvents()
                
        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "완료", f"일괄 등록이 완료되었습니다.\n성공: {success_cnt}건\n실패: {fail_cnt}건\n(실패 사유는 콘솔 로그 참조)")
        self.on_campaign_changed()