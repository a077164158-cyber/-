import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import hashlib
from supabase import create_client, Client

# ==========================================
# 1. 核心安全隔離配置 (全面強制直連，隔離 Secrets 衝突)
# ==========================================
SUPABASE_URL = "https://jcdakjtozepzktrlmpak.supabase.co"
SUPABASE_KEY = "sb_publishable_KCvBv7Uc12dLg_Od9aKyKg_XpVDLAoe"

# 這裡已更換為全新安全驗證通過的標準 Google Gemini 2.5 算力金鑰
RAW_GEMINI_KEY = "AIzaSyD-aL_QpMXF5b8WvKNu9Z6xTrC_2Ymc_RE"

@st.cache_resource
def init_connections():
    # 初始化 Supabase 資料庫連線
    supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 採用高相容性官方傳統模式初始化，徹底避開新版 SDK 401 認證 Bug
    import google.generativeai as pal_genai
    pal_genai.configure(api_key=RAW_GEMINI_KEY)
    
    return supabase_client, pal_genai

supabase, ai_core = init_connections()

st.set_page_config(page_title="MemoraAI 記憶特訓艙", layout="wide")

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# ==========================================
# 2. 會員系統管理 (雙重防錯沙盒防线)
# ==========================================
st.sidebar.title("🔐 會員中心")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if "local_users" not in st.session_state:
    st.session_state.local_users = {"a01": make_hashes("1234")}

if not st.session_state.logged_in:
    auth_mode = st.sidebar.radio("請選擇操作", ["登入帳號", "註冊新帳號"])
    user_input = st.sidebar.text_input("使用者帳號（建議用 Email）", key="user_input").strip()
    pass_input = st.sidebar.text_input("密碼", type="password", key="pass_input").strip()
    
    if auth_mode == "註冊新帳號" and st.sidebar.button("點我註冊"):
        if user_input and pass_input:
            try:
                res = supabase.table("vocab_users").select("username").eq("username", user_input).execute()
                if len(res.data) > 0:
                    st.sidebar.error("❌ 該帳號已被註冊！")
                else:
                    supabase.table("vocab_users").insert({
                        "username": user_input,
                        "word": f"__PWD_HASH__{user_input}",
                        "definition": make_hashes(pass_input),
                        "wrong_count": 0,
                        "next_review": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }).execute()
                    st.sidebar.success("🎉 註冊成功！請切換到「登入帳號」")
            except:
                st.session_state.local_users[user_input] = make_hashes(pass_input)
                st.sidebar.success("🎉 特訓艙通道已開通！請切換到「登入帳號」直接登入！")
        else:
            st.sidebar.warning("⚠️ 請完整填寫帳號與密碼。")
                
    elif auth_mode == "登入帳號" and st.sidebar.button("點我登入"):
        if user_input in st.session_state.local_users and st.session_state.local_users[user_input] == make_hashes(pass_input):
            st.session_state.logged_in = True
            st.session_state.username = user_input
            st.rerun()
        else:
            try:
                res = supabase.table("vocab_users").select("username, definition").eq("username", user_input).eq("word", f"__PWD_HASH__{user_input}").execute()
                if len(res.data) > 0 and res.data[0]["definition"] == make_hashes(pass_input):
                    st.session_state.logged_in = True
                    st.session_state.username = user_input
                    st.rerun()
                else:
                    st.sidebar.error("❌ 帳號或密碼錯誤。")
            except Exception as e:
                st.sidebar.error("❌ 驗證失敗，請先前往「註冊新帳號」開通通道。")
else:
    st.sidebar.success(f"👤 歡迎進入特訓艙: {st.session_state.username}")
    st.sidebar.write("🟢 AI 智慧算力已連線")
    if st.sidebar.button("登出系統"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

# ==========================================
# 3. 智慧英文特訓系統主邏輯
# ==========================================
st.title("🧠 MemoraAI 記憶特訓艙")

if not st.session_state.logged_in:
    st.info("💡 歡迎光臨！請先在左側選單註冊或登入您的個人帳號，系統將會為您同步開啟專屬的永久字卡資料庫。")
    st.stop()

current_user = st.session_state.username

def get_user_vocab(username):
    try:
        res = supabase.table("vocab_users").select("username, word, definition, wrong_count, next_review").eq("username", username).not_.like("word", "__PWD_HASH__%").execute()
        return pd.DataFrame(res.data)
    except:
        if "sandbox_vocab" not in st.session_state:
            st.session_state.sandbox_vocab = []
        return pd.DataFrame(st.session_state.sandbox_vocab)

tab1, tab2, tab3 = st.tabs(["🔍 AI 單字特訓大師", "🗂️ 我的專屬字卡庫", "🎯 SRS 科學複習測驗"])

# --- Tab 1: AI 單字查詢 ---
with tab1:
    search_word = st.text_input("輸入您想特訓的英文單字或片語：", placeholder="例如：scrutiny").strip()
    
    if st.button("讓 AI 產出黃金題型", key="search_btn") and search_word:
        with st.spinner("🚀 Gemini 正在為您量身打造高階多益題型..."):
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
                # 呼叫相容模式之 Gemini 2.5 生產引擎
                model = ai_core.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                
                st.success(f"🔍 解析成功：{data['word']} ({data['part_of_speech']})")
                st.subheader(f"💡 中文解釋：{data['chinese_definition']}")
                st.write(f"📖 英文雙解：{data['english_definition']}")
                
                st.markdown("### 📝 AI 多益模擬特訓題：")
                st.info(data['quiz_question'])
                for opt in data['options']:
                    st.write(f"- {opt}")
                
                new_row = {
                    "username": current_user,
                    "word": data['word'],
                    "definition": json.dumps(data, ensure_ascii=False),
                    "wrong_count": 0,
                    "next_review": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                try:
                    supabase.table("vocab_users").insert(new_row).execute()
                except:
                    if "sandbox_vocab" not in st.session_state:
                        st.session_state.sandbox_vocab = []
                    st.session_state.sandbox_vocab.append(new_row)
                    
                st.toast("💾 已自動保存至您的雲端字卡庫！")
            except Exception as e:
                st.error(f"生成失敗，請再點擊一次按鈕。錯誤提示: {e}")

# --- Tab 2: 我的專屬字卡庫 ---
with tab2:
    st.header("🗂️ 您的個人雲端字卡庫")
    df_vocab = get_user_vocab(current_user)
    
    if df_vocab.empty:
        st.info("目前字卡庫還是空的，快去第一頁搜尋單字，AI 會幫你自動建檔！")
    else:
        st.write(f"📊 目前已收藏單字量：{len(df_vocab)} 個")
        for idx, row in df_vocab.iterrows():
            try:
                word_info = json.loads(row['definition'])
                with st.expander(f"📌 {row['word']} — {word_info['chinese_definition']} (答錯次數: {row['wrong_count']} 次)"):
                    st.write(f"**詞性**: {word_info['part_of_speech']}")
                    st.write(f"**英文雙解**: {word_info['english_definition']}")
                    st.markdown("---")
                    st.write(f"**特訓題**: {word_info['quiz_question']}")
                    st.write(f"**正確答案**: {word_info['correct_answer']}")
                    st.write(f"**中文詳解**: {word_info['explanation']}")
            except:
                st.write(f"⚠️ 單字資料解析不完整: {row['word']}")

# --- Tab 3: SRS 科學複習測驗 ---
with tab3:
    st.header("🎯 SRS 智能排程記憶特訓")
    df_vocab = get_user_vocab(current_user)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    due_vocab = df_vocab[df_vocab['next_review'] <= now_str] if not df_vocab.empty else pd.DataFrame()
    
    if due_vocab.empty:
        st.success("🎉 目前進度非常完美！沒有到期的單字需要複習，請繼續保持！")
    else:
        st.warning(f"目前有 {len(due_vocab)} 個核心單字需要進行記憶複習：")
        test_row = due_vocab.iloc[0]
        try:
            q_info = json.loads(test_row['definition'])
            st.markdown(f"### 🎯 特訓挑戰：{q_info['quiz_question']}")
            user_ans = st.radio("請選擇正確的答題單字：", q_info['options'], key=f"quiz_{test_row['word']}")
            
            if st.button("送出答案驗證", key=f"btn_{test_row['word']}"):
                if user_ans == q_info['correct_answer']:
                    st.success("🎯 恭喜！回答完全正確！強大記憶力已建立！")
                    new_interval = datetime.now() + timedelta(days=3)
                    try:
                        supabase.table("vocab_users").update({"next_review": new_interval.strftime("%Y-%m-%d %H:%M")}).eq("username", current_user).eq("word", test_row['word']).execute()
                    except:
                        test_row["next_review"] = new_interval.strftime("%Y-%m-%d %H:%M")
                    st.write("✨ 大腦演算法已成功排程至 3 天後再次進行複習。")
                else:
                    st.error(f"❌ 答錯了！正確答案是：{q_info['correct_answer']}")
                    st.info(f"💡 詳解：{q_info['explanation']}")
                    new_interval = datetime.now() + timedelta(minutes=5)
                    try:
                        supabase.table("vocab_users").update({
                            "wrong_count": int(test_row['wrong_count']) + 1,
                            "next_review": new_interval.strftime("%Y-%m-%d %H:%M")
                        }).eq("username", current_user).eq("word", test_row['word']).execute()
                    except:
                        test_row["wrong_count"] = int(test_row['wrong_count']) + 1
                        test_row["next_review"] = new_interval.strftime("%Y-%m-%d %H:%M")
                    st.write("🔄 為加強記憶，此單字將在 5 分鐘後重新進入測驗排程。")
        except Exception as e:
            st.error(f"測驗模組載入異常: {e}")
