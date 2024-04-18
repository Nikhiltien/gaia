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

QTY_INCREMENT = 2 # as a %
ACTION_DIM = MAX_DEPTH * (100 // QTY_INCREMENT)


class DDQN(nn.Module):
    def __init__(self, input_dim=INPUT_DIM, action_dim=ACTION_DIM, lr=0.001, hidden_size=128, num_layers=2, 
                 num_heads=8, dim_feedforward=256):
        super(DDQN, self).__init__()

        # self.features_model = GRUTransformerModel(input_size, hidden_size, num_layers, num_heads, dim_feedforward, output_size)
        
        # Define the primary network layers
        self.fc1 = nn.Linear(input_dim, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc3a = nn.Linear(64, action_dim)  # Output for asks
        self.fc3b = nn.Linear(64, action_dim)  # Output for bids

        # Define the target network layers
        self.target_fc1 = nn.Linear(input_dim, 128)
        self.target_fc2 = nn.Linear(128, 64)
        self.target_fc3a = nn.Linear(64, action_dim)
        self.target_fc3b = nn.Linear(64, action_dim)

        # Initialize target network to be the same as the primary network
        self.update_target_network()

        self.optimizer = optim.Adam(self.parameters(), lr, weight_decay=1e-5)  # Added L2 regularization
    
    def forward(self, x, model="online"):
        x = x.mean(dim=1)
        if model == "online":
            x = F.relu(self.fc1(x))
            x = F.relu(self.fc2(x))
            bid_scores = self.fc3a(x)
            ask_scores = self.fc3b(x)
        else:  # using the target network
            x = F.relu(self.target_fc1(x))
            x = F.relu(self.target_fc2(x))
            bid_scores = self.target_fc3a(x)
            ask_scores = self.target_fc3b(x)
        return bid_scores, ask_scores

    def update_target_network(self):
        # Explicitly copy the parameters from the primary network to the target network
        self.target_fc1.load_state_dict(self.fc1.state_dict())
        self.target_fc2.load_state_dict(self.fc2.state_dict())
        self.target_fc3a.load_state_dict(self.fc3a.state_dict())
        self.target_fc3b.load_state_dict(self.fc3b.state_dict())

class Agent:
    def __init__(self, model: DDQN, target_update=10, gamma=0.99, epsilon=0.9, 
                 epsilon_min=0.01, epsilon_decay=0.995, lr=0.001, batch_size=1):
        self.model = model
        self.target_update = target_update
        self.update_count = 0

        self.gamma = gamma
        self.epsilon = epsilon  # Starting epsilon
        self.epsilon_min = epsilon_min  # Minimum epsilon
        self.epsilon_decay = epsilon_decay  # Epsilon decay rate
        self.batch_size = batch_size
        self.memory = deque(maxlen=10000)
        self.optimizer = optim.Adam(self.model.parameters(), lr=lr)
        self.loss_fn = nn.MSELoss()

    def select_action(self, state):
        self.epsilon = max(self.epsilon * self.epsilon_decay, self.epsilon_min)
        
        if random.random() > self.epsilon:
            state_tensor = torch.tensor(state, dtype=torch.float32).unsqueeze(0)
            bid_scores, ask_scores = self.model(state_tensor)
            bid_action = bid_scores.argmax(1).item()
            ask_action = ask_scores.argmax(1).item()
        else:
            bid_action = np.random.randint(0, 500)
            ask_action = np.random.randint(0, 500)
        return bid_action, ask_action

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    def replay(self):
        if len(self.memory) < self.batch_size:
            return
        batch = random.sample(self.memory, self.batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)

        states = torch.tensor(np.array(states), dtype=torch.float32)
        next_states = torch.tensor(np.array(next_states), dtype=torch.float32)
        rewards = torch.tensor(rewards, dtype=torch.float32)
        dones = torch.tensor(dones, dtype=torch.bool)

        bid_actions, ask_actions = zip(*actions)
        bid_actions = torch.tensor(bid_actions, dtype=torch.long).unsqueeze(-1)
        ask_actions = torch.tensor(ask_actions, dtype=torch.long).unsqueeze(-1)

        # Action selection from the primary network
        _, ask_scores = self.model(states)  # Only need ask_scores for selecting actions
        # Action evaluation from the target network
        next_bid_scores, _ = self.model(next_states, model="target")  # Only need bid_scores for evaluating the action

        # Gather the maximum Q value for the next state from the target network
        next_ask_q_values = next_bid_scores.max(1)[0].detach()

        # Compute expected Q values based on selected actions from the target network
        expected_ask_q_values = rewards + self.gamma * next_ask_q_values * (~dones)

        # Actual Q values from the current state using the primary network
        ask_q_values = ask_scores.gather(1, ask_actions).squeeze(-1)

        # Calculate loss
        loss = self.loss_fn(ask_q_values, expected_ask_q_values)

        # Backpropagation
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        # Periodically update the target network weights
        if self.update_count % self.target_update == 0:
            self.model.update_target_network()
        self.update_count += 1


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
