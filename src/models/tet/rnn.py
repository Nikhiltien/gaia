import torch
import torch.nn as nn

class RNNBackbone(nn.Module):
    def __init__(self, input_dim, hidden_dim, rnn_layers):
        super(RNNBackbone, self).__init__()
        self.hidden_dim = hidden_dim
        self.rnn_layers = rnn_layers
        self.rnn = nn.GRU(input_dim, hidden_dim, rnn_layers, batch_first=True)
        self.hidden = None

    def forward(self, x):
        batch_size = x.size(0)

        # Check if the hidden state is initialized
        if self.hidden is None or self.hidden.size(1) != batch_size:
            # Adjust the hidden state's batch size or initialize if necessary
            self.hidden = torch.zeros(self.rnn_layers, batch_size, self.hidden_dim, device=x.device)
        else:
            # Detach hidden state to prevent backpropagation through the entire sequence history
            self.hidden = self.hidden.detach()

        out, self.hidden = self.rnn(x, self.hidden)
        return out[:, -1, :]

    def reset_hidden_state(self):
        self.hidden = None
