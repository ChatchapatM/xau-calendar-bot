# XAU Calendar Bot — วิธี Deploy บน Railway

## ขั้นตอน

### 1. สมัคร Railway (ฟรี)
- ไปที่ https://railway.app
- กด "Start a New Project" → Login ด้วย GitHub

### 2. สร้าง GitHub Repository
- ไปที่ https://github.com/new
- ตั้งชื่อ: xau-calendar-bot
- กด "Create repository"
- Upload ไฟล์ bot.py และ requirements.txt

### 3. Deploy บน Railway
- ใน Railway → "New Project" → "Deploy from GitHub repo"
- เลือก xau-calendar-bot
- Railway จะ install และรันอัตโนมัติ

### 4. ตรวจสอบ
- ดู Logs ใน Railway ว่ามีข้อความ "พร้อมใช้งานแล้วครับ!"
- กลับไป Discord พิมพ์ /calendar

## คำสั่งที่ใช้ได้
- /calendar — ดูข่าววันนี้ทั้งหมด
- /calendar high — ดูเฉพาะ High Impact
- /next — ข่าวถัดไปที่กำลังจะมา
- /analyze — AI วิเคราะห์ผลกระทบต่อ XAUUSD

## Channel อัตโนมัติ
Bot จะสร้าง channel "trading-alerts" อัตโนมัติ
และแจ้งเตือนก่อนข่าว High Impact 30 นาที
