from pyqtgraph.Qt import QtGui
import sys
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QTimer

class HeatmapWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Heatmap setup
        self.graphWidget = pg.PlotWidget()
        self.setCentralWidget(self.graphWidget)
        self.heatmap = pg.ImageItem()
        self.graphWidget.addItem(self.heatmap)
        
        # Apply a color map
        colormap = pg.colormap.get('viridis', source='matplotlib')  # You can choose other colormaps like 'plasma', 'inferno', etc.
        self.heatmap.setLookupTable(colormap.getLookupTable())

        # Random data dimensions
        self.data_width = 50
        self.data_height = 50
        self.data = np.random.rand(self.data_height, self.data_width)
        
        # Update the heatmap every 1000 milliseconds (1 second)
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_heatmap)
        self.timer.start()

        # Initial display update
        self.update_heatmap()
    
    def update_heatmap(self):
        # Create sliding window effect by rolling the data horizontally
        self.data = np.roll(self.data, shift=-1, axis=0)
        
        # Insert new random data at the end of the roll
        self.data[-1, :] = np.random.rand(self.data_width)
        
        # Update the heatmap display
        self.heatmap.setImage(self.data, levels=(0, 1))
        
        # Auto-resize to fit the data
        self.graphWidget.autoRange()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main = HeatmapWindow()
    main.show()
    sys.exit(app.exec())
