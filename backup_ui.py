import sys

from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *

from pupil_labs.real_time_screen_gaze import marker_generator

PHYSICAL_SCREEN_WIDTH = 1920
PHYSICAL_SCREEN_HEIGHT = 1080

# Dimensions des AprilTags physiques
TAG_PATTERN_SIZE = 114  # Taille du motif AprilTag lui-même (sans bordure papier)
PAPER_TAG_SIZE = 168    # Taille totale du tag avec sa bordure papier
PAPER_TO_PATTERN_OFFSET = (PAPER_TAG_SIZE - TAG_PATTERN_SIZE) / 2 # 27 pixels

# Marge verticale pour le positionnement des tags (à ajuster selon votre installation)
# C'est la distance entre le bord supérieur/inférieur de l'écran et le bord supérieur/inférieur du MOTIF AprilTag.
VERTICAL_MARGIN_TOP = 0
VERTICAL_MARGIN_BOTTOM = 0 # Peut être différent de VERTICAL_MARGIN_TOP si besoin

# Coordonnées des coins des AprilTags physiques (motif 114x114px)
# par rapport au coin supérieur gauche de l'écran (0,0).
# Ordre des sommets : [Top-Left, Top-Right, Bottom-Right, Bottom-Left]

# Tag 0: En haut à gauche, sur le bord GAUCHE de l'écran
X_LEFT_TL = -PAPER_TAG_SIZE + PAPER_TO_PATTERN_OFFSET # Coordonnée X du coin supérieur gauche du motif
X_LEFT_TR = -PAPER_TO_PATTERN_OFFSET                 # Coordonnée X du coin supérieur droit du motif
Y_TOP_TL = VERTICAL_MARGIN_TOP
Y_TOP_BR = VERTICAL_MARGIN_TOP + TAG_PATTERN_SIZE

# Tag 3: En bas à gauche, sur le bord GAUCHE de l'écran (conventionnellement, le 3ème tag est en bas à gauche)
Y_BOTTOM_TL = PHYSICAL_SCREEN_HEIGHT - VERTICAL_MARGIN_BOTTOM - TAG_PATTERN_SIZE
Y_BOTTOM_BR = PHYSICAL_SCREEN_HEIGHT - VERTICAL_MARGIN_BOTTOM

# Tag 1: En haut à droite, sur le bord DROIT de l'écran
X_RIGHT_TL = PHYSICAL_SCREEN_WIDTH + PAPER_TO_PATTERN_OFFSET
X_RIGHT_TR = PHYSICAL_SCREEN_WIDTH + PAPER_TAG_SIZE - PAPER_TO_PATTERN_OFFSET

# Tag 2: En bas à droite, sur le bord DROIT de l'écran
PHYSICAL_MARKER_VERTICES = {
    0: [ # Tag en haut à gauche (sur le bord GAUCHE)
        (X_LEFT_TL, Y_TOP_TL),
        (X_LEFT_TR, Y_TOP_TL),
        (X_LEFT_TR, Y_TOP_BR),
        (X_LEFT_TL, Y_TOP_BR),
    ],
    1: [ # Tag en haut à droite (sur le bord DROIT)
        (X_RIGHT_TL, Y_TOP_TL),
        (X_RIGHT_TR, Y_TOP_TL),
        (X_RIGHT_TR, Y_TOP_BR),
        (X_RIGHT_TL, Y_TOP_BR),
    ],
    2: [ # Tag en bas à droite (sur le bord DROIT)
        (X_RIGHT_TL, Y_BOTTOM_TL),
        (X_RIGHT_TR, Y_BOTTOM_TL),
        (X_RIGHT_TR, Y_BOTTOM_BR),
        (X_RIGHT_TL, Y_BOTTOM_BR),
    ],
    3: [ # Tag en bas à gauche (sur le bord GAUCHE)
        (X_LEFT_TL, Y_BOTTOM_TL),
        (X_LEFT_TR, Y_BOTTOM_TL),
        (X_LEFT_TR, Y_BOTTOM_BR),
        (X_LEFT_TL, Y_BOTTOM_BR),
    ],
}

class TagWindow(QWidget):
    surfaceChanged = Signal()
    mouseEnableChanged = Signal(bool)
    dwellRadiusChanged = Signal(int)
    dwellTimeChanged = Signal(float)
    smoothingChanged = Signal(float)

    def __init__(self):
        super().__init__()

        self.setStyleSheet('* { font-size: 18pt }')

        self.markerIDs = []
        for markerID in range(4):
            self.markerIDs.append(markerID)

        self.point = (0, 0)
        self.clicked = False
        self.settingsVisible = True
        self.visibleMarkerIds = []

        self.form = QWidget()
        self.form.setLayout(QFormLayout())

        self.smoothingInput = QDoubleSpinBox()
        self.smoothingInput.setRange(0, 1.0)
        self.smoothingInput.setValue(0.8)
        self.smoothingInput.valueChanged.connect(self.smoothingChanged.emit)

        self.dwellRadiusInput = QSpinBox()
        self.dwellRadiusInput.setRange(0, 512)
        self.dwellRadiusInput.setValue(25)
        self.dwellRadiusInput.valueChanged.connect(self.dwellRadiusChanged.emit)

        self.dwellTimeInput = QDoubleSpinBox()
        self.dwellTimeInput.setRange(0, 20)
        self.dwellTimeInput.setValue(0.75)
        self.dwellTimeInput.valueChanged.connect(self.dwellTimeChanged.emit)

        self.mouseEnabledInput = QCheckBox('Mouse Control')
        self.mouseEnabledInput.setChecked(False)
        self.mouseEnabledInput.toggled.connect(self.mouseEnableChanged.emit)

        self.form.layout().addRow('Smoothing', self.smoothingInput)
        self.form.layout().addRow('Dwell Radius', self.dwellRadiusInput)
        self.form.layout().addRow('Dwell Time', self.dwellTimeInput)
        self.form.layout().addRow('', self.mouseEnabledInput)

        self.instructionsLabel = QLabel('Right-click one of the tags to toggle settings view.')
        self.instructionsLabel.setAlignment(Qt.AlignHCenter)

        self.statusLabel = QLabel()
        self.statusLabel.setAlignment(Qt.AlignHCenter)

        self.setLayout(QGridLayout())
        self.layout().setSpacing(50)

        self.layout().addWidget(self.instructionsLabel, 0, 0, 1, 3)
        self.layout().addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding), 1, 1, 1, 1)
        self.layout().addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum), 2, 0, 1, 1)
        self.layout().addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum), 2, 2, 1, 1)
        self.layout().addWidget(self.form, 3, 1, 1, 1)
        self.layout().addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding), 4, 1, 1, 1)
        self.layout().addWidget(self.statusLabel, 5, 0, 1, 3)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.setSettingsVisible(not self.settingsVisible)

    def setSettingsVisible(self, visible):
        self.settingsVisible = visible

        if sys.platform.startswith('darwin'):
            self.hide()
            self.setWindowFlag(Qt.FramelessWindowHint, not visible)
            self.setWindowFlag(Qt.WindowStaysOnTopHint, not visible)
            self.setAttribute(Qt.WA_TranslucentBackground, not visible)

            if visible:
                self.show()
            else:
                self.showMaximized()

        self.updateMask()

    def setStatus(self, status):
        self.statusLabel.setText(status)

    def setClicked(self, clicked):
        self.clicked = clicked
        self.repaint()

    def updatePoint(self, norm_x, norm_y):
        self.point = (norm_x, norm_y)
        self.repaint()
        return self.mapToGlobal(QPoint(*self.point))

    def showMarkerFeedback(self, markerIds):
        self.visibleMarkerIds = markerIds
        self.repaint()

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.settingsVisible:
            if self.clicked:
                painter.setBrush(Qt.red)
            else:
                painter.setBrush(Qt.white)
            painter.drawEllipse(QPoint(*self.point), self.dwellRadiusInput.value(), self.dwellRadiusInput.value())

    def resizeEvent(self, event):
        self.updateMask()
        self.surfaceChanged.emit()

    def getMarkerVerts(self):
        return PHYSICAL_MARKER_VERTICES

    def getSurfaceSize(self):
        return (PHYSICAL_SCREEN_WIDTH, PHYSICAL_SCREEN_HEIGHT)

    def updateMask(self):
        if self.settingsVisible:
            mask = QRegion(0, 0, self.width(), self.height())

        else:
            mask = QRegion(0, 0, 0, 0)
            for cornerIdx in range(4):
                rect = self.getCornerRect(cornerIdx).marginsAdded(QMargins(2, 2, 2, 2))
                mask = mask.united(rect)

        self.setMask(mask)

    def getCornerRect(self, cornerIdx):
        tagSize = 100
        tagPadding = tagSize / 8
        tagSizePadded = tagSize + tagPadding*2

        if cornerIdx == 0:
            return QRect(0, 0, tagSizePadded, tagSizePadded)

        elif cornerIdx == 1:
            return QRect(self.width()-tagSizePadded, 0, tagSizePadded, tagSizePadded)

        elif cornerIdx == 2:
            return QRect(self.width()-tagSizePadded, self.height()-tagSizePadded, tagSizePadded, tagSizePadded)

        elif cornerIdx == 3:
            return QRect(0, self.height()-tagSizePadded, tagSizePadded, tagSizePadded)
