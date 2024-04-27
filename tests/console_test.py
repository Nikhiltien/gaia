import sys
import asyncio
import numpy as np
import pyqtgraph as pg
from qasync import QEventLoop, QApplication, asyncClose, asyncSlot
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, \
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox

from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(base_dir))

from src.feed import Feed


class MainWindow(QWidget):
    def __init__(self, feed: Feed):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.feed = feed

        self.chart_window = ChartWindow()
        self.account_window = AccountWindow()
        self.layout().addWidget(self.chart_window)
        self.layout().addWidget(self.account_window)

        self.worker = Worker(feed)

    async def start(self):
        asyncio.create_task(self.worker.run())
        asyncio.create_task(self.chart_window.start_chart_updates())

    @asyncClose
    async def closeEvent(self, event):
        pass


class ChartWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        self.setup_controls()
        self.setup_chart()
    
    def setup_controls(self):
        """Setup symbol selection and display mode buttons."""
        control_layout = QHBoxLayout()
        self.layout().addLayout(control_layout)

        self.symbol_selector = QComboBox()
        self.symbol_selector.addItems(["BTC-USD", "ETH-USD", "LTC-USD"])
        control_layout.addWidget(self.symbol_selector)

        self.display_mode_button = QComboBox()
        self.display_mode_button.addItems(["Trades", "Order Book", "Candles"])
        control_layout.addWidget(self.display_mode_button)

    def setup_chart(self):
        """Initialize the chart widget."""
        self.chart = pg.PlotWidget()
        self.chart_plot = self.chart.plot(pen='g')
        self.layout().addWidget(self.chart)

    def toggle_display_mode(self):
        """Toggle between different display modes (trades, orderbook, candles)."""
        modes = ["trades", "orderbook", "candles"]
        current_index = modes.index(self.display_mode)
        self.display_mode = modes[(current_index + 1) % len(modes)]
        self.display_mode_button.setText(f"Mode: {self.display_mode.capitalize()}")

    async def start_chart_updates(self):
        """Simulate chart updates for demonstration purposes."""
        y = np.random.normal(size=(100,))
        while True:
            y[:-1] = y[1:]  # Shift data
            y[-1] = np.random.normal()  # Add new data point
            self.chart_plot.setData(y)
            await asyncio.sleep(0.1)


class AccountWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.setup_tabs()
    
    def setup_tabs(self):
        self.tab_widget = QTabWidget()
        self.layout().addWidget(self.tab_widget)

        self.setup_balances_tab()
        self.setup_inventory_tab()
        self.setup_orders_tab()
        self.setup_trades_tab()
        self.setup_performance_tab()
        
    def setup_balances_tab(self):
        self.tab_balances = QTableWidget(10, 2)
        self.tab_balances.setHorizontalHeaderLabels(["Total Equity", "Balance"])
        self.tab_widget.addTab(self.tab_balances, "Balances")

    def setup_inventory_tab(self):
        self.tab_inventory = QTableWidget(10, 5)
        self.tab_inventory.setHorizontalHeaderLabels(
            ["Symbol", "Qty", "Mkt Price", "Avg Entry Price", "Unrealized P/L"])
        self.tab_widget.addTab(self.tab_inventory, "Inventory")
        
    def setup_orders_tab(self):
        self.tab_orders = QTableWidget(10, 7)
        self.tab_orders.setHorizontalHeaderLabels(
            ["Event Time", "Status", "Symbol", "Side", "Price", "Orig Qty", "CumQty"])
        self.tab_widget.addTab(self.tab_orders, "Orders")
        
    def setup_trades_tab(self):
        self.tab_trades = QTableWidget(10, 6)
        self.tab_trades.setHorizontalHeaderLabels(
            ["Event Time", "Symbol", "Side", "Price", "Quantity", "P/L"])
        self.tab_widget.addTab(self.tab_trades, "Trades")
        
    def setup_performance_tab(self):
        self.tab_performance = QTableWidget(10, 2)
        self.tab_performance.setHorizontalHeaderLabels(["P/L (1 hr)", "Total Trades"])
        self.tab_widget.addTab(self.tab_performance, "Performance")


class Worker(QObject):
    data_updated = Signal(object)  # or more specific signal types depending on data structure

    def __init__(self, feed):
        super().__init__()
        self.feed = feed
        self.is_active = True

    async def run(self):
        while self.is_active:
            # Perform data fetching and processing
            data = 1 # await self.feed.get_latest_data()  # hypothetical async method
            self.data_updated.emit(data)
            print(data)
            await asyncio.sleep(1)  # polling interval


if __name__ == "__main__":
    app = QApplication(sys.argv)
    event_loop = QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)

    main_window = MainWindow(Feed())
    main_window.resize(800, 600)
    main_window.show()

    event_loop.create_task(main_window.start())

    with event_loop:
        event_loop.run_forever()