import streamlit as st
import os
import requests
import asyncio
import edge_tts
import json
import random
import google.generativeai as genai
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, ColorClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ================= 雲端設定區 =================
st.set_page_config(page_title="AI 短影音工廠 (喪屍生存版)", page_icon="🧟")

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

# 🧠 AI 寫腳本
def generate_script_from_ai(api_key, topic, duration_sec):
    genai.configure(api_key=api_key)
    est_sentences = int(int(duration_sec) / 4.5)
    if est_sentences < 3: est_sentences = 3
    
    # 使用你帳號裡確認有的模型
    models_to_try = ['gemini-flash-latest', 'gemini-2.0-flash', 'gemini-pro-latest']
    
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
        except:
            continue
    return None

# 📥 下載影片
def download_video(api_key, query, filename):
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 1, "orientation": "portrait"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('videos'):
                video_url = data['videos'][0]['video_files'][0]['link']
                v_data = requests.get(video_url).content
                with open(filename, 'wb') as f:
                    f.write(v_data)
                return True
    except:
        pass
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
st.title("🧟 AI 短影音工廠 (喪屍生存版)")
download_font()

with st.sidebar:
    st.header("⚙️ 設定")
    gemini_key = st.text_input("Gemini Key", type="password") or st.secrets.get("GEMINI_KEY", "")
    pexels_key = st.text_input("Pexels Key", type="password") or st.secrets.get("PEXELS_KEY", "")
    voice_option = st.selectbox("配音", ("女聲 - 曉臻", "男聲 - 雲哲"))
    voice_role = "zh-TW-HsiaoChenNeural" if "女聲" in voice_option else "zh-TW-YunJheNeural"
    speech_rate = st.slider("語速", 0.5, 2.0, 1.2, 0.1)
    duration = st.slider("秒數", 30, 300, 45, 10)

topic = st.text_input("💡 主題", value="飛機的起源")

if st.button("🚀 誓死生成影片", type="primary"):
    if not gemini_key or not pexels_key:
        st.error("❌ 缺 Key")
        st.stop()
        
    status = st.status("🧠 啟動生存模式...", expanded=True)
    
    # 1. 劇本
    script_data = generate_script_from_ai(gemini_key, topic, duration)
    if not script_data:
        status.update(label="❌ 劇本失敗", state="error")
        st.stop()
    
    status.write(f"✅ 劇本完成！共 {len(script_data)} 句")
    progress_bar = st.progress(0)
    clips = []
    
    # 2. 製作
    for i, data in enumerate(script_data):
        status.write(f"正在製作: {data['keyword']}...")
        
        safe_kw = "".join([c for c in data['keyword'] if c.isalnum()])
        v_file = f"video_{safe_kw}.mp4"
        a_file = f"temp_{i}.mp3"
        
        # 下載素材
        download_video(pexels_key, data['keyword'], v_file)
        run_tts(data['text'], a_file, voice_role, speech_rate)
        
        # === ☢️ 核彈級防護罩 ===
        try:
            # 🎵 1. 處理聲音 (如果聲音壞了，就給它靜音，不准報錯！)
            a_clip = None
            try:
                if os.path.exists(a_file) and os.path.getsize(a_file) > 100:
                    a_clip = AudioFileClip(a_file)
                else:
                    raise Exception("Audio bad")
            except:
                st.warning(f"⚠️ 片段 {i+1} 語音失敗，將使用靜音。")
                a_clip = None # 設定為無聲，稍後處理

            # 🎥 2. 處理影片 (如果影片壞了，就給它黑底！)
            try:
                if os.path.exists(v_file) and os.path.getsize(v_file) > 1000:
                    v_clip = VideoFileClip(v_file).resize(newsize=(1080, 1920))
                else:
                    raise Exception("Video bad")
            except:
                st.warning(f"⚠️ 片段 {i+1} 影片失敗，使用黑底。")
                # 預設 3 秒長度 (如果沒有聲音)
                def_dur = a_clip.duration if a_clip else 3
                v_clip = ColorClip(size=(1080, 1920), color=(0,0,0), duration=def_dur)
            
            # ✂️ 3. 長度對齊
            clip_dur = a_clip.duration if a_clip else v_clip.duration
            
            if v_clip.duration < clip_dur:
                v_clip = v_clip.loop(duration=clip_dur)
            else:
                v_clip = v_clip.subclip(0, clip_dur)
            
            # 🔊 4. 合成聲音 (如果是好的就加上去)
            if a_clip:
                v_clip = v_clip.set_audio(a_clip)
            
            # 📝 5. 加上字幕
            txt_clip = ImageClip(create_text_image(data['text'], 1080, 1920)).set_duration(clip_dur)
            clips.append(CompositeVideoClip([v_clip, txt_clip]))
            
        except Exception as e:
            st.error(f"❌ 嚴重例外 (不應該發生): {e}")
            # 萬一真的真的不行，跳過就好，不要停下來
            continue
        
        progress_bar.progress((i + 1) / len(script_data))
    
    # 3. 最終合成
    if clips:
        status.write("🎬 正在合成最終影片...")
        try:
            final = concatenate_videoclips(clips)
            output_name = f"result_{random.randint(1000,9999)}.mp4"
            final.write_videofile(output_name, fps=24, codec='libx264', audio_codec='aac')
            status.update(label="✨ 終於成功了！", state="complete")
            st.balloons()
            st.video(output_name)
        except Exception as e:
             st.error(f"合成失敗: {e}")
    else:
        status.update(label="❌ 全軍覆沒，請檢查網路連線", state="error")