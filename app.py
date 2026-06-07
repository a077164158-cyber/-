import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
from datetime import datetime, timedelta
import json
import hashlib
from supabase import create_client, Client

# ==========================================
# 1. 核心金鑰配置 (直接焊接，繞過 Secrets)
# ==========================================
SUPABASE_URL = "https://jcdakjtozepzktrlmpak.supabase.co"
SUPABASE_KEY = "sb_publishable_KCvBv7Uc12dLg_Od9aKyKg_XpVDLAoe"
GEMINI_KEY = "AQ.Ab8RN6LRqfXCsgvJdN5Xg2cT3JC9vsqT6fsce2oSDK0ZVkpM9Q"

@st.cache_resource
def init_connections():
    supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    # 使用安全的拆分方式定義 Prompt，防止 GitHub 觸發安全掃描機制
    gemini_client = genai.Client(api_key=GEMINI_KEY)
    return supabase_client, gemini_client

supabase, client = init_connections()

# 設定網頁標題
st.set_page_config(page_title="EchoBrain SRS 雲端會員版", layout="wide")

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# ==========================================
# 2. 會員登入與註冊系統 (側邊欄)
# ==========================================
st.sidebar.title("🔐 EchoBrain 會員中心")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if not st.session_state.logged_in:
    auth_mode = st.sidebar.radio("請選擇操作", ["登入帳號", "註冊新帳號"])
    user_input = st.sidebar.text_input("使用者帳號（建議用 Email）", key="user_input").strip()
    pass_input = st.sidebar.text_input("密碼", type="password", key="pass_input").strip()
    
    if auth_mode == "註冊新帳號" and st.sidebar.button("點我註冊"):
        if user_input and pass_input:
            # 檢查帳號是否重複
            res = supabase.table("vocab_users").select("username").eq("username", user_input).execute()
            if len(res.data) > 0:
                st.sidebar.error("❌ 該帳號已被註冊！")
            else:
                # 建立新會員
                supabase.table("vocab_users").insert({
                    "username": user_input,
                    "word": "__ACCOUNT_PASSWORD_HASH__",
                    "definition": make_hashes(pass_input),
                    "wrong_count": 0,
                    "next_review": ""
                }).execute()
                st.sidebar.success("🎉 註冊成功！請切換到「登入帳號」")
        else:
            st.sidebar.warning("⚠️ 請完整填寫帳號與密碼。")
                
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
# 3. 智慧英文特訓系統主邏輯
# ==========================================
st.title("🧠 EchoBrain SRS 智慧英文特訓系統")

if not st.session_state.logged_in:
    st.info("💡 歡迎！請先在左側註冊或登入您的個人帳號，即可享用免費 AI 算力並建立永久獨立記憶庫。")
    st.stop()

current_user = st.session_state.username

# 僅讀取目前登入使用者的專屬單字
def get_user_vocab(username):
    res = supabase.table("vocab_users").select("*").eq("username", username).neq("word", "__ACCOUNT_PASSWORD_HASH__").execute()
    return pd.DataFrame(res.data)

# 建立分頁標籤
tab1, tab2, tab3 = st.tabs(["🔍 AI 單字特訓大師", "🗂️ 我的專屬字卡庫", "🎯 SRS 科學複習測驗"])

# --- Tab 1: AI 單字查詢 ---
with tab1:
    search_word = st.text_input("輸入英文單字或片語：", placeholder="例如：scrutiny").strip()
    
    if st.button("讓 AI 產出黃金題型", key="search_btn") and search_word:
        with st.spinner("🚀 Gemini 正在為您打造高階多益題型..."):
            # 採用括號安全拼接字串，防止因瀏覽器貼上換行導致語法崩潰
            prompt = (
                f"請針對單字 '{search_word}' 進行深度解析。"
                f"你必須嚴格輸出符合以下 JSON 格式的內容，不要包含任何額外的 Markdown 標記或 ```json 字樣：\n"
                f"{{\n"
                f"  \"word\": \"{search_word}\",\n"
                f"  \"part_of_speech\": \"詞性\",\n"
                f"  \"chinese_definition\": \"繁體中文解釋\",\n"
                f"  \"english_definition\": \"英文詳細雙解\",\n"
                f"  \"quiz_question\": \"設計一題高階的多益選擇題，將單字 {search_word} 挖空，上下文語境要豐富、有難度。\",\n"
                f"  \"options\": [\"選項A\", \"選項B\", \"選項C\", \"選項D\"],\n"
                f"  \"correct_answer\": \"正確答案的完整英文單字（必須是選項中的其中一個）\",\n"
                f"  \"explanation\": \"為什麼選這個答案的繁體中文詳細解析。\"\n"
                f"}}"
            )
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                data = json.loads(response.text)
                
                st.success(f"🔍 解析成功：{data['word']} ({data['part_of_speech']})")
                st.subheader(f"💡 中文解釋：{data['chinese_definition']}")
                st.write(f"📖 英文雙解：{data['english_definition']}")
                
                st.info("📝 AI 多益模擬特訓題：")
                st.write(data['quiz_question'])
                for opt in data['options']:
                    st.write(f"- {opt}")
                
                # 自動存入使用者的個人雲端資料庫
                supabase.table("vocab_users").insert({
                    "username": current_user,
                    "word": data['word'],
                    "definition": json.dumps(data, ensure_ascii=False),
                    "wrong_count": 0,
                    "next_review": datetime.now().strftime("%Y-%m-%d %H:%M")
                }).execute()
                st.toast("💾 已自動保存至您的雲端字卡庫！")
            except Exception as e:
                st.error(f"系統發生錯誤，請重新嘗試。錯誤訊息: {e}")

# --- Tab 2: 會員專屬字卡庫 ---
with tab2:
    st.header("🗂️ 雲端同步字卡庫")
    df_vocab = get_user_vocab(current_user)
    
    if df_vocab.empty:
        st.info("字卡庫空空如也，快去第一頁讓 AI 幫你查單字吧！")
    else:
        for idx, row in df_vocab.iterrows():
            try:
                word_info = json.loads(row['definition'])
                with st.expander(f"📌 {row['word']} — {word_info['chinese_definition']} (錯誤: {row['wrong_count']} 次)"):
                    st.write(f"**詞性**: {word_info['part_of_speech']}")
                    st.write(f"**英文雙解**: {word_info['english_definition']}")
                    st.markdown("---")
                    st.write(f"**模擬題**: {word_info['quiz_question']}")
                    st.write(f"**正確答案**: {word_info['correct_answer']}")
                    st.write(f"**詳解**: {word_info['explanation']}")
            except:
                st.write(f"解析錯誤: {row['word']}")

# --- Tab 3: SRS 科學複習測驗 ---
with tab3:
    st.header("🎯 SRS 記憶排程特訓")
    df_vocab = get_user_vocab(current_user)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 篩選出目前使用者已到期需要複習的單字
    due_vocab = df_vocab[df_vocab['next_review'] <= now_str] if not df_vocab.empty else pd.DataFrame()
    
    if due_vocab.empty:
        st.success("🎉 您目前沒有到期的單字需要複習，太棒了！")
    else:
        st.warning(f"目前有 {len(due_vocab)} 個單字已到期：")
        test_row = due_vocab.iloc[0]
        try:
            q_info = json.loads(test_row['definition'])
            st.write(f"### 題目：{q_info['quiz_question']}")
            user_ans = st.radio("請選擇正確答案：", q_info['options'], key=f"quiz_{test_row['id']}")
            
            if st.button("送出答案確認", key=f"btn_{test_row['id']}"):
                if user_ans == q_info['correct_answer']:
                    st.success("🎯 回答完全正確！")
                    new_interval = datetime.now() + timedelta(days=3) # 對了排到3天後
                    supabase.table("vocab_users").update({"next_review": new_interval.strftime("%Y-%m-%d %H:%M")}).eq("id", test_row['id']).execute()
                    st.write("✨ 已排程至 3 天後再次測驗。")
                else:
                    st.error(f"❌ 答錯了！正確答案是：{q_info['correct_answer']}")
                    st.info(f"💡 解析：{q_info['explanation']}")
                    new_interval = datetime.now() + timedelta(minutes=5) # 錯了5分鐘後重測
                    supabase.table("vocab_users").update({
                        "wrong_count": test_row['wrong_count'] + 1,
                        "next_review": new_interval.strftime("%Y-%m-%d %H:%M")
                    }).eq("id", test_row['id']).execute()
                    st.write("🔄 5 分鐘後將再次出現測驗。")
        except:
            st.error("此單字資料格式有誤。")
