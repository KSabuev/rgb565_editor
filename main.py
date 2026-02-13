import sys
import json
import os
import traceback

from PyQt5.QtWidgets import (QApplication, QMainWindow, QMessageBox,
                             QPushButton, QLabel, QFileDialog, QDialog,
                             QVBoxLayout)
from PyQt5.QtCore import (Qt, pyqtSignal)
from PyQt5.QtGui import (QPainter, QImage, QPixmap, QColor)
from PyQt5 import uic

DEFAULT_WIDTH = 15
DEFAULT_HEIGHT = 15
MIN_SCALE = 2
MAX_SCALE = 20
DEFAULT_SCALE = 10
HISTORY_SIZE = 50
GRID_COLOR = QColor(100, 100, 100, 100)
SELECTION_COLOR = QColor(255, 0, 0, 100)


class LanguageDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_language = None
        self.ui_path = None
        self.setWindowTitle("Language")
        self.setModal(True)
        self.setFixedSize(300, 200)

        layout = QVBoxLayout(self)
        self.button_layout = QVBoxLayout()
        layout.addLayout(self.button_layout)
        self.scan_language_folders()

    def scan_language_folders(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        languages_dir = os.path.join(current_dir, 'languages')

        if os.path.exists(languages_dir) and os.path.isdir(languages_dir):
            for item in sorted(os.listdir(languages_dir)):
                item_path = os.path.join(languages_dir, item)
                ui_file = os.path.join(item_path, 'pixel_editor.ui')
                if os.path.isdir(item_path) and os.path.exists(ui_file):
                    self.add_language_button(item, ui_file)

        if self.button_layout.count() == 0:
            QMessageBox.critical(self, "Error", "No language UI files found!")
            self.reject()

    def add_language_button(self, lang_name, ui_path):
        btn = QPushButton(lang_name.upper())
        btn.clicked.connect(lambda: self.language_selected(lang_name, ui_path))
        self.button_layout.addWidget(btn)

    def language_selected(self, lang_name, ui_path):
        self.selected_language = lang_name
        self.ui_path = ui_path
        self.accept()


class ColorButton(QPushButton):
    colorSelected = pyqtSignal(int)

    def __init__(self, color_rgb565, parent=None):
        super().__init__(parent)
        self.color_rgb565 = color_rgb565
        self.setFixedSize(40, 40)
        self.setFlat(True)
        self.selected = False

        color = self.rgb565_to_qcolor(color_rgb565)
        self.normal_style = f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); border: 1px solid #888;"
        self.selected_style = f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); border: 3px solid #000;"

        self.setStyleSheet(self.normal_style)
        self.clicked.connect(lambda: self.colorSelected.emit(color_rgb565))

    @staticmethod
    def rgb565_to_qcolor(rgb565):
        r = ((rgb565 >> 11) & 0x1F) << 3
        g = ((rgb565 >> 5) & 0x3F) << 2
        b = (rgb565 & 0x1F) << 3
        return QColor(r, g, b)

    @staticmethod
    def qcolor_to_rgb565(color):
        r = color.red() >> 3
        g = color.green() >> 2
        b = color.blue() >> 3
        return (r << 11) | (g << 5) | b

    def select(self):
        self.setStyleSheet(self.selected_style)

    def deselect(self):
        self.setStyleSheet(self.normal_style)


class CanvasWidget(QLabel):
    pixelClicked = pyqtSignal(int, int, int)
    pixelHovered = pyqtSignal(int, int, int)
    imageChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.scale = DEFAULT_SCALE
        self.show_grid = True
        self.hover_x = -1
        self.hover_y = -1
        self.dragging = False
        self.tool = 'pencil'
        self.current_color_rgb565 = 0x0000
        self.selection_start = None
        self.selection_end = None
        self.selecting = False

        self.setMouseTracking(True)
        self.setMinimumSize(400, 400)
        self.setAlignment(Qt.AlignCenter)

    def set_image_size(self, width, height):
        self.image = QImage(width, height, QImage.Format_RGB16)
        self.image.fill(Qt.black)
        self.update_pixmap()
        self.imageChanged.emit()

    def set_image_data(self, data, width, height):
        if len(data) != width * height:
            if len(data) > width * height:
                data = data[:width * height]
            else:
                data = data + [0x0000] * (width * height - len(data))

        self.set_image_size(width, height)
        for y in range(height):
            for x in range(width):
                color = ColorButton.rgb565_to_qcolor(data[y * width + x])
                self.image.setPixelColor(x, y, color)
        self.update_pixmap()
        self.imageChanged.emit()
        return True

    def get_image_data(self):
        if not self.image:
            return []

        data = []
        w, h = self.image.width(), self.image.height()
        for y in range(h):
            for x in range(w):
                data.append(ColorButton.qcolor_to_rgb565(self.image.pixelColor(x, y)))
        return data

    def update_pixmap(self):
        if not self.image:
            return

        w, h = self.image.width() * self.scale, self.image.height() * self.scale
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.white)

        painter = QPainter(pixmap)
        painter.drawPixmap(0, 0,
                           QPixmap.fromImage(self.image.scaled(w, h, Qt.IgnoreAspectRatio, Qt.FastTransformation)))

        if self.show_grid and self.scale >= 4:
            painter.setPen(GRID_COLOR)
            for x in range(0, w, self.scale):
                painter.drawLine(x, 0, x, h)
            for y in range(0, h, self.scale):
                painter.drawLine(0, y, w, y)

        if self.selection_start and self.selection_end:
            x1 = min(self.selection_start.x(), self.selection_end.x()) * self.scale
            y1 = min(self.selection_start.y(), self.selection_end.y()) * self.scale
            x2 = max(self.selection_start.x(), self.selection_end.x()) * self.scale + self.scale
            y2 = max(self.selection_start.y(), self.selection_end.y()) * self.scale + self.scale
            painter.setPen(Qt.red)
            painter.setBrush(SELECTION_COLOR)
            painter.drawRect(x1, y1, x2 - x1, y2 - y1)

        if 0 <= self.hover_x < self.image.width() and 0 <= self.hover_y < self.image.height():
            painter.setPen(Qt.yellow)
            painter.drawRect(self.hover_x * self.scale, self.hover_y * self.scale, self.scale - 1, self.scale - 1)

        painter.end()
        self.setPixmap(pixmap)

    def get_pixel_coordinates(self, event):
        if not self.image or not self.pixmap():
            return -1, -1

        x, y = event.x(), event.y()
        pw, ph = self.pixmap().width(), self.pixmap().height()
        offset_x = (self.width() - pw) // 2
        offset_y = (self.height() - ph) // 2

        px, py = x - offset_x, y - offset_y
        if 0 <= px < pw and 0 <= py < ph:
            pixel_x, pixel_y = px // self.scale, py // self.scale
            if pixel_x < self.image.width() and pixel_y < self.image.height():
                return pixel_x, pixel_y
        return -1, -1

    def mousePressEvent(self, event):
        x, y = self.get_pixel_coordinates(event)
        if x >= 0 and y >= 0 and event.button() == Qt.LeftButton:
            self.dragging = True
            self.handle_click(x, y)

    def mouseMoveEvent(self, event):
        x, y = self.get_pixel_coordinates(event)
        if x != self.hover_x or y != self.hover_y:
            self.hover_x, self.hover_y = x, y
            if x >= 0 and y >= 0:
                color = self.image.pixelColor(x, y)
                self.pixelHovered.emit(x, y, ColorButton.qcolor_to_rgb565(color))
                if self.dragging and self.tool == 'pencil':
                    self.handle_click(x, y)
            self.update_pixmap()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False

    def handle_click(self, x, y):
        if self.tool == 'pencil':
            color = ColorButton.rgb565_to_qcolor(self.current_color_rgb565)
            self.image.setPixelColor(x, y, color)
            self.pixelClicked.emit(x, y, self.current_color_rgb565)
            self.imageChanged.emit()
        elif self.tool == 'pipette':
            self.pixelClicked.emit(x, y, ColorButton.qcolor_to_rgb565(self.image.pixelColor(x, y)))
        elif self.tool == 'fill':
            self.flood_fill(x, y)
            self.imageChanged.emit()
        self.update_pixmap()

    def flood_fill(self, x, y):
        if not self.image:
            return

        target = self.image.pixelColor(x, y)
        fill = ColorButton.rgb565_to_qcolor(self.current_color_rgb565)
        if target == fill:
            return

        w, h = self.image.width(), self.image.height()
        stack = [(x, y)]
        visited = [[False] * w for _ in range(h)]

        while stack:
            cx, cy = stack.pop()
            if cx < 0 or cx >= w or cy < 0 or cy >= h or visited[cy][cx]:
                continue
            if self.image.pixelColor(cx, cy) != target:
                continue

            visited[cy][cx] = True
            self.image.setPixelColor(cx, cy, fill)
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])

    def set_scale(self, scale):
        self.scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        self.update_pixmap()

    def zoom_in(self):
        self.set_scale(self.scale + 1)

    def zoom_out(self):
        self.set_scale(self.scale - 1)


class PixelEditor(QMainWindow):
    def __init__(self, ui_path='pixel_editor.ui'):
        super().__init__()
        self.current_color_rgb565 = 0x0000
        self.color_buttons = []
        self.selected_color_button = None
        self.history = []
        self.history_index = -1
        self.ui_path = ui_path

        self.setup_ui()
        self.setup_canvas()
        self.create_color_buttons([])
        self.setup_connections()
        self.setup_history()
        self.load_palette()

        self.canvas.current_color_rgb565 = self.current_color_rgb565
        self.update_color_preview()

    def setup_ui(self):
        if not os.path.exists(self.ui_path):
            QMessageBox.critical(None, "Error", f"UI file {self.ui_path} not found!")
            sys.exit(1)

        uic.loadUi(self.ui_path, self)

    def setup_canvas(self):
        if hasattr(self, 'labelCanvas'):
            self.canvas = CanvasWidget()
            parent = self.labelCanvas.parent()
            layout = parent.layout()
            index = layout.indexOf(self.labelCanvas)
            layout.removeWidget(self.labelCanvas)
            self.labelCanvas.deleteLater()
            layout.insertWidget(index, self.canvas)
            self.canvas.setMinimumSize(400, 400)
        else:
            self.canvas = CanvasWidget()
            central = self.centralWidget()
            if central and central.layout():
                central.layout().insertWidget(0, self.canvas)

        self.canvas.set_image_size(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        if hasattr(self, 'spinWidth'):
            self.spinWidth.setValue(DEFAULT_WIDTH)
            self.spinHeight.setValue(DEFAULT_HEIGHT)

    def zoom_in(self):
        self.canvas.zoom_in()
        self.update_info()

    def zoom_out(self):
        self.canvas.zoom_out()
        self.update_info()

    def create_color_buttons(self, colors):
        for button in self.color_buttons:
            button.deleteLater()
        self.color_buttons.clear()

        if hasattr(self, 'gridLayoutColors'):
            while self.gridLayoutColors.count():
                item = self.gridLayoutColors.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for i, color in enumerate(colors):
                button = ColorButton(color)
                button.colorSelected.connect(self.on_color_selected)
                self.gridLayoutColors.addWidget(button, i // 5, i % 5)
                self.color_buttons.append(button)

            if self.color_buttons:
                self.on_color_selected(self.color_buttons[0].color_rgb565)

    def setup_connections(self):
        if hasattr(self, 'pencilButton'):
            self.pencilButton.clicked.connect(lambda: self.set_tool('pencil'))
        if hasattr(self, 'fillButton'):
            self.fillButton.clicked.connect(lambda: self.set_tool('fill'))
        if hasattr(self, 'pipetteButton'):
            self.pipetteButton.clicked.connect(lambda: self.set_tool('pipette'))

        if hasattr(self, 'btnUndo'):
            self.btnUndo.clicked.connect(self.undo)
        if hasattr(self, 'btnRedo'):
            self.btnRedo.clicked.connect(self.redo)
        if hasattr(self, 'btnClear'):
            self.btnClear.clicked.connect(self.clear_canvas)
        if hasattr(self, 'btnSavePNG'):
            self.btnSavePNG.clicked.connect(self.save_png)
        if hasattr(self, 'btnLoadPNG'):
            self.btnLoadPNG.clicked.connect(self.load_png)
        if hasattr(self, 'btnApplySize'):
            self.btnApplySize.clicked.connect(self.apply_size)
        if hasattr(self, 'btnRotate90'):
            self.btnRotate90.clicked.connect(self.rotate_90)
        if hasattr(self, 'btnAddColor'):
            self.btnAddColor.clicked.connect(self.add_color)
        if hasattr(self, 'btnRemoveColor'):
            self.btnRemoveColor.clicked.connect(self.remove_selected_color)
        if hasattr(self, 'btnSaveColor'):
            self.btnSaveColor.clicked.connect(self.save_palette)

        if hasattr(self, 'btnZoomIn'):
            self.btnZoomIn.clicked.connect(self.zoom_in)
        if hasattr(self, 'btnZoomOut'):
            self.btnZoomOut.clicked.connect(self.zoom_out)

        if hasattr(self, 'spinR'):
            self.spinR.valueChanged.connect(self.update_color_from_spinboxes)
            self.spinG.valueChanged.connect(self.update_color_from_spinboxes)
            self.spinB.valueChanged.connect(self.update_color_from_spinboxes)

        if hasattr(self, 'textEditHex'):
            self.textEditHex.textChanged.connect(self.on_text_changed)

        self.canvas.pixelClicked.connect(self.on_pixel_clicked)
        self.canvas.pixelHovered.connect(self.on_pixel_hovered)
        self.canvas.imageChanged.connect(self.on_image_changed)

        self.update_info()

    def update_undo_redo_buttons(self):
        if hasattr(self, 'btnUndo'):
            self.btnUndo.setEnabled(self.history_index > 0)
        if hasattr(self, 'btnRedo'):
            self.btnRedo.setEnabled(self.history_index < len(self.history) - 1)

    def setup_history(self):
        if self.canvas and self.canvas.image:
            self.save_to_history()
        self.update_undo_redo_buttons()

    def set_tool(self, tool):
        self.canvas.tool = tool
        self.canvas.current_color_rgb565 = self.current_color_rgb565

        for btn in [self.pencilButton, self.fillButton, self.pipetteButton]:
            if btn:
                btn.setStyleSheet("")

        active = "background-color: lightblue"
        if tool == 'pencil' and hasattr(self, 'pencilButton'):
            self.pencilButton.setStyleSheet(active)
        elif tool == 'fill' and hasattr(self, 'fillButton'):
            self.fillButton.setStyleSheet(active)
        elif tool == 'pipette' and hasattr(self, 'pipetteButton'):
            self.pipetteButton.setStyleSheet(active)

        self.update_info()

    def on_color_selected(self, color_rgb565):
        for btn in self.color_buttons:
            btn.deselect()
            if btn.color_rgb565 == color_rgb565:
                btn.select()
                self.selected_color_button = btn

        self.current_color_rgb565 = color_rgb565
        self.canvas.current_color_rgb565 = color_rgb565
        self.update_color_from_rgb565(color_rgb565)

    def update_color_from_rgb565(self, rgb565):
        color = ColorButton.rgb565_to_qcolor(rgb565)
        if hasattr(self, 'spinR'):
            self.spinR.blockSignals(True)
            self.spinG.blockSignals(True)
            self.spinB.blockSignals(True)
            self.spinR.setValue(color.red())
            self.spinG.setValue(color.green())
            self.spinB.setValue(color.blue())
            self.spinR.blockSignals(False)
            self.spinG.blockSignals(False)
            self.spinB.blockSignals(False)
        self.update_color_preview()

    def update_color_from_spinboxes(self):
        color = QColor(self.spinR.value(), self.spinG.value(), self.spinB.value())
        self.current_color_rgb565 = ColorButton.qcolor_to_rgb565(color)
        self.canvas.current_color_rgb565 = self.current_color_rgb565
        self.update_color_preview()

    def update_color_preview(self):
        color = ColorButton.rgb565_to_qcolor(self.current_color_rgb565)
        if hasattr(self, 'labelColorPreview'):
            self.labelColorPreview.setStyleSheet(f"background-color: {color.name()}")
        if hasattr(self, 'labelHex'):
            self.labelHex.setText(f"HEX: 0x{self.current_color_rgb565:04X}")

    def on_pixel_clicked(self, x, y, color_rgb565):
        if self.canvas.tool == 'pipette':
            self.on_color_selected(color_rgb565)

    def on_pixel_hovered(self, x, y, color_rgb565):
        self.update_info()

    def on_image_changed(self):
        if not self.canvas.signalsBlocked():
            self.save_to_history()
        self.update_text_from_image()
        self.update_info()

    def save_to_history(self):
        if not self.canvas or not self.canvas.image:
            return

        current = self.canvas.get_image_data()
        if self.history and self.history_index >= 0:
            last = self.history[self.history_index]
            if (last['data'] == current and
                    last['width'] == self.canvas.image.width() and
                    last['height'] == self.canvas.image.height()):
                return

        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]

        self.history.append({
            'data': current.copy(),
            'width': self.canvas.image.width(),
            'height': self.canvas.image.height()
        })

        if len(self.history) > HISTORY_SIZE:
            self.history.pop(0)
        self.history_index = len(self.history) - 1
        self.update_undo_redo_buttons()

    def undo(self):
        if self.history_index > 0:
            self.history_index -= 1
            state = self.history[self.history_index]
            self.canvas.blockSignals(True)
            self.canvas.set_image_data(state['data'], state['width'], state['height'])
            self.canvas.blockSignals(False)
            self.update_text_from_image()
            self.update_undo_redo_buttons()
            self.update_info()

    def redo(self):
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            state = self.history[self.history_index]
            self.canvas.blockSignals(True)
            self.canvas.set_image_data(state['data'], state['width'], state['height'])
            self.canvas.blockSignals(False)
            self.update_text_from_image()
            self.update_undo_redo_buttons()
            self.update_info()

    def clear_canvas(self):
        reply = QMessageBox.question(self, 'Clear', 'Are you sure?', QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.canvas.blockSignals(True)
            w, h = self.canvas.image.width(), self.canvas.image.height()
            self.canvas.image = QImage(w, h, QImage.Format_RGB16)
            self.canvas.image.fill(Qt.black)
            self.canvas.update_pixmap()
            self.canvas.blockSignals(False)
            self.canvas.imageChanged.emit()
            self.update_text_from_image()

    def apply_size(self):
        if not hasattr(self, 'spinWidth') or not self.canvas.image:
            return

        w, h = self.spinWidth.value(), self.spinHeight.value()
        old_data = self.canvas.get_image_data()
        old_w, old_h = self.canvas.image.width(), self.canvas.image.height()

        self.canvas.set_image_size(w, h)
        if old_data:
            for y in range(min(old_h, h)):
                for x in range(min(old_w, w)):
                    color = ColorButton.rgb565_to_qcolor(old_data[y * old_w + x])
                    self.canvas.image.setPixelColor(x, y, color)

        self.canvas.update_pixmap()
        self.save_to_history()
        self.update_text_from_image()

    def rotate_90(self):
        if not self.canvas.image:
            return

        self.canvas.blockSignals(True)
        old_data = self.canvas.get_image_data()
        old_w, old_h = self.canvas.image.width(), self.canvas.image.height()
        new_w, new_h = old_h, old_w

        new_image = QImage(new_w, new_h, QImage.Format_RGB16)
        new_image.fill(Qt.black)

        for y in range(old_h):
            for x in range(old_w):
                color = ColorButton.rgb565_to_qcolor(old_data[y * old_w + x])
                new_image.setPixelColor(old_h - 1 - y, x, color)

        self.canvas.image = new_image
        self.canvas.update_pixmap()
        self.canvas.blockSignals(False)
        self.canvas.imageChanged.emit()
        self.update_text_from_image()

    def update_text_from_image(self):
        if not self.canvas.image:
            return

        data = self.canvas.get_image_data()
        w = self.canvas.image.width()

        lines = []
        for i in range(0, len(data), w):
            row = data[i:i + w]
            lines.append(", ".join([f"0x{val:04X}" for val in row]))
        text = "\n".join(lines)

        if hasattr(self, 'textEditHex'):
            self.textEditHex.blockSignals(True)
            self.textEditHex.setPlainText(text)
            self.textEditHex.blockSignals(False)

    def on_text_changed(self):
        text = self.textEditHex.toPlainText().strip()
        if not text:
            return

        hex_values = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            for part in line.split(','):
                part = part.strip().replace('0x', '').replace('0X', '')
                if part:
                    try:
                        value = int(part, 16)
                        if 0 <= value <= 0xFFFF:
                            hex_values.append(value)
                        else:
                            QMessageBox.warning(self, "Error", f"Invalid value: {part}")
                            return
                    except ValueError:
                        QMessageBox.warning(self, "Error", f"Invalid format: {part}")
                        return

        if not hex_values:
            return

        w = self.spinWidth.value() if hasattr(self, 'spinWidth') else self.canvas.image.width()
        h = self.spinHeight.value() if hasattr(self, 'spinHeight') else self.canvas.image.height()
        expected = w * h

        if len(hex_values) != expected:
            if len(hex_values) > expected:
                hex_values = hex_values[:expected]
            else:
                hex_values.extend([0x0000] * (expected - len(hex_values)))

        self.canvas.blockSignals(True)
        self.canvas.set_image_data(hex_values, w, h)
        self.canvas.blockSignals(False)
        self.canvas.imageChanged.emit()
        self.save_to_history()

    def update_info(self):
        if not self.canvas.image:
            return

        tool_names = {'pencil': 'Pencil', 'fill': 'Fill', 'pipette': 'Pipette'}
        info = f"Size: {self.canvas.image.width()}x{self.canvas.image.height()} | Scale: {self.canvas.scale}x | Tool: {tool_names.get(self.canvas.tool, 'Unknown')}"

        if hasattr(self, 'labelInfo'):
            self.labelInfo.setText(info)

    def add_color(self):
        colors = [btn.color_rgb565 for btn in self.color_buttons]
        if self.current_color_rgb565 not in colors:
            colors.append(self.current_color_rgb565)
            self.create_color_buttons(colors)

    def remove_selected_color(self):
        if self.selected_color_button and len(self.color_buttons) > 1:
            colors = [btn.color_rgb565 for btn in self.color_buttons if btn != self.selected_color_button]
            self.create_color_buttons(colors)
            self.selected_color_button = None

    def save_palette(self):
        try:
            with open('palette.json', 'w') as f:
                json.dump([btn.color_rgb565 for btn in self.color_buttons], f)
            QMessageBox.information(self, "Success", "Palette saved")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save palette: {e}")

    def load_palette(self):
        try:
            if os.path.exists('palette.json'):
                with open('palette.json', 'r') as f:
                    colors = json.load(f)
                if colors:
                    self.create_color_buttons(colors)
        except:
            pass

    def save_png(self):
        if not self.canvas.image:
            return

        filename, _ = QFileDialog.getSaveFileName(self, "Save PNG", "img", "PNG Images (*.png)")
        if filename:
            if not filename.endswith('.png'):
                filename += '.png'

            save_image = self.canvas.image.convertToFormat(QImage.Format_RGB888)
            if save_image.save(filename, "PNG"):
                QMessageBox.information(self, "Success", f"Image saved: {filename}")
            else:
                QMessageBox.warning(self, "Error", "Could not save image")

    def load_png(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Load PNG", "", "PNG Images (*.png)")
        if filename:
            image = QImage(filename).convertToFormat(QImage.Format_RGB16)
            if not image.isNull():
                if hasattr(self, 'spinWidth'):
                    self.spinWidth.setValue(image.width())
                    self.spinHeight.setValue(image.height())
                self.canvas.image = image
                self.canvas.update_pixmap()
                self.save_to_history()
                self.update_text_from_image()
            else:
                QMessageBox.warning(self, "Error", "Could not load image")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.canvas.zoom_in()
        elif event.key() == Qt.Key_Minus:
            self.canvas.zoom_out()
        elif event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_Z:
                self.undo()
            elif event.key() == Qt.Key_Y:
                self.redo()
            elif event.key() == Qt.Key_A and hasattr(self, 'textEditHex'):
                self.textEditHex.selectAll()
        super().keyPressEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    lang_dialog = LanguageDialog()
    if lang_dialog.exec_() == QDialog.Accepted and lang_dialog.selected_language:
        ui_path = lang_dialog.ui_path
        print(f"Selected language: {lang_dialog.selected_language}")
        print(f"UI file: {ui_path}")
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(current_dir, 'pixel_editor.ui')
        if not os.path.exists(ui_path):
            QMessageBox.critical(None, "Error", "No UI file found!")
            sys.exit(1)

    try:
        editor = PixelEditor(ui_path)
        editor.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Startup Error")
        msg.setText(f"Could not start the program:\n{e}")
        msg.setDetailedText(traceback.format_exc())
        msg.exec_()
        sys.exit(1)