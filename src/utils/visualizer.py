import dash
import numpy as np
import pandas as pd
import datetime as dt
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.interpolate import griddata
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from numpy.typing import NDArray

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

    def plot_candles(self, symbol: str, candles: NDArray):
        timestamps = candles[:, 0]
        opens = candles[:, 1]
        highs = candles[:, 2]
        lows = candles[:, 3]
        closes = candles[:, 4]
        volumes = candles[:, 5]
        upper = candles[:, 6]
        lower = candles[:, 7]

        # Convert timestamps from ms to datetime for plotting
        dates = [dt.datetime.utcfromtimestamp(ts / 1000) for ts in timestamps]

        df = pd.DataFrame({
            'Open': opens,
            'High': highs,
            'Low': lows,
            'Close': closes,
            'Volume': volumes,
            'Upper Band': upper,
            'Lower Band': lower
        }, index=pd.DatetimeIndex(dates))

        # Setup figure and subplot grid
        fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, gridspec_kw={'height_ratios': [3, 1]}, figsize=(10, 8))
        fig.suptitle(f'{symbol} Candlestick Chart')
        ax1.grid(True, which='both', linestyle='--', linewidth=0.5)
        ax2.grid(True, which='both', linestyle='--', linewidth=0.5)

        # Create candlestick bars for highs and lows
        colors = ['green' if close >= open_ else 'red' for open_, close in zip(df['Open'], df['Close'])]
        ax1.bar(df.index, df['High'] - df['Low'], bottom=df['Low'], color=colors, width=0.6/(24*60), linewidth=0)
        ax1.bar(df.index, df['Close'] - df['Open'], bottom=df['Open'], color=colors, width=0.3/(24*60), linewidth=0)

        # Plot Bollinger Bands
        ax1.plot(df.index, df['Upper Band'], label='Bollinger Bands', color='blue', linewidth=1.5)
        ax1.plot(df.index, df['Lower Band'], color='blue', linewidth=1.5)

        # Plot volume bars
        ax2.bar(df.index, df['Volume'], color='blue', width=0.6/(24*60))

        # Formatting dates on the x-axis
        ax1.xaxis_date()
        locator = mdates.AutoDateLocator(maxticks=10)
        formatter = mdates.ConciseDateFormatter(locator)
        ax1.xaxis.set_major_locator(locator)
        ax1.xaxis.set_major_formatter(formatter)
        fig.autofmt_xdate()  # Auto formats the x-axis labels to fit them better

        # Set labels and titles
        ax1.set_ylabel('Price')
        ax2.set_ylabel('Volume')
        ax2.set_xlabel('Date')

        # Add legend to distinguish plotted lines
        ax1.legend()

        plt.show()

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

                # implied_vol = calculate_implied_volatility(
                #     option_type, option_price, spot_price, strike, T, risk_free_rate
                # )

                strike_prices.append(strike)
                time_to_expirations.append(T)
                # implied_volatilities.append(implied_vol)

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