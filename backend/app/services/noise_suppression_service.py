import torch
import torchaudio
import os
from typing import Dict, Any

class NoiseSuppressionService:
    """
    Service to perform background noise suppression using a pre-trained ConvTasNet model.
    """
    
    def __init__(self):
        """
        Initializes the pre-trained ConvTasNet model from Torchaudio pipelines.
        """
        try:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            
            # Use the pre-trained ConvTasNet model trained on Libri2Mix speech separation
            from torchaudio.pipelines import CONVTASNET_BASE_LIBRI2MIX 
            self.bundle = CONVTASNET_BASE_LIBRI2MIX
            self.model = self.bundle.get_model()
            self.model.to(self.device)
            self.model.eval()
            
            print(f"NoiseSuppressionService initialized successfully on {self.device}")
            
        except Exception as e:
            print(f"Error initializing NoiseSuppressionService: {str(e)}")
            self.model = None
    
    def process_audio(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """
        Processes an audio file to separate speech from background noise.
        
        Args:
            input_path: Path to the noisy audio file.
            output_path: Path to save the processed clean audio file.
            
        Returns:
            Dict[str, Any]: Analysis results including success status and metrics.
        """
        if self.model is None:
            return {
                "success": False,
                "error": "Model not initialized properly",
                "clean_audio_url": ""
            }
        
        try:
            import librosa
            import soundfile as sf
            
            # 1. Load audio using librosa (very robust on Windows for WebM, MP3, WAV, etc.)
            # It automatically converts to mono and resamples to the model's sample rate (16kHz)
            y, sr = librosa.load(input_path, sr=self.bundle.sample_rate, mono=True)
            
            if len(y) == 0:
                raise ValueError("Loaded audio file is empty")
            
            # 2. Convert the numpy array to a PyTorch tensor
            # ConvTasNet expects shape: [batch, channels, time]
            waveform = torch.from_numpy(y).unsqueeze(0).to(self.device)
            
            # 3. Perform speech separation
            with torch.no_grad():
                separated = self.model(waveform.unsqueeze(0)) # Output shape: [1, num_sources, time]
                
                # Extract the clean speech source (Source 0) and send to CPU
                clean_waveform = separated[0][0].cpu().numpy()
            
            # 4. Save processed clean audio using soundfile (safest writer)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            sf.write(output_path, clean_waveform, self.bundle.sample_rate)
            
            return {
                "success": True,
                "error": None,
                "clean_audio_url": output_path
            }
            
        except Exception as e:
            print(f"Error processing audio: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "clean_audio_url": ""
            }
