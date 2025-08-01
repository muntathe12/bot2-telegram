# استخدام صورة Python الرسمية
FROM python:3.11-slim

# تعيين مسار العمل
WORKDIR /app

# نسخ ملف المتطلبات أولاً للاستفادة من التخزين المؤقت للطبقات
COPY requirements.txt .

# تثبيت المكتبات المطلوبة
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات إلى حاوية Docker
COPY . .

# تعيين متغير البيئة للتوكن
ENV BOT_TOKEN="your_bot_token_here"

# تعيين الأمر الافتراضي لتشغيل البوت
CMD ["python", "main.py"]
