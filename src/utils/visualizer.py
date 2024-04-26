import dash
import numpy as np
import pandas as pd
import datetime as dt
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.interpolate import griddata

class Visualizer:
    def __init__(self):
        # self.data = pd.DataFrame()
        self.app = dash.Dash(__name__)

        # Initialize Dash layout
        self.app.layout = html.Div([
            dcc.Graph(id='live-graph'),
            dcc.Interval(
                id='interval-update',
                interval=1*1000,  # Update every 1 second
                n_intervals=0
            ),
        ])

        # Initialize data
        self.time = []
        self.price = []

        @self.app.callback(
            Output('live-graph', 'figure'),
            [Input('interval-update', 'n_intervals')]
        )
        def update_graph(n):
            # Fetch new data from DataFrame
            new_time = self.data['timestamp'].tolist()
            new_price = self.data['price'].tolist()

            # Create new figure with updated data
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=new_time, y=new_price, mode='lines+markers'))
            return fig

    def update_data(self, df):
        self.data = df

    def plot_historical_data(self, historical_data=None):
        """
        Plot historical OHLC data or line plot from the DataFrame.
        """
        if historical_data is None or historical_data.empty:
            self.logger.warning("No historical data provided or empty DataFrame.")
            return

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.02, 
                            subplot_titles=("OHLC", "Volume"), 
                            row_heights=[0.7, 0.3])

        # Convert UNIX timestamp to datetime
        historical_data['timestamp'] = pd.to_datetime(historical_data['timestamp'], unit='s')

        # OHLC trace
        fig.add_trace(go.Candlestick(x=historical_data['timestamp'],
                                    open=historical_data['open'],
                                    high=historical_data['high'],
                                    low=historical_data['low'],
                                    close=historical_data['close'],
                                    name='OHLC'), row=1, col=1)

        # Volume trace
        fig.add_trace(go.Bar(x=historical_data['timestamp'], 
                            y=historical_data['volume'], 
                            name='Volume', 
                            marker_color='blue'), row=2, col=1)

        start_date = historical_data['timestamp'].min()
        end_date = historical_data['timestamp'].max()
        total_days = (end_date - start_date).days
        tickvals = [start_date + pd.Timedelta(days=i) for i in range(total_days + 1)]
        ticktext = [t.strftime('%Y-%m-%d') for t in tickvals]

        fig.update_xaxes(
            tickvals=tickvals,
            ticktext=ticktext,
            rangebreaks=[
                dict(pattern="hour", bounds=[0, 17.5]),
                dict(bounds=["sat", "mon"])
            ]
        )

        fig.update_layout(
            template='plotly_dark',
            width=1400,
            height=800,
            title="Historical Data Visualization"
        )

        fig.show()

    def compute_volatility_surface(self, spot_price, risk_free_rate, option_type, date=None):
        strike_prices = []
        time_to_expirations = []
        implied_volatilities = []

        if not date:
            date = dt.datetime.now()

        filtered_data = self.data[self.data['right'] == option_type].dropna()
        print(filtered_data)
        try:
            filtered_data['strike'] = filtered_data['strike'].astype(float)
            filtered_data['price'] = filtered_data['price'].astype(float)
        except ValueError as ve:
            print(f"Error converting data types: {ve}")
            return None, None, None

        unique_expirations = filtered_data['expiration'].dropna().unique()

        if len(unique_expirations) == 0:
            print("No unique expirations found in the filtered data.")
            return None, None, None

        for expiration_date in unique_expirations:
            if expiration_date is None:
                continue
            T = (expiration_date - date).days / 365.0
            expiration_data = filtered_data[filtered_data['expiration'] == expiration_date]

            for strike in expiration_data['strike'].unique():
                strike_data = expiration_data[expiration_data['strike'] == strike]

                if len(strike_data['price']) != 1:
                    print(f"Ambiguous or missing option prices for strike {strike}. Using the first one.")

                try:
                    option_price = float(strike_data['price'].iloc[0])
                except ValueError:
                    print(f"Invalid option price: {strike_data['price'].iloc[0]}")
                    continue

                if option_price < 0:
                    print(f"Negative option price: {option_price}")
                    continue

                implied_vol = calculate_implied_volatility(
                    option_type, option_price, spot_price, strike, T, risk_free_rate
                )

                strike_prices.append(strike)
                time_to_expirations.append(T)
                implied_volatilities.append(implied_vol)

        if len(strike_prices) == 0:
            print("No valid strikes found.")
            return None, None, None

        xi = np.linspace(min(strike_prices), max(strike_prices), 100)
        yi = np.linspace(min(time_to_expirations), max(time_to_expirations), 100)
        zi = griddata(
            (strike_prices, time_to_expirations), 
            implied_volatilities, 
            (xi[None, :], yi[:, None]), 
            method='cubic'
        )
        
        return xi, yi, zi

    def plot_surface(self, x, y, z, contract_name="SPY"):
        """
        Plot the volatility surface using plotly.
        Arguments:
        - x: Strikes or X-axis data
        - y: Expirations or Y-axis data
        - z: Volatility or Z-axis data
        """
        fig = go.Figure(data=[go.Surface(z=z, x=x, y=y)])
        
        fig.update_layout(
            template='plotly_dark',
            margin=dict(l=0, r=0, b=0, t=40),
            scene=dict(
                xaxis_title='Strikes',
                yaxis_title='Expiration',
                zaxis_title='Implied Volatility'
            ),
            title=f"{contract_name} Volatility Surface"
        )

        fig.show()

    def visualize(self, S, r, option_type):
        """
        Main method to fetch data, compute the volatility surface, and visualize it.
        """
        x, y, z = self.compute_volatility_surface(S, r, option_type)
        self.plot_surface(x, y, z)