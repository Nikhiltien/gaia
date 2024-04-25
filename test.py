# import os
# import asyncio

# from dotenv import load_dotenv
# from src.logger import setup_logger
# from src.zeromq.zeromq import ZeroMQ
# from src.game_env import GameEnv
# from src.adapters.HyperLiquid.HyperLiquid_api import HyperLiquid

# eth = {
#     "symbol": "ETH",
#     "currency": "USD",
#     "secType": "PERP",
#     "exchange": "HYPERLIQUID",
# }

# logging = setup_logger(level='INFO', stream=True)

# async def main():
#     zmq = ZeroMQ()
#     pub_socket = zmq.create_publisher(port=50000)

#     env_path = os.path.expanduser('~/gaia/keys/private_key.env')
#     load_dotenv(dotenv_path=env_path)
#     PRIVATE_KEY = os.getenv('PRIVATE_KEY_MAIN')
#     public = '0x7195d5fBC22Afa1FF6A0A25591285Db7a81838D4'
#     # vault = '0xb22177120b2f33d39770a25993bcb14f2753bae6'

#     adapter = HyperLiquid(msg_callback=pub_socket.publish_data)
#     await adapter.connect(key=PRIVATE_KEY, public=public) # , vault=vault)

#     # await adapter.subscribe_all_symbol([{"symbol": "ETH"}])
#     await adapter.subscribe_trades({"symbol": "ETH"})
#     await adapter.subscribe_order_book(contract={"symbol": "ETH"}, num_levels=10)

#     await asyncio.sleep(300)

# if __name__ == "__main__":
#     asyncio.run(main())

# ssh -i /Users/nikhiltien/Gaea/keys/oceanid_rsa root@157.245.123.122

import torch
import numpy as np
from src.utils.math import bbw
from src.models.tet.moe import MixtureOfExperts, load_model, save_model, train,\
evaluate_and_capture, plot_predictions_vs_actuals

SEQUENCE_LENGTH = 50
NUM_FEATURES = 128

def generate_synthetic_data(batch_size, sequence_length, num_features):
    """
    Generate synthetic data where the average of 128 features at each timestep
    follows a sinusoidal pattern, with derived labels for volatility, momentum, and trend.
    """
    data = np.random.normal(0, 1, (batch_size, sequence_length, num_features))
    labels = {
        'volatility': np.zeros((batch_size, 1)),
        'momentum': np.zeros((batch_size, 1)),
        'mean_reversion': np.zeros((batch_size, 1))
    }

    for i in range(batch_size):
        phase = np.random.uniform(0, 2 * np.pi)  # Random phase shift
        amplitude = np.random.uniform(0.5, 2.0)  # Random amplitude
        frequency = np.random.uniform(0.1, 0.5)  # Random frequency within a reasonable range

        sinusoidal_pattern = amplitude * np.sin(frequency * np.arange(sequence_length) + phase)
        
        # Adjust the data so that the mean of the features at each timestep matches the sinusoidal pattern
        data_mean_adjustment = sinusoidal_pattern - data[i].mean(axis=1)
        data[i] += data_mean_adjustment[:, np.newaxis]  # Broadcasting the adjustment

        # Generating labels based on the properties of the sinusoid
        labels['volatility'][i] = amplitude
        midpoint = sequence_length // 2
        labels['momentum'][i] = (sinusoidal_pattern[midpoint] - sinusoidal_pattern[midpoint - 1]) * frequency
        labels['mean_reversion'][i] = 1 if sinusoidal_pattern[-1] > sinusoidal_pattern[-10] else 0

    return torch.from_numpy(data).float(), {k: torch.from_numpy(v).float() for k, v in labels.items()}

def main():
    batch_size = 100
    epochs = 10
    model_path = 'mixture_of_experts.pth'

    model = MixtureOfExperts()
    model = load_model(model, model_path)

    # Prepare datasets
    train_data, train_labels = generate_synthetic_data(batch_size, SEQUENCE_LENGTH, NUM_FEATURES)
    test_data, test_labels = generate_synthetic_data(batch_size, SEQUENCE_LENGTH, NUM_FEATURES)

    train_labels_tensor = torch.stack([train_labels['volatility'], train_labels['momentum'], train_labels['mean_reversion']], dim=1).squeeze(-1)
    test_labels_tensor = torch.stack([test_labels['volatility'], test_labels['momentum'], test_labels['mean_reversion']], dim=1).squeeze(-1)

    train_dataset = torch.utils.data.TensorDataset(train_data, train_labels_tensor)
    test_dataset = torch.utils.data.TensorDataset(test_data, test_labels_tensor)

    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=batch_size, shuffle=True)

    # Training loop
    train(model, epochs, train_loader)

    # Evaluate
    # evaluate(model, test_loader)
    predictions, actuals = evaluate_and_capture(model, test_loader)

    # Plotting
    plot_predictions_vs_actuals(predictions, actuals)

    # Save the trained model
    # save_model(model, 'mixture_of_experts.pth')

if __name__ == "__main__":
    main()