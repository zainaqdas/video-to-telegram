import os
import requests
import threading
import time
import urllib.parse
from flask import Flask, render_template, request, flash

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Configuration (Add these in Railway "Variables" tab)
PIXELDRAIN_API_KEY = os.environ.get("PIXELDRAIN_API_KEY")
SHRINKME_API_TOKEN = os.environ.get("SHRINKME_API_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def process_video_task(video_url):
    """The background task: Download -> Pixeldrain -> ShrinkMe -> Telegram."""
    
    # 1. Determine a filename from the URL or timestamp
    parsed_url = urllib.parse.urlparse(video_url)
    original_filename = os.path.basename(parsed_url.path)
    if not original_filename.endswith(".mp4"):
        original_filename = f"video_{int(time.time())}.mp4"
    
    local_file = original_filename
    
    try:
        # Step A: Download the video
        with requests.get(video_url, stream=True) as r:
            r.raise_for_status()
            with open(local_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # Step B: Upload to Pixeldrain (PUT method as per Documentation)
        pd_api_url = f"https://pixeldrain.com/api/file/{local_file}"
        with open(local_file, 'rb') as f:
            pd_res = requests.put(
                pd_api_url, 
                auth=("", PIXELDRAIN_API_KEY), 
                data=f
            )
        
        if pd_res.status_code not in [200, 201]:
            raise Exception(f"Pixeldrain Error: {pd_res.text}")
        
        file_id = pd_res.json().get("id")
        pd_link = f"https://pixeldrain.com/u/{file_id}"

        # Step C: Shorten the Pixeldrain link with ShrinkMe
        sm_url = "https://shrinkme.io/api"
        sm_params = {
            'api': SHRINKME_API_TOKEN, 
            'url': pd_link, 
            'format': 'json'
        }
        sm_res = requests.get(sm_url, params=sm_params).json()
        
        if sm_res.get("status") != "success":
            raise Exception(f"ShrinkMe Error: {sm_res.get('message')}")
        
        short_link = sm_res.get("shortenedUrl")

        # Step D: Telegram Notification (Removed Pixeldrain Link)
        tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        # We only send the Short Link and the Filename
        msg = (
            f"✅ *Upload Complete*\n\n"
            f"*File:* `{local_file}`\n"
            f"*Short Link:* {short_link}"
        )
        
        requests.post(tg_url, json={
            "chat_id": TELEGRAM_CHAT_ID, 
            "text": msg, 
            "parse_mode": "Markdown"
        })

    except Exception as e:
        # Notify about errors via Telegram
        error_msg = f"❌ *Process Failed:*\n`{str(e)}`"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": error_msg, "parse_mode": "Markdown"})
    finally:
        # Always cleanup the server disk space
        if os.path.exists(local_file):
            os.remove(local_file)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        video_url = request.form.get('video_url')
        if video_url:
            # Start background thread
            thread = threading.Thread(target=process_video_task, args=(video_url,))
            thread.start()
            flash("Upload started! The short link will be sent to Telegram shortly.")
        else:
            flash("Please enter a valid URL.")
    return render_template('index.html')

if __name__ == "__main__":
    # Railway provides the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
