import streamlit as st
import os
import requests
import asyncio
import edge_tts
import json
import random
import gc
import textwrap
import base64
import google.generativeai as genai
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, 
    concatenate_videoclips, ColorClip, CompositeAudioClip
)
# 🚨 關鍵：引入音訊特效模組
from moviepy.audio.fx.all import audio_loop, volumex 
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ================= 設定區 =================
st.set_page_config(page_title="AI Shorts Maker (BGM Fixed)", page_icon="🎸")

# 📉 解析度與 BGM 設定
VIDEO_W, VIDEO_H = 540, 960 
BGM_URL = "https://www.bensound.com/bensound-music/bensound-creativeminds.mp3"
BGM_FILE = "bgm_default.mp3"

# 🔤 字體設定
def get_font(size):
    system_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf"
    ]
    for path in system_fonts:
        if os.path.exists(path):
            try: return ImageFont.truetype(path, size)
            except: continue
    return ImageFont.load_default()

# 🧠 AI 寫腳本
def generate_script(api_key, topic, duration):
    genai.configure(api_key=api_key)
    est_sentences = int(int(duration) / 5)
    if est_sentences < 3: est_sentences = 3
    prompt = f"""
    Create a short video script about: "{topic}".
    Target duration: {duration} seconds.
    Generate exactly {est_sentences} short sentences (max 10 words each).
    Return ONLY raw JSON array:
    [{{"text": "Sentence...", "keyword": "Keyword"}}]
    """
    models = ['gemini-flash-latest', 'gemini-2.0-flash', 'gemini-pro']
    for m in models:
        try:
            model = genai.GenerativeModel(m)
            response = model.generate_content(prompt)
            clean = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except: continue
    return None

# 📥 下載素材
def download_bgm(url, filename):
    if not os.path.exists(filename):
        try:
            r = requests.get(url, timeout=10)
            with open(filename, 'wb') as f:
                f.write(r.content)
            return True
        except: return False
    return True

def download_pexels(api_key, query, filename):
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
    except: pass
    return False

# 🗣️ TTS (試聽)
def run_tts_bytes(text, voice, rate):
    async def _gen():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": data += chunk["data"]
        return data
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_gen())
    except: return None

# 🗣️ TTS (存檔)
def run_tts_file(text, filename, voice, rate):
    async def _save():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(filename)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_save())
        return True
    except: return False

# 🖼️ 製作字幕 (智慧換行版)
def create_subtitle(text, width, height):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fixed_size = 32
    font = get_font(fixed_size)
    safe_width = width - 60 
    words = text.split(' ')
    lines, current_line = [], []
    for word in words:
        test_line = ' '.join(current_line + [word])
        if draw.textlength(test_line, font=font) <= safe_width:
            current_line.append(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
    if current_line: lines.append(' '.join(current_line))
    line_height = fixed_size + 12
    start_y = height - (len(lines) * line_height) - 120 
    for i, line in enumerate(lines):
        line_w = draw.textlength(line, font=font)
        x, y = (width - line_w) / 2, start_y + (i * line_height)
        draw.rectangle([x-8, y-4, x+line_w+8, y+line_height-8], fill=(0,0,0), 160)
        draw.text((x, y), line, font=font, fill="white")
    return np.array(img)

# --- 主程式 ---
st.title("🎸 AI Shorts Maker (BGM Fixed)")

with st.sidebar:
    st.header("⚙️ Settings")
    gemini_key = st.text_input("Gemini Key", type="password") or st.secrets.get("GEMINI_KEY", "")
    pexels_key = st.text_input("Pexels Key", type="password") or st.secrets.get("PEXELS_KEY", "")
    
    if gemini_key: st.success("✅ Gemini Ready")
    if pexels_key: st.success("✅ Pexels Ready")

    st.divider()
    voice_map = {"Ava (Female)": "en-US-AvaNeural", "Andrew (Male)": "en-US-AndrewNeural"}
    voice_role = voice_map[st.selectbox("Voice", list(voice_map.keys()))]
    rate = st.slider("Speed", 0.5, 1.5, 1.0, 0.1)
    
    st.subheader("🎵 BGM Settings")
    use_bgm = st.checkbox("Enable Background Music", value=True)
    bgm_vol = st.slider("BGM Volume", 0.0, 0.5, 0.15, 0.05)
    
    if st.button("🔊 Test Preview"):
        audio_bytes = run_tts_bytes("Testing background music sync.", voice_role, f"{int((rate-1)*100):+d}%")
        if audio_bytes:
            b64 = base64.b64encode(audio_bytes).decode()
            st.markdown(f'<audio controls autoplay><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>', unsafe_allow_html=True)

    st.divider()
    duration = st.slider("Duration (sec)", 15, 300, 30, 5)

# --- 右側主畫面 ---
if "script" not in st.session_state: st.session_state.script = None
topic = st.text_input("Topic", "The future of AI")

if st.button("Step 1: Generate Script", type="primary"):
    with st.spinner("Brainstorming..."):
        script = generate_script(gemini_key, topic, duration)
        if script: st.session_state.script = script; st.rerun()

if st.session_state.script:
    st.subheader("📝 Script Preview")
    for i, item in enumerate(st.session_state.script):
        st.markdown(f"**{i+1}. [{item['keyword']}]** {item['text']}")

    st.divider()

    if st.button("Step 2: Render Final Video", type="primary"):
        status = st.status("🎬 Processing...", expanded=True)
        progress_bar = st.progress(0)
        clips = []
        
        try:
            for i, data in enumerate(st.session_state.script):
                status.write(f"Building scene {i+1}...")
                v_file, a_file = f"v_{i}.mp4", f"a_{i}.mp3"
                download_pexels(pexels_key, data['keyword'], v_file)
                run_tts_file(data['text'], a_file, voice_role, f"{int((rate-1)*100):+d}%")
                
                try:
                    a_clip = AudioFileClip(a_file)
                    v_clip = VideoFileClip(v_file).resize(newsize=(VIDEO_W, VIDEO_H)) if os.path.exists(v_file) and os.path.getsize(v_file) > 1000 else ColorClip(size=(VIDEO_W, VIDEO_H), color=(0,0,0), duration=a_clip.duration)
                    
                    # 畫面循環與對齊
                    v_clip = v_clip.loop(duration=a_clip.duration) if v_clip.duration < a_clip.duration else v_clip.subclip(0, a_clip.duration)
                    v_clip = v_clip.set_audio(a_clip)
                    
                    # 字幕
                    txt_clip = ImageClip(create_subtitle(data['text'], VIDEO_W, VIDEO_H)).set_duration(a_clip.duration)
                    clips.append(CompositeVideoClip([v_clip, txt_clip]))
                    del v_clip, a_clip, txt_clip; gc.collect()
                except: continue
                progress_bar.progress((i+1)/len(st.session_state.script))
            
            if clips:
                status.write("🎸 Final Mixing...")
                final_video = concatenate_videoclips(clips, method="compose")
                
                if use_bgm:
                    download_bgm(BGM_URL, BGM_FILE)
                    if os.path.exists(BGM_FILE):
                        bgm = AudioFileClip(BGM_FILE)
                        # 🔥 修正點：改用 audio_loop 函數
                        bgm = audio_loop(bgm, duration=final_video.duration)
                        bgm = volumex(bgm, bgm_vol)
                        
                        final_audio = CompositeAudioClip([final_video.audio, bgm])
                        final_video = final_video.set_audio(final_audio)

                output_path = f"final_{random.randint(1000,9999)}.mp4"
                final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac', preset='ultrafast')
                status.update(label="✅ Success!", state="complete")
                
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2: st.video(output_path)
                with open(output_path, "rb") as f:
                    st.download_button("📥 Download Video", f, file_name="ai_video.mp4", mime="video/mp4", type="primary", use_container_width=True)
                st.balloons()
        except Exception as e: st.error(f"Render Error: {e}")