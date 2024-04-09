import numpy as np
from numpy.typing import NDArray
from numba import njit
from numba.types import bool_, int64, float64, Array
from numba.experimental import jitclass
from typing import Optional

from src.utils.ring_buffer import RingBufferF64

spec = [
    ('window', int64),
    ('alpha', float64),
    ('fast', bool_),
    ('value', float64),
    ('rb', RingBufferF64.class_type.instance_type),
]

@jitclass(spec)
class EMA:
    """
    Exponential Moving Average (EMA) with optional RingBuffer to store history.

    Attributes:
    -----------
    window : int
        The window size for the EMA calculation.

    alpha : float
        The smoothing factor applied to the EMA. Default is calculated as `3 / (window + 1)`.

    fast : bool
        If True, the history of calculated EMA values is not stored.

    value : float
        The current value of the EMA.

    rb : RingBufferF64
        A ring buffer to store EMA values history, activated if `fast` is False.
    """
    def __init__(self, window: int, alpha: Optional[float]=0, fast: bool=False):
        self.window = window
        self.alpha = alpha if alpha != 0 else 3 / (self.window + 1)
        self.fast = fast
        self.value = 0.0
        self.rb = RingBufferF64(self.window)

    def _recursive_ema_(self, update: float) -> float:
        """
        Internal method to calculate the EMA given a new data point.

        Parameters:
        -----------
        update : float
            The new data point to include in the EMA calculation.

        Returns:
        --------
        float
            The updated EMA value.
        """
        return self.alpha * update + (1 - self.alpha) * self.value

    def initialize(self, arr_in: Array) -> None:
        """
        Initializes the EMA calculator with a series of data points.

        Parameters:
        -----------
        arr_in : Iterable[float]
            The initial series of data points to feed into the EMA calculator.
        """
        _ = self.rb.reset()
        self.value = arr_in[0]
        for val in arr_in:
            self.value = self._recursive_ema_(val)
            if not self.fast:
                self.rb.appendright(self.value)

    def update(self, new_val: float) -> None:
        """
        Updates the EMA calculator with a new data point.

        Parameters:
        -----------
        new_val : float
            The new data point to include in the EMA calculation.
        """
        self.value = self._recursive_ema_(new_val)
        if not self.fast:
            self.rb.appendright(self.value)



@njit(cache=True)
def ema_weights(window: int, reverse: bool=False, alpha: Optional[float]=0) -> Array:
    """
    Calculate EMA (Exponential Moving Average)-like weights for a given window size.

    Parameters
    ----------
    window : int
        The number of periods to use for the EMA calculation.
    reverse : bool, optional
        If True, the weights are returned in reverse order. The default is False.
    alpha : float, optional
        The decay factor for the EMA calculation. If not provided, it is calculated as 3 / (window + 1).

    Returns
    -------
    Array
        An array of EMA-like weights.

    Examples
    --------
    >>> ema_weights(window=5)
    array([0.33333333, 0.22222222, 0.14814815, 0.09876543, 0.06584362])

    >>> ema_weights(window=5, reverse=True)
    array([0.06584362, 0.09876543, 0.14814815, 0.22222222, 0.33333333])

    >>> ema_weights(window=5, alpha=0.5)
    array([0.5    , 0.25   , 0.125  , 0.0625 , 0.03125])
    """
    alpha = 3 / float(window + 1) if alpha == 0 else alpha
    weights = np.empty(window, dtype=float64)

    for i in range(window):
        weights[i] = alpha * (1 - alpha) ** i
 
    return weights[::-1] if reverse else weights

@njit(cache=True)
def trades_imbalance(trades: NDArray, window: int) -> float:
    """
    Calculates the normalized imbalance between buy and sell trades within a specified window,
    using geometrically weighted quantities. The imbalance reflects the dominance of buy or sell trades,
    weighted by the recency of trades in the window.

    Steps:
    1. Determine the effective window size, the lesser of the specified window or the total trades count.
    2. Generate exponential moving average (EMA) weights for the effective window size, with recent trades
       given higher significance.
    3. Iterate through the trades within the window, applying the weights to the log of (1 + trade quantity)
       to calculate weighted trade quantities. Separate cumulative totals are maintained for buys and sells based
       on the trade side.
    4. Compute the normalized imbalance as the difference between cumulative buy and sell quantities divided
       by their sum, yielding a measure from -1 (sell dominance) to 1 (buy dominance).

    Parameters
    ----------
    trades : NDArray
        A 2D array of trade data, where each row represents a trade in format [time, side, price, size]
    window : int
        The number of most recent trades to consider for the imbalance calculation.

    Returns
    -------
    float
        The normalized imbalance, ranging from -1 (complete sell dominance) to 1 (complete buy dominance).

    Examples
    --------
    >>> trades = np.array([
    ...     [1e10, 0.0, 100.75728, 0.70708],
    ...     [1e10, 1.0, 100.29356, 0.15615],
    ...     [1e10, 0.0, 100.76157, 0.94895],
    ...     [1e10, 1.0, 100.46078, 0.23170],
    ...     [1e10, 0.0, 100.18463, 0.87096]
    ... ])
    >>> window = 5
    >>> print(trades_imbalance(trades, window))
    -0.7421903970691232
    """
    window = min(window, trades.shape[0])
    weights = ema_weights(window, reverse=True)
    delta_buys, delta_sells = 0.0, 0.0
    
    for i in range(window):
        trade_side = trades[i, 1]
        weighted_qty = np.log(1 + trades[i, 3]) * weights[i]

        if trade_side == 0.0:
            delta_buys += weighted_qty
        else:
            delta_sells += weighted_qty

    return (delta_buys - delta_sells) / (delta_buys + delta_sells)