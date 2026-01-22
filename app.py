import streamlit as st
import os
import requests
import asyncio
import edge_tts
import json
import random
import gc # 垃圾回收機制
import google.generativeai as genai
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, ColorClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ================= 雲端設定區 =================
st.set_page_config(page_title="AI 短影音工廠 (輕量版)", page_icon="⚡")

# 📉 設定影片解析度 (540x960 省記憶體，防止當機)
VIDEO_W, VIDEO_H = 540, 960 

# 🧹 清理字體
if os.path.exists("NotoSansTC-Bold.otf"):
    try:
        os.remove("NotoSansTC-Bold.otf")
    except:
        pass

def get_font(size=30):
    return ImageFont.load_default()

# 🧠 AI 寫腳本
def generate_script_from_ai(api_key, topic, duration_sec):
    genai.configure(api_key=api_key)
    est_sentences = int(int(duration_sec) / 5) # 稍微減少句子數量，減輕負擔
    if est_sentences < 3: est_sentences = 3
    
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
        r = requests.get(url, headers=headers, params=params, timeout=5)
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
    try:
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        font = get_font(30) # 字體小一點配合解析度
        
        text_len = len(text) * 15 
        x = (width - text_len) / 2
        if x < 10: x = 10
        y = height - 150
        
        draw.text((x+2, y+2), text, font=font, fill="black")
        draw.text((x, y), text, font=font, fill="white")
        return np.array(img)
    except:
        return np.array(Image.new('RGBA', (width, height), (0, 0, 0, 0)))

# --- 主程式 ---
st.title("⚡ AI 短影音工廠 (輕量版)")

with st.sidebar:
    st.header("⚙️ 設定")
    gemini_key = st.text_input("Gemini Key", type="password") or st.secrets.get("GEMINI_KEY", "")
    pexels_key = st.text_input("Pexels Key", type="password") or st.secrets.get("PEXELS_KEY", "")
    voice_option = st.selectbox("配音", ("女聲 - 曉臻", "男聲 - 雲哲"))
    voice_role = "zh-TW-HsiaoChenNeural" if "女聲" in voice_option else "zh-TW-YunJheNeural"
    speech_rate = st.slider("語速", 0.5, 2.0, 1.2, 0.1)
    duration = st.slider("秒數", 30, 300, 45, 10)

topic = st.text_input("💡 主題", value="飛機的起源")

if st.button("🚀 生成影片 (低負載模式)", type="primary"):
    if not gemini_key or not pexels_key:
        st.error("❌ 缺 Key")
        st.stop()
        
    status = st.status("🧠 啟動輕量引擎...", expanded=True)
    
    script_data = generate_script_from_ai(gemini_key, topic, duration)
    if not script_data:
        status.update(label="❌ 劇本失敗", state="error")
        st.stop()
    
    status.write(f"✅ 劇本完成！共 {len(script_data)} 句")
    progress_bar = st.progress(0)
    clips = []
    
    for i, data in enumerate(script_data):
        status.write(f"製作片段 {i+1}/{len(script_data)}: {data['keyword']}...")
        
        safe_kw = "".join([c for c in data['keyword'] if c.isalnum()])
        v_file = f"video_{safe_kw}.mp4"
        a_file = f"temp_{i}.mp3"
        
        download_video(pexels_key, data['keyword'], v_file)
        run_tts(data['text'], a_file, voice_role, speech_rate)
        
        try:
            # 1. 聲音處理
            a_clip = None
            try:
                if os.path.exists(a_file) and os.path.getsize(a_file) > 100:
                    a_clip = AudioFileClip(a_file)
            except:
                pass 
            
            # 2. 影片處理 (關鍵：使用較小的解析度)
            try:
                if os.path.exists(v_file) and os.path.getsize(v_file) > 1000:
                    # 縮小到 540x960，這會大幅減少記憶體消耗！
                    v_clip = VideoFileClip(v_file).resize(newsize=(VIDEO_W, VIDEO_H))
                else:
                    raise Exception("Video bad")
            except:
                dur = a_clip.duration if a_clip else 3
                v_clip = ColorClip(size=(VIDEO_W, VIDEO_H), color=(0,0,0), duration=dur)

            # 3. 合成與清理
            final_dur = a_clip.duration if a_clip else v_clip.duration
            
            # 確保不會過長
            if final_dur > 10: final_dur = 10 

            if v_clip.duration < final_dur:
                v_clip = v_clip.loop(duration=final_dur)
            else:
                v_clip = v_clip.subclip(0, final_dur)
            
            if a_clip:
                v_clip = v_clip.set_audio(a_clip)

            try:
                txt_img = create_text_image(data['text'], VIDEO_W, VIDEO_H)
                txt_clip = ImageClip(txt_img).set_duration(final_dur)
                clips.append(CompositeVideoClip([v_clip, txt_clip]))
            except:
                clips.append(v_clip)
            
            # 🧹【關鍵】強制回收記憶體，防止當機
            del v_clip
            del a_clip
            if 'txt_clip' in locals(): del txt_clip
            gc.collect() 
                
        except Exception as e:
            print(f"❌ Skip: {e}")
            continue
        
        progress_bar.progress((i + 1) / len(script_data))
    
    if clips:
        status.write("🎬 正在輕量合成...")
        try:
            # 使用 compose 方式合成，比較省記憶體
            final = concatenate_videoclips(clips, method="compose")
            output_name = f"result_{random.randint(1000,9999)}.mp4"
            # 使用 fast 預設，加快速度
            final.write_videofile(output_name, fps=24, codec='libx264', audio_codec='aac', preset='ultrafast')
            status.update(label="✨ 成功了！", state="complete")
            st.balloons()
            st.video(output_name)
        except Exception as e:
             st.error(f"合成失敗: {e}")
    else:
        status.update(label="❌ 失敗", state="error")