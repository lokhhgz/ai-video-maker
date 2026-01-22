import streamlit as st
import os
import requests
import asyncio
import edge_tts
import json
import random
import google.generativeai as genai
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, CompositeAudioClip
# 【重要】引入 audio_loop 用來處理音樂循環
from moviepy.audio.fx.all import audio_loop
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ================= 🔑 金鑰設定 (雲端部署安全版) =================
# 嘗試從 Streamlit Secrets 讀取，如果沒有就用空字串
try:
    DEFAULT_PEXELS_KEY = st.secrets["PEXELS_KEY"]
    DEFAULT_GEMINI_KEY = st.secrets["GEMINI_KEY"]
except:
    DEFAULT_PEXELS_KEY = ""
    DEFAULT_GEMINI_KEY = ""

# 設定標準短影音尺寸 (1080x1920)
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
# ===============================================================

# 1. 設置頁面
st.set_page_config(page_title="AI 短影音工廠", page_icon="🎬")

# --- 核心功能函式庫 ---

# 🕵️‍♂️ 字體偵探
def get_chinese_font(size=80):
    possible_fonts = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/Library/Fonts/Arial Unicode.ttf"
    ]
    for font_path in possible_fonts:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue
    return ImageFont.load_default()

# 🧠 AI 寫腳本
def generate_script_from_ai(api_key, topic, duration_sec):
    genai.configure(api_key=api_key)
    
    # 估算句子數量 (語速正常約 4.5秒一句)
    est_sentences = int(int(duration_sec) / 4.5)
    if est_sentences < 3: est_sentences = 3
    
    models_to_try = [
        'gemini-2.0-flash', 
        'gemini-flash-latest',
        'gemini-pro-latest',
        'gemini-2.0-flash-lite',
        'gemini-2.5-flash-lite',
        'gemini-flash-lite-latest',
        'gemini-2.5-flash',
        'gemini-2.5-pro'
    ]
    
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            # 提示詞優化：支援長影片
            prompt = f"""
            你是一個短影音腳本專家。請根據主題「{topic}」寫出一個短影音腳本。
            
            【規格要求】：
            1. 目標影片長度：{duration_sec} 秒。
            2. 請務必提供約 {est_sentences} 個分鏡句子 (Sentence)，以確保時長足夠。
            3. 每一句長度控制在 15-20 字以內，語氣要自然流暢。
            4. 每一句都要搭配一個最適合的「英文畫面搜尋單字」(名詞為主，例如: Forest, City, Man)。
            
            【重要】請嚴格按照以下 JSON 格式輸出，不要包含 ```json 或其他符號，只回傳純 JSON：
            [
                {{"text": "第一句旁白內容...", "keyword": "Keyword1"}},
                {{"text": "第二句旁白內容...", "keyword": "Keyword2"}},
                ...
            ]
            """
            response = model.generate_content(prompt)
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            continue 
            
    return None # 失敗回傳 None

# 📥 下載影片
def download_video(api_key, query, filename):
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        return True
    
    url = "https://api.pexels.com/videos/search"
    params = {"query": query, "per_page": 1, "orientation": "portrait"}
    headers = {"Authorization": api_key}
    
    try:
        r = requests.get(url, headers=headers, params=params)
        if r.status_code == 200:
            data = r.json()
            if data.get('videos') and len(data['videos']) > 0:
                video_url = data['videos'][0]['video_files'][0]['link']
                with open(filename, 'wb') as f:
                    f.write(requests.get(video_url).content)
                return True
    except:
        pass
    return False

# 🗣️ 生成語音 (支援語速調整)
async def generate_audio_file(text, filename, voice_role, rate_float):
    # 將小數點語速 (1.2) 轉換成 Edge-TTS 格式 ("+20%")
    rate_str = f"{int((rate_float - 1.0) * 100):+d}%"
    
    try:
        communicate = edge_tts.Communicate(text, voice_role, rate=rate_str)
        await communicate.save(filename)
        return True
    except Exception as e:
        return False

# 🎵 下載背景音樂
def ensure_bgm_exists():
    if not os.path.exists("music"):
        os.makedirs("music")
    music_path = "music/sample_bgm.mp3"
    
    # 檢查並下載
    if not os.path.exists(music_path) or os.path.getsize(music_path) < 10000:
        if os.path.exists(music_path): os.remove(music_path)
        url = "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/no_curator/Kevin_MacLeod/Impact/Kevin_MacLeod_-_03_-_Impact_Moderato.mp3"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                with open(music_path, "wb") as f:
                    f.write(r.content)
        except:
            pass

# 🖼️ 製作字幕圖片
def create_text_image(text, width, height):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_chinese_font(70)
    max_width = width * 0.85
    
    # 自動換行
    lines, current_line = [], ""
    for char in text:
        if draw.textlength(current_line + char, font=font) <= max_width:
            current_line += char
        else:
            lines.append(current_line)
            current_line = char
    lines.append(current_line)

    # 計算總高度
    total_h = sum([80 for _ in lines]) # 簡化行高計算
    current_y = (height - total_h) / 2
    
    for line in lines:
        w = draw.textlength(line, font=font)
        x = (width - w) / 2
        draw.text((x+4, current_y+4), line, font=font, fill="black")
        draw.text((x, current_y), line, font=font, fill="white")
        current_y += 80
    
    return np.array(img)

# --- 介面邏輯 ---

st.title("🎬 AI 全自動短影音工廠")
st.markdown("輸入主題，調整設定，一鍵生成你的專屬影片！")

# 側邊欄設定
with st.sidebar:
    st.header("⚙️ 參數設定")
    
    # 1. 安全修正：輸入框預設是「空的」，不要填入任何東西
    gemini_key_input = st.text_input("Gemini API Key (若已在雲端設定可留空)", type="password")
    pexels_key_input = st.text_input("Pexels API Key (若已在雲端設定可留空)", type="password")

    # 2. 程式邏輯：如果輸入框是空的，就自動去雲端後台 (Secrets) 拿金鑰
    gemini_key = gemini_key_input if gemini_key_input else st.secrets.get("GEMINI_KEY", "")
    pexels_key = pexels_key_input if pexels_key_input else st.secrets.get("PEXELS_KEY", "")

    # 3. 貼心提示：顯示綠色小字，讓你知道後台有成功抓到鑰匙
    if st.secrets.get("GEMINI_KEY") and not gemini_key_input:
        st.caption("✅ 已啟用雲端金鑰 (Gemini)")
    if st.secrets.get("PEXELS_KEY") and not pexels_key_input:
        st.caption("✅ 已啟用雲端金鑰 (Pexels)")
    
    st.divider()
    
    # 配音設定
    voice_option = st.selectbox(
        "選擇配音員",
        ("女聲 - 曉臻 (HsiaoChen)", "男聲 - 雲哲 (YunJhe)"),
        index=0
    )
    voice_role = "zh-TW-HsiaoChenNeural" if "女聲" in voice_option else "zh-TW-YunJheNeural"
    
    # 語速設定 (新增功能)
    speech_rate = st.slider("語速調整 (1.0 為正常)", 0.5, 2.0, 1.0, 0.1)
    
    # 試聽按鈕
    if st.button("🔊 試聽目前語音"):
        test_file = "preview_audio.mp3"
        asyncio.run(generate_audio_file("這是一個語音試聽測試，您覺得速度可以嗎？", test_file, voice_role, speech_rate))
        if os.path.exists(test_file):
            st.audio(test_file)
            
    st.divider()
    
    # 時間設定 (解鎖到 300 秒)
    video_duration = st.slider("影片目標長度 (秒)", 30, 300, 60, 10)

# 主畫面
topic = st.text_input("💡 請輸入影片主題", placeholder="例如：為什麼貓咪喜歡紙箱？")

if st.button("🚀 開始生成影片", type="primary"):
    if not topic:
        st.error("請先輸入主題！")
    else:
        # 1. 確保音樂存在
        ensure_bgm_exists()
        
        # 2. 生成腳本
        with st.status("🧠 正在呼叫 AI 大腦構思劇本...", expanded=True) as status:
            script_data = generate_script_from_ai(gemini_key, topic, video_duration)
            
            if not script_data:
                status.update(label="❌ AI 生成失敗，請稍後再試", state="error")
                st.stop()
            
            status.write(f"✅ 劇本完成！共 {len(script_data)} 個分鏡。")
            
            # 顯示劇本預覽
            with st.expander("👀 查看 AI 寫的劇本"):
                for idx, item in enumerate(script_data):
                    st.write(f"**[{idx+1}]** {item['text']} (關鍵字: {item['keyword']})")

            # 3. 開始製作
            progress_bar = st.progress(0)
            clips = []
            
            for i, data in enumerate(script_data):
                status.write(f"正在製作第 {i+1}/{len(script_data)} 個片段...")
                
                text = data["text"]
                keyword = data["keyword"]
                
                # 處理檔名
                safe_keyword = "".join([c for c in keyword if c.isalnum()])
                video_file = f"video_{safe_keyword}.mp4"
                audio_file = f"temp_{i}.mp3"
                
                # 下載素材
                if not download_video(pexels_key, keyword, video_file):
                    # 備用方案
                    video_file = "video_Abstract.mp4"
                    download_video(pexels_key, "Abstract", video_file)
                
                if not os.path.exists(video_file): continue

                # 生成語音
                asyncio.run(generate_audio_file(text, audio_file, voice_role, speech_rate))
                
                # 合成片段
                try:
                    video_clip = VideoFileClip(video_file)
                    audio_clip = AudioFileClip(audio_file)
                    
                    # 統一尺寸 & 調整長度
                    video_clip = video_clip.resize(newsize=(TARGET_WIDTH, TARGET_HEIGHT))
                    
                    if audio_clip.duration > 0:
                        if audio_clip.duration > video_clip.duration:
                            video_clip = video_clip.loop(duration=audio_clip.duration)
                        else:
                            video_clip = video_clip.subclip(0, audio_clip.duration)
                        
                        video_clip = video_clip.set_audio(audio_clip)
                        
                        # 上字幕
                        txt_img = create_text_image(text, video_clip.w, video_clip.h)
                        txt_clip = ImageClip(txt_img).set_duration(audio_clip.duration)
                        
                        final_chunk = CompositeVideoClip([video_clip, txt_clip])
                        clips.append(final_chunk)
                        
                except Exception as e:
                    print(f"Error processing clip {i}: {e}")
                
                # 更新進度條
                progress_bar.progress((i + 1) / len(script_data))

            # 4. 最終接合
            if clips:
                status.write("🎬 正在進行最終剪輯與配樂...")
                final_video_no_bgm = concatenate_videoclips(clips)
                
                # 配樂
                music_folder = "music"
                music_files = [f for f in os.listdir(music_folder) if f.endswith(('.mp3', '.ogg'))]
                
                if music_files:
                    bgm_path = os.path.join(music_folder, random.choice(music_files))
                    try:
                        bgm = AudioFileClip(bgm_path)
                        bgm = audio_loop(bgm, duration=final_video_no_bgm.duration)
                        bgm = bgm.volumex(0.15)
                        final_audio = CompositeAudioClip([final_video_no_bgm.audio, bgm])
                        final_video = final_video_no_bgm.set_audio(final_audio)
                    except:
                        final_video = final_video_no_bgm
                else:
                    final_video = final_video_no_bgm
                
                # 輸出
                output_filename = f"result_{topic}.mp4"
                final_video.write_videofile(output_filename, fps=24, codec='libx264', audio_codec='aac')
                
                status.update(label="✨ 影片製作完成！", state="complete")
                
                # 顯示影片與下載按鈕
                st.video(output_filename)
                
                with open(output_filename, "rb") as file:
                    st.download_button(
                        label="⬇️ 下載影片",
                        data=file,
                        file_name=output_filename,
                        mime="video/mp4"
                    )
                
                # 清理暫存音檔
                for i in range(len(script_data)):
                    if os.path.exists(f"temp_{i}.mp3"): os.remove(f"temp_{i}.mp3")
            else:
                status.update(label="❌ 製作失敗，沒有生成任何片段", state="error")