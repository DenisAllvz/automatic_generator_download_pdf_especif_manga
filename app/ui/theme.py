def stylesheet(dark):
    bg, surface, raised, text, muted, border, hover = (
        ('#111318', '#1b1e27', '#222631', '#f0f1f7', '#989eaf', '#2b303d', '#2a2e3b') if dark else
        ('#f1f4fa', '#ffffff', '#f7f8fc', '#202433', '#737b91', '#e4e7ef', '#eceefa'))
    accent = '#8576ff' if dark else '#6550e8'
    return f'''
        QWidget {{ color: {text}; font-family: 'Segoe UI'; font-size: 13px; }}
        QMainWindow, QWidget#main, QWidget#page {{ background: {bg}; }}
        QWidget#sidebar {{ background: {surface}; border-right: 1px solid {border}; }}
        QLabel {{ background: transparent; border: none; }}
        QLabel#brand {{ font-size: 21px; font-weight: 700; padding: 12px 6px; }}
        QLabel#eyebrow {{ color: {accent}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
        QLabel#heading {{ font-size: 30px; font-weight: 700; }}
        QLabel#caption, QLabel#statLabel {{ color: {muted}; }}
        QLabel#heroTitle {{ color: white; font-size: 30px; font-weight: 700; }}
        QLabel#heroCaption {{ color: #e5e0ff; font-size: 14px; }}
        QFrame#hero {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #6754d8,stop:1 #384b93); border-radius: 18px; }}
        QFrame#statCard, QFrame#queueHero {{ background: {surface}; border: 1px solid {border}; border-radius: 14px; }}
        QLabel#statValue {{ font-size: 29px; font-weight: 700; }}
        QLabel#sectionTitle {{ font-size: 16px; font-weight: 600; }}
        QPushButton {{ background: {raised}; border: 1px solid {border}; border-radius: 8px; padding: 10px 16px; font-weight: 600; }}
        QPushButton:hover {{ background: {hover}; border-color: {accent}; }}
        QPushButton#primary {{ background: {accent}; border-color: {accent}; color: white; }}
        QPushButton#primary:hover {{ background: #7663ed; }}
        QPushButton#primary:disabled {{ background: {raised}; border-color: {border}; color: {muted}; }}
        QPushButton#heroButton {{ background: white; border: none; color: #5747c6; }}
        QPushButton#link {{ background: transparent; color: {accent}; border: none; padding: 8px; }}
        QPushButton:disabled {{ color: {muted}; background: {raised}; border-color: {border}; }}
        QLineEdit, QSpinBox, QComboBox {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; padding: 10px; selection-background-color: {accent}; }}
        QLineEdit:focus, QComboBox:focus {{ border-color: {accent}; }}
        QListWidget, QTableWidget, QTextEdit {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; outline: none; selection-background-color: {hover}; }}
        QListWidget#navigation {{ background: transparent; border: none; }}
        QListWidget#navigation::item {{ padding: 14px 10px; margin: 3px 8px; border: none; border-radius: 8px; color: {muted}; }}
        QListWidget#navigation::item:selected {{ background: {raised}; color: {accent}; font-weight: 600; }}
        QListWidget#navigation::item:hover {{ background: {hover}; }}
        QListWidget#coverGrid::item {{ border: none; border-radius: 12px; padding: 6px; margin: 6px; }}
        QListWidget#coverGrid::item:selected {{ background: {hover}; }}
        QListWidget::item {{ padding: 11px; border-bottom: 1px solid {border}; }}
        QTableWidget::item {{ padding: 10px; border-bottom: 1px solid {border}; }}
        QTableWidget::item:selected {{ background: {hover}; color: {text}; }}
        QHeaderView::section {{ background: {surface}; padding: 14px 10px; border: none; border-bottom: 1px solid {border}; color: {muted}; font-size: 11px; font-weight: 600; }}
        QProgressBar {{ background: {raised}; border: none; border-radius: 5px; text-align: center; min-height: 10px; }}
        QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
        QProgressBar#rowProgress {{ margin: 16px 18px; min-height: 18px; font-size: 11px; }}
        QFrame#progressCell {{ background: {surface}; border: none; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: {raised}; width: 14px; margin: 1px; border-radius: 6px; }}
        QScrollBar::handle:vertical {{ background: {muted}; border-radius: 5px; min-height: 40px; }}
        QScrollBar::handle:vertical:hover {{ background: {accent}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QMenu {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; padding: 6px; }}
        QMenu::item {{ padding: 9px 24px; border-radius: 5px; }}
        QMenu::item:selected {{ background: {hover}; }}
        QCheckBox {{ spacing: 8px; }}
        QStatusBar {{ background: {bg}; color: {muted}; font-size: 11px; }}
    '''
