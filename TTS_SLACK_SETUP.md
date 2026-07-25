# Thiết lập TTS Tiếng Việt và Slack Agent cho OpenClaw

## 1. TTS Tiếng Việt

OpenClaw không có cấu hình TTS trực tiếp trong `openclaw.json`. Thay vào đó, bạn cần:

### Cách 1: Sử dụng Edge TTS (Khuyến nghị)

Edge TTS là công cụ miễn phí của Microsoft với nhiều giọng tiếng Việt chất lượng cao.

**Bước 1: Cài đặt Edge TTS**

```powershell
pip install edge-tts
```

**Bước 2: Tạo file script TTS** Tạo file `tts-vietnamese.py` trong thư mục dự án:

```python
import asyncio
from edge_tts import create_generator, Communicate

async def speak(text, output_file="output.mp3"):
    """Chuyển văn bản tiếng Việt thành giọng nói"""
    # Chọn giọng tiếng Việt
    voices = {
        "vietnamese-nam": "en-US-NamNeural",      # Nam (Namaste) - nam, ấm áp
        "vietnamese-hoai": "vi-VN-HoaiMyNeural",  # Hoài (Huaier) - nữ, trong trẻo
        "vietnamese-huy": "vi-VN-HuyTrinhNeural", # Huy (Hui) - nam, rõ ràng
        "vietnamese-lan": "vi-VN-LanNeural",      # Lan - nữ, dịu dàng
        "vietnamese-minh": "vi-VN-MinhKhaNeural"  # Minh Kha - nam, trầm ấm
    }
    
    voice_name = "vietnamese-hoai"  # Mặc định: giọng Hoài
    voice = voices.get(voice_name)
    
    if not voice:
        print(f"Lỗi: Giọng {voice_name} không tồn tại")
        return
    
    # Tạo generator
    communicate = Communicate()
    gen = create_generator(text, voice=voice)
    
    # Ghi âm thanh
    async for audio in gen:
        await communicate.write(audio)
    
    print(f"✅ Đã tạo file âm thanh: {output_file}")

# Ví dụ sử dụng
if __name__ == "__main__":
    text = "Xin chào! Đây là giọng tiếng Việt của OpenClaw."
    asyncio.run(speak(text))
```

**Bước 3: Gọi từ OpenClaw**

Thêm vào `AGENTS.md` hoặc tạo tool mới để gọi TTS:

```python
# tools/tts.py
import subprocess
import json

def tts_vietnamese(text, voice="vietnamese-hoai", output="output.mp3"):
    """
    Chuyển văn bản tiếng Việt thành giọng nói
    
    Args:
        text (str): Văn bản tiếng Việt
        voice (str): Giọng tiếng Việt (nam, hoai, huy, lan, minh)
        output (str): Đường dẫn file đầu ra
    
    Returns:
        str: Đường dẫn file âm thanh
    """
    # Gọi script Edge TTS
    cmd = [
        "python", "tts-vietnamese.py",
        "--text", text,
        "--voice", voice,
        "--output", output
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        return output
    else:
        raise Exception(f"TTS failed: {result.stderr}")
```

### Cách 2: Sử dụng Azure TTS (Nếu có subscription Azure)

Azure TTS cung cấp giọng tiếng Việt chất lượng cao với nhiều tùy chọn.

## 2. Slack Agent

Slack Agent trong OpenClaw được tích hợp sẵn qua plugin `slack`.

### Cấu hình Slack trong openclaw\.json

File cấu hình của bạn đã có sẵn:

```json
"channels": {
  "slack": {
    "enabled": true,
    "botToken": "xoxb-...",
    "appToken": "xapp-...",
    "groupPolicy": "allowlist",
    "channels": {
      "C01CKGYJHRS": {
        "enabled": true
      }
    },
    "capabilities": {
      "interactiveReplies": true
    },
    "allowBots": true,
    "configWrites": true,
    "reactionNotifications": "all",
    "replyToMode": "all"
  }
}
```

### Kích hoạt Slack Agent

Để kích hoạt Slack Agent, bạn cần:

**Bước 1: Đảm bảo Slack plugin đã được enable**

Trong `openclaw.json`, phần `plugins`:

```json
"plugins": {
  "entries": {
    "slack": {
      "enabled": true
    }
  }
}
```

**Bước 2: Tạo Slack Agent (nếu cần)**

Tạo file `agents/slack-agent/AGENTS.md`:

```markdown
# Slack Agent

## Mục đích
Agent chuyên xử lý các tác vụ Slack.

## Khả năng
- Gửi/nhận tin nhắn Slack
- Đọc và phản hồi tin nhắn
- Quản lý reactions (emoji)
- List channels/members
- Xử lý commands từ Slack

## Cấu hình
- Bot Token: Đã cấu hình trong openclaw.json
- App Token: Đã cấu hình trong openclaw.json
- Channels được enable: C01CKGYJHRS

## Sử dụng
Gọi tool `slack.sendMessage`, `slack.readMessage`, v.v.
```

**Bước 3: Khởi động lại Gateway**

```powershell
openclaw gateway restart
```

### Kiểm tra Slack Agent hoạt động

Sau khi khởi động lại, kiểm tra:

```powershell
openclaw status
```

Nếu thấy thông báo về Slack Agent trong logs, nghĩa là đã kích hoạt thành công.

## Tổng kết

✅ **TTS Tiếng Việt**: Sử dụng Edge TTS hoặc Azure TTS (tùy chọn) ✅ **Slack Agent**: Đã có sẵn trong OpenClaw, chỉ cần enable plugin và cấu hình tokens

## Lưu ý

1. **TTS**: OpenClaw không tích hợp TTS mặc định. Bạn cần cài đặt riêng Edge TTS hoặc Azure TTS.
2. **Slack Agent**: Đã được tích hợp sẵn qua plugin `slack`. Chỉ cần đảm bảo:
   - Bot token và App token đã cấu hình đúng
   - Plugin Slack đã enable
   - Gateway đã restart sau khi thay đổi

## Tài liệu tham khảo

- [Edge TTS Documentation](https://github.com/raymondh/edge-tts)
- [Slack API Documentation](https://api.slack.com/)
- [OpenClaw Slack Plugin](https://docs.openclaw.ai/plugins/slack)
