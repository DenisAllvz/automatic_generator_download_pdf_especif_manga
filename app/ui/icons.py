"""Simple line icons drawn by Qt, independent of old Windows stock artwork."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPainterPath


def icon(name, color='#8b8fa3'):
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if name == 'home':
        path = QPainterPath()
        path.moveTo(5, 14); path.lineTo(16, 5); path.lineTo(27, 14)
        painter.drawPath(path)
        painter.drawRoundedRect(QRectF(8, 14, 16, 13), 2, 2)
        painter.drawLine(14, 27, 14, 20); painter.drawLine(18, 20, 18, 27)
    elif name == 'cloud':
        painter.drawArc(QRectF(4, 12, 12, 13), 90*16, 180*16)
        painter.drawArc(QRectF(10, 5, 15, 18), 0, 180*16)
        painter.drawArc(QRectF(20, 13, 10, 12), -90*16, 180*16)
        painter.drawLine(9, 25, 25, 25)
        painter.drawLine(17, 13, 17, 27)
        painter.drawLine(13, 17, 17, 13)
        painter.drawLine(17, 13, 21, 17)
    elif name == 'book':
        painter.drawRoundedRect(QRectF(6, 5, 21, 23), 2, 2)
        painter.drawLine(11, 5, 11, 28)
        painter.drawLine(16, 11, 23, 11)
        painter.drawLine(16, 16, 23, 16)
    elif name == 'add':
        painter.drawRoundedRect(QRectF(6, 6, 20, 20), 6, 6)
        painter.drawLine(16, 11, 16, 21); painter.drawLine(11, 16, 21, 16)
    elif name == 'download':
        painter.drawLine(16, 5, 16, 21)
        painter.drawLine(10, 15, 16, 21); painter.drawLine(16, 21, 22, 15)
        painter.drawLine(6, 23, 6, 27); painter.drawLine(6, 27, 26, 27); painter.drawLine(26, 27, 26, 23)
    elif name == 'check':
        painter.drawEllipse(QRectF(5, 5, 22, 22))
        painter.drawLine(10, 16, 14, 20); painter.drawLine(14, 20, 22, 12)
    else:
        for y, x in ((9, 12), (16, 21), (23, 14)):
            painter.drawLine(5, y, x-3, y); painter.drawLine(x+3, y, 27, y)
            painter.drawEllipse(QRectF(x-3, y-3, 6, 6))
    painter.end()
    return QIcon(pixmap)
