import streamlit as st
import sqlite3
import datetime
import random
import json
import requests  # 用於呼叫 Supabase REST API
from google import genai
from google.genai import types

# ==========================================
# 0. 系統核心安全金鑰配置 (金鑰隱私保護保護層)
# ==========================================
SUPABASE_URL = "https://jcdakjtozepzktrlmpak.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_KCvBv7Uc12dLg_Od9aKyKg_XpVDLAoe"

# 🌟 全局共用後端 API Key（用戶無需輸入即可使用，且不會暴露在前端）
BACKEND_GEMINI_KEY = "你的_GEMINI_API_KEY_請在此處替換" 

# ==========================================
# 1. 資料庫初始化 (升級：支援多用戶隔離機制)
# ==========================================
def init_db():
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    # 新增 user_id 欄位以區分不同會員的專屬單字
    c.execute('''CREATE TABLE IF NOT EXISTS vocab 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id TEXT,
                  word TEXT, 
                  definition TEXT, 
                  grammar TEXT,
                  mnemonic TEXT,
                  confusable TEXT,
                  sentences TEXT, 
                  date_added TEXT,
                  ease_factor REAL DEFAULT 2.5,
                  interval INTEGER DEFAULT 0,
                  next_review_date TEXT,
                  error_count INTEGER DEFAULT 0,
                  success_count INTEGER DEFAULT 0,
                  streak INTEGER DEFAULT 0,
                  phrase_q TEXT,
                  phrase_options TEXT,
                  phrase_ans TEXT,
                  grammar_q TEXT,
                  grammar_options TEXT,
                  grammar_ans TEXT,
                  cloze_q TEXT,
                  cloze_options TEXT,
                  cloze_ans TEXT)''')
    
    # 建立複合唯一索引，確保「同一個用戶」不能重複匯入「同一個單字」
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_word ON vocab (user_id, word)")
    except Exception:
        pass
        
    conn.commit()
    conn.close()

# ==========================================
# 2. Supabase 會員驗證模組 (REST API 高速輕量版)
# ==========================================
def supabase_signup(email, password):
    url = f"{SUPABASE_URL}/auth/v1/signup"
    headers = {"apiKey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
    payload = {"email": email, "password": password}
    res = requests.post(url, json=payload, headers=headers)
    return res.json(), res.status_code

def supabase_signin(email, password):
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {"apiKey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
    payload = {"email": email, "password": password}
    res = requests.post(url, json=payload, headers=headers)
    return res.json(), res.status_code

# ==========================================
# 3. Google AI Studio (Gemini API) 數據大模組串接
# ==========================================
def fetch_gemini_learning_package(word, api_key):
    word = word.strip().lower()
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    你是一位精通台灣繁體中文的頂尖英文權威教授。請為單字 "{word}" 建立一個全方位的語言學習字卡大禮包。
    你必須嚴格遵循 JSON 格式返回數據。
    
    JSON 格式規範如下：
    {{
      "definition": "繁體中文核心釋義 (與括號英文詳細定義)",
      "grammar": "【1. 詞性與搭配公式】\\n• 詳細拆解該字常見的介系詞搭配 (例如 be vulnerable to N)。\\n【2. 核心文法句型】\\n• 寫出標準的文法結構句型公式。",
      "mnemonic": "【🎯 真實諧音聯想與口訣】\\n• 必須根據該字的英文發音，發想一個幽默、好記且與字義完美結合的台灣華語諧音口訣，並寫出畫面情境（絕對不能敷衍）。",
      "confusable": "【⚠️ 易混淆單字精準辨析與真實舉例】\\n• 找出1個與該字字形、發音或字義最容易搞混的高頻單字。\\n• 格式必須為：\\n  - 本字 (詞性) ➡️ 定義\\n    👉 實例：[中英文對比例句]\\n  - 混淆字 (詞性) ➡️ 定義\\n    👉 實例：[中英文對比例句]",
      "phrase_q": "考驗片語/介系詞搭配的句子，空格請用 _______ 代替。",
      "phrase_options": ["選項A", "選項B", "選項C", "選項D"],
      "phrase_ans": "必須是 phrase_options 中的其中一個精準正確答案",
      "grammar_q": "一個精心設計的『文法多模態辨析題』，完美模擬多益或高階英文檢定。空格用 ________ 代替。\\n請從以下兩大類別中『隨機挑選一種最適合該字衍生發展』的方式來出題，確保題型極具多樣性：\\n1.【詞性衍生多樣化變化】：設計一個需要填入該字之『名詞形』、『形容詞形』或『副詞形』的專業句子（例如：空格在動詞後面需要副詞修飾；或是空格在形容詞後面需要名詞）。\\n2.【動詞進階時態/語態】：若該字非常適合考時態，請設計一個需要『過去式』、『過去分詞』、『現在分詞』或『被動語態』的句子。",
      "grammar_options": ["選項1", "選項2", "選項3", "選項4"],
      "grammar_ans": "必須是 grammar_options 中唯一符合句子語法結構（如名詞、形容詞、副詞或特定時態）的正確衍生變形單字答案",
      "cloze_q": "一段包含2-3個句子的完整情境短文克漏字，將本字挖空寫成 [   ]。",
      "cloze_options": ["本字原形", "干擾字1", "干擾字2", "干擾字3"],
      "cloze_ans": "本字原形",
      "sentences": "第一句高階商務或生活英文例句||💡 中文翻譯###第二句高階商務或生活英文例句||💡 中文翻譯"
    }}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.4
            ),
        )
        res_text = response.text.strip()
        data = json.loads(res_text)
        return data
    except Exception as e:
        st.error(f"Gemini AI 核心生成失敗，請檢查管理員後台的 API Key 是否設定正確。錯誤訊息: {e}")
        return None

# ==========================================
# 4. Anki / SRS 演算法調控 (安全限縮至該用戶)
# ==========================================
def apply_anki_scheduling(user_id, word, is_correct, quality_override=None):
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("SELECT ease_factor, interval, streak, error_count, success_count FROM vocab WHERE user_id=? AND word=?", (user_id, word))
    row = c.fetchone()
    
    if row:
        ease_factor, interval, streak, error_count, success_count = row
        today = datetime.date.today()
        
        if not is_correct:
            streak = 0
            interval = 1
            error_count += 1
            ease_factor = max(1.3, ease_factor - 0.25)
        else:
            streak += 1
            success_count += 1
            quality = quality_override if quality_override is not None else 4
            
            if streak == 1: interval = 1
            elif streak == 2: interval = 3
            elif streak == 3: interval = 7
            else: interval = int(interval * ease_factor)
            
            if quality == 5:
                ease_factor += 0.15
                interval += 2
                
        next_review = today + datetime.timedelta(days=interval)
        c.execute('''UPDATE vocab SET ease_factor=?, interval=?, next_review_date=?, 
                     streak=?, error_count=?, success_count=? WHERE user_id=? AND word=?''',
                  (ease_factor, interval, str(next_review), streak, error_count, success_count, user_id, word))
        conn.commit()
    conn.close()

# ==========================================
# 5. 輔助功能與多用戶資料讀取
# ==========================================
def tts_button(word):
    html_code = f"""
    <button onclick="window.speechSynthesis.speak(new SpeechSynthesisUtterance('{word}'))" 
    style="background-color: #2E7D32; color: white; border: none; padding: 6px 12px; 
    text-align: center; font-size: 13px; cursor: pointer; border-radius: 4px;">
    🔊 發音聆聽
    </button>
    """
    st.components.v1.html(html_code, height=40)

def get_all_words(user_id):
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("SELECT word, definition, grammar, mnemonic, confusable, sentences, next_review_date, streak, error_count FROM vocab WHERE user_id=? ORDER BY id DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_due_words(user_id):
    today_str = str(datetime.date.today())
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("SELECT word, definition, grammar, mnemonic, confusable, sentences, error_count, phrase_q, phrase_options, phrase_ans, grammar_q, grammar_options, grammar_ans, cloze_q, cloze_options, cloze_ans FROM vocab WHERE user_id=? AND (next_review_date <= ? OR interval = 0)", (user_id, today_str))
    rows = c.fetchall()
    conn.close()
    return rows

# ==========================================
# 6. 主介面與登入系統邏輯
# ==========================================
def main():
    init_db()
    st.set_page_config(page_title="EchoBrain SRS 智慧英文特訓系統", layout="wide")
    
    # 初始化會員登入狀態 Session
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "user_email" not in st.session_state:
        st.session_state.user_email = ""

    # ---- 狀況 A: 會員尚未登入門檻 ----
    if not st.session_state.logged_in:
        st.title("🧠 EchoBrain SRS 系統門禁安全中心")
        st.markdown("歡迎使用全維度大腦記憶特訓系統！請登入或註冊您的會員帳號以開始使用。")
        
        tab1, tab2 = st.tabs(["🔐 會員登入", "📝 新用戶註冊"])
        
        with tab2:
            st.subheader("免費註冊新帳號")
            reg_email = st.text_input("設定電子郵件 (Email)", key="reg_email_input")
            reg_pwd = st.text_input("設定密碼 (至少 6 位字元)", type="password", key="reg_pwd_input")
            if st.button("註冊帳戶", key="btn_signup"):
                # 💡 關鍵優化：使用 .strip() 自動清除使用者不小心按到的前後空白字元
                clean_email = reg_email.strip() if reg_email else ""
                if clean_email and reg_pwd:
                    with st.spinner("正在向雲端安全性註冊..."):
                        res, code = supabase_signup(clean_email, reg_pwd)
                    if code == 200 or "id" in res.get("user", {}):
                        st.success("🎉 註冊成功！部分驗證可能需要查收確認信，您現在可以切換至「會員登入」分頁進入系統。")
                    else:
                        error_msg = res.get("error", {}).get("message") or res.get("msg", "註冊失敗，請檢查格式。")
                        st.error(f"❌ 註冊失敗：{error_msg}")
                else:
                    st.warning("請填寫所有欄位。")
                    
      with tab2:
            st.subheader("免費註冊新帳號")
            reg_email = st.text_input("設定電子郵件 (Email)", key="reg_email_input")
            reg_pwd = st.text_input("設定密碼 (至少 6 位字元)", type="password", key="reg_pwd_input")
            if st.button("註冊帳戶", key="btn_signup"):
                # 💡 關鍵優化：使用 .strip() 自動清除使用者不小心按到的前後空白字元
                clean_email = reg_email.strip() if reg_email else ""
                if clean_email and reg_pwd:
                    with st.spinner("正在向雲端安全性註冊..."):
                        res, code = supabase_signup(clean_email, reg_pwd)
                    if code == 200 or "id" in res.get("user", {}):
                        st.success("🎉 註冊成功！部分驗證可能需要查收確認信，您現在可以切換至「會員登入」分頁進入系統。")
                    else:
                        error_msg = res.get("error", {}).get("message") or res.get("msg", "註冊失敗，請檢查格式。")
                        st.error(f"❌ 註冊失敗：{error_msg}")
                else:
                    st.warning("請填寫所有欄位。")
        return # 攔截不讓其看見後台系統

    # ---- 狀況 B: 驗證通過，進入主要智慧應用程式面 ----
    user_id = st.session_state.user_id
    user_email = st.session_state.user_email
    
    st.title("🧠 EchoBrain SRS 全維度大腦記憶特訓系統")
    
    # 側邊欄控制
    st.sidebar.header("👤 會員控制中心")
    st.sidebar.info(f"帳號: `{user_email}`")
    if st.sidebar.button("登出系統"):
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.user_email = ""
        st.rerun()
        
    all_data = get_all_words(user_id)
    due_data = get_due_words(user_id)
    
    st.sidebar.markdown("---")
    st.sidebar.header("📊 本日任務進度")
    st.sidebar.metric(label="您的總收藏字數", value=len(all_data))
    st.sidebar.metric(label="待複習 (Anki 排程)", value=len(due_data))
    
    menu = ["📥 AI 智慧匯入單字", "🎯 智慧多維度測驗", "📊 完整字彙統計", "📕 核心錯題本", "📖 字庫模糊搜尋"]
    choice = st.sidebar.selectbox("切換面板", menu)
    
    if choice == "📥 AI 智慧匯入單字":
        st.subheader("📥 Gemini AI 智慧記憶大禮包生成")
        st.markdown("💡 **系統服務狀態**：`已自動串接管理員的雲端高速 Gemini-2.5-Flash 模型`，您無需自行準備 API Key！")
        
        words_input = st.text_area("請輸入英文單字（支援換行或逗號分隔）", placeholder="criticize\npersistent\ninnovate")
        
        if st.button("啟動 Gemini AI 數據打包匯入"):
            if not BACKEND_GEMINI_KEY or BACKEND_GEMINI_KEY == "你的_GEMINI_API_KEY_請在此處替換":
                st.error("系統配置錯誤：管理員後台未設定有效的 BACKEND_GEMINI_KEY。")
                return
            
            raw_list = words_input.replace("\n", ",").split(",")
            word_list = [w.strip() for w in raw_list if w.strip()]
            
            if not word_list:
                st.warning("請輸入單字內容。")
            else:
                conn = sqlite3.connect('anki_vocab.db')
                c = conn.cursor()
                success_num = 0
                
                for w in word_list:
                    # 檢查目前用戶是否已加入過此字
                    c.execute("SELECT id FROM vocab WHERE user_id=? AND word=?", (user_id, w))
                    if c.fetchone():
                        c.execute("UPDATE vocab SET interval=0, next_review_date=? WHERE user_id=? AND word=?", (str(datetime.date.today()), user_id, w))
                        success_num += 1
                        continue
                    
                    with st.spinner(f"Gemini AI 正在為您訂製單字 【{w}】 的專屬多功能學習大禮包..."):
                        pkg = fetch_gemini_learning_package(w, BACKEND_GEMINI_KEY)
                        
                    if pkg:
                        c.execute('''INSERT INTO vocab (
                                        user_id, word, definition, grammar, mnemonic, confusable, sentences, date_added, next_review_date,
                                        phrase_q, phrase_options, phrase_ans, grammar_q, grammar_options, grammar_ans,
                                        cloze_q, cloze_options, cloze_ans
                                     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                                  (user_id, w, pkg["definition"], pkg["grammar"], pkg["mnemonic"], pkg["confusable"], pkg["sentences"],
                                   str(datetime.date.today()), str(datetime.date.today()),
                                   pkg["phrase_q"], json.dumps(pkg["phrase_options"], ensure_ascii=False), pkg["phrase_ans"],
                                   pkg["grammar_q"], json.dumps(pkg["grammar_options"], ensure_ascii=False), pkg["grammar_ans"],
                                   pkg["cloze_q"], json.dumps(pkg["cloze_options"], ensure_ascii=False), pkg["cloze_ans"]))
                        success_num += 1
                conn.commit()
                conn.close()
                st.success(f"🎉 成功！已透過公用 API 完美生成並匯入 {success_num} 個單字至您的個人學習庫中。")

    elif choice == "🎯 智慧多維度測驗":
        st.subheader("✍️ 實戰多維度全題型演練")
        mode = st.radio("出題模式：", ["依 Anki 演算法排程", "指定特定匯入日期抽考"])
        
        if mode == "依 Anki 演算法排程":
            quiz_pool = get_due_words(user_id)
        else:
            target_date = st.date_input("選擇抽考哪天匯入的單字：", datetime.date.today())
            conn = sqlite3.connect('anki_vocab.db')
            c = conn.cursor()
            c.execute("SELECT word, definition, grammar, mnemonic, confusable, sentences, error_count, phrase_q, phrase_options, phrase_ans, grammar_q, grammar_options, grammar_ans, cloze_q, cloze_options, cloze_ans FROM vocab WHERE user_id=? AND date_added=?", (user_id, str(target_date)))
            quiz_pool = c.fetchall()
            conn.close()
            
        if not quiz_pool:
            st.info("🍀 目前選定的範圍內沒有需要複習的單字！")
        else:
            pool_key = f"pool_{mode}_{str(datetime.date.today())}"
            if 'current_pool_key' not in st.session_state or st.session_state.current_pool_key != pool_key:
                st.session_state.current_pool_key = pool_key
                st.session_state.srs_idx = 0
                st.session_state.quiz_pool = list(quiz_pool)
                random.shuffle(st.session_state.quiz_pool)
                st.session_state.ans_status = None
                st.session_state.types = [random.choice(['A', 'B', 'C', 'D']) for _ in range(len(quiz_pool))]

            idx = st.session_state.srs_idx
            if idx < len(st.session_state.quiz_pool):
                current = st.session_state.quiz_pool[idx]
                (word, definition, grammar, mnemonic, confusable, sentences, error_count,
                 phrase_q, phrase_options_str, phrase_ans, grammar_q, grammar_options_str, grammar_ans,
                 cloze_q, cloze_options_str, cloze_ans) = current
                
                q_type = st.session_state.types[idx]
                st.markdown(f"### 🎯 第 {idx+1} 題 / 共 {len(st.session_state.quiz_pool)} 題")
                
                if q_type == 'A':
                    st.info(f"🔤 **【核心單字拼寫題】**\n\n請根據中文核心釋義拼出正確單字：\n\n【 釋義 】： {definition}")
                    with st.form(key=f"form_A_{idx}"):
                        user_ans = st.text_input("輸入英文單字：").strip().lower()
                        if st.form_submit_button("送出判定"):
                            st.session_state.ans_status = ("checked", user_ans == word.lower(), word)
                
                elif q_type == 'B':
                    st.info(f"🔗 **【核心片語固定搭配題】**\n\n請選出最符合句意與習慣用法的固定介系詞或片語搭配：")
                    st.markdown(f"**題目:** {phrase_q if phrase_q else 'Missing text'}")
                    opts = json.loads(phrase_options_str) if phrase_options_str else ["A", "B", "C", "D"]
                    with st.form(key=f"form_B_{idx}"):
                        user_ans = st.radio("選擇答案：", opts)
                        if st.form_submit_button("送出判定"):
                            st.session_state.ans_status = ("checked", user_ans == phrase_ans, word)
                            
                elif q_type == 'C':
                    st.info(f"📊 **【語法結構與全衍生詞性辨析題】**\n\n請仔細分析句子結構（名詞/形容詞/副詞/時態），選出唯一符合語法的正確變形選項：")
                    st.markdown(f"**題目:** {grammar_q if grammar_q else 'Missing text'}")
                    opts = json.loads(grammar_options_str) if grammar_options_str else ["A", "B", "C", "D"]
                    with st.form(key=f"form_C_{idx}"):
                        user_ans = st.radio("選擇答案：", opts)
                        if st.form_submit_button("送出判定"):
                            st.session_state.ans_status = ("checked", user_ans == grammar_ans, word)

                elif q_type == 'D':
                    st.info(f"📝 **【進階情境段落克漏字】**\n\n閱讀情境短文，選出最適合填入空格 [   ] 的單字：")
                    st.code(cloze_q if cloze_q else "Missing Cloze Text", language="text")
                    opts = json.loads(cloze_options_str) if cloze_options_str else ["A", "B", "C", "D"]
                    with st.form(key=f"form_D_{idx}"):
                        user_ans = st.radio("選擇答案：", opts)
                        if st.form_submit_button("送出判定"):
                            st.session_state.ans_status = ("checked", user_ans == cloze_ans, word)

                if st.session_state.ans_status:
                    _, is_match, target_word = st.session_state.ans_status
                    st.markdown("---")
                    
                    if is_match:
                        st.success(f"🎉 答對了！")
                    else:
                        st.error(f"❌ 答錯了！本題的核心目標原形單字是： **{target_word}**")
                        if q_type == 'C':
                            st.warning(f"💡 本題正確的文法變形答案（符合此句子詞性/時態）為： **{grammar_ans}**")
                    
                    st.warning(f"📢 核心中文釋義： **{definition}**")
                    tts_button(target_word)
                    
                    col_left, col_right = st.columns(2)
                    with col_left:
                        st.success(f"💡 專屬諧音聯想密技\n\n{mnemonic}")
                        st.info(f"📊 核心語法結構與搭配解析\n\n{grammar}")
                    with col_right:
                        st.warning(f"⚠️ 易混淆單字精準辨析與真實舉例\n\n{confusable}")
                    
                    st.markdown("##### 🎯 請根據本次記憶熟練度，點擊下方按鈕切換下一題：")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        if st.button("👎 沒記起來/答錯 (1天後重考)"):
                            apply_anki_scheduling(user_id, target_word, is_correct=False)
                            st.session_state.srs_idx += 1
                            st.session_state.ans_status = None
                            st.rerun()
                    with c2:
                        if st.button("👌 普通/勉強答對 (3-4天後複習)"):
                            apply_anki_scheduling(user_id, target_word, is_correct=is_match, quality_override=3)
                            st.session_state.srs_idx += 1
                            st.session_state.ans_status = None
                            st.rerun()
                    with c3:
                        if st.button("👍 記得很熟! (大幅拉長週期)"):
                            apply_anki_scheduling(user_id, target_word, is_correct=is_match, quality_override=5)
                            st.session_state.srs_idx += 1
                            st.session_state.ans_status = None
                            st.rerun()
            else:
                st.balloons()
                st.success("🎊 本輪所有題型的排程測驗全部結束！")
                if st.button("重新整理測驗"):
                    del st.session_state.srs_idx
                    del st.session_state.quiz_pool
                    st.session_state.ans_status = None
                    st.rerun()

    elif choice == "📊 完整字彙統計":
        st.subheader("📊 全字庫多維度學習數據統計中心")
        
        conn = sqlite3.connect('anki_vocab.db')
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM vocab WHERE user_id=? AND streak >= 4", (user_id,))
        mastered_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM vocab WHERE user_id=? AND streak > 0 AND streak < 4", (user_id,))
        learning_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM vocab WHERE user_id=? AND streak = 0", (user_id,))
        new_cnt = c.fetchone()[0]
        
        c.execute("SELECT word, error_count FROM vocab WHERE user_id=? AND error_count > 0 ORDER BY error_count DESC LIMIT 7", (user_id,))
        top_errors = c.fetchall()
        conn.close()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("您的總字庫容量", len(all_data))
        m2.metric("🏆 精熟字數 (連勝>=4)", mastered_cnt)
        m3.metric("📈 記憶中字數", learning_cnt)
        m4.metric("🚨 待拯救生字", new_cnt)
        
        st.markdown("---")
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.markdown("#### 🎯 記憶熟練度佔比分佈")
            if len(all_data) == 0:
                st.info("尚無單字數據，無法繪製圖表。")
            else:
                pie_data = {
                    "狀態": ["🏆 精熟", "📈 記憶中", "🚨 新進/生疏"],
                    "字數": [mastered_cnt, learning_cnt, new_cnt]
                }
                st.bar_chart(data=pie_data, x="狀態", y="字數", color="#1E88E5")
                st.caption("說明：連勝達 4 次以上的單字會自動歸類為『精熟』，排程會大幅自動拉長。")
                
        with col_chart2:
            st.markdown("#### 🚨 核心高頻錯題大魔王排行榜 (Top 7)")
            if not top_errors:
                st.success("🎉 目前沒有任何答錯單字！太棒了！")
            else:
                err_dict = {
                    "單字": [x[0] for x in top_errors],
                    "答錯次數": [x[1] for x in top_errors]
                }
                st.bar_chart(data=err_dict, x="單字", y="答錯次數", color="#E53935")
                st.caption("提示：這些字是你的核心大魔王，建議去『核心錯題本』多加強複習！")

    elif choice == "📕 核心錯題本":
        st.subheader("🚨 高頻錯字重點攻克本")
        conn = sqlite3.connect('anki_vocab.db')
        c = conn.cursor()
        c.execute("SELECT word, definition, grammar, mnemonic, confusable, error_count, sentences FROM vocab WHERE user_id=? AND error_count > 0 ORDER BY error_count DESC", (user_id,))
        wrong_words = c.fetchall()
        conn.close()
        
        if not wrong_words:
            st.info("😎 完美！目前沒有任何答錯紀錄的單字。")
        else:
            for w, df, gram, mnem, conf, err, sents in wrong_words:
                with st.expander(f"❌ {w} (累計答錯 {err} 次) — {df}"):
                    tts_button(w)
                    st.markdown(f"**💡 專屬諧音：**\n{mnem}")
                    st.markdown(f"**⚠️ 易混淆單字真實對比：**\n{conf}")
                    st.markdown(f"**📊 語法結構：**\n{gram}")
                    st.write("**📝 精選翻譯例句：**")
                    if sents:
                        for s in sents.split("###"):
                            if "||" in s: st.write(f"👉 *{s.split('||')[0]}*\n   ↳ {s.split('||')[1]}")

    elif choice == "📖 字庫模糊搜尋":
        st.subheader("🔍 整合記憶狀態庫")
        search = st.text_input("輸入關鍵字搜尋（英漢皆可）：")
        words = get_all_words(user_id)
        
        if words:
            if search:
                words = [r for r in words if search.lower() in r[0].lower() or search in r[1]]
            for w, df, gram, mnem, conf, sents, next_date, streak, err in words:
                with st.expander(f"🔤 {w} [ 下次複習: {next_date} | 連勝次數: {streak} | 錯題: {err}次 ]"):
                    tts_button(w)
                    st.write(f"**💡 中文核心釋義：** {df}")
                    st.markdown(f"**💡 諧音/聯想記憶：**\n{mnem}")
                    st.markdown(f"**⚠️ 易混淆單字對比舉例：**\n{conf}")
                    st.markdown(f"**📊 詞性語法解析：**\n{gram}")
                    st.write("**📝 海量例句庫：**")
                    if sents:
                        for s in sents.split("###"):
                            if "||" in s: st.write(f"• *{s.split('||')[0]}* \n  ↳ {s.split('||')[1]}")

if __name__ == "__main__":
    main()
