from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from PyQt6.QtCore import Qt

class UserGuideWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("background-color: white; padding: 20px; font-family: 'Malgun Gothic'; font-size: 14px;")
        
        # HTML 형식의 사용 설명서
        html_content = """
        <h1 style="color: #03c75a;">📌 네이버 광고 관리 솔루션 사용 가이드</h1>
        <hr>
        <h3>1. 🚀 자동 입찰 (Auto Bid)</h3>
        <ul>
            <li><b>목표:</b> 원하는 순위를 유지하면서 입찰가를 자동으로 조절합니다.</li>
            <li><b>사용법:</b> 좌측 목록에서 그룹을 선택하고, 우측에서 목표 순위와 최대 입찰가를 설정한 후 '저장'하세요.</li>
            <li>설정이 완료되면 체크박스를 켜고 <b>'입찰 시작'</b> 버튼을 누르세요.</li>
        </ul>
        <br>
        <h3>2. 🎨 소재 관리 (Creative)</h3>
        <ul>
            <li>소재를 쉽고 빠르게 생성하고, 다른 그룹으로 복사할 수 있습니다.</li>
            <li><b>일괄 복사:</b> 잘 만든 소재 하나를 수백 개의 그룹에 한 번에 등록해보세요.</li>
        </ul>
        <br>
        <h3>3. 🔗 확장 소재 & ✨ 키워드 확장</h3>
        <ul>
            <li><b>확장 소재:</b> 전화번호, 위치 정보를 누락된 그룹에 일괄 적용합니다.</li>
            <li><b>키워드 확장:</b> '지역명 + 키워드' 조합을 자동으로 생성하여 대량 등록합니다.</li>
        </ul>
        <hr>
        <p style="color: #666;">문의사항이 있으시면 관리자에게 연락 바랍니다.</p>
        """
        
        self.browser.setHtml(html_content)
        layout.addWidget(self.browser)