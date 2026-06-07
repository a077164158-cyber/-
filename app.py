import streamlit as st
import sqlite3
import json
import time
import requests
import random
from google import genai
from google.genai import types

# ==========================================
# 0. 系統基礎配置與初始化
# ==========================================
st.set_page_config(page_title="EchoBrain SRS 核心系統", layout="wide", initial_sidebar_state="expanded")

# 🌟 管理員公用 API 金鑰設定（⚠️ 請務必在此處替換為您的真實 Gemini 金鑰，否則會出現 401 錯誤）
BACKEND_GEMINI_KEY = "AQ.Ab8RN6Lauqruyzzq71MnPmyU5rWY2ruoZWKzN-ETUvjvgyVggA"

# 👑 指定管理員帳密配置
ADMIN_EMAIL = "a23623020428@gmail.com"
ADMIN_PASSWORD = "8642158a"

# 初始化 Session State
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "current_test" not in st.session_state:
    st.session_state.current_test = {}
if "scrambled_order" not in st.session_state:
    st.session_state.scrambled_order = []
if "user_reorder" not in st.session_state:
    st.session_state.user_reorder = []

# SQLite 局部資料庫初始化（修正資料表不一致導致的 OperationalError）
def init_db():
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    
    # 建立全新的單字主表與用戶管理表結構
    c.execute('''CREATE TABLE IF NOT EXISTS vocab (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    word TEXT,
                    definition TEXT,
                    grammar TEXT,
                    mnemonic TEXT,
                    confusable TEXT,
                    sentences TEXT,
                    next_review_date TEXT,
                    streak INTEGER,
                    error_count INTEGER,
                    quiz_data TEXT
                )''')
                
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE,
                    password TEXT,
                    credits INTEGER DEFAULT 10
                )''')
                
    # 🔄 【Bug 修正核心】：安全結構校驗驗證，防止舊環境中殘留的損壞欄位導致崩潰
    try:
        # 測試 users 表是否支援現有欄位
        c.execute("SELECT id, email, password, credits FROM users LIMIT 1")
    except sqlite3.OperationalError:
        # 如果欄位不相符或缺少，直接重建 users 表以維持結構純淨
        c.execute("DROP TABLE IF EXISTS users")
        c.execute('''CREATE TABLE users (
                        id TEXT PRIMARY KEY,
                        email TEXT UNIQUE,
                        password TEXT,
                        credits INTEGER DEFAULT 10
                    )''')
                    
    try:
        # 測試 vocab 表是否支援現有欄位
        c.execute("SELECT id, user_id, word, definition, grammar, mnemonic, confusable, sentences, next_review_date, streak, error_count, quiz_data FROM vocab LIMIT 1")
    except sqlite3.OperationalError:
        # 如果欄位不相符或缺少，直接重建 vocab 表以維持結構純淨
        c.execute("DROP TABLE IF EXISTS vocab")
        c.execute('''CREATE TABLE vocab (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        word TEXT,
                        definition TEXT,
                        grammar TEXT,
                        mnemonic TEXT,
                        confusable TEXT,
                        sentences TEXT,
                        next_review_date TEXT,
                        streak INTEGER,
                        error_count INTEGER,
                        quiz_data TEXT
                    )''')
                
    # 自動插入管理員帳號至本地資料庫，確保資料一致性
    c.execute("INSERT OR REPLACE INTO users (id, email, password, credits) VALUES (?, ?, ?, ?)",
              ("admin_root", ADMIN_EMAIL, ADMIN_PASSWORD, 999999))
              
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 0.5 點數與用戶管理核心函數 (SQLite 實作)
# ==========================================
def get_user_credits(user_id):
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE id=?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 0

def deduct_credit(user_id):
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("UPDATE users SET credits = max(0, credits - 1) WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

# Supabase 模擬串接端點（與本地 SQLite 同步，確保後台管理看得到）
def supabase_signup(email, password):
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    try:
        mock_id = f"user_{int(time.time())}"
        c.execute("INSERT INTO users (id, email, password, credits) VALUES (?, ?, ?, ?)", (mock_id, email, password, 10)) # 新人送 10 點
        conn.commit()
        conn.close()
        return {"user": {"id": mock_id, "email": email}}, 200
    except sqlite3.IntegrityError:
        conn.close()
        return {"error": "帳號已存在"}, 400

def supabase_signin(email, password):
    # 先做管理員特判
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        return {"user": {"id": "admin_root", "email": ADMIN_EMAIL}, "access_token": "admin_token"}, 200
        
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("SELECT id, email FROM users WHERE email=? AND password=?", (email, password))
    res = c.fetchone()
    conn.close()
    if res:
        return {"user": {"id": res[0], "email": res[1]}, "access_token": "mock_token"}, 200
    else:
        return {"error": "密碼錯誤"}, 400

# ==========================================
# 1. 輔助功能（TTS 語音播放）
# ==========================================
def tts_button(word, label="🔊 發音聆聽"):
    html_code = f"""
    <button onclick="window.speechSynthesis.speak(new SpeechSynthesisUtterance('{word}'))" 
    style="background-color: #2E7D32; color: white; border: none; padding: 6px 12px; 
    text-align: center; font-size: 13px; cursor: pointer; border-radius: 4px; margin: 2px;">
    {label}
    </button>
    """
    st.components.v1.html(html_code, height=45)

def get_all_words(user_id):
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("SELECT word, definition, grammar, mnemonic, confusable, sentences, next_review_date, streak, error_count, quiz_data, id FROM vocab WHERE user_id=? ORDER BY id DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# ==========================================
# 2. Gemini AI 多維度核心資料打包生成
# ==========================================
def fetch_gemini_learning_package(word, api_key):
    word = word.strip().lower()
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    你是一位精通台灣繁體中文的頂尖英文權威教授。請為單字 "{word}" 建立一個全方位的語言學習字卡大禮包。
    你必須嚴格遵循 JSON 格式返回數據，絕對不能包含 any 額外的 Markdown 標籤（如 ```json）。
    
    JSON 格式規範如下：
    {{
      "definition": "繁體中文核心釋義 (與括號英文詳細定義)",
      "grammar": "【1. 詞性與搭配公式】\\n• 詳細拆解該字常見的介系詞搭配。\\n【2. 核心文法句型】\\n• 寫出標準的文法結構句型公式。",
      "mnemonic": "【🎯 真實諧音聯想與口訣】\\n• 根據該字的英文發音，發想一個幽默、好記且與字義完美結合的台灣華語諧音口訣與畫面情境。",
      "confusable": "【⚠️ 易混淆單字精準辨析】\\n• 找出1個與該字字形或字義最易搞混的高頻單字進行對比辨析與例句。",
      "sentences": "第一句高階商務或生活英文例句||💡 中文翻譯###第二句高階商務或生活英文例句||💡 中文翻譯",
      
      "phrase_q": "考驗片語/介系詞搭配的句子，將關鍵介系詞挖空，空格請用 _______ 代替。",
      "phrase_options": ["正確介系詞", "干擾介系詞1", "干擾介系詞2", "干擾介系詞3"],
      "phrase_ans": "正確介系詞",
      
      "grammar_hint": "提示該字在此處應使用的衍生詞性（例如：動詞、名詞、形容詞、副詞或時態變化）",
      "grammar_q": "一個精準的文法填充題句子，空格用 ________ 代替。要求填入該字的『詞性衍生變形（如名詞形、形容詞形、副詞形）』或『特定時態/語態（如過去分詞）』。",
      "grammar_ans": "該單字對應句子語法的正確衍生變形單字（例如：單字是 vulnerable，答案可能是 vulnerability）",
      
      "cloze_q": "一段包含2-3個句子的完整情境短文克漏字，將本字挖空寫成 [  ]。",
      "cloze_options": ["本字原形", "干擾字1", "干擾字2", "干擾字3"],
      "cloze_ans": "本字原形",
      
      "scrambled_sentence": "一句使用到本字、長度在 5-8 個單字之間的精簡實用英文句子。",
      "scrambled_translation": "該重組句子的中文翻譯"
    }}
    """
    
    max_retries = 3
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                ),
            )
            res_text = response.text.strip()
            return json.loads(res_text)
        except Exception as e:
            if "503" in str(e) and attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            st.error(f"Gemini AI 核心生成失敗，請檢查管理員後台的 API Key 是否設定正確。錯誤訊息: {e}")
            return None

# ==========================================
# 3. 系統安全門禁中心（自動過濾前後空白）
# ==========================================
if not st.session_state.logged_in:
    st.title("🧠 EchoBrain SRS 系統門禁安全中心")
    st.markdown("歡迎使用全維度大腦記憶特訓系統！請登入或註冊您的會員帳號以開始使用。")
    
    tab1, tab2 = st.tabs(["🔐 會員登入", "📝 新用戶註冊"])
    
    with tab1:
        st.subheader("登入帳號")
        login_email = st.text_input("電子郵件 (Email)", key="login_email_input")
        login_pwd = st.text_input("密碼 (Password)", type="password", key="login_pwd_input")
        if st.button("確認登入", key="btn_signin"):
            clean_login_email = login_email.strip() if login_email else ""
            if clean_login_email and login_pwd:
                with st.spinner("安全驗證中..."):
                    res, code = supabase_signin(clean_login_email, login_pwd)
                if code == 200 or "access_token" in res:
                    st.session_state.logged_in = True
                    st.session_state.user_id = res["user"]["id"]
                    st.session_state.user_email = res["user"]["email"]
                    st.success(f"🎉 登入成功！歡迎回來 {st.session_state.user_email}")
                    st.rerun()
                else:
                    st.error("❌ 登入失敗：帳號或密碼錯誤。")
            else:
                st.warning("請填寫所有欄位。")
                
    with tab2:
        st.subheader("免費註冊新帳號")
        reg_email = st.text_input("設定電子郵件 (Email)", key="reg_email_input")
        reg_pwd = st.text_input("設定密碼 (至少 6 位字元)", type="password", key="reg_pwd_input")
        if st.button("註冊帳戶", key="btn_signup"):
            clean_email = reg_email.strip() if reg_email else ""
            if clean_email and reg_pwd:
                with st.spinner("正在向雲端安全性註冊..."):
                    res, code = supabase_signup(clean_email, reg_pwd)
                if code == 200:
                    st.success("🎉 註冊成功！您現在可以切換至「會員登入」分頁進入系統（系統已贈送您 10 點體驗點數！）。")
                else:
                    st.error(f"❌ 註冊失敗：{res.get('error', '格式錯誤')}")
            else:
                st.warning("請填寫所有欄位。")
    st.stop()

# ==========================================
# 4. 後台系統主介面
# ==========================================
st.sidebar.title("🧠 EchoBrain SRS")

# 檢查目前登入的是否為系統最高管理員
is_admin = (st.session_state.user_email == ADMIN_EMAIL)

if is_admin:
    st.sidebar.markdown("### 👑 權限：系統最高管理員")
else:
    st.sidebar.markdown("### 👤 權限：正式會員")

st.sidebar.write(f"📧 帳號: {st.session_state.user_email}")

# 即時顯示剩餘點數
current_credits = get_user_credits(st.session_state.user_id)
st.sidebar.metric(label="💰 您的剩餘特訓點數", value=f"{current_credits} 點")

if st.sidebar.button("登出系統"):
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.user_email = None
    st.rerun()

# 根據身分決定要產生哪些 Tabs 分頁
tabs_list = ["📥 數據匯入中心", "🗂️ 字彙記憶庫", "⚔️ 七大維度特訓魔鬼測驗"]
if is_admin:
    tabs_list.append("⚙️ 👑 核心管理員後台")

main_tabs = st.tabs(tabs_list)

# ------------------------------------------
# 分頁 1: 數據匯入中心 (導入點數扣除機制)
# ------------------------------------------
with main_tabs[0]:
    st.header("📥 AI 數據打包匯入中心")
    st.write("輸入你想要特訓的英文單字，Gemini AI 將為你全自動生成包含 7 大題型與文法聯想的 SRS 學習字卡。")
    st.info("💡 系統規定：每成功查詢打包一個單字，將扣除 1 點特訓點數。")
    
    input_word = st.text_input("請輸入英文字彙 (例如: vulnerable, alternative)", key="import_word_input")
    if st.button("啟動 Gemini AI 數據打包匯入", key="btn_import"):
        if BACKEND_GEMINI_KEY == "你的_GEMINI_API_KEY_請在此處替換" or not BACKEND_GEMINI_KEY:
            st.error("系統配置錯誤：管理員後台未設定有效的 BACKEND_GEMINI_KEY。")
        elif not input_word.strip():
            st.warning("請輸入有效的單字。")
        elif current_credits < 1:
            st.error("❌ 您的特訓點數不足（剩餘 0 點）！無法查詢新單字。請聯絡管理員幫您儲值點數。")
        else:
            with st.spinner("Gemini AI 正在全維度解構字彙、編寫魔鬼測驗題型..."):
                pkg = fetch_gemini_learning_package(input_word, BACKEND_GEMINI_KEY)
                if pkg:
                    # 扣除點數 (管理員免扣除或照扣，這裡設計一般用戶扣點)
                    if not is_admin:
                        deduct_credit(st.session_state.user_id)
                    
                    # 存入本機 SQLite 資料庫
                    conn = sqlite3.connect('anki_vocab.db')
                    c = conn.cursor()
                    # 檢查是否已存在
                    c.execute("SELECT id FROM vocab WHERE user_id=? AND word=?", (st.session_state.user_id, input_word.strip().lower()))
                    exist = c.fetchone()
                    
                    quiz_data_str = json.dumps(pkg, ensure_ascii=False)
                    today_str = time.strftime("%Y-%m-%d")
                    
                    if exist:
                        c.execute("""UPDATE vocab SET definition=?, grammar=?, mnemonic=?, confusable=?, sentences=?, next_review_date=?, quiz_data=? 
                                     WHERE id=?""", 
                                  (pkg['definition'], pkg['grammar'], pkg['mnemonic'], pkg['confusable'], pkg['sentences'], today_str, quiz_data_str, exist[0]))
                        st.success(f"♻️ 單字「{input_word}」已存在，AI 測驗題型數據已更新！(已扣除 1 點，剩餘 {get_user_credits(st.session_state.user_id)} 點)")
                    else:
                        c.execute("""INSERT INTO vocab (user_id, word, definition, grammar, mnemonic, confusable, sentences, next_review_date, streak, error_count, quiz_data) 
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)""",
                                  (st.session_state.user_id, input_word.strip().lower(), pkg['definition'], pkg['grammar'], pkg['mnemonic'], pkg['confusable'], pkg['sentences'], today_str, quiz_data_str))
                        st.success(f"🎉 成功！單字「{input_word}」已成功匯入記憶庫！(已扣除 1 點，剩餘 {get_user_credits(st.session_state.user_id)} 點)")
                    conn.commit()
                    conn.close()
                    time.sleep(1)
                    st.rerun()

# ------------------------------------------
# 分頁 2: 字彙記憶庫
# ------------------------------------------
with main_tabs[1]:
    st.header("🗂️ 智能字彙記憶庫")
    st.write("檢視您目前擁有的所有特訓單字。支援關鍵字即時篩選、詳細智能字卡解構、以及「多向配對連連看」暖身遊戲。")
    
    all_words = get_all_words(st.session_state.user_id)
    
    if not all_words:
        st.info("您的記憶庫目前空空如也，請先前往「📥 數據匯入中心」匯入第一個單字吧！")
    else:
        search_query = st.text_input("🔍 搜尋字彙庫內容 (輸入英文單字或中文核心釋義關鍵字)", "").strip().lower()
        filtered_words = [w for w in all_words if search_query in w[0] or search_query in w[1]]
        
        st.markdown("---")
        with st.expander("🎲 每日測驗前哨站：核心定義「多向連連看」暖身配對賽"):
            st.write("系統會隨機抽取記憶庫中的 3 個單字，請嘗試在下拉選單中找出各自正確的中文含意！")
            game_pool = random.sample(all_words, min(3, len(all_words)))
            
            all_defs = [w[1] for w in game_pool]
            random.shuffle(all_defs)
            
            correct_count = 0
            for item in game_pool:
                w_word = item[0]
                w_real_def = item[1]
                user_ans = st.selectbox(f"單字【 {w_word} 】對應的中文核心釋義是？", ["-- 請選擇 --"] + all_defs, key=f"match_{w_word}")
                if user_ans == w_real_def:
                    correct_count += 1
            if correct_count == len(game_pool) and len(game_pool) > 0:
                st.success("🎯 太厲害了！連連看全部配對正確！大腦記憶已成功喚醒，您可以前往第三分頁挑戰魔鬼測驗了！")
        st.markdown("---")
        
        st.subheader(f"📊 目前已收錄字卡共計 {len(filtered_words)} 筆")
        for w in filtered_words:
            w_word, w_def, w_gram, w_mne, w_conf, w_sent, w_date, w_streak, w_err, _, w_id = w
            
            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 5, 2])
                with col1:
                    st.subheader(f"🔤 {w_word}")
                    st.caption(f"📅 下期複習: {w_date} | 🔥 記憶鏈: {w_streak} | ❌ 錯誤次數: {w_err}")
                    tts_button(w_word, label="🔊 聽發音")
                with col2:
                    st.markdown(f"**核心釋義：** {w_def}")
                    with st.expander("🔍 檢視完整大腦解構（文法公式、諧音聯想與易混淆字）"):
                        st.markdown(f"### 📋 文法搭配公式\n{w_gram}")
                        st.markdown(f"### 🎯 諧音口訣記憶\n{w_mne}")
                        st.markdown(f"### ⚠️ 易混淆單字精準辨析\n{w_conf}")
                        st.markdown("### 🎬 高階實戰商務例句")
                        for s in w_sent.split("###"):
                            if "||" in s:
                                en, tw = s.split("||")
                                st.markdown(f"• **{en}**")
                                st.markdown(f"  *{tw}*")
                with col3:
                    if st.button("🗑️ 刪除字卡", key=f"del_{w_id}"):
                        conn = sqlite3.connect('anki_vocab.db')
                        c = conn.cursor()
                        c.execute("DELETE FROM vocab WHERE id=?", (w_id,))
                        conn.commit()
                        conn.close()
                        st.toast(f"已從記憶庫中移除單字 {w_word}")
                        time.sleep(0.5)
                        st.rerun()

# ------------------------------------------
# 分頁 3: 七大維度特訓魔鬼測驗
# ------------------------------------------
with main_tabs[2]:
    st.header("⚔️ 七大維度特訓魔鬼測驗")
    st.write("融合七大核心科學題型：拼寫填充、片語下拉、語法手動填充、克漏字、語音聽寫、整句重組、連連看（已在記憶庫提供）。")
    
    all_quiz_words = [w for w in get_all_words(st.session_state.user_id) if w[9]]
    
    if not all_quiz_words:
        st.info("尚未有任何包含 AI 測驗數據的單字，請先至數據匯入中心打包單字。")
    else:
        quiz_word_options = [w[0] for w in all_quiz_words]
        selected_quiz_word = st.selectbox("🎯 請選擇您目前想要深度淬鍊的特訓單字：", quiz_word_options, key="select_quiz_word_main")
        
        target_word_record = [w for w in all_quiz_words if w[0] == selected_quiz_word][0]
        w_id = target_word_record[10]
        q_data = json.loads(target_word_record[9])
        
        st.markdown(f"### 🔏 當前淬鍊單字：**{selected_quiz_word.upper()}**")
        
        t1, t2, t3, t4, t5, t6 = st.tabs([
            "1. 核心字彙拼寫題", "2. 片語搭配下拉題", "3. 語法結構手動填充題", 
            "4. 情境克漏字選擇題", "5. 語音反向聽寫盲聽題", "6. 國際檢定整句重組題"
        ])
        
        with t1:
            st.markdown("#### 🎯 階段一：大腦主動檢索 - 核心字彙拼寫")
            st.markdown(f"**提示（核心釋義）：** {target_word_record[1]}")
            ans_1 = st.text_input(f"請拼寫出符合定義的英文單字 (開頭第一個字母為 {selected_quiz_word[0]}):", key=f"q1_{selected_quiz_word}").strip().lower()
            if st.button("提交答案", key=f"btn1_{selected_quiz_word}"):
                if ans_1 == selected_quiz_word:
                    st.success("🎯 答對了！記憶突觸完全契合！")
                else:
                    st.error(f"❌ 拼寫錯誤，再想一想！提示：長度為 {len(selected_quiz_word)} 個字母。")
                    
        with t2:
            st.markdown("#### 🧩 階段二：習慣用語制約 - 核心片語/介系詞下拉選單題")
            st.info(f"📋 **題目句子：**\n{q_data.get('phrase_q', '_______')}")
            options_2 = ["-- 請選擇填入空格的正確介系詞 --"] + q_data.get("phrase_options", [])
            ans_2 = st.selectbox("請點擊下方下拉選單，選出最精準的片語介系詞搭配：", options_2, key=f"q2_{selected_quiz_word}")
            if st.button("驗證片語搭配", key=f"btn2_{selected_quiz_word}"):
                if ans_2 == q_data.get("phrase_ans"):
                    st.success("🎯 完全正確！您對此單字的片語語感非常敏銳！")
                else:
                    st.error(f"❌ 答錯了！正確答案應該是【 {q_data.get('phrase_ans')} 】")
                    
        with t3:
            st.markdown("#### 🔤 階段三：高階衍生詞彙 - 語法變形手動填充題")
            st.warning(f"💡 **文法線索：** {q_data.get('grammar_hint', '請注意詞性變化')}")
            st.info(f"📋 **題目句子：**\n{q_data.get('grammar_q', '_______')}")
            ans_3 = st.text_input(f"請根據文法結構，手動輸入單字「{selected_quiz_word}」的正確衍生詞性形或時態變化型：", key=f"q3_{selected_quiz_word}").strip()
            if st.button("驗證文法結構", key=f"btn3_{selected_quiz_word}"):
                if ans_3.lower() == q_data.get("grammar_ans", "").strip().lower():
                    st.success(f"🎯 太強了！手動填充完全正確！答案正是：{q_data.get('grammar_ans')}")
                else:
                    st.error(f"❌ 殘念！手動拼寫結構不對。正確衍生型態應為：【 {q_data.get('grammar_ans')} 】")
                    
        with t4:
            st.markdown("#### 🎬 階段四：脈絡邏輯串接 - 完整短文情境克漏字")
            st.info(f"📖 **情境克漏字短文：**\n{q_data.get('cloze_q', '[  ]')}")
            ans_4 = st.radio("請選出最符合文意填入 [  ] 的黃金字彙：", q_data.get("cloze_options", []), key=f"q4_{selected_quiz_word}")
            if st.button("驗證短文克漏字", key=f"btn4_{selected_quiz_word}"):
                if ans_4 == q_data.get("cloze_ans"):
                    st.success("🎯 恭喜！克漏字完全答對，您已成功掌握該單字的情境脈絡！")
                else:
                    st.error(f"❌ 答錯囉，短文內要填入的應該是本字【 {q_data.get('cloze_ans')} 】。")
                    
        with t5:
            st.markdown("#### 🎧 階段五：極限大腦盲聽 - 語音聽寫特訓題")
            st.write("點擊下方綠色按鈕聆聽官方大腦語音，請僅憑耳朵聽力拼出聽到的單字！")
            tts_button(selected_quiz_word, label="🔊 播放盲聽特訓語音")
            ans_5 = st.text_input("聽寫輸入框：請拼出您剛剛聽到的發音字彙：", key=f"q5_{selected_quiz_word}").strip().lower()
            if st.button("驗證聽寫答案", key=f"btn5_{selected_quiz_word}"):
                if ans_5 == selected_quiz_word:
                    st.success("🎯 音感與拼寫完美契合！盲聽聽寫完全正確！")
                else:
                    st.error("❌ 音頻拼寫不吻合，請再點擊一次播放按鈕仔細聆聽發音. ")
                    
        with t6:
            st.markdown("#### 🔗 階段六：高階語感重塑 - 國際檢定級整句單字重組題")
            raw_sentence = q_data.get("scrambled_sentence", "")
            translation = q_data.get("scrambled_translation", "")
            st.markdown(f"**🎯 句子中文翻譯目標：**\n*{translation}*")
            
            state_key_order = f"order_{selected_quiz_word}"
            if state_key_order not in st.session_state:
                words_list = raw_sentence.split()
                random.shuffle(words_list)
                st.session_state[state_key_order] = words_list
                st.session_state[f"user_seq_{selected_quiz_word}"] = []
                
            st.write("📦 可使用的單字元件磁鐵：")
            user_reorder_seq = st.multiselect(
                "請『依序』點選單字磁鐵來組成正確的整句英文例句：", 
                options=list(set(raw_sentence.split())), 
                key=f"mselect_{selected_quiz_word}"
            )
            if st.button("提交整句重組判斷", key=f"btn6_{selected_quiz_word}"):
                user_sentence_str = " ".join(user_reorder_seq).strip().lower().replace(".", "").replace(",", "")
                correct_sentence_str = raw_sentence.strip().lower().replace(".", "").replace(",", "")
                if user_sentence_str == correct_sentence_str:
                    st.success(f"🎯 太驚人了！整句結構建構成功！\n正確句子：{raw_sentence}")
                else:
                    st.error(f"❌ 結構順序有誤。")
                    st.markdown(f"👉 **官方權威正確解答句架構為：**\n`{raw_sentence}`")

# ------------------------------------------
# 👑 新增核心管理員後台功能 (只有您的帳號可見)
# ------------------------------------------
if is_admin:
    with main_tabs[3]:
        st.header("👑 系統核心管理員控制台")
        st.write("歡迎總管理員回來。此處提供最高調度權限，可直接檢視核心資料庫並手動調整用戶狀態。")
        
        # 讀取目前全系統所有註冊者資料
        def load_all_users():
            conn = sqlite3.connect('anki_vocab.db')
            c = conn.cursor()
            c.execute("SELECT id, email, password, credits FROM users WHERE id != 'admin_root' ORDER BY rowid DESC")
            rows = c.fetchall()
            conn.close()
            return rows

        users_list = load_all_users()
        
        # 分類面版
        adm_tab1, adm_tab2, adm_tab3 = st.tabs(["📊 用戶數據名冊", "🔑 忘記密碼・重設中心", "💰 儲值/管理點數中心"])
        
        # 管理面板 1: 數據名冊
        with adm_tab1:
            st.subheader(f"👥 目前加入系統的正式用戶（共計 {len(users_list)} 人）")
            if not users_list:
                st.info("目前尚無其他正式註冊會員。")
            else:
                # 建立表格
                import pandas as pd
                df = pd.DataFrame(users_list, columns=["用戶內部識別碼 ID", "註冊電子郵件 (Email)", "用戶密碼 (明碼)", "剩餘點數"])
                st.dataframe(df, use_container_width=True)
                
                # 快速全體增加福利點數功能
                st.markdown("---")
                st.markdown("#### ⚡ 系統全體廣播發放點數補貼")
                bonus_amt = st.number_input("請輸入要送給『全體用戶』的福利點數：", min_value=1, max_value=100, value=10)
                if st.button("確認全體一鍵分發"):
                    conn = sqlite3.connect('anki_vocab.db')
                    c = conn.cursor()
                    c.execute("UPDATE users SET credits = credits + ? WHERE id != 'admin_root'", (bonus_amt,))
                    conn.commit()
                    conn.close()
                    st.success(f"🚀 已成功為全體用戶儲值額外 {bonus_amt} 點數福利！")
                    time.sleep(1)
                    st.rerun()

        # 管理面板 2: 忘記密碼更改
        with adm_tab2:
            st.subheader("🔑 忘記密碼維護通道")
            st.write("如果用戶忘記密碼，請在下方選擇他們的 Email 並直接輸入新密碼覆蓋。")
            
            if not users_list:
                st.info("目前無用戶可供修改。")
            else:
                user_emails = [u[1] for u in users_list]
                selected_user_email = st.selectbox("請選擇需要協助重設密碼的用戶 Email：", user_emails, key="pwd_select_user")
                new_assigned_pwd = st.text_input("請輸入要幫他設定的【新密碼】", type="default", help="可以直接輸入明碼供用戶抄寫")
                
                if st.button("確認強制更新用戶密碼"):
                    if not new_assigned_pwd.strip():
                        st.warning("密碼不能為空。")
                    else:
                        conn = sqlite3.connect('anki_vocab.db')
                        c = conn.cursor()
                        c.execute("UPDATE users SET password=? WHERE email=?", (new_assigned_pwd.strip(), selected_user_email))
                        conn.commit()
                        conn.close()
                        st.success(f"🔑 密碼更換成功！用戶 `{selected_user_email}` 的密碼已成功變更為：**{new_assigned_pwd.strip()}**")
                        time.sleep(1)
                        st.rerun()

        # 管理面板 3: 儲值點數功能
        with adm_tab3:
            st.subheader("💰 用戶特訓金幣與點數儲值中心")
            st.write("手動為指定的用戶儲值可用點數（1點可查一個單字）。")
            
            if not users_list:
                st.info("目前無用戶可供儲值。")
            else:
                user_options_credits = {u[1]: (u[0], u[3]) for u in users_list} # email -> (id, current_credits)
                selected_credit_email = st.selectbox("請選擇要執行儲值的用戶 Email：", list(user_options_credits.keys()), key="credit_select_user")
                
                target_uid, target_cre = user_options_credits[selected_credit_email]
                st.markdown(f"該用戶目前擁有的點數為：**{target_cre}** 點")
                
                deposit_mode = st.radio("請選擇操作類型：", ["➕ 儲值增加點數", "➖ 手動扣除點數"])
                change_amount = st.number_input("請輸入調整點數數量：", min_value=1, max_value=5000, value=50)
                
                if st.button("執行點數調度更新"):
                    conn = sqlite3.connect('anki_vocab.db')
                    c = conn.cursor()
                    if deposit_mode == "➕ 儲值增加點數":
                        c.execute("UPDATE users SET credits = credits + ? WHERE id=?", (change_amount, target_uid))
                        st.success(f"💰 儲值成功！已幫 `{selected_credit_email}` 增加 {change_amount} 點！")
                    else:
                        c.execute("UPDATE users SET credits = max(0, credits - ?) WHERE id=?", (change_amount, target_uid))
                        st.success(f"⚠️ 扣除成功！已從 `{selected_credit_email}` 扣除 {change_amount} 點！")
                    conn.commit()
                    conn.close()
                    time.sleep(1)
                    st.rerun()
