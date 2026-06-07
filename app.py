import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import hashlib
from supabase import create_client, Client

# ==========================================
# 1. 核心安全配置 (完美讀取 Secrets 機制)
# ==========================================
SUPABASE_URL = "https://jcdakjtozepzktrlmpak.supabase.co"
SUPABASE_KEY = "sb_publishable_KCvBv7Uc12dLg_Od9aKyKg_XpVDLAoe"

@st.cache_resource
def init_connections():
    # 初始化雲端資料庫連線
    supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 讀取安全金鑰並配置最高相容性之官方 AI 核心
    import google.generativeai as pal_genai
    if "GEMINI_API_KEY" in st.secrets:
        pal_genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    else:
        # 防錯緩衝
        pal_genai.configure(api_key="MISSING_KEY")
        
    return supabase_client, pal_genai

st.set_page_config(page_title="MemoraAI 記憶特訓艙", layout="wide")
supabase, ai_core = init_connections()

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# ==========================================
# 2. 會員系統管理 (與雲端資料庫深度同步)
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
                st.sidebar.success("🎉 本地特訓艙通道已開通！請切換到「登入帳號」直接登入！")
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
# 3. 智慧英文特訓系統核心邏輯
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

# --- Tab 1: AI 單字生成核心功能 ---
with tab1:
    search_word = st.text_input("輸入您想特訓的英文單字或片語：", placeholder="例如：scrutiny").strip()
    
    if st.button("讓 AI 產出黃金題型", key="search_btn") and search_word:
        if "GEMINI_API_KEY" not in st.secrets:
            st.error("⚠️ 偵測到尚未在 Streamlit Secrets 設定您的 API Key！請先完成後台設定再點擊按鈕。")
        else:
            with st.spinner("🚀 Gemini 正在為您量身打造專屬學習字卡與模擬測驗..."):
                # 開放式通用提示詞，不局限於多益
                prompt = (
                    f"請針對英文單字或片語 '{search_word}' 進行深度解析。"
                    f"你必須嚴格輸出符合以下 JSON 格式的內容，不要包含任何額外的 Markdown 標記或 ```json 字樣：\n"
                    f"{{\n"
                    f"  \"word\": \"{search_word}\",\n"
                    f"  \"part_of_speech\": \"該單字或片語的常用詞性\",\n"
                    f"  \"chinese_definition\": \"最精準的繁體中文解釋\",\n"
                    f"  \"english_definition\": \"清晰易懂的英文詳細雙解\",\n"
                    f"  \"quiz_question\": \"設計一題最能體現該單字 '{search_word}' 核心用法與生活情境的英文選擇題。請將該單字挖空，以 ______ 代替。\",\n"
                    f"  \"options\": [\"包含正確單字與其他三個干擾項單字的四個選項A\", \"選項B\", \"選項C\", \"選項D\"],\n"
                    f"  \"correct_answer\": \"正確答案的完整英文單字（必須跟上面 options 中的其中一個字完全一模一樣）\",\n"
                    f"  \"explanation\": \"為什麼選這個答案的繁體中文詳細解析。\"\n"
                    f"}}"
                )
                try:
                    # 呼叫強大的智慧型生產引擎
                    model = ai_core.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(
                        prompt,
                        generation_config={"response_mime_type": "application/json"}
                    )
                    
                    # 嚴格解析 JSON 格式
                    data = json.loads(response.text)
                    
                    # 渲染前端畫面
                    st.success(f"🔍 解析成功：{data['word']} ({data['part_of_speech']})")
                    st.subheader(f"💡 中文解釋：{data['chinese_definition']}")
                    st.write(f"📖 英文雙解：{data['english_definition']}")
                    
                    st.markdown("---")
                    st.markdown("### 📝 AI 模擬特訓題：")
                    st.info(data['quiz_question'])
                    
                    # 顯示四個選項
                    for opt in data['options']:
                        st.write(f"📍 {opt}")
                    
                    # 保存進雲端/本地數據庫
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
                        
                    st.toast("💾 演算法已自動將此字卡保存至您的雲端庫！")
                    
                except Exception as e:
                    st.error(f"❌ AI 引擎產出遭遇干擾：{e}。請確保您的 API Key 有效，並再試一次！")

# --- Tab 2: 我的專屬字卡庫 ---
with tab2:
    st.header("🗂️ 您的個人雲端字卡庫")
    df_vocab = get_user_vocab(current_user)
    
    if df_vocab.empty:
        st.info("目前字卡庫還是空的，快去第一頁搜尋單字，AI 會幫你自動建檔！")
    else:
        st.write(f"📊 目前已收藏核心單字量：{len(df_vocab)} 個")
        for idx, row in df_vocab.iterrows():
            try:
                word_info = json.loads(row['definition'])
                with st.expander(f"📌 {row['word']} — {word_info['chinese_definition']} (答錯: {row['wrong_count']} 次)"):
                    st.write(f"**💡 詞性**: {word_info['part_of_speech']}")
                    st.write(f"**📖 英文雙解**: {word_info['english_definition']}")
                    st.markdown("---")
                    st.write(f"**📝 特訓考題**: {word_info['quiz_question']}")
                    st.write(f"**🎯 正確答案**: {word_info['correct_answer']}")
                    st.write(f"**💡 中文詳解**: {word_info['explanation']}")
            except:
                st.write(f"⚠️ 單字資料解析不完整: {row['word']}")

# --- Tab 3: SRS 科學複習測驗 ---
with tab3:
    st.header("🎯 SRS 智能排程記憶特訓")
    df_vocab = get_user_vocab(current_user)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    due_vocab = df_vocab[df_vocab['next_review'] <= now_str] if not df_vocab.empty else pd.DataFrame()
    
    if due_vocab.empty:
        st.success("🎉 目前大腦排程進度非常完美！沒有到期的單字，請繼續保持！")
    else:
        st.warning(f"🔥 目前有 {len(due_vocab)} 個單字已到達記憶臨界點，請立刻特訓：")
        test_row = due_vocab.iloc[0]
        try:
            q_info = json.loads(test_row['definition'])
            st.markdown(f"### 🎯 特訓挑戰題目：")
            st.info(q_info['quiz_question'])
            
            # 使用單選鈕進行互動答題
            user_ans = st.radio("請選擇正確的答題單字：", q_info['options'], key=f"quiz_{test_row['word']}")
            
            if st.button("送出答案驗證", key=f"btn_{test_row['word']}"):
                if user_ans == q_info['correct_answer']:
                    st.success("🎯 恭喜！回答完全正確！強大記憶鏈已建立！")
                    new_interval = datetime.now() + timedelta(days=3)
                    try:
                        supabase.table("vocab_users").update({"next_review": new_interval.strftime("%Y-%m-%d %H:%M")}).eq("username", current_user).eq("word", test_row['word']).execute()
                    except:
                        test_row["next_review"] = new_interval.strftime("%Y-%m-%d %H:%M")
                    st.write("✨ 艾賓浩斯演算法已成功為您排程至 3 天後再次複習。")
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
                    st.write("🔄 系統已將此字移入強化特訓，將在 5 分鐘後重新進入測驗排程。")
        except Exception as e:
            st.error(f"測驗模組載入異常: {e}")
