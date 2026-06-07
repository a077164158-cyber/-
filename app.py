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

# 🌟 管理員公用 API 金鑰設定（請在此處填入您的真實金鑰）
BACKEND_GEMINI_KEY = "AQ.Ab8RN6Lauqruyzzq71MnPmyU5rWY2ruoZWKzN-ETUvjvgyVggA"
ADMIN_EMAIL = "a23623020428@gmail.com"

# 初始化 Session State
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "current_test" not in st.session_state:
    st.session_state.current_test = {}

# SQLite 資料庫初始化（整合用戶管理、密碼儲存與點數系統）
def init_db():
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    # 建立字彙表
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
    # 建立在地用戶表（用於支援管理員直接查看、改密碼與儲值功能）
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE,
                    password TEXT,
                    points INTEGER DEFAULT 10
                )''')
    
    # 預先自動寫入最高管理員帳號
    c.execute("INSERT OR IGNORE INTO users (id, email, password, points) VALUES (?, ?, ?, ?)", 
              ("admin_root", ADMIN_EMAIL, "8642158a", 99999))
    
    conn.commit()
    conn.close()

init_db()

# 輔助資料庫函式
def get_user_points(user_id):
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE id=?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 0

def deduct_user_point(user_id):
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("UPDATE users SET points = points - 1 WHERE id=? AND points > 0", (user_id,))
    conn.commit()
    conn.close()

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
    你必須嚴格遵循 JSON 格式返回數據，絕對不能包含任何額外的 Markdown 標籤（如 ```json）。
    
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
      
      "cloze_q": "一段包含2-3個句子的完整情境短文克漏字，將本字挖空寫成 [   ]。",
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
            st.error(f"Gemini AI 核心生成失敗。錯誤訊息: {e}")
            return None

# ==========================================
# 3. 系統安全門禁中心（整合系統預設帳密驗證）
# ==========================================
if not st.session_state.logged_in:
    st.title("🧠 EchoBrain SRS 系統門禁安全中心")
    st.markdown("歡迎使用全維度大腦記憶特訓系統！請登入或註冊您的會員帳號以開始使用。")
    
    tab1, tab2 = st.tabs(["🔐 會員登入", "📝 新用戶註冊"])
    
    with tab1:
        st.subheader("登入帳號")
        login_email = st.text_input("電子郵件 (Email)", key="login_email_input").strip()
        login_pwd = st.text_input("密碼 (Password)", type="password", key="login_pwd_input")
        
        if st.button("確認登入", key="btn_signin"):
            if login_email and login_pwd:
                # 優先檢查在地資料庫
                conn = sqlite3.connect('anki_vocab.db')
                c = conn.cursor()
                c.execute("SELECT id, email FROM users WHERE email=? AND password=?", (login_email, login_pwd))
                user_match = c.fetchone()
                conn.close()
                
                if user_match:
                    st.session_state.logged_in = True
                    st.session_state.user_id = user_match[0]
                    st.session_state.user_email = user_match[1]
                    st.success(f"🎉 登入成功！歡迎回來 {st.session_state.user_email}")
                    st.rerun()
                else:
                    st.error("❌ 登入失敗：帳號或密碼錯誤。")
            else:
                st.warning("請填寫所有欄位。")
                
    with tab2:
        st.subheader("免費註冊新帳號")
        reg_email = st.text_input("設定電子郵件 (Email)", key="reg_email_input").strip()
        reg_pwd = st.text_input("設定密碼 (至少 6 位字元)", type="password", key="reg_pwd_input")
        if st.button("註冊帳戶", key="btn_signup"):
            if reg_email and reg_pwd:
                if len(reg_pwd) < 6:
                    st.warning("密碼長度至少需要 6 位字元。")
                else:
                    conn = sqlite3.connect('anki_vocab.db')
                    c = conn.cursor()
                    try:
                        new_uid = "user_" + str(int(time.time()))
                        # 新註冊用戶預設給予 10 點點數
                        c.execute("INSERT INTO users (id, email, password, points) VALUES (?, ?, ?, ?)", (new_uid, reg_email, reg_pwd, 10))
                        conn.commit()
                        st.success("🎉 註冊成功！您已獲得預設開通 10 點點數。請切換至「會員登入」分頁進入系統。")
                    except sqlite3.IntegrityError:
                        st.error("❌ 註冊失敗：該電子郵件已被註冊。")
                    finally:
                        conn.close()
            else:
                st.warning("請填寫所有欄位。")
    st.stop()

# ==========================================
# 4. 後台系統主介面與功能導覽
# ==========================================
st.sidebar.title("🧠 EchoBrain SRS")
st.sidebar.write(f"👤 會員: {st.session_state.user_email}")

# 即時顯示點數餘額
current_points = get_user_points(st.session_state.user_id)
if st.session_state.user_email == ADMIN_EMAIL:
    st.sidebar.info("👑 您是系統最高管理員（無限點數）")
else:
    st.sidebar.metric(label="🪙 我的可用查詢點數", value=f"{current_points} 點")

if st.sidebar.button("登出系統"):
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.user_email = None
    st.rerun()

# 判斷是否顯示管理員分頁
tabs_list = ["📥 數據匯入中心", "🗂️ 字彙記憶庫", "⚔️ 七大維度特訓魔鬼測驗"]
if st.session_state.user_email == ADMIN_EMAIL:
    tabs_list.append("🛠️ 系統最高管理員後台")

active_tabs = st.tabs(tabs_list)

# ------------------------------------------
# 分頁 1: 數據匯入中心 (加裝扣點功能)
# ------------------------------------------
with active_tabs[0]:
    st.header("📥 AI 數據打包匯入中心")
    st.write("輸入你想要特訓的英文單字，Gemini AI 將為你全自動生成學習字卡。**提示：每次成功打包新單字將扣除 1 點。**")
    
    input_word = st.text_input("請輸入英文字彙 (例如: vulnerable)", key="import_word_input")
    if st.button("啟動 Gemini AI 數據打包匯入", key="btn_import"):
        if BACKEND_GEMINI_KEY == "你的_GEMINI_API_KEY_請在此處替換" or not BACKEND_GEMINI_KEY:
            st.error("系統配置錯誤：管理員後台未設定有效的 BACKEND_GEMINI_KEY。")
        elif not input_word.strip():
            st.warning("請輸入有效的單字。")
        elif current_points <= 0 and st.session_state.user_email != ADMIN_EMAIL:
            st.error("❌ 您的可用點數已耗盡！無法進行 AI 數據查詢。請聯絡管理員為您新增點數。")
        else:
            with st.spinner("Gemini AI 正在解構字彙中..."):
                pkg = fetch_gemini_learning_package(input_word, BACKEND_GEMINI_KEY)
                if pkg:
                    conn = sqlite3.connect('anki_vocab.db')
                    c = conn.cursor()
                    c.execute("SELECT id FROM vocab WHERE user_id=? AND word=?", (st.session_state.user_id, input_word.strip().lower()))
                    exist = c.fetchone()
                    
                    quiz_data_str = json.dumps(pkg, ensure_ascii=False)
                    today_str = time.strftime("%Y-%m-%d")
                    
                    if exist:
                        c.execute("""UPDATE vocab SET definition=?, grammar=?, mnemonic=?, confusable=?, sentences=?, next_review_date=?, quiz_data=? 
                                     WHERE id=?""", 
                                  (pkg['definition'], pkg['grammar'], pkg['mnemonic'], pkg['confusable'], pkg['sentences'], today_str, quiz_data_str, exist[0]))
                        st.success(f"♻️ 單字「{input_word}」已成功更新覆蓋數據！")
                    else:
                        c.execute("""INSERT INTO vocab (user_id, word, definition, grammar, mnemonic, confusable, sentences, next_review_date, streak, error_count, quiz_data) 
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)""",
                                  (st.session_state.user_id, input_word.strip().lower(), pkg['definition'], pkg['grammar'], pkg['mnemonic'], pkg['confusable'], pkg['sentences'], today_str, quiz_data_str))
                        
                        # 只有非管理員需要扣除點數
                        if st.session_state.user_email != ADMIN_EMAIL:
                            deduct_user_point(st.session_state.user_id)
                        st.success(f"🎉 成功！單字「{input_word}」已成功打包並扣除 1 點點數！")
                    conn.commit()
                    conn.close()
                    time.sleep(1)
                    st.rerun()

# ------------------------------------------
# 分頁 2: 字彙記憶庫
# ------------------------------------------
with active_tabs[1]:
    st.header("🗂️ 智能字彙記憶庫")
    all_words = get_all_words(st.session_state.user_id)
    
    if not all_words:
        st.info("您的記憶庫目前空空如也，請先前往匯入中心新增單字！")
    else:
        search_query = st.text_input("🔍 搜尋字彙庫內容", "").strip().lower()
        filtered_words = [w for w in all_words if search_query in w[0] or search_query in w[1]]
        
        # 暖身小遊戲
        with st.expander("🎲 核心定義「多向連連看」暖身配對賽"):
            game_pool = random.sample(all_words, min(3, len(all_words)))
            all_defs = [w[1] for w in game_pool]
            random.shuffle(all_defs)
            correct_count = 0
            for item in game_pool:
                w_word = item[0]
                w_real_def = item[1]
                user_ans = st.selectbox(f"單字【 {w_word} 】的中文释义？", ["-- 請選擇 --"] + all_defs, key=f"match_{w_word}")
                if user_ans == w_real_def:
                    correct_count += 1
            if correct_count == len(game_pool) and len(game_pool) > 0:
                st.success("🎯 連連看全部正確！")
        
        st.subheader(f"📊 收錄字卡共 {len(filtered_words)} 筆")
        for w in filtered_words:
            w_word, w_def, w_gram, w_mne, w_conf, w_sent, w_date, w_streak, w_err, _, w_id = w
            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 5, 2])
                with col1:
                    st.subheader(f"🔤 {w_word}")
                    tts_button(w_word, label="🔊 聽發音")
                with col2:
                    st.markdown(f"**核心釋義：** {w_def}")
                    with st.expander("🔍 檢視完整字卡解構"):
                        st.markdown(f"**文法搭配：**\n{w_gram}")
                        st.markdown(f"**諧音聯想：**\n{w_mne}")
                        st.markdown(f"**易混淆辨析：**\n{w_conf}")
                with col3:
                    if st.button("🗑️ 刪除", key=f"del_{w_id}"):
                        conn = sqlite3.connect('anki_vocab.db')
                        c = conn.cursor()
                        c.execute("DELETE FROM vocab WHERE id=?", (w_id,))
                        conn.commit()
                        conn.close()
                        st.rerun()

# ------------------------------------------
# 分頁 3: 七大維度特訓魔鬼測驗
# ------------------------------------------
with active_tabs[2]:
    st.header("⚔️ 七大維度特訓魔鬼測驗")
    all_quiz_words = [w for w in get_all_words(st.session_state.user_id) if w[9]]
    
    if not all_quiz_words:
        st.info("尚未有任何測驗數據，請先至數據匯入中心「重新匯入單字」以補齊全新的測驗欄位結構！")
    else:
        quiz_word_options = [w[0] for w in all_quiz_words]
        selected_quiz_word = st.selectbox("🎯 請選擇想要深度特訓的字彙：", quiz_word_options)
        
        target_word_record = [w for w in all_quiz_words if w[0] == selected_quiz_word][0]
        q_data = json.loads(target_word_record[9])
        
        t1, t2, t3, t4, t5, t6 = st.tabs(["1. 核心拼寫", "2. 片語下拉", "3. 語法填充", "4. 克漏字選擇", "5. 語音聽寫", "6. 整句重組"])
        
        with t1:
            st.markdown(f"**提示（核心釋義）：** {target_word_record[1]}")
            ans_1 = st.text_input("請拼寫英文單字：", key=f"q1_{selected_quiz_word}").strip().lower()
            if st.button("提交答案", key=f"btn1_{selected_quiz_word}"):
                if ans_1 == selected_quiz_word:
                    st.success("🎯 答對了！")
                else:
                    st.error(f"❌ 錯誤。提示第一個字母是 {selected_quiz_word[0]}")
                    
        with t2:
            st.info(f"📋 **題目句子：**\n{q_data.get('phrase_q', '_______')}")
            options_2 = ["-- 請選擇 --"] + q_data.get("phrase_options", [])
            ans_2 = st.selectbox("選擇正確的介系詞：", options_2, key=f"q2_{selected_quiz_word}")
            if st.button("驗證答案", key=f"btn2_{selected_quiz_word}"):
                if ans_2 == q_data.get("phrase_ans"):
                    st.success("🎯 完全正確！")
                else:
                    st.error(f"❌ 答案應為：{q_data.get('phrase_ans')}")
                    
        with t3:
            st.warning(f"💡 **文法線索：** {q_data.get('grammar_hint', '')}")
            st.info(f"📋 **題目：**\n{q_data.get('grammar_q', '')}")
            ans_3 = st.text_input("手動輸入正確衍生詞形變化：", key=f"q3_{selected_quiz_word}").strip()
            if st.button("驗證文法", key=f"btn3_{selected_quiz_word}"):
                if ans_3.lower() == q_data.get('grammar_ans', '').strip().lower():
                    st.success("🎯 完全正確！")
                else:
                    st.error(f"❌ 正確解答為：{q_data.get('grammar_ans')}")
                    
        with t4:
            st.info(f"📖 **短文：**\n{q_data.get('cloze_q', '')}")
            ans_4 = st.radio("選出適當單字：", q_data.get("cloze_options", []), key=f"q4_{selected_quiz_word}")
            if st.button("驗證克漏字", key=f"btn4_{selected_quiz_word}"):
                if ans_4 == q_data.get("cloze_ans"):
                    st.success("🎯 答對了！")
                else:
                    st.error("❌ 答案應為本字。")
                    
        with t5:
            st.write("🎵 盲聽發音聽寫：")
            tts_button(selected_quiz_word, label="🔊 播放特訓語音")
            ans_5 = st.text_input("輸入你聽到的單字：", key=f"q5_{selected_quiz_word}").strip().lower()
            if st.button("驗證聽寫", key=f"btn5_{selected_quiz_word}"):
                if ans_5 == selected_quiz_word:
                    st.success("🎯 聽寫完全正確！")
                else:
                    st.error("❌ 拼寫不符，再聽一次。")
                    
        with t6:
            raw_sentence = q_data.get("scrambled_sentence", "")
            translation = q_data.get("scrambled_translation", "")
            st.markdown(f"**🎯 中文目標：** *{translation}*")
            user_reorder_seq = st.multiselect("請『依序』選點單字磁鐵重組句子：", options=list(set(raw_sentence.split())), key=f"mselect_{selected_quiz_word}")
            if st.button("提交重組判斷", key=f"btn6_{selected_quiz_word}"):
                user_str = " ".join(user_reorder_seq).strip().lower().replace(".", "").replace(",", "")
                correct_str = raw_sentence.strip().lower().replace(".", "").replace(",", "")
                if user_str == correct_str:
                    st.success(f"🎯 重組成功！\n{raw_sentence}")
                else:
                    st.error(f"❌ 順序有誤。正確答案為：{raw_sentence}")

# ------------------------------------------
# 分頁 4: 🛠️ 系統最高管理員後台 
# ------------------------------------------
if st.session_state.user_email == ADMIN_EMAIL:
    with active_tabs[3]:
        st.header("👑 系統最高管理員安全控制台")
        st.write("您好，管理員！您可以在此處查閱全站註冊會員、直接修正用戶密碼，以及核發/增減查詢點數。")
        
        conn = sqlite3.connect('anki_vocab.db')
        c = conn.cursor()
        c.execute("SELECT id, email, password, points FROM users")
        user_rows = c.fetchall()
        conn.close()
        
        # 1. 列表呈現所有人員與其帳密
        st.subheader("👥 現有註冊成員名冊與配置")
        
        user_data_list = []
        for r in user_rows:
            user_data_list.append({
                "用戶唯一識別碼": r[0],
                "電子郵件 (Email)": r[1],
                "目前密碼 (Password)": r[2],
                "剩餘可用點數 (Tokens)": r[3]
            })
        st.dataframe(user_data_list, use_container_width=True)
        
        st.markdown("---")
        
        # 2. 忘記密碼改密碼 / 點數變更操作區
        st.subheader("🛠️ 會員核心狀態特調維護")
        
        user_emails_options = [r[1] for r in user_rows if r[1] != ADMIN_EMAIL]
        
        if not user_emails_options:
            st.info("目前除了管理員您之外，尚無其他一般會員註冊。")
        else:
            target_manage_email = st.selectbox("請選擇您要維護的會員帳號：", user_emails_options)
            
            # 撈出該用戶目前的詳細資訊
            current_target_info = [r for r in user_rows if r[1] == target_manage_email][0]
            t_id, t_email, t_pwd, t_pts = current_target_info
            
            col_manage1, col_manage2 = st.columns(2)
            
            with col_manage1:
                st.markdown("#### 🔐 變更/重設用戶密碼")
                new_assigned_pwd = st.text_input("輸入全新密碼：", value=t_pwd)
                if st.button("確認重設該會員密碼"):
                    if new_assigned_pwd.strip():
                        conn = sqlite3.connect('anki_vocab.db')
                        c = conn.cursor()
                        c.execute("UPDATE users SET password=? WHERE id=?", (new_assigned_pwd.strip(), t_id))
                        conn.commit()
                        conn.close()
                        st.success(f"🎉 成功！已將會員 `{t_email}` 的登入密碼修改為 `{new_assigned_pwd}`！")
                        time.sleep(1)
                        st.rerun()
            
            with col_manage2:
                st.markdown("#### 🪙 儲值/增減查詢點數")
                st.write(f"目前該會員點數餘額： **{t_pts}** 點")
                points_action = st.radio("調整類型：", ["增加點數", "扣除點數", "直接設為特定數值"])
                points_value = st.number_input("調整點數值：", min_value=0, value=5, step=1)
                
                if st.button("確認調整點數"):
                    conn = sqlite3.connect('anki_vocab.db')
                    c = conn.cursor()
                    if points_action == "增加點數":
                        c.execute("UPDATE users SET points = points + ? WHERE id=?", (points_value, t_id))
                    elif points_action == "扣除點數":
                        c.execute("UPDATE users SET points = MAX(0, points - ?) WHERE id=?", (points_value, t_id))
                    else:
                        c.execute("UPDATE users SET points = ? WHERE id=?", (points_value, t_id))
                    conn.commit()
                    conn.close()
                    st.success(f"🎯 點數調整成功！已成功更新 `{t_email}` 的可用點數。")
                    time.sleep(1)
                    st.rerun()
