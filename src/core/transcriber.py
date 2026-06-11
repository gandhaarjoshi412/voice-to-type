import os
from groq import Groq, APIError

class Transcriber:
    def __init__(self, api_key: str = None):
        """
        Initializes the Groq Transcriber.
        
        Args:
            api_key (str, optional): Groq API key. If None, it will look for GROQ_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Groq API key must be provided or set as GROQ_API_KEY environment variable.")
        
        self.client = Groq(api_key=self.api_key)
        self.model = "whisper-large-v3-turbo"

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribes an audio file using Groq's Whisper model.
        
        Args:
            audio_path (str): Path to the audio file.
            
        Returns:
            str: The transcribed text.
            
        Raises:
            FileNotFoundError: If the audio file does not exist.
            APIError: If the Groq API returns an error.
            Exception: For other unexpected errors.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            with open(audio_path, "rb") as file:
                transcription = self.client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), file.read()),
                    model=self.model,
                    response_format="text"
                )
            return transcription
        except APIError as e:
            # Re-raise APIError to be handled by the caller
            raise e
        except Exception as e:
            # Wrap other exceptions if necessary or just let them propagate
            raise Exception(f"An unexpected error occurred during transcription: {str(e)}")
