import sys
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QLineEdit, QTextEdit, QPushButton, QScrollArea, QFrame, 
    QMessageBox, QGroupBox, QDialog, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QSplitter
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QAction

from api.api_client import api

# -------------------------------------------------------------------------
# [커스텀 위젯] 소재 카드 (리스트에 표시될 아이템)
# -------------------------------------------------------------------------
class AdCard(QFrame):
    def __init__(self, ad_data, parent_widget):
        super().__init__()
        self.ad = ad_data
        self.parent_widget = parent_widget # 부모 위젯 (삭제/수정 요청용)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            AdCard {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
            AdCard:hover {
                border: 1px solid #007bff;
            }
        """)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. 헤더 (상태뱃지 + 버튼)
        header = QHBoxLayout()
        
        # 상태 뱃지 (ON/OFF)
        # userLock이 True면 OFF(중지), False면 ON(노출)
        is_paused = self.ad.get('userLock', False)
        status_text = "OFF (중지)" if is_paused else "ON (노출가능)"
        status_color = "#6c757d" if is_paused else "#28a745"
        
        lbl_status = QLabel(status_text)
        lbl_status.setStyleSheet(f"color: white; background-color: {status_color}; border-radius: 4px; padding: 2px 6px; font-weight: bold; font-size: 11px;")
        header.addWidget(lbl_status)
        header.addStretch()
        
        # 복사 버튼 (입력폼으로 내용 복사)
        btn_copy = QPushButton("내용 복사")
        btn_copy.setMinimumSize(80, 28)
        btn_copy.setStyleSheet("background-color: #f8f9fa; color: #333; border: 1px solid #ccc; font-size: 10pt; padding: 3px;")
        btn_copy.clicked.connect(self.copy_to_form)
        header.addWidget(btn_copy)

        # ON/OFF 토글 버튼
        btn_toggle = QPushButton("켜기" if is_paused else "끄기")
        btn_toggle.setMinimumSize(60, 28)
        btn_toggle.setStyleSheet(f"background-color: {'#28a745' if is_paused else '#ffc107'}; color: {'white' if is_paused else 'black'}; font-size: 10pt; padding: 3px;")
        btn_toggle.clicked.connect(lambda: self.parent_widget.toggle_ad_status(self.ad['nccAdId'], not is_paused))
        header.addWidget(btn_toggle)

        # 삭제 버튼
        btn_del = QPushButton("삭제")
        btn_del.setMinimumSize(60, 28)
        btn_del.setStyleSheet("background-color: #dc3545; color: white; font-size: 10pt; padding: 3px;")
        btn_del.clicked.connect(lambda: self.parent_widget.delete_ad(self.ad['nccAdId']))
        header.addWidget(btn_del)
        
        layout.addLayout(header)
        
        # 2. 본문 (제목, 설명)
        ad_detail = self.ad.get('ad', {})
        if isinstance(ad_detail, str): ad_detail = json.loads(ad_detail) # 혹시 문자열로 오면 파싱
        
        headline = ad_detail.get('headline', '제목 없음')
        desc = ad_detail.get('description', '설명 없음')
        
        lbl_head = QLabel(headline)
        lbl_head.setStyleSheet("color: #007bff; font-weight: bold; font-size: 16px; margin-top: 5px;")
        layout.addWidget(lbl_head)
        
        lbl_desc = QLabel(desc)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #555; font-size: 13px;")
        layout.addWidget(lbl_desc)
        
        # 3. URL 정보
        pc_url = ad_detail.get('pc', {}).get('final', '')
        mo_url = ad_detail.get('mobile', {}).get('final', '')
        
        if pc_url or mo_url:
            url_box = QLabel(f"🔗 {pc_url or mo_url}")
            url_box.setStyleSheet("background-color: #f1f8e9; color: #2e7d32; padding: 4px; border-radius: 4px; font-size: 11px;")
            layout.addWidget(url_box)

    def copy_to_form(self):
        # 부모 위젯의 입력폼에 데이터 채워넣기
        ad_detail = self.ad.get('ad', {})
        self.parent_widget.set_form_data(
            ad_detail.get('headline', ''),
            ad_detail.get('description', ''),
            ad_detail.get('pc', {}).get('final', ''),
            ad_detail.get('mobile', {}).get('final', '')
        )

# -------------------------------------------------------------------------
# [다이얼로그] 소재 일괄 복사 (Bulk Copy)
# -------------------------------------------------------------------------
class BulkCopyDialog(QDialog):
    def __init__(self, source_group_name, source_group_id):
        super().__init__()
        self.setWindowTitle("소재 일괄 복사 (Bulk Copy)")
        self.resize(500, 600)
        self.source_id = source_group_id
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(f"<b>원본 그룹:</b> {source_group_name}"))
        layout.addWidget(QLabel("아래에서 복사할 <b>대상 그룹</b>들을 선택하세요."))
        
        # 타겟 선택 트리
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("캠페인 / 광고그룹")
        layout.addWidget(self.tree)
        
        # 실행 버튼
        self.btn_run = QPushButton("선택한 그룹에 복사하기")
        self.btn_run.setStyleSheet("background-color: #007bff; color: white; padding: 10px; font-weight: bold;")
        self.btn_run.clicked.connect(self.run_copy)
        layout.addWidget(self.btn_run)
        
        # 진행률
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        
        # 로그창
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        
        self.load_targets()

    def load_targets(self):
        self.tree.clear()
        try:
            camps = api.get_campaigns()
            if not camps:
                self.log_view.append("캠페인 목록을 가져올 수 없습니다.")
                return
            
            for c in camps:
                c_item = QTreeWidgetItem(self.tree)
                c_item.setText(0, c['name'])
                # PyQt6에서 ItemIsTristate 제거하고 ItemIsAutoTristate 사용
                c_item.setFlags(c_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                c_item.setCheckState(0, Qt.CheckState.Unchecked)
                
                try:
                    groups = api.get_adgroups(c['nccCampaignId'])
                    if not groups:
                        continue
                    
                    added_count = 0
                    for g in groups:
                        # 원본 그룹만 제외 (같은 캠페인의 다른 그룹들은 표시)
                        if g['nccAdgroupId'] == self.source_id: 
                            continue
                        
                        g_item = QTreeWidgetItem(c_item)
                        g_item.setText(0, g['name'])
                        g_item.setData(0, Qt.ItemDataRole.UserRole, g['nccAdgroupId'])
                        g_item.setFlags(g_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        g_item.setCheckState(0, Qt.CheckState.Unchecked)
                        added_count += 1
                    
                    # 그룹이 하나도 추가되지 않은 캠페인 항목 제거 (원본 그룹만 있는 경우)
                    if added_count == 0:
                        self.tree.invisibleRootItem().removeChild(c_item)
                        
                except Exception as e:
                    print(f"그룹 로드 실패 ({c['name']}): {e}")
                    self.tree.invisibleRootItem().removeChild(c_item)
                    continue
                    
            self.tree.expandAll()
            total_campaigns = self.tree.topLevelItemCount()
            self.log_view.append(f"{total_campaigns}개 캠페인 로드 완료")
        except Exception as e:
            self.log_view.append(f"오류: {e}")
            print(f"캠페인 로드 실패: {e}")

    def get_selected_targets(self):
        targets = []
        iterator = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value()
            gid = item.data(0, Qt.ItemDataRole.UserRole)
            if gid: targets.append(gid)
            iterator += 1
        return targets

    def run_copy(self):
        targets = self.get_selected_targets()
        if not targets:
            QMessageBox.warning(self, "경고", "대상 그룹을 선택해주세요.")
            return
        
        if QMessageBox.question(self, "확인", f"총 {len(targets)}개 그룹에 소재를 복사하시겠습니까?") != QMessageBox.StandardButton.Yes:
            return
            
        self.btn_run.setEnabled(False)
        self.log_view.append("🚀 원본 소재를 불러옵니다...")
        
        # 1. 원본 소재 조회
        source_ads = api.get_ads(self.source_id)
        if not source_ads:
            self.log_view.append("❌ 원본 그룹에 소재가 없습니다.")
            self.btn_run.setEnabled(True)
            return

        total = len(targets)
        success_grp = 0
        
        # 2. 타겟 순회하며 복제
        for i, target_id in enumerate(targets):
            self.log_view.append(f"[{i+1}/{total}] 그룹({target_id})에 복사 중...")
            try:
                for ad in source_ads:
                    ad_content = ad.get('ad') # Dict 형태
                    # 새 광고 생성 (userLock 같은 상태값은 복사 안함, 기본 ON)
                    body = {
                        "type": "TEXT_45",
                        "nccAdgroupId": target_id,
                        "ad": ad_content
                    }
                    api.call_naver("/ncc/ads", method="POST", body=body)
                success_grp += 1
            except Exception as e:
                self.log_view.append(f"   -> 실패: {e}")
            
            self.progress.setValue(int(((i+1)/total)*100))
            QApplication.processEvents() # UI 멈춤 방지
            
        self.log_view.append(f"🏁 완료! 성공: {success_grp}개 그룹")
        self.btn_run.setEnabled(True)
        QMessageBox.information(self, "완료", "복사 작업이 끝났습니다.")

# QTreeWidgetItemIterator import (맨 아래에 있어도 되지만 안전하게)
from PyQt6.QtWidgets import QTreeWidgetItemIterator, QApplication

# -------------------------------------------------------------------------
# [메인 위젯] 소재 관리 탭
# -------------------------------------------------------------------------
class CreativeManagerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.current_ads = [] # 현재 리스트에 있는 광고들

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # 1. 상단 필터 (캠페인 -> 그룹 선택)
        filter_layout = QHBoxLayout()
        self.combo_camp = QComboBox()
        self.combo_camp.setPlaceholderText("캠페인 선택")
        self.combo_camp.currentIndexChanged.connect(self.on_campaign_changed)
        
        self.combo_group = QComboBox()
        self.combo_group.setPlaceholderText("광고그룹 선택")
        self.combo_group.currentIndexChanged.connect(self.on_group_changed)
        
        filter_layout.addWidget(QLabel("캠페인:"))
        filter_layout.addWidget(self.combo_camp, 1)
        filter_layout.addWidget(QLabel("그룹:"))
        filter_layout.addWidget(self.combo_group, 1)
        
        # 새로고침 버튼
        btn_refresh = QPushButton("새로고침")
        btn_refresh.clicked.connect(self.load_campaigns)
        filter_layout.addWidget(btn_refresh)
        
        main_layout.addLayout(filter_layout)
        
        # 2. 메인 컨텐츠 (좌: 입력폼 / 우: 리스트)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # --- [좌측] 입력 폼 ---
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        grp_input = QGroupBox("새 소재 등록 / 수정")
        in_layout = QVBoxLayout()
        
        in_layout.addWidget(QLabel("제목 (Headline)"))
        self.in_head = QLineEdit()
        self.in_head.setPlaceholderText("제목을 입력하세요")
        in_layout.addWidget(self.in_head)
        
        in_layout.addWidget(QLabel("설명 (Description)"))
        self.in_desc = QTextEdit()
        self.in_desc.setPlaceholderText("설명을 입력하세요")
        self.in_desc.setFixedHeight(80)
        in_layout.addWidget(self.in_desc)
        
        in_layout.addWidget(QLabel("PC URL"))
        self.in_pc = QLineEdit()
        self.in_pc.setPlaceholderText("http://...")
        in_layout.addWidget(self.in_pc)

        in_layout.addWidget(QLabel("Mobile URL"))
        self.in_mo = QLineEdit()
        self.in_mo.setPlaceholderText("http://...")
        in_layout.addWidget(self.in_mo)
        
        self.btn_submit = QPushButton("소재 등록하기")
        self.btn_submit.setStyleSheet("background-color: #007bff; color: white; padding: 10px; font-weight: bold; margin-top: 10px;")
        self.btn_submit.clicked.connect(self.create_ad)
        in_layout.addWidget(self.btn_submit)
        
        # 일괄 복사 버튼 (하단에 배치)
        self.btn_bulk = QPushButton("🔄 이 그룹의 소재를 다른 그룹들로 복사")
        self.btn_bulk.setStyleSheet("background-color: #6610f2; color: white; margin-top: 20px;")
        self.btn_bulk.clicked.connect(self.open_bulk_copy)
        in_layout.addWidget(self.btn_bulk)
        
        grp_input.setLayout(in_layout)
        form_layout.addWidget(grp_input)
        
        # --- [우측] 소재 리스트 ---
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ddd;")
        
        self.scroll_content = QWidget()
        self.scroll_vbox = QVBoxLayout(self.scroll_content)
        self.scroll_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll.setWidget(self.scroll_content)
        list_layout.addWidget(self.scroll)
        
        splitter.addWidget(form_widget)
        splitter.addWidget(list_widget)
        splitter.setSizes([300, 600])
        
        main_layout.addWidget(splitter)
        
        # 초기 로드
        self.load_campaigns()

    # --- 데이터 로딩 로직 ---
    def load_campaigns(self):
        self.combo_camp.clear()
        try:
            camps = api.get_campaigns()
            for c in camps:
                self.combo_camp.addItem(c['name'], c['nccCampaignId'])
        except Exception as e:
            pass

    def on_campaign_changed(self):
        self.combo_group.clear()
        camp_id = self.combo_camp.currentData()
        if not camp_id: return
        try:
            groups = api.get_adgroups(camp_id)
            for g in groups:
                self.combo_group.addItem(g['name'], g['nccAdgroupId'])
        except: pass

    def on_group_changed(self):
        group_id = self.combo_group.currentData()
        if not group_id: 
            self.clear_list()
            return
        self.load_ads(group_id)

    def load_ads(self, group_id):
        self.clear_list()
        try:
            ads = api.get_ads(group_id)
            self.current_ads = ads
            if not ads:
                lbl = QLabel("등록된 소재가 없습니다.")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.scroll_vbox.addWidget(lbl)
                return

            for ad in ads:
                card = AdCard(ad, self)
                self.scroll_vbox.addWidget(card)
        except Exception as e:
            QMessageBox.warning(self, "오류", str(e))

    def clear_list(self):
        while self.scroll_vbox.count():
            item = self.scroll_vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    # --- 기능 로직 ---
    def set_form_data(self, head, desc, pc, mo):
        self.in_head.setText(head)
        self.in_desc.setText(desc)
        self.in_pc.setText(pc)
        self.in_mo.setText(mo)

    def create_ad(self):
        group_id = self.combo_group.currentData()
        if not group_id:
            QMessageBox.warning(self, "경고", "광고그룹을 먼저 선택하세요.")
            return
            
        head = self.in_head.text().strip()
        desc = self.in_desc.toPlainText().strip()
        pc = self.in_pc.text().strip()
        mo = self.in_mo.text().strip()
        
        if not head or not desc:
            QMessageBox.warning(self, "경고", "제목과 설명은 필수입니다.")
            return

        if QMessageBox.question(self, "등록", "소재를 등록하시겠습니까?") == QMessageBox.StandardButton.Yes:
            res = api.create_ad(group_id, head, desc, pc, mo)
            if res:
                QMessageBox.information(self, "성공", "소재가 등록되었습니다.")
                self.load_ads(group_id) # 새로고침
                # 입력폼 초기화
                self.in_head.clear()
                self.in_desc.clear()
            else:
                QMessageBox.critical(self, "실패", "등록 중 오류가 발생했습니다.")

    def delete_ad(self, ad_id):
        if QMessageBox.question(self, "삭제", "정말 삭제하시겠습니까?") == QMessageBox.StandardButton.Yes:
            res = api.call_naver(f"/ncc/ads/{ad_id}", method="DELETE")
            if res is not None:
                self.load_ads(self.combo_group.currentData())
            else:
                QMessageBox.critical(self, "오류", "삭제 실패")

    def toggle_ad_status(self, ad_id, target_lock):
        # target_lock: True(중지), False(노출)
        res = api.call_naver(f"/ncc/ads/{ad_id}", method="PUT", params={'fields': 'userLock'}, body={'userLock': target_lock})
        if res:
            self.load_ads(self.combo_group.currentData())
        else:
            QMessageBox.critical(self, "오류", "상태 변경 실패")

    def open_bulk_copy(self):
        group_id = self.combo_group.currentData()
        group_name = self.combo_group.currentText()
        if not group_id:
            QMessageBox.warning(self, "경고", "복사할 원본 그룹을 선택하세요.")
            return
            
        dialog = BulkCopyDialog(group_name, group_id)
        dialog.exec()