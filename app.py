import streamlit as st
import os
import requests
import asyncio
import edge_tts
import json
import random
import google.generativeai as genai
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ================= 雲端設定區 =================
st.set_page_config(page_title="AI 短影音工廠 (終極偵錯)", page_icon="🕵️‍♂️")

# 🚨【偵探模式】顯示版本號
import importlib.metadata
try:
    ver = importlib.metadata.version("google-generativeai")
except:
    ver = "無法取得"
st.warning(f"🔍 偵測報告：\n1. Google AI 套件版本: {ver}\n2. Python 版本: {os.sys.version.split()[0]}")
# ------------------------------------------------

# 📥 自動下載中文字體 ... (後面照舊)

# 📥 自動下載中文字體
def download_font():
    font_path = "NotoSansTC-Bold.otf"
    if not os.path.exists(font_path):
        url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansTC-Bold.otf"
        try:
            r = requests.get(url)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except:
            pass
    return font_path

def get_font(size=80):
    font_path = "NotoSansTC-Bold.otf"
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()

# 🧠 AI 寫腳本 (改回穩定版模型，並顯示錯誤)
def generate_script_from_ai(api_key, topic, duration_sec):
    genai.configure(api_key=api_key)
    est_sentences = int(int(duration_sec) / 4.5)
    if est_sentences < 3: est_sentences = 3
    
    # 這裡改用最穩定的模型，成功率最高
    models_to_try = ['gemini-1.5-flash-latest','gemini-1.5-flash', 
        'gemini-1.5-pro', 'gemini-pro']
    
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            prompt = f"""
            你是一個短影音腳本專家。請根據主題「{topic}」寫出一個短影音腳本。
            【規格】：影片長度 {duration_sec} 秒，請提供 {est_sentences} 個分鏡句子。
            【要求】：每句 15-20 字，搭配一個英文搜尋單字 (Keyword)。
            【格式】：請只回傳純 JSON 陣列，不要有 markdown 符號：
            [
                {{"text": "第一句旁白...", "keyword": "Keyword1"}},
                {{"text": "第二句旁白...", "keyword": "Keyword2"}}
            ]
            """
            response = model.generate_content(prompt)
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            # 【關鍵修改】如果失敗，會顯示黃色警告告訴你是哪個模型壞了
            st.warning(f"⚠️ 嘗試模型 {model_name} 失敗: {e}")
            continue
    return None

# 📥 下載影片
def download_video(api_key, query, filename):
    url = "https://api.pexels.com/videos/search"
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    params = {"query": query, "per_page": 1, "orientation": "portrait"}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get('videos') and len(data['videos']) > 0:
                video_url = data['videos'][0]['video_files'][0]['link']
                v_r = requests.get(video_url, headers=headers, timeout=30)
                if v_r.status_code == 200:
                    with open(filename, 'wb') as f:
                        f.write(v_r.content)
                    return True
    except Exception as e:
        st.error(f"下載失敗: {e}")
    return False

# 🗣️ TTS
def run_tts(text, filename, voice, rate):
    rate_str = f"{int((rate - 1.0) * 100):+d}%"
    async def _tts():
        communicate = edge_tts.Communicate(text, voice, rate=rate_str)
        await communicate.save(filename)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_tts())
        loop.close()
        return True
    except:
        return False

# 🖼️ 字幕圖片
def create_text_image(text, width, height):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_font(70)
    max_width = width * 0.85
    lines, current_line = [], ""
    for char in text:
        if draw.textlength(current_line + char, font=font) <= max_width:
            current_line += char
        else:
            lines.append(current_line)
            current_line = char
    lines.append(current_line)
    total_h = len(lines) * 80
    current_y = (height - total_h) / 2
    for line in lines:
        w = draw.textlength(line, font=font)
        x = (width - w) / 2
        for adj in range(-2, 3):
             for adj2 in range(-2, 3):
                 draw.text((x+adj, current_y+adj2), line, font=font, fill="black")
        draw.text((x, current_y), line, font=font, fill="white")
        current_y += 80
    return np.array(img)

# --- 主程式 ---
st.title("🎬 AI 短影音工廠 (穩定版)")

download_font()

with st.sidebar:
    st.header("⚙️ 參數設定")
    gemini_key_input = st.text_input("Gemini API Key (若已在雲端設定可留空)", type="password")
    pexels_key_input = st.text_input("Pexels API Key (若已在雲端設定可留空)", type="password")
    
    gemini_key = gemini_key_input if gemini_key_input else st.secrets.get("GEMINI_KEY", "")
    pexels_key = pexels_key_input if pexels_key_input else st.secrets.get("PEXELS_KEY", "")
    
    if st.secrets.get("GEMINI_KEY") and not gemini_key_input:
        st.caption("✅ 已啟用雲端金鑰 (Gemini)")
    if st.secrets.get("PEXELS_KEY") and not pexels_key_input:
        st.caption("✅ 已啟用雲端金鑰 (Pexels)")

    st.divider()
    voice_option = st.selectbox("配音員", ("女聲 - 曉臻", "男聲 - 雲哲"))
    voice_role = "zh-TW-HsiaoChenNeural" if "女聲" in voice_option else "zh-TW-YunJheNeural"
    speech_rate = st.slider("語速調整", 0.5, 2.0, 1.0, 0.1)
    duration = st.slider("影片目標長度 (秒)", 30, 300, 60, 10)

topic = st.text_input("💡 請輸入影片主題", placeholder="例如：吸塵器的起源")

if st.button("🚀 開始生成影片", type="primary"):
    if not gemini_key or not pexels_key:
        st.error("❌ 缺少 API Key！")
    elif not topic:
        st.error("❌ 請輸入主題")
    else:
        status = st.status("🧠 正在構思劇本...", expanded=True)
        try:
            # 1. 生成劇本
            script_data = generate_script_from_ai(gemini_key, topic, duration)
            if not script_data:
                # 這裡會因為上面的 st.warning 讓你看到具體原因
                status.update(label="❌ 劇本生成失敗 (請看上方黃色警告)", state="error")
                st.stop()
            
            status.write(f"✅ 劇本完成！共 {len(script_data)} 個分鏡")
            progress_bar = st.progress(0)
            clips = []
            
            # 2. 製作片段
            for i, data in enumerate(script_data):
                status.write(f"正在製作第 {i+1} 個片段: {data['keyword']}...")
                
                safe_kw = "".join([c for c in data['keyword'] if c.isalnum()])
                v_file = f"video_{safe_kw}.mp4"
                a_file = f"temp_{i}.mp3"
                
                if not download_video(pexels_key, data['keyword'], v_file):
                    if not download_video(pexels_key, "Abstract", "video_fallback.mp4"):
                        continue
                    v_file = "video_fallback.mp4"
                
                run_tts(data['text'], a_file, voice_role, speech_rate)
                
                try:
                    v_clip = VideoFileClip(v_file).resize(newsize=(1080, 1920))
                    a_clip = AudioFileClip(a_file)
                    if a_clip.duration > v_clip.duration:
                        v_clip = v_clip.loop(duration=a_clip.duration)
                    else:
                        v_clip = v_clip.subclip(0, a_clip.duration)
                    
                    v_clip = v_clip.set_audio(a_clip)
                    txt_clip = ImageClip(create_text_image(data['text'], 1080, 1920)).set_duration(a_clip.duration)
                    clips.append(CompositeVideoClip([v_clip, txt_clip]))
                    
                except Exception as e:
                    # 如果又出現 unknown file format，這裡會印出來
                    st.error(f"❌ 剪輯失敗: {e}")
                
                progress_bar.progress((i + 1) / len(script_data))
            
            if clips:
                status.write("🎬 正在合成最終影片...")
                final = concatenate_videoclips(clips)
                output_name = f"result_{random.randint(1000,9999)}.mp4"
                final.write_videofile(output_name, fps=24, codec='libx264', audio_codec='aac')
                status.update(label="✨ 製作完成！", state="complete")
                st.video(output_name)
            else:
                status.update(label="❌ 製作失敗", state="error")
                
        except Exception as e:
            st.error(f"系統錯誤: {e}")