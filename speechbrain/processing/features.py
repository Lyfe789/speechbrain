"""Low-level feature pipeline components

This library gathers functions that compute popular speech  features over
batches of data. All the classes are of type nn.Module. This gives the
possibility to have end-to-end  differentiability and to backpropagate the
gradient through them. Our functions are a modified version the ones
in torch audio toolkit (https://github.com/pytorch/audio).

Example
-------
>>> import torch
>>> import soundfile as sf
>>> signal, fs=sf.read('samples/audio_samples/example1.wav')
>>> signal=torch.tensor(signal).float().unsqueeze(0)
>>> compute_STFT = STFT(
...     sample_rate=fs, win_length=25, hop_length=10, n_fft=400
... )
>>> features = compute_STFT(signal)
>>> features = spectral_magnitude(features)
>>> compute_fbanks = Filterbank(n_mels=40)
>>> features = compute_fbanks(features, init_params=True)
>>> compute_mfccs = DCT(n_out=20)
>>> features = compute_mfccs(features, init_params=True)
>>> compute_deltas = Deltas()
>>> delta1 = compute_deltas(features, init_params=True)
>>> delta2 = compute_deltas(delta1)
>>> features = torch.cat([features, delta1, delta2], dim=2)
>>> compute_cw = ContextWindow(left_frames=5, right_frames=5)
>>> features  = compute_cw(features)
>>> norm = InputNormalization()
>>> features = norm(features, torch.tensor([1]).float())

Author
    Mirco Ravanelli 2020
"""
import math
import torch
import logging
from speechbrain.utils.checkpoints import (
    mark_as_saver,
    mark_as_loader,
    register_checkpoint_hooks,
)

logger = logging.getLogger(__name__)


class STFT(torch.nn.Module):
    """computes the Short-Term Fourier Transform (STFT).

    This class computes the Short-Term Fourier Transform of an audio signal.
    It supports multi-channel audio inputs (batch, time, channels).

    Arguments
    ---------
    sample_rate : int
        Sample rate of the input audio signal (e.g 16000).
    win_length : float
         Length (in ms) of the sliding window used to compute the STFT.
    hop_length : float
        Length (in ms) of the hope of the sliding window used to compute
        the STFT.
    n_fft : int
        Number of fft point of the STFT. It defines the frequency resolution
        (n_fft should be <= than win_len).
    window_type : str
        Window function used to compute the STFT ('bartlett','blackman',
        'hamming', 'hann', default: hamming).
    normalized_stft : bool
        If True, the function returns the  normalized STFT results,
        i.e., multiplied by win_length^-0.5 (default is False).
    center : bool
        If True (default), the input will be padded on both sides so that the
        t-th frame is centered at time t×hop_length. Otherwise, the t-th frame
        begins at time t×hop_length.
    pad_mode : str
        It can be 'constant','reflect','replicate', 'circular', 'reflect'
        (default). 'constant' pads the input tensor boundaries with a
        constant value. 'reflect' pads the input tensor using the reflection
        of the input boundary. 'replicate' pads the input tensor using
        replication of the input boundary. 'circular' pads using  circular
        replication.
    onesided : True
        If True (default) only returns nfft/2 values. Note that the other
        samples are redundant due to the Fourier transform conjugate symmetry.

    Example
    -------
    >>> import torch
    >>> compute_STFT = STFT(
    ...     sample_rate=16000, win_length=25, hop_length=10, n_fft=400
    ... )
    >>> inputs = torch.randn([10, 16000])
    >>> features = compute_STFT(inputs)
    >>> features.shape
    torch.Size([10, 101, 201, 2])
    """

    def __init__(
        self,
        sample_rate,
        win_length=25,
        hop_length=10,
        n_fft=400,
        window_type="hamming",
        normalized_stft=False,
        center=True,
        pad_mode="constant",
        onesided=True,
    ):
        super().__init__()
        self.sample_rate = sample_rate
        self.win_length = win_length
        self.hop_length = hop_length
        self.n_fft = n_fft
        self.window_type = window_type
        self.normalized_stft = normalized_stft
        self.center = center
        self.pad_mode = pad_mode
        self.onesided = onesided

        # Convert win_length and hop_length from ms to samples
        self.win_length = int(
            round((self.sample_rate / 1000.0) * self.win_length)
        )
        self.hop_length = int(
            round((self.sample_rate / 1000.0) * self.hop_length)
        )

        self.window = self._create_window()

    def forward(self, x):
        """Returns the STFT generated from the input waveforms.

        Arguments
        ---------
        x : tensor
            A batch of audio signals to transform.
        """

        # Managing multi-channel stft
        or_shape = x.shape
        if len(or_shape) == 3:
            x = x.transpose(1, 2)
            x = x.reshape(or_shape[0] * or_shape[2], or_shape[1])

        stft = torch.stft(
            x,
            self.n_fft,
            self.hop_length,
            self.win_length,
            self.window.to(x.device),
            self.center,
            self.pad_mode,
            self.normalized_stft,
            self.onesided,
        )

        # Retrieving the original dimensionality (batch,time, channels)
        if len(or_shape) == 3:
            stft = stft.reshape(
                or_shape[0],
                or_shape[2],
                stft.shape[1],
                stft.shape[2],
                stft.shape[3],
            )
            stft = stft.permute(0, 3, 2, 4, 1)
        else:
            # (batch, time, channels)
            stft = stft.transpose(2, 1)

        return stft

    def _create_window(self):
        """Returns the window used for STFT computation.
        """
        if self.window_type == "bartlett":
            wind_cmd = torch.bartlett_window

        if self.window_type == "blackman":
            wind_cmd = torch.blackman_window

        if self.window_type == "hamming":
            wind_cmd = torch.hamming_window

        if self.window_type == "hann":
            wind_cmd = torch.hann_window

        window = wind_cmd(self.win_length)

        return window


class ISTFT(torch.nn.Module):
    """ Computes the Inverse Short-Term Fourier Transform (ISTFT)

    This class computes the Inverse Short-Term Fourier Transform of
    an audio signal. It supports multi-channel audio inputs
    (batch, time_step, n_fft, 2, n_channels [optional]).

    Arguments
    ---------
    sample_rate : int
        Sample rate of the input audio signal (e.g. 16000).
    win_length : float
        Length (in ms) of the sliding window used when computing the STFT.
    hop_length : float
        Length (in ms) of the hope of the sliding window used when computing
        the STFT.
    sig_length : int
        The length of the output signal in number of samples. If not specified
        will be equal to: (time_step - 1) * hop_length + n_fft
    window_type : str
        Window function used to compute the STFT ('bartlett','blackman',
        'hamming', 'hann', default: hamming).
    normalized_stft : bool
        If True, the function assumes that it's working with the normalized
        STFT results. (default is False)
    center : bool
        If True (default), the function assumes that the STFT result was padded
        on both sides.
    onesided : True
        If True (default), the function assumes that there are n_fft/2 values
        for each time frame of the STFT.
    epsilon : float
        A small value to avoid division by 0 when normalizing by the sum of the
        squared window. Playing with it can fix some abnormalities at the
        beginning and at the end of the reconstructed signal. The default value
        of epsilon is 1e-12.

    Example
    -------
    >>> import torch
    >>> compute_STFT = STFT(
    ...     sample_rate=16000, win_length=25, hop_length=10, n_fft=400
    ... )
    >>> compute_ISTFT = ISTFT(
    ...     sample_rate=16000, win_length=25, hop_length=10
    ... )
    >>> inputs = torch.randn([10, 16000])
    >>> outputs = compute_ISTFT(compute_STFT(inputs))
    >>> outputs.shape
    torch.Size([10, 16000])
    """

    def __init__(
        self,
        sample_rate,
        win_length=25,
        hop_length=10,
        sig_length=None,
        window_type="hamming",
        normalized_stft=False,
        center=True,
        onesided=True,
        epsilon=1e-12,
    ):
        super().__init__()
        self.sample_rate = sample_rate
        self.win_length = win_length
        self.hop_length = hop_length
        self.sig_length = sig_length
        self.window_type = window_type
        self.normalized_stft = normalized_stft
        self.center = center
        self.onesided = onesided
        self.epsilon = epsilon

        # Convert win_length and hop_length from ms to samples
        self.win_length = int(
            round((self.sample_rate / 1000.0) * self.win_length)
        )
        self.hop_length = int(
            round((self.sample_rate / 1000.0) * self.hop_length)
        )

        self.window = self._create_window()

    def forward(self, x):
        """ Returns the ISTFT generated from the input signal.

        Arguments
        ---------
        x : tensor
            A batch of audio signals in the frequency domain to transform.
        """

        or_shape = x.shape

        # Changing the format for (batch, time_step, n_channels, n_fft, 2)
        if len(or_shape) == 5:
            x = x.permute(0, 1, 4, 2, 3)

        # Computing the n_fft according to value of self.onesided
        if self.onesided:
            n_fft = 2 * (or_shape[2] - 1)

        else:
            n_fft = or_shape[2]

        # Applying an IFFT on the input frames
        q = torch.irfft(
            x, 1, self.normalized_stft, self.onesided, signal_sizes=[n_fft]
        )

        # Computing the estimated signal length
        estimated_length = (or_shape[1] - 1) * self.hop_length + n_fft

        # Working with the given window
        if self.window.shape[0] < n_fft:
            padding_size = n_fft - self.window.shape[0]
            beginning_pad = padding_size // 2
            ending_pad = padding_size - beginning_pad

            self.window = torch.cat(
                (
                    torch.zeros(beginning_pad),
                    self.window,
                    torch.zeros(ending_pad),
                ),
                -1,
            )

        elif self.window.shape[0] > n_fft:
            crop_size = self.window.shape[0] - n_fft
            crop_point = crop_size // 2
            self.window = self.window[crop_point : (crop_point + n_fft)]

        q = q * self.window

        # Intializing variables for the upcoming normalization
        sum_squared_wn = torch.zeros(estimated_length)
        squared_wn = self.window * self.window

        # Reconstructing the signal from the frames
        if len(or_shape) == 5:
            istft = torch.zeros((or_shape[0], or_shape[4], estimated_length))

        else:
            istft = torch.zeros((or_shape[0], estimated_length))

        for frame_index in range(or_shape[1]):
            time_point = frame_index * self.hop_length

            istft[..., time_point : (time_point + n_fft)] += q[:, frame_index]
            sum_squared_wn[time_point : (time_point + n_fft)] += squared_wn

        # Normalizing the signal by the sum of the squared window
        non_zero_indices = sum_squared_wn > self.epsilon
        istft[..., non_zero_indices] /= sum_squared_wn[non_zero_indices]

        # Cropping the signal to remove the padding if center is True
        if self.center:
            istft = istft[..., (n_fft // 2) : -(n_fft // 2)]
            estimated_length -= n_fft

        # Adjusting the size of the output signal if needed
        if self.sig_length is not None:

            if self.sig_length > estimated_length:

                if len(or_shape) == 5:
                    padding = torch.zeros(
                        (
                            or_shape[0],
                            or_shape[4],
                            self.sig_length - estimated_length,
                        )
                    )

                else:
                    padding = torch.zeros(
                        (or_shape[0], self.sig_length - estimated_length)
                    )

                istft = torch.cat((istft, padding), -1)

            elif self.sig_length < estimated_length:
                istft = istft[..., 0 : self.sig_length]

        if len(or_shape) == 5:
            istft = istft.transpose(1, 2)

        return istft

    def _create_window(self):
        """ Returns the window used for the ISTFT computation.
        """
        if self.window_type == "bartlett":
            wind_cmd = torch.bartlett_window

        if self.window_type == "blackman":
            wind_cmd = torch.blackman_window

        if self.window_type == "hamming":
            wind_cmd = torch.hamming_window

        if self.window_type == "hann":
            wind_cmd = torch.hann_window

        window = wind_cmd(self.win_length)

        return window


def spectral_magnitude(stft, power=1, log=False):
    """Returns the magnitude of a complex spectrogram.

    Arguments
    ---------
    stft : torch.Tensor
        A tensor, output from the stft function.
    power : int
        What power to use in computing the magnitude.
        Use power=1 for the power spectrogram.
        Use power=0.5 for the magnitude spectrogram.
    log : bool
        Whether to apply log to the spectral features.

    Example
    -------

    """
    mag = stft.pow(2).sum(-1).pow(power)
    if log:
        return torch.log(mag)
    return mag


class Filterbank(torch.nn.Module):
    """computes filter bank (FBANK) features given spectral magnitudes.

    Arguments
    ---------
     n_mels : float
         Number of Mel fiters used to average the spectrogram.
     log_mel : bool
         If True, it computes the log of the FBANKs.
     filter_shape : str
         Shape of the filters ('triangular', 'rectangular', 'gaussian').
     f_min : int
         Lowest frequency for the Mel filters.
     f_max : int
         Highest frequency for the Mel filters.
     n_fft : int
         Number of fft points of the STFT. It defines the frequency resolution
         (n_fft should be<= than win_len).
     sample_rate : int
         Sample rate of the input audio signal (e.g, 16000)
     power_spectrogram : float
         Exponent used for spectrogram computation.
     amin : float
         Minimum amplitude (used for numerical stability).
     ref_value : float
         Reference value used for the dB scale.
     top_db : float
         Top dB valu used for log-mels.
     freeze : bool
         if False, it the central frequency and the band of each filter are
         added into nn.parameters. If True, the standard frozen features
         are computed.

    Example
    -------
    >>> import torch
    >>> compute_fbanks = Filterbank()
    >>> inputs = torch.randn([10, 101, 201])
    >>> features = compute_fbanks(inputs, init_params=True)
    >>> features.shape
    torch.Size([10, 101, 40])
    """

    def __init__(
        self,
        n_mels=40,
        log_mel=True,
        filter_shape="triangular",
        f_min=0,
        f_max=8000,
        n_fft=400,
        sample_rate=16000,
        power_spectrogram=2,
        amin=1e-10,
        ref_value=1.0,
        top_db=80.0,
        freeze=True,
    ):
        super().__init__()
        self.n_mels = n_mels
        self.log_mel = log_mel
        self.filter_shape = filter_shape
        self.f_min = f_min
        self.f_max = f_max
        self.n_fft = n_fft
        self.sample_rate = sample_rate
        self.power_spectrogram = power_spectrogram
        self.amin = amin
        self.ref_value = ref_value
        self.top_db = top_db
        self.freeze = freeze
        self.n_stft = self.n_fft // 2 + 1
        self.db_multiplier = math.log10(max(self.amin, self.ref_value))
        self.device_inp = torch.device("cpu")

        if self.power_spectrogram == 2:
            self.multiplier = 10
        else:
            self.multiplier = 20

        # Make sure f_min < f_max
        if self.f_min >= self.f_max:
            err_msg = "Require f_min: %f < f_max: %f" % (
                self.f_min,
                self.f_max,
            )
            logger.error(err_msg, exc_info=True)

        # Filter definition
        mel = torch.linspace(
            self._to_mel(self.f_min), self._to_mel(self.f_max), self.n_mels + 2
        )
        hz = self._to_hz(mel)

        # Computation of the filter bands
        band = hz[1:] - hz[:-1]
        self.band = band[:-1]
        self.f_central = hz[1:-1]

        # Adding the central frequency and the band to the list of nn param
        if not self.freeze:
            self.f_central = torch.nn.Parameter(self.f_central)
            self.band = torch.nn.Parameter(self.band)

        # Frequency axis
        all_freqs = torch.linspace(0, self.sample_rate // 2, self.n_stft)

        # Replicating for all the filters
        self.all_freqs_mat = all_freqs.repeat(self.f_central.shape[0], 1)

    def init_params(self, first_input):
        """
        Arguments
        ---------
        first_input : tensor
            A dummy input of the right shape for initializing parameters.
        """
        self.band = self.band.to(self.device_inp)
        self.f_central = self.f_central.to(self.device_inp)
        self.all_freqs_mat = self.all_freqs_mat.to(self.device_inp)

    def forward(self, spectrogram, init_params=False):
        """Returns the FBANks.

        Arguments
        ---------
        x : tensor
            A batch of spectrogram tensors.
        """
        if init_params:
            self.init_params(spectrogram)

        # Computing central frequency and bandwidth of each filter
        f_central_mat = self.f_central.repeat(
            self.all_freqs_mat.shape[1], 1
        ).transpose(0, 1)
        band_mat = self.band.repeat(self.all_freqs_mat.shape[1], 1).transpose(
            0, 1
        )

        # Creation of the multiplication matrix
        fbank_matrix = self._create_fbank_matrix(f_central_mat, band_mat).to(
            spectrogram.device
        )

        sp_shape = spectrogram.shape

        # Managing multi-channels case (batch, time, channels)
        if len(sp_shape) == 4:
            spectrogram = spectrogram.reshape(
                sp_shape[0] * sp_shape[3], sp_shape[1], sp_shape[2]
            )

        # FBANK computation
        fbanks = torch.matmul(spectrogram, fbank_matrix)
        if self.log_mel:
            fbanks = self._amplitude_to_DB(fbanks)

        # Reshaping in the case of multi-channel inputs
        if len(sp_shape) == 4:
            fb_shape = fbanks.shape
            fbanks = fbanks.reshape(
                sp_shape[0], fb_shape[1], fb_shape[2], sp_shape[3]
            )

        return fbanks

    @staticmethod
    def _to_mel(hz):
        """Returns mel-frequency value corresponding to the input
        frequency value in Hz.

        Arguments
        ---------
        x : float
            The frequency point in Hz.
        """
        return 2595 * math.log10(1 + hz / 700)

    @staticmethod
    def _to_hz(mel):
        """Returns hz-frequency value corresponding to the input
        mel-frequency value.

        Arguments
        ---------
        x : float
            The frequency point in the mel-scale.
        """
        return 700 * (10 ** (mel / 2595) - 1)

    def _triangular_filters(self, all_freqs, f_central, band):
        """Returns fbank matrix using triangular filters.

        Arguments
        ---------
        all_freqs : Tensor
            Tensor gathering all the frequency points.
        f_central : Tensor
            Tensor gathering central frequencies of each filter.
        band : Tensor
            Tensor gathering the bands of each filter.
        """

        # Computing the slops of the filters
        slope = (all_freqs - f_central) / band
        left_side = slope + 1.0
        right_side = -slope + 1.0

        # Adding zeros for negative values
        zero = torch.zeros(1).to(self.device_inp)
        fbank_matrix = torch.max(
            zero, torch.min(left_side, right_side)
        ).transpose(0, 1)

        return fbank_matrix

    def _rectangular_filters(self, all_freqs, f_central, band):
        """Returns fbank matrix using rectangular filters.

        Arguments
        ---------
        all_freqs : Tensor
            Tensor gathering all the frequency points.
        f_central : Tensor
            Tensor gathering central frequencies of each filter.
        band : Tensor
            Tensor gathering the bands of each filter.
        """

        # cut-off frequencies of the filters
        low_hz = f_central - band
        high_hz = f_central + band

        # Left/right parts of the filter
        left_side = right_size = all_freqs.ge(low_hz)
        right_size = all_freqs.le(high_hz)

        fbank_matrix = (left_side * right_size).float().transpose(0, 1)

        return fbank_matrix

    def _gaussian_filters(
        self, all_freqs, f_central, band, smooth_factor=torch.tensor(2)
    ):
        """Returns fbank matrix using gaussian filters.

        Arguments
        ---------
        all_freqs : Tensor
            Tensor gathering all the frequency points.
        f_central : Tensor
            Tensor gathering central frequencies of each filter.
        band : Tensor
            Tensor gathering the bands of each filter.
        smooth_factor: Tensor
            Smoothing factor of the gaussian filter. It can be used to employ
            sharper or flatter filters.
        """
        fbank_matrix = torch.exp(
            -0.5 * ((all_freqs - f_central) / (band / smooth_factor)) ** 2
        ).transpose(0, 1)

        return fbank_matrix

    def _create_fbank_matrix(self, f_central_mat, band_mat):
        """Returns fbank matrix to use for averaging the spectrum with
           the set of filter-banks.

        Arguments
        ---------
        f_central : Tensor
            Tensor gathering central frequencies of each filter.
        band : Tensor
            Tensor gathering the bands of each filter.
        smooth_factor: Tensor
            Smoothing factor of the gaussian filter. It can be used to employ
            sharper or flatter filters.
        """
        if self.filter_shape == "triangular":
            fbank_matrix = self._triangular_filters(
                self.all_freqs_mat, f_central_mat, band_mat
            )

        elif self.filter_shape == "rectangular":
            fbank_matrix = self._rectangular_filters(
                self.all_freqs_mat, f_central_mat, band_mat
            )

        else:
            fbank_matrix = self._gaussian_filters(
                self.all_freqs_mat, f_central_mat, band_mat
            )

        return fbank_matrix

    def _amplitude_to_DB(self, x):
        """Converts  linear-FBANKs to log-FBANKs.

        Arguments
        ---------
        x : Tensor
            A batch of linear FBANK tensors.

        """
        x_db = self.multiplier * torch.log10(torch.clamp(x, min=self.amin))
        x_db -= self.multiplier * self.db_multiplier

        # Setting up dB max
        new_x_db_max = torch.tensor(
            float(x_db.max()) - self.top_db, dtype=x_db.dtype, device=x.device,
        )
        # Clipping to dB max
        x_db = torch.max(x_db, new_x_db_max)

        return x_db


class DCT(torch.nn.Module):
    """Computes the discrete cosine transform.

    This class is primarily used to compute MFCC features of an audio signal
    given a set of FBANK features as input.

    Arguments
    ---------
    n_out : int
        Number of output coefficients.
    ortho_norm : bool
        Whether to use orthogonal norm.

    Example
    -------
    >>> import torch
    >>> compute_mfccs = DCT()
    >>> inputs = torch.randn([10, 101, 40])
    >>> features = compute_mfccs(inputs, init_params=True)
    >>> features.shape
    torch.Size([10, 101, 20])
    """

    def __init__(
        self, n_out=20, ortho_norm=True,
    ):
        super().__init__()
        self.n_out = n_out
        self.ortho_norm = ortho_norm

    def init_params(self, first_input):
        """
        Arguments
        ---------
        first_input : tensor
            A dummy input of the right shape for initializing parameters.
        """
        self.n_in = first_input.size(-1)

        if self.n_out > self.n_in:
            err_msg = (
                "Cannot select more DCT coefficients than inputs "
                "(n_out=%i, n_in=%i)" % (self.n_out, self.n_in)
            )
            raise ValueError(err_msg)

        # Generate matix for DCT transformation
        self.dct_mat = self._create_dct(first_input.device)

    def _create_dct(self, device):
        """Compute the matrix for the DCT transformation.

        Arguments
        ---------
        device : str
            A torch device to use for storing the dct matrix.
        """
        n = torch.arange(float(self.n_in), device=device)
        k = torch.arange(float(self.n_out), device=device).unsqueeze(1)
        dct = torch.cos(math.pi / float(self.n_in) * (n + 0.5) * k)

        if self.ortho_norm:
            dct[0] *= 1.0 / math.sqrt(2.0)
            dct *= math.sqrt(2.0 / float(self.n_in))
        else:
            dct *= 2.0

        return dct.t()

    def forward(self, x, init_params=False):
        """Returns the DCT of the input tensor.

        Arguments
        ---------
        x : tensor
            A batch of tensors to transform, usually fbank features.
        """
        if init_params:
            self.init_params(x)

        # Managing multi-channels case
        input_shape = x.shape
        if len(input_shape) == 4:
            x = x.reshape(x.shape[0] * x.shape[3], x.shape[1], x.shape[2])

        # apply the DCT transform
        dct = torch.matmul(x, self.dct_mat)

        # Reshape in the case of multi-channels
        if len(input_shape) == 4:
            dct = dct.reshape(
                input_shape[0], dct.shape[1], dct.shape[2], input_shape[3]
            )

        return dct


class Deltas(torch.nn.Module):
    """Computes delta coefficients (time derivatives).

    Arguments
    ---------
    win_length : int
        Length of the window used to compute the time derivatives.

    Example
    -------
    >>> import torch
    >>> compute_deltas = Deltas()
    >>> inputs = torch.randn([10, 101, 20])
    >>> features = compute_deltas(inputs, init_params=True)
    >>> features.shape
    torch.Size([10, 101, 20])
    """

    def __init__(
        self, window_length=5,
    ):
        super().__init__()
        self.n = (window_length - 1) // 2
        self.denom = self.n * (self.n + 1) * (2 * self.n + 1) / 3

    def init_params(self, first_input):
        """
        Arguments
        ---------
        first_input : tensor
            A dummy input of the right shape for initializing parameters.
        """
        self.device = first_input.device
        self.kernel = torch.arange(
            -self.n, self.n + 1, device=self.device, dtype=torch.float32,
        ).repeat(first_input.shape[2], 1, 1)

    def forward(self, x, init_params=False):
        """Returns the delta coefficients.

        Arguments
        ---------
        x : tensor
            A batch of tensors.
        """
        if init_params:
            self.init_params(x)

        # Managing multi-channel deltas reshape tensor (batch*channel,time)
        x = x.transpose(1, 2).transpose(2, -1)
        or_shape = x.shape
        if len(or_shape) == 4:
            x = x.reshape(or_shape[0] * or_shape[2], or_shape[1], or_shape[3])

        # Padding for time borders
        x = torch.nn.functional.pad(x, (self.n, self.n), mode="replicate")

        # Derivative estimation (with a fixed convolutional kernel)
        delta_coeff = (
            torch.nn.functional.conv1d(x, self.kernel, groups=x.shape[1])
            / self.denom
        )

        # Retrieving the original dimensionality (for multi-channel case)
        if len(or_shape) == 4:
            delta_coeff = delta_coeff.reshape(
                or_shape[0], or_shape[1], or_shape[2], or_shape[3],
            )
        delta_coeff = delta_coeff.transpose(1, -1).transpose(2, -1)

        return delta_coeff


class ContextWindow(torch.nn.Module):
    """Computes the context window.

    This class applies a context window by gathering multiple time steps
    in a single feature vector. The operation is performed with a
    convolutional layer based on a fixed kernel designed for that.

    Arguments
    ---------
    left_frames : int
         Number of left frames (i.e, past frames) to collect.
    right_frames : int
        Number of right frames (i.e, future frames) to collect.

    Example
    -------
    >>> import torch
    >>> compute_cw = ContextWindow(left_frames=5, right_frames=5)
    >>> inputs = torch.randn([10, 101, 20])
    >>> features = compute_cw(inputs)
    >>> features.shape
    torch.Size([10, 101, 220])
    """

    def __init__(
        self, left_frames=0, right_frames=0,
    ):
        super().__init__()
        self.left_frames = left_frames
        self.right_frames = right_frames
        self.context_len = self.left_frames + self.right_frames + 1
        self.kernel_len = 2 * max(self.left_frames, self.right_frames) + 1

        # Kernel definition
        self.kernel = torch.eye(self.context_len, self.kernel_len)

        if self.right_frames > self.left_frames:
            lag = self.right_frames - self.left_frames
            self.kernel = torch.roll(self.kernel, lag, 1)

        self.first_call = True

    def forward(self, x):
        """Returns the tensor with the sourrounding context.

        Arguments
        ---------
        x : tensor
            A batch of tensors.
        """

        x = x.transpose(1, 2)

        if self.first_call is True:
            self.first_call = False
            self.kernel = (
                self.kernel.repeat(x.shape[1], 1, 1)
                .view(x.shape[1] * self.context_len, self.kernel_len,)
                .unsqueeze(1)
            )

        # Managing multi-channel case
        or_shape = x.shape
        if len(or_shape) == 4:
            x = x.reshape(or_shape[0] * or_shape[2], or_shape[1], or_shape[3])

        # Compute context (using the estimated convolutional kernel)
        cw_x = torch.nn.functional.conv1d(
            x,
            self.kernel.to(x.device),
            groups=x.shape[1],
            padding=max(self.left_frames, self.right_frames),
        )

        # Retrieving the original dimensionality (for multi-channel case)
        if len(or_shape) == 4:
            cw_x = cw_x.reshape(
                or_shape[0], cw_x.shape[1], or_shape[2], cw_x.shape[-1]
            )

        cw_x = cw_x.transpose(1, 2)

        return cw_x


@register_checkpoint_hooks
class InputNormalization(torch.nn.Module):
    """Performs mean and variance normalization of the input tensor.
        mean_norm=True,
        std_norm=True,
        norm_type="global",
        avg_factor=None,
        requires_grad=False,

    Arguments
    ---------
    mean_norm : True
         If True, the mean will be normalized.
    std_norm : True
         If True, the standard deviation will be normalized.
    norm_type : str
         It defines how the statistics are computed ('sentence' computes them
         at sentence level, 'batch' at batch level, 'speaker' at speaker
         level, while global computes a single normalization vector for all
         the sentences in the dataset). Speaker and global statistics are
         computed with a moving average approach.
    avg_factor : float
         It can be used to manually set the weighting factor between
         current statistics and accumulated ones.

    Example
    -------
    >>> import torch
    >>> norm = InputNormalization()
    >>> inputs = torch.randn([10, 101, 20])
    >>> inp_len = torch.ones([10])
    >>> features = norm(inputs, inp_len)
    """

    from typing import Dict

    spk_dict_mean: Dict[int, torch.Tensor]
    spk_dict_std: Dict[int, torch.Tensor]
    spk_dict_count: Dict[int, int]

    def __init__(
        self,
        mean_norm=True,
        std_norm=True,
        norm_type="global",
        avg_factor=None,
        requires_grad=False,
    ):
        super().__init__()
        self.mean_norm = mean_norm
        self.std_norm = std_norm
        self.norm_type = norm_type
        self.avg_factor = avg_factor
        self.requires_grad = requires_grad
        self.glob_mean = torch.tensor([0])
        self.glob_std = torch.tensor([0])
        self.spk_dict_mean = {}
        self.spk_dict_std = {}
        self.spk_dict_count = {}
        self.weight = 1.0
        self.count = 0
        self.eps = 1e-10
        self.device_inp = torch.device("cpu")

    def forward(self, x, lengths, spk_ids=torch.tensor([])):
        """Returns the tensor with the sourrounding context.

        Arguments
        ---------
        x : tensor
            A batch of tensors.
        lengths : tensor
            A batch of tensors containing the relative length of each
            sentence (e.g, [0.7, 0.9, 1.0]). It is used to avoid
            computing stats on zero-padded steps.
        spk_ids : tensor containing the ids of each speaker (e.g, [0 10 6]).
            It is used to perform per-speaker normalization when
            norm_type='speaker'.
        """
        self.device_inp = x.device
        N_batches = x.shape[0]

        current_means = []
        current_stds = []

        for snt_id in range(N_batches):

            # Avoiding padded time steps
            actual_size = int(torch.round(lengths[snt_id] * x.shape[1]))

            # computing statistics
            current_mean, current_std = self._compute_current_stats(
                x[snt_id, 0:actual_size, ...]
            )

            current_means.append(current_mean)
            current_stds.append(current_std)

            if self.norm_type == "sentence":

                x[snt_id] = (x[snt_id] - current_mean.data) / current_std.data

            if self.norm_type == "speaker":

                spk_id = int(spk_ids[snt_id][0])

                if spk_id not in self.spk_dict_mean:

                    # Initialization of the dictionary
                    self.spk_dict_mean[spk_id] = current_mean
                    self.spk_dict_std[spk_id] = current_std
                    self.spk_dict_count[spk_id] = 1

                else:
                    self.spk_dict_count[spk_id] = (
                        self.spk_dict_count[spk_id] + 1
                    )

                    if self.avg_factor is None:
                        self.weight = 1 / self.spk_dict_count[spk_id]
                    else:
                        self.weight = self.avg_factor

                    self.spk_dict_mean[spk_id] = (
                        1 - self.weight
                    ) * self.spk_dict_mean[spk_id] + self.weight * current_mean
                    self.spk_dict_std[spk_id] = (
                        1 - self.weight
                    ) * self.spk_dict_std[spk_id] + self.weight * current_std

                    self.spk_dict_mean[spk_id].detach()
                    self.spk_dict_std[spk_id].detach()

                x[snt_id] = (
                    x[snt_id] - self.spk_dict_mean[spk_id].data
                ) / self.spk_dict_std[spk_id].data

        if self.norm_type == "batch" or self.norm_type == "global":
            current_mean = torch.mean(torch.stack(current_means), dim=0)
            current_std = torch.mean(torch.stack(current_stds), dim=0)

            if self.norm_type == "batch":
                x = (x - current_mean.data) / (current_std.data)

            if self.norm_type == "global":

                if self.count == 0:
                    self.glob_mean = current_mean
                    self.glob_std = current_std

                else:
                    if self.avg_factor is None:
                        self.weight = 1 / (self.count + 1)
                    else:
                        self.weight = self.avg_factor

                    self.glob_mean = (
                        1 - self.weight
                    ) * self.glob_mean + self.weight * current_mean

                    self.glob_std = (
                        1 - self.weight
                    ) * self.glob_std + self.weight * current_std

                self.glob_mean.detach()
                self.glob_std.detach()

                x = (x - self.glob_mean.data) / (self.glob_std.data)

        self.count = self.count + 1

        return x

    def _compute_current_stats(self, x):
        """Returns the tensor with the sourrounding context.

        Arguments
        ---------
        x : tensor
            A batch of tensors.
        """
        # Compute current mean
        if self.mean_norm:
            current_mean = torch.mean(x, dim=0).detach().data
        else:
            current_mean = torch.tensor([0.0]).to(x.device)

        # Compute current std
        if self.std_norm:
            current_std = torch.std(x, dim=0).detach().data
        else:
            current_std = torch.tensor([1.0]).to(x.device)

        # Improving numerical stability of std
        current_std = torch.max(
            current_std, self.eps * torch.ones_like(current_std)
        )

        return current_mean, current_std

    def _statistics_dict(self):
        """Fills the dictionary containing the normalization statistics.
        """
        state = {}
        state["count"] = self.count
        state["glob_mean"] = self.glob_mean
        state["glob_std"] = self.glob_std
        state["spk_dict_mean"] = self.spk_dict_mean
        state["spk_dict_std"] = self.spk_dict_std
        state["spk_dict_count"] = self.spk_dict_count

        return state

    def _load_statistics_dict(self, state):
        """Loads the dictionary containing the statistics.

        Arguments
        ---------
        state : dict
            A dictionary containing the normalization statistics.
        """
        self.count = state["count"]
        if isinstance(state["glob_mean"], int):
            self.glob_mean = state["glob_mean"]
            self.glob_std = state["glob_std"]
        else:
            self.glob_mean = state["glob_mean"]  # .to(self.device_inp)
            self.glob_std = state["glob_std"]  # .to(self.device_inp)

        # Loading the spk_dict_mean in the right device
        self.spk_dict_mean = {}
        for spk in state["spk_dict_mean"]:
            self.spk_dict_mean[spk] = state["spk_dict_mean"][spk].to(
                self.device_inp
            )

        # Loading the spk_dict_std in the right device
        self.spk_dict_std = {}
        for spk in state["spk_dict_std"]:
            self.spk_dict_std[spk] = state["spk_dict_std"][spk].to(
                self.device_inp
            )

        self.spk_dict_count = state["spk_dict_count"]

        return state

    @mark_as_saver
    def _save(self, path):
        """Save statistic dictionary.

        Arguments
        ---------
        path : str
            A path where to save the dictionary.
        """
        stats = self._statistics_dict()
        torch.save(stats, path)

    @mark_as_loader
    def _load(self, path, end_of_epoch):
        """Load statistic dictionary.

        Arguments
        ---------
        path : str
            The path of the statistic dictionary
        end_of_epoch: bool
            If True, the training has completed a full epoch.
        """
        del end_of_epoch  # Unused here.
        stats = torch.load(path)
        self._load_statistics_dict(stats)
