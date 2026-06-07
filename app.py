import streamlit as st
import sqlite3
import datetime
import random
import json
import pandas as pd
import time
from google import genai
from google.genai import types

# ==========================================
# 1. 資料庫初始化
# ==========================================
def init_db():
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vocab 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  word TEXT UNIQUE, 
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
    conn.commit()
    conn.close()

# ==========================================
# 2. Google AI Studio (Gemini API) 數據大模組串接
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
      "grammar_q": "一個精心設計的『文法多模態辨析題』，完美模擬多益或高階英文檢定。空格用 ________ 代替。\\n請從以下兩大類別中『隨機挑選一種最適合該字衍生發展』的方式來出題，確保題型極具多樣性：\\n1.【詞性衍生多樣化變化】：設計一個需要填入該字之『名詞形』替代、或是其『形容詞形』、『副詞形』的專業句子。\\n2.【動詞進階時態/語態】：若該字非常適合考時態，請設計一個需要『過去式』、『過去分詞』、『現在分詞』或『被動語態』的句子。",
      "grammar_options": ["選項1", "選項2", "選項3", "選項4"],
      "grammar_ans": "必須是 grammar_options 中唯一符合句子語法結構（如名詞、形容詞、副詞或特定時態）的正確衍生變形單字答案",
      "cloze_q": "一段包含2-3個句子的完整情境短文克漏字，將本字挖空寫成 [   ]。",
      "cloze_options": ["本字原形", "干擾字1", "干擾字2", "干擾字3"],
      "cloze_ans": "本字原形",
      "sentences": "第一句高階商務或生活英文例句||💡 中文翻譯###第二句高階商務或生活英文例句||💡 中文翻譯"
    }}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
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
            if "503" in str(e) and attempt < max_retries - 1:
                time.sleep(3)
                continue
            st.error(f"Gemini AI 核心生成失敗。錯誤訊息: {e}")
            return None

# ==========================================
# 3. Anki / SRS 演算法調控
# ==========================================
def apply_anki_scheduling(word, is_correct, quality_override=None):
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("SELECT ease_factor, interval, streak, error_count, success_count FROM vocab WHERE word=?", (word,))
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
                     streak=?, error_count=?, success_count=? WHERE word=?''',
                  (ease_factor, interval, str(next_review), streak, error_count, success_count, word))
        conn.commit()
    conn.close()

# ==========================================
# 4. 輔助功能與發音
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


def get_all_words():
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("SELECT word, definition, grammar, mnemonic, confusable, sentences, next_review_date, streak, error_count FROM vocab ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows


def get_due_words():
    today_str = str(datetime.date.today())
    conn = sqlite3.connect('anki_vocab.db')
    c = conn.cursor()
    c.execute("SELECT word, definition, grammar, mnemonic, confusable, sentences, error_count, phrase_q, phrase_options, phrase_ans, grammar_q, grammar_options, grammar_ans, cloze_q, cloze_options, cloze_ans FROM vocab WHERE next_review_date <= ? OR interval = 0", (today_str,))
    rows = c.fetchall()
    conn.close()
    return rows

# ==========================================
# 5. 主介面設計
# ==========================================
def main():
    init_db()
    st.set_page_config(page_title="EchoBrain SRS 智慧英文特訓系統", layout="wide")
    st.title("🧠 EchoBrain SRS 全維度大腦記憶特訓系統")
    
    # ----------------------------------------
    # 🛠️ 側邊欄：萬用安全自動載入 API Key 機制
    # ----------------------------------------
    st.sidebar.header("🔑 Google AI Studio 設定")
    try:
        default_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        default_key = ""

    gemini_key = st.sidebar.text_input(
        "輸入 Gemini API Key", 
        value=default_key, 
        type="password", 
        placeholder="AIzaSy..."
    )

    if not gemini_key:
        st.sidebar.warning("⚠️ 請先在 .streamlit/secrets.toml 設定 Key 或是手動輸入！")
    else:
        if gemini_key == default_key:
            st.sidebar.success("✅ 已自動從 secrets.toml 載入您的專屬金鑰")
        else:
            st.sidebar.success("✅ 已成功載入手動輸入的金鑰")
        
    all_data = get_all_words()
    due_data = get_due_words()
    
    st.sidebar.markdown("---")
    st.sidebar.header("📊 本日任務進度")
    st.sidebar.metric(label="總收藏字數", value=len(all_data))
    st.sidebar.metric(label="待複習 (Anki 排程)", value=len(due_data))
    
    menu = ["📥 AI 智慧匯入單字", "🎯 智慧多維度測驗", "📊 完整字彙統計", "📕 核心錯題本", "📖 全字彙記憶庫"]
    choice = st.sidebar.selectbox("切換面板", menu)
    
    if choice == "📥 AI 智慧匯入單字":
        st.subheader("📥 Gemini AI 智慧記憶大禮包生成（串接 gemini-2.5-flash）")
        
        words_input = st.text_area("請輸入英文單字（支援換行或逗號分隔）", placeholder="criticize\npersistent\ninnovate")
        
        if st.button("啟動 Gemini AI 數據打包匯入"):
            if not gemini_key:
                st.error("拒絕執行：缺乏 API Key，無法產生高質量解析。")
                return
            
            raw_list = words_input.replace("\n", ",").split(",")
            word_list = [w.strip() for w in raw_list if w.strip()]
            
            if not word_list:
                st.warning("請輸入單字內容。")
            else:
                conn = sqlite3.connect('anki_vocab.db')
                c = conn.cursor()
                success_num = 0
                
                total_words = len(word_list)
                progress_bar = st.progress(0)
                
                for idx, w in enumerate(word_list):
                    c.execute("SELECT id FROM vocab WHERE word=?", (w,))
                    if c.fetchone():
                        c.execute("UPDATE vocab SET interval=0, next_review_date=? WHERE word=?", (str(datetime.date.today()), w))
                        success_num += 1
                        progress_bar.progress((idx + 1) / total_words)
                        continue
                    
                    with st.spinner(f"({idx+1}/{total_words}) Gemini AI 正在為單字 【{w}】 深度定制學習大禮包..."):
                        pkg = fetch_gemini_learning_package(w, gemini_key)
                        
                    if pkg:
                        c.execute('''INSERT INTO vocab (
                                        word, definition, grammar, mnemonic, confusable, sentences, date_added, next_review_date,
                                        phrase_q, phrase_options, phrase_ans, grammar_q, grammar_options, grammar_ans,
                                        cloze_q, cloze_options, cloze_ans
                                     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                                  (w, pkg["definition"], pkg["grammar"], pkg["mnemonic"], pkg["confusable"], pkg["sentences"],
                                   str(datetime.date.today()), str(datetime.date.today()),
                                   pkg["phrase_q"], json.dumps(pkg["phrase_options"], ensure_ascii=False), pkg["phrase_ans"],
                                   pkg["grammar_q"], json.dumps(pkg["grammar_options"], ensure_ascii=False), pkg["grammar_ans"],
                                   pkg["cloze_q"], json.dumps(pkg["cloze_options"], ensure_ascii=False), pkg["cloze_ans"]))
                        success_num += 1
                        time.sleep(3.5)
                    progress_bar.progress((idx + 1) / total_words)
                    
                conn.commit()
                conn.close()
                st.success(f"🎉 成功！已透過 Gemini AI 完美生成並導入 {success_num} 個單字的專屬多維度記憶特訓卡。")

    elif choice == "🎯 智慧多維度測驗":
        st.subheader("✍️ 實戰多維度全題型演練")
        mode = st.radio("出題模式：", ["依 Anki 演算法排程", "指定特定匯入日期抽考"])
        
        if mode == "依 Anki 演算法排程":
            quiz_pool = get_due_words()
        else:
            target_date = st.date_input("選擇抽考哪天匯入的單字：", datetime.date.today())
            conn = sqlite3.connect('anki_vocab.db')
            c = conn.cursor()
            c.execute("SELECT word, definition, grammar, mnemonic, confusable, sentences, error_count, phrase_q, phrase_options, phrase_ans, grammar_q, grammar_options, grammar_ans, cloze_q, cloze_options, cloze_ans FROM vocab WHERE date_added=?", (str(target_date),))
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
                            is_correct = (user_ans == word.lower())
                            st.session_state.ans_status = ("checked", is_correct, word, word)
                
                elif q_type == 'B':
                    st.info(f"🔗 **【核心片語固定搭配題】**\n\n請選出最符合句意與習慣用法的固定介系詞或片語搭配：")
                    st.markdown(f"**題目:** {phrase_q if phrase_q else 'Missing text'}")
                    opts = json.loads(phrase_options_str) if phrase_options_str else ["A", "B", "C", "D"]
                    with st.form(key=f"form_B_{idx}"):
                        user_ans = st.radio("選擇答案：", opts)
                        if st.form_submit_button("送出判定"):
                            is_correct = (user_ans.strip().lower() == phrase_ans.strip().lower())
                            st.session_state.ans_status = ("checked", is_correct, phrase_ans, word)
                            
                elif q_type == 'C':
                    st.info(f"📊 **【語法結構與全衍生詞性辨析題】**\n\n請仔細分析句子結構（名詞/形容詞/副詞/時態），選出唯一符合語法的正確變形選項：")
                    st.markdown(f"**題目:** {grammar_q if grammar_q else 'Missing text'}")
                    opts = json.loads(grammar_options_str) if grammar_options_str else ["A", "B", "C", "D"]
                    with st.form(key=f"form_C_{idx}"):
                        user_ans = st.radio("選擇答案：", opts)
                        if st.form_submit_button("送出判定"):
                            is_correct = (user_ans.strip().lower() == grammar_ans.strip().lower())
                            st.session_state.ans_status = ("checked", is_correct, grammar_ans, word)

                elif q_type == 'D':
                    st.info(f"📝 **【進階情境段落克漏字】**\n\n閱讀情境短文，選出最適合填入空格 [   ] 的單字：")
                    st.code(cloze_q if cloze_q else "Missing Cloze Text", language="text")
                    opts = json.loads(cloze_options_str) if cloze_options_str else ["A", "B", "C", "D"]
                    with st.form(key=f"form_D_{idx}"):
                        user_ans = st.radio("選擇答案：", opts)
                        if st.form_submit_button("送出判定"):
                            is_correct = (user_ans.strip().lower() == cloze_ans.strip().lower())
                            st.session_state.ans_status = ("checked", is_correct, cloze_ans, word)

                if st.session_state.ans_status:
                    _, is_match, correct_answer_display, target_word = st.session_state.ans_status
                    st.markdown("---")
                    
                    if is_match:
                        st.success(f"🎉 答對了！")
                    else:
                        st.error(f"❌ 答錯了！本題的正確答案應該是： **{correct_answer_display}**")
                        if q_type in ['B', 'C', 'D']:
                            st.warning(f"💡 本題測驗對應的核心原形目標單字為： **{target_word}**")
                    
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
                            apply_anki_scheduling(target_word, is_correct=False)
                            st.session_state.srs_idx += 1
                            st.session_state.ans_status = None
                            st.rerun()
                    with c2:
                        if st.button("👌 普通/勉強答對 (3-4天後複習)"):
                            apply_anki_scheduling(target_word, is_correct=is_match, quality_override=3)
                            st.session_state.srs_idx += 1
                            st.session_state.ans_status = None
                            st.rerun()
                    with c3:
                        if st.button("👍 記得很熟! (大幅拉長週期)"):
                            apply_anki_scheduling(target_word, is_correct=is_match, quality_override=5)
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
        
        c.execute("SELECT COUNT(*) FROM vocab WHERE streak >= 4")
        mastered_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM vocab WHERE streak > 0 AND streak < 4")
        learning_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM vocab WHERE streak = 0")
        new_cnt = c.fetchone()[0]
        
        c.execute("SELECT word, error_count FROM vocab WHERE error_count > 0 ORDER BY error_count DESC LIMIT 7")
        top_errors = c.fetchall()
        conn.close()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("總字庫容量", len(all_data))
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
                pie_df = pd.DataFrame(pie_data).set_index("狀態")
                st.bar_chart(pie_df)
                st.caption("說明：連勝達 4 次以上的單字會自動歸類為『精熟』。")
                
        with col_chart2:
            st.markdown("#### 🚨 核心高頻錯題大魔王排行榜 (Top 7)")
            if not top_errors:
                st.success("🎉 目前沒有任何答錯單字！太棒了！")
            else:
                err_dict = {
                    "單字": [x[0] for x in top_errors],
                    "答錯次數": [x[1] for x in top_errors]
                }
                err_df = pd.DataFrame(err_dict).set_index("單字")
                st.bar_chart(err_df)

    elif choice == "📕 核心錯題本":
        st.subheader("🚨 高頻錯字重點攻克本")
        conn = sqlite3.connect('anki_vocab.db')
        c = conn.cursor()
        c.execute("SELECT word, definition, grammar, mnemonic, confusable, error_count, sentences FROM vocab WHERE error_count > 0 ORDER BY error_count DESC")
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
                    st.markdown("**📝 精選翻譯例句：**")
                    if sents:
                        for s in sents.split("###"):
                            if "||" in s: st.write(f"👉 *{s.split('||')[0]}*\n   ↳ {s.split('||')[1]}")

    elif choice == "📖 全字彙記憶庫":
        st.subheader("🔍 整合記憶狀態庫")
        search = st.text_input("輸入關鍵字搜尋（英漢皆可）：")
        words = get_all_words()
        
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
        else:
            st.info("尚無符合條件的字庫資料。")

if __name__ == "__main__":
    main()
