import streamlit as st
import json
import time
import requests
import random
from datetime import datetime, timedelta
from google import genai
from google.genai import types

# ==========================================
# 0. 系統基礎配置與初始化
# ==========================================
st.set_page_config(page_title="EchoBrain SRS 核心系統", layout="wide", initial_sidebar_state="expanded")

# 🌟 分享給別人用必填：管理員公用 Gemini API 金鑰（⚠️ 請在此處替換為您的真實 Gemini 金鑰）
BACKEND_GEMINI_KEY = "AQ.Ab8RN6LvjUf8uqSF22wg7md4x0o3HXhaRyau0G5M18EiObo5Kw"

# 👑 指定管理員帳密配置
ADMIN_EMAIL = "a23623020428@gmail.com"
ADMIN_PASSWORD = "8642158a"

# 🌐 您專屬的 Supabase 雲端資料庫連線配置
SUPABASE_URL = "https://jcdakjtozepzktrlmpak.supabase.co"
SUPABASE_KEY = "sb_publishable_KCvBv7Uc12dLg_Od9aKyKg_XpVDLAoe"

# 初始化 Session State
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None

# ==========================================
# 0.5 雲端資料庫核心整合函數 (Supabase REST API)
# ==========================================
def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def get_user_credits(user_id):
    if user_id == "admin_root":
        return 999999
    try:
        url = f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=credits"
        r = requests.get(url, headers=supabase_headers())
        if r.status_code == 200 and r.json():
            return r.json()[0].get("credits", 0)
    except:
        pass
    return 10

def deduct_credit(user_id):
    if user_id == "admin_root":
        return
    current = get_user_credits(user_id)
    new_credit = max(0, current - 1)
    try:
        url = f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}"
        requests.patch(url, headers=supabase_headers(), json={"credits": new_credit})
    except:
        pass

def update_anki_schedule(vocab_id, level):
    today = datetime.now()
    days_to_add = 1
    if level == "blur": days_to_add = 3
    elif level == "master": days_to_add = 7
    
    next_date = (today + timedelta(days=days_to_add)).strftime("%Y-%m-%d")
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/vocab?id=eq.{vocab_id}"
        r = requests.get(url + "&select=streak", headers=supabase_headers())
        current_streak = r.json()[0].get("streak", 0) if r.json() else 0
        
        if level == "forgot":
            payload = {"next_review_date": next_date, "streak": 0}
        elif level == "blur":
            payload = {"next_review_date": next_date, "streak": current_streak + 1}
        elif level == "master":
            payload = {"next_review_date": next_date, "streak": current_streak + 2}
            
        requests.patch(url, headers=supabase_headers(), json=payload)
    except:
        pass

def supabase_signup(email, password):
    url = f"{SUPABASE_URL}/rest/v1/users"
    chk = requests.get(url + f"?email=eq.{email}", headers=supabase_headers())
    if chk.status_code == 200 and chk.json():
        return {"error": "帳號已存在"}, 400
    
    mock_id = f"user_{int(time.time())}"
    payload = {"id": mock_id, "email": email, "password": password, "credits": 10}
    r = requests.post(url, headers=supabase_headers(), json=payload)
    if r.status_code in [200, 201]:
        return {"user": {"id": mock_id, "email": email}}, 200
    return {"error": "雲端註冊失敗"}, 400

def supabase_signin(email, password):
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        return {"user": {"id": "admin_root", "email": ADMIN_EMAIL}}, 200
    url = f"{SUPABASE_URL}/rest/v1/users?email=eq.{email}&password=eq.{password}"
    r = requests.get(url, headers=supabase_headers())
    if r.status_code == 200 and r.json():
        res = r.json()[0]
        return {"user": {"id": res["id"], "email": res["email"]}}, 200
    return {"error": "密碼或帳號錯誤"}, 400

def get_all_words(user_id):
    try:
        url = f"{SUPABASE_URL}/rest/v1/vocab?user_id=eq.{user_id}&order=id.desc"
        r = requests.get(url, headers=supabase_headers())
        if r.status_code == 200:
            rows = []
            for item in r.json():
                rows.append((
                    item.get("word"), item.get("definition"), item.get("grammar"),
                    item.get("mnemonic"), item.get("confusable"), item.get("sentences"),
                    item.get("next_review_date"), item.get("streak", 0), item.get("error_count", 0),
                    item.get("quiz_data"), item.get("id"), item.get("created_date")
                ))
            return rows
    except:
        pass
    return []

def tts_button(word, label="🔊 發音聆聽"):
    html_code = f"""
    <button onclick="window.speechSynthesis.speak(new SpeechSynthesisUtterance('{word}'))" 
    style="background-color: #2E7D32; color: white; border: none; padding: 6px 12px; 
    text-align: center; font-size: 13px; cursor: pointer; border-radius: 4px; margin: 2px;">
    {label}
    </button>
    """
    st.components.v1.html(html_code, height=45)

# ==========================================
# 2. Gemini AI 多維度核心資料打包生成
# ==========================================
def fetch_gemini_learning_package(word, api_key):
    word = word.strip().lower()
    
    # 【安全防護】如果忘記換 Key，直接擋下提示
    if "請在此處替換" in api_key or not api_key.startswith("AIzaSy"):
        st.error("❌ 偵測到未配置有效的 Gemini API 金鑰！請修改 app.py 第 15 行的 BACKEND_GEMINI_KEY。")
        return None
        
    try:
        # 🔥 強制在初始化時傳入指定金鑰，阻斷環境變數干擾
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
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
        )
        return json.loads(response.text.strip())
    except Exception as e:
        st.error(f"Gemini AI 生成失敗，請檢查管理員後台的 API Key 是否設定正確。錯誤訊息: {e}")
        return None

# ==========================================
# 3. 系統安全門禁中心
# ==========================================
if not st.session_state.logged_in:
    st.title("🧠 EchoBrain SRS 系統門禁安全中心")
    tab1, tab2 = st.tabs(["🔐 會員登入", "📝 新用戶註冊"])
    with tab1:
        login_email = st.text_input("電子郵件 (Email)", key="login_email_input")
        login_pwd = st.text_input("密碼 (Password)", type="password", key="login_pwd_input")
        if st.button("確認登入", key="btn_signin"):
            if login_email and login_pwd:
                res, code = supabase_signin(login_email.strip(), login_pwd)
                if code == 200:
                    st.session_state.logged_in = True
                    st.session_state.user_id = res["user"]["id"]
                    st.session_state.user_email = res["user"]["email"]
                    st.rerun()
                else:
                    st.error("❌ 帳號或密碼錯誤。")
    with tab2:
        reg_email = st.text_input("設定電子郵件 (Email)", key="reg_email_input")
        reg_pwd = st.text_input("設定密碼", type="password", key="reg_pwd_input")
        if st.button("註冊帳戶", key="btn_signup"):
            if reg_email and reg_pwd:
                res, code = supabase_signup(reg_email.strip(), reg_pwd)
                if code == 200: st.success("🎉 註冊成功！請切換至登入分頁。")
                else: st.error(f"❌ 註冊失敗: {res.get('error')}")
    st.stop()

# ==========================================
# 4. 後台系統主介面
# ==========================================
st.sidebar.title("🧠 EchoBrain SRS")
is_admin = (st.session_state.user_email == ADMIN_EMAIL)
st.sidebar.write(f"📧 帳號: {st.session_state.user_email}")
current_credits = get_user_credits(st.session_state.user_id)
st.sidebar.metric(label="💰 您的剩餘特訓點數", value=f"{current_credits} 點")

if st.sidebar.button("登出系統"):
    st.session_state.logged_in = False
    st.rerun()

tabs_list = ["📥 數據匯入中心", "🗂️ 字彙記憶庫", "⚔️ 七大維度特訓魔鬼測驗"]
if is_admin: tabs_list.append("⚙️ 👑 核心管理員後台")
main_tabs = st.tabs(tabs_list)

# ------------------------------------------
# 分頁 1: 數據匯入中心
# ------------------------------------------
with main_tabs[0]:
    st.header("📥 AI 數據打包匯入中心")
    input_word = st.text_input("請輸入英文字彙", key="import_word_input")
    custom_import_date = st.date_input("📅 設定此單字的「查詢/加入日期」：", value=datetime.now().date(), key="custom_import_date_picker")
    
    if st.button("啟動 Gemini AI 數據打包匯入", key="btn_import"):
        if not input_word.strip(): st.warning("請輸入單字。")
        elif current_credits < 1: st.error("❌ 點數不足！")
        else:
            with st.spinner("AI 正在打包數據..."):
                pkg = fetch_gemini_learning_package(input_word, BACKEND_GEMINI_KEY)
                if pkg:
                    if not is_admin: deduct_credit(st.session_state.user_id)
                    word_clean = input_word.strip().lower()
                    quiz_data_str = json.dumps(pkg, ensure_ascii=False)
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    chosen_date_str = custom_import_date.strftime("%Y-%m-%d")
                    
                    chk_url = f"{SUPABASE_URL}/rest/v1/vocab?user_id=eq.{st.session_state.user_id}&word=eq.{word_clean}"
                    r_chk = requests.get(chk_url, headers=supabase_headers())
                    
                    payload = {
                        "user_id": st.session_state.user_id, "word": word_clean,
                        "definition": pkg['definition'], "grammar": pkg['grammar'],
                        "mnemonic": pkg['mnemonic'], "confusable": pkg['confusable'],
                        "sentences": pkg['sentences'], "next_review_date": today_str,
                        "quiz_data": quiz_data_str, "created_date": chosen_date_str
                    }
                    
                    if r_chk.status_code == 200 and r_chk.json():
                        v_id = r_chk.json()[0]["id"]
                        requests.patch(f"{SUPABASE_URL}/rest/v1/vocab?id=eq.{v_id}", headers=supabase_headers(), json=payload)
                    else:
                        payload["streak"] = 0
                        payload["error_count"] = 0
                        requests.post(f"{SUPABASE_URL}/rest/v1/vocab", headers=supabase_headers(), json=payload)
                        
                    st.success(f"🎉 成功！單字「{word_clean}」已永久存入雲端，日期歸類為：{chosen_date_str}")
                    time.sleep(1)
                    st.rerun()

# ------------------------------------------
# 分頁 2: 字彙記憶庫
# ------------------------------------------
with main_tabs[1]:
    st.header("🗂️ 智能字彙記憶庫")
    filter_by_date_view = st.checkbox("📅 啟用查詢日期篩選功能（若關閉則顯示全部單字）", value=False, key="filter_date_vocab_toggle")
    
    all_words = get_all_words(st.session_state.user_id)
    
    if filter_by_date_view:
        selected_view_date = st.date_input("📅 請選擇查詢日期：", value=datetime.now().date(), key="vocab_review_date_input")
        target_date_str = selected_view_date.strftime("%Y-%m-%d")
        all_words = [w for w in all_words if (w[11] == target_date_str or (w[11] is None and w[6] == target_date_str))]
        
    if not all_words:
        st.info("此條件下目前沒有單字，您可以關閉日期篩選功能來查看所有單字！")
    else:
        search_query = st.text_input("🔍 關鍵字搜尋", "").strip().lower()
        filtered_words = [w for w in all_words if search_query in w[0] or search_query in w[1]]
        
        st.subheader(f"📊 字卡清單 共計 {len(filtered_words)} 筆")
        for w in filtered_words:
            w_word, w_def, w_gram, w_mne, w_conf, w_sent, w_date, w_streak, w_err, _, w_id, w_cdate = w
            display_cdate = w_cdate if w_cdate else w_date
            
            with st.container(border=True):
                col_left, col_mid, col_right = st.columns([2, 5, 2])
                with col_left:
                    st.subheader(f"🔤 {w_word}")
                    st.caption(f"📅 查詢日期: {display_cdate}")
                    tts_button(w_word, label="🔊 聽發音")
                with col_mid:
                    st.markdown(f"**核心釋義：** {w_def}")
                with col_right:
                    if st.button("🗑️ 刪除", key=f"del_{w_id}"):
                        requests.delete(f"{SUPABASE_URL}/rest/v1/vocab?id=eq.{w_id}", headers=supabase_headers())
                        st.rerun()
                        
                st.markdown("#### 🔍 大腦解構全景圖")
                card_col1, card_col2, card_col3 = st.columns(3)
                with card_col1: st.info(f"📋 **文法搭配公式**\n\n{w_gram}")
                with card_col2: st.success(f"🎯 **諧音口訣記憶**\n\n{w_mne}")
                with card_col3: st.warning(f"⚠️ **易混淆單字辨析**\n\n{w_conf}")

# ------------------------------------------
# 分頁 3: 七大維度特訓魔鬼測驗
# ------------------------------------------
with main_tabs[2]:
    st.header("⚔️ 七大維度特訓魔鬼測驗")
    filter_by_date_quiz = st.checkbox("📅 啟用測驗日期篩選功能（若關閉則載入所有單字）", value=False, key="filter_date_quiz_toggle")
    
    all_quiz_words = [w for w in get_all_words(st.session_state.user_id) if w[9]]
    
    if filter_by_date_quiz:
        selected_quiz_date = st.date_input("📅 請選擇要複習哪一天查的單字：", value=datetime.now().date(), key="quiz_review_date_input")
        target_quiz_date_str = selected_quiz_date.strftime("%Y-%m-%d")
        all_quiz_words = [w for w in all_quiz_words if (w[11] == target_quiz_date_str or (w[11] is None and w[6] == target_quiz_date_str))]
        
    if not all_quiz_words:
        st.info("目前無單字可供測驗。您可以取消勾選上方篩選功能，即可直接特訓所有查過的單字！")
    else:
        quiz_word_options = [w[0] for w in all_quiz_words]
        selected_quiz_word = st.selectbox("🎯 請選擇您想要特訓的單字：", quiz_word_options, key="select_quiz_word_main")
        
        target_word_record = [w for w in all_quiz_words if w[0] == selected_quiz_word][0]
        w_id = target_word_record[10]
        q_data = json.loads(target_word_record[9])
        
        st.markdown(f"### 🔏 當前淬鍊單字：**{selected_quiz_word.upper()}**")
        
        btn_s1, btn_s2, btn_s3 = st.columns(3)
        with btn_s1:
            if st.button("🔴 忘記了", key=f"anki_f_{w_id}", use_container_width=True):
                update_anki_schedule(w_id, "forgot")
                st.rerun()
        with btn_s2:
            if st.button("🟡 稍微模糊", key=f"anki_b_{w_id}", use_container_width=True):
                update_anki_schedule(w_id, "blur")
                st.rerun()
        with btn_s3:
            if st.button("🟢 完全熟練", key=f"anki_m_{w_id}", use_container_width=True):
                update_anki_schedule(w_id, "master")
                st.rerun()
        
        st.markdown("---")
        t1, t2, t3, t4, t5, t6 = st.tabs(["1. 拼寫題", "2. 片語題", "3. 文法填充", "4. 克漏字", "5. 盲聽題", "6. 重組題"])
        
        with t1:
            st.markdown(f"**提示（核心釋義）：** {target_word_record[1]}")
            ans_1 = st.text_input(f"請拼寫英文單字 (第一個字母為 {selected_quiz_word[0]}):", key=f"q1_{selected_quiz_word}").strip().lower()
            if st.button("提交答案", key=f"btn1_{selected_quiz_word}"):
                if ans_1 == selected_quiz_word: st.success("🎯 答對了！")
                else: st.error("❌ 拼寫錯誤。")
                    
        with t2:
            st.info(f"📋 **題目：**\n{q_data.get('phrase_q', '_______')}")
            options_2 = ["-- 請選擇 --"] + q_data.get("phrase_options", [])
            ans_2 = st.selectbox("請選擇正確介系詞：", options_2, key=f"q2_{selected_quiz_word}")
            if st.button("驗證片語搭配", key=f"btn2_{selected_quiz_word}"):
                if ans_2 == q_data.get("phrase_ans"): st.success("🎯 完全正確！")
                else: st.error(f"❌ 正確答案是【 {q_data.get('phrase_ans')} 】")
                    
        with t3:
            st.warning(f"💡 **文法線索：** {q_data.get('grammar_hint', '請注意詞性變化')}")
            st.info(f"📋 **題目：**\n{q_data.get('grammar_q', '_______')}")
            ans_3 = st.text_input("請輸入衍生型態：", key=f"q3_{selected_quiz_word}").strip()
            if st.button("驗證文法結構", key=f"btn3_{selected_quiz_word}"):
                if ans_3.lower() == q_data.get("grammar_ans", "").strip().lower(): st.success("🎯 正確！")
                else: st.error(f"❌ 應該是：【 {q_data.get('grammar_ans')} 】")
                    
        with t4:
            st.info(f"📖 **短文：**\n{q_data.get('cloze_q', '[  ]')}")
            ans_4 = st.radio("請選出正確字彙：", q_data.get("cloze_options", []), key=f"q4_{selected_quiz_word}")
            if st.button("驗證短文克漏字", key=f"btn4_{selected_quiz_word}"):
                if ans_4 == q_data.get("cloze_ans"): st.success("🎯 完全答對！")
                else: st.error(f"❌ 答案應為：【 {q_data.get('cloze_ans')} 】")
                    
        with t5:
            tts_button(selected_quiz_word, label="🔊 播放盲聽語音")
            ans_5 = st.text_input("請聽寫拼出單字：", key=f"q5_{selected_quiz_word}").strip().lower()
            if st.button("驗證聽寫答案", key=f"btn5_{selected_quiz_word}"):
                if ans_5 == selected_quiz_word: st.success("🎯 聽寫完全正確！")
                else: st.error("❌ 拼寫不吻合。")
                    
        with t6:
            raw_sentence = q_data.get("scrambled_sentence", "")
            translation = q_data.get("scrambled_translation", "")
            st.markdown(f"**🎯 中文翻譯目標：**\n*{translation}*")
            user_reorder_seq = st.multiselect("請『依序』選出單字重組句子：", options=list(set(raw_sentence.split())), key=f"mselect_{selected_quiz_word}")
            if st.button("提交整句重組判斷", key=f"btn6_{selected_quiz_word}"):
                user_str = " ".join(user_reorder_seq).strip().lower().replace(".", "").replace(",", "")
                correct_str = raw_sentence.strip().lower().replace(".", "").replace(",", "")
                if user_str == correct_str: st.success("🎯 重組成功！")
                else: st.error(f"❌ 順序有誤。解答為：{raw_sentence}")

# ------------------------------------------
# 👑 最高管理員後台功能（全套接回無刪減版）
# ------------------------------------------
if is_admin:
    with main_tabs[3]:
        st.header("👑 最高管理員戰略控制中心")
        
        # 核心加載函數
        def load_all_users_full():
            try:
                url = f"{SUPABASE_URL}/rest/v1/users?order=id.desc"
                r = requests.get(url, headers=supabase_headers())
                if r.status_code == 200:
                    return r.json()
            except:
                pass
            return []
            
        current_users_data = load_all_users_full()
        
        adm_tab1, adm_tab2, adm_tab3 = st.tabs(["📊 用戶名冊總覽", "🔑 學生密碼強制重設", "💰 學習點數儲值與扣除"])
        
        # 子分頁 1：總覽
        with adm_tab1:
            st.subheader("👥 現有註冊會員清單")
            if not current_users_data:
                st.info("目前雲端資料庫中尚無其他註冊會員。")
            else:
                table_rows = []
                for u in current_users_data:
                    table_rows.append({
                        "用戶識別碼 (ID)": u.get("id"),
                        "電子郵件 (Email)": u.get("email"),
                        "當前儲存密碼": u.get("password"),
                        "剩餘特訓點數": u.get("credits", 0)
                    })
                import pandas as pd
                st.dataframe(pd.DataFrame(table_rows), use_container_width=True)
                st.caption(f"💡 目前雲端總計有 {len(current_users_data)} 位註冊使用者")
                
        # 子分頁 2：變更密碼
        with adm_tab2:
            st.subheader("🔑 遠端強制更換密碼系統")
            if not current_users_data:
                st.warning("無任何學生帳號可供變更。")
            else:
                email_list_pwd = [u.get("email") for u in current_users_data if u.get("id") != "admin_root"]
                if not email_list_pwd:
                    st.info("目前只有管理員帳號，無一般學生帳號。")
                else:
                    selected_email_pwd = st.selectbox("請選擇要強制重設密碼的學生 Email：", email_list_pwd, key="sb_pwd_user")
                    new_assigned_pwd = st.text_input("請輸入全新密碼：", type="password", key="ti_new_pwd_field")
                    
                    if st.button("重設該帳號密碼", key="btn_execute_reset_pwd"):
                        if not new_assigned_pwd.strip():
                            st.error("密碼不可為空！")
                        else:
                            try:
                                update_url = f"{SUPABASE_URL}/rest/v1/users?email=eq.{selected_email_pwd}"
                                patch_res = requests.patch(update_url, headers=supabase_headers(), json={"password": new_assigned_pwd.strip()})
                                if patch_res.status_code in [200, 204]:
                                    st.success(f"🎉 成功！已將帳號 {selected_email_pwd} 的密碼變更為新密碼。")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("遠端更新失敗，請檢查資料庫權限設定。")
                            except Exception as ex:
                                st.error(f"系統錯誤: {ex}")
                                
        # 子分頁 3：增減點數
        with adm_tab3:
            st.subheader
