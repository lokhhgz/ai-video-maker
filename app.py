import streamlit as st
import os
import requests
import asyncio
import edge_tts
import json
import random
import gc
import base64
import google.generativeai as genai
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, ColorClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ================= 設定區 =================
st.set_page_config(page_title="AI Shorts Maker (Fixed Font Size)", page_icon="🇺🇸")

# 📉 解析度設定
VIDEO_W, VIDEO_H = 540, 960 

# 🔤 字體設定
def get_font(size):
    system_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf"
    ]
    for path in system_fonts:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()

# 🧠 AI 寫英文腳本
def generate_script(api_key, topic, duration):
    genai.configure(api_key=api_key)
    est_sentences = int(int(duration) / 4)
    if est_sentences < 3: est_sentences = 3
    
    prompt = f"""
    You are a professional short video script writer. Create a script about topic: "{topic}".
    Target duration: {duration} seconds.
    Generate exactly {est_sentences} sentences.
    
    CRITICAL REQUIREMENTS:
    1. Language: English.
    2. Length: Max 12 words per sentence.
    3. Style: Clear and engaging.
    4. Keyword: Provide 1 English search keyword for stock video.
    5. Format: Return ONLY a raw JSON array:
    [
        {{"text": "Coffee originated in Ethiopia.", "keyword": "Ethiopia"}},
        {{"text": "Goats discovered the beans first.", "keyword": "Goat"}}
    ]
    """
    
    models = ['gemini-flash-latest', 'gemini-2.0-flash', 'gemini-pro']
    for m in models:
        try:
            model = genai.GenerativeModel(m)
            response = model.generate_content(prompt)
            clean = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except:
            continue
    return None

# 📥 下載影片
def download_video(api_key, query, filename):
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 1, "orientation": "portrait"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get('videos'):
                link = data['videos'][0]['video_files'][0]['link']
                with open(filename, 'wb') as f:
                    f.write(requests.get(link).content)
                return True
    except:
        pass
    return False

# 🗣️ TTS (試聽用 - Base64)
def run_tts_bytes(text, voice, rate):
    async def _gen():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
        return data
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_gen())
    except:
        return None

# 🗣️ TTS (合成用 - 存檔)
def run_tts_file(text, filename, voice, rate):
    async def _save():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(filename)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_save())
        return True
    except:
        return False

# 🖼️ 製作字幕 (🔥 改用像素寬度精準換行)
def create_subtitle(text, width, height):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 1. 固定字體大小為 32px (或你想要的適中大小)
    fixed_size = 32
    font = get_font(fixed_size)
    safe_width = width - 60 # 兩邊各留 30px 邊界
    
    # 2. 智慧像素換行邏輯
    words = text.split(' ')
    lines = []
    current_line = []
    
    for word in words:
        # 測試加上這個單字後是否會太寬
        test_line = ' '.join(current_line + [word])
        w = draw.textlength(test_line, font=font)
        
        if w <= safe_width:
            current_line.append(word)
        else:
            # 太寬了，把目前的內容存為一行，新的單字放到下一行
            lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
        
    # 3. 計算繪製位置與背景
    line_height = fixed_size + 12
    total_height = len(lines) * line_height
    start_y = height - total_height - 120 # 固定在中偏下位置
    
    for i, line in enumerate(lines):
        line_w = draw.textlength(line, font=font)
        x = (width - line_w) / 2
        y = start_y + (i * line_height)
        
        # 畫半透明底色
        pad = 8
        draw.rectangle(
            [x - pad, y - pad/2, x + line_w + pad, y + line_height - pad], 
            fill=(0, 0, 0, 160)
        )
        # 畫文字
        draw.text((x, y), line, font=font, fill="white")
    
    return np.array(img)

# --- 主程式 ---
st.title("🇺🇸 AI Shorts Maker (Clean Subtitles)")

with st.sidebar:
    st.header("⚙️ Settings")
    
    gemini_key = st.text_input("Gemini Key", type="password") or st.secrets.get("GEMINI_KEY", "")
    pexels_key = st.text_input("Pexels Key", type="password") or st.secrets.get("PEXELS_KEY", "")
    
    if gemini_key: st.success("✅ Gemini Key Ready")
    if pexels_key: st.success("✅ Pexels Key Ready")

    st.divider()

    voice_map = {
        "Female (Ava)": "en-US-AvaNeural",
        "Male (Andrew)": "en-US-AndrewNeural",
        "Female (Emma)": "en-US-EmmaNeural",
        "Male (Brian)": "en-US-BrianNeural"
    }
    voice_name = st.selectbox("Voice Actor", list(voice_map.keys()))
    voice_role = voice_map[voice_name]
    rate = st.slider("Speaking Speed", 0.5, 1.5, 1.0, 0.1)
    
    if st.button("🔊 Test Voice Now"):
        test_text = "This is a test. My font size will remain consistent and clear."
        rate_str = f"{int((rate - 1.0) * 100):+d}%"
        audio_bytes = run_tts_bytes(test_text, voice_role, rate_str)
        if audio_bytes:
            b64 = base64.b64encode(audio_bytes).decode()
            md = f'<audio controls autoplay><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>'
            st.markdown(md, unsafe_allow_html=True)

    st.divider()
    duration = st.slider("Duration (sec)", 15, 300, 30, 5)

# --- 右側主畫面 ---

if "script" not in st.session_state:
    st.session_state.script = None

topic = st.text_input("Topic", "Life of Albert Einstein")

if st.button("Step 1: Generate Script", type="primary"):
    with st.spinner("Writing script..."):
        script = generate_script(gemini_key, topic, duration)
        if script:
            st.session_state.script = script
            st.rerun()

if st.session_state.script:
    st.subheader("📝 Script Preview")
    for i, item in enumerate(st.session_state.script):
        st.markdown(f"**{i+1}. [{item['keyword']}]** {item['text']}")

    st.divider()

    if st.button("Step 2: Render Video", type="primary"):
        status = st.status("🎬 Rendering video...", expanded=True)
        progress_bar = st.progress(0)
        clips = []
        
        try:
            for i, data in enumerate(st.session_state.script):
                status.write(f"Processing scene {i+1}...")
                
                v_file = f"v_{i}.mp4"
                a_file = f"a_{i}.mp3"
                
                download_video(pexels_key, data['keyword'], v_file)
                run_tts_file(data['text'], a_file, voice_role, f"{int((rate - 1.0) * 100):+d}%")
                
                try:
                    a_clip = AudioFileClip(a_file)
                    if os.path.exists(v_file) and os.path.getsize(v_file) > 1000:
                        v_clip = VideoFileClip(v_file).resize(newsize=(VIDEO_W, VIDEO_H))
                    else:
                        v_clip = ColorClip(size=(VIDEO_W, VIDEO_H), color=(0,0,0), duration=a_clip.duration)
                    
                    final_dur = a_clip.duration
                    v_clip = v_clip.loop(duration=final_dur) if v_clip.duration < final_dur else v_clip.subclip(0, final_dur)
                    v_clip = v_clip.set_audio(a_clip)
                    
                    # 製作固定大小的字幕
                    txt_img = create_subtitle(data['text'], VIDEO_W, VIDEO_H)
                    txt_clip = ImageClip(txt_img).set_duration(final_dur)
                    
                    clips.append(CompositeVideoClip([v_clip, txt_clip]))
                    del v_clip, a_clip, txt_clip
                    gc.collect()
                except:
                    continue
                
                progress_bar.progress((i + 1) / len(st.session_state.script))
            
            if clips:
                final_video = concatenate_videoclips(clips, method="compose")
                output_path = f"final_{random.randint(1000,9999)}.mp4"
                final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac', preset='ultrafast')
                status.update(label="✅ Done!", state="complete")
                st.video(output_path)
        except Exception as e:
            st.error(f"Failed: {e}")