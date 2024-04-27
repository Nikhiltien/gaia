import sys
import asyncio
import numpy as np
from qasync import QEventLoop, QApplication, asyncClose
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTableWidget, QTableWidgetItem
import pyqtgraph as pg

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.setup_chart()
        self.setup_tabs()
    
    def setup_chart(self):
        self.chart = pg.PlotWidget()
        self.chart_plot = self.chart.plot(pen='y')
        self.layout().addWidget(self.chart)

    def setup_tabs(self):
        self.tab_widget = QTabWidget()
        self.tab_inventory = QTableWidget(10, 3, self)
        self.tab_inventory.setHorizontalHeaderLabels(['Item', 'Quantity', 'Location'])
        self.tab_balances = QTableWidget(5, 2, self)
        self.tab_balances.setHorizontalHeaderLabels(['Account', 'Balance'])
        self.tab_trades = QTableWidget(15, 4, self)
        self.tab_trades.setHorizontalHeaderLabels(['Date', 'Buy/Sell', 'Quantity', 'Price'])
        self.tab_widget.addTab(self.tab_inventory, "Inventory")
        self.tab_widget.addTab(self.tab_balances, "Balances")
        self.tab_widget.addTab(self.tab_trades, "Trades")
        self.layout().addWidget(self.tab_widget)

    @asyncClose
    async def closeEvent(self, event):
        pass

    async def start_chart_updates(self):
        y = np.random.normal(size=(100,))
        while True:
            y[:-1] = y[1:]  # Shift data
            y[-1] = np.random.normal()  # Add new data point
            self.chart_plot.setData(y)
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    event_loop = QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)

    main_window = MainWindow()
    main_window.resize(800, 600)
    main_window.show()

    event_loop.create_task(main_window.start_chart_updates())

    with event_loop:
        event_loop.run_forever()