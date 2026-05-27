import os
import sqlite3
import streamlit as st
import pandas as pd
import io
import zipfile
import time
from parser import HHParser
import main as orchestrator

st.set_page_config(
    page_title="QA Smart Assistant & Analytics",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stMetricValue"] { font-size: 26px; font-weight: 700; color: #1E3A8A; }
    .vacancy-card { background-color: #ffffff; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 15px; }
    .letter-body {
        background-color: #1e1e1e; color: #ffffff; padding: 15px; border-radius: 8px;
        font-family: monospace; white-space: pre-wrap; word-wrap: break-word; overflow-x: hidden;
    }
    .recommendation-box {
        background-color: #eff6ff; color: #1e3a8a; padding: 18px; border-radius: 8px;
        border-left: 5px solid #3b82f6; margin-top: 15px; margin-bottom: 15px; font-size: 15px;
    }
    div[data-testid="stHorizontalBlock"] > div:nth-child(2) path.mark-rect.role-mark { fill: #ff4b4b !important; stroke: #ff4b4b !important; }
    </style>
""", unsafe_allow_html=True)


def load_db_data():
    if not os.path.exists("data/processed_vacancies.db"):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect("data/processed_vacancies.db")
        df = pd.read_sql_query("SELECT id, title, company, salary_min, salary_max, status FROM vacancies", conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Ошибка чтения БД: {e}")
        return pd.DataFrame()


def generate_zip_of_covers():
    zip_buffer = io.BytesIO()
    if os.path.exists("covers"):
        files = [f for f in os.listdir("covers") if f.endswith(".txt")]
        if not files:
            return None
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for f_name in files:
                f_path = os.path.join("covers", f_name)
                zip_file.write(f_path, f_name)
        return zip_buffer.getvalue()
    return None


if 'db_updated' not in st.session_state:
    st.session_state['db_updated'] = False

with st.sidebar:
    st.title("📝 Параметры поиска")

    search_keyword = st.text_input("Ключевое слово для hh.ru:", value="QA Engineer")
    exclude_words = st.text_input("Исключить слова (через запятую):", value="Senior, Lead, Стажер")

    experience_opt = st.selectbox(
        "Опыт работы:",
        options=["noExperience", "between1And3", "between3And6", "moreThan6"],
        index=1,
        format_func=lambda x: {"noExperience": "Без опыта", "between1And3": "1–3 года", "between3And6": "3–6 лет",
                               "moreThan6": "Более 6 лет"}[x]
    )

    schedule_opt = st.selectbox(
        "График работы:",
        options=["remote", "fullDay", "flexible", "flyInFlyOut"],
        index=0,
        format_func=lambda x: {"remote": "Удаленная работа", "fullDay": "Полный день", "flexible": "Гибкий график",
                               "flyInFlyOut": "Вахтовый метод"}[x]
    )

    area_opt = st.selectbox(
        "Регион поиска:",
        options=[113, 1, 2, 88],
        index=0,
        format_func=lambda x: {113: "Вся Россия", 1: "Москва", 2: "Санкт-Петербург", 88: "Казань"}[x]
    )

    ui_proxy = st.text_input("Прокси-сервер (если нужен):", value="")
    st.write("---")

    zip_data = generate_zip_of_covers()
    if zip_data:
        st.download_button("Скачать письма (.ZIP)", data=zip_data, file_name="cover_letters.zip",
                           mime="application/zip", width="stretch")

st.title("💼 QA Smart Assistant & Market Analytics")
st.write("---")

tab1, tab2 = st.tabs(["✉️ Подбор вакансий и генерация писем", "📊 Аналитическая панель"])

with tab1:
    st.subheader("Шаг 1: Разведка рынка вакансий")
    btn_scout = st.button("🔍 Найти и подгрузить свежие вакансии с hh.ru", type="primary", width="stretch")

    if btn_scout:
        with st.spinner("Безопасный поиск вакансий с обходом антифрода..."):
            orchestrator.run_scout_process(
                keyword=search_keyword, exclude=exclude_words, experience=experience_opt,
                schedule=schedule_opt, area=area_opt, proxy_url=ui_proxy
            )
        st.success("Сканирование завершено!")
        st.session_state['db_updated'] = not st.session_state['db_updated']
        st.rerun()

    st.write("---")
    df_all = load_db_data()

    if not df_all.empty:
        st.subheader("📋 Шаг 2: Выберите галочками вакансии для генерации:")
        df_show = df_all[df_all['status'] == 'discovered'].copy()

        if df_show.empty:
            st.info("В базе нет новых необработанных позиций.")
        else:
            df_show.insert(0, "Выбрать", False)
            edited_df = st.data_editor(df_show, hide_index=True,
                                       column_config={"Выбрать": st.column_config.CheckboxColumn(required=True)},
                                       width="stretch")

            if st.button("✨ Сгенерировать сопроводительные письма для ВЫБРАННЫХ позиций", width="stretch"):
                selected_rows = edited_df[edited_df["Выбрать"] == True]
                if not selected_rows.empty:
                    progress_text = st.empty()
                    bar = st.progress(0)
                    total = len(selected_rows)

                    for idx, row in enumerate(selected_rows.itertuples()):
                        progress_text.write(f"Генерация ИИ для: **{row.company} — {row.title}**")
                        success, error_msg = orchestrator.run_generation_process(v_id=row.id, feedback_text="",
                                                                                 proxy_url=ui_proxy)
                        if not success:
                            st.error(f"Ошибка: {error_msg}")
                            st.stop()
                        bar.progress((idx + 1) / total)

                    st.success(f"Успешно сгенерировано писем: {total}!")
                    st.session_state['db_updated'] = not st.session_state['db_updated']
                    st.rerun()

        st.write("---")
        st.subheader("📂 Шаг 3: Просмотр, копирование и корректировка готовых писем")
        files = [f for f in os.listdir("covers") if f.endswith(".txt")] if os.path.exists("covers") else []
        if files:
            clean_names = [f.replace(".txt", "").replace("_", " ") for f in files]
            file_mapping = dict(zip(clean_names, files))
            selected_clean = st.selectbox("Выберите готовое письмо для работы:", clean_names)

            if selected_clean:
                current_file = file_mapping[selected_clean]
                with open(os.path.join("covers", current_file), "r", encoding="utf-8") as f:
                    content = f.read()

                parts = content.split("==================================================")
                st.markdown("<div class='vacancy-card'>", unsafe_allow_html=True)

                v_id = None
                if len(parts) > 1:
                    meta_block = parts[0].strip()
                    main_body_block = parts[1].strip()

                    FILE_SEPARATOR = "\n\n===SYSTEM_RECOMMENDATIONS_SPLIT_MARKER===\n\n"
                    letter_parts = main_body_block.split(FILE_SEPARATOR)
                    clean_letter = letter_parts[0].strip()
                    clean_recommendations = letter_parts[1].strip() if len(
                        letter_parts) > 1 else "Изучите ключевые требования вакансии."

                    url_link = "https://hh.ru"
                    v_company = "Компания"
                    v_title = "Vacancy"

                    for line in meta_block.split("\n"):
                        if "ССЫЛКА НА ВАКАНСИЮ:" in line:
                            url_link = line.replace("ССЫЛКА НА ВАКАНСИЮ:", "").strip()
                            v_id = url_link.split("/vacancy/")[1].strip()
                        elif "КОМПАНИЯ:" in line:
                            v_company = line.replace("КОМПАНИЯ:", "").strip()
                        elif "ВАКАНСИЯ:" in line:
                            v_title = line.replace("ВАКАНСИЯ:", "").strip()
                        else:
                            st.markdown(f"**{line}**")

                    st.link_button("🔗 Открыть эту вакансию на hh.ru", url_link, type="secondary")

                    st.markdown("<div class='recommendation-box'>", unsafe_allow_html=True)
                    st.markdown(f"🎯 **Рекомендации ИИ по подготовке к собеседованию в {v_company}:**")
                    st.write(clean_recommendations)
                    st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown("---")
                    st.write("💡 **Текущий текст сопроводительного письма:**")
                    st.markdown(f"<div class='letter-body'>{clean_letter}</div>", unsafe_allow_html=True)

                    st.write("---")
                    st.write("🛠️ **Что нужно исправить или добавить в это письмо?**")
                    user_feedback = st.text_area(
                        "Напишите ваши замечания для ИИ:",
                        key=f"fb_{v_id}",
                        placeholder="ИИ перепишет текст с учётом этого комментария..."
                    )

                    if st.button("✨ Перегенерировать письмо с учётом правок", key=f"btn_fb_{v_id}", width="stretch"):
                        if not user_feedback.strip():
                            st.warning("Пожалуйста, введите текст правки!")
                        else:
                            with st.spinner("ИИ перерабатывает сопроводительное письмо по вашим замечаниям..."):
                                success, error_msg = orchestrator.run_generation_process(v_id=v_id,
                                                                                         feedback_text=user_feedback,
                                                                                         proxy_url=ui_proxy)
                                if not success:
                                    st.error(f"Ошибка ИИ: {error_msg}")
                                    st.stop()
                            st.success("Письмо успешно обновлено!")
                            time.sleep(1)
                            st.rerun()
                else:
                    st.markdown(f"<div class='letter-body'>{content}</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.caption("Папка с готовыми письмами пока пуста.")
    else:
        st.warning("Локальная база данных пуста.")

with tab2:
    st.header("📈 Сравнительный анализ зарплатного рынка")
    st.write("---")
    col_graph1, col_stat2 = st.columns(2, gap="large")
    with col_graph1:
        st.subheader("💰 Что предлагают компании (Вакансии)")
        if not df_all.empty and 'salary_max' in df_all.columns and not df_all['salary_max'].isna().all():
            df_valid = df_all[df_all['salary_max'].notna()]
            m1, m2, m3 = st.columns(3)
            m1.metric("Минимум предложений", f"{int(df_valid['salary_min'].min()):,} ₽")
            m2.metric("Медиана рынка вакансий",
                      f"{int((df_valid['salary_min'].mean() + df_valid['salary_max'].mean()) // 2):,} ₽")
            m3.metric("Максимум предложений", f"{int(df_valid['salary_max'].max()):,} ₽")
            st.write("---")
            st.write("**Разброс вилок по компаниям:**")
            st.area_chart(df_valid.tail(15).set_index('company')[['salary_min', 'salary_max']])
        else:
            st.info("Пока нет собранных вакансий с открытыми зарплатными вилками.")
    with col_stat2:
        st.subheader("👥 Что просят конкуренты (Резюме)")
        st.write(f"Анализ ожиданий кандидатов по запросу: **{search_keyword}**")
        btn_analyze = st.button("📊 Просканировать и обновить базу соискателей", type="secondary", width="stretch")
        if btn_analyze:
            with st.spinner("Сбор и математическая группировка грейдов рынка..."):
                parser = HHParser(proxy_url=ui_proxy if ui_proxy.strip() else None)
                raw_salaries = parser.fetch_resume_analytics(search_keyword, area=area_opt)
                bins = [0, 80000, 130000, 180000, 250000, 1000000]
                labels = ["До 80к (Junior-)", "80к–130к (Junior+ / Middle)", "130к–180к (Middle+)",
                          "180к–250к (Senior)", "От 250к+ (Lead)"]
                df_res = pd.DataFrame(raw_salaries, columns=["salary"])
                df_res["Диапазон"] = pd.cut(df_res["salary"], bins=bins, labels=labels, include_lowest=True)
                total_candidates = len(df_res)
                summary = df_res["Диапазон"].value_counts().reindex(labels).reset_index()
                summary.columns = ["Грейд и диапазон", "Кандидатов (чел.)"]
                summary["Доля рынка (%)"] = ((summary["Кандидатов (чел.)"] / total_candidates) * 100).round(1)
                st.session_state['new_resume_stats'] = summary
        if 'new_resume_stats' in st.session_state:
            df_display = st.session_state['new_resume_stats']
            st.dataframe(df_display, width="stretch", hide_index=True)
            st.write("---")
            st.write("**Визуальное долевое распределение соискателей:**")
            chart_data = df_display.set_index("Грейд и диапазон")["Доля рынка (%)"]
            st.bar_chart(chart_data)
        else:
            st.info("Нажмите на кнопку выше, чтобы рассчитать процентные доли соискателей на рынке.")