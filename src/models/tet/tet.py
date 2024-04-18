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
    def __init__(self, input_dim=INPUT_DIM, action_dim=ACTION_DIM, lr=0.001, hidden_size=256, num_layers=2):
        super(DDQN, self).__init__()

        self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden_size, num_layers=num_layers, batch_first=True)
        
        # Primary network layers
        self.fc1 = nn.Linear(hidden_size, 128)
        self.fc2 = nn.Linear(128, 64)
        # Separate value and advantage streams for bids and asks
        self.value_stream_bid = nn.Linear(64, 1)
        self.advantage_stream_bid = nn.Linear(64, action_dim)
        self.value_stream_ask = nn.Linear(64, 1)
        self.advantage_stream_ask = nn.Linear(64, action_dim)

        # Target network layers
        self.target_lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden_size, num_layers=num_layers, batch_first=True)
        self.target_fc1 = nn.Linear(hidden_size, 128)
        self.target_fc2 = nn.Linear(128, 64)
        self.target_value_stream_bid = nn.Linear(64, 1)
        self.target_advantage_stream_bid = nn.Linear(64, action_dim)
        self.target_value_stream_ask = nn.Linear(64, 1)
        self.target_advantage_stream_ask = nn.Linear(64, action_dim)

        self.optimizer = optim.Adam(self.parameters(), lr=lr, weight_decay=1e-5)

        # Initialize target network to be the same as the primary network
        self.update_target_network()

    def forward(self, x, model="online"):
        if model == "online":
            x, _ = self.lstm(x)
            x = x[:, -1, :]
            x = F.relu(self.fc1(x))
            x = F.relu(self.fc2(x))
            
            value_bid = self.value_stream_bid(x)
            advantages_bid = self.advantage_stream_bid(x)
            q_values_bid = value_bid + (advantages_bid - advantages_bid.mean(dim=1, keepdim=True))
            
            value_ask = self.value_stream_ask(x)
            advantages_ask = self.advantage_stream_ask(x)
            q_values_ask = value_ask + (advantages_ask - advantages_ask.mean(dim=1, keepdim=True))
        else:
            x, _ = self.target_lstm(x)
            x = x[:, -1, :]
            x = F.relu(self.target_fc1(x))
            x = F.relu(self.target_fc2(x))
            
            value_bid = self.target_value_stream_bid(x)
            advantages_bid = self.target_advantage_stream_bid(x)
            q_values_bid = value_bid + (advantages_bid - advantages_bid.mean(dim=1, keepdim=True))
            
            value_ask = self.target_value_stream_ask(x)
            advantages_ask = self.target_advantage_stream_ask(x)
            q_values_ask = value_ask + (advantages_ask - advantages_ask.mean(dim=1, keepdim=True))

        return q_values_bid, q_values_ask

    def update_target_network(self):
        # Copy parameters from the primary to the target network
        self.target_lstm.load_state_dict(self.lstm.state_dict())
        self.target_fc1.load_state_dict(self.fc1.state_dict())
        self.target_fc2.load_state_dict(self.fc2.state_dict())
        self.target_value_stream_bid.load_state_dict(self.value_stream_bid.state_dict())
        self.target_advantage_stream_bid.load_state_dict(self.advantage_stream_bid.state_dict())
        self.target_value_stream_ask.load_state_dict(self.value_stream_ask.state_dict())
        self.target_advantage_stream_ask.load_state_dict(self.advantage_stream_ask.state_dict())

class Agent:
    def __init__(self, model: DDQN, target_update=10, gamma=0.99, epsilon=0.9, 
                 epsilon_min=0.01, epsilon_decay=0.995, lr=0.001, batch_size=32):
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

        # Gather scores for both bids and asks from primary network
        bid_scores, ask_scores = self.model(states)
        # Gather next scores from target network
        next_bid_scores, next_ask_scores = self.model(next_states, model="target")

        # Compute max Q-values for next states from target network for both actions
        next_bid_q_values = next_bid_scores.max(1)[0].detach()
        next_ask_q_values = next_ask_scores.max(1)[0].detach()

        # Compute expected Q values based on selected actions
        expected_bid_q_values = rewards + self.gamma * next_bid_q_values * (~dones)
        expected_ask_q_values = rewards + self.gamma * next_ask_q_values * (~dones)

        # Actual Q values from the current state using the primary network
        bid_q_values = bid_scores.gather(1, bid_actions).squeeze(-1)
        ask_q_values = ask_scores.gather(1, ask_actions).squeeze(-1)

        # Calculate loss for both bid and ask actions
        loss_bid = self.loss_fn(bid_q_values, expected_bid_q_values)
        loss_ask = self.loss_fn(ask_q_values, expected_ask_q_values)
        loss = loss_bid + loss_ask  # Combine losses if appropriate

        # Backpropagation
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        # Update target network periodically
        if self.update_count % self.target_update == 0:
            self.model.update_target_network()
        self.update_count += 1
