import sys
import time
import random
import logging
import json
import asyncio
import pyqtgraph as pg
from datetime import datetime
from src.zeromq.zeromq import SubscriberSocket
from PyQt5.QtWidgets import QApplication, QMainWindow, QDockWidget, QWidget, QVBoxLayout, QTabWidget, QTableView, QPushButton
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import pyqtSignal, QObject, QThread, QTimer, Qt
from asyncqt import QEventLoop

# Worker class for handling asynchronous tasks
class Worker(QObject):
    finished = pyqtSignal()
    dataFetched = pyqtSignal(dict)

    def __init__(self, zmq_subscriber, contract_id):
        super().__init__()
        self.zmq_subscriber = zmq_subscriber
        self.contract_id = contract_id

    async def run(self):
        try:
            while True:
                message = await self.zmq_subscriber.receive_message()
                logging.debug(f"message: {message}")
                market_data = json.loads(message)

                if market_data.get('contract_id') == self.contract_id:
                    self.dataFetched.emit(market_data)
        except Exception as e:
            logging.error(f"Error in Worker: {e}")
            self.finished.emit()

# EventBusConnector (mock implementation)
class EventBusConnector(QObject):
    def __init__(self):
        super().__init__()
        # Setup connections to event_bus here

# AccountWindow for displaying account information
class AccountWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        self.tabs.addTab(self.createTableView(["Total Balance", "Available"]), "Balances")
        self.tabs.addTab(self.createTableView(["Symbol", "Quantity", "Mkt Price", "Avg Entry Price", "P&L"]), "Positions")
        self.tabs.addTab(self.createTableView(["Creation Time", "Event Time", "Status", "Symbol", "Type", "Side",
                                               "Price", "Orig Qty", "CumQty"]), "Orders")
        self.tabs.addTab(self.createTableView(["Event Time", "Symbol", "Side", "Price", "Quantity", "Value"]), "Trades")
        self.tabs.addTab(self.createTableView(["P&L(daily)", "Total Trades"]), "Performance")

    def createTableView(self, columns):
        tableView = QTableView()
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(columns)
        tableView.setModel(model)
        return tableView

    def update_data(self, data):
        # Update each tab with new data
        # This is a placeholder for actual data update logic
        logging.debug(f"Updating AccountWindow with data: {data}")

class TimeAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [datetime.fromtimestamp(value).strftime('%H:%M:%S') for value in values]

class ChartWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # self.trade_plot_widget = pg.PlotWidget(axisItems={'bottom': TimeAxisItem(orientation='bottom')})
        self.trade_plot_widget = None
        self.bid_ask_plot_widget = pg.PlotWidget(axisItems={'bottom': TimeAxisItem(orientation='bottom')})
        self.layout.addWidget(self.bid_ask_plot_widget)

        self.bid_x_data = []
        self.bid_y_data = []
        self.ask_x_data = []
        self.ask_y_data = []

        self.bid_plot_data = self.bid_ask_plot_widget.plot(self.bid_x_data, self.bid_y_data, pen=pg.mkPen(color=(102, 255, 102), width=2))
        self.ask_plot_data = self.bid_ask_plot_widget.plot(self.ask_x_data, self.ask_y_data, pen=pg.mkPen(color='red', width=2))
        self.bid_ask_plot_widget.showGrid(x=True, y=True, alpha=0.3)  # Show faint grid lines

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.timer.start(25) # milliseconds
        self.time_window = 6 # window size (seconds)

        self.toggle_button = QPushButton("Show Trades", self)
        self.toggle_button.clicked.connect(self.toggle_plot)
        self.layout.addWidget(self.toggle_button, alignment=Qt.AlignTop | Qt.AlignLeft)
        self.current_plot = "bid_ask"

    def toggle_plot(self):
        if self.current_plot == 'trade':
            self.layout.replaceWidget(self.trade_plot_widget, self.bid_ask_plot_widget)
            self.trade_plot_widget.setParent(None)
            self.bid_ask_plot_widget.show()
            self.toggle_button.setText("Show Trades")
            self.current_plot = 'bid_ask'
        else:
            if not self.trade_plot_widget:
                self.initialize_trade_plot()
            self.layout.replaceWidget(self.bid_ask_plot_widget, self.trade_plot_widget)
            self.bid_ask_plot_widget.setParent(None)
            self.trade_plot_widget.show()
            self.toggle_button.setText("Show Bid/Ask")
            self.current_plot = 'trade'

    def initialize_trade_plot(self):
        self.trade_plot_widget = pg.PlotWidget(axisItems={'bottom': TimeAxisItem(orientation='bottom')})
        self.trade_x_data = []
        self.trade_y_data = []
        self.trade_plot_data = self.trade_plot_widget.plot(self.trade_x_data, self.trade_y_data, pen=pg.mkPen(color=(102, 255, 102), width=2))
        self.trade_plot_widget.showGrid(x=True, y=True, alpha=0.3)

    def update_time(self):
        current_time = time.time()
        if self.current_plot == "bid_ask":

            # Append the current time to the last data point
            if self.bid_y_data:
                self.bid_x_data.append(current_time)
                self.bid_y_data.append(self.bid_y_data[-1])

            if self.ask_y_data:
                self.ask_x_data.append(current_time)
                self.ask_y_data.append(self.ask_y_data[-1])

            while self.bid_x_data and current_time - self.bid_x_data[0] > self.time_window:
                self.bid_x_data.pop(0)
                self.bid_y_data.pop(0)
                self.ask_x_data.pop(0)
                self.ask_y_data.pop(0)

            # Update the plots
            self.bid_plot_data.setData(self.bid_x_data, self.bid_y_data)
            self.ask_plot_data.setData(self.ask_x_data, self.ask_y_data)

            # Adjust the x-axis range based on combined data
            combined_x_data = self.bid_x_data + self.ask_x_data
            if combined_x_data:
                start_time = current_time - self.time_window
                end_time = current_time
                self.bid_ask_plot_widget.setXRange(start_time, end_time, padding=0.05)
        elif self.current_plot == "trade":
            if self.trade_y_data:
                self.trade_x_data.append(current_time)
                self.trade_y_data.append(self.trade_y_data[-1])
            else:
                self.trade_x_data.append(current_time)
                self.trade_y_data.append(0)  # Default starting value

            while self.trade_x_data and current_time - self.trade_x_data[0] > self.time_window:
                self.trade_x_data.pop(0)
                self.trade_y_data.pop(0)

            self.trade_plot_data.setData(self.trade_x_data, self.trade_y_data)
            if self.trade_x_data:
                self.trade_plot_widget.setXRange(min(self.trade_x_data), max(self.trade_x_data), padding=0)


    def update_chart(self, market_data):
        timestamp = market_data.get('timestamp') / 1000.0
        if self.current_plot == "bid_ask":
            bid_price = market_data.get('bid_price')
            ask_price = market_data.get('ask_price')

            # Check if there is new data to append
            if bid_price is not None and (not self.bid_y_data or bid_price != self.bid_y_data[-1]):
                self.bid_x_data.append(timestamp)
                self.bid_y_data.append(bid_price)

            if ask_price is not None and (not self.ask_y_data or ask_price != self.ask_y_data[-1]):
                self.ask_x_data.append(timestamp)
                self.ask_y_data.append(ask_price)
        elif self.current_plot == "trade":
            trade_price = market_data.get('price')
            if trade_price is not None:
                self.trade_x_data.append(timestamp)
                self.trade_y_data.append(trade_price)

# Main application window
class Console(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HFT Console")
        self.setGeometry(100, 100, 800, 600)

        # Worker setup for asynchronous operations
        self.worker = Worker(zmq_subscriber, contract_id)
        self.worker.dataFetched.connect(self.update_ui_with_data)
        asyncio.create_task(self.worker.run())

        # Adding dockable panes
        self.add_dock_widget("Chart", ChartWindow())
        self.add_dock_widget("Account", AccountWindow())
        self.add_dock_widget("Systems", QWidget())

    def add_dock_widget(self, title, widget):
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        return dock

    def update_ui_with_data(self, data):
        dock_widgets = self.findChildren(QDockWidget)
        
        for dock in dock_widgets:
            if isinstance(dock.widget(), AccountWindow):
                dock.widget().update_data(data)
            elif isinstance(dock.widget(), ChartWindow):
                dock.widget().update_chart(data)

stylesheet = """
    QMainWindow {
        background-color: #1E1E1E; /* Dark background */
        color: #FFFFFF; /* Light text */
    }

    QDockWidget {
        border: 1px solid #444444;
    }
    
    QTabWidget::pane {
        border: 1px solid #444444;
    }

    QTabWidget::tab-bar {
        alignment: left;
    }

    QTabBar::tab {
        font-size: 12pt;
        background: #2E2E2E;
        color: #FFFFFF;
        padding: 5px;
        border: 1px solid #444444;
        width: 80%;
        height: 25%;
    }

    QTabBar::tab:selected {
        background: #3E3E3E;
        border-bottom-color: #1E1E1E; /* same as QMainWindow background for merging effect */
    }
    
    QTableView {
        selection-background-color: #3E3E3E;
        gridline-color: #3E3E3E;
    }

    QWidget {
        font-family: 'Consolas';
        font-size: 10pt;
    }

    QTableView {
        border: 1px solid #444444;
        /* Other table styles */
    }

    QTableView::item {
        padding: 2px;
    }
    
    QHeaderView::section {
        background-color: #2E2E2E;
        padding: 4px;
        border: 1px solid #444444;
    }
"""

zmq_subscriber = None # SubscriberSocket(address="tcp://localhost:5556")
contract_id = 603558814

# if __name__ == '__main__':
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

#     app = QApplication(sys.argv)
#     loop = QEventLoop(app)
#     asyncio.set_event_loop(loop)
    
#     def quit_application():
#         loop.stop()

#     app.aboutToQuit.connect(quit_application)
#     app.setStyleSheet(stylesheet)

#     with loop:
#         mainWin = Console()
#         mainWin.show()
#         loop.run_forever()
#     sys.exit(0)