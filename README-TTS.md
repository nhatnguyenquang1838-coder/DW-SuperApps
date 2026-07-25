# Hướng dẫn Sử dụng TTS Tiếng Việt cho OpenClaw

## Cài đặt

### 1. Cài đặt Edge TTS

```powershell
pip install edge-tts
```

### 2. Kiểm tra cài đặt

```powershell
python -c "import edge_tts; print('✅ Edge TTS đã cài đặt')"
```

## Sử dụng

### Cách 1: Command Line

```powershell
# Đọc văn bản với giọng mặc định (Hoài)
python tools\tts-vietnamese.py --text "Xin chào! Đây là giọng tiếng Việt của OpenClaw."

# Đọc với giọng cụ thể
python tools\tts-vietnamese.py --text "Chào mừng bạn đến với OpenClaw" --voice nam

# Đọc và ghi vào file cụ thể
python tools\tts-vietnamese.py --text "Đây là một đoạn văn bản dài để test TTS." --output "test.mp3"
```

### Cách 2: Sử dụng từ Python

```python
from tts_vietnamese import speak, VIETNAMESE_VOICES

# Đọc trực tiếp
async def main():
    await speak("Xin chào!", voice_name="hoai", output_file="greeting.mp3")

import asyncio
asyncio.run(main())
```

### Cách 3: Tích hợp vào OpenClaw

Tạo tool mới trong OpenClaw:

```python
# tools/openclaw-tts.py
import subprocess
from pathlib import Path

def tts_vietnamese(text, voice="hoai", output="output.mp3"):
    """
    Tool TTS cho OpenClaw
    
    Args:
        text (str): Văn bản tiếng Việt
        voice (str): Giọng (nam, hoai, huy, lan, minh, phuong)
        output (str): Đường dẫn file đầu ra
    
    Returns:
        str: Đường dẫn file âm thanh
    """
    cmd = [
        "python", "tools/tts-vietnamese.py",
        "--text", text,
        "--voice", voice,
        "--output", output
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        return Path(output).resolve()
    else:
        raise Exception(f"TTS failed: {result.stderr}")
```

## Các Giọng Tiếng Việt Có Sẵn

| Giọng | Tên | Mô tả | Phù hợp |
|-------|-----|-------|---------|
| `nam` | Nam (Namaste) | Giọng nam ấm áp | Tin tức, báo cáo |
| `hoai` | Hoài (Huaier) | Giọng nữ trong trẻo | Truyện kể, hướng dẫn |
| `huy` | Huy (Hui) | Giọng nam rõ ràng | Thông báo, tin tức |
| `lan` | Lan | Giọng nữ dịu dàng | Thơ ca, truyện |
| `minh` | Minh Kha | Giọng nam trầm ấm | Thuyết trình, giáo dục |
| `phuong` | Phương | Giọng nữ tươi tắn | Quảng cáo, giới thiệu |

## Ví dụ Thực Tế

### 1. Đọc tin tức hàng ngày

```python
async def read_news():
    news = """
    Tin tức hôm nay: Thị trường chứng khoán tăng nhẹ. 
    Giá vàng trong nước ổn định ở mức 98 triệu đồng/lượng.
    Thời tiết Hà Nội nắng nóng, nhiệt độ lên tới 37 độ C.
    """
    await speak(news, voice_name="nam", output_file="news.mp3")
```

### 2. Đọc truyện kể

```python
async def read_story():
    story = """
    Một lần nọ, có một chú mèo tên là Mimi. 
    Mimi rất thích đi dạo trong công viên và gặp nhiều bạn mới.
    """
    await speak(story, voice_name="hoai", output_file="story.mp3")
```

### 3. Đọc hướng dẫn

```python
async def read_guide():
    guide = """
    Hướng dẫn sử dụng OpenClaw:
    Bước 1: Cài đặt Edge TTS
    Bước 2: Chạy script tts-vietnamese.py
    Bước 3: Nghe giọng tiếng Việt chất lượng cao!
    """
    await speak(guide, voice_name="huy", output_file="guide.mp3")
```

## Tích hợp vào OpenClaw

### Tạo Tool TTS trong OpenClaw

1. Tạo file `tools/openclaw-tts.py`:

```python
"""TTS tool cho OpenClaw"""
import subprocess
from pathlib import Path

def tts_vietnamese(text, voice="hoai", output="output.mp3"):
    """
    Chuyển văn bản tiếng Việt thành giọng nói
    
    Args:
        text (str): Văn bản tiếng Việt
        voice (str): Giọng (nam, hoai, huy, lan, minh, phuong)
        output (str): Đường dẫn file đầu ra
    
    Returns:
        str: Đường dẫn file âm thanh
    """
    cmd = [
        "python", "tools/tts-vietnamese.py",
        "--text", text,
        "--voice", voice,
        "--output", output
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        return Path(output).resolve()
    else:
        raise Exception(f"TTS failed: {result.stderr}")
```

2. Thêm vào `AGENTS.md`:

```markdown
## TTS Tool

Sử dụng tool `tts_vietnamese` để chuyển văn bản tiếng Việt thành giọng nói.

Ví dụ:
```python
await tts_vietnamese("Xin chào!", voice="hoai", output="greeting.mp3")
```
"""
```

### Cấu hình trong AGENTS.md

Thêm vào file `AGENTS.md`:

```markdown
## TTS Tiếng Việt

OpenClaw đã được tích hợp TTS tiếng Việt thông qua Edge TTS.

### Sử dụng

Gọi tool `tts_vietnamese` với các tham số:
- `text`: Văn bản tiếng Việt cần đọc
- `voice`: Giọng (nam, hoai, huy, lan, minh, phuong)
- `output`: Đường dẫn file đầu ra

### Ví dụ

```python
# Đọc tin tức
await tts_vietnamese(
    "Thị trường chứng khoán hôm nay tăng nhẹ.",
    voice="nam",
    output="news.mp3"
)

# Đọc truyện
await tts_vietnamese(
    "Một lần nọ, có một chú mèo tên là Mimi...",
    voice="hoai",
    output="story.mp3"
)
```

### Giọng Có Sẵn

- `nam`: Giọng nam ấm áp (tin tức, báo cáo)
- `hoai`: Giọng nữ trong trẻo (truyện kể, hướng dẫn) [Mặc định]
- `huy`: Giọng nam rõ ràng (thông báo)
- `lan`: Giọng nữ dịu dàng (thơ ca, truyện)
- `minh`: Giọng nam trầm ấm (thuyết trình)
- `phuong`: Giọng nữ tươi tắn (quảng cáo)
```

## Lưu Ý

1. **Yêu cầu**: Cần cài đặt `edge-tts` qua pip
2. **Thời gian**: Quá trình chuyển văn bản thành giọng nói có thể mất vài giây
3. **Kích thước file**: File MP3 thường khoảng 1MB cho mỗi phút nói
4. **Chất lượng**: Edge TTS cung cấp chất lượng tốt với nhiều giọng tiếng Việt tự nhiên

## Troubleshooting

### Lỗi: ModuleNotFoundError: No module named 'edge_tts'

```powershell
pip install edge-tts
```

### Lỗi: Giọng không tồn tại

Kiểm tra lại tên giọng trong `VIETNAMESE_VOICES` của script.

### File âm thanh không được tạo

Đảm bảo có quyền ghi vào thư mục chứa file.

## Tài Nguyên

- [Edge TTS Documentation](https://github.com/raymondh/edge-tts)
- [Microsoft Azure Neural Voices - Vietnamese](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support-language-vocal-profiles?tabs=windows#vietnamese)

## Hỗ Trợ

Nếu gặp vấn đề, hãy kiểm tra:
1. Edge TTS đã cài đặt chưa?
2. Giọng có tồn tại không?
3. Có quyền ghi vào thư mục không?
4. Văn bản có chứa ký tự đặc biệt không?
