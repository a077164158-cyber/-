import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
from datetime import datetime, timedelta
import json
import hashlib
from supabase import create_client, Client

# ==========================================
# 1. 雲端保險箱 Secrets 讀取與安全性檢查
# ==========================================
if "supabase" not in st.secrets or "GEMINI_API_KEY" not in st.secrets:
    st.error("❌ 偵測到 Streamlit Secrets 尚未設定完成，請確認 SUPABASE 與 GEMINI_API_KEY 皆已填入。")
    st.stop()

SUPABASE_URL = st.secrets["supabase"]["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["supabase"]["SUPABASE_KEY"]
GEMINI_KEY = st.secrets["GEMINI_API_KEY"]

# 初始化 Supabase 與 Gemini 用戶端
@st.cache_resource
def init_connections():
    supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    gemini_client = genai.Client(api_key=GEMINI_KEY)
    return supabase_client, gemini_client

supabase, client = init_connections()

st.set_page_config(page_title="EchoBrain SRS 雲端會員版", layout="wide")

# ==========================================
# 2. 簡單雜湊密碼加密（保護會員個資）
# ==========================================
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# ==========================================
# 3. 會員註冊與登入系統 (側邊欄)
# ==========================================
st.sidebar.title("🔐 EchoBrain 會員中心")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if not st.session_state.logged_in:
    auth_mode = st.sidebar.radio("請選擇操作", ["登入帳號", "註冊新帳號"])
    user_input = st.sidebar.text_input("使用者帳號 (Email 或名稱)", key="user_input")
    pass_input = st.sidebar.text_input("密碼", type="password", key="pass_input")
    
    if auth_mode == "註冊新帳號":
        if st.sidebar.button("點我註冊"):
            if user_input and pass_input:
                # 檢查帳號是否被註冊過
                res = supabase.table("vocab_users").select("username").eq("username", user_input).execute()
                if len(res.data) > 0:
                    st.sidebar.error("❌ 該帳號已被註冊，請換一個！")
                else:
                    # 在雲端建立一筆初始隨便的單字當作帳號成立註記，或者直接寫入
                    hashed_pass = make_hashes(pass_input)
                    # 我們將帳密資訊安全地存放在特殊結構中，這裡利用一個特定單字儲存密碼雜湊
                    supabase.table("vocab_users").insert({
                        "username": user_input,
                        "word": "__ACCOUNT_PASSWORD_HASH__",
                        "definition": hashed_pass,
                        "wrong_count": 0,
                        "next_review": ""
                    }).execute()
                    st.sidebar.success("🎉 註冊成功！請切換到「登入帳號」登入。")
            else:
                st.sidebar.warning("⚠️ 請填寫完整的帳號與密碼。")
                
    elif auth_mode == "登入帳號":
        if st.sidebar.button("點我登入"):
            hashed_pass = make_hashes(pass_input)
            res = supabase.table("vocab_users").select("definition").eq("username", user_input).eq("word", "__ACCOUNT_PASSWORD_HASH__").execute()
            if len(res.data) > 0 and res.data[0]["definition"] == hashed_pass:
                st.session_state.logged_in = True
                st.session_state.username = user_input
                st.rerun()
            else:
                st.sidebar.error("❌ 帳號或密碼錯誤，請重新檢查。")
else:
    st.sidebar.success(st.session_state.username)
    st.sidebar.write("會員專屬算力：🟢 已啟用 (由開發者提供)")
    if st.sidebar.button("登出系統"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

# ==========================================
# 4. 主程式邏輯 (只有登入後才能看到內容)
# ==========================================
st.title("🧠 EchoBrain SRS 智慧英文特訓系統")

if not st.session_state.logged_in:
    st.info("💡 歡迎使用 EchoBrain！請先在左側側邊欄「註冊」或「登入」您的個人帳號，即可開始建立您專屬的永久單字庫。")
    st.stop()

current_user = st.session_state.username

# 定義從雲端抓取與儲存單字的函式
def get_user_vocab(username):
    res = supabase.table("vocab_users").select("*").eq("username", username).neq("word", "__ACCOUNT_PASSWORD_HASH__").execute()
    return pd.DataFrame(res.data)

def save_word_to_cloud(username, word, definition):
    supabase.table("vocab_users").insert({
        "username": username,
        "word": word,
        "definition": json.dumps(definition, ensure_ascii=False),
        "wrong_count": 0,
        "next_review": datetime.now().strftime("%Y-%m-%d %H:%M")
    }).execute()

# --- 分頁設計 ---
tab1, tab2, tab3 = st.tabs(["🔍 AI 單字特訓大師", "🗂️ 我的專屬字卡庫", "🎯 SRS 科學複習測驗"])

# --- Tab 1: AI 單字查詢 ---
with tab1:
    search_word = st.text_input("輸入你想特訓的英文單字或片語：", placeholder="例如：scrutiny").strip()
    
    if st.button("讓 AI 產出黃金題型", key="search_btn"):
        if search_word:
            with st.spinner("🚀 Gemini 正在為您量身打造最高階的多益/英檢特訓題型..."):
                prompt = f"""
                請針對英文單字或片語 "{search_word}" 進行深度解析。
                你必須嚴格輸出符合以下 JSON 格式的內容，不要包含任何額外的 Markdown 標記或 ```json 字樣：
                {{
                  "word": "{search_word}",
                  "part_of_speech": "詞性",
                  "chinese_definition": "精準的繁體中文解釋",
                  "english_definition": "英文詳細雙解",
                  "quiz_question": "設計一題高階的多益或英檢選擇題，將該單字挖空，上下文語境要豐富、有難度。",
                  "options":
