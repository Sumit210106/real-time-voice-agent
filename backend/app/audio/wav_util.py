import io
import wave
import numpy as np

def float32_to_wav_bytes(pcm_array: np.ndarray , sample_rate: int = 16000) -> bytes:
    """
    Converts a NumPy Float32 array (-1.0 to 1.0) to 16-bit PCM WAV bytes.
    """
    
    int16_data = (pcm_array * 32767).astype(np.int16)
    byte_io = io.BytesIO()
    with wave.open(byte_io, 'wb') as wav_file:
        wav_file.setnchannels(1)     
        wav_file.setsampwidth(2)     
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(int16_data.tobytes())
    
    return byte_io.getvalue()


def calculate_duration(pcm_array: np.ndarray, sample_rate: int = 16000) -> float:
    """
    Formula: Total Samples / Sample Rate
    """
    return round(len(pcm_array) / sample_rate, 2)