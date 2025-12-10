"""Text-to-speech placeholder."""


def synthesize_speech(text: str) -> bytes:
    """Pretend to synthesize speech and return fake audio bytes.

    TODO: replace with real TTS synthesis and streaming.
    """
    return f"[tts-bytes for '{text}']".encode()

