import torch.nn as nn

from ddqn import DuelingDQN
from rnn import RNNBackbone

class Tet(nn.Module):
    def __init__(self, rnn_input_dim, rnn_hidden_dim, rnn_layers, action_dim, hidden_dim=256):
        super(Tet, self).__init__()
        self.rnn = RNNBackbone(rnn_input_dim, rnn_hidden_dim, rnn_layers)
        self.ddqn = DuelingDQN(rnn_hidden_dim, action_dim, hidden_dim)

    def forward(self, sequence):
        rnn_out = self.rnn(sequence)  # Process sequence data through RNN
        q_values = self.ddqn(rnn_out)  # Use RNN output as DDQN input
        return q_values