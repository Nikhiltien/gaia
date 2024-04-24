import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam

SEQUENCE_LENGTH = 50

SYMBOLS = 1
MAX_DEPTH = 10

TIMESTAMP = 1
ORDER_BOOK_DIM = MAX_DEPTH * 2 * 2
TRADES_DIM = 6
KLINES_DIM = 5

INPUT_DIM = SYMBOLS * (TIMESTAMP + ORDER_BOOK_DIM + TRADES_DIM + KLINES_DIM)

SEQUENCE_LENGTH = 50
NUM_FEATURES = 128  # Adjust based on calculated input dimensions
NUM_SEGMENTS = 10
NUM_EXPERTS = 3

class SegmentGatingNetwork(nn.Module):
    def __init__(self, num_features, num_experts):
        super().__init__()
        self.segment_gate = nn.Conv1d(in_channels=num_features, out_channels=num_experts, kernel_size=5, stride=5, padding=0)

    def forward(self, x):
        # x shape: [batch, features, sequence_length]
        x = x.permute(0, 2, 1)  # IMPORTANT: adjust to [batch, sequence_length, features] for Conv1d
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
        self.fc_layer = nn.Linear(64 * 7, 100)  # Adjust output size calculation as necessary

    def forward(self, x):
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
        self.transformer_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=8, dropout=0.1)
        self.encoder = nn.TransformerEncoder(self.transformer_layer, num_layers=1)
        self.fc_layer = nn.Linear(d_model, 100)

    def forward(self, x):
        x = self.positional_encoder(x)
        x = self.encoder(x)
        x = torch.mean(x, 1)  # Average pooling over sequence dimension
        x = self.fc_layer(x)
        return x

class FullyConnectedExpert(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc_layers = nn.Sequential(
            nn.Linear(128, 300),  # Adjust input dimension based on actual input flattening
            nn.ReLU(),
            nn.Linear(300, 100)
        )

    def forward(self, x):
        x = torch.flatten(x, 1)
        x = self.fc_layers(x)
        return x

class MixtureOfExperts(nn.Module):
    def __init__(self):
        super().__init__()
        self.experts = nn.ModuleList([
            CNNExpert(NUM_FEATURES),
            TransformerExpert(NUM_FEATURES, SEQUENCE_LENGTH),
            FullyConnectedExpert()
        ])
        self.gating_network = SegmentGatingNetwork(NUM_FEATURES, NUM_EXPERTS)
        self.output_heads = nn.ModuleDict({
            'volatility': nn.Linear(100 * NUM_SEGMENTS, 1),
            'momentum': nn.Linear(100 * NUM_SEGMENTS, 1),
            'mean_reversion': nn.Linear(100 * NUM_SEGMENTS, 1),
        })

    def forward(self, x):
        gating_weights = self.gating_network(x)  # [batch, num_experts, num_segments]
        expert_outputs = torch.stack([expert(x).unsqueeze(1).repeat(1, NUM_SEGMENTS, 1) for expert in self.experts], dim=1)  # [batch, num_experts, num_segments, output]
        outputs = torch.einsum('bns,bnso->bso', gating_weights, expert_outputs).view(x.shape[0], -1)  # Weighted sum over experts and flatten
        final_outputs = {name: head(outputs) for name, head in self.output_heads.items()}
        return final_outputs
    
def save_model(model, filepath):
    torch.save(model.state_dict(), filepath)

def load_model(model, filepath):
    try:
        model.load_state_dict(torch.load(filepath))
        model.train()
    except Exception as e:
        print(f"Error loading model: {e} - Starting new model.")

def generate_synthetic_data(batch_size, sequence_length, num_features, num_samples=500):
    """
    Generate synthetic data imitating a simplified financial market sequence.
    Three patterns for volatility, momentum, and mean reversion.
    """
    data = np.zeros((num_samples, batch_size, sequence_length, num_features))
    labels = {'volatility': np.zeros((num_samples, batch_size, 1)),
              'momentum': np.zeros((num_samples, batch_size, 1)),
              'mean_reversion': np.zeros((num_samples, batch_size, 1))}

    for i in range(num_samples):
        for j in range(batch_size):
            data[i, j, :, :] = np.random.normal(0, 1, (sequence_length, num_features)).astype(np.float32)

            # Simple patterns: sinusoidal for volatility, linear trend for momentum, oscillation for mean reversion
            labels['volatility'][i, j] = np.sin(i % sequence_length) + np.random.normal(0, 0.1)
            labels['momentum'][i, j] = (i % sequence_length) / sequence_length + np.random.normal(0, 0.1)
            labels['mean_reversion'][i, j] = np.abs(np.cos(i % sequence_length)) + np.random.normal(0, 0.1)
        
    return torch.from_numpy(data), {k: torch.from_numpy(v).float() for k, v in labels.items()}

def train(model, epochs, train_loader, optimizer, criterion):
    model.train()
    for epoch in range(epochs):
        total_loss = 0
        for x_batch, y_batch_all in train_loader:
            outputs = model(x_batch)  # Assuming your model gives a dict with three outputs
            loss = 0
            for i, key in enumerate(['volatility', 'momentum', 'mean_reversion']): 
                label = y_batch_all[:, i].unsqueeze(1)
                loss += criterion(outputs[key], label)
                
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        print(f"Epoch {epoch+1}/{epochs}, Loss: {total_loss/len(train_loader)}")

def evaluate(model, test_loader, criterion):
    model.eval()
    with torch.no_grad():
        total_loss = 0
        for x_batch, y_batch in test_loader:
            outputs = model(x_batch)
            loss = sum(criterion(outputs[key], y_batch[key]) for key in outputs)
            total_loss += loss.item()
        print(f"Test Loss: {total_loss/len(test_loader)}")


if __name__ == "__main__":
    batch_size = 32
    learning_rate = 0.001
    epochs = 10

    # Prepare datasets
    train_data, train_labels = generate_synthetic_data(batch_size, SEQUENCE_LENGTH, NUM_FEATURES, num_samples=500)
    test_data, test_labels = generate_synthetic_data(batch_size, SEQUENCE_LENGTH, NUM_FEATURES, num_samples=100)

    train_labels_tensor = torch.stack([train_labels['volatility'], train_labels['momentum'], train_labels['mean_reversion']], dim=1).squeeze(-1)
    test_labels_tensor = torch.stack([test_labels['volatility'], test_labels['momentum'], test_labels['mean_reversion']], dim=1).squeeze(-1)

    train_dataset = torch.utils.data.TensorDataset(train_data, train_labels_tensor)
    test_dataset = torch.utils.data.TensorDataset(test_data, test_labels_tensor)

    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=batch_size, shuffle=True)

    # Initialize model and optimizer
    # model = load_model('mixture-of-experts.pth')
    model = MixtureOfExperts()
    optimizer = Adam(model.parameters(), lr=learning_rate)
    criterion = nn.MSELoss()

    # Training loop
    train(model, epochs, train_loader, optimizer, criterion)

    # Evaluation
    evaluate(model, test_loader, criterion)

    # Save the trained model
    save_model(model, 'mixture_of_experts.pth')