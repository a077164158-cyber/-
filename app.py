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

@st.cache_resource
def init_connections():
    supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    gemini_client = genai.Client(api_key=GEMINI_KEY)
    return supabase_client, gemini_client

supabase, client = init_connections()

st.set_page_config(page_title="EchoBrain SRS 雲端會員版", layout="wide")

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# ==========================================
# 2. 會員系統 (側邊欄)
# ==========================================
st.sidebar.title("🔐 EchoBrain 會員中心")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if not st.session_state.logged_in:
    auth_mode = st.sidebar.radio("請選擇操作", ["登入帳號", "註冊新帳號"])
    user_input = st.sidebar.text_input("使用者帳號", key="user_input")
    pass_input = st.sidebar.text_input("密碼", type="password", key="pass_input")
    
    if auth_mode == "註冊新帳號" and st.sidebar.button("點我註冊"):
        if user_input and pass_input:
            res = supabase.table("vocab_users").select("username").eq("username", user_input).execute()
            if len(res.data) > 0:
                st.sidebar.error("❌ 該帳號已被註冊！")
            else:
                supabase.table("vocab_users").insert({
                    "username": user_input,
                    "word": "__ACCOUNT_PASSWORD_HASH__",
                    "definition": make_hashes(pass_input),
                    "wrong_count": 0,
                    "next_review": ""
                }).execute()
                st.sidebar.success("🎉 註冊成功！請切換到「登入帳號」")
        else:
            st.sidebar.warning("⚠️ 請填寫帳號與密碼。")
                
    elif auth_mode == "登入帳號" and st.sidebar.button("點我登入"):
        res = supabase.table("vocab_users").select("definition").eq("username", user_input).eq("word", "__ACCOUNT_PASSWORD_HASH__").execute()
        if len(res.data) > 0 and res.data[0]["definition"] == make_hashes(pass_input):
            st.session_state.logged_in = True
            st.session_state.username = user_input
            st.rerun()
        else:
            st.sidebar.error("❌ 帳號或密碼錯誤。")
else:
    st.sidebar.success(f"👤 已登入: {st.session_state.username}")
    st.sidebar.write("🟢 開發者公用算力已啟用")
    if st.sidebar.button("登出系統"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

# ==========================================
# 3. 主程式邏輯
# ==========================================
st.title("🧠 EchoBrain SRS 智慧英文特訓系統")

if not st.session_state.logged_in:
    st.info("💡 歡迎！請先在左側註冊或登入您的個人帳號，即可享用免費 AI 算力並建立永久單字庫。")
    st.stop()

current_user = st.session_state.username

def get_user_vocab(username):
    res = supabase.table("vocab_users").select("*").eq("username", username).neq("word", "__ACCOUNT_PASSWORD_HASH__").execute()
    return pd.DataFrame(res.data)

tab1, tab2, tab3 = st.tabs(["🔍 AI 單字特訓大師", "🗂️ 我的專屬字卡庫", "🎯 SRS 科學複習測驗"])

# --- Tab 1: AI 單字查詢 ---
with tab1:
    search_word = st.text_input("輸入英文單字或片語：", placeholder="例如：scrutiny").strip()
    
    if st.button("讓 AI 產出黃金題型", key="search_btn") and search_word:
        with st.spinner("🚀 Gemini 正在為您打造高階多益題型..."):
            prompt = f"請針對單字 '{search_word}' 解析。嚴格輸出 JSON 格式且勿包含 
http://googleusercontent.com/immersive_entry_chip/0

5. 貼上後，滑到最下方點擊綠色的 **`Commit changes...`** 存檔。

---

### 🏁 最後見證奇蹟的時刻：
存好檔後，回到你的 Streamlit 網頁。如果程式還沒反應過來，你可以一樣點開右下角的 **`Manage app` -> `...` -> `Reboot app`**。

重啟跑完後，黑色的錯誤畫面就會徹徹底底轉化為最完美的「**會員註冊登入系統**」！你和你的朋友就能開始瘋狂使用了！
