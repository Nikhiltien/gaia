import os
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam
import matplotlib.pyplot as plt

SEQUENCE_LENGTH = 50

SYMBOLS = 1
MAX_DEPTH = 10

TIMESTAMP = 1
ORDER_BOOK_DIM = MAX_DEPTH * 2 * 2
TRADES_DIM = 6
KLINES_DIM = 5

INPUT_DIM = SYMBOLS * (TIMESTAMP + ORDER_BOOK_DIM + TRADES_DIM + KLINES_DIM)

SEQUENCE_LENGTH = 50
NUM_FEATURES = 128
NUM_SEGMENTS = 10
NUM_EXPERTS = 3


class SegmentGatingNetwork(nn.Module):
    def __init__(self, num_features, num_experts):
        super().__init__()
        self.segment_gate = nn.Conv1d(in_channels=num_features, out_channels=num_experts, kernel_size=5, stride=5, padding=0)

    def forward(self, x):
        x = x.permute(0, 2, 1)
        segmented_gates = self.segment_gate(x)  # Apply convolutions along temporal dimension: [batch, experts, segments]
        return F.softmax(segmented_gates, dim=1)  # Softmax over experts dimension for each segment

class CNNExpert(nn.Module):
    def __init__(self, num_features):
        super().__init__()
        self.conv_layers = nn.Sequential(
            nn.Conv1d(in_channels=num_features, out_channels=32, kernel_size=5, stride=1, padding=2),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=2, stride=2),
            nn.Conv1d(32, 64, kernel_size=5, stride=1, padding=2),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=2, stride=2)
        )
        self.fc_layer = nn.Linear(64 * 12, 100)  # Adjust output size calculation as necessary

    def forward(self, x):
        x = x.permute(0, 2, 1)
        x = self.conv_layers(x)
        x = torch.flatten(x, 1)
        x = self.fc_layer(x)
        return x

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=5000):
        super().__init__()
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe = torch.zeros(max_len, d_model)
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.encoding = pe.unsqueeze(0)

    def forward(self, x):
        x = x + self.encoding[:, :x.size(1)].detach()
        return x

class TransformerExpert(nn.Module):
    def __init__(self, d_model, max_seq_length):
        super().__init__()
        self.positional_encoder = PositionalEncoding(d_model, max_seq_length)
        self.transformer_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=8, dropout=0.1, batch_first=True)
        self.encoder = nn.TransformerEncoder(self.transformer_layer, num_layers=1)
        self.fc_layer = nn.Linear(d_model, 100)

    def forward(self, x):
        x = self.positional_encoder(x)
        x = self.encoder(x)
        x = torch.mean(x, 1)  # Average pooling over sequence dimension
        x = self.fc_layer(x)
        return x

class FullyConnectedExpert(nn.Module):
    def __init__(self, in_features):
        super().__init__()
        self.fc_layers = nn.Sequential(
            nn.Linear(in_features, 300),  # Adjust input dimension based on actual input flattening
            nn.ReLU(),
            nn.Linear(300, 100)
        )

    def forward(self, x):
        x = torch.flatten(x, 1)
        x = self.fc_layers(x)
        return x

class MixtureOfExperts(nn.Module):
    def __init__(self, learning_rate=0.001):
        super().__init__()
        self.experts = nn.ModuleList([
            CNNExpert(NUM_FEATURES),
            TransformerExpert(NUM_FEATURES, SEQUENCE_LENGTH),
            FullyConnectedExpert(NUM_FEATURES * SEQUENCE_LENGTH)
        ])
        self.gating_network = SegmentGatingNetwork(NUM_FEATURES, NUM_EXPERTS)
        self.output_heads = nn.ModuleDict({
            'volatility': nn.Linear(100 * NUM_SEGMENTS, 1),
            'momentum': nn.Linear(100 * NUM_SEGMENTS, 1),
            'mean_reversion': nn.Linear(100 * NUM_SEGMENTS, 1),
        })

        self.optimizer = Adam(self.parameters(), lr=learning_rate)
        self.criterion = nn.MSELoss()

    def forward(self, x):
        gating_weights = self.gating_network(x)  # [batch, num_experts, num_segments]
        expert_outputs = torch.stack([expert(x).unsqueeze(1).repeat(1, NUM_SEGMENTS, 1) for expert in self.experts], dim=1)  # [batch, num_experts, num_segments, output]
        outputs = torch.einsum('bns,bnso->bso', gating_weights, expert_outputs).view(x.shape[0], -1)  # Weighted sum over experts and flatten
        final_outputs = {name: head(outputs) for name, head in self.output_heads.items()}
        return final_outputs


def save_model(model, filepath):
    torch.save({
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': model.optimizer.state_dict()
    }, filepath)
    print("Model and optimizer saved successfully.")

def load_model(model, filepath):
    if os.path.exists(filepath):
        try:
            checkpoint = torch.load(filepath)
            model.load_state_dict(checkpoint['model_state_dict'])
            model.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            print("Model and optimizer loaded successfully.")
        except Exception as e:
            print(f"Error loading model and optimizer: {e}")
    else:
        print("No model file found; starting with a new model.")
    model.train()
    return model

def train(model, epochs, train_loader):
    model.train()
    for epoch in range(epochs):
        total_loss = 0
        for x_batch, y_batch_all in train_loader:
            outputs = model(x_batch)
            loss = 0
            for i, key in enumerate(['volatility', 'momentum', 'mean_reversion']): 
                label = y_batch_all[:, i].unsqueeze(1)
                loss += model.criterion(outputs[key], label)
                
            model.optimizer.zero_grad()
            loss.backward()
            model.optimizer.step()
            total_loss += loss.item()

        print(f"Epoch {epoch+1}/{epochs}, Loss: {total_loss/len(train_loader)}")

def evaluate(model, test_loader):
    model.eval()
    with torch.no_grad():
        total_loss = 0
        for x_batch, y_batch in test_loader:
            outputs = model(x_batch)
            loss = 0
            for i, key in enumerate(['volatility', 'momentum', 'mean_reversion']): 
                label = y_batch[:, i].unsqueeze(1)  # Access labels by column index
                loss += model.criterion(outputs[key], label)
            total_loss += loss.item()
        print(f"Test Loss: {total_loss/len(test_loader)}")

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

def evaluate_and_capture(model, test_loader):
    model.eval()
    predictions = []
    actuals = []
    with torch.no_grad():
        for x_batch, y_batch in test_loader:
            outputs = model(x_batch)
            # Assuming you want to visualize the predictions for 'volatility'
            predicted = outputs['momentum'].squeeze(1).cpu().numpy()  # Adjust indexing based on your output dictionary keys
            actual = y_batch[:, 1].cpu().numpy()  # Adjust indexing if different label is needed
            predictions.extend(predicted)
            actuals.extend(actual)
    return predictions, actuals

def plot_predictions_vs_actuals(predictions, actuals):
    plt.figure(figsize=(10, 6))
    plt.scatter(range(len(actuals)), actuals, color='blue', label='Actual', alpha=0.5)
    plt.scatter(range(len(predictions)), predictions, color='red', label='Predicted', alpha=0.5)
    plt.title('Comparison of Actual and Predicted Values')
    plt.xlabel('Sample Index')
    plt.ylabel('Value')
    plt.legend()
    plt.show()

if __name__ == "__main__":
    batch_size = 100
    learning_rate = 0.001
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
    save_model(model, 'mixture_of_experts.pth')