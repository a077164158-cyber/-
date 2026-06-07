import streamlit as st
import json
import datetime
import random
from google import genai
from google.genai import types
from supabase import create_client, Client

# ==========================================
# 🌟 核心連線設定（請在此處填入您的正確資訊）
# ==========================================
# 1. Supabase 雲端資料庫設定（請至 Supabase 後台 Project Settings -> API 複製）
SUPABASE_URL = "https://jcdakjtozepzktrlmpak.supabase.co"
SUPABASE_KEY = "sb_publishable_KCvBv7Uc12dLg_Od9aKyKg_XpVDLAoe"

# 2. Gemini AI 專用金鑰設定（⚠️ 請務必使用以 AIzaSy 開頭的正確金鑰）
BACKEND_GEMINI_KEY = "AQ.Ab8RN6Jmwzg4PyFZ8Lwnym_oIKXZaadXaBGHuPMSlNAewTe5Ww"

# 初始化 Supabase 用戶端
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 🛠️ 資料庫操作函數（全面改寫為 Supabase 雲端版）
# ==========================================
def db_login_user(email, password):
    """使用者登入與自動註冊機制"""
    try:
        # 尋找是否已有該 email 的使用者
        res = supabase.table("users").select("*").eq("email", email).execute()
        if res.data:
            user = res.data[0]
            if user["password"] == password:
                return user
            else:
                return "WRONG_PASSWORD"
        else:
            # 沒註冊過，自動幫他註冊
            user_id = f"user_{int(datetime.datetime.now().timestamp())}_{random.randint(100,999)}"
            new_user = {
                "id": user_id,
                "email": email,
                "password": password,
                "credits": 20  # 註冊送 20 點
            }
            supabase.table("users").insert(new_user).execute()
            return new_user
    except Exception as e:
        st.error(f"資料庫連線異常: {e}")
        return None

def db_get_user_credits(user_id):
    """取得使用者目前剩餘點數"""
    try:
        res = supabase.table("users").select("credits").eq("id", user_id).execute()
        if res.data:
            return res.data[0]["credits"]
        return 0
    except:
        return 0

def db_deduct_credit(user_id):
    """成功查詢單字時扣除 1 點"""
    try:
        current_credits = db_get_user_credits(user_id)
        if current_credits > 0:
            supabase.table("users").update({"credits": current_credits - 1}).eq("id", user_id).execute()
            return True
        return False
    except:
        return False

def get_all_words(user_id):
    """獲取該使用者的所有單字庫"""
    try:
        res = supabase.table("vocab").select("*").eq("user_id", user_id).execute()
        return res.data if res.data else []
    except Exception as e:
        st.error(f"讀取單字庫失敗: {e}")
        return []

def save_word_to_db(user_id, word, data):
    """將 Gemini 生成的完整大禮包儲存到雲端"""
    try:
        # 先檢查這個單字是不是已經在該使用者的庫中了
        res = supabase.table("vocab").select("id").eq("user_id", user_id).eq("word", word).execute()
        
        vocab_data = {
            "user_id": user_id,
            "word": word,
            "definition": data.get("definition", ""),
            "grammar": data.get("grammar", ""),
            "mnemonic": data.get("mnemonic", ""),
            "confusable": data.get("confusable", ""),
            "sentences": data.get("sentences", ""),
            "phrase_q": data.get("phrase_q", ""),
            "phrase_options": json.dumps(data.get("phrase_options", [])),
            "phrase_ans": data.get("phrase_ans", ""),
            "grammar_hint": data.get("grammar_hint", ""),
            "grammar_q": data.get("grammar_q", ""),
            "grammar_ans": data.get("grammar_ans", ""),
            "cloze_q": data.get("cloze_q", ""),
            "cloze_options": json.dumps(data.get("cloze_options", [])),
            "cloze_ans": data.get("cloze_ans", ""),
            "scrambled_sentence": data.get("scrambled_sentence", ""),
            "scrambled_translation": data.get("scrambled_translation", ""),
            "quiz_data": json.dumps(data),
            "next_review_date": datetime.date.today().strftime("%Y-%m-%d"),
            "created_date": datetime.date.today().strftime("%Y-%m-%d")
        }
        
        if res.data:
            # 存在就更新
            supabase.table("vocab").update(vocab_data).eq("user_id", user_id).eq("word", word).execute()
        else:
            # 不存在就新增
            supabase.table("vocab").insert(vocab_data).execute()
        return True
    except Exception as e:
        st.error(f"儲存單字庫失敗: {e}")
        return False

def update_review_date(word_id, is_correct):
    """更新複習時間與錯誤次數"""
    try:
        res = supabase.table("vocab").select("wrong_count").eq("id", word_id).execute()
        if not res.data:
            return
        
        current_wrong = res.data[0]["wrong_count"] or 0
        
        if is_correct:
            # 答對了，天數加長
            days_to_add = 3 if current_wrong == 0 else 1
            next_date = (datetime.date.today() + datetime.timedelta(days=days_to_add)).strftime("%Y-%m-%d")
            new_wrong = max(0, current_wrong - 1)
        else:
            # 答錯了，明天立刻複習，且加重錯誤次數
            next_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            new_wrong = current_wrong + 1
            
        supabase.table("vocab").update({
            "next_review_date": next_date,
            "wrong_count": new_wrong
        }).eq("id", word_id).execute()
    except Exception as e:
        st.error(f"更新複習進度失敗: {e}")

# ==========================================
# 🤖 Gemini AI 核心處理（確保使用前端或後端金鑰）
# ==========================================
def fetch_gemini_learning_package(word, api_key):
    word = word.strip().lower()
    
    # 金鑰基本防禦性防護
    if "請在此處替換" in api_key or not api_key.startswith("AIzaSy"):
        st.error("❌ 偵測到無效的 Gemini API 金鑰！請至 app.py 第 17 行配置正確的 BACKEND_GEMINI_KEY。")
        return None
        
    try:
        # 🔥 強制在宣告 Client 時帶入金鑰，徹底隔絕環境變數衝突
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
        st.error(f"Gemini AI 核心生成失敗，請檢查金鑰設定。錯誤訊息: {e}")
        return None

# ==========================================
# 🎨 Streamlit 網頁前端 UI 介面
# ==========================================
st.set_page_config(page_title="AI 數據打包匯入中心", page_icon="📥", layout="wide")

if "user_id" not in st.session_state:
    st.title("🔐 AI 智慧單字特訓系統 - 登入 / 註冊")
    st.write("輸入常用的 Email 與密碼即可開始使用。若為全新帳號系統將全自動為您建立。")
    
    with st.form("login_form"):
        email = st.text_input("電子郵件 (Email)", placeholder="example@gmail.com")
        password = st.text_input("密碼", type="password")
        submit = st.form_submit_with_name("確認登入 / 自動註冊")
        
        if submit:
            if not email or not password:
                st.warning("請填寫完整資訊！")
            else:
                user = db_login_user(email, password)
                if user == "WRONG_PASSWORD":
                    st.error("密碼輸入錯誤，請再試一次！")
                elif user:
                    st.session_state.user_id = user["id"]
                    st.session_state.email = user["email"]
                    st.success("🎉 登入成功！正在載入特訓中心...")
                    st.rerun()
    st.stop()

# 頂部導覽列與狀態
user_credits = db_get_user_credits(st.session_state.user_id)
st.sidebar.markdown(f"### 👤 帳號: `{st.session_state.email}`")
st.sidebar.markdown(f"### 🪙 剩餘特訓點數: **{user_credits}** 點")
if st.sidebar.button("登出帳號"):
    del st.session_state.user_id
    st.rerun()

menu = st.tabs(["📥 AI 數據打包匯入中心", "📚 我的大腦字卡單字庫", "🎯 每日大腦核心特訓"])

# --- TAB 1: 匯入中心 ---
with menu[0]:
    st.title("📥 AI 數據打包匯入中心")
    st.write("輸入你想特訓的英文單字，Gemini AI 將為你全自動生成包含 7 大題型與文法聯想的 SRS 學習字卡。")
    
    st.info("💡 系統規定：每成功查詢打包一個單字，將扣除 1 點特訓點數。")
    
    input_word = st.text_input("請輸入英文字彙 (例如: vulnerable, alternative)", key="search_input_word").strip()
    
    if st.button("啟動 Gemini AI 數據打包匯入"):
        if not input_word:
            st.warning("請先輸入單字！")
        elif user_credits <= 0:
            st.error("❌ 您的特訓點數已耗盡，無法打包數據！請聯絡管理員充值。")
        else:
            with st.spinner("🚀 Gemini AI 正在對大腦進行高速深度聯想與數據打包，請稍候..."):
                res_json = fetch_gemini_learning_package(input_word, BACKEND_GEMINI_KEY)
                if res_json:
                    deduct_success = db_deduct_credit(st.session_state.user_id)
                    if deduct_success:
                        save_word_to_db(st.session_state.user_id, input_word.lower(), res_json)
                        st.success(f"🎉 單字 '{input_word}' 數據打包完美成功！已安全同步儲存至您的雲端字卡庫 (扣除 1 點)。")
                        
                        st.markdown(f"### 核心釋義：**{res_json.get('definition')}**")
                        with st.expander("🔍 檢視完整大腦解構（文法公式、諧音聯想與易混淆字）", expanded=True):
                            st.markdown(f"### 📋 文法搭配公式\n{res_json.get('grammar')}")
                            st.markdown(f"### 🎯 諧音口訣記憶\n{res_json.get('mnemonic')}")
                            st.markdown(f"### ⚠️ 易混淆字辨析\n{res_json.get('confusable')}")
                    else:
                        st.error("扣點失敗，終止匯入作業。")

# --- TAB 2: 我的字卡庫 ---
with menu[1]:
    st.title("📚 我的大腦字卡單字庫")
    all_words = get_all_words(st.session_state.user_id)
    
    if not all_words:
        st.write("目前您的字卡庫空空如也，快去匯入中心打包第一個單字吧！")
    else:
        st.write(f"目前共儲存了 **{len(all_words)}** 個高頻單字大禮包：")
        for w in all_words:
            with st.expander(f"🔐 {w['word'].upper()} — {w['definition']}"):
                st.markdown(f"### 📝 文法與搭配結構\n{w['grammar']}\n")
                st.markdown(f"### 🎯 幽默諧音口訣\n{w['mnemonic']}\n")
                st.markdown(f"### ⚠️ 易混淆單字辨析\n{w['confusable']}\n")
                
                st.markdown("### 🗣️ 精選核心場景例句")
                if w['sentences']:
                    for sent_pair in w['sentences'].split("###"):
                        if "||" in sent_pair:
                            eng, zht = sent_pair.split("||")
                            st.markdown(f"• **{eng}**\n  *{zht}*")

# --- TAB 3: 每日特訓 ---
with menu[2]:
    st.title("🎯 每日大腦核心特訓")
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    all_words = get_all_words(st.session_state.user_id)
    
    # 篩選出今天或以前需要複習的單字
    review_pool = [w for w in all_words if (w.get('next_review_date') or today_str) <= today_str]
    
    if not review_pool:
        st.balloons()
        st.success("☀️ 太棒了！您今天所有的大腦單字特訓進度皆已全部達標！請明天繼續保持！")
    else:
        st.warning(f"⚡ 偵測到大腦目前有 **{len(review_pool)}** 個單字的核心連結正在轉弱，請立刻啟動特訓：")
        
        # 固定取 pool 裡面的第一個進行特訓
        selected_quiz = review_pool[0]
        st.info(f"當前特訓目標單字：🧱 **{selected_quiz['word'].upper()}**")
        
        quiz_raw = selected_quiz.get('quiz_data')
        if quiz_raw:
            try:
                q_data = json.loads(quiz_raw)
            except:
                q_data = selected_quiz
        else:
            q_data = selected_quiz

        # 題型 1: 片語介系詞挖空選擇題
        st.markdown("---")
        st.markdown("### 🌟 階段一：核心片語與介系詞搭配特訓")
        st.markdown(f"**題目：** {q_data.get('phrase_q')}")
        
        p_opts = q_data.get('phrase_options', [])
        if isinstance(p_opts, str):
            try: p_opts = json.loads(p_opts)
            except: p_opts = []
            
        ans_phrase = st.radio("請選擇正確的介系詞/搭配詞：", p_opts, key=f"r1_{selected_quiz['id']}")
        if st.button("驗證片語答案", key=f"btn1_{selected_quiz['id']}"):
            if ans_phrase == q_data.get('phrase_ans'):
                st.success("🎯 完全正確！大腦皮質連結加深！")
                update_review_date(selected_quiz['id'], is_correct=True)
            else:
                st.error(f"❌ 答錯了！正確答案應該是：【{q_data.get('phrase_ans')}】。此字明天將重新特訓。")
                update_review_date(selected_quiz['id'], is_correct=False)
                
        # 題型 2: 衍生文法形變填充題
        st.markdown("---")
        st.markdown("### 🌟 階段二：高頻文法詞性衍生變形特訓")
        st.markdown(f"**題目句：** {q_data.get('grammar_q')}")
        st.caption(f"💡 大腦提示：{q_data.get('grammar_hint')}")
        
        ans_grammar = st.text_input("請手寫輸入空格處單字的正確衍生變形：", key=f"t2_{selected_quiz['id']}").strip()
        if st.button("驗證文法結構", key=f"btn2_{selected_quiz['id']}"):
            if ans_grammar.lower() == str(q_data.get('grammar_ans')).lower().strip():
                st.success("🎯 完美答對！您的核心文法思維非常精準！")
                update_review_date(selected_quiz['id'], is_correct=True)
            else:
                st.error(f"❌ 結構出錯！正確形變答案應為：【{q_data.get('grammar_ans')}】")
                update_review_date(selected_quiz['id'], is_correct=False)

        # 題型 3: 情境克漏字極限辨析
        st.markdown("---")
        st.markdown("### 🌟 階段三：全面情境邏輯克漏字特訓")
        st.markdown(f"**短文情境：**\n{q_data.get('cloze_q')}")
        
        c_opts = q_data.get('cloze_options', [])
        if isinstance(c_opts, str):
            try: c_opts = json.loads(c_opts)
            except: c_opts = []
            
        ans_cloze = st.selectbox("根據前後文邏輯，[  ] 內應填入哪個單字？", c_opts, key=f"s3_{selected_quiz['id']}")
        if st.button("驗證克漏字邏輯", key=f"btn3_{selected_quiz['id']}"):
            if ans_cloze == q_data.get('cloze_ans'):
                st.success("🎯 答對了！您成功攻克了這個核心情境短文！")
                update_review_date(selected_quiz['id'], is_correct=True)
            else:
                st.error(f"❌ 邏輯偏移！正確答案應為本字：【{q_data.get('cloze_ans')}】")
                update_review_date(selected_quiz['id'], is_correct=False)
