import math
import torch
import torch.nn as nn
import torch.nn.functional as F

from utils.utils_audio import build_Fourier_basis, build_window, build_optimal_window

class BatchSTFT(nn.Module):
    def __init__(self, fft_size, hop_size=None, window_fn='hann', normalize=False):
        super().__init__()
        
        if hop_size is None:
            hop_size = fft_size//2
        
        self.fft_size, self.hop_size = fft_size, hop_size
    
        window = build_window(fft_size, window_fn=window_fn) # (fft_size,)

        cos_basis, sin_basis = build_Fourier_basis(fft_size, normalize=normalize)
        cos_basis, sin_basis = cos_basis[:fft_size//2+1] * window, - sin_basis[:fft_size//2+1] * window
        
        basis = torch.cat([cos_basis, sin_basis], dim=0)
        
        self.basis = nn.Parameter(basis.unsqueeze(dim=1), requires_grad=False)
        
    def forward(self, input):
        """
        Args:
            input (batch_size, T)
        Returns:
            output (batch_size, 2*F_bin, T_bin): F_bin = fft_size//2+1, T_bin = (T - fft_size)//hop_size + 1. T_bin may be different because of padding.
        """
        batch_size, T = input.size()
    
        fft_size, hop_size = self.fft_size, self.hop_size
        
        padding = (hop_size - (T - fft_size)%hop_size)%hop_size + 2 * fft_size # Assume that "fft_size%hop_size is 0"
        padding_left = padding // 2
        padding_right = padding - padding_left
        
        input = F.pad(input, (padding_left, padding_right))
        input = input.unsqueeze(dim=1)
        output = F.conv1d(input, self.basis, stride=self.hop_size)
        
        return output

class BatchInvSTFT(nn.Module):
    def __init__(self, fft_size, hop_size=None, window_fn='hann', normalize=False):
        super().__init__()
        
        if hop_size is None:
            hop_size = fft_size//2
        
        self.fft_size, self.hop_size = fft_size, hop_size

        window = build_window(fft_size, window_fn=window_fn) # (fft_size,)
        optimal_window = build_optimal_window(window, hop_size=hop_size)

        cos_basis, sin_basis = build_Fourier_basis(fft_size, normalize=normalize)
        cos_basis, sin_basis = cos_basis[:fft_size//2+1] * optimal_window, - sin_basis[:fft_size//2+1] * optimal_window
        
        if not normalize:
            cos_basis = cos_basis / fft_size
            sin_basis = sin_basis / fft_size
        
        basis = torch.cat([cos_basis, sin_basis], dim=0)
        
        self.basis = nn.Parameter(basis.unsqueeze(dim=1), requires_grad=False)
        
    def forward(self, input, T=None):
        """
        Args:
            input (batch_size, 2*F_bin, T_bin): F_bin = fft_size//2+1, T_bin = (T - fft_size)//hop_size + 1. T_bin may be different because of padding.
        Returns:
            output (batch_size, T):
        """
        fft_size, hop_size = self.fft_size, self.hop_size
        
        if T is None:
            padding = 2 * fft_size
        else:
            padding = (hop_size - (T - fft_size)%hop_size)%hop_size + 2 * fft_size # Assume that "fft_size%hop_size is 0"
        padding_left = padding // 2
        padding_right = padding - padding_left
        
        input = torch.cat([input, input[:,1:fft_size//2], input[:,-fft_size//2:-1]], axis=1)
        basis = torch.cat([self.basis, self.basis[1:fft_size//2], self.basis[-fft_size//2:-1]], axis=0)
        
        output = F.conv_transpose1d(input, basis, stride=self.hop_size)
        output = F.pad(output, (-padding_left, -padding_right))
        output = output.squeeze(dim=1)
        
        return output

if __name__ == '__main__':
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    torch.manual_seed(111)

    batch_size = 2
    T = 64
    fft_size, hop_size = 8, 2
    window_fn = 'hamming'

    input = torch.randn((batch_size, T), dtype=torch.float)
    
    stft = BatchSTFT(fft_size=fft_size, hop_size=hop_size, window_fn=window_fn)
    istft = BatchInvSTFT(fft_size=fft_size, hop_size=hop_size, window_fn=window_fn)
    spectrogram = stft(input)
    
    plt.figure()
    plt.pcolormesh(spectrogram[0], cmap='bwr')
    plt.colorbar()
    plt.savefig('data/spectrogram.png')
    plt.close()
    
    real = spectrogram[:,:fft_size//2+1,:]
    imag = spectrogram[:,fft_size//2+1:,:]
    power = real**2+imag**2

    plt.figure()
    plt.pcolormesh(power[0], cmap='bwr')
    plt.colorbar()
    plt.savefig('data/power.png')
    plt.close()
    
    output = istft(spectrogram, T=T)
    print(input.size(), output.size())

    plt.figure()
    plt.plot(range(T), input[0].numpy())
    plt.plot(range(T), output[0].numpy())
    plt.savefig('data/Fourier.png')
    plt.close()
