import sys
import asyncio
import numpy as np
import pyqtgraph as pg
from collections import deque

from qasync import QEventLoop, QApplication, asyncClose, asyncSlot
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, \
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox
from typing import List, Dict, Tuple, Any

from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(base_dir))

from src.logger import setup_logger
from src.core import load_config
from src.database.db_manager import PGDatabase


class MainWindow(QWidget):
    def __init__(self, config: Dict, database: PGDatabase):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.config = config
        self.db = database

        self.chart_window = ChartWindow()
        self.chart_window.symbol_selector.currentTextChanged.connect(self.symbol_changed)
        self.account_window = AccountWindow()

        self.layout().addWidget(self.chart_window)
        self.layout().addWidget(self.account_window)

        self.worker = Worker(self.db)
        self.worker.orderbook_updated.connect(self.chart_window.update_orderbook)

    async def start(self):
        await self.db.start(self.config)
        symbols = await self.db.fetch_all_contracts()
        self.chart_window.add_symbols(symbols)
        asyncio.create_task(self.worker.run())

    def symbol_changed(self, new_symbol):
        if new_symbol != "-- Select symbol --":  # Assuming first item is a placeholder
            self.worker.update_symbol(new_symbol)
            self.chart_window.reset_charts()

    @asyncClose
    async def closeEvent(self, event):
        pass


class ChartWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.initialize_windows()

        self.setup_controls()
        self.setup_chart()
    
    def initialize_windows(self):
        self.bid_history = deque(maxlen=50)
        self.ask_history = deque(maxlen=50)

    def reset_charts(self):
        """Reset the chart data."""
        self.initialize_windows()  # Clear history
        self.bid_plot.clear()
        self.ask_plot.clear()
        self.chart.autoRange()

    def setup_controls(self):
        """Setup symbol selection and display mode buttons."""
        control_layout = QHBoxLayout()
        self.layout().addLayout(control_layout)

        self.symbol_selector = QComboBox()
        self.symbol_selector.addItem("-- Select symbol --")
        control_layout.addWidget(self.symbol_selector)

        self.display_mode_button = QComboBox()
        self.display_mode_button.addItems(["Trades", "Order Book", "Candles"])
        control_layout.addWidget(self.display_mode_button)

    def add_symbols(self, symbols: List):
        formatted_symbols = [f"{contract['exchange']}:{contract['symbol']}" for contract in symbols]
        self.symbol_selector.addItems(formatted_symbols)

    def setup_chart(self):
        """Initialize chart widget with two line plots for bid and ask."""
        self.chart = pg.PlotWidget()
        self.bid_plot = self.chart.plot(pen=pg.mkPen('g', width=2))
        self.ask_plot = self.chart.plot(pen=pg.mkPen('r', width=2))
        self.chart.showGrid(x=True, y=True, alpha=0.3)
        self.layout().addWidget(self.chart)

    def toggle_display_mode(self):
        """Toggle between different display modes (trades, orderbook, candles)."""
        modes = ["trades", "orderbook", "candles"]
        current_index = modes.index(self.display_mode)
        self.display_mode = modes[(current_index + 1) % len(modes)]
        self.display_mode_button.setText(f"Mode: {self.display_mode.capitalize()}")

    def update_orderbook(self, orderbook):
        """Update the chart with new orderbook data, plotting only the best bid and best ask prices, and update heatmap."""
        bids, asks = orderbook
        if bids.size > 0 and asks.size > 0:
            best_bid_price = bids[-1][0]  # Highest bid price
            best_ask_price = asks[0][0]  # Lowest ask price

            # Append new data points to the historical prices for plotting
            self.bid_history.append(best_bid_price)
            self.ask_history.append(best_ask_price)

            # Update plot data
            self.bid_plot.setData(list(range(len(self.bid_history))), self.bid_history)
            self.ask_plot.setData(list(range(len(self.ask_history))), self.ask_history)

            # Update heatmap
            # self.update_heatmap(bids, asks)

            padding = 0  # 5% padding
            y_min = bids[0][0] - (bids[0][0] * padding)
            y_max = asks[-1][0] + (asks[-1][0] * padding)
            self.chart.setYRange(y_min, y_max)
            

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
    data_updated = Signal(object)  # for other updates
    orderbook_updated = Signal(tuple)  # to emit orderbook data as (bids, asks)

    def __init__(self, database: PGDatabase):
        super().__init__()
        self.db = database
        self.is_active = True
        self.symbol = None
    
    def update_symbol(self, symbol):
        self.symbol = symbol

    async def run(self):
        while self.is_active:
            if self.symbol:
                exchange, symbol = self.symbol.split(":")
                con_id, _ = await self.db.fetch_contract_by_symbol_exchange(symbol, exchange)
                orderbook = await self.db.fetch_order_book(con_id)
                orderbook = self.db.json_to_numpy(orderbook[0]['bids'], orderbook[0]['asks'])
                self.orderbook_updated.emit(orderbook)
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    logging = setup_logger(level='INFO', stream=True)
    
    app = QApplication(sys.argv)
    event_loop = QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)

    config = load_config()
    database = PGDatabase()

    main_window = MainWindow(config, database)
    main_window.resize(800, 600)
    main_window.show()

    event_loop.create_task(main_window.start())

    with event_loop:
        event_loop.run_forever()