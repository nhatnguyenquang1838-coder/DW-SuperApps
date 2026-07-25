"""
TTS Vietnamese for OpenClaw - Using Edge TTS (Free)

Install: pip install edge-tts
Usage: python tts-vietnamese.py --text "Hello" --voice "hoai" --output "output.mp3"
"""

import asyncio
import argparse
from pathlib import Path
from edge_tts import Communicate

# Vietnamese voice list
VIETNAMESE_VOICES = {
    "nam": {
        "name": "Nam",
        "voice": "en-US-NamNeural",
        "description": "Warm male voice, suitable for news, reports"
    },
    "hoai": {
        "name": "Hoai",
        "voice": "vi-VN-HoaiMyNeural",
        "description": "Clear female voice, suitable for storytelling, guides"
    },
    "huy": {
        "name": "Huy",
        "voice": "vi-VN-HuyTrinhNeural",
        "description": "Clear male voice, suitable for announcements"
    },
    "lan": {
        "name": "Lan",
        "voice": "vi-VN-LanNeural",
        "description": "Gentle female voice, suitable for poetry, stories"
    },
    "minh": {
        "name": "Minh Kha",
        "voice": "vi-VN-MinhKhaNeural",
        "description": "Deep male voice, suitable for presentations"
    },
    "phuong": {
        "name": "Phuong",
        "voice": "vi-VN-PhuongNeural",
        "description": "Bright female voice, suitable for ads, introductions"
    }
}

DEFAULT_VOICE = "hoai"  # Default: Hoai (female, clear)


async def speak(text: str, voice_name: str, output_file: str):
    """
    Convert Vietnamese text to speech
    
    Args:
        text: Text to read (Vietnamese)
        voice_name: Voice name (nam, hoai, huy, lan, minh, phuong)
        output_file: Output audio file path
    """
    # Check voice
    if voice_name not in VIETNAMESE_VOICES:
        available = ", ".join(VIETNAMESE_VOICES.keys())
        raise ValueError(f"Voice '{voice_name}' not found. Available voices: {available}")
    
    voice_info = VIETNAMESE_VOICES[voice_name]
    print(f"[INFO] Using voice: {voice_info['name']} ({voice_info['description']})")
    
    # Prepare text
    text = str(text).strip()
    if not text:
        raise ValueError("Text cannot be empty!")
    
    # Create Communicate with text and voice
    communicate = Communicate(text=text, voice=voice_info['voice'])
    
    # Save to output file
    await communicate.save(output_file)
    
    # Ensure file is created
    output_path = Path(output_file)
    if not output_path.exists():
        raise RuntimeError(f"Audio file was not created: {output_file}")
    
    print(f"[SUCCESS] Audio file created successfully!")
    print(f"[FILE] {output_path.absolute()}")
    print(f"[SIZE] {output_path.stat().st_size / 1024:.1f} KB")
    
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="TTS Vietnamese for OpenClaw - Using Edge TTS free",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  # Read text with default voice (Hoai)
  python tts-vietnamese.py --text "Xin chao! Day la gioing tieng Viet cua OpenClaw."
  
  # Read with specific voice
  python tts-vietnamese.py --text "Chao mung ban den voi OpenClaw" --voice nam
  
  # Read and save to specific file
  python tts-vietnamese.py --text "Day la mot doan van ban dai de test TTS." --output "test.mp3"

Available Vietnamese voices:
  - nam    : Warm male voice (suitable for news, reports)
  - hoai   : Clear female voice (suitable for storytelling, guides) [Default]
  - huy    : Clear male voice (suitable for announcements)
  - lan    : Gentle female voice (suitable for poetry, stories)
  - minh   : Deep male voice (suitable for presentations)
  - phuong : Bright female voice (suitable for ads, introductions)
        """
    )
    
    parser.add_argument(
        "--text", "-t",
        type=str,
        required=True,
        help="Vietnamese text to read"
    )
    
    parser.add_argument(
        "--voice", "-v",
        type=str,
        default=DEFAULT_VOICE,
        choices=list(VIETNAMESE_VOICES.keys()),
        help=f"Vietnamese voice (default: {DEFAULT_VOICE})"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="output.mp3",
        help="Output audio file path (default: output.mp3)"
    )
    
    args = parser.parse_args()
    
    try:
        asyncio.run(speak(args.text, args.voice, args.output))
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
