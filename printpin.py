"""
PrintPin - fixe seus prints na tela, de forma rapida e minimalista.

Tire um print (Print Screen ou Win+Shift+S). Uma bolinha aparece:
arraste e solte perto de um dos pontos da borda da tela.

No print fixado: passe o mouse para ver o X (fechar) e a alca de tamanho,
arraste o print para mover, o scroll tambem redimensiona.
Fechar a janela principal nao encerra o app: ele fica na bandeja.
"""
import math
import os
import sys
import time

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

# =============================================================================
#  ICONE DO APP  (bandeja do Windows, janela e atalho do .exe)
#
#  >>> PARA TROCAR A IMAGEM: substitua o arquivo "icon.ico" (mesma pasta do
#  >>> printpin.py) por outro .ico com o MESMO NOME e gere o .exe de novo.
#  >>> Converta qualquer PNG/JPG para .ico em sites como convertio.co ou
#  >>> icoconvert.com (escolha varios tamanhos, ex.: 256, 64, 32 e 16 px).
#  >>> Se quiser outro nome de arquivo, mude ICON_FILE abaixo E tambem o
#  >>> nome no build.bat e no .github/workflows/build.yml.
# =============================================================================
ICON_FILE = "icon.ico"

# ----------------------------------------------------------------- constantes
ACCENT = QColor(90, 169, 255)
PAD = 18            # margem transparente ao redor (sombra + botoes)
EDGE = 16           # distancia minima entre o print e a borda da tela
RADIUS = 14         # arredondamento dos cantos do print
DOT_INSET = 26      # distancia dos pontos ate a borda da tela
DOT_SPACING = 84    # espacamento entre os pontos
INSTANCE_NAME = "PrintPin-single-instance"

FLAGS = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
    | Qt.WindowType.WindowDoesNotAcceptFocus
)

TEXT = (
    "Tire um print (Print Screen ou Win+Shift+S).\n"
    "Aparece uma bolinha: arraste e solte perto de um ponto da borda da tela. "
    "O print fica fixado ali.\n\n"
    "No print fixado:\n"
    "• passe o mouse para ver o × (fechar) e a alça de tamanho\n"
    "• arraste a alça, ou use o scroll, para mudar o tamanho\n"
    "• arraste o print para mover para outro ponto\n\n"
    "Fechar esta janela não encerra o app: ele continua na bandeja, "
    "perto do relógio."
)


# -------------------------------------------------------------------- helpers
def dist(a, b):
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def resource_path(name):
    """Caminho de um arquivo, funcionando tanto em .py quanto no .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def mix(e):
    """Mistura branco -> cor de destaque conforme e (0..1)."""
    r = int(255 - (255 - ACCENT.red()) * e)
    g = int(255 - (255 - ACCENT.green()) * e)
    b = int(255 - (255 - ACCENT.blue()) * e)
    return QColor(r, g, b)


def _mask_image(w, h):
    m = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    m.fill(QColor(0, 0, 0, 0))
    return m


def circle_mask(n, rect):
    m = _mask_image(n, n)
    p = QPainter(m)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(rect)
    p.end()
    return m


def rrect_mask(w, h, rect, r):
    m = _mask_image(w, h)
    p = QPainter(m)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255))
    p.drawRoundedRect(rect, r, r)
    p.end()
    return m


def circle_thumb(img, d, dpr):
    """Miniatura circular (recorte central) com anel branco, bordas suaves."""
    n = int(round(d * dpr))
    b = max(2, int(round(3 * dpr)))
    s = min(img.width(), img.height())
    crop = img.copy((img.width() - s) // 2, (img.height() - s) // 2, s, s)
    inner = n - 2 * b
    crop = crop.scaled(
        inner, inner, Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    layer = _mask_image(n, n)
    p = QPainter(layer)
    p.drawImage(b, b, crop)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.drawImage(0, 0, circle_mask(n, QRectF(b, b, inner, inner)))
    p.end()

    out = _mask_image(n, n)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(QRectF(0, 0, n, n))
    p.drawImage(0, 0, layer)
    p.end()
    out.setDevicePixelRatio(dpr)
    return out


def draw_shadow(p, c, r):
    """Sombra suave de um circulo."""
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(1, 11):
        p.setBrush(QColor(0, 0, 0, int(20 * (1 - i / 11) ** 2)))
        rr = r + i * 1.2
        p.drawEllipse(QPointF(c.x(), c.y() + 3), rr, rr)


def draw_shadow_rect(p, rect, r):
    """Sombra suave de um retangulo arredondado."""
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(1, 11):
        p.setBrush(QColor(0, 0, 0, int(20 * (1 - i / 11) ** 2)))
        g = i * 1.2
        p.drawRoundedRect(
            QRectF(rect.x() - g, rect.y() - g + 3, rect.width() + 2 * g, rect.height() + 2 * g),
            r + g, r + g,
        )


def make_dots(avail):
    """Pontos distribuidos ao redor da area util da tela."""
    l, t = avail.left() + DOT_INSET, avail.top() + DOT_INSET
    r, b = avail.right() + 1 - DOT_INSET, avail.bottom() + 1 - DOT_INSET
    pts = []
    for x0, y0, x1, y1 in ((l, t, r, t), (r, t, r, b), (r, b, l, b), (l, b, l, t)):
        n = max(1, round(math.hypot(x1 - x0, y1 - y0) / DOT_SPACING))
        for i in range(n):
            f = i / n
            pts.append(QPointF(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
    return pts


def snap_center(avail, dot, w, h):
    """Centro do print ao encaixar em um ponto (sempre dentro da tela)."""
    hw, hh = w / 2 + EDGE, h / 2 + EDGE
    cx = min(max(dot.x(), avail.left() + hw), avail.right() + 1 - hw)
    cy = min(max(dot.y(), avail.top() + hh), avail.bottom() + 1 - hh)
    return QPointF(cx, cy)


def snap_rect(avail, dot, w, h):
    c = snap_center(avail, dot, w, h)
    fw, fh = int(w) + 2 * PAD, int(h) + 2 * PAD
    return QRect(round(c.x() - fw / 2), round(c.y() - fh / 2), fw, fh)


def screen_at(point):
    return QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()


def make_icon():
    """Icone padrao (usado se o arquivo ICON_FILE nao for encontrado)."""
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(ACCENT)
    p.drawEllipse(QRectF(4, 4, 56, 56))
    p.setBrush(QColor(255, 255, 255))
    p.drawRoundedRect(QRectF(17, 21, 30, 22), 4, 4)
    p.end()
    return QIcon(pm)


def load_icon():
    path = resource_path(ICON_FILE)
    if os.path.exists(path):
        ic = QIcon(path)
        if not ic.isNull():
            return ic
    return make_icon()


def base_window(w):
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


# -------------------------------------------------------------------- overlay
class Overlay(QWidget):
    """Camada transparente (nao captura mouse) com os pontos da borda."""

    RANGE = 230

    def __init__(self):
        super().__init__(None, FLAGS | Qt.WindowType.WindowTransparentForInput)
        base_window(self)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dots, self.energy, self.tenergy = [], [], []
        self.fade = self.fade_t = 0.0
        self.cur = QPointF()
        self.ghost = QPointF()
        self.ghost_t = QPointF()
        self.ghost_w = self.ghost_h = 0.0
        self.size_w = self.size_h = 300
        self.nearest = -1
        self.avail = QRect()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)

    def begin(self, screen, size, g):
        geo = screen.geometry()
        # 1px a menos evita que o Windows trate como "tela cheia"
        self.setGeometry(geo.x(), geo.y(), geo.width(), geo.height() - 1)
        self.avail = screen.availableGeometry()
        self.size_w, self.size_h = size
        self.dots = make_dots(self.avail)
        n = len(self.dots)
        self.energy = [0.0] * n
        self.tenergy = [0.0] * n
        self.cur, self.ghost, self.ghost_t = QPointF(g), QPointF(g), QPointF(g)
        self.ghost_w, self.ghost_h = self.size_w * 0.6, self.size_h * 0.6
        self.fade, self.fade_t = 0.0, 1.0
        self.show()
        self.timer.start()
        self.move_to(g)

    def move_to(self, g):
        if not self.dots:
            return
        self.cur = QPointF(g)
        best, bd = 0, 1e18
        for i, d in enumerate(self.dots):
            dd = (d.x() - g.x()) ** 2 + (d.y() - g.y()) ** 2
            if dd < bd:
                best, bd = i, dd
        self.nearest = best
        for i, d in enumerate(self.dots):
            self.tenergy[i] = max(0.0, 1 - dist(d, g) / self.RANGE) ** 2
        self.tenergy[best] = 1.0
        self.ghost_t = snap_center(self.avail, self.dots[best], self.size_w, self.size_h)

    def end(self):
        self.fade_t = 0.0
        if self.nearest < 0 or not self.dots:
            return None, None
        return self.nearest, QPointF(self.dots[self.nearest])

    def tick(self):
        self.fade += (self.fade_t - self.fade) * 0.25
        for i in range(len(self.energy)):
            self.energy[i] += (self.tenergy[i] - self.energy[i]) * 0.3
        self.ghost = QPointF(
            self.ghost.x() + (self.ghost_t.x() - self.ghost.x()) * 0.28,
            self.ghost.y() + (self.ghost_t.y() - self.ghost.y()) * 0.28,
        )
        self.ghost_w += (self.size_w - self.ghost_w) * 0.25
        self.ghost_h += (self.size_h - self.ghost_h) * 0.25
        if self.fade_t == 0.0 and self.fade < 0.02:
            self.timer.stop()
            self.hide()
            return
        self.update()

    def paintEvent(self, _):
        if self.fade < 0.01 or not self.dots:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(-self.x(), -self.y())  # desenhamos em coordenadas globais
        p.setOpacity(self.fade)

        # retangulo "fantasma" mostrando onde o print vai ficar
        g = self.ghost
        p.setPen(QPen(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 170), 2))
        p.setBrush(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 34))
        p.drawRoundedRect(
            QRectF(g.x() - self.ghost_w / 2, g.y() - self.ghost_h / 2,
                   self.ghost_w, self.ghost_h),
            RADIUS, RADIUS,
        )

        for i, pt in enumerate(self.dots):
            e = self.energy[i]
            v = QPointF(self.cur.x() - pt.x(), self.cur.y() - pt.y())
            d = math.hypot(v.x(), v.y())
            pos = pt if d < 1 else QPointF(
                pt.x() + v.x() / d * 12 * e, pt.y() + v.y() / d * 12 * e
            )
            r = 3.5 + 9 * e
            col = mix(e)
            col.setAlpha(int(150 + 105 * e))
            p.setPen(QPen(QColor(0, 0, 0, int(110 + 40 * e)), 1))
            p.setBrush(col)
            p.drawEllipse(pos, r, r)
            if i == self.nearest:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 200), 2))
                p.drawEllipse(pos, r + 6, r + 6)


# --------------------------------------------------------------------- bolinha
class Bubble(QWidget):
    D = 96

    def __init__(self, ctl, img, screen):
        super().__init__(None, FLAGS)
        base_window(self)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.ctl, self.img, self.scr = ctl, img, screen
        self.pressed = self.dragging = self.closing = False
        self.setToolTip("Arraste até um ponto da borda da tela")
        self.thumb = circle_thumb(img, self.D, screen.devicePixelRatio())

        full = self.D + 2 * PAD
        avail = screen.availableGeometry()
        end = QRect(avail.right() + 1 - full - 24, avail.center().y() - full // 2, full, full)
        start = end.translated(60, 0)
        self.setGeometry(start)
        self.setWindowOpacity(0.0)
        self.show()

        a1 = QPropertyAnimation(self, b"geometry")
        a1.setDuration(320)
        a1.setStartValue(start)
        a1.setEndValue(end)
        a1.setEasingCurve(QEasingCurve.Type.OutCubic)
        a2 = QPropertyAnimation(self, b"windowOpacity")
        a2.setDuration(220)
        a2.setStartValue(0.0)
        a2.setEndValue(1.0)
        self.intro = QParallelAnimationGroup(self)
        self.intro.addAnimation(a1)
        self.intro.addAnimation(a2)
        self.intro.start()

        self.life = QTimer(self)
        self.life.setSingleShot(True)
        self.life.timeout.connect(self.dismiss)
        self.life.start(15000)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_shadow(p, QPointF(self.width() / 2, self.height() / 2), self.D / 2)
        p.drawImage(QPointF(PAD, PAD), self.thumb)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.dismiss()
        elif e.button() == Qt.MouseButton.LeftButton and not self.closing:
            self.intro.stop()
            self.pressed = True
            self.start_g = e.globalPosition()
            self.off = e.globalPosition().toPoint() - self.pos()
            self.life.stop()

    def mouseMoveEvent(self, e):
        if not self.pressed:
            return
        g = e.globalPosition()
        if not self.dragging:
            if dist(g, self.start_g) < 4:
                return
            self.dragging = True
            self.ctl.drag_begin(self)
        self.move(g.toPoint() - self.off)
        self.ctl.drag_move(g)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.pressed:
            return
        self.pressed = False
        if self.dragging:
            self.dragging = False
            self.ctl.drop_bubble(self)
        else:
            self.life.start(8000)

    def dismiss(self):
        if self.closing or self.dragging:
            return
        self.closing = True
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(180)
        a.setStartValue(self.windowOpacity())
        a.setEndValue(0.0)
        a.finished.connect(self.close)
        a.start()
        self._fade = a

    def closeEvent(self, e):
        if self.ctl.bubble is self:
            self.ctl.bubble = None
        e.accept()


# ----------------------------------------------------------------------- pin
class Pin(QWidget):
    """Print fixado: retangulo que acompanha a proporcao da imagem."""

    def __init__(self, ctl, img, rect):
        super().__init__(None, FLAGS)
        base_window(self)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.ctl = ctl
        if max(img.width(), img.height()) > 1800:
            img = img.scaled(
                1800, 1800, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.src = img
        self.aspect = img.width() / img.height()
        self.closing = False
        self.action = None
        self.moved = False
        self.dot_key = None
        self._disc = None
        self._disc_key = None
        self._anim = None
        self._ctrl = 0.0
        self._ca = QVariantAnimation(self)
        self._ca.setDuration(140)
        self._ca.valueChanged.connect(self._set_ctrl)
        self.setGeometry(rect)
        self.show()
        ctl.pins.append(self)

    # ---- geometria
    def rect_w(self):
        return self.width() - 2 * PAD

    def rect_h(self):
        return self.height() - 2 * PAD

    def center_pt(self):
        return QPointF(self.x() + self.width() / 2, self.y() + self.height() / 2)

    def _limits(self):
        a = screen_at(self.geometry().center()).availableGeometry()
        maxw = min(a.width() - 2 * EDGE, (a.height() - 2 * EDGE) * self.aspect)
        minw = min(max(160.0, 70 * self.aspect), maxw)
        return minw, maxw

    def _resize_to(self, center, w):
        lo, hi = self._limits()
        w = min(max(w, lo), hi)
        h = w / self.aspect
        fw, fh = int(round(w)) + 2 * PAD, int(round(h)) + 2 * PAD
        self.setGeometry(round(center.x() - fw / 2), round(center.y() - fh / 2), fw, fh)

    def animate_to(self, rect):
        self._stop_anim()
        a = QPropertyAnimation(self, b"geometry", self)
        a.setDuration(300)
        a.setStartValue(self.geometry())
        a.setEndValue(rect)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start()
        self._anim = a

    def _stop_anim(self):
        if self._anim is not None:
            self._anim.stop()
            self._anim = None

    # ---- controles (X e alca)
    def _set_ctrl(self, v):
        self._ctrl = float(v)
        self.update()

    def _fade_ctrl(self, to):
        self._ca.stop()
        self._ca.setStartValue(float(self._ctrl))
        self._ca.setEndValue(float(to))
        self._ca.start()

    def _centers(self):
        rw, rh = self.rect_w(), self.rect_h()
        return (
            QPointF(PAD + rw - 16, PAD + 16),        # fechar (canto sup. direito)
            QPointF(PAD + rw - 16, PAD + rh - 16),   # redimensionar (canto inf. direito)
        )

    def _hit(self, pos):
        close_c, resize_c = self._centers()
        if dist(pos, close_c) <= 13:
            return "close"
        if dist(pos, resize_c) <= 13:
            return "resize"
        if QRectF(PAD, PAD, self.rect_w(), self.rect_h()).contains(pos):
            return "body"
        return None

    # ---- desenho
    def _build(self):
        dpr = self.devicePixelRatioF()
        w, h = self.width(), self.height()
        W, H = max(1, round(w * dpr)), max(1, round(h * dpr))
        x0 = PAD * dpr
        rw, rh = W - 2 * x0, H - 2 * x0

        img = _mask_image(W, H)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scaled = self.src.scaled(
            max(1, round(rw)), max(1, round(rh)),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        p.drawImage(round(x0), round(x0), scaled)

        # cantos arredondados com borda suave
        r = RADIUS * dpr
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.drawImage(0, 0, rrect_mask(W, H, QRectF(x0, x0, rw, rh), r))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QPen(QColor(255, 255, 255, 60), max(1.0, dpr)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        half = 0.5 * dpr
        p.drawRoundedRect(QRectF(x0 + half, x0 + half, rw - dpr, rh - dpr), r, r)
        p.end()
        img.setDevicePixelRatio(dpr)
        self._disc, self._disc_key = img, (w, h)

    def resizeEvent(self, e):
        self._disc = None
        super().resizeEvent(e)

    def paintEvent(self, _):
        if self._disc is None or self._disc_key != (self.width(), self.height()):
            self._build()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        draw_shadow_rect(p, QRectF(PAD, PAD, self.rect_w(), self.rect_h()), RADIUS)
        p.drawImage(QPointF(0, 0), self._disc)
        if self._ctrl > 0.01:
            self._draw_controls(p)

    def _draw_controls(self, p):
        p.setOpacity(self._ctrl)
        close_c, resize_c = self._centers()
        for kind, ctr in (("close", close_c), ("resize", resize_c)):
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            p.setBrush(QColor(28, 28, 34, 235))
            p.drawEllipse(ctr, 11, 11)
            pen = QPen(QColor(255, 255, 255, 235), 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            x, y = ctr.x(), ctr.y()
            if kind == "close":
                a = 3.6
                p.drawLine(QPointF(x - a, y - a), QPointF(x + a, y + a))
                p.drawLine(QPointF(x - a, y + a), QPointF(x + a, y - a))
            else:
                a = 3.8
                p.drawLine(QPointF(x - a, y - a), QPointF(x + a, y + a))
                p.drawLine(QPointF(x + a, y + a), QPointF(x + a - 4, y + a))
                p.drawLine(QPointF(x + a, y + a), QPointF(x + a, y + a - 4))
                p.drawLine(QPointF(x - a, y - a), QPointF(x - a + 4, y - a))
                p.drawLine(QPointF(x - a, y - a), QPointF(x - a, y - a + 4))
        p.setOpacity(1.0)

    # ---- mouse
    def enterEvent(self, e):
        if self.action is None and not self.closing:
            self._fade_ctrl(1.0)

    def leaveEvent(self, e):
        if self.action is None:
            self._fade_ctrl(0.0)

    def mousePressEvent(self, e):
        if self.closing or e.button() != Qt.MouseButton.LeftButton:
            return
        hit = self._hit(e.position())
        if hit is None:
            e.ignore()
            return
        self._stop_anim()
        self.action, self.moved = hit, False
        self.press_g = e.globalPosition()
        self.off = e.globalPosition().toPoint() - self.pos()
        self.anchor = self.center_pt()
        self.w0 = self.rect_w()
        self.d0 = max(1.0, dist(self.press_g, self.anchor))

    def mouseMoveEvent(self, e):
        g = e.globalPosition()
        if self.action is None:
            hit = self._hit(e.position())
            self.setCursor({
                "close": Qt.CursorShape.PointingHandCursor,
                "resize": Qt.CursorShape.SizeFDiagCursor,
                "body": Qt.CursorShape.SizeAllCursor,
            }.get(hit, Qt.CursorShape.ArrowCursor))
            return
        if not self.moved and dist(g, self.press_g) < 4:
            return
        if self.action == "resize":
            self.moved = True
            self._resize_to(self.anchor, self.w0 * dist(g, self.anchor) / self.d0)
        elif self.action == "body":
            if not self.moved:
                self.moved = True
                self._fade_ctrl(0.0)
                self.ctl.drag_begin(self, (self.rect_w(), self.rect_h()))
            self.move(g.toPoint() - self.off)
            self.ctl.drag_move(g)

    def mouseReleaseEvent(self, e):
        act, self.action = self.action, None
        if act is None:
            return
        if act == "close":
            if self._hit(e.position()) == "close":
                self.fade_out()
            return
        if act == "body" and self.moved:
            self.ctl.drop_pin(self)
        if not self.closing:
            self._fade_ctrl(1.0 if self.underMouse() else 0.0)

    def wheelEvent(self, e):
        if self.closing:
            return
        f = 1.07 if e.angleDelta().y() > 0 else 1 / 1.07
        self._stop_anim()
        self._resize_to(self.center_pt(), self.rect_w() * f)

    # ---- fechar
    def fade_out(self):
        if self.closing:
            return
        self.closing = True
        self._stop_anim()
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(160)
        a.setStartValue(self.windowOpacity())
        a.setEndValue(0.0)
        a.finished.connect(self.close)
        a.start()
        self._fade = a

    def closeEvent(self, e):
        if self in self.ctl.pins:
            self.ctl.pins.remove(self)
        e.accept()


# --------------------------------------------------------------- janela inicial
class Home(QWidget):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setWindowTitle("PrintPin")
        self.setWindowIcon(ctl.icon)
        self.setFixedWidth(410)
        self.setStyleSheet(
            "QWidget{background:#1b1b1f;color:#e8e8ec;font-size:13px;}"
            "QPushButton{background:#2a2a31;border:1px solid #3a3a44;"
            "border-radius:6px;padding:7px 12px;}"
            "QPushButton:hover{background:#34343d;}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        title = QLabel("PrintPin")
        title.setStyleSheet("font-size:20px;font-weight:600;")
        body = QLabel(TEXT)
        body.setWordWrap(True)
        row = QHBoxLayout()
        hide = QPushButton("Ocultar na bandeja")
        hide.clicked.connect(self.close)
        quit_ = QPushButton("Sair do PrintPin")
        quit_.clicked.connect(QApplication.quit)
        row.addWidget(hide)
        row.addWidget(quit_)
        lay.addWidget(title)
        lay.addWidget(body)
        lay.addLayout(row)

    def closeEvent(self, e):
        if QGuiApplication.isSavingSession():
            e.accept()
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            e.accept()
            QApplication.quit()
            return
        e.ignore()
        self.hide()
        self.ctl.tray_hint()


# ------------------------------------------------------------------ controlador
class PrintPin:
    def __init__(self, qapp):
        self.qapp = qapp
        self.pins = []
        self.bubble = None
        self.overlay = Overlay()
        self.drag_screen = None
        self.last_sig = None
        self.last_t = 0.0
        self.hinted = False
        self.icon = load_icon()
        qapp.setWindowIcon(self.icon)

        self.clip_timer = QTimer()
        self.clip_timer.setSingleShot(True)
        self.clip_timer.setInterval(150)
        self.clip_timer.timeout.connect(self.read_clipboard)
        qapp.clipboard().dataChanged.connect(self.clip_timer.start)

        self.menu = QMenu()
        act_open = QAction("Abrir PrintPin", self.menu)
        act_open.triggered.connect(self.show_home)
        act_clear = QAction("Remover todos os fixados", self.menu)
        act_clear.triggered.connect(self.clear_pins)
        act_quit = QAction("Sair", self.menu)
        act_quit.triggered.connect(qapp.quit)
        self.menu.addAction(act_open)
        self.menu.addAction(act_clear)
        self.menu.addSeparator()
        self.menu.addAction(act_quit)
        self.tray = QSystemTrayIcon(self.icon, qapp)
        self.tray.setToolTip("PrintPin")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_click)
        self.tray.show()
        qapp.aboutToQuit.connect(self.tray.hide)

        self.home = Home(self)

    # ---- bandeja / janela
    def tray_click(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_home()

    def show_home(self):
        self.home.show()
        self.home.raise_()
        self.home.activateWindow()

    def tray_hint(self):
        if not self.hinted:
            self.hinted = True
            self.tray.showMessage(
                "PrintPin",
                "Continua rodando aqui na bandeja. "
                "Clique com o botão direito no ícone para sair.",
                self.icon, 4000,
            )

    def clear_pins(self):
        for p in list(self.pins):
            p.fade_out()

    # ---- area de transferencia
    def read_clipboard(self):
        cb = self.qapp.clipboard()
        md = cb.mimeData()
        if md is None or not md.hasImage():
            return
        img = cb.image()
        if img.isNull() or img.width() < 8 or img.height() < 8:
            return
        img = img.convertToFormat(QImage.Format.Format_RGB32)
        small = img.scaled(
            24, 24, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        sig = hash((
            img.width(), img.height(),
            tuple(small.pixel(x, y) for y in range(24) for x in range(24)),
        ))
        now = time.monotonic()
        if sig == self.last_sig and now - self.last_t < 3:
            return
        self.last_sig, self.last_t = sig, now
        self.show_bubble(img)

    def show_bubble(self, img):
        scr = screen_at(QCursor.pos())
        if self.bubble is not None:
            self.bubble.close()
        self.bubble = Bubble(self, img, scr)

    # ---- tamanho padrao do print fixado (segue a proporcao da imagem)
    def default_size(self, img, scr):
        a = scr.availableGeometry()
        iw, ih = img.width(), img.height()
        maxw = min(460.0, 0.32 * a.width())
        maxh = 0.42 * a.height()
        s = min(maxw / iw, maxh / ih, 1.0)
        if iw * s < 220:
            s = 220 / iw
        return round(iw * s), round(ih * s)

    # ---- arrastar / soltar
    def drag_begin(self, widget, size=None):
        scr = screen_at(QCursor.pos())
        self.drag_screen = scr
        if size is None:
            size = self.default_size(widget.img, scr)
        self.overlay.begin(scr, size, QPointF(QCursor.pos()))
        widget.raise_()

    def drag_move(self, g):
        self.overlay.move_to(g)

    def drag_end(self):
        idx, dot = self.overlay.end()
        return self.drag_screen, idx, dot

    def drop_bubble(self, bubble):
        scr, idx, dot = self.drag_end()
        img = bubble.img
        size = self.default_size(img, scr)
        # o print nasce do tamanho da bolinha e cresce ate o tamanho final
        aspect = img.width() / img.height()
        if aspect >= 1:
            sw, sh = Bubble.D * aspect, Bubble.D
        else:
            sw, sh = Bubble.D, Bubble.D / aspect
        c = bubble.geometry().center()
        fw, fh = round(sw) + 2 * PAD, round(sh) + 2 * PAD
        start = QRect(c.x() - fw // 2, c.y() - fh // 2, fw, fh)
        pin = Pin(self, img, start)
        bubble.close()
        self.place_pin(pin, scr, idx, dot, size)

    def drop_pin(self, pin):
        scr, idx, dot = self.drag_end()
        self.place_pin(pin, scr, idx, dot, (pin.rect_w(), pin.rect_h()))

    def place_pin(self, pin, scr, idx, dot, size):
        if dot is None:
            return
        key = (scr.name(), idx)
        for other in list(self.pins):
            if other is not pin and other.dot_key == key:
                other.fade_out()
        pin.dot_key = key
        pin.animate_to(snap_rect(scr.availableGeometry(), dot, size[0], size[1]))


# ------------------------------------------------------------------------ main
def main():
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName("PrintPin")

    # instancia unica: se ja estiver rodando, apenas mostra a janela dela
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_NAME)
    if sock.waitForConnected(400):
        sock.write(b"show")
        sock.waitForBytesWritten(400)
        sock.disconnectFromServer()
        return 0

    QLocalServer.removeServer(INSTANCE_NAME)
    server = QLocalServer()
    server.listen(INSTANCE_NAME)

    ctl = PrintPin(qapp)

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.deleteLater()
        ctl.show_home()

    server.newConnection.connect(on_connection)
    ctl.show_home()
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
