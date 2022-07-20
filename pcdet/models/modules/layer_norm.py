import torch
from torch import nn
from torch.nn import functional


class LayerNorm1d(nn.Module):
    r"""LayerNorm that supports two data formats: channels_last (default) or channels_first.
    The ordering of the dimensions in the inputs. channels_last corresponds to inputs with
    shape (batch_size, height, width, channels) while channels_first corresponds to inputs
    with shape (batch_size, channels, height, width).
    """

    def __init__(self, normalized_shape, eps=1e-6, data_format="channels_last"):
        assert data_format in ("channels_last", "channels_first")
        super().__init__()
        self.weight = nn.Parameter(torch.ones(normalized_shape))
        self.bias = nn.Parameter(torch.zeros(normalized_shape))
        self.eps = eps
        self.data_format = data_format
        self.normalized_shape = (normalized_shape,)

    def forward(self, x: torch.Tensor):
        if self.data_format == "channels_last":
            return functional.layer_norm(x, self.normalized_shape, self.weight, self.bias, self.eps)
        u = torch.mean(x, dim=1, keepdim=True)
        s = torch.pow(x - u, 2).mean(1, keepdim=True)
        x = (x - u) / torch.sqrt(s + self.eps)
        return self.weight[:, None] * x + self.bias[:, None]


class LayerNorm2d(nn.Module):
    r"""LayerNorm that supports two data formats: channels_last (default) or channels_first.
    The ordering of the dimensions in the inputs. channels_last corresponds to inputs with
    shape (batch_size, height, width, channels) while channels_first corresponds to inputs
    with shape (batch_size, channels, height, width).
    """

    def __init__(self, normalized_shape, eps=1e-6, data_format="channels_last"):
        assert data_format in ("channels_last", "channels_first")
        super().__init__()
        self.weight = nn.Parameter(torch.ones(normalized_shape))
        self.bias = nn.Parameter(torch.zeros(normalized_shape))
        self.eps = eps
        self.data_format = data_format
        self.normalized_shape = (normalized_shape,)

    def forward(self, x: torch.Tensor):
        if self.data_format == "channels_last":
            return functional.layer_norm(x, self.normalized_shape, self.weight, self.bias, self.eps)
        u = torch.mean(x, dim=1, keepdim=True)
        s = torch.pow(x - u, 2).mean(1, keepdim=True)
        x = (x - u) / torch.sqrt(s + self.eps)
        return self.weight[:, None, None] * x + self.bias[:, None, None]
