import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
import random
from collections import deque

SEQUENCE_LENGTH = 50

SYMBOLS = 1
MAX_DEPTH = 10
MAX_ORDERS = MAX_DEPTH * 2 * SYMBOLS

ORDER_BOOK_DIM = MAX_DEPTH * 2 * 2
TRADES_DIM = 7
KLINES_DIM = 6

ORDERS_DIM = MAX_ORDERS * 3 
INVENTORY_DIM = SYMBOLS * 3
BALANCES_DIM = 1

SYMBOLS_DATA_DIM = SYMBOLS * ORDER_BOOK_DIM + TRADES_DIM + KLINES_DIM

INPUT_DIM = ORDERS_DIM + INVENTORY_DIM + BALANCES_DIM + SYMBOLS_DATA_DIM

ACTION_SIZE = ORDER_BOOK_DIM
    

class DDQN(nn.Module):
    def __init__(self, input_dim=INPUT_DIM, action_dim=ACTION_SIZE, lr=0.001, hidden_size=128, num_layers=2, 
                 num_heads=8, dim_feedforward=256):
        super(DDQN, self).__init__()

        # self.features_model = GRUTransformerModel(input_size, hidden_size, num_layers, num_heads, dim_feedforward, output_size)
        self.fc1 = nn.Linear(input_dim, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc3 = nn.Linear(64, action_dim)
        self.optimizer = optim.Adam(self.parameters(), lr)
        self.loss = nn.MSELoss()
    
    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = torch.sigmoid(self.fc3(x))
        return x


class Agent:
    def __init__(self, model: DDQN, gamma=0.99, epsilon=0.9, lr=0.001, batch_size=64):
        
        self.model = model
        self.optimizer = optim.Adam(self.model.parameters(), lr=lr)
        self.loss_fn = nn.MSELoss()
        self.memory = deque(maxlen=10000)
        self.batch_size = batch_size
        self.gamma = gamma  # Discount factor for future rewards
        self.epsilon = epsilon

    def select_action(self, state, epsilon):
        if random.random() > epsilon:
            state = torch.tensor(state, dtype=torch.float32, device='cpu').unsqueeze(0)
            with torch.no_grad():
                q_values = self.model(state)
                action = q_values.argmax(dim=1).cpu().numpy()  # Ensure it returns array-like actions
        else:
            action = np.random.uniform(low=0, high=1, size=self.model.fc3.out_features)  # Random actions
        return action

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    def replay(self):
        if len(self.memory) < self.batch_size:
            return
        batch = random.sample(self.memory, self.batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        
        states = torch.tensor(states, dtype=torch.float32)
        next_states = torch.tensor(next_states, dtype=torch.float32)
        actions = torch.tensor(actions)
        rewards = torch.tensor(rewards)
        dones = torch.tensor(dones, dtype=torch.float32)

        current_q_values = self.model(states).gather(1, actions.unsqueeze(1)).squeeze(1)
        next_q_values = self.model(next_states).max(1)[0]
        expected_q_values = rewards + self.gamma * next_q_values * (1 - dones)

        loss = self.loss_fn(current_q_values, expected_q_values)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()


class GRUTransformerModel(nn.Module):
    def __init__(self, input_size=INPUT_DIM, hidden_size=128, num_layers=2, 
                 num_heads=8, dim_feedforward=256, output_size=ORDER_BOOK_DIM):
        super(GRUTransformerModel, self).__init__()
        self.gru = nn.GRU(input_size, hidden_size, num_layers, batch_first=True)
        self.transformer = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model=hidden_size, nhead=num_heads, dim_feedforward=dim_feedforward),
            num_layers=num_layers
        )
        self.fc = nn.Linear(hidden_size, output_size)
    
    def forward(self, x, h0):
        # GRU forward pass
        gru_out, hn = self.gru(x, h0)
        
        # Transformer takes the output from the GRU
        # Reshape the GRU output to (seq_len, batch, features) for Transformer
        trans_input = gru_out.permute(1, 0, 2)
        transformer_out = self.transformer(trans_input)
        
        # Taking the output from the last time step
        final_feature_map = transformer_out[-1, :, :]
        
        # Passing through the final fully connected layer
        output = self.fc(final_feature_map)
        return output, hn
