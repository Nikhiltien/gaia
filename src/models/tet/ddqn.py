import torch.nn as nn

class DuelingDQN(nn.Module):
    def __init__(self, state_dim, action_dim, hidden_dim=256):
        super(DuelingDQN, self).__init__()
        
        # Common feature layer
        self.feature_layer = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
        )
        
        # Value stream
        self.value_stream = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)  # Single value output
        )
        
        # Advantage stream
        self.advantage_stream = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim)  # One advantage value per action
        )
    
    def forward(self, state):
        features = self.feature_layer(state)
        
        # Compute value and advantages
        value = self.value_stream(features)
        advantages = self.advantage_stream(features)
        
        # Combine using the dueling architecture formula
        q_values = value + (advantages - advantages.mean(dim=1, keepdim=True))
        
        return q_values
