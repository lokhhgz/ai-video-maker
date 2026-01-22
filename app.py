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
st.set_page_config(page_title="AI 短影音工廠 (絕對成功版)", page_icon="🏆")

# 🧹【強制清理】刪除可能損壞的字體檔
if os.path.exists("NotoSansTC-Bold.otf"):
    try:
        os.remove("NotoSansTC-Bold.otf")
        print("已刪除舊字體檔")
    except:
        pass

# 📥 獲取字體 (改用絕對安全的預設字體)
def get_font(size=50):
    # 直接回傳預設字體，雖然醜一點但絕不會報錯
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

# 🖼️ 字幕圖片 (簡化版，防止崩潰)
def create_text_image(text, width, height):
    try:
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        font = get_font(50)
        
        # 簡單置中繪製，不做複雜運算以免報錯
        # 預設字體不支援 getlength，所以我們用簡單估算
        text_len = len(text) * 20 # 估算寬度
        x = (width - text_len) / 2
        if x < 10: x = 10
        y = height - 200
        
        # 畫黑底白字
        draw.text((x+2, y+2), text, font=font, fill="black")
        draw.text((x, y), text, font=font, fill="white")
        return np.array(img)
    except:
        # 萬一畫圖失敗，回傳全透明圖 (至少影片不會掛掉)
        return np.array(Image.new('RGBA', (width, height), (0, 0, 0, 0)))

# --- 主程式 ---
st.title("🏆 AI 短影音工廠 (絕對成功版)")

with st.sidebar:
    st.header("⚙️ 設定")
    gemini_key = st.text_input("Gemini Key", type="password") or st.secrets.get("GEMINI_KEY", "")
    pexels_key = st.text_input("Pexels Key", type="password") or st.secrets.get("PEXELS_KEY", "")
    voice_option = st.selectbox("配音", ("女聲 - 曉臻", "男聲 - 雲哲"))
    voice_role = "zh-TW-HsiaoChenNeural" if "女聲" in voice_option else "zh-TW-YunJheNeural"
    speech_rate = st.slider("語速", 0.5, 2.0, 1.2, 0.1)
    duration = st.slider("秒數", 30, 300, 45, 10)

topic = st.text_input("💡 主題", value="飛機的起源")

if st.button("🚀 生成影片", type="primary"):
    if not gemini_key or not pexels_key:
        st.error("❌ 缺 Key")
        st.stop()
        
    status = st.status("🧠 正在運作中...", expanded=True)
    
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
        
        download_video(pexels_key, data['keyword'], v_file)
        run_tts(data['text'], a_file, voice_role, speech_rate)
        
        # === 🛡️ 全方位防護罩 ===
        try:
            # 1. 聲音
            a_clip = None
            try:
                if os.path.exists(a_file) and os.path.getsize(a_file) > 100:
                    a_clip = AudioFileClip(a_file)
            except:
                pass # 聲音壞了就靜音
            
            # 2. 影片
            try:
                if os.path.exists(v_file) and os.path.getsize(v_file) > 1000:
                    v_clip = VideoFileClip(v_file).resize(newsize=(1080, 1920))
                else:
                    raise Exception("Video bad")
            except:
                # 影片壞了就黑底
                dur = a_clip.duration if a_clip else 3
                v_clip = ColorClip(size=(1080, 1920), color=(0,0,0), duration=dur)

            # 3. 對齊
            final_dur = a_clip.duration if a_clip else v_clip.duration
            if v_clip.duration < final_dur:
                v_clip = v_clip.loop(duration=final_dur)
            else:
                v_clip = v_clip.subclip(0, final_dur)
            
            if a_clip:
                v_clip = v_clip.set_audio(a_clip)

            # 4. 字幕 (加入防護)
            try:
                # 這裡最關鍵！如果 create_text_image 失敗，這裡會抓住
                txt_img = create_text_image(data['text'], 1080, 1920)
                txt_clip = ImageClip(txt_img).set_duration(final_dur)
                clips.append(CompositeVideoClip([v_clip, txt_clip]))
            except Exception as e:
                # 萬一字幕真的不行，至少把沒字幕的影片加進去
                print(f"字幕失敗: {e}")
                clips.append(v_clip)
                
        except Exception as e:
            # 這是最後一道防線，如果連上面都穿透了，這句就跳過，但不崩潰
            print(f"❌ 跳過片段 {i}: {e}")
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
        status.update(label="❌ 什麼都沒生出來", state="error")