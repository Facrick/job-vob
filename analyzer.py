import os
import logging
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


class CoverLetterGenerator:
    def __init__(self):
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            logging.error("Критическая ошибка: GROQ_API_KEY не найден в переменных окружения (.env)!")
            self.groq_client = None
        else:
            self.groq_client = Groq(api_key=groq_key)

        self.primary_model = "llama-3.3-70b-versatile"
        self.fallback_model = "llama-3.1-8b-instant"

    def _execute_json_request(self, prompt, system_message, model_name):
        if not self.groq_client:
            return '{"letter": "Ошибка конфигурации API", "recommendations": []}'

        chat_completion = self.groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            model=model_name,
            temperature=0.2,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )
        return chat_completion.choices[0].message.content.strip()

    def generate(self, resume_text, vacancy_title, company_name, description):
        """Первичная генерация структурированного JSON-пакета"""
        system_msg = (
            "Ты — карьерный робот-аналитик. Ты анализируешь вакансии и пишешь сопроводительные письма. "
            "Ты общаешься с бэкендом СТРОГО через JSON. Внутри поля 'letter' запрещено использовать "
            "маркеры списков (-, *, •) и писать советы по обучению."
        )

        prompt = f"""
        На основе резюме кандидата и описания вакансии "{vacancy_title}" в компании "{company_name}" сформируй JSON-объект.

        Резюме соискателя:
        \"\"\"
        {resume_text}
        \"\"\"

        Описание вакансии:
        \"\"\"
        {description}
        \"\"\"

        Ответь СТРОГО в формате следующей JSON-структуры:
        {{
            "letter": "Связный текст сопроводительного письма (3-4 абзаца). Без списков, без советов, без упоминания того, что нужно подучить!",
            "recommendations": [
                "Пункт 1: Инструмент или тема, которую нужно повторить соискателю",
                "Пункт 2: Ещё один инструмент или пробел в знаниях под требования вакансии",
                "Пункт 3: На что сделать упор на техническом интервью"
            ]
        }}
        """
        try:
            return self._execute_json_request(prompt, system_msg, self.primary_model)
        except Exception as e:
            logging.warning(f"Сбой {self.primary_model}: {e}. Переключаюсь на резерв...")
            try:
                return self._execute_json_request(prompt, system_msg, self.fallback_model)
            except Exception as ex:
                logging.error(f"Полный сбой Groq: {ex}")
                fallback_data = {
                    "letter": "Не удалось автоматически сгенерировать письмо из-за сбоя ИИ.",
                    "recommendations": ["Изучите требования вакансии самостоятельно."]
                }
                return json.dumps(fallback_data)

    def regenerate_with_feedback(self, old_letter, feedback, vacancy_title, description):
        """Правка текстовой части письма по фидбеку"""
        system_msg = "Ты правишь текст письма по фидбеку. Ты возвращаешь JSON с единственным ключом 'letter'."

        prompt = f"""
        Скорректируй сопроводительное письмо на вакансию "{vacancy_title}" на основе замечаний соискателя.

        Описание вакансии: {description}
        Текущая версия письма: {old_letter}
        Замечания пользователя: 👉 "{feedback}"

        Верни ответ строго в формате JSON:
        {{
            "letter": "Полный обновленный связный текст сопроводительного письма с учетом правок."
        }}
        """
        try:
            return self._execute_json_request(prompt, system_msg, self.primary_model)
        except Exception:
            try:
                return self._execute_json_request(prompt, system_msg, self.fallback_model)
            except Exception:
                return json.dumps({"letter": old_letter})