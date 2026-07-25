# Slack Agent

## Mục đích

Agent chuyên xử lý các tác vụ Slack, bao gồm:

- Gửi/nhận tin nhắn
- Đọc và phản hồi tin nhắn
- Quản lý reactions (emoji)
- List channels/members
- Xử lý commands từ Slack

## Cấu hình

### Token (đã cấu hình trong openclaw\.json)

```json
"channels": {
  "slack": {
    "botToken": "xoxb-...",
    "appToken": "xapp-...",
    "enabled": true
  }
}
```

### Channels được enable

Trong `openclaw.json`:

```json
"channels": {
  "slack": {
    "channels": {
      "C01CKGYJHRS": {
        "enabled": true
      }
    }
  }
}
```

## Khả năng

### sendMessage

Gửi tin nhắn đến channel hoặc DM.

**Tham số:**

- `channel`: ID channel (ví dụ: `C01CKGYJHRS`) hoặc username
- `text`: Nội dung tin nhắn
- `thread_ts` (optional): Timestamp của thread để reply

**Ví dụ:**

```python
await slack.sendMessage(
    channel="C01CKGYJHRS",
    text="Xin chào mọi người! Đây là tin nhắn từ Slack Agent."
)
```

### readMessage

Đọc tin nhắn từ Slack.

**Tham số:**

- `channel`: ID channel
- `timestamp` (optional): Timestamp cụ thể của tin nhắn

**Ví dụ:**

```python
message = await slack.readMessage(
    channel="C01CKGYJHRS"
)
print(message.text)
```

### editMessage

Sửa tin nhắn đã gửi.

**Tham số:**

- `channel`: ID channel
- `timestamp`: Timestamp của tin nhắn cần sửa
- `text`: Nội dung mới

**Ví dụ:**

```python
await slack.editMessage(
    channel="C01CKGYJHRS",
    timestamp="1234567890.123456",
    text="Đã được cập nhật!"
)
```

### deleteMessage

Xóa tin nhắn.

**Tham số:**

- `channel`: ID channel
- `timestamp`: Timestamp của tin nhắn cần xóa

**Ví dụ:**

```python
await slack.deleteMessage(
    channel="C01CKGYJHRS",
    timestamp="1234567890.123456"
)
```

### react

Thêm reaction (emoji) cho tin nhắn.

**Tham số:**

- `channel`: ID channel
- `timestamp`: Timestamp của tin nhắn
- `reaction`: Emoji (ví dụ: `:+1:`, `:thumbsup:`)

**Ví dụ:**

```python
await slack.react(
    channel="C01CKGYJHRS",
    timestamp="1234567890.123456",
    reaction=":+1:"
)
```

### listChannels

Liệt kê các channels trong workspace.

**Tham số:**

- `limit` (optional): Số lượng channels trả về

**Ví dụ:**

```python
channels = await slack.listChannels()
for channel in channels:
    print(f"- {channel.name}: {channel.topic}")
```

### listMembers

Liệt kê các thành viên trong workspace.

**Tham số:**

- `limit` (optional): Số lượng members trả về

**Ví dụ:**

```python
members = await slack.listMembers()
for member in members:
    print(f"- {member.name} ({member.id})")
```

## Ví dụ Sử Dụng

### 1. Gửi chào mừng khi có thành viên mới

```python
async def welcome_new_member(user_id, username):
    message = f":wave: Chào mừng {username} gia nhập team! 🎉\n\nHãy giới thiệu bản thân trong channel #general."
    
    await slack.sendMessage(
        channel="C01CKGYJHRS",  # Channel #general
        text=message
    )
```

### 2. Đọc và phản hồi tin nhắn

```python
async def reply_to_message(channel, timestamp, reply_text):
    await slack.sendMessage(
        channel=channel,
        text=f"<!subteam^S>{reply_text}",  # Reply in thread
        thread_ts=timestamp
    )
```

### 3. Tạo daily standup reminder

```python
async def send_standup_reminder():
    message = """:calendar: Nhắc nhở Daily Standup!

Mọi người nhớ cập nhật tiến độ trong channel #standup trước 9h sáng nhé.

#standup format:
- ✅ Hoàn thành: ...
- 🚧 Đang làm: ...
- 📋 Kế hoạch: ..."""
    
    await slack.sendMessage(
        channel="C01CKGYJHRS",
        text=message
    )
```

### 4. Xử lý command từ Slack

```python
@slack.command("standup")
async def standup_command(channel, say):
    """Command để tạo standup template"""
    
    template = """:memo: Standup Template

**Hoàn thành:**
- **Đang làm:**
- **Kế hoạch:**
- **Blockers:**
- """
    
    await say(text=template)
```

## Cấu hình Nâng cao

### Tạo cron job để gửi tin nhắn định kỳ

```python
from datetime import datetime

# Gửi standup reminder mỗi sáng 9h
cron_job = {
    "name": "daily-standup-reminder",
    "schedule": {
        "kind": "cron",
        "expr": "0 9 * * *",  # Mỗi ngày lúc 9h
        "tz": "Asia/Ho_Chi_Minh"
    },
    "payload": {
        "kind": "agentTurn",
        "message": """Gửi daily standup reminder:

:calendar: Nhắc nhở Daily Standup!

Mọi người nhớ cập nhật tiến độ trong channel #standup trước 9h sáng nhé.

#standup format:
- ✅ Hoàn thành: ...
- 🚧 Đang làm: ...
- 📋 Kế hoạch: ..."""
    },
    "sessionTarget": "isolated"
}
```

### Tích hợp với OpenClaw

Thêm vào `AGENTS.md` chính:

```markdown
## Slack Agent

Agent chuyên xử lý các tác vụ Slack.

**Location:** `agents/slack-agent/AGENTS.md`

**Khả năng:**
- sendMessage, readMessage, editMessage, deleteMessage
- react, listChannels, listMembers
- command handling

**Cấu hình:**
- Bot Token: Đã cấu hình trong openclaw.json
- App Token: Đã cấu hình trong openclaw.json
- Channels enabled: C01CKGYJHRS

**Sử dụng:**
Gọi các tools từ `agents/slack-agent/` để tương tác với Slack.
"""
```

## Troubleshooting

### Lỗi: "invalid_auth"

Kiểm tra bot token trong `openclaw.json`:

```json
"channels": {
  "slack": {
    "botToken": "xoxb-..."  // Đảm bảo token đúng
  }
}
```

### Lỗi: "channel_not_found"

Kiểm tra channel ID có tồn tại và đã enable trong cấu hình.

### Lỗi: "permission_denied"

Đảm bảo bot có quyền cần thiết cho các actions.

## Tài Nguyên

- [Slack API Documentation](https://api.slack.com/)
- [Slack Bots Guide](https://api.slack.com/tutorials/build-a-slack-bot)
- [OpenClaw Slack Plugin](https://docs.openclaw.ai/plugins/slack)
