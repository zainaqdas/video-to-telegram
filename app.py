import os
import requests
import threading
import time
from flask import Flask, render_template, request, flash

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Configuration (Railway uses Environment Variables for security)
PIXELDRAIN_API_KEY = os.environ.get("PIXELDRAIN_API_KEY")
SHRINKME_API_TOKEN = os.environ.get("SHRINKME_API_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def process_video_task(video_url):
    """The background task to download, upload, shorten, and notify."""
    timestamp = int(time.time())
    local_file = f"video_{timestamp}.mp4"
    
    try:
        # 1. Download
        with requests.get(video_url, stream=True) as r:
            r.raise_for_status()
            with open(local_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # 2. Upload to Pixeldrain (PUT method as per instructions)
        filename = os.path.basename(local_file)
        pd_api_url = f"https://pixeldrain.com/api/file/{filename}"
        with open(local_file, 'rb') as f:
            pd_res = requests.put(pd_api_url, auth=("", PIXELDRAIN_API_KEY), data=f)
        
        if pd_res.status_code not in [200, 201]:
            raise Exception(f"Pixeldrain Upload Failed: {pd_res.text}")
        
        file_id = pd_res.json().get("id")
        pd_link = f"https://pixeldrain.com/u/{file_id}"

        # 3. Shorten with ShrinkMe
        sm_url = "https://shrinkme.io/api"
        sm_params = {'api': SHRINKME_API_TOKEN, 'url': pd_link, 'format': 'json'}
        sm_res = requests.get(sm_url, params=sm_params).json()
        
        if sm_res.get("status") != "success":
            raise Exception(f"ShrinkMe Failed: {sm_res.get('message')}")
        
        short_link = sm_res.get("shortenedUrl")

        # 4. Telegram Notification
        tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        msg = f"✅ *Video Ready!*\n\n*Pixeldrain:* {pd_link}\n*Short Link:* {short_link}"
        requests.post(tg_url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

    except Exception as e:
        error_msg = f"❌ *Error Processing Video:*\n{str(e)}"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": error_msg})
    finally:
        if os.path.exists(local_file):
            os.remove(local_file)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        video_url = request.form.get('video_url')
        if video_url:
            # Run the process in a background thread so the webpage doesn't hang
            thread = threading.Thread(target=process_video_task, args=(video_url,))
            thread.start()
            flash("Processing started! You will receive a Telegram message when finished.")
        else:
            flash("Please enter a valid URL.")
    return render_template('index.html')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
